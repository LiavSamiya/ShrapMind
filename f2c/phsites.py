"""Find the residues whose protonation state changes between two pH values.

The chief biologist's feasibility review asks a narrower question than "is this
enzyme stable at pH 7.4". It asks which *sites* are sensitive. That is a
structural question with a structural answer, and it is answerable from a PDB
file without a simulation.

The reasoning is short. A protein's pH behaviour is dominated by its
titratable side chains, and a side chain only *responds* to a pH change if its
pKa lies between the two pH values in question. Moving an enzyme from a pH 8
assay to pH 7.4 tissue changes essentially nothing for Asp (pKa 3.9) or Arg
(12.5) -- both are fully ionised at either end. It changes a great deal for
histidine, whose model pKa of 6.0 sits inside the span that matters, and for
cysteine and tyrosine at the alkaline end.

So the screen is: for each titratable residue, how much does its ionisation
fraction change across the span, and how close is it to the catalytic site.
The product of those two is the ranking.

Two honest limits, stated here rather than in a footnote:

* **These are model pKa values, not computed ones.** A buried or
  salt-bridged residue can shift by several units, and the shift is exactly
  what a real pKa calculation (PROPKA, H++, constant-pH MD) exists to find.
  This module computes a *shortlist to send to such a calculation*, not a
  substitute for one. Every output carries that label.
* **Proximity is a proxy for coupling.** A residue 20 A away can still matter
  through a hydrogen-bond network or by changing the surface charge. Distance
  ranks the shortlist; it does not define it, and the module reports the
  distant titratable residues too.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# Model pKa values for side chains in water, with the atom that carries the
# ionisable group. These are the textbook figures; the point of the module is
# to say which ones are worth measuring, so a precise starting value matters
# less than a consistent one.
TITRATABLE: dict[str, dict[str, Any]] = {
    "ASP": {"pKa": 3.9, "charged_when": "deprotonated", "atoms": ("OD1", "OD2"),
            "note": "Fully ionised at both ends of the physiological span."},
    "GLU": {"pKa": 4.2, "charged_when": "deprotonated", "atoms": ("OE1", "OE2"),
            "note": "Fully ionised at both ends of the physiological span."},
    "HIS": {"pKa": 6.0, "charged_when": "protonated", "atoms": ("ND1", "NE2"),
            "note": "The residue that actually switches between pH 6 and 8. "
                    "Where a histidine is catalytic, this is the pH "
                    "dependence."},
    "CYS": {"pKa": 8.3, "charged_when": "deprotonated", "atoms": ("SG",),
            "note": "Thiolate formation; also the residue that forms "
                    "disulfides, so a pKa shift here changes folding as well "
                    "as chemistry."},
    "TYR": {"pKa": 10.1, "charged_when": "deprotonated", "atoms": ("OH",),
            "note": "Normally spectator in this span unless its pKa is "
                    "depressed by a nearby positive charge."},
    "LYS": {"pKa": 10.5, "charged_when": "protonated", "atoms": ("NZ",),
            "note": "Normally fully protonated across this span."},
    "ARG": {"pKa": 12.5, "charged_when": "protonated", "atoms": ("NH1", "NH2", "NE"),
            "note": "Effectively never titrates in a biological range."},
}

# Henderson-Hasselbalch: the fraction in the charged form at a given pH.
def charged_fraction(pKa: float, pH: float, charged_when: str) -> float:
    ratio = 10 ** (pH - pKa)
    deprotonated = ratio / (1.0 + ratio)
    return deprotonated if charged_when == "deprotonated" else 1.0 - deprotonated


@dataclass
class Residue:
    chain: str
    number: int
    name: str
    atoms: dict[str, tuple[float, float, float]]

    def key(self) -> str:
        return f"{self.name}{self.number}"


def parse_pdb(path: Path, chain: str | None = None) -> list[Residue]:
    """Minimal ATOM-record parser. No dependency, because the only thing
    needed is residue identity and a few atom coordinates."""
    residues: dict[tuple[str, int], Residue] = {}
    for line in Path(path).read_text().splitlines():
        if not line.startswith("ATOM"):
            continue
        ch = line[21]
        if chain and ch != chain:
            continue
        try:
            num = int(line[22:26])
            x, y, z = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError:
            continue
        name = line[17:20].strip()
        atom = line[12:16].strip()
        res = residues.setdefault((ch, num), Residue(ch, num, name, {}))
        res.atoms.setdefault(atom, (x, y, z))
    return [residues[k] for k in sorted(residues)]


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.dist(a, b)


BACKBONE = ("N", "CA", "C", "O", "OXT")


def _sidechain(res: Residue, only: tuple[str, ...] | None = None
               ) -> list[tuple[float, float, float]]:
    """Side-chain atoms, optionally just the ionisable ones.

    Backbone atoms are excluded because every residue's backbone is covalently
    bonded to its sequence neighbours'. Measuring all atoms made His129 sit
    1.33 A from Ser130 -- a peptide bond length, not a functional proximity --
    and put a residue on the shortlist for being adjacent in sequence rather
    than for touching the site.
    """
    if only:
        return [res.atoms[a] for a in only if a in res.atoms]
    return [xyz for name, xyz in res.atoms.items() if name not in BACKBONE]


def _min_distance(res: Residue, targets: list[Residue],
                  ionisable: tuple[str, ...] | None = None) -> float | None:
    """Closest approach between this residue's ionisable group and the site.

    Measured from the atoms that actually carry the charge, because what
    couples a titratable residue to catalysis is where its proton sits, not
    where its alpha carbon is.
    """
    source = _sidechain(res, ionisable) or _sidechain(res) or list(res.atoms.values())
    best = None
    for t in targets:
        for pb in _sidechain(t) or list(t.atoms.values()):
            for pa in source:
                d = _dist(pa, pb)
                if best is None or d < best:
                    best = d
    return best


def analyse(pdb_path: Path, site_residues: Iterable[int], chain: str | None = None,
            pH_from: float = 8.0, pH_to: float = 7.4,
            near_angstroms: float = 12.0) -> dict[str, Any]:
    """Rank titratable residues by how much the pH move changes them.

    `site_residues` are the catalytic positions in *this file's* numbering.
    They are required rather than guessed: a module that located active sites
    by heuristic would be the kind of unprovenanced inference this project
    exists to refuse.
    """
    residues = parse_pdb(pdb_path, chain)
    by_number = {r.number: r for r in residues}
    site = [by_number[n] for n in site_residues if n in by_number]
    missing = [n for n in site_residues if n not in by_number]

    rows: list[dict[str, Any]] = []
    for res in residues:
        spec = TITRATABLE.get(res.name)
        if not spec:
            continue
        f_from = charged_fraction(spec["pKa"], pH_from, spec["charged_when"])
        f_to = charged_fraction(spec["pKa"], pH_to, spec["charged_when"])
        delta = abs(f_to - f_from)
        d = _min_distance(res, site, spec["atoms"]) if site else None
        # Proximity weight falls off linearly to the cutoff, then stops. A
        # product, so a residue has to be both responsive AND near the site to
        # rank highly -- either alone is not a lead.
        prox = 1.0 if d is None else max(0.0, 1.0 - d / near_angstroms)
        rows.append({
            "residue": res.key(),
            "number": res.number,
            "name": res.name,
            "chain": res.chain,
            "model_pKa": spec["pKa"],
            "charged_fraction_at_from": round(f_from, 4),
            "charged_fraction_at_to": round(f_to, 4),
            "ionisation_change": round(delta, 4),
            "distance_to_site_a": None if d is None else round(d, 2),
            "near_site": bool(d is not None and d <= near_angstroms),
            "priority": round(delta * prox, 5),
            "is_catalytic": res.number in set(site_residues),
            "note": spec["note"],
        })

    rows.sort(key=lambda r: (-r["priority"], r["distance_to_site_a"] or 1e9))
    responsive = [r for r in rows if r["ionisation_change"] >= 0.01]
    return {
        "structure": Path(pdb_path).name,
        "chain": chain,
        "pH_from": pH_from,
        "pH_to": pH_to,
        "near_angstroms": near_angstroms,
        "site_residues": list(site_residues),
        "site_residues_missing_from_structure": missing,
        "titratable_total": len(rows),
        "responsive_in_span": len(responsive),
        "rows": rows,
        "shortlist": [r for r in rows if r["priority"] > 0][:12],
        "evidence": "derived",
        "what_this_is": (
            "A shortlist computed from model side-chain pKa values and "
            "distance to the catalytic site. It says which residues are worth "
            "a real pKa calculation and a mutant, not what their pKa is."
        ),
        "what_this_is_not": (
            "Not a pKa calculation. A buried or salt-bridged side chain can "
            "shift several units from its model value, and that shift is the "
            "whole question -- PROPKA, H++ or constant-pH MD answer it, and "
            "this ranking is what you hand them."
        ),
    }


def isoelectric_point(sequence: str) -> dict[str, Any]:
    """Theoretical pI, and what it implies at pH 7.4.

    A protein near its pI has minimal net charge and minimal colloidal
    stability, which is where aggregation happens. For an injected depot that
    is a formulation problem, not a catalytic one, so it is reported
    separately from the site analysis.
    """
    # Model pKa set for termini and side chains (Bjellqvist-style).
    pk = {"Cterm": 3.65, "Nterm": 8.2, "D": 3.9, "E": 4.2, "C": 8.3,
          "Y": 10.1, "H": 6.0, "K": 10.5, "R": 12.5}
    counts = {aa: sequence.count(aa) for aa in "DECYHKR"}

    def net(pH: float) -> float:
        pos = 1.0 / (1.0 + 10 ** (pH - pk["Nterm"]))
        for aa in "HKR":
            pos += counts[aa] / (1.0 + 10 ** (pH - pk[aa]))
        neg = 1.0 / (1.0 + 10 ** (pk["Cterm"] - pH))
        for aa in "DECY":
            neg += counts[aa] / (1.0 + 10 ** (pk[aa] - pH))
        return pos - neg

    lo, hi = 0.0, 14.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if net(mid) > 0:
            lo = mid
        else:
            hi = mid
    pI = (lo + hi) / 2
    return {
        "pI": round(pI, 2),
        "net_charge_at_7_4": round(net(7.4), 2),
        "titratable_counts": counts,
        "aggregation_risk_near_pI": abs(pI - 7.4) < 1.0,
        "evidence": "derived",
        "note": (
            "Theoretical, from sequence composition alone. It ignores burial, "
            "which shifts real pKa values, and it says nothing about whether "
            "the fold tolerates the charge it computes."
        ),
    }
