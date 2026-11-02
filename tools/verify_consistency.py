"""Check what the published pages claim against what the engine computes.

tools/verify_sources.py checks imported warehouse data. tools/verify_refs.py
checks the hand-typed references. Neither checks the third failure mode, which
is the one that actually happened: a page states a figure, the engine changes,
and the page keeps stating the old figure. Nobody notices, because a stale
number looks exactly like a current one.

The Fragment-to-Catalyst Safety Review was written on 2026-10-27 and said the
warehouse's 289 catalytic constants broke down as 168 model esters, 42
oligomers and 58 unrecorded. Those sum to 268, not 289, and the engine says
180 / 47 / 62. It also quoted Proteinase K at 3509 s-1 as "the highest in the
dataset" when 3509 is the mean of its two measurements and the highest is
3654. And it described a host-safety screen as "now a gate" when no such code
existed.

So each page's load-bearing figures are declared here, beside the engine
expression that produces them, and a mismatch fails. A page is a claim; the
engine is the only thing entitled to settle it.

    python -m tools.verify_consistency
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _engine() -> dict[str, Any]:
    payload = ROOT / "ui" / "decisions.json"
    if not payload.exists():
        raise SystemExit("ui/decisions.json missing -- run "
                         "`python -m f2c.cli export-ui` first")
    return json.loads(payload.read_text())


def _pool(d: dict[str, Any], material: str) -> int | None:
    """The candidate count, as the decision's own rationale states it."""
    rec = d["decisions"].get(material)
    if not rec:
        return None
    m = re.search(r"from (\d+) enzymes", rec.get("rationale", ""))
    return int(m.group(1)) if m else None


def _selected(d: dict[str, Any], material: str) -> str | None:
    rec = d["decisions"].get(material) or {}
    return (rec.get("selected") or {}).get("name")


def _substrate_counts() -> dict[str, int]:
    from f2c import substrate, warehouse
    counts: dict[str, int] = {}
    for p in warehouse.load():
        for o in p.observations:
            if o.metric in substrate.KINETIC_METRICS:
                cls = substrate.classify((o.conditions or {}).get("substrate"))
                counts[cls] = counts.get(cls, 0) + 1
    return counts


def _kcat_values() -> list[float]:
    from f2c import warehouse
    return [o.value for p in warehouse.load() for o in p.observations
            if o.metric == "kcat" and o.value]


def _enzymes_with(metric: str) -> int:
    from f2c import warehouse
    return sum(1 for p in warehouse.load()
               if any(o.metric == metric for o in p.observations))


def _oligomer_enzymes() -> int:
    from f2c import substrate, warehouse
    names = set()
    for p in warehouse.load():
        for o in p.observations:
            if (o.metric in substrate.KINETIC_METRICS
                    and substrate.classify(
                        (o.conditions or {}).get("substrate")) == "oligomer"):
                names.add(p.name)
    return len(names)


