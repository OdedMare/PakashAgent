/** What the in-app guide says, per surface.
 *
 *  Kept apart from the components so the copy can be read and corrected in
 *  one place. Every sentence here describes behaviour that already exists —
 *  the guide teaches the product, it does not promise one. If a button is
 *  renamed, the tour step naming it is the second place to change.
 *
 *  Steps point at `data-tour` attributes on real elements rather than at
 *  class names, so restyling a screen cannot silently detach the tour. */

export type Surface = "setup" | "manager" | "employee" | "member";

export interface TourStep {
  /** The `data-tour` value of the element to spotlight. */
  target: string;
  title: string;
  body: string;
  /** Skipped when the element is not on screen — a coverage bar only exists
   *  once there is a week, a change alert only once something changed. A
   *  required step whose target is missing renders centred instead. */
  optional?: boolean;
  /** A named action the surface registered, run before the step is shown —
   *  opening the drawer the step is about. Navigation only: no action a
   *  surface registers may write anything. */
  prepare?: string;
}

export const TOURS: Partial<Record<Surface, TourStep[]>> = {
  setup: [
    {
      target: "setup-workplace",
      title: "מתחילים בתמונה הכללית",
      body: "כתבו את שם היחידה, בחרו את אורך הסידור ואת ימי הפעילות. בתיאור היציאות הכללי מוסיפים רק מידע שמשותף לכל הצוות; את המבנה האישי מגדירים בהמשך לכל אדם.",
    },
    {
      target: "setup-rotations",
      title: "מגדירים סבב רק אם צריך",
      body: "אם הצוות עובד בסבבים או בתלתונים, בוחרים את המבנה ומגדירים את העוגן והשעות של קבוצה א׳. המערכת מחשבת ממנו את שאר הקבוצות. למחזור ימים כמו 11/3, 12/2 או שבוע־שבוע מוסיפים מחזור ימים, ומגדירים ימים בבסיס ובבית, עוגן ושעות יציאה וחזרה. אם אין אצלכם מבנה כזה, אפשר להשאיר את האפשרויות הנוספות כבויות.",
    },
    {
      target: "setup-people",
      title: "מוסיפים את אנשי הצוות",
      body: "לכל אדם ממלאים שם ותפקיד, מבנה יציאות וקבוצה. כאן גם מסמנים מי מפקד/ת משמרת, מי יכול/ה לחפוף ולאילו משמרות האדם מתאים.",
    },
    {
      target: "setup-shifts",
      title: "מתארים כל סוג משמרת",
      body: "הוסיפו שם, שעות ותקן נדרש לכל משמרת. הימים, התפקידים המוסמכים והצורך במפקד/ת משמרת אומרים למערכת את מי מותר לשבץ ואיפה.",
    },
    {
      target: "setup-rules",
      title: "מוסיפים רק כללים קבועים",
      body: "כלל קשיח הוא דרישה חזקה וכלל רך הוא העדפה. כתבו כאן כללים שחוזרים בכל סידור; אילוץ חד־פעמי לתאריך מסוים מוסיפים אחר כך באזור הניהול.",
    },
    {
      target: "setup-limits",
      title: "קובעים גבולות לבדיקה",
      body: "מקסימום שעות וימים רצופים ומינימום מנוחה עוזרים למערכת להתריע על עומס. הם מציפים חריגות לבדיקה ואינם חוסמים החלטה שלכם.",
    },
    {
      target: "setup-save",
      title: "שומרים ועוברים ללוח",
      body: "כדי להמשיך צריך שם יחידה, לפחות איש צוות אחד ולפחות סוג משמרת אחד. השמירה יוצרת את פרופיל היחידה; תמיד אפשר לחזור ולעדכן אותו מאזור הניהול.",
    },
    {
      target: "help",
      title: "אפשר לחזור להסבר בכל רגע",
      body: "כפתור ‘עזרה’ מחזיר לסיור הזה, למילון המונחים ולמדריך המלא. אפשר גם ללחוץ ? כשלא מקלידים בשדה.",
    },
  ],
  manager: [
    {
      target: "nav",
      title: "ארבעה מסכים, מקום אחד",
      body: "‘לוח המשמרות’ הוא מרכז העבודה. ‘כוח אדם’ מרכז עובדים, משמרות ואילוצים, ו‘סקירה’ מציגה את המספרים שמאחורי הסידור. ‘סוכן הסידור’ נפתח לצד הלוח, כך שלא מאבדים את ההקשר; מתחת — ‘שיחה חדשה’ והשיחות הקודמות, עם חיפוש.",
      prepare: "board",
    },
    {
      target: "week-nav",
      title: "תצוגה וניווט בלוח",
      body: "בוחרים כמה רואים: יום, שבוע, שבועיים או חודש. ביום ובשבוע משבצים ועורכים; שבועיים וחודש הם מבט־על — לחיצה על יום פותחת אותו, ולחיצה על שבוע פותחת את הלוח שלו. החצים זזים לפי התצוגה. במקלדת: ← קדימה, → אחורה, ו‑T (או א) חוזר להיום.",
      prepare: "board",
    },
    {
      target: "board-actions",
      title: "טיוטה, קובץ ופרסום",
      body: "התג מראה אם השבוע עוד טיוטה או כבר פורסם. ‘פרסום לצוות’ הוא הרגע שבו העובדים רואים את הגרסה, ואזהרות אינן חוסמות אותו. ‘אקסל’ מוריד קובץ בלי לשנות דבר. ‘ניקוי השבוע’ מרוקן את השיבוצים ומשאיר את השורות; ‘מחיקת הסידור’ מחזירה את השבוע למצב שלפני בנייה.",
      optional: true,
    },
    {
      target: "empty-week",
      title: "שתי דרכים להתחיל שבוע",
      body: "‘בניית הסידור’ פותחת חלון בנייה: מתאריך עד תאריך, אילו סוגי משמרות, והנחיות לתקופה. הבנייה רצה ברקע והלוח נשאר פתוח לשיבוץ ידני. ‘שבוע ריק’ משאיר את השיבוץ בידיים שלכם.",
      optional: true,
    },
    {
      target: "coverage",
      title: "מצב השבוע במבט אחד",
      body: "איוש, משמרות פתוחות, התנגשויות ושעות. לחיצה על ‘משמרות פתוחות’ או ‘התנגשויות’ מסננת את הלוח בדיוק למקומות האלה.",
      optional: true,
    },
    {
      target: "filters",
      title: "סינון הלוח",
      body: "מציגים רק עובד, תפקיד או משמרת מסוימים. הסינון משנה רק את התצוגה, לא את הסידור.",
      optional: true,
    },
    {
      target: "grid",
      title: "שיבוץ ישיר על הלוח",
      body: "+ בתא ריק משבץ מיד. גרירה של שיבוץ קיים היא הצעה: המערכת בודקת את ההשפעה ומבקשת סיבה לפני שהשינוי נשמר. בראש כל עמודה: של מי הסגירה, ‘סוכן ליום’, ‘בנייה מכאן’ ו‘נקה יום’. את סדר השורות אפשר לגרור — זה משנה רק את התצוגה.",
      optional: true,
    },
    {
      target: "agent-composer",
      title: "לדבר עם הסוכן",
      body: "כתבו שאלה או בקשה במילים שלכם. שאלה מקבלת תשובה ולא משנה דבר. בקשה לשינוי חוזרת כתוכנית עם הנימוק והאזהרות — ושום דבר לא נשמר עד ‘החלת התוכנית’. את המפריד בין השיחה ללוח אפשר לגרור; לחיצה כפולה מאפסת.",
      prepare: "agent",
      optional: true,
    },
    {
      target: "drawer-tabs",
      title: "כלי הניהול",
      body: "המגירה מרכזת עבודה שוטפת: ‘סוכן’, ‘שינויים’ (החלפת משמרת, הוספת חייל והוספת משמרת — הסידור הקיים נשמר ככל האפשר), ‘בקשות’ של עובדים והחלפות, ו‘צוות’ עם ההעדפות שהסוכן זוכר. ה־X בקצה סוגר את הסוכן והלוח מתרחב.",
      prepare: "agent",
      optional: true,
    },
    {
      target: "header-actions",
      title: "הגדרות היחידה",
      body: "אייקון המחוונים פותח את הגדרת היחידה, ושם מגדירים עובדים, משמרות, סבבים ותלתונים: לכל סבב, תלתון ורבעון (שבת אחת מכל ארבע) עונים על שלוש שאלות — מתי קבוצה א׳ סוגרת, איזה סוג סבב (11/3, 12/2, 10/4, שבוע־שבוע או ימים ושעות אחרים) ואילו סופ״שים חריגים — ורואים את הסופ״שים הקרובים עוד לפני השמירה. מחזורי ימים מוגדרים בנפרד, בימים בבסיס ובבית. חייל או משמרת שנוספו משתלבים בטיוטות מהיום והלאה. אייקון השיתוף מציג את קישור הצפייה לצוות והירח מחליף למצב כהה. הגדרות המערכת (מודל ופותר) מנוהלות על ידי צוות משמרות זהב. מתפריט החשבון בקצה הסרגל מתנתקים.",
    },
    {
      target: "help",
      title: "העזרה תמיד כאן",
      body: "מכאן חוזרים לסיור, לרשימת הצעדים הראשונים, לקיצורי המקלדת ולמילון המונחים. אפשר גם ללחוץ ? מכל מקום.",
    },
  ],
  employee: [
    {
      target: "change-alert",
      title: "מה השתנה מאז הביקור הקודם",
      body: "כשמשמרת שלכם זזה, ההודעה מופיעה כאן עם הסיבה. ‘ראיתי’ מסמן שקראתם — זה לא אישור ולא הסכמה.",
      optional: true,
    },
    {
      target: "employee-tabs",
      title: "האזור האישי שלכם",
      body: "‘המשמרות שלי’ — מתי ועם מי, ומתחת השינויים שנגעו לכם. ‘הלוח המלא’ — הסידור שפורסם, לקריאה בלבד.",
    },
    {
      target: "employee-requests-tab",
      title: "בקשות והחלפות",
      body: "שלחו אילוץ (תאריך, משמרת או כל היום, וסיבה) או הציעו החלפה לעמית. בקשה נשארת ‘ממתינה’ ואינה משנה דבר עד שהמנהל מחליט, ואפשר לבטל אותה עד אז; החלפה דורשת גם את הסכמת העמית.",
    },
    {
      target: "help",
      title: "העזרה תמיד כאן",
      body: "מכאן חוזרים לסיור ולמילון המונחים. אפשר גם ללחוץ ? מכל מקום.",
    },
  ],
  member: [
    {
      target: "member-schedule",
      title: "הסידור שפורסם",
      body: "זו הגרסה שהמנהל פרסם לצוות, לקריאה בלבד. אין כאן גרירה, מחיקה או אישור.",
      optional: true,
    },
    {
      target: "member-personal",
      title: "האזור האישי",
      body: "בחרו את השם שלכם והגדירו קוד אישי כדי לראות את המשמרות והשעות שלכם ולשלוח בקשות. אחרי זה אפשר להיכנס ישירות מ‘עובד/ת’ במסך הכניסה.",
    },
    {
      target: "help",
      title: "העזרה תמיד כאן",
      body: "מכאן חוזרים לסיור ולמילון המונחים. אפשר גם ללחוץ ? מכל מקום.",
    },
  ],
};

