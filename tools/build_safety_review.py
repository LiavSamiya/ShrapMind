"""Fill the safety review's figures from the engine.

The page was written by hand on 2026-10-27 and its numbers were correct then.
By 2026-11-02 the ranking had changed twice, the substrate classifier had been
added, and the host-safety screen had gone from prose to code -- and the page
still stated the October figures. Every one of them looked exactly as
authoritative as a current one.

So the prose stays hand-written in `ui/safety-review.src.html` and every
figure in it is a token this script substitutes. A number that cannot drift is
a number nobody has to re-check.

    python -m tools.build_safety_review
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "ui" / "safety-review.src.html"
OUT = ROOT / "ui" / "safety-review.html"

MATERIALS = ("PET", "PA", "PLA", "PHA", "PBS", "PEF", "PC", "PUR", "PBAT", "NR")

SEVERITY_PILL = {"blocking": "b", "serious": "s", "caution": "n",
                 "unflagged": "c"}
SEVERITY_LABEL = {"blocking": "refused", "serious": "caution",
                  "caution": "watch", "unflagged": "no flag"}


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def table_refused(d: dict) -> str:
    """Every enzyme the screen refuses outright, with what refuses it."""
    from f2c import hostsafety, warehouse
    rows = []
    for p in warehouse.load():
        v = hostsafety.screen(p)
        if v["severity"] != hostsafety.BLOCKING:
            continue
        rows.append(
            f'<tr><td class="name">{esc(p.name)}</td>'
            f'<td class="num">{esc(", ".join(p.ec_numbers) or "none")}</td>'
            f'<td>{esc(v["host_substrate"])}</td>'
            f'<td class="num">{esc(v["basis"])}</td>'
            f'<td><span class="pill b">refused</span></td></tr>')
    n = len(rows)
    by_name = sum(1 for p in warehouse.load()
                  if hostsafety.screen(p)["severity"] == hostsafety.BLOCKING
                  and not p.ec_numbers)
    return (
        f'<caption>The {n} enzymes the screen refuses outright. '
        f'{by_name} of them carry no EC number at all and are caught on their '
        f'name, because a missing classification must not mean a missing '
        f'flag.</caption>'
        '<thead><tr><th>Enzyme</th><th>EC</th><th>Host substrate at risk</th>'
        '<th>Basis</th><th>Verdict</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def table_screen(d: dict) -> str:
    hs = d["host_safety"]
    classes = {c["severity"]: c for c in reversed(d["host_safety_classes"])}
    text = {
        "blocking": ("EC 3.4.x, or named a protease",
                     "Digests host structural protein; not recoverable"),
        "serious": ("EC 3.1.1.3, 1.11.1, or named a lipase",
                    "Host fat hydrolysis; oxidative stress in an inflamed site"),
        "caution": ("EC 3.1.1, 3.2.1",
                    "Promiscuous activity on host esters and sugars; bound it "
                    "experimentally"),
        "unflagged": ("—",
                      "Nothing flagged from classification. Not evidence of "
                      "selectivity."),
    }
    rows = []
    for sev in ("blocking", "serious", "caution", "unflagged"):
        where, what = text[sev]
        rows.append(
            f'<tr><td><span class="pill {SEVERITY_PILL[sev]}">'
            f'{SEVERITY_LABEL[sev]}</span></td>'
            f'<td class="num">{hs["counts"][sev]}</td>'
            f'<td class="num">{esc(where)}</td><td>{esc(what)}</td></tr>')
    return (
        f'<caption>Host-safety screen across all {hs["total"]} enzymes, as '
        f'<code>f2c/hostsafety.py</code> computes it. The screen is a gate in '
        f'<code>rank.py</code>: refused candidates sort below every unflagged '
        f'one, whatever they score.</caption>'
        '<thead><tr><th>Severity</th><th>Count</th><th>Classes</th>'
        '<th>Consequence</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def table_materials(d: dict) -> str:
    """What each material actually selects now, and on what evidence."""
    from f2c import hostsafety, substrate, warehouse
    by_name = {p.name: p for p in warehouse.load()}
    rows = []
    for key in MATERIALS:
        rec = d["decisions"].get(key) or {}
        sel = (rec.get("selected") or {}).get("name")
        m = re.search(r"from (\d+) enzymes", rec.get("rationale", ""))
        pool = m.group(1) if m else "—"
        unsafe = sum(
            1 for p in warehouse.load()
            if hostsafety.screen(p)["severity"] == hostsafety.BLOCKING
            and any((s.get("abbreviation") or "").upper() == key
                    for s in (p.substrates or [])))
        kcat = measured_on = cls = "—"
        prot = by_name.get(sel)
        if prot:
            best = [(o.value, (o.conditions or {}).get("substrate"))
                    for o in prot.observations
                    if o.metric == "kcat" and o.value]
            if best:
                v, sub = max(best)
                kcat = f"{v:g} s⁻¹"
                measured_on = sub or "not recorded"
                cls = substrate.classify(sub)
        rows.append(
            f'<tr><td class="name">{esc(key)}</td>'
            f'<td class="num">{esc(pool)}</td>'
            f'<td class="num">{unsafe}</td>'
            f'<td class="name">{esc(sel or "—")}</td>'
            f'<td class="num">{esc(kcat)}</td>'
            f'<td>{esc(measured_on)}</td>'
            f'<td><span class="pill n">{esc(cls)}</span></td></tr>')
    return (
        '<caption>What each material selects, the substrate its turnover '
        'number was measured on, and how many enzymes in its pool the screen '
        'refuses. A dash under k<sub>cat</sub> means the selected candidate '
        'has none: since catalytic evidence stopped rewarding a model-ester '
        'constant, the strongest candidate is often one with no constant at '
        'all.</caption>'
        '<thead><tr><th>Material</th><th>Pool</th><th>Refused</th>'
        '<th>Selected</th><th>k<sub>cat</sub></th><th>Measured on</th>'
        '<th>Substrate class</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>')


def main() -> int:
    payload = ROOT / "ui" / "decisions.json"
    if not payload.exists():
        print("ui/decisions.json missing -- run `python -m f2c.cli export-ui`",
              file=sys.stderr)
        return 1
    d = json.loads(payload.read_text())

    from f2c import substrate, warehouse
    proteins = warehouse.load()
    counts: dict[str, int] = {}
    for p in proteins:
        for o in p.observations:
            if o.metric in substrate.KINETIC_METRICS:
                cls = substrate.classify((o.conditions or {}).get("substrate"))
                counts[cls] = counts.get(cls, 0) + 1
    olig_enzymes = {
        p.name for p in proteins for o in p.observations
        if o.metric in substrate.KINETIC_METRICS
        and substrate.classify((o.conditions or {}).get("substrate")) == "oligomer"
    }
    kcats = [o.value for p in proteins for o in p.observations
             if o.metric == "kcat" and o.value]

    subs = {
        "{{PROTEINS}}": d["warehouse"]["proteins"],
        "{{OBSERVATIONS}}": sum(len(p.observations) for p in proteins),
        "{{CONSTANTS}}": d["kinetics_total"],
        "{{MODEL}}": counts.get("model", 0),
        "{{OLIGOMER}}": counts.get("oligomer", 0),
        "{{UNKNOWN}}": counts.get("unknown", 0),
        "{{WITH_KCAT}}": sum(1 for p in proteins
                             if any(o.metric == "kcat" for o in p.observations)),
        "{{OLIGOMER_ENZYMES}}": len(olig_enzymes),
        "{{PROTEINASE_K_KCAT}}": f"{max(kcats):g}" if kcats else "—",
        "{{UNFLAGGED}}": d["host_safety"]["counts"]["unflagged"],
        "{{TABLE_REFUSED}}": table_refused(d),
        "{{TABLE_SCREEN}}": table_screen(d),
        "{{TABLE_MATERIALS}}": table_materials(d),
    }

    text = SRC.read_text()
    for token, value in subs.items():
        text = text.replace(token, str(value))

    left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text)))
    if left:
        print(f"unsubstituted token(s): {left}", file=sys.stderr)
        return 1

    OUT.write_text(text)
    print(f"wrote {OUT} ({len(text) // 1024} KB)")
    for k in ("{{PROTEINS}}", "{{CONSTANTS}}", "{{MODEL}}", "{{OLIGOMER}}",
              "{{UNKNOWN}}", "{{WITH_KCAT}}", "{{OLIGOMER_ENZYMES}}",
              "{{PROTEINASE_K_KCAT}}"):
        print(f"  {k.strip('{}'):20s} {subs[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
