"""What the project does not know, held as data rather than as prose.

Every other module here records what is known and labels its provenance. This
one records the complement: the questions nobody on the team has answered,
including the ones that are nobody's fault because no literature exists.

It is a separate module for a reason. A gap mentioned in a chat message, a
review paragraph or a verbal hand-off is a gap that disappears -- and the two
feasibility documents the team produced, both careful and both well sourced,
between them do not mention a single item on this list. Not because the
authors missed them: because a document answers the question it set out to
answer, and these fall between the documents.

Each entry says what is missing, why it matters, what would close it, and who
is placed to close it. `severity` is about consequence, not difficulty:

  blocks_injection  nothing can be put into an animal, let alone a person,
                    until this is answered
  blocks_trial      a trial could not be designed or read without it
  blocks_claim      a specific claim the project makes rests on it
  incomplete        real, bounded, and not in the critical path

The ordering is deliberate: `premise` comes first because if it fails, every
other entry becomes irrelevant.
"""
from __future__ import annotations

from typing import Any

OPEN = "open"
CLOSED = "closed"
# A gap is closed when the thing that was missing exists. It is not closed
# because someone intends to do it, and it is not removed from the register
# when it closes: the record of what was missing and what closed it is worth
# as much as the absence was. Entries carry `closed_by`, and where closing one
# left something smaller behind, `residual` says what.

BLOCKS_INJECTION = "blocks_injection"
BLOCKS_TRIAL = "blocks_trial"
BLOCKS_CLAIM = "blocks_claim"
INCOMPLETE = "incomplete"

SEVERITY_ORDER = (BLOCKS_INJECTION, BLOCKS_TRIAL, BLOCKS_CLAIM, INCOMPLETE)

