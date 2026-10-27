"""Command line entry point.

    python -m f2c.cli build
    python -m f2c.cli stats
    python -m f2c.cli select --material PET --mass-mg 50 --crystallinity 35
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import warehouse
from .engine import decide
from .report import render
from .schema import MaterialSpec


def _add_material_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--material", required=True, help="polymer name or abbreviation")
    p.add_argument("--form", default="polymer", choices=["polymer", "oligomer", "film", "fibre", "powder"])
    p.add_argument("--mass-mg", type=float, default=None)
    p.add_argument("--crystallinity", type=float, default=None, help="percent")
    p.add_argument("--particle-size-mm", type=float, default=None)
    p.add_argument("--site", default="deep_muscle")
    p.add_argument("--store", type=Path, default=warehouse.DEFAULT_STORE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f2c", description="Fragment-to-Catalyst")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="pull sources and build the warehouse")
    b.add_argument("--store", type=Path, default=warehouse.DEFAULT_STORE)
    b.add_argument("--refresh", action="store_true", help="re-download PAZy")
    b.add_argument("--uniprot-limit", type=int, default=None)

    s = sub.add_parser("stats", help="describe the warehouse")
    s.add_argument("--store", type=Path, default=warehouse.DEFAULT_STORE)

    sel = sub.add_parser("select", help="choose the catalyst for a fragment")
    _add_material_args(sel)
    sel.add_argument("--json", action="store_true", help="emit JSON instead of text")

    args = parser.parse_args(argv)

    if args.command == "build":
        proteins = warehouse.build(
            store=args.store, refresh=args.refresh, uniprot_limit=args.uniprot_limit
        )
        print(json.dumps(warehouse.stats(proteins), indent=2))
        return 0

    if args.command == "stats":
        print(json.dumps(warehouse.stats(warehouse.load(args.store)), indent=2))
        return 0

    material = MaterialSpec(
        polymer=args.material,
        form=args.form,
        mass_mg=args.mass_mg,
        crystallinity_pct=args.crystallinity,
        particle_size_mm=args.particle_size_mm,
        site=args.site,
    )
    decision = decide(material, warehouse.load(args.store))
    if args.json:
        print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        print(render(decision))
    return 0 if decision.verdict == "enzyme_selected" else 2


if __name__ == "__main__":
    sys.exit(main())
