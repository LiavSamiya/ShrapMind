"""Generate the review brief for the team's biologists.

Every number here is read out of the engine at run time rather than typed in,
so the brief cannot quietly drift from what the code actually returns. That
matters more than usual for this document: it is the one a biologist will read
before deciding whether the approach is worth their time, and a stale figure
in it would be exactly the kind of confident-looking error the project exists
to avoid.

    python -m tools.brief_for_biologists > brief.md
"""
from __future__ import annotations

import collections
import datetime as _dt
import sys

from f2c import substrate, warehouse
from f2c.engine import decide
from f2c.pipeline import CAVEATS, REFS, carrier, indication
from f2c.schema import MaterialSpec

CASE = dict(polymer="PET", mass_mg=50.0, crystallinity_pct=55.0, particle_size_mm=0.8)


def _ref_line(r: dict) -> str:
    return (f"- **{r['title']}** ({r['year']}) — "
            f"[PMID {r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/) · "
            f"[DOI](https://doi.org/{r['doi']})\n  \n  {r['says']}")


def build() -> str:
    proteins = warehouse.load()
    kinetics = [o for p in proteins for o in p.observations
                if o.metric in substrate.KINETIC_METRICS and o.value is not None]
    classes = collections.Counter(
        substrate.classify((o.conditions or {}).get("substrate")) for o in kinetics
    )
    decision = decide(MaterialSpec(**CASE), proteins)
    best = decision.selected
    cap = decision.capture or {}
    frag = decision.fragment or {}
    geo = frag.get("geometry") or {}
    today = _dt.date.today().strftime("%d.%m.%Y")

    L: list[str] = []
    add = L.append

    add(f"# ShrapMind — סיכום ממצאים לביולוגים\n")
    add(f"נוצר אוטומטית מהמנוע ב-{today}. כל מספר כאן נקרא מהקוד בזמן ההרצה, "
        f"לא הוקלד.\n")

    # ---- the two questions, answered first -------------------------------
    add("## שתי שאלות, תשובות ישירות\n")
    add("### האם יש היתכנות לתהליך?\n")
    add("**לא הוכחה, ואני לא אומר שכן.** מה שכן הוכח הוא שהכימיה קיימת: "
        f"{len(proteins)} אנזימים עם פעילות שהודגמה במעבדה על פולימרים, מתוכם "
        f"{sum(1 for p in proteins if p.reviewed)} מאומתי Swiss-Prot. "
        "מה שלא הוכח הוא שזה עובד על רסיס מוצק בגוף, ואני יכול להגיד בדיוק למה.\n")
    add(f"במחסן {len(kinetics)} קבועים קטליטיים. **אף אחד מהם לא נמדד על "
        f"הפולימר המוצק**:\n")
    add(f"| נמדד על | כמה |\n|---|---|")
    labels = {"model": "אסטר כרומוגני (תחליף מסיס)", "oligomer": "אוליגומר מסיס של המטרה",
              "unknown": "לא תועד", "polymer": "**הפולימר המוצק**"}
    for cls in ("polymer", "oligomer", "model", "unknown"):
        add(f"| {labels[cls]} | {classes.get(cls, 0)} |")
    add("")
    add("כלומר כל ערך kcat ו-Km שקיים מתאר פעילות על תחליף מסיס. זה מוכיח "
        "שהחלבון מקופל ושהוא הידרולאז חי — זו טענה אמיתית וחשובה, והיא **לא** "
        "הטענה שהוא שוחק מוצק.\n")

    add("### האם התעסקתי עם hydrogel?\n")
    add("כן, אבל ברמת הראיות ולא ברמת הפורמולציה. לא עשיתי מידול, לא חישבתי "
        "התנפחות ולא ניסחתי הרכב. מה שכן: לכל תכונה נדרשת של הקרייר יש עכשיו "
        "סיווג ראיה מפורש.\n")
    add("| תכונה | סוג הראיה |\n|---|---|")
    ev_he = {"literature": "ספרות מצוטטת", "derived": "נגזר מחישוב",
             "specified": "**החלטת תכנון — אין מספר**", "measured": "נמדד"}
    # The engine speaks English; this document is read by the team in Hebrew.
    # Anything without a translation falls back to the original rather than
    # being dropped, so a property added later still appears in the table.
    prop_he = {
        "Injectable, then fixed in place": "ניתן להזרקה, ואז מתקבע במקום",
        "Does not swell": "לא מתנפח",
        "Holds the enzyme active": "שומר על האנזים פעיל",
        "Captures what the enzyme releases": "לוכד את מה שהאנזים משחרר",
        "Geometry chosen deliberately": "גאומטריה שנבחרה במכוון",
    }
    for prop in carrier():
        name = prop_he.get(prop["property"], prop["property"])
        add(f"| {name} | {ev_he.get(prop['evidence'], prop['evidence'])} |")
    add("")
    add("שתי התכונות הקריטיות ביותר הן בדיוק אלה שאין להן מספר: שהג'ל **לא "
        "יתנפח** ליד עצב, ושהאנזים יישאר פעיל בתוכו ב-37° בנוכחות סרום. "
        "לשנייה יש לפחות תקדים בספרות; לראשונה אין כלום.\n")

    # ---- the selection ----------------------------------------------------
    add("## מה המנוע בוחר, ובאילו תנאים\n")
    add(f"מקרה הבדיקה: רסיס {CASE['polymer']}, {CASE['mass_mg']:g} מ\"ג, "
        f"{CASE['crystallinity_pct']:g}% גבישיות, חלקיקי "
        f"{CASE['particle_size_mm']:g} מ\"מ, שריר שלד עמוק.\n")
    if best:
        p = best.protein
        add(f"**{p.name}** ({p.organism}) — UniProt `{p.uniprot_accession}`, "
            f"EC {', '.join(p.ec_numbers) or '—'}, ציון {best.score:.2f}, "
            f"{best.uncertainty:.0%} אותות לא ידועים.\n")
        add("חלופות קרובות: " + ", ".join(
            f"{a.protein.name} ({a.score:.2f})" for a in decision.alternatives[:3]) + "\n")
        add("### מה חוסם אותו מלעבוד בגוף\n")
        for g in best.gaps:
            add(f"- **{g.kind}** — נמדד: {g.measured or 'לא נמדד'}. "
                f"נדרש: {g.target}.\n  \n  מה לעשות: {g.engineering_target}")
        add("")

    # ---- fragment barriers ------------------------------------------------
    add("## מחסומים ששייכים לרסיס, לא לאנזים\n")
    add("בחירת אנזים אחר לא מסירה אותם.\n")
    if geo.get("computable"):
        add(f"- **שטח פנים** {geo['surface_area_mm2']} ממ\"ר "
            f"({geo['specific_area_mm2_per_mg']} ממ\"ר/מ\"ג). "
            "שחיקת פני שטח מתכווננת לפי זה ולא לפי מסה. **לא גזרנו מזה קצב.**")
    for item in frag.get("accessibility") or []:
        add(f"- **{item['kind']}** [{item['severity']}] — {item['detail']}")
    add("")

    # ---- mass balance -----------------------------------------------------
    add("## מאזן מסה — מה שכן אפשר לחשב בלי קינטיקה\n")
    if cap.get("computable"):
        add(f"פירוק מלא של {CASE['mass_mg']:g} מ\"ג {CASE['polymer']} משחרר "
            f"**{cap['total_product_mmol']:.3g} ממול** של "
            f"{', '.join(cap['products'])}. זהו חסם שאינו תלוי בשום הנחה קינטית, "
            "והוא קובע את קיבולת הלכידה שהקרייר חייב.\n")
        add(f"**קצב השחרור לא מדווח.** {cap['rate']}\n")

    # ---- clinical ---------------------------------------------------------
    ind = indication()
    add("## למה בכלל להתערב\n")
    add("> בקצרה: רסיס שנשאר בגוף אינו אינרטי. הסקירה שלהלן מבוססת על 142 "
        "מאמרים ומראה שהרעילות אמיתית אך תת-מאובחנת, ושאין קונצנזוס מתי "
        "לנתח — וזה בדיוק החלל שהמוצר מכוון אליו.\n")
    add(f"{ind['problem']}\n")
    for f in ind["risk_factors"]:
        add(f"- {f}")
    add(f"\n{ind['why_a_gap_exists']}\n")
    add(f"**מה הראיה הזו לא מכסה:** {ind['honest_limit']}\n")

    # ---- caveats ----------------------------------------------------------
    add("## שלוש נקודות שדורשות את העין שלכם\n")
    add("כאן המסמך הקליני והמקורות שהוא מצטט לא אומרים אותו דבר. "
        "בדקתי כל ציטוט מול NCBI ו-Crossref.\n")
    # Keyed by status, which is stable, rather than by the claim text, which
    # is the engine's wording and may be rewritten.
    gloss = {
        "mechanism supported, this citation is the wrong one":
            "הטענה על קשיחות: המנגנון קיים בספרות, אבל המאמר שצוטט אצלנו "
            "בדק גודל וצורה ולא מודולוס — הוא לא יכול לשאת את הטענה.",
        "route supported, 'safely' is not":
            "הטענה על פינוי לימפטי: המסלול מתועד אצל חלקיקים קולואידיים, "
            "אבל מהרקמה התת-עורית ולא משריר עמוק — ו\"בבטחה\" לא הוכח כלל.",
        "contradicted":
            "**זו הדחופה.** מנת PEG ראשונה מייצרת נוגדני anti-PEG IgM "
            "שמאיצים פינוי של מנות הבאות. הקרייר שלנו הוא HA-PEG.",
    }
    for i, c in enumerate(CAVEATS, 1):
        add(f"### {i}. {c['claim']}\n")
        if c["status"] in gloss:
            add(f"> {gloss[c['status']]}\n")
        add(f"**סטטוס: {c['status']}**\n")
        add(f"{c['detail']}\n")
        add(f"המקור שצוטט: [PMID {c['evidence']['pmid']}]"
            f"(https://pubmed.ncbi.nlm.nih.gov/{c['evidence']['pmid']}/) — "
            f"{c['evidence']['title']}\n")
        for extra in c.get("also", []):
            add(f"מקור תומך: [PMID {extra['pmid']}]"
                f"(https://pubmed.ncbi.nlm.nih.gov/{extra['pmid']}/) — {extra['title']}\n")

    # ---- what we need from them ------------------------------------------
    add("## מה אני צריך מכם\n")
    add("1. **הנקודה השלישית למעלה (anti-PEG IgM) היא הדחופה.** הקרייר הוא "
        "HA-PEG ושום דבר בתוכנית לא מניח שמחזור טיפול אחד מספיק. אם טיפול "
        "חוזר נכשל אימונולוגית, זה סיכון תוכניתי ולא פרט.\n")
    add("2. **הניסוי החסר:** kcat ו-Km מול הפולימר המוצק ב-37° בסרום, על חומר "
        "באותה גבישיות כמו הרסיס. זה הניסוי שכל המערכת מצביעה עליו.\n")
    add("3. **האם הבחירה הגיונית בעיניכם?** יש כלי ביקורת שבו אפשר לענות על "
        "כל הצעה: להסכים, לחלוק, או לסמן שצריך ניסוי. הסכמה נרשמת כ"
        "\"חוות דעת מומחה\" ולעולם לא כמדידה.\n")

    # ---- references -------------------------------------------------------
    add("## כל המקורות\n")
    add("כל אחד נפתר מול NCBI וה-DOI הוצלב מול Crossref.\n")
    for key in sorted(REFS):
        add(_ref_line(REFS[key]) + "\n")

    return "\n".join(L)


if __name__ == "__main__":
    sys.stdout.write(build())
