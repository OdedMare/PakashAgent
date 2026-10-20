# שלב 1 — אילוצים מקומפלים (מטמון תרגום)

> מטרה: אילוץ קבוע מתורגם **פעם אחת**, נשמר, ונטען מהמטמון בכל בנייה.
> בנייה שכל האילוצים שלה כבר קומפלו עולה **אפס קריאות מודל** לתרגום.

## 1. המצב היום

- `Scheduler._code_result` (`bl/scheduler/scheduler.py`) קורא ל־`DirectiveAgent.translate`
  **בכל** `generate_span` במצב `auto`. ב־`GenerationStepper` זה אומר: בכל span (יום או שבוע) של כל בנייה.
- `semantic_sources` (`bl/scheduler/directives.py`) נותן לכל מקור מזהה **לפי מיקום**
  (`source-1`, `source-2`...), כך שמזהה לא נשאר יציב אם מוסיפים כלל.
- התרגום **קשור לתקופה**: הפרומפט פורס כלל כמו "כל שלישי" לתאריכים של התקופה הנוכחית.
  לכן אי אפשר לשמור אותו כמו שהוא ולהשתמש בו בשבוע הבא.
- **אין מטמון שלילי.** מקור מחייב שהמודל מסמן `unresolved` (למשל `rest_policy`) נשלח שוב
  לתרגום בכל span ואז נופל ל־AI מלא. אלה טוקנים על כישלון ידוע מראש.

## 2. העיקרון

נפריד בין שני סוגי מקורות:

| סוג | דוגמאות | מטופל |
|---|---|---|
| **קבוע** (persistent) | `rule`, מדיניות טקסטואלית, `preference`, `employee_notes`, `recurring_constraint` וכו' | **נשמר במטמון**, בצורה שלא תלויה בתקופה |
| **חד־פעמי** (one-off) | `instructions` של הבנייה הנוכחית | מתורגם בכל בנייה, כמו היום |

לכל מקור קבוע נשמרת **רשומה מקומפלת** עם אחד משלושה מצבים:

- `compiled`: רשימת `requests` ו־`pins` שלא תלויה בתקופה, ונטענת ומסוננת לכל תקופה.
- `unresolved`: הקוד לא יכול לייצג את המקור (עם הסיבה). זה **מטמון שלילי**:
  - מקור מחייב → `auto` הולך ישר ל־AI, בלי לשלם על ניסיון תרגום.
  - משאלה → הקוד בונה בלעדיה ומציין אותה ב־`notes`, כמו היום.
- `period_bound`: המקור תלוי בזמן יחסי ("השבוע", "בשבוע הבא"). לא נשמר במטמון, ומתורגם בכל בנייה כמו היום.

## 3. הצורה המקומפלת: בלי תלות בתקופה

כדי שתרגום יהיה תקף לכל תקופה, במצב קומפילציה הפרומפט מחייב:

- **`requests` עם `weekdays`/`shifts` ולא עם `dates`.** "דנה לא בלילות שלישי"
  הופך ל־`avoid` עם `weekdays:["שלישי"]`, `shifts:["לילה"]`, `dates:[]`.
- **תאריך מוחלט מותר רק אם כתוב בטקסט עצמו**, למשל "דנה בחופשה 3–7.11".
  זה הופך ל־`avoid` קשיח עם `dates` ב־ISO. בזמן הבנייה תאריך שמחוץ לתקופה פשוט לא תואם אף משבצת.
- **`unavailable` חד־פעמי** (עובד + משמרת + תאריך מוחלט) נשמר כ־`avoid` קשיח עם
  `dates:[d]`, `shifts:[s]`. ככה יש צורה אחת בלבד במטמון.
- **`required_assignment`** נשמר כ־`pin` עם תאריך מוחלט. בבנייה ממזגים רק pins שבתוך התקופה.
- **"חובה כל שלישי" חוזר** אין לו ייצוג (`prefer` הוא רך בלבד), ולכן הוא מסומן `unresolved`.
  שלב 2 יוסיף לו סוג משלו.

למה זה בטוח: `honoring.py` כבר מסנן בקשות לפי `dates`/`weekdays`/`shifts`, כך שבקשה עם
תאריך מחוץ לתקופה לא משפיעה. לא צריך לשנות את מנוע הקוד.

## 4. מפתח המטמון ופסילה