/** Who a glossary entry is for. A manager sees every entry; an employee
 *  sees the words their own screens use. */
type Audience = "manager" | "team";

export interface GlossaryEntry {
  term: string;
  definition: string;
  audience: Audience[];
}

export const GLOSSARY: GlossaryEntry[] = [
  {
    term: "טיוטה",
    definition: "סידור שעוד בעבודה. הצוות לא רואה אותו, ואפשר לשבץ, להזיז ולנקות בו.",
    audience: ["manager"],
  },
  {
    term: "פרסום",
    definition: "הרגע שבו הצוות רואה את הגרסה הנוכחית. סידור מפורסם נעול לעריכה; ‘החזרה לטיוטה’ פותחת אותו שוב.",
    audience: ["manager", "team"],
  },
  {
    term: "אזהרה",
    definition: "ממצא של הבדיקה האוטומטית: שעות, משמרות רצופות, שיבוץ כפול, התנגשות עם אילוץ או משמרת חסרה. אזהרה מיידעת ולעולם אינה חוסמת שמירה או פרסום.",
    audience: ["manager", "team"],
  },
  {
    term: "התנגשות",
    definition: "אזהרה ממשית (להבדיל מהערה). האריח ‘התנגשויות’ בראש הלוח סופר אותן, ולחיצה עליו מסננת את הלוח אליהן.",
    audience: ["manager"],
  },
  {
    term: "משמרת פתוחה",
    definition: "מקום במשמרת שעוד לא שובץ אליו אף אחד.",
    audience: ["manager"],
  },
  {
    term: "כלל קשיח / רך",
    definition: "כלל קשיח הוא הוראה חזקה לסוכן ומלווה באזהרה בולטת כשהוא מופר. כלל רך הוא יעד שהסוכן משתדל להשיג. גם כלל קשיח אינו חוסם — ההחלטה נשארת שלכם.",
    audience: ["manager"],
  },
  {
    term: "תוכנית",
    definition: "שינוי שהסוכן הכין ומחכה לכם: השינויים, הנימוק והאזהרות הצפויות. שום דבר לא נשמר עד ‘החלת התוכנית’.",
    audience: ["manager"],
  },
  {
    term: "שאלה לסוכן",
    definition: "מחזירה תשובה בלבד, בלי כפתור אישור — כי דבר לא השתנה.",
    audience: ["manager"],
  },
  {
    term: "סיבה",
    definition: "הזזה של מי שכבר שובץ, למשל בגרירה, מבקשת סיבה שנשמרת ביומן השינויים. בשיחה עם הסוכן, הבקשה שכתבתם נרשמת כסיבה.",
    audience: ["manager"],
  },
  {
    term: "יומן שינויים",
    definition: "רשימה שרק מתווספים אליה: מה השתנה, מתי ולמה. ממנה העובדים מקבלים ‘שינויים שנגעו לי’, וממנה נגזרות ההצעות שב‘מה שחוזר על עצמו’.",
    audience: ["manager"],
  },
  {
    term: "אילוץ",
    definition: "מתי מישהו לא יכול או מעדיף שלא לעבוד. כל אילוץ מסומן במקור שלו: מנהל, סוכן, דיווח של העובד או הגדרה קודמת.",
    audience: ["manager", "team"],
  },
  {
    term: "תורנות חוסמת",
    definition: "טווח שעות שבו החייל/ת כבר בתפקיד אחר, כמו שמירה, מטבח או חמ״ל. אי אפשר לשבץ משמרת שחופפת לתורנות, גם כשהיא חוצה חצות.",
    audience: ["manager", "team"],
  },
  {
    term: "בקשת אילוץ",
    definition: "אילוץ שעובד/ת שלח/ה. היא ‘ממתינה’ ואינה משנה דבר עד שהמנהל מאשר; דחייה מגיעה עם סיבה. אפשר למשוך בקשה שעוד ממתינה.",
    audience: ["manager", "team"],
  },
  {
    term: "החלפה",
    definition: "הצעה להתחלף במשמרת עם עמית. הסידור משתנה רק אחרי שהעמית מסכים והמנהל מאשר.",
    audience: ["manager", "team"],
  },
  {
    term: "העדפה",
    definition: "הקשר שהסוכן זוכר בניסוח שלכם, כמו ‘מאיה מעדיפה בקרים’. העדפה שהסוכן הציע אינה פעילה עד שתאשרו, וכולן גלויות וניתנות לעריכה, השבתה ומחיקה בלשונית ‘צוות’ שבמגירת הסוכן.",
    audience: ["manager"],
  },
  {
    term: "סבב יציאות",
    definition: "דפוס היציאות של אדם — סבב, תלתון, חמשושים או שושים — והקבוצה שלו בתוכו. מכאן מחושב של מי הסגירה בכל יום.",
    audience: ["manager", "team"],
  },
  {
    term: "סגירה / חילוף",
    definition: "ראש עמודת היום מציין איזו קבוצה בסגירה. ביום חילוף הקבוצה נמצאת בבוקר ויוצאת בהמשך היום.",
    audience: ["manager", "team"],
  },
  {
    term: "נחפף/ת",
    definition: "מי שנמצא/ת בתקופת חפיפה. מופיע/ה בלוח, ובדרך כלל לא נספר/ת באיוש המשמרת.",
    audience: ["manager", "team"],
  },
  {
    term: "מפקד/ת משמרת",
    definition: "מי שיכול/ה לנהל משמרת. מסומן/ת בתג על כרטיס השיבוץ.",
    audience: ["manager", "team"],
  },
  {
    term: "כוננות",
    definition: "משמרת כונן, למשל כונן לילה. איך היא נספרת לשעות ולהוגנות נקבע בהגדרת היחידה.",
    audience: ["manager", "team"],
  },
  {
    term: "הגדרת יחידה",
    definition: "הטופס שבו מגדירים עובדים, משמרות, סבבים וכללים. השמירה מעדכנת את הפרופיל שממנו נבנים הסידורים.",
    audience: ["manager"],
  },
  {
    term: "מה שחוזר על עצמו",
    definition: "במסך ‘סקירה’: כללים שהתיקונים שלכם בסידור מרמזים עליהם, עם הראיות. הצעות בלבד — כלל נוסף רק בהגדרת היחידה.",
    audience: ["manager"],
  },
  {
    term: "ניקוי / מחיקה",
    definition: "‘ניקוי’ מרוקן את השיבוצים ומשאיר את שורות המשמרות, כדי לשבץ מחדש. ‘מחיקה’ מסירה את הסידור ומחזירה את השבוע למצב שלפני בנייה. שתיהן חסומות בשבוע מפורסם.",
    audience: ["manager"],
  },
  {
    term: "בנייה חלקית",
    definition: "בנייה של טווח ימים או של סוגי משמרות מסוימים בתוך סידור קיים. מה ששובץ ידנית נשאר, ושאר המשמרות לא משתנות.",
    audience: ["manager"],
  },
  {
    term: "שינויים",
    definition: "לשונית במגירת הסוכן: החלפת משמרת למי שלא זמין/ה, הוספת חייל והוספת משמרת — תוך שמירה על הסידור הקיים ככל האפשר.",
    audience: ["manager"],
  },
  {
    term: "הוצאה מהסגל",
    definition: "סיום עבודה מתאריך מסוים. המשמרות מאותו תאריך מתפנות והשם נשמר בהיסטוריה; אפשר להחזיר לסגל.",
    audience: ["manager"],
  },
  {
    term: "קישור צוות",
    definition: "קישור צפייה בסידור שפורסם, בלי סיסמה. כל מי שמחזיק בו רואה את הלוח; החלפת הקישור מבטלת את הקודם לכולם.",
    audience: ["manager", "team"],
  },
  {
    term: "קוד אישי",
    definition: "הסיסמה של עובד/ת לשם שבחר/ה בצוות. נכנסים איתו דרך ‘עובד/ת’ במסך הכניסה.",
    audience: ["manager", "team"],
  },
  {
    term: "ראיתי",
    definition: "בהודעה על שינוי במשמרות: מסמן שקראתם. זה לא אישור ולא הסכמה לשינוי.",
    audience: ["team"],
  },
];