# Each entry: the page, what it says, and how to compute the truth.
# `claimed` is transcribed from the published page by hand, which is the point:
# if someone edits the page they must edit this too, and if they edit only one
# the check fails.
CHECKS: list[dict[str, Any]] = [
    # --- Fragment-to-Catalyst Safety Review ------------------------------
    {"page": "safety-review", "what": "warehouse proteins",
     "claimed": 505, "truth": lambda d: d["warehouse"]["proteins"]},
    {"page": "safety-review", "what": "total observations",
     "claimed": 396,
     "truth": lambda d: sum(len(p.observations)
                            for p in __import__("f2c.warehouse",
                                                fromlist=["load"]).load())},
    {"page": "safety-review", "what": "catalytic constants",
     "claimed": 266, "truth": lambda d: d["kinetics_total"]},
    {"page": "safety-review", "what": "constants on model esters",
     "claimed": 180, "truth": lambda d: _substrate_counts().get("model")},
    {"page": "safety-review", "what": "constants on oligomers",
     "claimed": 44, "truth": lambda d: _substrate_counts().get("oligomer")},
    {"page": "safety-review", "what": "constants with no substrate recorded",
     "claimed": 42, "truth": lambda d: _substrate_counts().get("unknown")},
    {"page": "safety-review", "what": "constants measured on solid polymer",
     "claimed": 0, "truth": lambda d: _substrate_counts().get("polymer", 0)},
    {"page": "safety-review", "what": "enzymes with any kcat",
     "claimed": 8, "truth": lambda d: _enzymes_with("kcat")},
    {"page": "safety-review", "what": "enzymes with a measured half-life",
     "claimed": 0, "truth": lambda d: _enzymes_with("half_life_h")},
    {"page": "safety-review", "what": "enzymes with an oligomer-level constant",
     "claimed": 6, "truth": lambda d: _oligomer_enzymes()},
    {"page": "safety-review", "what": "highest kcat in the warehouse",
     "claimed": 3654.0, "truth": lambda d: max(_kcat_values())},
    {"page": "safety-review", "what": "host screen: blocking",
     "claimed": 6, "truth": lambda d: d["host_safety"]["counts"]["blocking"]},
    {"page": "safety-review", "what": "host screen: serious",
     "claimed": 10, "truth": lambda d: d["host_safety"]["counts"]["serious"]},
    {"page": "safety-review", "what": "host screen: caution",
     "claimed": 32, "truth": lambda d: d["host_safety"]["counts"]["caution"]},
    {"page": "safety-review", "what": "host screen: nothing flagged",
     "claimed": 457, "truth": lambda d: d["host_safety"]["counts"]["unflagged"]},
    # Candidate pools, per material.
    {"page": "safety-review", "what": "PET pool",
     "claimed": 323, "truth": lambda d: _pool(d, "PET")},
    {"page": "safety-review", "what": "PA pool",
     "claimed": 62, "truth": lambda d: _pool(d, "PA")},
    {"page": "safety-review", "what": "PLA pool",
     "claimed": 50, "truth": lambda d: _pool(d, "PLA")},
    {"page": "safety-review", "what": "PHA pool",
     "claimed": 22, "truth": lambda d: _pool(d, "PHA")},
    {"page": "safety-review", "what": "PBS pool",
     "claimed": 19, "truth": lambda d: _pool(d, "PBS")},
    {"page": "safety-review", "what": "PEF pool",
     "claimed": 7, "truth": lambda d: _pool(d, "PEF")},
    {"page": "safety-review", "what": "PC pool",
     "claimed": 10, "truth": lambda d: _pool(d, "PC")},
    {"page": "safety-review", "what": "PUR pool",
     "claimed": 55, "truth": lambda d: _pool(d, "PUR")},
    {"page": "safety-review", "what": "PBAT pool",
     "claimed": 23, "truth": lambda d: _pool(d, "PBAT")},
    {"page": "safety-review", "what": "NR pool",
     "claimed": 8, "truth": lambda d: _pool(d, "NR")},
    # Which candidate each material actually selects. These are what drifted
    # furthest, because the ranking changed twice after the page was written.
    {"page": "safety-review", "what": "PET selection",
     "claimed": "Cut190", "truth": lambda d: _selected(d, "PET")},
    {"page": "safety-review", "what": "PA selection",
     "claimed": "NylC", "truth": lambda d: _selected(d, "PA")},
    {"page": "safety-review", "what": "PLA selection",
     "claimed": "Cutinase", "truth": lambda d: _selected(d, "PLA")},
    {"page": "safety-review", "what": "PC selection",
     "claimed": "PHL-7", "truth": lambda d: _selected(d, "PC")},
    {"page": "safety-review", "what": "PBAT selection",
     "claimed": "PLE628", "truth": lambda d: _selected(d, "PBAT")},

    # --- ShrapMind, metal arm --------------------------------------------
    {"page": "shrapmind", "what": "mg DFO per mg iron",
     "claimed": 10.04,
     "truth": lambda d: round(
         d["metals"]["capacity_constants"]["dfo_g_per_mol"]
         / d["metals"]["capacity_constants"]["fe_g_per_mol"], 2)},
    {"page": "shrapmind", "what": "carrier lifetime, weeks",
     "claimed": 8.0, "truth": lambda d: d["metals"]["carrier_lifetime_weeks"]},
    {"page": "shrapmind", "what": "edge fraction for a 20% debulk, %",
     "claimed": 3.58,
     "truth": lambda d: round(
         __import__("f2c.metals", fromlist=["x"])._penetration_fraction(0.20)
         * 100, 2)},

    # --- protocol (Hebrew) -----------------------------------------------
    {"page": "protocol", "what": "construct length, bp",
     "claimed": 810, "truth": lambda d: _construct()["dna_length_bp"]},
    {"page": "protocol", "what": "titratable residues in 4CG1",
     "claimed": 65, "truth": lambda d: _ph("narrow")["titratable_total"]},
    {"page": "protocol", "what": "responsive, pH 8 to 7.4",
     "claimed": 8, "truth": lambda d: _ph("narrow")["responsive_in_span"]},
    {"page": "protocol", "what": "responsive, pH 2 to 7.4",
     "claimed": 31, "truth": lambda d: _ph("wide")["responsive_in_span"]},
    {"page": "protocol", "what": "theoretical pI of TfH",
     "claimed": 7.96, "truth": lambda d: _pi()["pI"]},
    {"page": "protocol", "what": "top-ranked pH-sensitive residue",
     "claimed": "HIS208",
     "truth": lambda d: _ph("narrow")["shortlist"][0]["residue"]},
    {"page": "protocol", "what": "codons moved off the preferred choice",
     "claimed": 2,
     "truth": lambda d: len(_construct()["codon_swaps_from_preferred"])},
    {"page": "protocol", "what": "reported temperature optima for TfH",
     "claimed": "25, 25, 50, 55", "truth": lambda d: _topts()},

    # --- carrier-review (Hebrew) -----------------------------------------
    {"page": "carrier-review", "what": "DFO for a 20% debulk of 50 mg, mg",
     "claimed": 98,
     "truth": lambda d: round(__import__("f2c.metals", fromlist=["x"])
                              .chelator_demand("steel", 50.0, 0.20)
                              ["dfo_free_base_mg"])},
    {"page": "carrier-review", "what": "placements, 0.8 mm at 9x",
     "claimed": 1,
     "truth": lambda d: _placements(d, 0.8, "accelerated_9x")},
    {"page": "carrier-review", "what": "placements, 0.8 mm at the slowest rate",
     "claimed": 38,
     "truth": lambda d: _placements(d, 0.8, "pure_iron_low")},
    {"page": "carrier-review", "what": "placements, 3.0 mm at the slowest rate",
     "claimed": 141,
     "truth": lambda d: _placements(d, 3.0, "pure_iron_low")},
]


