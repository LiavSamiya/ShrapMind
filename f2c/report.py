"""Render a Decision for a human reader."""
from __future__ import annotations

from .formulate import residue_note
from .schema import Decision, ScoredCandidate

RULE = "=" * 72


def _candidate_block(c: ScoredCandidate, indent: str = "") -> list[str]:
    p = c.protein
    out = [
        f"{indent}{p.name}  [{p.protein_id}]",
        f"{indent}  organism      : {p.organism}",
    ]
    if p.uniprot_accession:
        review = (
            "reviewed" if p.reviewed else "unreviewed" if p.reviewed is not None else "?"
        )
        out.append(f"{indent}  UniProt       : {p.uniprot_accession} ({review})")
    if p.ec_numbers:
        out.append(f"{indent}  EC            : {', '.join(p.ec_numbers)}")
    if p.rhea_ids:
        out.append(f"{indent}  Rhea          : {', '.join(p.rhea_ids[:3])}")
    if p.catalytic_reactions:
        out.append(f"{indent}  reaction      : {p.catalytic_reactions[0]}")
    if p.pdb_ids:
        out.append(f"{indent}  structures    : {', '.join(p.pdb_ids[:5])}")
    out.append(f"{indent}  score         : {c.score:.2f}   unknown signals: {c.uncertainty:.0%}")
    for reason in c.reasons:
        out.append(f"{indent}    + {reason}")
    for unknown in c.unknowns:
        out.append(f"{indent}    ? {unknown}: not curated in the sources used")
    return out


def render(decision: Decision) -> str:
    m = decision.material
    lines = [
        RULE,
        "FRAGMENT-TO-CATALYST  ::  catalyst selection",
        RULE,
        "",
        "FRAGMENT",
        f"  material      : {m.polymer}  (form: {m.form})",
        f"  mass          : {m.mass_mg if m.mass_mg is not None else 'not supplied'} mg",
        f"  crystallinity : {m.crystallinity_pct if m.crystallinity_pct is not None else 'not characterised'}",
        f"  site          : {m.site}",
        "",
        f"VERDICT: {decision.verdict}",
        f"  {decision.rationale}",
        "",
    ]

    if decision.selected is None:
        if decision.alternatives:
            lines += ["CANDIDATES BELOW THE BAR", ""]
            for c in decision.alternatives:
                lines += _candidate_block(c, "  ") + [""]
        lines += [RULE]
        return "\n".join(lines)

    lines += ["SELECTED CATALYST", ""]
    lines += _candidate_block(decision.selected, "  ")
    lines += ["", "  evidence trail:"]
    seen: set[str] = set()
    for lit in decision.selected.protein.literature[:6]:
        ref = lit.get("doi") or lit.get("title") or ""
        if ref in seen:
            continue
        seen.add(ref)
        year = lit.get("year") or ""
        title = (lit.get("title") or "").strip()
        lines.append(f"    - {title} ({year})")
        if lit.get("doi"):
            lines.append(f"      {lit['doi']}")
    lines.append("")

    if decision.selected.gaps:
        lines += ["GAP TO BODY CONDITIONS  (the brief for the engineering layer)", ""]
        for g in decision.selected.gaps:
            src = f"  [{g.evidence.citation()}]" if g.evidence else ""
            lines.append(f"  * {g.kind}: {g.detail}{src}")
            lines.append(f"      measured : {g.measured or 'not measured'}")
            lines.append(f"      target   : {g.target}")
            lines.append(f"      action   : {g.engineering_target}")
        lines.append("")

    frag = decision.fragment or {}
    if frag:
        lines += ["FRAGMENT BARRIERS  (not fixed by choosing another catalyst)", ""]
        geo = frag.get("geometry") or {}
        if geo.get("computable") and "specific_area_mm2_per_mg" in geo:
            lines += [
                f"  surface area       : {geo['surface_area_mm2']} mm2 "
                f"({geo['specific_area_mm2_per_mg']} mm2/mg)",
                f"  basis              : {geo['basis']}",
                "  surface erosion scales with this, not with mass. No rate is derived "
                "from it.",
                "",
            ]
        elif geo.get("note"):
            lines += [f"  surface area       : {geo['note']}", ""]
        for item in frag.get("accessibility") or []:
            lines.append(f"  * {item['kind']} [{item['severity']}]: {item['detail']}")
            lines.append(f"      action   : {item['action']}")
        lines.append("")

    cap = decision.capture or {}
    lines += ["PRODUCT BURDEN AND CAPTURE", ""]
    if cap.get("computable"):
        lines += [
            f"  basis              : {cap['basis']}",
            f"  repeat unit        : {cap['repeat_unit_g_per_mol']} g/mol",
            f"  total product      : {cap['total_product_mmol']:.4g} mmol at complete degradation",
            f"  products           : {', '.join(cap['products'])}",
        ]
        if cap["requires_active_capture"]:
            lines.append(
                f"  needs capture      : {', '.join(cap['requires_active_capture'])}"
            )
            lines.append(
                f"  carrier capacity   : >= {cap['capture_capacity_mmol']:.4g} mmol"
            )
        if cap["metabolically_cleared"]:
            lines.append(
                f"  metabolic clearance: {', '.join(cap['metabolically_cleared'])}"
            )
        lines.append(f"  release rate       : {cap['rate']}")
    else:
        lines.append(f"  not computable: {cap.get('reason', 'unknown')}")
    lines += ["", f"  residue: {residue_note(m.polymer)}", ""]

    if decision.alternatives:
        lines += ["ALTERNATIVES CONSIDERED", ""]
        for c in decision.alternatives:
            p = c.protein
            lines.append(
                f"  - {p.name} ({p.organism}) score {c.score:.2f}, "
                f"{c.uncertainty:.0%} unknown"
            )
        lines.append("")

    lines += [
        "NOTE",
        "  Ranking reflects strength of experimental evidence and fit to body",
        "  conditions. It is not a predicted degradation rate: no public dataset",
        "  links a sequence to turnover on a solid fragment in tissue.",
        "",
        RULE,
    ]
    return "\n".join(lines)
