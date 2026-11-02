"""Build the single page from its two payloads.

The project shipped three separate surfaces: a decision page, a structure
viewer, and a review dashboard. A clinician looking at a fragment should not
have to know which one answers their question, so the first two fold into one
file here. The review queue stays separate on purpose — it is a different job
for a different person, and it needs a database the page cannot carry.

Two payloads go in. `ui/decisions.json` is every material's decision; the
trimmed chain-A coordinates of 4CG1 are the structure. Both are inlined
rather than fetched, because the artifact sandbox blocks a page's own fetches
and a file:// copy has nowhere to fetch from either.

    python -m f2c.cli export-ui          # writes ui/decisions.json
    python tools/build_structure.py      # writes the trimmed PDB
    python -m tools.build_app            # writes ui/shrapmind.html
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "ui" / "app.html"
DECISIONS = ROOT / "ui" / "decisions.json"
PDB = ROOT / "data" / "raw" / "structures" / "4cg1_trimmed.pdb"
OUT = ROOT / "ui" / "shrapmind.html"


def _literal(text: str) -> str:
    """A JSON string literal safe to sit inside a <script> element.

    `</` has to be broken up: a browser ends the script at the first `</script`
    inside it, whatever the quoting, and a PDB file or a paper title can carry
    that sequence.
    """
    return json.dumps(text).replace("</", "<\\/")


def main() -> int:
    if not TEMPLATE.exists():
        print(f"missing {TEMPLATE}", file=sys.stderr)
        return 1
    if not DECISIONS.exists():
        print("missing ui/decisions.json — run `python -m f2c.cli export-ui` first",
              file=sys.stderr)
        return 1

    html = TEMPLATE.read_text()
    data = DECISIONS.read_text()

    if PDB.exists():
        pdb = _literal(PDB.read_text())
        structure_note = f"structure inlined ({PDB.stat().st_size / 1024:.0f} KB)"
    else:
        # The page already hides the viewer when PDB is null, so a build
        # without coordinates is degraded rather than broken. Say so, because
        # a silently missing structure is the kind of absence nobody notices.
        pdb = "null"
        structure_note = ("no structure: run `python tools/build_structure.py` "
                          "for the viewer")

    for marker, value in (
        ("window.__DATA__", data.replace("</", "<\\/")),
        ("window.__PDB__", pdb),
    ):
        if marker not in html:
            print(f"marker {marker} not found in {TEMPLATE}", file=sys.stderr)
            return 1
        html = html.replace(marker, value, 1)

    OUT.write_text(html)
    materials = len(json.loads(data)["decisions"])
    print(f"wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, "
          f"{materials} materials, {structure_note})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
