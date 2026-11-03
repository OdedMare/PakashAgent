"""צוות אלחוט — מגן מרכבה: כל האנשים, עם ההערות.

מקורות:
  * גיליון "אלחוטנים" (רשימת האנשים: מקור, שיבוץ, כשירות, רמה, הערות של יובל)
  * לוח המשמרות (באיזה תא כל אחד יושב בפועל, מי לא בפול, מי באי-זמינות ארוכה)

כשהגיליון והלוח לא מסכימים על התא — הלוח קובע (cab), והשיבוץ מהגיליון נשמר
ב-sheet_assignment לבדיקה.

כשירות / רמה: 1 = גבוה, 3 = נמוך. None = "לא ידוע".
מספרים אישיים לא נשמרים כאן בכוונה — השיבוץ לא צריך אותם.

then_cab: אנשי הסיבוב (ס') עוברים לתא הזה אחרי הלילה הראשון.

flags — אילוצים שחולצו מההערות (ההערה המקורית תמיד ב-note):
  first_72h_only   זמין רק ב-72 השעות הראשונות
  emergency_only   מגיע רק בחירום מלא (משובץ רק עם --full-emergency)
  fri_sat_only     יכול רק שישי-שבת
  blocked          חסום ע"י יחידת המקור / כרגע במקום אחר
  unavailable      לא זמין (הריון, אירוע אישי, אי זמינות ארוכה)
  not_in_pool      "לא בפול" בלוח
  under_review     "מעיין" בלוח — עוד לא בפנים
  refuser          סרבנית
  uncertain        לא בטוח שיגיע (משובץ, אבל מסומן)
  not_certified    לא מוסמך/ת עדיין — רק עם בכיר באותה משמרת
  unknown_person   יובל לא מכיר — רק עם בכיר באותה משמרת
  rear_cab_only    מוסמכת רק לתא אחורי
  in_handover      בחפיפות
  no_nights        לא משבצים בלילה (אמא / אבא טרי)
  conditional      מגיע בתנאי (למשל לא בזמן לימודים)
  sensitive        דורש התייחסות מצד המפקד
  verify           הקריאה מהתמונה לא ודאית — לבדוק מול המקור
"""

P = dict  # קיצור

