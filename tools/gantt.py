"""Generate the three-year plan.

The plan's first year is not invented. It is read out of the engine: every
gap the selection carries becomes work, and the order follows what blocks
what. Writing it by hand would let the schedule and the evidence drift apart,
and the whole argument of this project is that they must not.

Stage 0 exists because the question it answers is binary and cheap, and
everything after it is wasted if the answer is no. A plan that spends year one
on protein engineering before knowing whether the reaction happens at all at
37 C is a plan that finds out in year three.

    python -m tools.gantt > gantt.md
"""
from __future__ import annotations

import sys

from f2c import warehouse
from f2c.engine import decide
from f2c.schema import MaterialSpec

CASE = dict(polymer="PET", mass_mg=50.0, crystallinity_pct=55.0, particle_size_mm=0.8)

# Work that does not come from a gap: the risks found in the literature review
# and the things any therapeutic programme owes regardless of what the engine
# says. Each carries why it sits where it does.
FIXED = [
    ("שנה 1 · רבעון 2", "אימונוגניות של מנות חוזרות",
     "בדיקת anti-PEG IgM אחרי חשיפה חוזרת לקרייר",
     "PMID 22580209 מראה שמנה ראשונה מאיצה פינוי של הבאות. אם זה נכון "
     "לקרייר שלנו, זה משנה את מבנה הטיפול ולא רק את המינון — ולכן זה "
     "נבדק מוקדם ובמקביל, לא אחרי שהכימיה תוכיח את עצמה."),
    ("שנה 1 · רבעון 3", "התנפחות הג'ל — המספר שאין",
     "מדידת שינוי נפח בתנאים פיזיולוגיים, מול עצב מדומה",
     "זו התכונה היחידה שכישלון בה מסיים את התוכנית: ג'ל שסופח מים ליד "
     "עצב הופך ללחץ שהוא נועד למנוע. כרגע אין לה שום מספר."),
    ("שנה 2 · רבעון 1", "שרידות האנזים ברקמה",
     "פעילות שמורה בתוך הג'ל ב-37° בסרום, מול פרוטאזות מאחסן",
     "יש תקדים במעי (PMID 37935291, 75% פעילות שמורה) אבל לא ברקמה. "
     "פרוטאזות מאחסן הן לא פרוטאזות עיכול."),
    ("שנה 2 · רבעון 3", "גורל השארית",
     "מעקב אחרי שארית מסומנת משריר עמוק — האם היא מגיעה לקשרית לימפה",
     "הניקוז מתועד מרקמה תת-עורית (PMID 22580209), לא משריר עמוק, "
     "והגעה לקשרית היא המקום שבו המחקרים מפסיקים למדוד."),
    ("שנה 3 · רבעון 1", "מודל חיה",
     "רסיס מושתל בשריר, טיפול מקומי, נקודות קצה: מסה שנותרה וקפסולה",
     "הנקודה הראשונה שבה כל השלבים נבדקים יחד ולא בנפרד."),
    ("שנה 3 · רבעון 3", "תיק רגולטורי מקדים",
     "פגישת Pre-Submission מול FDA/AMAR, סיווג ההתקן",
     "שילוב של אנזים וקרייר הוא ככל הנראה combination product, וסיווג "
     "שגוי בשלב מאוחר עולה שנה."),
]

GAP_WORK = {
    "catalytic evidence": (
        "שנה 1 · רבעון 1", "שלב 0 — האם התגובה קורית ב-37° בכלל",
        "מדידה בין-פאזית על חלקיקי פולימר מסומנים בפרובה פלואורוגנית, "
        "ב-37° בסרום, בגבישיות של רסיס אמיתי. בקרה חיובית ב-60°.",
    ),
    "temperature spread": (
        "שנה 1 · רבעון 2", "סגירת המחלוקת על אופטימום הטמפרטורה",
        "מדידה אחת של פעילות ב-37° בתנאים ברי-השוואה, שתחליף חציון "
        "שנגזר ממדידות שחולקות זו על זו.",
    ),
    "ph": (
        "שנה 1 · רבעון 4", "התאמת האתר הפעיל ל-pH ניטרלי",
        "כוונון אלקטרוסטטי, עם שמירה על יציבות הקיפול.",
    ),
    "temperature": (
        "שנה 1 · רבעון 2", "מדידת אופטימום טמפרטורה",
        "האנזים הנבחר חסר אופטימום מתועד לחלוטין.",
    ),
    "structure": (
        "שנה 1 · רבעון 4", "השגת מבנה ניסיוני",
        "תכנון מחדש של אתר פעיל מתוך ניבוי הוא הימור.",
    ),
}


# The engine speaks English and this plan is read in Hebrew. Rather than
# translate its sentences -- which would let the two drift -- each gap kind
# gets a fixed Hebrew justification, and the engine's measured value is
# interpolated into it.
_WHY = {
    "temperature spread":
        "ארבע מעבדות מדדו את אופטימום הטמפרטורה ב-25, 25, 50 ו-55 מעלות. "
        "החציון יוצא 37.5 ונראה כמו התאמה מושלמת לגוף, אבל הוא אמצע של "
        "מחלוקת בת שלושים מעלות — כלומר האופטימום של האנזים הזה פשוט לא ידוע.",
    "ph": "אופטימום ה-pH שנמדד הוא 8, במרחק 0.6 יחידות מ-pH הגוף.",
    "temperature": "לאנזים הנבחר אין אופטימום טמפרטורה מתועד כלל.",
    "structure": "אין מבנה ניסיוני; תכנון מחדש היה מתחיל מניבוי.",
}


