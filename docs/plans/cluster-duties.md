# תורנויות מכלול: מפקד המכלול משבץ תורנויות לכל החיילים

> מטרה: דרג חדש מעל הצוותים, **מכלול**. מפקד המכלול מגדיר סוגי תורנויות
> (מטבח, שמירה, ש״ג…) ומשבץ אליהן חיילים מכל הצוותים שבמכלול. חייל בתורנות
> **חסום ליום כולו**: הפותר לא ישבץ אותו, ומנהל הצוות לא יכול לעקוף את החסימה.
> השיבוץ ידני, ויש גם "מלא בהוגנות" שמציע חלוקה למפקד לאישור, בלי מודל.

## סטטוס: תוכנית, עוד לא מומשה

החלטות שהתקבלו: (1) תפקיד חדש מעל הצוותים, (2) חסימה של יום שלם,
(3) שיבוץ ידני עם הצעה הוגנת.

---

## 1. מה קיים היום ועל מה בונים

- **`duties`** (`dal/repository/ddl/scheduling.py`): תורנות חוסמת לחייל אחד,
  לפי שעות, ברמת הצוות. `records.availability()` מאחדת אותה עם `availability`
  לצורה אחת (`constraint_type='duty'`).
- **אכיפה, שקיימת כבר בכל המקומות**:
  - הפותר: `scheduler/availability.py` → `effective_availability`
  - שיבוץ ידני וגרירה: `schedule_service/operations.py::assert_no_blocking_duty`
    (`ConflictError` שאי אפשר לעקוף)
  - ביקורת: `audit/constraints.py::_duty_overlaps`, `audit/checks/people.py`
  - כלי הצ'אט "מי לא נמצא": `tools/team_tools.py`, `planner/team_answers.py`
  - ממשק: `ConfirmDrop.tsx` ו־`ShiftEditor.tsx` כבר מסבירים "תורנות חוסמת"
- **תפקידים**: `boss` / `member` / `employee` לכל צוות (`common/sessions.py`),
  ובנוסף `admin` (צוות משמרות זהב) עם cookie נפרד (D28). אין היום שום דרג
  מעל צוות.

**העיקרון**: תורנות מכלול נכנסת **לאותה שאילתה** (`records.availability`)
כשורת `duty`. כך כל מנגנוני האכיפה הקיימים מכבדים אותה בלי שינוי. הדבר
החדש היחיד במסלול האכיפה הוא הסמנטיקה של "יום שלם".

---

## 2. מודל נתונים

```sql
-- מכלול: קבוצת צוותים עם מפקד אחד
CREATE TABLE IF NOT EXISTS clusters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,          -- הסיסמה של מפקד המכלול
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- לכל צוות לכל היותר מכלול אחד
ALTER TABLE teams ADD COLUMN IF NOT EXISTS cluster_id TEXT
    REFERENCES clusters(id) ON DELETE SET NULL;

-- סוגי התורנויות של המכלול
CREATE TABLE IF NOT EXISTS cluster_duty_types (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                   -- "מטבח", "שמירה"
    seats INT NOT NULL DEFAULT 1,         -- כמה חיילים ביום
    days TEXT[] NOT NULL DEFAULT '{}',    -- ריק = כל יום
    active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (cluster_id, name)
);

-- שיבוץ: חייל אחד, יום אחד, תורנות אחת
CREATE TABLE IF NOT EXISTS cluster_duties (
    id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL REFERENCES clusters(id) ON DELETE CASCADE,
    duty_type_id TEXT NOT NULL REFERENCES cluster_duty_types(id) ON DELETE CASCADE,
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    employee TEXT NOT NULL,               -- השם כפי שהוא בפרופיל הצוות
    duty_date DATE NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id, employee, duty_date) -- תורנות אחת ליום לחייל
);
CREATE INDEX IF NOT EXISTS cluster_duties_team_date_idx
    ON cluster_duties (team_id, duty_date);
```

**למה טבלה נפרדת ולא שורות ב־`duties`**: הבעלים הוא המכלול ולא הצוות. מנהל
הצוות לא מוחק ולא עורך אותן (`delete_availability` מוחק לפי `team_id`, ולכן
לא יגיע לטבלה הזו). ההיסטוריה של המכלול שלמה גם אם צוות עוזב.

**זיהוי חייל**: `(team_id, employee)`, כמו בכל שאר המערכת. כשמשנים שם חייל
בפרופיל, צריך לעדכן גם את `cluster_duties` (באותו מקום שבו שינוי שם מטופל
היום), אחרת התורנות "תתנתק".

---

## 3. אכיפה: איך היא מגיעה לכל מקום

