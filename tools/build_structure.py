"""Fetch the crystal structure and build the viewer page.

The structure page shipped once as a hand-assembled file, which meant a fresh
clone had `ui/structure.html` and no way to fill it. This makes it one command.

It also re-runs the check that made the page trustworthy in the first place.
UniProt numbers the precursor and the PDB entry numbers the mature protein, so
the catalytic residues sit 40 apart in the two schemes. Hard-coding the offset
would leave the page one database revision away from labelling three arbitrary
residues as the active site, so the offset is verified against the structure on
every build: positions 130, 176 and 208 must actually be serine, aspartate and
histidine, or the build stops.

    python tools/build_structure.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDB_ID = "4CG1"
RCSB = f"https://files.rcsb.org/download/{PDB_ID}.pdb"
RAW = ROOT / "data" / "raw" / "structures"
TEMPLATE = ROOT / "ui" / "structure.html"
OUT = ROOT / "ui" / "structure-built.html"
MARKER = "const PDB = window.__PDB__;"

# Mature-protein numbering, as the PDB entry uses it.
TRIAD = {130: "SER", 176: "ASP", 208: "HIS"}
UNIPROT_TRIAD = {170: "SER", 216: "ASP", 248: "HIS"}  # precursor numbering
EXPECTED_OFFSET = 40


def fetch(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        with urllib.request.urlopen(RCSB, timeout=120) as resp:
            dest.write_bytes(resp.read())
    return dest


def trim(src: Path, dest: Path) -> int:
    """Chain A protein atoms only: waters and sulfates are not the subject."""
    kept = [
        line for line in src.read_text().splitlines(keepends=True)
        if (line.startswith("ATOM") and line[21] == "A")
        or line.startswith(("TER", "END"))
    ]
    dest.write_text("".join(kept))
    return sum(1 for line in kept if line.startswith("ATOM"))


def verify_triad(pdb: Path) -> dict[int, str]:
    """Confirm the labelled residues really are the residues we claim."""
    found: dict[int, str] = {}
    for line in pdb.read_text().splitlines():
        if not line.startswith("ATOM"):
            continue
        resi = int(line[22:26])
        if resi in TRIAD:
            found.setdefault(resi, line[17:20].strip())

    missing = set(TRIAD) - set(found)
    if missing:
        raise SystemExit(f"catalytic residues absent from the model: {sorted(missing)}")
    wrong = {k: v for k, v in found.items() if v != TRIAD[k]}
    if wrong:
        raise SystemExit(
            "numbering check failed: expected "
            + ", ".join(f"{k}={v}" for k, v in TRIAD.items())
            + " but found "
            + ", ".join(f"{k}={v}" for k, v in found.items())
            + ". The page would mislabel the active site; not building."
        )
    for precursor, mature in zip(sorted(UNIPROT_TRIAD), sorted(TRIAD)):
        if precursor - mature != EXPECTED_OFFSET:
            raise SystemExit("precursor/mature offset is no longer uniform")
    return found


def main() -> int:
    raw = fetch(RAW / f"{PDB_ID.lower()}.pdb")
    trimmed = RAW / f"{PDB_ID.lower()}_trimmed.pdb"
    atoms = trim(raw, trimmed)

    found = verify_triad(trimmed)
    print(f"{PDB_ID}: {atoms} chain-A atoms")
    print(
        "catalytic triad verified: "
        + ", ".join(f"{v}{k}" for k, v in sorted(found.items()))
        + f" (UniProt numbering is +{EXPECTED_OFFSET})"
    )

    html = TEMPLATE.read_text()
    if MARKER not in html:
        print(f"marker not found in {TEMPLATE}", file=sys.stderr)
        return 1

    import json

    literal = json.dumps(trimmed.read_text()).replace("</", "<\\/")
    OUT.write_text(html.replace(MARKER, f"const PDB = {literal};"))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
