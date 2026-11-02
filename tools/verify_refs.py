"""Check the hand-written references against NCBI.

tools/verify_sources.py resolves every identifier in the warehouse, which is
imported data. The references in f2c/pipeline.py and f2c/metals.py are not
imported -- they were typed -- and nothing checked them. That gap produced
seven fabricated DOIs and two fabricated titles in the metal arm, including a
ceruloplasmin citation that pointed at a paper about ferritin structure.

The project caught BRENDA shipping three wrong citations out of 1024 and then
shipped seven of its own, so this runs over the typed references with the same
severity: resolve the PMID, compare the stored title against the real one, and
compare the stored DOI against the one NCBI records.

    python -m tools.verify_refs
    python -m tools.verify_refs --fix     # rewrite DOIs that NCBI contradicts
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "shrapmind-verify (liav.s123@gmail.com)"}
ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# How much of the stored title's distinctive vocabulary must appear in NCBI's.
# Below this the stored title is describing a different paper.
TITLE_OVERLAP_FLOOR = 0.40


def collect() -> dict[str, dict]:
    """Every typed reference, keyed by PMID."""
    from f2c import metals, pipeline

    out: dict[str, dict] = {}
    for module, label in ((pipeline, "pipeline"), (metals, "metals")):
        for key, ref in getattr(module, "REFS", {}).items():
            out.setdefault(ref.get("pmid", ""), {
                "pmid": ref.get("pmid", ""),
                "doi": ref.get("doi", ""),
                "title": ref.get("title", ""),
                "where": f"{label}.REFS[{key!r}]",
            })
    return out


def fetch(pmids: list[str]) -> dict:
    url = f"{ESUMMARY}?db=pubmed&retmode=json&id={','.join(pmids)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=UA), timeout=60) as resp:
                return json.load(resp).get("result", {})
        except Exception:  # noqa: BLE001
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 2))
    return {}


def _words(text: str) -> set[str]:
    return {w.lower().strip(".,:;()[]") for w in text.split() if len(w) > 4}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fix", action="store_true",
                    help="rewrite DOIs that NCBI contradicts, in place")
    args = ap.parse_args()

    refs = collect()
    empty = [r for pmid, r in refs.items() if not pmid or not r["doi"]]
    for r in empty:
        print(f"  EMPTY  {r['where']}: pmid={r['pmid']!r} doi={r['doi']!r}")
        print("         A reference with no identifier renders a dead link. If "
              "it records a negative result, it is not a reference.")

    pmids = [p for p in refs if p]
    if not pmids:
        print("no references to check", file=sys.stderr)
        return 1
    records = fetch(pmids)

    problems: list[tuple[str, str, str]] = []
    for pmid in sorted(pmids):
        ref = refs[pmid]
        rec = records.get(pmid)
        if not rec or rec.get("error"):
            print(f"  GONE   {pmid}  does not resolve  ({ref['where']})")
            problems.append((pmid, "", "unresolvable"))
            continue

        real_title = (rec.get("title") or "").rstrip(".")
        real_doi = next((a["value"] for a in rec.get("articleids", [])
                         if a.get("idtype") == "doi"), "")
        want = _words(ref["title"])
        overlap = len(want & _words(real_title)) / max(len(want), 1)
        doi_ok = (not real_doi) or real_doi.lower() == ref["doi"].lower()

        if overlap < TITLE_OVERLAP_FLOOR:
            print(f"  TITLE  {pmid}  stored title describes a different paper")
            print(f"         stored: {ref['title'][:94]}")
            print(f"         NCBI  : {real_title[:94]}")
            print(f"         at    : {ref['where']}")
            problems.append((pmid, real_doi, "title"))
        elif not doi_ok:
            print(f"  DOI    {pmid}  stored {ref['doi']}  NCBI {real_doi}")
            print(f"         at    : {ref['where']}")
            problems.append((pmid, real_doi, "doi"))

    if args.fix:
        fixed = 0
        for module in ("f2c/pipeline.py", "f2c/metals.py"):
            path = ROOT / module
            text = path.read_text()
            for pmid, real_doi, kind in problems:
                if kind != "doi" or not real_doi:
                    continue
                stored = refs[pmid]["doi"]
                pattern = f'"{pmid}", "{re.escape(stored)}"'
                if re.search(pattern, text):
                    text = re.sub(pattern, f'"{pmid}", "{real_doi}"', text)
                    fixed += 1
            path.write_text(text)
        print(f"\nrewrote {fixed} DOI(s). A wrong title is not auto-fixable: "
              "the citation has to be re-chosen by hand, because a paper that "
              "does not say what it was cited for cannot be repaired by editing "
              "its identifier.")

    total = len(problems) + len(empty)
    print(f"\n{len(pmids)} references checked, {total} problem(s)")
    if total and not args.fix:
        print("run with --fix to correct the DOIs; titles need a human")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
