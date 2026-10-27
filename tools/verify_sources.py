"""Resolve every identifier the product would print.

The failure mode this guards against is a citation that looks right and does
not exist. Each PMID, DOI and UniProt accession in the warehouse is resolved
against the issuing authority; anything that does not come back is reported so
it can be removed before it reaches a slide.

    python tools/verify_sources.py --sample 40
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f2c import warehouse  # noqa: E402

UNIPROT = "https://rest.uniprot.org/uniprotkb/{}.json?fields=accession"
PUBMED = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    "?db=pubmed&retmode=json&id={}"
)
# Resolved against Crossref's registry rather than doi.org, which redirects to
# the publisher -- and publishers return 403 to scripts, which would look
# exactly like a fabricated DOI. Crossref answers for the registration itself.
CROSSREF = "https://api.crossref.org/works/{}"
UA = {"User-Agent": "fragment-to-catalyst/verify (research prototype)"}


def _ok(
    url: str, timeout: int = 25, method: str = "GET", retries: int = 3
) -> tuple[bool, str]:
    """Fetch with backoff, so a rate limit is never mistaken for a bad id."""
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=UA, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= resp.status < 400, str(resp.status)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return False, f"HTTP {exc.code}"
        except Exception as exc:  # network conditions vary; report, do not crash
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return False, type(exc).__name__
    return False, "exhausted retries"


def check_uniprot(acc: str) -> tuple[bool, str]:
    return _ok(UNIPROT.format(urllib.parse.quote(acc)))


def check_pmid(pmid: str) -> tuple[bool, str]:
    """esummary answers 200 even for an unknown id, so inspect the payload."""
    url = PUBMED.format(urllib.parse.quote(pmid))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=25
            ) as resp:
                payload = json.loads(resp.read())
            record = payload.get("result", {}).get(pmid, {})
            if record.get("error") or not record.get("title"):
                return False, "not found in PubMed"
            return True, record["title"][:70]
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2.0 * (attempt + 1))
                continue
            return False, f"HTTP {exc.code}"
        except Exception as exc:
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            return False, type(exc).__name__
    return False, "exhausted retries"


def check_doi(doi: str) -> tuple[bool, str]:
    suffix = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    return _ok(CROSSREF.format(urllib.parse.quote(suffix, safe="/")))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 3}


def check_title_agreement(pmid: str, claimed_title: str) -> tuple[bool, str]:
    """Does the PMID actually point at the paper the source says it does?

    Existence is not enough. A database can carry a real PMID attached to the
    wrong paper, and that citation looks perfect right up until someone opens
    it. Comparing titles is what catches it.
    """
    ok, detail = check_pmid(pmid)
    if not ok:
        return False, detail
    actual = detail
    claimed, real = _words(claimed_title), _words(actual)
    if not claimed or not real:
        return True, "no title to compare"
    overlap = len(claimed & real) / min(len(claimed), len(real))
    if overlap < 0.3:
        return False, f"points at: {actual!r}"
    return True, f"{overlap:.0%} title overlap"


def _verify_brenda_titles(
    subset_path: Path, pause: float, sample: int, seed: int
) -> int:
    """Check that every BRENDA reference's PMID really is that paper."""
    subset = json.loads(subset_path.read_text())
    pairs: list[tuple[str, str, str]] = []
    for ec, entry in subset["data"].items():
        for ref in (entry.get("reference") or {}).values():
            if ref.get("pmid") and ref.get("title"):
                pairs.append((ec, str(ref["pmid"]), ref["title"]))

    seen: set[str] = set()
    unique = []
    for ec, pmid, title in pairs:
        if pmid not in seen:
            seen.add(pmid)
            unique.append((ec, pmid, title))

    if sample:
        unique = random.Random(seed).sample(unique, min(sample, len(unique)))

    print(f"BRENDA references: checking {len(unique)} PMID/title pairs\n")
    mismatches = []
    for ec, pmid, title in unique:
        ok, detail = check_title_agreement(pmid, title)
        if not ok:
            mismatches.append((ec, pmid, title, detail))
            print(f"  MISMATCH  EC {ec}  PMID {pmid}")
            print(f"    BRENDA says : {title[:88]}")
            print(f"    PubMed says : {detail[:88]}")
        time.sleep(pause)

    # Feed the result back into ingest. The digit/year heuristic in
    # brenda.suspect_references is a cheap pre-filter and misses the case that
    # matters most: a well-formed, real PMID attached to the wrong paper. Only
    # resolving the id catches that, so what resolving found is written down.
    blocklist = subset_path.parent / "bad_references.json"
    if not sample:
        blocklist.write_text(
            json.dumps(
                {
                    "checked_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    "checked": len(unique),
                    "pmids": sorted({pmid for _, pmid, _, _ in mismatches}),
                    "detail": [
                        {"ec": ec, "pmid": pmid, "claimed_title": title, "actual": detail}
                        for ec, pmid, title, detail in mismatches
                    ],
                },
                indent=2,
            )
        )
        print(f"\nwrote {blocklist}")

    print("\n" + "=" * 60)
    print(f"{len(unique) - len(mismatches)}/{len(unique)} references check out")
    if mismatches:
        print(f"{len(mismatches)} reference(s) point at a different paper.")
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=warehouse.DEFAULT_STORE)
    ap.add_argument("--sample", type=int, default=0, help="0 = check everything")
    ap.add_argument("--pause", type=float, default=0.12)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--brenda-titles",
        type=Path,
        default=None,
        help="BRENDA subset.json: check each reference's PMID points at that paper",
    )
    args = ap.parse_args()

    if args.brenda_titles:
        return _verify_brenda_titles(args.brenda_titles, args.pause, args.sample, args.seed)

    proteins = warehouse.load(args.store)

    accessions = sorted({p.uniprot_accession for p in proteins if p.uniprot_accession})
    pmids = sorted(
        {
            o.evidence.pmid
            for p in proteins
            for o in p.observations
            if o.evidence.pmid
        }
    )
    dois = sorted(
        {
            lit["doi"]
            for p in proteins
            for lit in p.literature
            if lit.get("doi")
        }
    )

    rng = random.Random(args.seed)
    if args.sample:
        accessions = rng.sample(accessions, min(args.sample, len(accessions)))
        pmids = rng.sample(pmids, min(args.sample, len(pmids)))
        dois = rng.sample(dois, min(args.sample, len(dois)))

    failures: list[str] = []
    for label, items, check in (
        ("UniProt", accessions, check_uniprot),
        ("PMID", pmids, check_pmid),
        ("DOI", dois, check_doi),
    ):
        print(f"\n{label}: checking {len(items)}")
        bad = 0
        for item in items:
            ok, detail = check(item)
            if not ok:
                bad += 1
                failures.append(f"{label} {item}: {detail}")
                print(f"  FAIL {item}  {detail}")
            time.sleep(args.pause)
        print(f"  {len(items) - bad}/{len(items)} resolved")

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} identifier(s) did not resolve:")
        for f in failures:
            print("  -", f)
        return 1
    print("every identifier resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
