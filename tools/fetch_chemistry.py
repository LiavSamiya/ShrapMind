#!/usr/bin/env python3
"""Resolve compound identity, physical properties and GHS hazard.

The simulator's mesh-hindrance term and its product-hazard gate both depend on
per-compound data that nothing in this project previously sourced. This script
fills that gap from PubChem (identity, formula, weight, SMILES, InChIKey, GHS)
and ChEBI via OLS4 (names and formulas behind the ChEBI ids the enzyme
warehouse already carries).

Offline it is a no-op that leaves the committed snapshot untouched: the run
reports which hosts it could not reach and exits non-zero, rather than writing
a half-resolved snapshot or inventing values.

    python tools/fetch_chemistry.py              # resolve everything
    python tools/fetch_chemistry.py --only mhet ethylene_glycol
    python tools/fetch_chemistry.py --hazard-only
    python tools/fetch_chemistry.py --dry-run    # show what would be fetched

NETWORK
    Needs pubchem.ncbi.nlm.nih.gov and www.ebi.ac.uk. A restricted cloud
    environment will refuse both; add them under Allowed domains in the
    environment's network settings.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from f2c.sources import chemistry as C  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", metavar="KEY",
                    help="resolve only these compound keys")
    ap.add_argument("--hazard-only", action="store_true",
                    help="only refresh GHS classification")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pause", type=float, default=0.25,
                    help="seconds between requests (be polite to PubChem)")
    ap.add_argument("--store", default=None, help="snapshot path")
    args = ap.parse_args(argv)

    store = C.load(args.store)
    keys = list(args.only) if args.only else sorted(store)
    unknown = [k for k in keys if k not in store]
    if unknown:
        print(f"unknown compound keys: {', '.join(unknown)}", file=sys.stderr)
        print(f"known: {', '.join(sorted(store))}", file=sys.stderr)
        return 2

    # Things with no molecular identity cannot be resolved against a chemical
    # database, and asking would be meaningless.
    skip = {"microparticle", "oligomer", "metal_ion"}
    targets = [k for k in keys if k not in skip]

    if args.dry_run:
        print(f"would resolve {len(targets)} compounds against "
              f"PubChem{'' if args.hazard_only else ' and ChEBI'}:")
        for k in targets:
            c = store[k]
            print(f"  {k:<24} {c.name:<40} level={c.level} "
                  f"hazard={'resolved' if c.hazard_resolved else 'unresolved'}")
        print(f"skipping (no molecular identity): {', '.join(sorted(skip & set(keys)))}")
        return 0

    resolved = hazard_done = failed = 0
    for key in targets:
        c = store[key]
        before = (c.level, c.hazard_resolved)
        if not args.hazard_only:
            c = C.fetch_pubchem(c)
            if c.chebi_id and c.level != "resolved":
                c = C.fetch_chebi(c)
            time.sleep(args.pause)
        if c.pubchem_cid:
            c = C.fetch_ghs(c)
            time.sleep(args.pause)
        c.retrieved_at = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        store[key] = c
        if c.level == "resolved" and before[0] != "resolved":
            resolved += 1
        if c.hazard_resolved and not before[1]:
            hazard_done += 1
        if c.level != "resolved" and not c.hazard_resolved:
            failed += 1
            print(f"  could not reach a database for {key}", file=sys.stderr)
        else:
            flags = []
            if c.level == "resolved":
                flags.append(f"CID {c.pubchem_cid}")
            if c.hazard_resolved:
                flags.append(f"GHS {','.join(c.ghs_codes or []) or 'none recorded'}")
            print(f"  {key:<24} {' | '.join(flags)}")

    if failed == len(targets):
        print("\nNothing could be resolved - every request failed.", file=sys.stderr)
        print("This is almost certainly the network policy, not the script: "
              "PubChem and EBI must be allowed outbound. The committed snapshot "
              "has been left untouched.", file=sys.stderr)
        return 1

    path = C.save(store, args.store)
    print(f"\nwrote {path}")
    print(f"identity resolved: {resolved}   hazard resolved: {hazard_done}   "
          f"unreachable: {failed}")
    if failed:
        print("Partially resolved. Unreachable compounds keep their previous "
              "values and stay labelled accordingly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
