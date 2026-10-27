"""Inline the exported decisions into the page, ready to publish.

The payload is embedded rather than fetched so the page is complete in its
first frame: no empty shell while a request resolves, and nothing to break if
the data file is served from somewhere the page cannot reach.

    python tools/build_ui.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "ui" / "index.html"
PAYLOAD = ROOT / "ui" / "decisions.json"
OUT = ROOT / "ui" / "fragment-to-catalyst.html"

MARKER = "const DATA = window.__F2C__;"


def main() -> int:
    if not PAYLOAD.exists():
        print("No decisions.json. Run: python -m f2c.cli export-ui", file=sys.stderr)
        return 1

    html = TEMPLATE.read_text()
    data = json.loads(PAYLOAD.read_text())

    if MARKER not in html:
        print(f"Marker not found in {TEMPLATE}", file=sys.stderr)
        return 1

    # `</script>` inside the JSON would close the tag early and break the page.
    literal = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    OUT.write_text(html.replace(MARKER, f"const DATA = {literal};"))

    size_kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT} ({size_kb:.0f} KB, {len(data['decisions'])} materials)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