export function glossaryFor(surface: Surface | null): GlossaryEntry[] {
  // Nobody signed in yet: show everything, the visitor may be either.
  if (surface === null || surface === "setup" || surface === "manager") {
    return GLOSSARY;
  }
  return GLOSSARY.filter((entry) => entry.audience.includes("team"));
}

export interface Shortcut {
  keys: string[];
  label: string;
  /** The keys are alternatives (either works) rather than a chord. */
  either?: boolean;
}

export function shortcutsFor(surface: Surface | null): { title: string; items: Shortcut[] }[] {
  const groups: { title: string; items: Shortcut[] }[] = [
    {
      title: "בכל מסך",
      items: [
        { keys: ["?"], label: "פתיחת העזרה" },
        { keys: ["Esc"], label: "סגירת חלון או סיור" },
      ],
    },
  ];
  if (surface === "manager") {
    groups.push(
      {
        // Mirrored for RTL, as `useBoardKeys` binds them.
        title: "לוח המשמרות",
        items: [
          { keys: ["←"], label: "קדימה — יום, שבוע או חודש, לפי התצוגה" },
          { keys: ["→"], label: "אחורה" },
          { keys: ["T", "א"], label: "חזרה להיום", either: true },
        ],
      },
      {
        title: "שיחה עם הסוכן",
        items: [
          { keys: ["Enter"], label: "שליחת ההודעה" },
          { keys: ["Shift", "Enter"], label: "שורה חדשה" },
        ],
      },
    );
  }
  groups.push({
    title: "בזמן סיור מודרך",
    items: [
      { keys: ["←"], label: "השלב הבא" },
      { keys: ["→"], label: "השלב הקודם" },
    ],
  });
  return groups;
}