```
source_key  = sha256(kind | context | text)            # זהות המקור, לפי התוכן
vocab_key   = sha256(sorted(employee names) | sorted(shift names) | sorted(weekdays in use))
compiler    = COMPILER_VERSION (קבוע בקוד) + sha256(prompt "scheduler_compile.md")
PRIMARY KEY = (team_id, source_key, vocab_key, compiler)
```

- **שינוי בטקסט** יוצר `source_key` חדש, כלומר החטאה וקומפילציה של המקור הזה בלבד.
- **שינוי ברוסטר או במשמרות** משנה את `vocab_key`, וכל המקורות של הצוות מקומפלים מחדש בבנייה הבאה.
  זה מכוון: "דני" יכול להפוך לדו־משמעי כשמצטרף "דניאל".
- **שינוי בפרומפט או בקוד המתרגם** (העלאת `COMPILER_VERSION`) פוסל את כל המטמון.
- **אימות גם בקריאה:** כל רשומה שנטענת עוברת שוב `read_requests` מול הפרופיל הנוכחי.
  רשומה שנכשלת נחשבת החטאה, ונכתבת מחדש אחרי קומפילציה. זה זול, אפס טוקנים.
- רשומות ישנות לא נמחקות מיד. ניקוי לפי `last_used_at` (מעל 90 יום) נכנס ל־worker של הקופיילוט.

## 5. סכמה: `compiled_sources`

ב־`dal/repository/ddl/agent.py`, בבלוק נפרד ואחרי `COMMIT` משלו (מוסכמת `schema.py`):

```sql
CREATE TABLE IF NOT EXISTS compiled_sources (
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source_key  TEXT NOT NULL,
    vocab_key   TEXT NOT NULL,
    compiler    TEXT NOT NULL,
    kind        TEXT NOT NULL,             -- rule / preference / employee_notes ...
    context     TEXT NOT NULL DEFAULT '',  -- employee name, when relevant
    text        TEXT NOT NULL,             -- the source as it was, for display (step 3)
    binding     BOOLEAN NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('compiled','unresolved')),
    requests    JSONB NOT NULL DEFAULT '[]',
    pins        JSONB NOT NULL DEFAULT '[]',
    reason      TEXT NOT NULL DEFAULT '',  -- why unresolved
    tokens      INTEGER NOT NULL DEFAULT 0,-- what compiling it cost; feeds the "saved" metric
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (team_id, source_key, vocab_key, compiler)
);
COMMIT;
```

`period_bound` לא נשמר בטבלה, ולכן אין לו ערך ב־`status`.

Repository חדש, `dal/repository/compiled_sources.py`, ב־mixin של `Repository`:

- `compiled_sources(team_id, vocab_key, compiler, source_keys) -> List[dict]`
- `save_compiled_sources(team_id, rows)`: `INSERT ... ON CONFLICT DO UPDATE`
- `touch_compiled_sources(team_id, keys)`: מעדכן `last_used_at`, ונקרא פעם אחת לבנייה
- `prune_compiled_sources(older_than)`: נקרא מה־worker

## 6. קוד — קבצים ושינויים

### 6.1 `bl/compiled_sources/` (חבילה חדשה, בלי SQL)

| מודול | אחראי על |
|---|---|
| `keys.py` | `source_key(source)`, `vocab_key(profile)`, `COMPILER_VERSION`, `compiler_id()` |
| `shape.py` | המרה בין התשובה המתורגמת לצורה המקומפלת, ובחזרה לקלט של התקופה (`to_period(rows, starts_on, ends_on)`: מסנן pins לתקופה ומחזיר `requests`, `required_assignments`) |
| `cache.py` | `TranslationCache`: port שקשור לצוות אחד. מקבל repository ו־`team_id`, ומספק `lookup(profile, sources)` ו־`store(profile, rows)`. יש גם `NullCache` לטסטים ולמסלולים בלי צוות |
| `__init__.py` | טבלת מודולים כמו בשאר החבילות |

### 6.2 `bl/scheduler/directives.py`

- `semantic_sources` מוסיף לכל מקור `persistent: bool` (`False` רק ל־`instructions`)
  ו־`key` (`source_key`). `id` נשאר מיקומי, כי המודל עובד איתו בתוך קריאה אחת.

### 6.3 `bl/directive_agent/`

