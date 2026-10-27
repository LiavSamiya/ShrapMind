"""Download every source the engine can reach, once, into data/raw/.

After this runs the engine works offline: the build reads local files and the
network is only needed to refresh. Each source writes a manifest entry
recording what was pulled, when, and under what licence, because provenance
that stops at the database name is not provenance.

    python tools/fetch_sources.py            # everything reachable
    python tools/fetch_sources.py --only mcsa interpro
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f2c import warehouse  # noqa: E402
from f2c.sources import pazy  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
UA = {"User-Agent": "fragment-to-catalyst/fetch (research prototype)", "Accept": "application/json"}

# Sources the manifest names but which cannot be pulled unattended, and why.
BLOCKED = {
    "brenda": (
        "data is CC BY 4.0, but the download requires actively ticking the licence "
        "box on brenda-enzymes.org/download.php -- an acceptance that has to be "
        "made by a person, not a script"
    ),
    "sabio_rk": "REST service returns the web application, not data, from this network",
    "fireprotdb": "documented API paths return 404; endpoint needs confirming",
    "rhea": "direct JSON blocked (403); Rhea ids are captured via UniProt instead",
}

# CAZy publishes one flat archive and asks to be cited rather than gating access.
CAZY_URL = "https://www.cazy.org/IMG/cazy_data/cazy_data.zip"


def get(url: str, timeout: int = 40, retries: int = 3) -> bytes | None:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            return None
        except Exception:
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
    return None


def cached(path: Path, url: str, pause: float = 0.2) -> bool:
    """Fetch `url` into `path` unless already present. True if the file exists."""
    if path.exists():
        return True
    payload = get(url)
    if payload is None:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    time.sleep(pause)
    return True


# --- individual sources -------------------------------------------------

def fetch_pazy() -> dict:
    path = RAW / "pazy_proteins.json"
    if not path.exists():
        pazy.fetch(path)
    records = pazy.load(path)
    return {"records": len(records), "file": str(path.relative_to(ROOT))}


def fetch_mcsa(page_size: int = 100) -> dict:
    """The full M-CSA catalytic-mechanism set, paginated."""
    out = RAW / "mcsa"
    out.mkdir(parents=True, exist_ok=True)
    url = (
        "https://www.ebi.ac.uk/thornton-srv/m-csa/api/entries/"
        f"?format=json&page_size={page_size}"
    )
    total, page = 0, 1
    while url:
        dest = out / f"entries_p{page}.json"
        if not cached(dest, url):
            break
        payload = json.loads(dest.read_text())
        total += len(payload.get("results", []))
        url = payload.get("next")
        page += 1
    return {"entries": total, "pages": page - 1, "dir": str(out.relative_to(ROOT))}


def fetch_per_accession(accessions: list[str], name: str, template: str) -> dict:
    out = RAW / name
    ok = 0
    for acc in accessions:
        if cached(out / f"{acc}.json", template.format(acc=urllib.parse.quote(acc))):
            ok += 1
    return {"requested": len(accessions), "retrieved": ok, "dir": str(out.relative_to(ROOT))}


def fetch_pdb(pdb_ids: list[str]) -> dict:
    out = RAW / "pdb"
    ok = 0
    for pid in pdb_ids:
        if cached(
            out / f"{pid}.json",
            f"https://data.rcsb.org/rest/v1/core/entry/{urllib.parse.quote(pid)}",
            pause=0.12,
        ):
            ok += 1
    return {"requested": len(pdb_ids), "retrieved": ok, "dir": str(out.relative_to(ROOT))}


def fetch_cazy() -> dict:
    """The CAZy family assignments archive.

    These are family memberships, not measured activities, so downstream they
    are features that widen the candidate pool -- never activity labels.
    """
    dest = RAW / "cazy" / "cazy_data.zip"
    if not cached(dest, CAZY_URL):
        return {"retrieved": False, "reason": "download failed"}
    import zipfile

    with zipfile.ZipFile(dest) as archive:
        members = archive.namelist()
        uncompressed = sum(archive.getinfo(n).file_size for n in members)
    return {
        "retrieved": True,
        "file": str(dest.relative_to(ROOT)),
        "members": members,
        "uncompressed_bytes": uncompressed,
        "content": "family assignments (feature, not activity label)",
        "terms": "no access gate; CAZy asks to be cited",
    }


def fetch_chebi(chebi_ids: list[str]) -> dict:
    out = RAW / "chebi"
    ok = 0
    for cid in chebi_ids:
        dest = out / f"{cid.replace(':', '_')}.json"
        url = (
            "https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms"
            f"?obo_id={urllib.parse.quote(cid)}"
        )
        if cached(dest, url, pause=0.15):
            ok += 1
    return {"requested": len(chebi_ids), "retrieved": ok, "dir": str(out.relative_to(ROOT))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--max-pdb", type=int, default=400)
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "fetched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "sources": {},
        "unavailable": BLOCKED,
    }

    def want(name: str) -> bool:
        return args.only is None or name in args.only

    if want("pazy"):
        print("PAZy ...", flush=True)
        manifest["sources"]["pazy"] = fetch_pazy()

    # Everything below keys off what the warehouse already holds.
    proteins = warehouse.load() if warehouse.DEFAULT_STORE.exists() else []
    accessions = sorted({p.uniprot_accession for p in proteins if p.uniprot_accession})
    pdb_ids = sorted({pid for p in proteins for pid in p.pdb_ids})[: args.max_pdb]
    chebi_ids = sorted({c for p in proteins for c in p.chebi_ids})

    if want("mcsa"):
        print("M-CSA ...", flush=True)
        manifest["sources"]["mcsa"] = fetch_mcsa()

    if want("interpro"):
        print(f"InterPro ({len(accessions)}) ...", flush=True)
        manifest["sources"]["interpro"] = fetch_per_accession(
            accessions,
            "interpro",
            "https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{acc}/",
        )

    if want("alphafold"):
        print(f"AlphaFold ({len(accessions)}) ...", flush=True)
        manifest["sources"]["alphafold"] = fetch_per_accession(
            accessions,
            "alphafold",
            "https://alphafold.ebi.ac.uk/api/prediction/{acc}",
        )

    if want("pdb"):
        print(f"PDB ({len(pdb_ids)}) ...", flush=True)
        manifest["sources"]["pdb"] = fetch_pdb(pdb_ids)

    if want("chebi"):
        print(f"ChEBI ({len(chebi_ids)}) ...", flush=True)
        manifest["sources"]["chebi"] = fetch_chebi(chebi_ids)

    if want("cazy"):
        print("CAZy ...", flush=True)
        manifest["sources"]["cazy"] = fetch_cazy()

    path = RAW / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    print("\n" + json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