GAPS: tuple[dict[str, Any], ...] = (
    {
        "id": "premise",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "Answered, and answered against the premise. Rochkind 2014 "
            "(PMID 24898760), 42 patients and 58 nerves with 26 of them "
            "shrapnel at a median 33 months: the presence of foreign "
            "particles PREDICTED A WORSE outcome, 28% pain improvement "
            "against 67% without them, and nerve grafting beat neurolysis "
            "100% to 47%. Relieving the compression is not what relieves "
            "the pain; replacing the destroyed segment is. Rochkind 2026 "
            "(PMID 42006932), 107 patients, adds that about 55% of "
            "shrapnel nerve injuries carry the fragment inside the nerve "
            "rather than beside it."
        ),
        "closed_by_he": (
            "נענה, והתשובה נגד ההנחה. Rochkind 2014 (PMID 24898760), 42 "
            "מטופלים ו-58 עצבים מהם 26 מרסס, מעקב חציוני 33 חודשים: נוכחות "
            "חלקיקים זרים ניבאה תוצאה גרועה יותר — 28% שיפור בכאב מול "
            "67% בלעדיהם — והשתלת עצב ניצחה נוירוליזה 100% מול 47%. "
            "שחרור הלחץ אינו מה שמקל על הכאב; החלפת המקטע ההרוס היא. "
            "Rochkind 2026 (PMID 42006932) מוסיף ש-55% מפגיעות הרסס הן עם "
            "הרסיס בתוך העצב ולא לידו."
        ),
        "consequence": (
            "The indication narrows rather than disappearing. The product "
            "addresses fragments causing mechanical pressure on an intact "
            "nerve, which is a real population and a smaller one. It does "
            "not address a fragment lodged in an injured nerve, where the "
            "evidence says graft. Saying so before the pitch is worth more "
            "than being asked it during."
        ),
        "residual": (
            "How large the intact-nerve population is. Rochkind separates "
            "intraneural from extraneural but does not report outcomes "
            "for extraneural fragments as its own arm."
        ),
        "area": "clinical",
        "severity": BLOCKS_TRIAL,
        "title": "Nobody has shown that removing volume relieves the symptom",
        "title_he": "אף אחד לא הראה שהורדת נפח מקלה על הסימפטום",
        "what_is_missing": (
            "The whole product rests on one assumption: that making a fragment "
            "smaller reduces the pressure on the nerve beside it. No source in "
            "this project supports it -- not the engine, not the clinical "
            "feasibility review, not the carrier document."
        ),
        "what_is_missing_he": (
            "כל המוצר נשען על הנחה אחת: שהקטנת רסיס מפחיתה את הלחץ על העצב "
            "שלידו. אף מקור בפרויקט לא תומך בה — לא המנוע, לא הסקירה הקלינית "
            "ולא מסמך הנשא."
        ),
        "why_it_matters": (
            "If the pressure comes from the contracting fibrotic capsule "
            "rather than from the fragment's bulk, then debulking solves the "
            "wrong problem and no amount of enzyme engineering fixes that. "
            "This is the only gap on the list that can invalidate the others."
        ),
        "why_it_matters_he": (
            "אם הלחץ מגיע מהקפסולה הפיברוטית המתכווצת ולא מנפח הרסיס, אז "
            "הורדת נפח פותרת את הבעיה הלא נכונה, ושום הנדסת אנזים לא תתקן את "
            "זה. זה הפער היחיד ברשימה שיכול לבטל את כל השאר."
        ),
        "what_would_close_it": (
            "A literature search of the surgical series: in retained-fragment "
            "cases where symptoms resolved after removal, was the mechanism "
            "decompression or neurolysis? Surgeons have this data. It is a "
            "reading task, not an experiment."
        ),
        "whose": "clinical lead, before the pitch",
    },
    {
        "id": "endotoxin",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "Stage 4 of the protocol now carries a polymyxin-B or "
            "anion-exchange depletion step after IMAC, with LAL as a "
            "release test, in both languages."
        ),
        "closed_by_he": (
            "שלב 4 בפרוטוקול נושא עכשיו הסרת אנדוטוקסין בזיקה "
            "לפולימיקסין-B או חילוף אניונים אחרי IMAC, עם LAL כבדיקת "
            "שחרור, בשתי השפות."
        ),
        "area": "protein",
        "severity": BLOCKS_INJECTION,
        "title": "No endotoxin removal step anywhere in the protocol",
        "title_he": "אין שום שלב להסרת אנדוטוקסין בפרוטוקול",
        "what_is_missing": (
            "Protein expressed in E. coli carries lipopolysaccharide. The FDA "
            "limit for parenteral products is 5 EU per kg per hour. The "
            "protocol purifies by IMAC and SEC and then stops."
        ),
        "what_is_missing_he": (
            "חלבון שמבוטא ב-E. coli נושא ליפופוליסכריד. המגבלה של ה-FDA "
            "למוצרים פרנטרליים היא 5 EU לק\"ג לשעה. הפרוטוקול מטהר ב-IMAC "
            "וב-SEC ועוצר שם."
        ),
        "why_it_matters": (
            "Without it nothing from this protocol can go into an animal, let "
            "alone a person. Endotoxin also causes exactly the inflammatory "
            "response the product exists to reduce, so a contaminated "
            "preparation would read as a failed therapy rather than as a "
            "failed purification."
        ),
        "why_it_matters_he": (
            "בלעדיו שום דבר מהפרוטוקול לא יכול להיכנס לבעל חיים, קל וחומר "
            "לאדם. אנדוטוקסין גם גורם בדיוק לתגובה הדלקתית שהמוצר קיים כדי "
            "להפחית, ולכן תכשיר מזוהם ייקרא ככישלון טיפולי ולא ככישלון טיהור."
        ),
        "what_would_close_it": (
            "Add a polymyxin-B or anion-exchange depletion step after IMAC, "
            "and a LAL assay as a release test with a stated limit. Both are "
            "routine."
        ),
        "whose": "whoever runs the purification",
    },
    {
        "id": "enzyme_dose",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "metals.enzyme_dose() closes it as arithmetic rather than as "
            "a number. The rate has no default and the function refuses "
            "without one, so the gap is now exactly one measurement wide "
            "-- stage 2 of the protocol produces that measurement, and "
            "the dose follows the way the chelator mass already does."
        ),
        "closed_by_he": (
            "metals.enzyme_dose() סוגרת אותו כאריתמטיקה ולא כמספר. לקצב "
            "אין ברירת מחדל והפונקציה מסרבת בלעדיו, כך שהפער ברוחב מדידה "
            "אחת בדיוק — שלב 2 בפרוטוקול מייצר אותה, והמינון נובע כמו "
            "שמסת המכלב כבר נובעת."
        ),
        "area": "formulation",
        "severity": BLOCKS_TRIAL,
        "title": "How many milligrams of enzyme go into the depot",
        "title_he": "כמה מיליגרם אנזים נכנסים לדפו",
        "what_is_missing": (
            "The engine computes ferritin mass, deferoxamine mass and even "
            "hydrogen volume from the fragment. It does not compute an enzyme "
            "dose, because a dose needs a rate and no rate has been measured "
            "on a solid substrate at body conditions."
        ),
        "what_is_missing_he": (
            "המנוע מחשב מסת פריטין, מסת DFO ואפילו נפח מימן מתוך הרסיס. הוא "
            "לא מחשב מינון אנזים, כי מינון דורש קצב ואף קצב לא נמדד על "
            "סובסטרט מוצק בתנאי גוף."
        ),
        "why_it_matters": (
            "Every formulation decision depends on it: gel volume, loading "
            "density, whether the carrier can physically hold the amount "
            "needed. It is also the first number a regulator asks for."
        ),
        "why_it_matters_he": (
            "כל החלטת פורמולציה תלויה בו: נפח הג'ל, צפיפות ההעמסה, והאם הנשא "
            "בכלל יכול להחזיק פיזית את הכמות הדרושה. זה גם המספר הראשון "
            "שרגולטור מבקש."
        ),
        "what_would_close_it": (
            "Stage 7 of the protocol -- rate per unit surface area on real "
            "substrate. The dose follows from it arithmetically, as the "
            "chelator mass already does."
        ),
        "whose": "follows from the bench work; nothing to do before it",
    },
    {
        "id": "readout",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "metals.readout() names the assay and computes the flux. Not "
            "the fragment but what leaves it: human iron excretion is "
            "unregulated (PMID 38489995), so there is no physiological "
            "iron flux into urine for a signal to hide behind, and "
            "deferoxamine clears renally as ferrioxamine (PMID 15720959). "
            "The chelator the product already contains is its reporter."
        ),
        "closed_by_he": (
            "metals.readout() נוקב בבדיקה ומחשב את השטף. לא הרסיס אלא מה "
            "שיוצא ממנו: הפרשת ברזל באדם אינה מווסתת (PMID 38489995), "
            "ולכן אין שטף ברזל פיזיולוגי לשתן שהאות יכול להיעלם בתוכו, "
            "ודפרוקסאמין מפונה כלייתית כפרוקסאמין (PMID 15720959). המכלב "
            "שכבר נמצא במוצר הוא גם הדיווח שלו."
        ),
        "residual": (
            "A quantitative baseline for urinary iron in an untreated "
            "person. The signal-to-background argument is mechanistic "
            "here, not computed, and no detection claim should be made "
            "until that figure is sourced."
        ),
        "area": "clinical",
        "severity": BLOCKS_TRIAL,
        "title": "No way to tell, in a living subject, whether it worked",
        "title_he": "אין דרך לדעת, בגוף חי, אם זה עבד",
        "what_is_missing": (
            "The project has no in vivo measurement. The carrier document "
            "notes that ZIF-8 nanoparticles are echogenic; nothing in the "
            "engine turns that into a readout, and fragment volume change of "
            "a few percent is below what routine imaging resolves."
        ),
        "what_is_missing_he": (
            "לפרויקט אין מדידה in vivo. מסמך הנשא מציין שחלקיקי ZIF-8 "
            "אקוסטיים; שום דבר במנוע לא הופך את זה לקריאוּת, ושינוי נפח של "
            "אחוזים בודדים נמצא מתחת לרזולוציה של הדמיה שגרתית."
        ),
        "why_it_matters": (
            "Without a readout there is no trial, only a treatment. And the "
            "quantity that matters -- a 3.6% change in edge length for a 20% "
            "debulk -- is specifically the quantity hardest to see."
        ),
        "why_it_matters_he": (
            "בלי קריאוּת אין ניסוי, רק טיפול. והכמות שחשובה — שינוי של 3.6% "
            "באורך המקצוע עבור הורדה של 20% — היא בדיוק הכמות הכי קשה לראות."
        ),
        "what_would_close_it": (
            "Measure the released iron instead of the remaining fragment. "
            "Serum ferritin and transferrin saturation, or urinary "
            "ferrioxamine, are the products of the reaction and they are "
            "assayed routinely. The output is easier to see than the input."
        ),
        "whose": "clinical lead with the chemist",
    },
    {
        "id": "specific_activity",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "Stage 5 defines it before the first reading: one micromole "
            "of Fe(II) oxidised per minute at 37 C, per milligram of "
            "protein by A280."
        ),
        "closed_by_he": (
            "שלב 5 מגדיר אותה לפני הקריאה הראשונה: מיקרומול Fe(II) "
            "מחומצן לדקה ב-37°C, למיליגרם חלבון לפי A280."
        ),
        "area": "protein",
        "severity": BLOCKS_CLAIM,
        "title": "Activity is measured without a defined unit",
        "title_he": "הפעילות נמדדת בלי יחידה מוגדרת",
        "what_is_missing": (
            "The protocol follows nitrophenol release but never defines "
            "U/mg. Without it, two preparations, two days or two laboratories "
            "cannot be compared."
        ),
        "what_is_missing_he": (
            "הפרוטוקול עוקב אחרי שחרור ניטרופנול ואף פעם לא מגדיר U/mg. "
            "בלי זה אי אפשר להשוות בין שני תכשירים, שני ימים או שתי מעבדות."
        ),
        "why_it_matters": (
            "Every rate the engine would later import depends on the unit the "
            "rate was measured in, and an undefined unit is how a number "
            "becomes unprovenanced."
        ),
        "why_it_matters_he": (
            "כל קצב שהמנוע ייבא בהמשך תלוי ביחידה שבה הוא נמדד, ויחידה לא "
            "מוגדרת היא הדרך שבה מספר מאבד את המקור שלו."
        ),
        "what_would_close_it": (
            "Define one micromole of nitrophenol released per minute at "
            "37 C and pH 7.4 as one unit, and report per milligram of protein "
            "by A280 with the computed extinction coefficient."
        ),
        "whose": "trivial; do it before the first assay, not after",
    },
    {
        "id": "biodistribution",
        "status": OPEN,
        "waiting_on": "the first in vivo study",
        "waiting_note": (
            "Not unowned, and not deferrable either: labelling the "
            "enzyme and following it costs almost nothing once an "
            "animal study is running, and nothing at all if it is "
            "designed in from the start. It becomes expensive only if "
            "the first study is run without it."
        ),
        "area": "clinical",
        "severity": BLOCKS_TRIAL,
        "title": "What happens to the enzyme after it has worked",
        "title_he": "מה קורה לאנזים אחרי שהוא עבד",
        "what_is_missing": (
            "Whether the protein stays in the depot, how much reaches "
            "circulation, and how it is cleared. Not addressed anywhere."
        ),
        "what_is_missing_he": (
            "האם החלבון נשאר בדפו, כמה מגיע למחזור הדם, ואיך הוא מפונה. לא "
            "מטופל בשום מקום."
        ),
        "why_it_matters": (
            "It is among the first questions a regulator asks, and for a "
            "microbial enzyme next to a nerve it is also an immunogenicity "
            "question: systemic exposure is what turns a local protein into a "
            "sensitising one."
        ),
        "why_it_matters_he": (
            "זו מהשאלות הראשונות שרגולטור שואל, ולאנזים מיקרוביאלי ליד עצב זו "
            "גם שאלת אימונוגניות: חשיפה מערכתית היא מה שהופך חלבון מקומי "
            "לחלבון מרגיש."
        ),
        "what_would_close_it": (
            "Label the enzyme and follow it. Standard, and it belongs in the "
            "first animal study rather than after one."
        ),
        "whose": "whoever designs the first in vivo study",
    },
    {
        "id": "contamination",
        "status": OPEN,
        "partially_closed_by": (
            "Stage 1 of the protocol now records culture of the "
            "retrieved fragment, antibiotic cover and tetanus status as "
            "enrolment criteria. What stays open is the quantity: this "
            "project has not established how often a chronically "
            "retained fragment is colonised, and the biofilm question "
            "is a potency problem as well as a safety one."
        ),
        "waiting_on": "a colonisation rate from retrieved fragments",
        "area": "clinical",
        "severity": BLOCKS_TRIAL,
        "title": "A retained fragment is a contaminated foreign body",
        "title_he": "רסיס שמור הוא גוף זר מזוהם",
        "what_is_missing": (
            "No consideration of existing bacterial colonisation, biofilm on "
            "the fragment surface, or tetanus status. The safety review "
            "mentions non-sterile fragments for wood; the metal arm does not "
            "carry it."
        ),
        "what_is_missing_he": (
            "אין התייחסות לקולוניזציה חיידקית קיימת, לביופילם על פני הרסיס או "
            "למצב חיסון טטנוס. סקר הבטיחות מזכיר רסיסים לא סטריליים לגבי עץ; "
            "זרוע המתכות לא נושאת את זה."
        ),
        "why_it_matters": (
            "Injecting a protein-rich hydrogel beside a colonised foreign body "
            "is also injecting a growth medium. And biofilm blocks the surface "
            "the catalyst is trying to reach, which makes it a potency problem "
            "as well as a safety one."
        ),
        "why_it_matters_he": (
            "הזרקת הידרוג'ל עשיר בחלבון ליד גוף זר מקולוניז היא גם הזרקת מצע "
            "גידול. וביופילם חוסם את פני השטח שהקטליזטור מנסה להגיע אליהם, "
            "ולכן זו בעיית יעילות ולא רק בעיית בטיחות."
        ),
        "what_would_close_it": (
            "Culture retrieved fragments; state antibiotic cover and tetanus "
            "status as enrolment criteria."
        ),
        "whose": "clinical lead",
    },
    {
        "id": "alloy",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "METAL_FRACTION became COMPOSITION, a per-element breakdown, "
            "and metals.released_elements() runs the mass balance element "
            "by element. For a 20% debulk of a 50 mg fragment it reports "
            "0.2 mg of manganese, silicon, carbon and phosphorus with no "
            "capture route, and names nickel and chromium as allergens "
            "deferoxamine does not bind."
        ),
        "closed_by_he": (
            "METAL_FRACTION הפך ל-COMPOSITION, פירוט לפי יסוד, "
            "ו-metals.released_elements() מריצה את מאזן המסה יסוד אחרי "
            "יסוד. להורדת 20% מרסיס 50 מ\"ג היא מדווחת 0.2 מ\"ג מנגן, "
            "סיליקון, פחמן וזרחן בלי מסלול לכידה, ונוקבת בניקל ובכרום "
            "כאלרגנים שדפרוקסאמין אינו קושר."
        ),
        "residual": (
            "The compositions are nominal for the grade, not measurements "
            "of anyone's fragment. Stage 1 of the protocol replaces them "
            "with XRF, and every non-iron figure is labelled nominal "
            "until it does."
        ),
        "area": "metal",
        "severity": BLOCKS_CLAIM,
        "title": "The alloying elements are not modelled",
        "title_he": "יסודות הסגסוגת אינם ממודלים",
        "what_is_missing": (
            "METAL_FRACTION assumes steel is 98% iron without saying which "
            "steel. Fragmentation steel carries manganese and silicon, and "
            "sometimes nickel and chromium below the stainless threshold. "
            "Nickel and chromium are recognised contact allergens."
        ),
        "what_is_missing_he": (
            "METAL_FRACTION מניח שפלדה היא 98% ברזל בלי לומר איזו פלדה. פלדת "
            "רסס נושאת מנגן וסיליקון, ולפעמים ניקל וכרום מתחת לסף הנירוסטה. "
            "ניקל וכרום הם אלרגני מגע מוכרים."
        ),
        "why_it_matters": (
            "Dissolving the fragment releases whatever is in it, not only "
            "iron, and the chelator is selective for Fe(III). Liberated "
            "nickel has neither a capture route here nor a mass balance."
        ),
        "why_it_matters_he": (
            "המסת הרסיס משחררת את כל מה שיש בו, לא רק ברזל, והמכלב סלקטיבי "
            "ל-Fe(III). לניקל משוחרר אין כאן לא מסלול לכידה ולא מאזן מסה."
        ),
        "what_would_close_it": (
            "XRF or SEM-EDS on retrieved fragments gives the composition "
            "directly, and the mass balance then runs per element."
        ),
        "whose": "anyone with access to retrieved fragments",
    },
    {
        "id": "multiple_fragments",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "metals.aggregate() sums across a patient's fragments and "
            "reports the ones with no route separately rather than "
            "dropping them. Five fragments including one stainless come "
            "to 325 mg of deferoxamine and 14.8 mL of hydrogen, with up "
            "to 70 sequential placements at the slowest rate in the "
            "bracket."
        ),
        "closed_by_he": (
            "metals.aggregate() מסכמת על פני רסיסי המטופל ומדווחת בנפרד "
            "על אלה שאין להם מסלול במקום להשמיט אותם. חמישה רסיסים "
            "שאחד מהם נירוסטה מגיעים ל-325 מ\"ג דפרוקסאמין ו-14.8 מ\"ל "
            "מימן, ועד 70 הזרקות רצופות בקצב האיטי בטווח."
        ),
        "residual": (
            "The ceiling to compare the total against. A maximum "
            "tolerated local deferoxamine dose and a maximum tolerated "
            "gas volume are both unestablished, so the function reports "
            "demand and cannot yet report acceptability."
        ),
        "area": "clinical",
        "severity": INCOMPLETE,
        "title": "Every calculation is for one fragment",
        "title_he": "כל חישוב הוא לרסיס אחד",
        "what_is_missing": (
            "Mass balance, chelator demand, placement count and hydrogen "
            "volume are all computed per fragment. A blast patient has many, "
            "sometimes of more than one material."
        ),
        "what_is_missing_he": (
            "מאזן המסה, דרישת המכלב, מספר ההזרקות ונפח המימן מחושבים כולם "
            "לרסיס אחד. לפצוע פיצוץ יש רבים, לעיתים מיותר מחומר אחד."
        ),
        "why_it_matters": (
            "The chelator ceiling and the hydrogen volume are the two "
            "quantities that do not scale comfortably. Treating five "
            "fragments is not five times a solved problem."
        ),
        "why_it_matters_he": (
            "תקרת המכלב ונפח המימן הן שתי הכמויות שלא מתרחבות בנוחות. טיפול "
            "בחמישה רסיסים אינו פי חמישה בעיה פתורה."
        ),
        "what_would_close_it": (
            "Arithmetic. Sum the per-fragment demands and report the "
            "aggregate against a per-dose ceiling, which is a short change to "
            "the engine."
        ),
        "whose": "engine; cheap",
    },
    {
        "id": "storage",
        "status": OPEN,
        "waiting_on": "the stability arm of the protocol",
        "waiting_note": (
            "Falls out of stage 6 at no extra cost once that is "
            "running. Recorded now so it is not discovered late, which "
            "is the usual way a result fails to become a thing."
        ),
        "area": "formulation",
        "severity": INCOMPLETE,
        "title": "No stability, storage or freeze-thaw data",
        "title_he": "אין נתוני יציבות, אחסון או הקפאה-הפשרה",
        "what_is_missing": (
            "Lyophilisation, excipients, freeze-thaw cycles, shelf life. A "
            "protein that loses 40% of its activity on first thaw is not a "
            "product."
        ),
        "what_is_missing_he": (
            "ליופיליזציה, אקסיפיינטים, מחזורי הקפאה-הפשרה, חיי מדף. חלבון "
            "שמאבד 40% מפעילותו בהפשרה הראשונה אינו מוצר."
        ),
        "why_it_matters": (
            "It is the difference between a result and a thing, and for a "
            "field-deployable product it is closer to the centre than it looks."
        ),
        "why_it_matters_he": (
            "זה ההבדל בין תוצאה לבין דבר, ולמוצר שאמור לעבוד בשטח זה קרוב "
            "למרכז יותר ממה שזה נראה."
        ),
        "what_would_close_it": (
            "Falls out of the stability arm of the protocol at no extra cost "
            "once that is running."
        ),
        "whose": "later; noted so it is not discovered late",
    },
    {
        "id": "aggregation",
        "status": CLOSED,
        "closed_on": "2026-11-03",
        "closed_by": (
            "Twice over. The protocol adds a dynamic light scattering "
            "read per buffer in stage 5, and the target changed: human "
            "ferritin has a theoretical pI of 5.18 against TfH's 7.96, "
            "so it sits well away from tissue pH and the colloidal "
            "stability problem this gap described does not arise."
        ),
        "closed_by_he": (
            "פעמיים. הפרוטוקול מוסיף קריאת פיזור אור דינמי לכל באפר "
            "בשלב 5, והמטרה השתנתה: ה-pI התיאורטי של פריטין אנושי הוא "
            "5.18 מול 7.96 של TfH, כלומר רחוק מ-pH הרקמה ובעיית היציבות "
            "הקולואידית שהפער תיאר אינה מתעוררת."
        ),
        "area": "formulation",
        "severity": INCOMPLETE,
        "title": "The pI finding is flagged and not acted on",
        "title_he": "ממצא ה-pI מסומן ולא מטופל",
        "what_is_missing": (
            "TfH's theoretical pI is 7.96, within one unit of tissue pH, "
            "where colloidal stability is at its minimum. The protocol notes "
            "it at the size-exclusion step and does nothing further."
        ),
        "what_is_missing_he": (
            "ה-pI התיאורטי של TfH הוא 7.96, בתוך יחידה אחת מ-pH הרקמה, שם "
            "היציבות הקולואידית מינימלית. הפרוטוקול מציין את זה בשלב ה-SEC "
            "ולא עושה יותר מזה."
        ),
        "why_it_matters": (
            "An aggregated enzyme is an inactive enzyme and an immunogenic "
            "one. For an injected depot this is a formulation question that "
            "cannot be deferred to formulation."
        ),
        "why_it_matters_he": (
            "אנזים אגרגטיבי הוא אנזים לא פעיל וגם אימונוגני. לדפו מוזרק זו "
            "שאלת פורמולציה שאי אפשר לדחות לשלב הפורמולציה."
        ),
        "what_would_close_it": (
            "Dynamic light scattering across the buffer series already being "
            "prepared for the pH profile. One extra read per sample."
        ),
        "whose": "add it to stage 4; nearly free",
    },
)


