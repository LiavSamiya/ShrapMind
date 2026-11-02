"""Fill the lab protocol's figures and sequence from the design tools.

Same reasoning as tools/build_safety_review.py: a protocol that quotes a
sequence by hand is a protocol whose sequence will not match the construct
anyone actually orders. The prose lives in ui/protocol.src.html; every number,
table and base pair in it is substituted from f2c/phsites.py and
tools/design_construct.py at build time.

    python -m tools.build_protocol
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SRC = ROOT / "ui" / "protocol.src.html"
OUT = ROOT / "ui" / "protocol.html"
STRUCTURE = ROOT / "data" / "raw" / "structures" / "4cg1_trimmed.pdb"

TARGET = "TfH"
SITE = [130, 176, 208]          # structure numbering, verified on every build
SIGNAL_PEPTIDE = 40
MUTATION = "H208A"
# TfH's reported optimum, from the warehouse rather than from memory; the
# protocol runs its second temperature series here.
FALLBACK_TOPT = 65


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def table_sites(narrow: dict, wide: dict) -> str:
    rows = []
    for x in narrow["shortlist"][:8]:
        wide_row = next((w for w in wide["rows"] if w["residue"] == x["residue"]),
                        None)
        cat = "כן" if x["is_catalytic"] else "—"
        rows.append(
            f'<tr><td class="name">{esc(x["residue"])}</td>'
            f'<td class="num">{x["model_pKa"]:.1f}</td>'
            f'<td class="num">{"—" if x["distance_to_site_a"] is None else x["distance_to_site_a"]}</td>'
            f'<td class="num">{x["ionisation_change"]:.3f}</td>'
            f'<td class="num">{0.0 if wide_row is None else wide_row["ionisation_change"]:.3f}</td>'
            f'<td class="num">{x["priority"]:.4f}</td>'
            f'<td class="num">{cat}</td></tr>')
    return (
        '<div class="scroll"><table>'
        '<caption>שיירים מתכיילים לפי עדיפות, מתוך '
        f'{narrow["titratable_total"]} במבנה. עמודת Δיוניזציה השנייה מראה מה '
        'היה קורה במעבר מ-pH 2, לשם השוואה.</caption>'
        '<thead><tr><th>שייר</th><th>pKa מודל</th><th>מרחק (Å)</th>'
        '<th>Δיון 8→7.4</th><th>Δיון 2→7.4</th><th>priority</th>'
        '<th>קטליטי</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>')


def table_construct(report: dict) -> str:
    muts = ", ".join(m["mutation"] for m in report["mutations"]) or "—"
    rows = [
        ("אנזים", f'{report["target"]} · {report["uniprot"]} · '
                  f'{report["organism"]}'),
        ("מחלקת EC", ", ".join(report["ec"]) or "—"),
        ("אורך פראי", f'{report["wild_type_length"]} שיירים'),
        ("פפטיד איתות שנחתך", f'{report["signal_peptide_removed"]} שיירים'),
        ("מוטציות", muts),
        ("תגית", f'{report["tag"]["protein"]} בקצה N'),
        ("חלבון מבוטא", f'{report["protein_length"]} שיירים'),
        ("אורך DNA", f'{report["dna_length_bp"]} בסיסים'),
        ("תכולת GC", f'{report["gc_percent"]}% · חלונות '
                     f'{report["gc_window_min"]}–{report["gc_window_max"]}%'),
        ("קודונים שהוזזו", str(len(report["codon_swaps_from_preferred"]))),
        ("אתרי חיתוך שנבדקו", ", ".join(report["restriction_sites_checked"])),
        ("הפרות אילוץ", ", ".join(report["constraint_violations"]) or "אין"),
    ]
    body = "".join(
        f'<tr><td class="name">{esc(k)}</td><td>{esc(v)}</td></tr>'
        for k, v in rows)
    return ('<div class="scroll"><table>'
            '<caption>מפרט הקונסטרקט, כפי שהכלי מדווח אותו.</caption>'
            '<thead><tr><th>שדה</th><th>ערך</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def sequence_block(report: dict, dna: str) -> str:
    lines = []
    for i in range(0, len(dna), 60):
        lines.append(f"{i + 1:>4}  {dna[i:i + 60]}")
    muts = ", ".join(m["mutation"] for m in report["mutations"]) or "wild type"
    return (
        '<div class="seq">'
        f'<div class="head"><span>{esc(report["target"])} {esc(muts)}</span>'
        f'<span>{report["dna_length_bp"]} bp</span>'
        f'<span>GC {report["gc_percent"]}%</span>'
        '<span>E. coli codon-optimised</span></div>'
        f'<pre>{esc(chr(10).join(lines))}</pre>'
        '<div class="foot">מתחיל ב-<code>ATG</code>, ואחריו תגית '
        'הקסאהיסטידין, ואחריו החלבון הבוגר ללא פפטיד האיתות. מסתיים בשני קודוני '
        'עצירה בפאזה, כך שקריאת-יתר בודדת עדיין נעצרת. '
        'הרצף עובר תרגום חוזר מול טבלת קודונים סטנדרטית שנבנית בנפרד בחבילת '
        'הבדיקות, ולא מול הטבלה שהכלי עצמו משתמש בה.</div></div>')


def main() -> int:
    from f2c import phsites, warehouse

    if not STRUCTURE.exists():
        print(f"missing {STRUCTURE} -- run `python -m tools.build_structure`",
              file=sys.stderr)
        return 1

    proteins = {p.name: p for p in warehouse.load()}
    prot = proteins.get(TARGET)
    if prot is None or not prot.sequence:
        print(f"{TARGET} not in the warehouse", file=sys.stderr)
        return 1

    narrow = phsites.analyse(STRUCTURE, SITE, pH_from=8.0, pH_to=7.4)
    wide = phsites.analyse(STRUCTURE, SITE, pH_from=2.0, pH_to=7.4)
    if narrow["site_residues_missing_from_structure"]:
        print("catalytic residues absent from the structure: "
              f"{narrow['site_residues_missing_from_structure']}", file=sys.stderr)
        return 1
    pi = phsites.isoelectric_point(prot.sequence)

    construct = ROOT / "data" / "constructs" / f"{TARGET}_{MUTATION}.json"
    fasta = ROOT / "data" / "constructs" / f"{TARGET}_{MUTATION}.fasta"
    if not construct.exists():
        print(f"missing {construct} -- run `python -m tools.design_construct "
              f"--target {TARGET} --mutate {MUTATION} "
              f"--remove-signal-peptide {SIGNAL_PEPTIDE}`", file=sys.stderr)
        return 1
    report = json.loads(construct.read_text())
    dna = "".join(l for l in fasta.read_text().split(">")[2].splitlines()[1:])

    # Molecular weight of the expressed chain, so the gel band has a number.
    avg = {"A": 71.08, "R": 156.19, "N": 114.10, "D": 115.09, "C": 103.14,
           "Q": 128.13, "E": 129.12, "G": 57.05, "H": 137.14, "I": 113.16,
           "L": 113.16, "K": 128.17, "M": 131.19, "F": 147.18, "P": 97.12,
           "S": 87.08, "T": 101.10, "W": 186.21, "Y": 163.18, "V": 99.13}
    mw = sum(avg.get(a, 110.0) for a in report["protein_expressed"]) + 18.02

    # Every reported optimum, not the first one above a threshold. TfH's four
    # measurements run 25, 25, 50, 55 -- a median of 37.5, which is body
    # temperature. Quoting one of them as "the" optimum would have put an
    # unsupported claim in a bench protocol, which is the failure this project
    # exists to prevent, committed by this project.
    topts = sorted(o.value for o in prot.observations
                   if o.metric == "temperature_optimum_c" and o.value)
    topt = max(topts) if topts else FALLBACK_TOPT
    mid = len(topts) // 2
    topt_median = (topts[mid] if len(topts) % 2
                   else (topts[mid - 1] + topts[mid]) / 2) if topts else topt

    subs = {
        "{{BUILT}}": _dt.date.today().isoformat(),
        "{{DNA_BP}}": report["dna_length_bp"],
        "{{TITRATABLE}}": narrow["titratable_total"],
        "{{NARROW_N}}": narrow["responsive_in_span"],
        "{{WIDE_N}}": wide["responsive_in_span"],
        "{{PI}}": pi["pI"],
        "{{NET_CHARGE}}": pi["net_charge_at_7_4"],
        "{{SWAPS}}": len(report["codon_swaps_from_preferred"]),
        "{{KDA}}": round(mw / 1000, 1),
        "{{TOPT}}": int(topt),
        "{{TOPT_VALUES}}": ", ".join(f"{v:g}" for v in topts) or "—",
        "{{TOPT_SPREAD}}": f"{(max(topts) - min(topts)):g}" if topts else "—",
        "{{TOPT_MEDIAN}}": f"{topt_median:g}",
        "{{TABLE_SITES}}": table_sites(narrow, wide),
        "{{TABLE_CONSTRUCT}}": table_construct(report),
        "{{SEQUENCE_BLOCK}}": sequence_block(report, dna),
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
    for k in ("{{DNA_BP}}", "{{TITRATABLE}}", "{{NARROW_N}}", "{{WIDE_N}}",
              "{{PI}}", "{{KDA}}", "{{TOPT}}", "{{TOPT_VALUES}}",
              "{{TOPT_MEDIAN}}", "{{SWAPS}}"):
        print(f"  {k.strip('{}'):12s} {subs[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