ROSTER = [
    # ---------- א' ----------
    P(name="אלי ראמשאני", cab="א'", service='הצ"ח', source="NLS", sheet_assignment="א'", competency=1, level=1, note='אע"צ NLS; בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="ליאת מילאנו", cab="א'", service="מילואים", source="110", sheet_assignment="א'", competency=1, level=1, note="", flags=[]),
    P(name="תומר אברהמי", cab="א'", service="מילואים", source="110", sheet_assignment="א'", competency=1, level=2, note="אשתו ילדה לאחרונה", flags=["no_nights"]),
    P(name="עידו בבאי", cab="א'", service="מילואים", source="גבעה", sheet_assignment="א'", competency=1, level=1, note="חסום גבעה", flags=["blocked"]),
    P(name="ניקול קלימי", cab="א'", service="קבע", source="110", sheet_assignment="א'", competency=1, level=1, note='כורדית; בגיליון הדיסציפלינה "כחול", בלוח יושבת בא\'', flags=["verify"]),
    P(name="שירה ברזילי", cab="א'", service="מילואים", source="110", sheet_assignment="א'", competency=1, level=1, note="", flags=[]),
    P(name="סיני קלימי", cab="א'", service="מילואים", source="גבעה", sheet_assignment="א'", competency=1, level=1, note="כורדית; חסום בגבעה", flags=["blocked"]),
    P(name="לירון מנשה", cab="א'", service="מילואים", source="110", sheet_assignment="א'", competency=3, level=2, note="", flags=[]),
    P(name="ציון קלימי", cab="א'", service="", source="", sheet_assignment="", competency=None, level=None, note="אי זמינות ארוכה (מהלוח)", flags=["unavailable", "verify"]),
    P(name="דור עוז", cab="א'", service="", source="", sheet_assignment="", competency=None, level=None, note="מעיין (מהלוח)", flags=["under_review", "verify"]),
    P(name="מאור חכימיאן", cab="א'", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול — יש לו צו בכחול", flags=["not_in_pool", "verify"]),
    P(name="ישר פשאי", cab="א'", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול — מבצעים", flags=["not_in_pool", "verify"]),

    # ---------- ת' ----------
    P(name="עומר שירזי", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=2, note="מוכן להגיע רק בחירום מלא", flags=["emergency_only"]),
    P(name="מקסים דוסטרה", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=1, note="", flags=[]),
    P(name="לירון אילי", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=1, note="", flags=[]),
    P(name="איתי בבאי", cab="ת'", service="מילואים", source='שב"כ', sheet_assignment="ת'", competency=2, level=1, note='חסום שב"כ, יכול בעיקר שישי שבת', flags=["blocked", "fri_sat_only"]),
    P(name="גבי סיני", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=1, note="", flags=[]),
    P(name="נעה אורן", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=1, note="", flags=[]),
    P(name="מאור אגאי", cab="ת'", service="מילואים", source="110", sheet_assignment="ת'", competency=1, level=1, note="", flags=[]),

    # ---------- ד' ----------
    P(name="רפאל סעידיאן", cab="ד'", service="מילואים", source="110", sheet_assignment="ד'", competency=1, level=1, note="", flags=[]),
    P(name="פז בן דוד", cab="ד'", service="מילואים", source="110", sheet_assignment="ד'", competency=1, level=1, note="", flags=[]),
    P(name="ניר טבת", cab="ד'", service="מילואים", source="110", sheet_assignment="ד'", competency=1, level=1, note="", flags=[]),
    P(name="יניב ניקחו", cab="ד'", service="מילואים", source="סיגמא", sheet_assignment="ד'", competency=1, level=2, note="", flags=[]),
    P(name="אמיל אברהם", cab="ד'", service="", source="", sheet_assignment="", competency=None, level=None, note='בשורת "אלחוטן אד"רית" בלוח, השם באפור — לא בגיליון', flags=["unknown_person", "verify"]),
    P(name="דנה סימאן", cab="ד'", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול (מהלוח)", flags=["not_in_pool", "verify"]),
    P(name="מואיס אליאסיאן", cab="ד'", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול (מהלוח)", flags=["not_in_pool", "verify"]),

    # ---------- ע' ----------
    P(name="רז פרדה", cab="ע'", service='הצ"ח', source="110", sheet_assignment="ע'", competency=2, level=2, note='בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="ליאורה איינהסזאן אהובים", cab="ע'", service="מילואים", source="NLS", sheet_assignment="ע'", competency=1, level=2, note="", flags=["verify"]),
    P(name="הילה חמדאדאש", cab="ע'", service="מילואים", source="110", sheet_assignment="ע'", competency=3, level=None, note="לא מכיר", flags=["unknown_person"]),
    P(name="שי בזוגלו", cab="ע'", service="מילואים", source="110", sheet_assignment="ע'", competency=3, level=None, note="לא מכיר", flags=["unknown_person"]),
    P(name="אלי שמחי", cab="ע'", service="מילואים", source="110", sheet_assignment="מ'", competency=3, level=None, note="לא מכיר; מנסים עכשיו להביא אותו לחפיפות (בלוח באפור)", flags=["unknown_person", "in_handover"]),
    P(name="יוסף יחייב", cab="ע'", service="", source="", sheet_assignment="", competency=None, level=None, note="אי זמינות ארוכה (מהלוח)", flags=["unavailable", "verify"]),
    P(name="מעוז בר שמעון", cab="ע'", service="", source="", sheet_assignment="", competency=None, level=None, note="מעיין (מהלוח)", flags=["under_review", "verify"]),
    P(name="ניקאן מוטיעי", cab="ע'", service="מילואים", source="110", sheet_assignment="ע'", competency=1, level=1, note='כרגע תחת אמ"צ; לא בפול', flags=["not_in_pool"]),

    # ---------- מ' ----------
    P(name="עדן מודילבסקי", cab="מ'", service="חובה", source="110", sheet_assignment="מ'", competency=1, level=1, note='בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="נאזנין סעידיאן", cab="מ'", service="מילואים", source="110", sheet_assignment="מ'", competency=2, level=1, note="סרבנית", flags=["refuser"]),
    P(name="לירן סעידיאן", cab="מ'", service="חובה", source="110", sheet_assignment="התרעה", competency=1, level=3, note="לא מוסמכת עדיין", flags=["not_certified"]),
    P(name="ירין ארפנשאד", cab="מ'", service="מילואים", source="110", sheet_assignment="ח'", competency=1, level=1, note="", flags=[]),
    P(name="אופיר מרגלית", cab="מ'", service="מילואים", source="110", sheet_assignment="מ'", competency=2, level=1, note="", flags=[]),
    P(name="דור קטיראג'י", cab="מ'", service="מילואים", source="110", sheet_assignment="מ'", competency=1, level=1, note="", flags=["verify"]),
    P(name="דנה קרבנסקי", cab="מ'", service="מילואים", source="סיגמא", sheet_assignment="מ'", competency=2, level=3, note="בבחינה", flags=[]),
    P(name="שני יחזקליאן", cab="מ'", service="", source="", sheet_assignment="", competency=None, level=None, note="מעיין (מהלוח)", flags=["under_review", "verify"]),

    # ---------- ח' ----------
    P(name="עידן מלכאן", cab="ח'", service="חובה", source="110", sheet_assignment="ר'", competency=1, level=1, note='בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="נעה זהר", cab="ח'", service='הצ"ח', source="110", sheet_assignment="ח'", competency=1, level=1, note="", flags=[]),
    P(name="קרן ארפנשאד", cab="ח'", service="מילואים", source="סיגמא", sheet_assignment="ח'", competency=1, level=2, note="בהריון מתקדם", flags=["unavailable"]),
    P(name="טופז פרי", cab="ח'", service="מילואים", source="110", sheet_assignment="מ'", competency=1, level=2, note="", flags=[]),
    P(name="נעם בלס", cab="ח'", service="מילואים", source="110", sheet_assignment="ח'", competency=2, level=1, note="לא בטוח שתגיע למלחמה הבאה, עובדת NLS", flags=["uncertain"]),
    P(name="אוראל ג'והיאן", cab="ח'", service="מילואים", source="110", sheet_assignment="ח'", competency=1, level=1, note="", flags=["verify"]),
    P(name="אור-חן דגן", cab="ח'", service="מילואים", source="110", sheet_assignment="ח'", competency=1, level=1, note="", flags=[]),
    P(name="נוי בבאי", cab="ח'", service="", source="", sheet_assignment="", competency=None, level=None, note="אי זמינות ארוכה (מהלוח)", flags=["unavailable", "verify"]),

    # ---------- ר' ----------
    P(name="מאיה גלעד", cab="ר'", service='הצ"ח', source="110", sheet_assignment="ר'", competency=1, level=1, note='בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="יהונתן ראוף", cab="ר'", service="מילואים", source="סיגמא", sheet_assignment="ר'", competency=1, level=1, note="", flags=[]),
    P(name="אורן דודזאדה", cab="ר'", service="מילואים", source="110", sheet_assignment="ר'", competency=1, level=1, note="", flags=[]),
    P(name="רוי סולימני", cab="ר'", service="מילואים", source="110", sheet_assignment="ר'", competency=1, level=1, note="", flags=[]),
    P(name="אדיר סמהי", cab="ר'", service="מילואים", source="110", sheet_assignment="ר'", competency=1, level=1, note="אם יש לימודים הוא לא מגיע", flags=["conditional"]),
    P(name="ספיר אמרניאן", cab="ר'", service="מילואים", source="110", sheet_assignment="ר'", competency=1, level=1, note="אין מספר אישי בגיליון", flags=["verify"]),
    P(name="שירן פירחזיאן", cab="ר'", service="מילואים", source="110", sheet_assignment="ר'", competency=1, level=1, note="", flags=["verify"]),
    P(name="רועי מרדי", cab="ר'", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול (מהלוח)", flags=["not_in_pool", "verify"]),

    # ---------- מרחקים ----------
    P(name="אוראל שקני", cab="מרחקים", service="מילואים", source="110", sheet_assignment="מרחקים", competency=1, level=2, note="", flags=[]),
    P(name="איתי חקשור", cab="מרחקים", service="מילואים", source="110", sheet_assignment="מרחקים", competency=3, level=None, note="לפעמים עושה קצת צרות", flags=["sensitive", "unknown_person"]),
    P(name="נתנאל יומטוביאן", cab="מרחקים", service="מילואים", source="110", sheet_assignment="מרחקים", competency=3, level=None, note="לא מכיר", flags=["unknown_person"]),
    P(name="מואיס סולימאן", cab="מרחקים", service="", source="", sheet_assignment="", competency=None, level=None, note="לא בפול (מהלוח)", flags=["not_in_pool", "verify"]),

    # ---------- ס' (סיבוב) — לילה ראשון, ואז עוברים ----------
    P(name="זוהר גולרוך", cab="ס'", then_cab="ד'", service="מילואים", source="110", sheet_assignment="ס'", competency=1, level=1, note="דורש יחס מיוחד; בלוח: ס' ואז ד'", flags=["sensitive"]),
    P(name="אליצפן ריינהיאן", cab="ס'", then_cab="ע'", service="מילואים", source="סיגמא", sheet_assignment="ס'", competency=1, level=1, note="בלוח: ס' ואז ע'", flags=["verify"]),
    P(name="אלישי בטסאן", cab="ס'", then_cab="ד'", service="מילואים", source="גדוד קדמי", sheet_assignment="ס'", competency=1, level=1, note="בלוח: ס' ואז ד'", flags=["verify"]),
    P(name="ספיר ניסני", cab="ס'", then_cab="מ'", service="מילואים", source="110", sheet_assignment="ס' ואז מ'", competency=1, level=2, note="", flags=[]),
    P(name="נעה כהן", cab="ס'", then_cab="א'", service="מילואים", source="170", sheet_assignment="ס' ואז א'", competency=1, level=1, note="", flags=[]),
    P(name="שר דלהים", cab="ס'", then_cab="ע'", service="מילואים", source="110", sheet_assignment="ס' ואז ע'", competency=1, level=2, note='ברה"ן', flags=["sensitive", "verify"]),

    # ---------- רוחב ----------
    P(name="קורל יומטוביאן", cab="רוחב", service="מילואים", source="110", sheet_assignment="רוחב", competency=1, level=3, note="מוסמכת רק תא אחורי", flags=["rear_cab_only"]),
    P(name="דורית פררו", cab="רוחב", service="מילואים", source="110", sheet_assignment="רוחב", competency=1, level=3, note="מוסמכת רק תא אחורי", flags=["rear_cab_only"]),
    P(name="לימי רובין", cab="רוחב", service="מילואים", source="110", sheet_assignment="רוחב", competency=1, level=2, note="חדשה ואמא אז לא יכולה לעשות משמרות א... (חתוך בתמונה)", flags=["no_nights", "verify"]),
    P(name="אור אדיבי", cab="רוחב", service="מילואים", source="110", sheet_assignment="רוחב", competency=1, level=2, note="אמא", flags=["no_nights"]),

    # ---------- התרעה ----------
    P(name="עומר רז", cab="התרעה", service='הצ"ח', source="110", sheet_assignment="התרעה", competency=1, level=1, note='בשורת סדיר/הצ"ח בלוח', flags=[]),
    P(name="ליאור מכובד", cab="התרעה", service="מילואים", source="110", sheet_assignment="מ'", competency=1, level=1, note="", flags=[]),
    P(name="משה כהן", cab="התרעה", service='אע"צ', source="110", sheet_assignment="התרעה", competency=1, level=2, note="רק 72 שעות ראשונות", flags=["first_72h_only"]),
    P(name="מאור כהן", cab="התרעה", service="מילואים", source="110", sheet_assignment="התרעה", competency=1, level=1, note="", flags=[]),
    P(name="הילה אברהם פור", cab="התרעה", service="מילואים", source="110", sheet_assignment="התרעה", competency=1, level=1, note="אירוע אישי", flags=["unavailable"]),
    P(name="עדן קשני", cab="התרעה", service="קבע", source="110", sheet_assignment="התרעה", competency=1, level=1, note="רק 72 שעות ראשונות; אין מספר אישי בגיליון", flags=["first_72h_only"]),
    P(name="אהרון ישעיהו", cab="התרעה", service="קבע", source="110", sheet_assignment="התרעה", competency=1, level=1, note="רק 72 שעות ראשונות", flags=["first_72h_only"]),
    P(name="רפאל אחוואן", cab="התרעה", service="מילואים", source="110", sheet_assignment="התרעה", competency=1, level=1, note="", flags=[]),
    P(name="שיראל יחזקליאן", cab="התרעה", service="מילואים", source="110", sheet_assignment="התרעה", competency=1, level=1, note="", flags=[]),
    P(name="שיראל קשני", cab="התרעה", service="מילואים", source="110", sheet_assignment="התרעה", competency=1, level=2, note="", flags=[]),

    # ---------- חפיפות ----------
    P(name="אודליה עניתי", cab="חפיפות", service="מילואים", source="110", sheet_assignment="רוחב", competency=1, level=3, note="מוסמכת רק תא אחורי; חפיפות", flags=["rear_cab_only", "in_handover"]),
    P(name="טליה מויאל", cab="חפיפות", service="מילואים", source="110", sheet_assignment="חפיפות", competency=1, level=2, note="חפיפות", flags=["in_handover"]),
    P(name="שני שרייבר", cab="חפיפות", service="", source="", sheet_assignment="", competency=None, level=None, note="מופיעה רק בלוח, לא בגיליון", flags=["in_handover", "verify"]),

    # ---------- לא בלוח ----------
    P(name="דולב אושר אליאס", cab=None, service="חובה", source="110", sheet_assignment="מפקדת שמע", competency=1, level=1, note="מפקדת שמע; לא מסומן שובץ ולא מופיע בלוח", flags=["not_in_pool"]),
    # משמרת כחול לא נכללת לפי בקשה: אוריאל יעקובי, מלודי כהן
]

# מי לא נכנס לשיבוץ בכלל (עד שמשהו משתנה)
EXCLUDE_FLAGS = {"blocked", "unavailable", "not_in_pool", "under_review", "refuser"}
# מי צריך בכיר (רמה 1-2, מוכר) לצידו באותה משמרת ובאותו תא
NEEDS_SENIOR_FLAGS = {"not_certified", "unknown_person"}


def is_senior(p: dict) -> bool:
    return p["level"] in (1, 2) and not (set(p["flags"]) & NEEDS_SENIOR_FLAGS)


def needs_senior(p: dict) -> bool:
    return bool(set(p["flags"]) & NEEDS_SENIOR_FLAGS) or p["level"] == 3


for _p in ROSTER:
    _p.setdefault("then_cab", None)