- `agent.translate(..., cache=NullCache())`:
  1. `sources = semantic_sources(...)`
  2. `hits, misses = cache.lookup(profile, sources)`. רק מקורות קבועים יכולים להיות hit.
  3. **אם hit מחייב הוא `unresolved`, מחזירים `None` מיד.** אפס טוקנים, ישר ל־AI.
  4. אם אין misses: מרכיבים תוצאה מה־hits בלבד, בלי קריאת מודל.
  5. אחרת מריצים את הלולאה הקיימת **רק על ה־misses**. במקורות קבועים נשלח `mode: "compile"`
     לצד המקור, והוא מפעיל את כללי הצורה של §3.
  6. מפצלים את התשובה **לפי מקור** (ראו 6.4), שומרים את הקבועים עם `cache.store`,
     וממזגים עם ה־hits.
- **`partial.py`**: מפצלים מ־`read_partial` פונקציה בשם `per_source(answer, sources, profile, ...)`
  שמחזירה `{source_id: ("kept", items) | ("left", reason)}`. `read_partial` עצמו נבנה מעליה,
  וההתנהגות שלו לא משתנה. הפיצול הזה הוא מה שמאפשר לשמור כל מקור לחוד.
- **הבדל בין קומפילציה לאימות:** במצב compile, `translated_row` מאמת `(shift, date)` מול
  `build_slots` של התקופה, וזה פוסל תאריך מוחלט מחוץ לתקופה. לכן במצב compile:
  pin נבדק רק מול שם העובד, אוצר המשמרות ותאריך ISO תקין, ו־`avoid` עם `dates` נבדק
  ב־`read_requests` כמו היום.
- **`period_bound`:** מוסיפים שדה אופציונלי `"period_bound": true` לשורת `unresolved` ב־schema.
  שורה כזו לא נשמרת, והתרגום שלה בתוך התקופה ממשיך כרגיל.
  חלופה פשוטה יותר: לא לשמור שום מקור שהתרגום שלו כולל `dates` שלא מופיעים כ־ISO בטקסט המקור.
  זו שאלה פתוחה (§10).

### 6.4 `bl/prompts/scheduler_directives.md`

סעיף חדש בשם "Compile mode", שחל על מקור שמסומן `mode: "compile"`:
- אסור לפרוס לתאריכי התקופה. משתמשים ב־`weekdays`/`shifts`.
- `dates` רק כשהתאריך כתוב במפורש בטקסט.
- זמן יחסי ("השבוע", "מחר") מסומן `unresolved` + `period_bound: true`.
- חובה חוזרת מסומנת `unresolved` עם הסיבה.

`test_prompts.py` צריך לעבור. כל שינוי בפרומפט משנה את `compiler_id()` ופוסל את המטמון אוטומטית.

### 6.5 `bl/scheduler/scheduler.py`

- `generate_span(..., translation_cache=None)` ו־`generate_verified` מעבירים את המטמון הלאה
  עד `_translate_directives`.
- מוסיפים ל־`metrics`:
  - `compiled_hits`, `compiled_misses`
  - `compiled_negative`: hits מחייבים מסוג `unresolved` ששלחו ישר ל־AI
  - `tokens_saved`: סכום `tokens` של ה־hits
- כשהתרגום כולו מגיע מהמטמון, `summary` הוא "ההנחיות נטענו מתרגום שמור והשיבוץ נבנה בקוד".

### 6.6 החיבור לצוות

- `ScheduleContext.translation_cache(team_id)` מחזיר `TranslationCache(repository, team_id)`.
- `GenerationStepper._ask_model`, `PeriodBuilder`, `chat_generation.py` ו־`chat_lifecycle.py`
  מעבירים `translation_cache=...`.
- `Scheduler` נשאר בלי repository. הוא מקבל port, כמו ש־`PlanningAgent` מקבל tools
  (`schedule_service/service.py`).

### 6.7 קומפילציה מוקדמת (prewarm), אופציונלי בסוף השלב

- ה־worker של הקופיילוט (`bl/copilot.py`) מריץ בכל סבב `CompileSources(team)`:
  מחפש misses ומקמפל אותם ברקע עם תקופה ייחוסית (השבוע הבא) עבור `dry_run`.
- ככה גם הבנייה הראשונה אחרי שמירת כלל לא משלמת. בלי ה־prewarm, הבנייה הראשונה משלמת
  פעם אחת, וכל הבנייות שאחריה חינמיות.