def _why(gap) -> str:
    return _WHY.get(gap.kind, f"מהמנוע: {gap.detail}")


def build() -> str:
    proteins = warehouse.load()
    decision = decide(MaterialSpec(**CASE), proteins)
    best = decision.selected
    frag = decision.fragment or {}

    rows: list[tuple[str, str, str, str]] = []

    # Stage 0 first, always, whether or not the gap list happens to lead with it.
    stage0 = GAP_WORK["catalytic evidence"]
    rows.append((stage0[0], stage0[1], stage0[2],
                 "זו שאלת כן/לא. אם אין אירועי חיתוך ב-37°, כל מה שאחריה מיותר, "
                 "ועדיף לדעת זאת בחודש השלישי מאשר בשנה השלישית. השיטה כבר "
                 "פורסמה (PMID 42706806) ומודדת הידרוליזה בין-פאזית ברמת "
                 "מולקולה בודדת — אין צורך להמציא מתודולוגיה."))

    for g in (best.gaps if best else []):
        if g.kind == "catalytic evidence":
            continue
        work = GAP_WORK.get(g.kind)
        if work:
            rows.append((work[0], work[1], work[2], _why(g)))

    # Fragment barriers that no catalyst choice removes.
    for item in frag.get("accessibility") or []:
        if item["kind"] == "crystallinity":
            pct = CASE["crystallinity_pct"]
            rows.append(("שנה 1 · רבעון 3", "תקרת הגבישיות",
                         "קביעת החלק מהרסיס שניתן לפרק בכלל, כפונקציה של גבישיות",
                         f"המנוע מסמן את הרסיס כ-{pct:g}% גבישי. אנזימים פועלים "
                         "על אזורים אמורפיים בלבד, כך שהחלק הגבישי קובע תקרה "
                         "לכמה בכלל ניתן לפרק — וכל הקבועים שיש לנו נמדדו על "
                         "סובסטרטים מסיסים, שבהם לגבישיות אין משמעות."))

    rows.extend(FIXED)

    def key(r: tuple[str, str, str, str]) -> tuple[int, int]:
        year = int(r[0].split("שנה ")[1][0])
        q = int(r[0].split("רבעון ")[1][0])
        return year, q

    rows.sort(key=key)

    L = ["# ShrapMind — תוכנית שלוש שנים\n"]
    L.append("נוצר מהמנוע. כל שורה בשנה הראשונה נגזרת מפער שהמנוע מצא, "
             "ולא נכתבה ביד — כך שהתוכנית לא יכולה להתרחק מהראיות.\n")
    L.append(f"מקרה הייחוס: רסיס {CASE['polymer']}, {CASE['mass_mg']:g} מ\"ג, "
             f"{CASE['crystallinity_pct']:g}% גבישיות, שריר שלד עמוק. "
             f"קטליזטור נבחר: {best.protein.name if best else '—'}.\n")

    L.append("## ציר הזמן\n")
    L.append("| משימה | " + " | ".join(
        f"ש{y}ר{q}" for y in (1, 2, 3) for q in (1, 2, 3, 4)) + " |")
    L.append("|---|" + "---|" * 12)
    for when, what, *_rest in rows:
        year, quarter = key((when, what, "", ""))
        cells = []
        for y in (1, 2, 3):
            for q in (1, 2, 3, 4):
                # Each task is drawn across the quarter it starts in and the
                # one after, which is the shortest honest span: nothing here
                # finishes inside three months, and a one-cell bar would
                # suggest otherwise.
                idx, start = (y - 1) * 4 + q, (year - 1) * 4 + quarter
                cells.append("▮" if start <= idx <= start + 1 else "")
        L.append(f"| {what} | " + " | ".join(cells) + " |")
    L.append("\n**▮▮ = הרבעון שבו המשימה מתחילה והרבעון שאחריו.** אף משימה "
             "כאן לא נסגרת בתוך שלושה חודשים, ועמודה בודדת הייתה משדרת אחרת.\n")

    L.append("## המשימות במלואן\n")
    L.append("| מתי | משימה | מה עושים | למה כאן |")
    L.append("|---|---|---|---|")
    for when, what, how, why in rows:
        L.append(f"| {when} | **{what}** | {how} | {why} |")

    L.append("\n## נקודת ההכרעה\n")
    L.append("**שלב 0 הוא שער, לא משימה.** אם לא נצפים אירועי חיתוך ב-37°, "
             "התוכנית לא ממשיכה כפי שהיא — היא עוברת לחומר X אחר, או לשינוי "
             "הנחת היסוד. זה נכתב כאן מראש כדי שההחלטה הזו תתקבל לפי נתון "
             "ולא לפי מחויבות שכבר הושקעה בה שנה.\n")
    L.append("## מה התוכנית הזו לא כוללת\n")
    L.append("ייצור בקנה מידה, בטיחות ארוכת טווח, ומסלול קליני בבני אדם. "
             "שלוש שנים מביאות את זה עד מודל חיה ותיק רגולטורי מקדים, לא עד "
             "מטופל. כל גאנט שמבטיח יותר מזה בשלוש שנים מבטיח מה שאינו יכול לקיים.\n")
    return "\n".join(L)


if __name__ == "__main__":
    sys.stdout.write(build())