1. **`records.availability()`**: מוסיפים ענף שלישי ל־`UNION ALL`:
   ```sql
   SELECT cd.id, cd.team_id, cd.employee, cd.duty_date AS constraint_date,
          '' AS shift_name, FALSE AS available,
          '' AS start_time, '' AS end_time, TRUE AS is_hard,
          t.name AS reason,  -- "מטבח"
          'cluster' AS source, cd.created_at, 'duty' AS constraint_type
   FROM cluster_duties cd JOIN cluster_duty_types t ON t.id = cd.duty_type_id
   ```
   - מרחיבים את `source` (גם ב־CHECK של `availability`/`duties` אם נדרש)
     בערך `'cluster'`, כדי שהממשק יידע לכתוב "נקבע ע״י מפקד המכלול".
2. **סמנטיקת יום שלם**: תורנות בלי שעות = חוסמת **כל משמרת שתאריכה הוא
   יום התורנות**.
   - `audit/constraints.py::_duty_overlaps`: אם אין `start_time`/`end_time`
     משווים תאריך (`_same_occurrence` בלי shift) במקום חפיפת שעות.
   - `schedule_service/constraints.py` ו־`api/contracts/*`: לא משנים. תורנות
     ידנית של הצוות עדיין דורשת שעות. רק שורות `source='cluster'` מגיעות בלי.
   - `operations.py::assert_no_blocking_duty`: הודעה חדשה כשאין שעות:
     `"%s בתורנות מכלול (%s) בתאריך הזה ולכן לא ניתן לשבץ אותו/ה."`
   - הסינון של היום הקודם ב־`records.availability` / `_explicit_rows`
     (`-1 day` לתורנות לילה) לא מזיק, כי תורנות יום שלם לא חוצה חצות.
3. **פותר**: אין שינוי. הוא כבר מוציא שורת `duty` קשיחה מרשימת המועמדים.
   צריך לוודא בבדיקה ש־`solver/rows.py` מחשב את החפיפה דרך `constraint_conflicts`.
4. **מחיקה ע״י מנהל צוות**: `delete_availability` מוחק רק מ־`availability`
   ומ־`duties`, ולכן תורנות מכלול נשארת. בממשק מסתירים לה את כפתור המחיקה.

---

## 4. כשתורנות נופלת על משמרת שכבר שובצה

זה המקרה הקשה. הצעה:

| מצב השבוע | מה קורה |
|---|---|
| טיוטה (לא פורסם) | המושב מתפנה ומתמלא אוטומטית במסלול של D40/D37 (`refit`) |
| פורסם | המושב **לא** מתפנה לבד. נוצרת התראה למנהל הצוות ("X בתורנות מטבח ב־12/11 ומשובץ לבוקר") עם כפתור "מצא מחליף" (מסלול ההיעדרות של D36) |

לפני שמירה, מסך המפקד מציג אזהרה: "החייל משובץ למשמרת בוקר בצוות א׳". זו
אזהרה ולא חסימה: המפקד מחליט, והצוות מתאים את עצמו.

---

## 5. "מלא בהוגנות" (בלי מודל)

`bl/cluster/fill.py`, פונקציה טהורה:

- **קלט**: סוגי תורנויות, טווח תאריכים, כל החיילים הפעילים בצוותי המכלול,
  שיבוצים קיימים, ומונה תורנויות לכל חייל (היסטוריה של 60 יום אחורה).
- **פסילה (קשיח)**: חייל בבית לפי הסבב (`rotation/presence.py::presence_status`),
  אילוץ יום שלם קשיח, תורנות אחרת באותו יום, `inactive_from`, נחפף/ת (לבחירה).
- **דירוג (רך)**: הכי מעט תורנויות קודם, אחר כך מי שאין לו משמרת באותו יום,
  אחר כך הכי רחוק מהתורנות האחרונה, ושובר שוויון קבוע (שם) לתוצאה דטרמיניסטית.
- **פלט**: הצעה בלבד (רשימת שורות + סיבה לכל אחת). שום דבר לא נשמר עד
  שהמפקד לוחץ "אשר". אותו עיקרון כמו D20 ("סימולציה אינה הצעה").

אלגוריתם חמדני יום אחרי יום מספיק. CP-SAT לא נדרש בשלב הזה.

---

## 6. הרשאות והתחברות

- **תפקיד חדש `cluster`** עם cookie נפרד `pakash_cluster`, באותו דפוס של
  `pakash_admin` (D28): המפקד לא שייך לצוות אחד, ושני ה־cookies צריכים לחיות
  יחד בדפדפן. `Guards.cluster()` ב־`api/dependencies.py`.
- **מי פותח מכלול**: המפעיל, בקונסולה `/admin`: "פתיחת מכלול" (שם + סיסמה,
  כרטיס מסירה חד-פעמי כמו בצוות) ושיוך צוותים למכלול (`teams.cluster_id`).
  איפוס סיסמה דרך המפעיל.
- **מה המפקד רואה**: שמות, צוות, תפקיד, סבב ונוכחות של כל חייל בצוותי
  המכלול, ואילו משמרות יש לו (קריאה בלבד). הוא **לא** רואה צ'אט, בקשות או
  הערות של הצוות.
