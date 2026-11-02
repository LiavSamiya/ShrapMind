"""Build the metal-enzyme candidate set, the way PAZy gave us the polymer one.

There is no PAZy for metals. What there is instead is an EC class: 1.16,
"oxidoreductases acting on metal ions", and under it 1.16.3.1, ferroxidase.
That is the systematic handle, and querying it is how this set is assembled
rather than recalled.

Served through the EBI Proteins API rather than UniProt's own REST endpoint.
Both serve UniProtKB; on the day this was written uniprot.org returned 500 for
every request and ebi.ac.uk answered normally, so the fallback is the primary
here. Both are recorded in the manifest so a later run can tell which answered.

What came back reframed the whole arm. EC 1.16.3.1 is dominated by ferritins,
and a ferritin is not merely an oxidase: it oxidises Fe(II) and stores the
Fe(III) inside its own shell. The metal arm had oxidation and capture as
separate stages and listed "fuse the oxidase to the chelator" as an
engineering target. Ferritin is already that fusion, it is human, and it works
at the pH of human cytosol rather than at the pH 2 an acidophile's enzyme
needs.

    python -m tools.fetch_metal_candidates
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "metal_candidates.json"

UA = {"User-Agent": "shrapmind (liav.s123@gmail.com)", "Accept": "application/json"}
EBI = "https://www.ebi.ac.uk/proteins/api/proteins"
UNIPROT = "https://rest.uniprot.org/uniprotkb/search"

# What to ask for, and what each query is for. A query that returns nothing is
# recorded as such: an empty class is a finding about the biology, not a bug.
QUERIES = [
    ("ferroxidase", {"ec": "1.16.3.1"},
     "Fe(II) -> Fe(III). The class that matters most, because iron is the "
     "commonest fragment metal."),
    ("ferroxidase_bacterial", {"ec": "1.16.3.2"},
     "Bacterial non-heme ferritins, the prokaryotic equivalent."),
    ("metal_nadp", {"ec": "1.16.1.-"},
     "Metal ion reduction with NAD(P)+ as acceptor -- the reverse direction, "
     "listed to show it was looked at."),
    ("multicopper_oxidase", {"ec": "1.10.3.2"},
     "Laccase-class multicopper oxidases, which handle copper and some other "
     "metals."),
]


def fetch(params: dict[str, str], size: int = 200, tries: int = 4):
    """EBI first, UniProt as the fallback. Returns (rows, which_source)."""
    q = urllib.parse.urlencode({**params, "size": size, "reviewed": "true"})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(f"{EBI}?{q}", headers=UA)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp), "ebi.ac.uk/proteins"
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return [], "ebi.ac.uk/proteins"
        except Exception:  # noqa: BLE001
            pass
        if attempt < tries - 1:
            time.sleep(2 ** (attempt + 2))

    ec = params.get("ec")
    if ec:
        q2 = urllib.parse.urlencode({
            "query": f"ec:{ec} AND reviewed:true", "size": min(size, 100),
            "fields": "accession,protein_name,organism_name,ec,xref_pdb",
        })
        try:
            req = urllib.request.Request(f"{UNIPROT}?{q2}", headers=UA)
            with urllib.request.urlopen(req, timeout=90) as resp:
                return json.load(resp).get("results", []), "rest.uniprot.org"
        except Exception:  # noqa: BLE001
            pass
    return None, None


def _name(entry: dict) -> str:
    # The two APIs nest the name differently; handle both rather than assume
    # which one answered.
    prot = entry.get("protein") or entry.get("proteinDescription") or {}
    rec = prot.get("recommendedName") or {}
    full = rec.get("fullName") or {}
    if isinstance(full, dict) and full.get("value"):
        return full["value"]
    sub = prot.get("submittedName") or prot.get("submissionNames") or []
    if sub:
        return ((sub[0].get("fullName") or {}).get("value")) or "?"
    return "?"


def _organism(entry: dict) -> str:
    org = entry.get("organism") or {}
    if org.get("scientificName"):
        return org["scientificName"]
    names = org.get("names") or []
    return names[0].get("value", "?") if names else "?"


def _pdbs(entry: dict) -> list[str]:
    refs = entry.get("dbReferences") or entry.get("uniProtKBCrossReferences") or []
    out = []
    for ref in refs:
        if (ref.get("type") or ref.get("database")) == "PDB":
            out.append(ref.get("id", ""))
    return [p for p in out if p]


def main() -> int:
    collected: dict[str, dict] = {}
    report: dict[str, dict] = {}

    for label, params, purpose in QUERIES:
        rows, source = fetch(params)
        if rows is None:
            report[label] = {"purpose": purpose, "status": "unreachable",
                             "note": "both UniProt and the EBI mirror refused"}
            print(f"  {label}: unreachable", file=sys.stderr)
            continue
        report[label] = {"purpose": purpose, "status": "ok",
                         "source": source, "returned": len(rows)}
        print(f"  {label}: {len(rows)} via {source}")
        for entry in rows:
            acc = entry.get("accession") or entry.get("primaryAccession")
            if not acc:
                continue
            rec = collected.setdefault(acc, {
                "accession": acc,
                "name": _name(entry),
                "organism": _organism(entry),
                "pdb_ids": _pdbs(entry),
                "classes": [],
            })
            if label not in rec["classes"]:
                rec["classes"].append(label)
        time.sleep(1)

    payload = {
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "queries": report,
        "candidates": sorted(collected.values(), key=lambda r: r["accession"]),
        "note": (
            "Assembled from EC classes rather than from a curated list, because "
            "no PAZy equivalent exists for metals. Every entry here is reviewed "
            "in Swiss-Prot and none has been tested against a fragment in "
            "tissue -- these are candidates, at literature level, exactly as "
            "the polymer arm would label them."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))

    human = [c for c in payload["candidates"] if c["organism"] == "Homo sapiens"]
    structured = [c for c in payload["candidates"] if c["pdb_ids"]]
    print(f"\nwrote {OUT} ({len(payload['candidates'])} candidates)")
    print(f"  human: {len(human)}   with a structure: {len(structured)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