## 7. מסמכים

- **`docs/DECISIONS.md` — D32, "תרגום אילוץ קבוע נשמר" (מתקן את D31 ואת D21).**
  - D21 אומר שאין אוצר מובנה שהעדפה מתקמפלת אליו. מאז D31 יש, ולכן D32 צריך לומר זאת.
  - המטמון הוא **נגזרת** של הטקסט ולא מחליף אותו. הטקסט נשאר המקור, ושינוי שלו פוסל את התרגום.
  - מטמון שלילי לא מוריד את המקור: מקור מחייב שלא תורגם תמיד מגיע ל־AI.
- `bl/CLAUDE.md`: שורה ל־`compiled_sources/` ופסקה על המטמון.
- `dal/CLAUDE.md`: להוסיף את `compiled_sources` לרשימת הטבלאות.

## 8. בדיקות

`tests/test_compiled_sources.py` (חדש), עם `_ScriptedLlm` מ־`test_directive_agent.py`
ומטמון בזיכרון (`dict`):

1. **בנייה שנייה בלי טוקנים:** כלל רך "עדיף שדנה לא בלילות שני".
   בבנייה של שבוע 1 יש קריאת מודל אחת ושמירה. בשבוע 2 אין אף קריאה, `compiled_hits == 1`,
   ובקשת ה־`avoid` זהה.
2. **מטמון שלילי:** `rest_policy` מחייב שסומן `unresolved` בבנייה הראשונה. בבנייה השנייה
   `translate` מחזיר `None` בלי קריאה, ו־`compiled_negative == 1`.
3. **שינוי טקסט:** עורכים את הכלל, ורק המקור הזה מקומפל מחדש. כלל אחר נשאר hit.
4. **שינוי רוסטר:** כשמצטרף עובד, הכול החטאה.
5. **`instructions` לא נשמרות** לעולם.
6. **תאריך מוחלט מחוץ לתקופה:** "דנה בחופשה 3.11" נשמר. בבנייה של אוקטובר לא נוצר avoid
   אפקטיבי. בבנייה של נובמבר דנה לא משובצת ב־3.11.
7. **אימות בקריאה:** רשומה במטמון עם עובד שכבר לא ברוסטר נחשבת החטאה.
8. **ערבוב:** 2 hits ו־1 miss יוצרים קריאת מודל אחת, שהמקורות ב־payload שלה הם **רק** ה־miss.
9. **`period_bound` לא נשמר.**
10. **`per_source`:** `read_partial` נותן אותה תוצאה כמו לפני הפיצול. הטסטים הקיימים ב־`test_directive_agent.py` עוברים בלי שינוי.

`tests/test_admin_postgres.py`/Postgres: טסט round-trip ל־repository, בתבנית של הטסטים הקיימים מול Postgres.

`docs/scheduler-comparison`: להוסיף תרחיש של "4 בנייות רצופות עם אותם כללים" ולהציג את `total_tokens` לכל בנייה.

## 9. סדר עבודה (commits)

1. `per_source` מתוך `partial.py`. ריפקטור טהור, הטסטים הקיימים ירוקים.
2. `keys.py` + `shape.py` + טסטים טהורים.
3. DDL + repository + טסט מול Postgres.
4. `TranslationCache`/`NullCache` + החיבור ב־`DirectiveAgent` (hits, misses, מטמון שלילי).
5. Compile mode בפרומפט ובאימות.
6. העברת המטמון דרך `Scheduler` וכל הקוראים, + metrics.
7. D32 + עדכוני `CLAUDE.md`.
8. (אופציונלי) prewarm ב־worker + ניקוי.

## 10. שאלות פתוחות

- **זיהוי `period_bound`:** לסמוך על המודל (שדה ב־schema), או על הכלל המכני של §6.3
  ("dates שלא כתובים בטקסט פירושם לא לשמור")? ההמלצה: **שניהם**. המודל מסמן, והקוד אוכף את הכלל המכני כרשת ביטחון.
- **`instructions` שחוזרות:** אם מנהל כותב את אותה הנחיה בכל שבוע, האם לשמור גם אותן, לפי hash יחד עם התקופה? לא בשלב 1. נמדוד קודם.
- **prewarm:** האם להכניס כבר עכשיו, או אחרי שנראה מספרים מהמטמון העצל?