def status(gap: dict[str, Any]) -> str:
    """Open unless an entry says otherwise, so a new gap starts open."""
    return gap.get("status", OPEN)


def by_status(want: str) -> list[dict[str, Any]]:
    return [g for g in GAPS if status(g) == want]


def open_gaps() -> list[dict[str, Any]]:
    """Worst first, and only the ones still open."""
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    return sorted(by_status(OPEN), key=lambda g: (rank[g["severity"]], g["id"]))


def by_severity(severity: str | None = None) -> list[dict[str, Any]]:
    """Gaps, worst first. `severity` narrows to one band."""
    rank = {s: i for i, s in enumerate(SEVERITY_ORDER)}
    rows = [g for g in GAPS if severity is None or g["severity"] == severity]
    return sorted(rows, key=lambda g: (rank[g["severity"]], g["id"]))


def summary() -> dict[str, Any]:
    counts: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    by_state = {OPEN: len(by_status(OPEN)), CLOSED: len(by_status(CLOSED))}
    areas: dict[str, int] = {}
    for g in GAPS:
        counts[g["severity"]] += 1
        areas[g["area"]] = areas.get(g["area"], 0) + 1
    return {
        "total": len(GAPS),
        "open": by_state[OPEN],
        "closed": by_state[CLOSED],
        "counts": counts,
        "counts_open": {s: sum(1 for g in by_status(OPEN)
                               if g["severity"] == s) for s in SEVERITY_ORDER},
        "areas": areas,
        "absent_from_team_documents": len(GAPS),
        "note": (
            "Neither of the team's two feasibility documents raises any item "
            "on this list, and that is not a criticism of either: a document "
            "answers the question it set out to answer. These fall between "
            "them, which is why they are held here instead of in prose."
        ),
    }