_PH_CACHE: dict[str, Any] = {}


def _ph(which: str) -> dict[str, Any]:
    """The pH-site analysis the protocol page quotes."""
    if which not in _PH_CACHE:
        from f2c import phsites
        pdb = ROOT / "data" / "raw" / "structures" / "4cg1_trimmed.pdb"
        spans = {"narrow": (8.0, 7.4), "wide": (2.0, 7.4)}
        a, b = spans[which]
        _PH_CACHE[which] = phsites.analyse(pdb, [130, 176, 208],
                                           pH_from=a, pH_to=b)
    return _PH_CACHE[which]


def _pi() -> dict[str, Any]:
    from f2c import phsites, warehouse
    seq = {p.name: p for p in warehouse.load()}["TfH"].sequence
    return phsites.isoelectric_point(seq)


def _topts() -> str:
    from f2c import warehouse
    prot = {p.name: p for p in warehouse.load()}["TfH"]
    vals = sorted(o.value for o in prot.observations
                  if o.metric == "temperature_optimum_c" and o.value)
    return ", ".join(f"{v:g}" for v in vals)


def _construct() -> dict[str, Any]:
    path = ROOT / "data" / "constructs" / "TfH_H208A.json"
    if not path.exists():
        raise SystemExit("run tools.design_construct first")
    return json.loads(path.read_text())


def _placements(d: dict[str, Any], size_mm: float, label: str) -> int:
    import math
    from f2c import metals
    rows = metals.carrier_placements("steel", size_mm, 0.20)["rows"]
    row = next(r for r in rows if r["label"] == label)
    n = row["placements"]
    return 1 if n <= 1.25 else math.ceil(n)


def main() -> int:
    d = _engine()
    failures: list[tuple[str, str, Any, Any]] = []
    by_page: dict[str, list[bool]] = {}

    for check in CHECKS:
        page, what, claimed = check["page"], check["what"], check["claimed"]
        try:
            truth = check["truth"](d)
        except Exception as exc:  # noqa: BLE001
            failures.append((page, what, claimed, f"<error: {exc}>"))
            by_page.setdefault(page, []).append(False)
            continue
        ok = (abs(claimed - truth) < 0.02
              if isinstance(claimed, float) and isinstance(truth, (int, float))
              else claimed == truth)
        by_page.setdefault(page, []).append(ok)
        if not ok:
            failures.append((page, what, claimed, truth))

    for page, results in sorted(by_page.items()):
        bad = results.count(False)
        mark = "ok" if not bad else f"{bad} STALE"
        print(f"  {page:16s} {len(results):3d} figures checked   {mark}")

    if failures:
        print("\nfigures the page states and the engine contradicts:\n")
        for page, what, claimed, truth in failures:
            print(f"  {page}: {what}")
            print(f"      page   {claimed}")
            print(f"      engine {truth}")
        print("\nThe engine settles it. Either the page is edited to match, or "
              "the claim in this file is edited along with the page -- but a "
              "page that states a number the engine contradicts is the failure "
              "this check exists to catch.")
        return 1

    print(f"\n{len(CHECKS)} figures checked across {len(by_page)} pages, "
          "all consistent with the engine")
    return 0


if __name__ == "__main__":
    sys.exit(main())