- **מה מנהל הצוות רואה**: את תורנויות המכלול של אנשיו (קריאה בלבד, עם תג
  "מפקד המכלול"), בלוח, ב־TeamPanel וב"מי לא נמצא".
- **חייל**: רואה את התורנות שלו באזור האישי.
- כל השאילתות חוצות-הצוותים של המכלול נמצאות ב־mixin אחד,
  `dal/repository/clusters.py`, כמו `admin.py`, כדי שיהיה קובץ אחד לבדוק.
  כל שאילתה מסוננת `WHERE team.cluster_id = session.cluster_id`.

---

## 7. API

`api/routers/cluster.py`, הכול תחת `Guards.cluster()`:

| שיטה | נתיב | מה |
|---|---|---|
| POST | `/api/cluster/login` · `/logout` · GET `/me` | התחברות |
| GET | `/api/cluster/roster?from&to` | כל החיילים + נוכחות + משמרות בטווח |
| GET/POST/PATCH/DELETE | `/api/cluster/duty-types[/{id}]` | ניהול סוגי תורנויות |
| GET | `/api/cluster/duties?from&to` | השיבוצים |
| POST | `/api/cluster/duties` | שיבוץ (מחזיר אזהרות התנגשות) |
| DELETE | `/api/cluster/duties/{id}` | ביטול |
| POST | `/api/cluster/duties/suggest` | "מלא בהוגנות": מחזיר הצעה ולא שומר |
| POST | `/api/cluster/duties/bulk` | אישור הצעה (טרנזקציה אחת) |
| GET | `/api/cluster/stats?from&to` | מונה תורנויות לחייל |

לכל שמירה ומחיקה: `append_change` ביומן של **הצוות** של החייל (פעולה חדשה
`ACTION_CLUSTER_DUTY`), כדי ש"למה יוסי הוזז" ימשיך לקבל תשובה (D4). אחר כך
מפעילים refit לטיוטות ומתריעים על שבועות שפורסמו (§4).

Admin: `POST /api/admin/clusters`, `PATCH /api/admin/teams/{id}` עם `cluster_id`.

---

## 8. ממשק

- **`/cluster`** (דף חדש, `components/Cluster/`):
  - **לוח תורנויות**: שורות = סוגי תורנויות, עמודות = ימים (שבוע/שבועיים).
    כל תא = מושבים. לחיצה פותחת בורר חיילים עם חיפוש, סינון לפי צוות, וסימון
    "בבית" / "במשמרת" / "כבר בתורנות", כמו `CandidateFilters` בלוח הקיים.
  - כפתור **"מלא בהוגנות"** לטווח: ההצעה מוצגת בתאים בצבע טיוטה, ואחריה
    "אשר" או "בטל".
  - **הגדרות**: ניהול סוגי תורנויות.
  - **מאזן**: טבלת מונה תורנויות לכל חייל (מי קיבל הכי הרבה, מי הכי מעט).
- **Admin**: לשונית "מכלולים" (פתיחה, שיוך צוותים, איפוס סיסמה).
- **צוות**: תג "תורנות מכלול · מטבח" בלוח וב־TeamPanel, בלי כפתור מחיקה.
  התראה על התנגשות בשבוע שפורסם.
- **מדריך**: מונח חדש "תורנות מכלול" ב־`Guide/content.ts`.

---

## 9. סדר מימוש (כל שלב נבדק לבד)

1. **DDL + repository + אכיפה**: הטבלאות, הענף ב־`availability()`,
   סמנטיקת יום שלם ב־`_duty_overlaps` ו־`assert_no_blocking_duty`.
   בדיקות: הפותר לא משבץ, שיבוץ ידני נדחה, ביקורת מסמנת, מנהל לא מוחק.
2. **תפקיד + התחברות + Admin**: `clusters`, `pakash_cluster`, פתיחה ושיוך.
3. **API ידני**: roster, duty-types, duties, יומן שינויים.
4. **התנגשויות**: refit לטיוטות והתראה לשבועות שפורסמו.
5. **ממשק המפקד**: לוח, בורר, הגדרות.
6. **"מלא בהוגנות"** + מאזן.
7. **תצוגה בצד הצוות והחייל** + מדריך + `DECISIONS.md` (D43).

---

## 10. שאלות פתוחות

- **משמרת לילה שמסתיימת בבוקר יום התורנות**: לחסום גם אותה? (ההצעה: לא.
  "יום שלם" = משמרות שתאריכן הוא יום התורנות.)
- **מנוחה אחרי תורנות** (למשל אחרי שמירת לילה): לא בשלב הזה. אפשר להוסיף
  בהמשך `rest_hours_after` לסוג התורנות.
- **האם חייל רואה את התורנות של אחרים?** (ההצעה: רק את שלו.)
- **חיילים שלא בשום צוות** (למשל אנשי מטה): כרגע מחוץ לתחום. כל חייל שייך
  לצוות.
