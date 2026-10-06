/** What the in-app guide says, per surface.
 *
 *  Kept apart from the components so the copy can be read and corrected in
 *  one place. Every sentence here describes behaviour that already exists —
 *  the guide teaches the product, it does not promise one. If a button is
 *  renamed, the tour step naming it is the second place to change.
 *
 *  Steps point at `data-tour` attributes on real elements rather than at
 *  class names, so restyling a screen cannot silently detach the tour. */

export type Surface = "manager" | "employee" | "member" | "interview";

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
  manager: [
    {
      target: "nav",
      title: "שלושה מסכים, מקום אחד",
      body: "‘לוח המשמרות’ הוא מרכז העבודה. ‘כוח אדם’ מרכז עובדים, משמרות ואילוצים, ו‘נתונים’ מציג כיסוי, שעות ועומס. ‘סוכן הסידור’ נפתח לצד הלוח, כך שלא מאבדים את ההקשר.",
      prepare: "board",
    },
    {
      target: "week-nav",
      title: "מעבר בין שבועות",
      body: "החצים עוברים שבוע קדימה או אחורה. במקלדת: ← לשבוע הבא, → לשבוע הקודם, ו‑T (או א) חוזר לשבוע הנוכחי.",
      prepare: "board",
    },
    {
      target: "board-actions",
      title: "טיוטה, קובץ ופרסום",
      body: "התג מראה אם השבוע עוד טיוטה או כבר פורסם. ‘פרסום לצוות’ הוא הרגע שבו העובדים רואים את הגרסה, ואזהרות אינן חוסמות אותו. ‘אקסל’ מוריד קובץ בלי לשנות דבר.",
      optional: true,
    },
    {
      target: "empty-week",
      title: "שלוש דרכים להתחיל שבוע",
      body: "‘בניית הסידור’ מפעילה את הסוכן. ‘שבוע ריק’ משאיר את השיבוץ בידיים שלכם. ‘ייבוא מקובץ’ קורא סידור קיים ומציג איך הבין אותו לפני שמשהו נשמר.",
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
      body: "+ בתא ריק משבץ מיד. גרירה של שיבוץ קיים היא הצעה: המערכת בודקת את ההשפעה ומבקשת סיבה לפני שהשינוי נשמר. ‘סוכן ליום’ בראש עמודה פותח את הסוכן על אותו יום.",
      optional: true,
    },
    {
      target: "agent-composer",
      title: "לדבר עם הסוכן",
      body: "כתבו שאלה או בקשה במילים שלכם. שאלה מקבלת תשובה ולא משנה דבר. בקשה לשינוי חוזרת כתוכנית עם הנימוק והאזהרות — ושום דבר לא נשמר עד ‘החלת התוכנית’.",
      prepare: "agent",
      optional: true,
    },
    {
      target: "drawer-tabs",
      title: "כלי הניהול",
      body: "‘בקשות’ — אילוצים והחלפות שעובדים שלחו לאישורכם. ‘צוות’ — העדפות שהסוכן זוכר ואילוצים. ‘סקירה’ — אזהרות, היסטוריית שינויים והתצפיות שהסוכן אסף מיוזמתו.",
      prepare: "agent",
      optional: true,
    },
    {
      target: "header-actions",
      title: "הגדרות היחידה",
      body: "הנצנוץ פותח מחדש את ראיון ההיכרות (מספר עליו = נושאים פתוחים). אייקון השיתוף מציג את קישור הצפייה לצוות, וגלגל השיניים מנהל את חיבור המודל והסיסמה.",
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
      body: "‘המשמרות שלי’ — מתי ועם מי. ‘הנתונים שלי’ — שעות ומשמרות ביחס לצוות. ‘הלוח המלא’ — הסידור שפורסם, לקריאה בלבד.",
    },
    {
      target: "employee-requests-tab",
      title: "בקשות והחלפות",
      body: "שלחו אילוץ (תאריך, משמרת וסיבה) או הציעו החלפה לעמית. בקשה נשארת ‘ממתינה’ ואינה משנה דבר עד שהמנהל מחליט; החלפה דורשת גם את הסכמת העמית.",
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
    term: "סימולציה",
    definition: "‘מה יקרה אם…’ — חישוב ההשפעה של שינוי על כיסוי, שעות ואזהרות, בלי לשמור דבר.",
    audience: ["manager"],
  },
  {
    term: "סיבה",
    definition: "הזזה של מי שכבר שובץ, למשל בגרירה, מבקשת סיבה שנשמרת ביומן השינויים. בשיחה עם הסוכן, הבקשה שכתבתם נרשמת כסיבה.",
    audience: ["manager"],
  },
  {
    term: "יומן שינויים",
    definition: "רשימה שרק מתווספים אליה: מה השתנה, מתי ולמה. נמצא בלשונית ‘סקירה’.",
    audience: ["manager"],
  },
  {
    term: "אילוץ",
    definition: "מתי מישהו לא יכול או מעדיף שלא לעבוד. כל אילוץ מסומן במקור שלו: מנהל, סוכן, דיווח של העובד או הראיון.",
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
    definition: "הקשר שהסוכן זוכר בניסוח שלכם, כמו ‘מאיה מעדיפה בקרים’. העדפה שהסוכן הציע אינה פעילה עד שתאשרו, וכולן גלויות וניתנות למחיקה בלשונית ‘צוות’.",
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
    definition: "משמרת כונן, למשל כונן לילה. איך היא נספרת לשעות ולהוגנות נקבע בראיון ההיכרות.",
    audience: ["manager", "team"],
  },
  {
    term: "ראיון היכרות",
    definition: "השיחה שבה פקש לומד את היחידה: עובדים, משמרות, צרכים וכללים. אפשר לעצור באמצע ולחזור; המספר על כפתור הראיון סופר נושאים פתוחים.",
    audience: ["manager"],
  },
  {
    term: "תיבת הסוכן",
    definition: "בלשונית ‘סקירה’: תצפיות והצעות שהסוכן אסף מיוזמתו. הוא לא משנה סידור לבד — כל תיקון נשאר הצעה לאישורכם.",
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
  if (surface === null || surface === "manager" || surface === "interview") {
    return GLOSSARY;
  }
  return GLOSSARY.filter((entry) => entry.audience.includes("team"));
}

export interface Shortcut {
  keys: string[];
  label: string;
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
          { keys: ["←"], label: "השבוע הבא" },
          { keys: ["→"], label: "השבוע הקודם" },
          { keys: ["T", "א"], label: "חזרה לשבוע הנוכחי" },
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
