"""צוות אלחוט — מגן מרכבה: כל האנשים.

נבנה מהאקסל של כל הפול — רק מי שהדיסציפלינה שלו "אלחוט", מגיליונות התאים
(הגיליון "כל הפול - לא עדכני" לא נקרא). בלי טלפונים ובלי מספרים אישיים.

  cab          התא (לפי הגיליון שבו האדם מופיע)
  then_cab     אנשי ס' (סיבוב): עוברים לתא הזה אחרי הלילה הראשון
  service      מילואים / סדיר / אע"צ / הצ"ח (מעמודת "מקור"; חובה וקבע = סדיר)
  competency   כשירות (1 גבוה - 3 נמוך), None = לא ידוע
  level        רמה (1 גבוה - 3 נמוך), None = לא ידוע
  unavailable  חסום / לא יכול להגיע / לא בפול — הסיבה. None = זמין

כשירות ורמה שחסרו באקסל (התרעה, רוחב, חפיפות) נלקחו מגיליון האלחוטנים.
"""

P = dict

ROSTER = [
    # ---------- א' ----------
    P(name='אלי ראמשאני', cab="א'", then_cab=None, service='הצ"ח', competency=1, level=1, unavailable=None),
    P(name='דור עוז', cab="א'", then_cab=None, service='מילואים', competency=1, level=1, unavailable='המעיין לא מאשרים הסטה'),
    P(name='ליאת מילאנו', cab="א'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='לירון מנשה', cab="א'", then_cab=None, service='מילואים', competency=3, level=2, unavailable=None),
    P(name='ניקול קלימי', cab="א'", then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    # ---------- ס' ----------
    P(name='נעה כהן', cab="ס'", then_cab="א'", service='מילואים', competency=1, level=1, unavailable=None),
    # ---------- א' ----------
    P(name='סיני קלימי', cab="א'", then_cab=None, service='מילואים', competency=1, level=1, unavailable='הוסט לסופה לימים הקרובים'),
    P(name='עידו בבאי', cab="א'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='שירה ברזילי', cab="א'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='תומר אברהמי', cab="א'", then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='ציון קלימי', cab="א'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='בחו"ל, לבטל צו'),
    P(name='מאור חכימיאן', cab="א'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='לא יכול להיות מזומן למרכבה (צו בכחול)'),
    P(name='ישר פשאי', cab="א'", then_cab=None, service='הצ"ח', competency=3, level=1, unavailable=None),
    # ---------- ת' ----------
    P(name='איתי בבאי', cab="ת'", then_cab=None, service='מילואים', competency=2, level=1, unavailable='בחו"ל + משרד הביטחון'),
    P(name='גבי סיני', cab="ת'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='לירון אילי', cab="ת'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='מאור אגאי', cab="ת'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='מקסים דוסטרה', cab="ת'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='נועה אורן', cab="ת'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='עומר שירזי', cab="ת'", then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    # ---------- ס' ----------
    P(name='אליצפן ריינהיאן', cab="ס'", then_cab="ע'", service='מילואים', competency=1, level=1, unavailable='לא מגיע'),
    # ---------- ע' ----------
    P(name='אלי שמחי', cab="ע'", then_cab=None, service='מילואים', competency=1, level=None, unavailable=None),
    P(name='הילה חמדאדאש', cab="ע'", then_cab=None, service='מילואים', competency=3, level=None, unavailable=None),
    P(name='ליאורה איינהסזאן אהובים', cab="ע'", then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='רז פררה', cab="ע'", then_cab=None, service='הצ"ח', competency=1, level=2, unavailable='בקבע, כרגע לא לפנות'),
    P(name='שי בוזגלו', cab="ע'", then_cab=None, service='מילואים', competency=1, level=None, unavailable=None),
    # ---------- ס' ----------
    P(name='שר דלרהים', cab="ס'", then_cab="ע'", service='מילואים', competency=1, level=2, unavailable=None),
    # ---------- ע' ----------
    P(name='יוסף יחייב', cab="ע'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='אירוע אישי'),
    P(name='ניקאן מוטיעי', cab="ע'", then_cab=None, service='מילואים', competency=1, level=1, unavailable='לא יכול להגיע'),
    P(name='מעוז בר שמעון', cab="ע'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='במעיין, לא יאושר'),
    P(name='ליאל בן דוד', cab="ע'", then_cab=None, service='מילואים', competency=1, level=1, unavailable='לא מאושרת לזימון'),
    # ---------- ס' ----------
    P(name='אלישי בטסזאן', cab="ס'", then_cab="ד'", service='מילואים', competency=1, level=1, unavailable='לא מאושר - גדוד קדמי'),
    P(name='זוהר גולרוך', cab="ס'", then_cab="ד'", service='מילואים', competency=1, level=1, unavailable=None),
    # ---------- ד' ----------
    P(name='יניב ניקחו', cab="ד'", then_cab=None, service='מילואים', competency=2, level=2, unavailable='מוקפא למילואים'),
    P(name='ניר טבת', cab="ד'", then_cab=None, service='מילואים', competency=2, level=1, unavailable=None),
    P(name='פז בן דוד', cab="ד'", then_cab=None, service='מילואים', competency=2, level=1, unavailable=None),
    P(name='רפאל סעידיאן', cab="ד'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='מואיס אליאסיאן', cab="ד'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='פול כחול זירתי'),
    P(name='דנה סימאן', cab="ד'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='סיגמא - אין אישור לזמן'),
    # ---------- מ' ----------
    P(name='אופיר מרגלית', cab="מ'", then_cab=None, service='מילואים', competency=1, level=1, unavailable='לא לפנות כרגע'),
    P(name="דור קטיראג'י", cab="מ'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='דנה קראבסי', cab="מ'", then_cab=None, service='מילואים', competency=1, level=3, unavailable=None),
    P(name='ירין ארפנשאד', cab="מ'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='לירז סעידיאן', cab="מ'", then_cab=None, service='סדיר', competency=3, level=3, unavailable=None),
    P(name='נאזנין סעידיאן', cab="מ'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    # ---------- ס' ----------
    P(name='ספיר ניסני', cab="ס'", then_cab="מ'", service='מילואים', competency=1, level=2, unavailable=None),
    # ---------- מ' ----------
    P(name='עדן מודילבסקי', cab="מ'", then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    P(name='שני יחזקליאן', cab="מ'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='הריון'),
    # ---------- ח' ----------
    P(name='אור-חן דגן', cab="ח'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name="אוראל ג'רהיאן", cab="ח'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='טופז פרי', cab="ח'", then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='נועה זהר', cab="ח'", then_cab=None, service='הצ"ח', competency=1, level=1, unavailable=None),
    P(name='נעם בלס', cab="ח'", then_cab=None, service='מילואים', competency=2, level=1, unavailable=None),
    P(name='עידן מלכאן', cab="ח'", then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    P(name='קרן ארפנשאד', cab="ח'", then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='נוי בבאי', cab="ח'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='הריון'),
    # ---------- ר' ----------
    P(name='אדיר סמהי', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='אורון דאודזאדה', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='רוי סולימני', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='יהונתן ראוף', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='מאיה גלעוז', cab="ר'", then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    P(name='ספיר ארמניאן', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='שירן פירוזיאן', cab="ר'", then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='רועי מררי', cab="ר'", then_cab=None, service='מילואים', competency=None, level=None, unavailable='אין אישור סיגמא לזימון'),
    # ---------- מרחקים ----------
    P(name='אוראל שקני', cab='מרחקים', then_cab=None, service='מילואים', competency=1, level=2, unavailable='מרוחקים - אלחוט לא מגיעים'),
    P(name='איתי חקשור', cab='מרחקים', then_cab=None, service='מילואים', competency=3, level=None, unavailable='מרוחקים - אלחוט לא מגיעים'),
    P(name='נתנאל יומטוביאן', cab='מרחקים', then_cab=None, service='מילואים', competency=3, level=None, unavailable='מרוחקים - אלחוט לא מגיעים'),
    P(name='מואיס סולימאן', cab='מרחקים', then_cab=None, service='מילואים', competency=None, level=None, unavailable='מרוחקים - אלחוט לא מגיעים'),
    # ---------- רוחב ----------
    P(name='אודליה ענייתי', cab='רוחב', then_cab=None, service='מילואים', competency=1, level=3, unavailable=None),
    P(name='אור אדיבי', cab='רוחב', then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='דורית פרח', cab='רוחב', then_cab=None, service='מילואים', competency=1, level=3, unavailable=None),
    P(name='לינוי חבין', cab='רוחב', then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    P(name='קורל יומטוביאן', cab='רוחב', then_cab=None, service='מילואים', competency=1, level=3, unavailable=None),
    # ---------- התרעה ----------
    P(name='אהרון ישייהי', cab='התרעה', then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    P(name='הילה אברהם פור', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='מאור כהן', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='משה כהן', cab='התרעה', then_cab=None, service='אע"צ', competency=1, level=2, unavailable=None),
    P(name='עדן קשני', cab='התרעה', then_cab=None, service='סדיר', competency=1, level=1, unavailable=None),
    P(name='עומר רז', cab='התרעה', then_cab=None, service='הצ"ח', competency=1, level=1, unavailable=None),
    P(name='רפאל אחוואן', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='שיראל יחזקליאן', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='ליאור מכובד', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=1, unavailable=None),
    P(name='שיראל קשני', cab='התרעה', then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
    # ---------- חפיפות ----------
    P(name='טליה מויאל', cab='חפיפות', then_cab=None, service='מילואים', competency=1, level=2, unavailable=None),
]
