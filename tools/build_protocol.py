"""Fill the metal-arm lab protocol, in both languages, from the design tools.

Two sources, one builder, one set of numbers. `ui/protocol.src.html` is the
Hebrew prose and `ui/protocol.en.src.html` the English; every figure, table
and base pair in either is a token substituted here, and both pages are
emitted from one run so they cannot disagree with each other or with the
engine.

The target is human H ferritin, which is what the engine selects for iron.
An earlier version of this protocol was built around TfH, a PET cutinase --
correct bench work aimed at the wrong arm, since the team decided to focus on
metals. The polymer version is gone; what survived is the tooling, which was
never specific to either.

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

SOURCES = {
    "he": (ROOT / "ui" / "protocol.src.html", ROOT / "ui" / "protocol.html"),
    "en": (ROOT / "ui" / "protocol.en.src.html",
           ROOT / "ui" / "protocol.en.html"),
}
CSS = ROOT / "ui" / "protocol.css"
STRUCTURE = ROOT / "data" / "raw" / "structures" / "1fha.pdb"

# Human H ferritin. The engine reached it by querying EC 1.16.3 rather than by
# recalling the literature, and it is the arm's lead because it fuses
# oxidation and storage in one human protein.
TARGET = "hFTH1"
ACCESSION = "P02794"
CHAIN = "A"
MUTATION = "H65A"
# The di-iron ferroxidase centre, in 1FHA numbering. Verified against the
# structure on every build rather than trusted.
SITE = [27, 34, 61, 62, 65, 107, 141]
EXPECTED = {27: "GLU", 34: "TYR", 61: "GLU", 62: "GLU",
            65: "HIS", 107: "GLU", 141: "GLN"}
# Mature ferritin has its initiator methionine removed, so the structure is
# UniProt minus one.
OFFSET = 1

# The pH span that matters for a metal fragment is not assay-to-tissue. Iron
# corrosion acidifies its own surface through Fe(II) hydrolysis, so the enzyme
# meets a microenvironment below tissue pH, and 5.5 is the figure used for a
# corroding steel surface. The second span is ferritin's own cytosol, as a
# control on the method.
ACID_SPAN = (7.4, 5.5)
HOME_SPAN = (7.4, 7.2)

FRAGMENT_MG = 50.0
DEBULK = 0.20

LABELS = {
    "he": {
        "sites_caption": (
            "שיירים מתכיילים לפי עדיפות, מתוך {n} בשרשרת A. עמודת Δיוניזציה "
            "השנייה היא ה-pH הביתי של פריטין, כבקרה על השיטה."),
        "cols": ("שייר", "pKa מודל", "מרחק (Å)", "Δיון 7.4→5.5",
                 "Δיון 7.4→7.2", "priority", "באתר"),
        "yes": "כן", "dash": "—",
        "construct_caption": "מפרט הקונסטרקט, כפי שהכלי מדווח אותו.",
        "construct_cols": ("שדה", "ערך"),
        "fields": ("אנזים", "מחלקת EC", "אורך פראי", "מוטציות", "תגית",
                   "חלבון מבוטא", "אורך DNA", "תכולת GC", "קודונים שהוזזו",
                   "אתרי חיתוך שנבדקו", "הפרות אילוץ"),
        "none": "אין",
        "seq_foot": (
            "מתחיל ב-<code>ATG</code>, ואחריו תגית הקסאהיסטידין, ואחריו החלבון "
            "המלא. מסתיים בשני קודוני עצירה בפאזה. הרצף עובר תרגום חוזר מול "
            "טבלת קודונים סטנדרטית שנבנית בנפרד בחבילת הבדיקות, ולא מול "
            "הטבלה שהכלי עצמו משתמש בה."),
        "gaps_caption": (
            "מה עדיין פתוח. אף אחד משני מסמכי ההיתכנות של הצוות לא מעלה אף "
            "פריט ברשימה."),
        "gaps_cols": ("חומרה", "תחום", "מה חסר", "מה יסגור את זה",
                      "ממתין ל"),
        "gaps_closed_caption": (
            "מה נסגר, ומה סגר אותו. פער שנסגר נשאר במרשם: התיעוד של מה שהיה "
            "חסר שווה כמו החסר עצמו, ואחת התשובות כאן חזרה שלילית."),
        "gaps_closed_cols": ("סטטוס", "תחום", "הפער", "מה סגר אותו", "מתי"),
        "closed": "נסגר",
        "residual": "נותר:",
        "partly": "נסגר חלקית:",
        "severity": {"blocks_injection": "חוסם הזרקה",
                     "blocks_trial": "חוסם ניסוי",
                     "blocks_claim": "חוסם טענה",
                     "incomplete": "חלקי"},
        "area": {"clinical": "קליני", "protein": "חלבון",
                 "formulation": "פורמולציה", "metal": "מתכת"},
    },
    "en": {
        "sites_caption": (
            "Titratable residues by priority, of {n} in chain A. The second "
            "ionisation column is ferritin's own cytosolic pH, as a control "
            "on the method."),
        "cols": ("Residue", "Model pKa", "Distance (Å)", "Δion 7.4→5.5",
                 "Δion 7.4→7.2", "Priority", "In site"),
        "yes": "yes", "dash": "—",
        "construct_caption": "The construct as the tool reports it.",
        "construct_cols": ("Field", "Value"),
        "fields": ("Enzyme", "EC class", "Wild-type length", "Mutations",
                   "Tag", "Expressed protein", "DNA length", "GC content",
                   "Codons moved", "Restriction sites checked",
                   "Constraint violations"),
        "none": "none",
        "seq_foot": (
            "Begins with <code>ATG</code>, then the hexahistidine tag, then "
            "the full protein. Ends in two in-frame stop codons. The sequence "
            "passes a back-translation check against a standard codon table "
            "built separately in the test suite, not against the table the "
            "tool itself uses."),
        "gaps_caption": (
            "What is still open. Neither of the team's two feasibility "
            "documents raises a single item on this register."),
        "gaps_cols": ("Severity", "Area", "What is missing",
                      "What would close it", "Waiting on"),
        "gaps_closed_caption": (
            "What closed, and what closed it. A closed gap stays on the "
            "register: the record of what was missing is worth as much as "
            "the absence was, and one of these answers came back negative."),
        "gaps_closed_cols": ("Status", "Area", "The gap", "What closed it",
                             "When"),
        "closed": "closed",
        "residual": "Residual:",
        "partly": "Partly closed:",
        "severity": {"blocks_injection": "blocks injection",
                     "blocks_trial": "blocks trial",
                     "blocks_claim": "blocks claim",
                     "incomplete": "incomplete"},
        "area": {"clinical": "clinical", "protein": "protein",
                 "formulation": "formulation", "metal": "metal"},
    },
}

PILL = {"blocks_injection": "b", "blocks_trial": "s",
        "blocks_claim": "s", "incomplete": "n"}


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def verify_site() -> None:
    """Fail the build if the ferroxidase centre is not where it should be.

    Same contract tools/build_structure.py holds for the TfH triad: a page
    that names catalytic residues must not be buildable from a structure in
    which they are something else.
    """
    from f2c import phsites
    residues = {r.number: r.name
                for r in phsites.parse_pdb(STRUCTURE, chain=CHAIN)}
    wrong = {n: residues.get(n) for n, want in EXPECTED.items()
             if residues.get(n) != want}
    if wrong:
        raise SystemExit(
            f"ferroxidase site does not verify in {STRUCTURE.name}: {wrong}. "
            f"Expected {EXPECTED}.")


def table_sites(acid: dict, home: dict, L: dict) -> str:
    rows = []
    for x in acid["shortlist"][:8]:
        h = next((w for w in home["rows"] if w["residue"] == x["residue"]), None)
        rows.append(
            f'<tr><td class="name">{esc(x["residue"])}</td>'
            f'<td class="num">{x["model_pKa"]:.1f}</td>'
            f'<td class="num">{L["dash"] if x["distance_to_site_a"] is None else x["distance_to_site_a"]}</td>'
            f'<td class="num">{x["ionisation_change"]:.3f}</td>'
            f'<td class="num">{0.0 if h is None else h["ionisation_change"]:.3f}</td>'
            f'<td class="num">{x["priority"]:.4f}</td>'
            f'<td class="num">{L["yes"] if x["is_catalytic"] else L["dash"]}</td></tr>')
    head = "".join(f"<th>{esc(c)}</th>" for c in L["cols"])
    return ('<div class="scroll"><table><caption>'
            + esc(L["sites_caption"].format(n=acid["titratable_total"]))
            + f'</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def table_construct(r: dict, L: dict) -> str:
    muts = ", ".join(m["mutation"] for m in r["mutations"]) or L["dash"]
    values = (
        f'{r["target"]} · {r["uniprot"]} · {r["organism"]}',
        ", ".join(r["ec"]) or "EC 1.16.3.1",
        f'{r["wild_type_length"]}',
        muts,
        f'{r["tag"]["protein"]} (N)',
        f'{r["protein_length"]}',
        f'{r["dna_length_bp"]} bp',
        f'{r["gc_percent"]}% · {r["gc_window_min"]}–{r["gc_window_max"]}%',
        str(len(r["codon_swaps_from_preferred"])),
        ", ".join(r["restriction_sites_checked"]),
        ", ".join(r["constraint_violations"]) or L["none"],
    )
    body = "".join(f'<tr><td class="name">{esc(k)}</td><td>{esc(v)}</td></tr>'
                   for k, v in zip(L["fields"], values))
    head = "".join(f"<th>{esc(c)}</th>" for c in L["construct_cols"])
    return ('<div class="scroll"><table><caption>'
            + esc(L["construct_caption"])
            + f'</caption><thead><tr>{head}</tr></thead>'
            f'<tbody>{body}</tbody></table></div>')


def sequence_block(r: dict, dna: str, L: dict) -> str:
    lines = [f"{i + 1:>4}  {dna[i:i + 60]}" for i in range(0, len(dna), 60)]
    muts = ", ".join(m["mutation"] for m in r["mutations"]) or "wild type"
    return ('<div class="seq">'
            f'<div class="head"><span>{esc(r["target"])} {esc(muts)}</span>'
            f'<span>{r["dna_length_bp"]} bp</span>'
            f'<span>GC {r["gc_percent"]}%</span>'
            '<span>E. coli codon-optimised</span></div>'
            f'<pre>{esc(chr(10).join(lines))}</pre>'
            f'<div class="foot">{L["seq_foot"]}</div></div>')


def table_gaps(lang: str, L: dict) -> str:
    """Two tables: what is still open, and what closed and what closed it.

    A closed gap stays on the register. The record of what was missing and
    what answered it is worth as much as the absence was, and one of the
    answers here came back negative -- which is the single most useful thing
    the register has produced.
    """
    from f2c import gaps
    suffix = "_he" if lang == "he" else ""

    def row_open(g):
        title = g.get(f"title{suffix}") or g["title"]
        missing = g.get(f"what_is_missing{suffix}") or g["what_is_missing"]
        waiting = g.get("waiting_on")
        partial = g.get("partially_closed_by")
        extra = ""
        if partial:
            extra = f'<br><em>{esc(L["partly"])}</em> {esc(partial)}'
        return (f'<tr><td><span class="pill {PILL[g["severity"]]}">'
                f'{esc(L["severity"][g["severity"]])}</span></td>'
                f'<td class="num">{esc(L["area"][g["area"]])}</td>'
                f'<td><strong>{esc(title)}</strong><br>{esc(missing)}{extra}</td>'
                f'<td>{esc(g["what_would_close_it"])}</td>'
                f'<td class="num">{esc(waiting or g["whose"])}</td></tr>')

    def row_closed(g):
        title = g.get(f"title{suffix}") or g["title"]
        closed_by = g.get(f"closed_by{suffix}") or g.get("closed_by", "")
        residual = g.get("residual")
        extra = f'<br><em>{esc(L["residual"])}</em> {esc(residual)}' if residual else ""
        return (f'<tr><td><span class="pill o">{esc(L["closed"])}</span></td>'
                f'<td class="num">{esc(L["area"][g["area"]])}</td>'
                f'<td><strong>{esc(title)}</strong></td>'
                f'<td>{esc(closed_by)}{extra}</td>'
                f'<td class="num">{esc(g.get("closed_on", ""))}</td></tr>')

    head_open = "".join(f"<th>{esc(c)}</th>" for c in L["gaps_cols"])
    head_closed = "".join(f"<th>{esc(c)}</th>" for c in L["gaps_closed_cols"])
    open_rows = "".join(row_open(g) for g in gaps.open_gaps())
    closed_rows = "".join(
        row_closed(g) for g in gaps.GAPS if gaps.status(g) == gaps.CLOSED)
    return (
        '<div class="scroll"><table><caption>'
        + esc(L["gaps_caption"])
        + f'</caption><thead><tr>{head_open}</tr></thead>'
        f'<tbody>{open_rows}</tbody></table></div>'
        '<div class="scroll"><table><caption>'
        + esc(L["gaps_closed_caption"])
        + f'</caption><thead><tr>{head_closed}</tr></thead>'
        f'<tbody>{closed_rows}</tbody></table></div>')


def _uncaptured() -> float:
    """Milligrams released by a 20% debulk that nothing here captures."""
    from f2c import metals
    out = metals.released_elements("steel", FRAGMENT_MG, DEBULK)
    return out["uncaptured_mg"] if out.get("computable") else 0.0


def main() -> int:
    from f2c import gaps, metals, phsites

    if not STRUCTURE.exists():
        print(f"missing {STRUCTURE}; fetch 1FHA from RCSB", file=sys.stderr)
        return 1
    verify_site()

    acid = phsites.analyse(STRUCTURE, SITE, chain=CHAIN,
                           pH_from=ACID_SPAN[0], pH_to=ACID_SPAN[1])
    home = phsites.analyse(STRUCTURE, SITE, chain=CHAIN,
                           pH_from=HOME_SPAN[0], pH_to=HOME_SPAN[1])

    fasta_seq = ROOT / "data" / "sequences" / f"{ACCESSION}.fasta"
    if not fasta_seq.exists():
        print(f"missing {fasta_seq}; run tools.design_construct --uniprot "
              f"{ACCESSION}", file=sys.stderr)
        return 1
    seq = "".join(l.strip() for l in fasta_seq.read_text().splitlines()[1:]
                  if not l.startswith(">"))
    pi = phsites.isoelectric_point(seq)

    stem = f"{TARGET}_{MUTATION}"
    cj = ROOT / "data" / "constructs" / f"{stem}.json"
    cf = ROOT / "data" / "constructs" / f"{stem}.fasta"
    if not cj.exists():
        print(f"missing {cj}; run tools.design_construct --target {TARGET} "
              f"--uniprot {ACCESSION} --mutate {MUTATION} --offset {OFFSET}",
              file=sys.stderr)
        return 1
    report = json.loads(cj.read_text())
    dna = "".join(l for l in cf.read_text().split(">")[2].splitlines()[1:])

    his = next(x for x in acid["rows"] if x["residue"] == "HIS65")
    cap = metals.capacity("steel", FRAGMENT_MG)
    chel = metals.chelator_demand("steel", FRAGMENT_MG, DEBULK)
    h2 = metals.hydrogen_evolution("steel", FRAGMENT_MG, DEBULK)

    common = {
        "{{STYLE}}": f"<style>\n{CSS.read_text()}</style>",
        "{{BUILT}}": _dt.date.today().isoformat(),
        "{{DNA_BP}}": report["dna_length_bp"],
        "{{TITRATABLE}}": acid["titratable_total"],
        "{{ACID_N}}": acid["responsive_in_span"],
        "{{HOME_N}}": home["responsive_in_span"],
        "{{HIS65_FROM}}": f'{his["charged_fraction_at_from"] * 100:.0f}',
        "{{HIS65_TO}}": f'{his["charged_fraction_at_to"] * 100:.0f}',
        "{{PI}}": pi["pI"],
        "{{NET_CHARGE}}": pi["net_charge_at_7_4"],
        "{{SWAPS}}": len(report["codon_swaps_from_preferred"]),
        "{{FRAGMENT_MG}}": f"{FRAGMENT_MG:g}",
        "{{FERRITIN_MG}}": f'{cap["ferritin_mg"]:.0f}',
        "{{FERRITIN_RATIO}}": f'{cap["ratio_to_fragment"]:.1f}',
        "{{DFO_MG}}": f'{chel["dfo_free_base_mg"]:.0f}',
        "{{H2_ML}}": f'{h2["h2_ml_at_37c"]:.1f}',
        "{{GAP_TOTAL}}": gaps.summary()["total"],
        "{{GAP_OPEN}}": gaps.summary()["open"],
        "{{GAP_CLOSED}}": gaps.summary()["closed"],
        "{{ELEMENTS_UNCAPTURED}}": f'{_uncaptured():.2f}',
    }

    for lang, (src, out) in SOURCES.items():
        if not src.exists():
            print(f"missing {src}", file=sys.stderr)
            return 1
        L = LABELS[lang]
        subs = dict(common)
        subs["{{OTHER_URL}}"] = SOURCES["en" if lang == "he" else "he"][1].name
        subs["{{TABLE_SITES}}"] = table_sites(acid, home, L)
        subs["{{TABLE_CONSTRUCT}}"] = table_construct(report, L)
        subs["{{SEQUENCE_BLOCK}}"] = sequence_block(report, dna, L)
        subs["{{TABLE_GAPS}}"] = table_gaps(lang, L)

        text = src.read_text()
        for token, value in subs.items():
            text = text.replace(token, str(value))
        left = sorted(set(re.findall(r"\{\{[A-Z_]+\}\}", text)))
        if left:
            print(f"{lang}: unsubstituted token(s): {left}", file=sys.stderr)
            return 1
        out.write_text(text)
        print(f"wrote {out} ({len(text) // 1024} KB)")

    print(f"  target        {TARGET} / {ACCESSION} / 1FHA chain {CHAIN}")
    print(f"  ferroxidase   {', '.join(f'{v}{k}' for k, v in EXPECTED.items())}")
    print(f"  His65         {common['{{HIS65_FROM}}']}% -> "
          f"{common['{{HIS65_TO}}']}% protonated across pH 7.4 to 5.5")
    print(f"  responsive    {acid['responsive_in_span']} of "
          f"{acid['titratable_total']} (vs {home['responsive_in_span']} at "
          f"ferritin's own pH)")
    print(f"  construct     {report['dna_length_bp']} bp, "
          f"{report['gc_percent']}% GC, "
          f"{len(report['codon_swaps_from_preferred'])} swaps")
    print(f"  gaps recorded {gaps.summary()['total']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
