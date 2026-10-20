# שלב 1 — אילוצים מקומפלים (מטמון תרגום)

> מטרה: אילוץ קבוע מתורגם **פעם אחת**, נשמר, ונטען מהמטמון בכל בנייה.
> בנייה שכל האילוצים שלה כבר קומפלו עולה **אפס קריאות מודל** לתרגום.
> אילוצי הגדרת היחידה מתורגמים כבר ברגע שהם נשמרים (§6.7), כך שגם הבנייה הראשונה חינמית.

## סטטוס: מומש (D32)

הקוד ב־`backend/app/bl/compiled_sources/`. מה שונה מהתוכנית בזמן המימוש:

- **טבלה:** עמודת `translation` אחת מסוג JSONB (availability, pins, requests) במקום `requests`/`pins` נפרדים.
- **מה לא נשמר:** רק מה שהמודל עצמו סימן `unresolved` נשמר כשלילי. מה שהקוד דחה, או שהמודל דילג עליו, ינוסה שוב בבנייה הבאה.
- **משימת קומפילציה בלי מודל, או כשהמודל לא זמין:** מסתיימת בלי retry ובלי פריט בתיבת הקופיילוט. הבנייה הבאה מתרגמת מה שחסר.
- **מסך:** סעיף נפרד "מה הקוד הבין" בהגדרת היחידה, ולא תגים ליד כל שדה.
- **בתוך טרנזקציית אישור הצ'אט** בדיקת המטמון בשמירה רק קוראת, בלי `touch`.

## שלב 2: מומש

ארבעה סוגי בקשות חדשים ב־`bl/schedule_requests.py`, שנאכפים ב־`deterministic_scheduler/limits.py`:

| סוג | משמעות | דוגמה |
|---|---|---|
| `min_rest` | לפחות `count` שעות בין משמרות. `shifts` מצמצם למנוחות שנוגעות במשמרות האלה | "מינימום 12 שעות", "16 שעות אחרי לילה" |
| `max_consecutive` | לכל היותר `count` ימים רצופים במשמרות התואמות. נספרים גם 14 הימים שלפני התקופה | "לא יותר משני לילות ברצף" |
| `balance` | חלוקה שווה בין העובדים (או כל הצוות). תמיד רך | "סופ״שים מתחלקים שווה" |
| `requires_with` | העובד משובץ רק כשאחד מ־`partners` באותה משמרת | "נועה רק עם דנה" |

- `min_rest`, `max_consecutive` ו־`balance` יכולים לא לציין אף עובד, ואז הם חלים על כל הצוות. זה מה שמאפשר לתרגם מדיניות.
- `COMPILER_VERSION` עלה ל־2, כך שכל מדיניות שנשמרה קודם כ"לא תורגם" תיקרא מחדש.
- **מה עדיין הולך ל־AI:** מדיניות חניכה (הקוד לא משבץ חניכים), מדיניות שרק חוזרת על הסבבים, וניסוחים כמו "שיקול דעת". חונך שמתואר בלי שם ("רק עם מישהו ותיק") גם הוא לא מתורגם.

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

מקור עם **זמן יחסי** ("עודד חולה 3 או 4 ימים", "מחר", "בשבוע הבא") לא נשאר "קשור לתקופה".
המודל מעגן אותו לתאריך שבו האילוץ נכתב, הופך אותו לתאריכים מוחלטים, והתוצאה נשמרת במטמון
כמו כל מקור אחר (§3.1).

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

### 3.1 זמן יחסי: המודל מזהה ומעגן

אילוצים כמו "עודד חולה 3 או 4 ימים" נכתבים בשפה חופשית, בלי תאריך. המודל מזהה את ביטוי
הזמן והופך אותו לתאריכים מוחלטים, לפי **תאריך העיגון** (`anchored_on`): היום שבו הטקסט
נכתב, ולא היום שבו מריצים בנייה.

**מאיפה בא תאריך העיגון.** `israel_today()` (`common/time_context.py`) ברגע שה־hook
של השמירה רואה את הטקסט לראשונה. הוא נשמר בטבלה `source_anchors` (§5) לפי `source_key`.
הוא **לא משתנה** כשמקמפלים מחדש בגלל שינוי ברוסטר או בפרומפט. אחרת "3 ימים" היה זז קדימה
בכל קומפילציה. שינוי בטקסט יוצר `source_key` חדש, וכך גם עיגון חדש. זה נכון: מנהל שכותב
"עודד חולה עוד יומיים" מתכוון להיום.

**מה המודל מחזיר לכל מקור** (שדה חדש `timing` בתשובה, שורה לכל `source_id`):

| שדה | משמעות |
|---|---|
| `kind` | `none` (אין זמן), `absolute` (תאריך כתוב בטקסט), `relative` (מעוגן ל־`anchored_on`) |
| `phrase` | ביטוי הזמן כפי שהופיע ("3 או 4 ימים"), להצגה למנהל |
| `starts_on` / `ends_on` | הטווח הוודאי, ב־ISO |
| `maybe_through` | סוף הטווח כשיש אי־ודאות ("או 4"), אחרת ריק |
| `question` | שאלה קצרה בעברית למנהל כשיש אי־ודאות ("לחסום גם את 24.10?") |

**"עודד חולה 3 או 4 ימים"**, שנכתב ב־20.10.2026 (שלישי):
- `relative`, טווח ודאי 20.10–22.10, `maybe_through: 23.10`.
- הימים הוודאיים הופכים ל־`avoid` קשיח (`dates: 20–22`, כל המשמרות), כי מחלה היא היעדרות ולא משאלה.
- היום הלא־ודאי (23.10) הופך ל־`avoid` **רך** עם `weight: 3`. הקוד ינסה לא לשבץ את עודד,
  אבל אם אין ברירה ישבץ ויציין זאת ב־`notes`.
- `question` מוצגת כתג "צריך אישור" ליד ההערה (D24: הסוכן שואל במקום לנחש).
  כשהמנהל עונה, הטקסט מתעדכן ("עודד חולה עד 23.10"), ומתקבל `source_key` חדש ותרגום מדויק.

ספירת "ימים" פירושה ימים קלנדריים, כולל יום הכתיבה, אלא אם כתוב "ימי עבודה". זה כתוב בפרומפט ונבדק בטסט.

**רשת הביטחון בקוד** (`compiled_sources/timing.py`), שבודקת כל שורת `timing` לפני שמירה:
- `none` אבל התרגום כולל `dates` → לא נשמר, ומתורגם בתוך התקופה כמו היום.
- `relative`: כל התאריכים בתוך `[anchored_on, anchored_on + 90 יום]`, ו־`starts_on <= ends_on <= maybe_through`.
  אחרת המקור מסומן `unresolved` ("ביטוי הזמן לא הובן").
- `absolute`: כל תאריך בתרגום חייב להופיע בטקסט, בכל אחד מהפורמטים `d.m`, `d/m`, `d.m.yy` או ISO.
- המטמון שומר `expires_on` (התאריך המאוחר ביותר). אחרי שעבר:
  - הרשומה לא משפיעה, וממילא אין משבצות בתאריכים האלה.
  - בהגדרת היחידה מופיע תג "פג תוקף, אפשר למחוק את ההערה".
  - מקור מחייב שפג תוקפו **לא** שולח את הבנייה ל־AI.

**ביטוי שאין לו עיגון** ("בתקופה שאחרי החגים", "כשיחזור מהמילואים") מסומן `unresolved` עם הסיבה.
אם הוא מחייב, הבנייה עוברת ל־AI כמו היום.

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

בנוסף, `compiled_sources` מקבלת שני שדות: `expires_on DATE NULL` ו־`question TEXT NOT NULL DEFAULT ''`.

עוד טבלה קטנה, לתאריך העיגון של כל מקור (§3.1):

```sql
CREATE TABLE IF NOT EXISTS source_anchors (
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    source_key  TEXT NOT NULL,
    anchored_on DATE NOT NULL,
    PRIMARY KEY (team_id, source_key)
);
COMMIT;
```

היא נכתבת עם `INSERT ... ON CONFLICT DO NOTHING`, כך שהעיגון הראשון נשאר.

Repository חדש, `dal/repository/compiled_sources.py`, ב־mixin של `Repository`:

- `compiled_sources(team_id, vocab_key, compiler, source_keys) -> List[dict]`
- `save_compiled_sources(team_id, rows)`: `INSERT ... ON CONFLICT DO UPDATE`
- `touch_compiled_sources(team_id, keys)`: מעדכן `last_used_at`, ונקרא פעם אחת לבנייה
- `prune_compiled_sources(older_than)`: נקרא מה־worker

## 6. קוד — קבצים ושינויים

### 6.1 `bl/compiled_sources/` (חבילה חדשה, בלי SQL)

| מודול | אחראי על |
|---|---|
| `timing.py` | בדיקת שורות `timing` מול `anchored_on` והטקסט, וחישוב `expires_on` (§3.1) |
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
- **זמן:** כל מקור קבוע נשלח עם `anchored_on` שלו, וה־schema של התשובה מקבל מערך `timing` (§3.1).
  `compiled_sources/timing.py` בודק אותו לפני `cache.store`.
  מקור `instructions` (חד־פעמי) מעוגן לתאריך הבנייה ולא נשמר.

### 6.4 `bl/prompts/scheduler_directives.md`

סעיף חדש בשם "Compile mode", שחל על מקור שמסומן `mode: "compile"`:
- אסור לפרוס לתאריכי התקופה. משתמשים ב־`weekdays`/`shifts`.
- `dates` רק כשהתאריך כתוב במפורש בטקסט.
- זיהוי ביטויי זמן ועיגונם ל־`anchored_on` של המקור, לפי §3.1: טווח ודאי, `maybe_through`,
  שאלה למנהל כשיש אי־ודאות, וימים קלנדריים כולל יום הכתיבה.
- ודאי → `avoid` קשיח. לא ודאי → `avoid` רך עם `weight: 3`. מחלה וחופשה הן היעדרות ולא משאלה.
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

### 6.7 קומפילציה בזמן שמירת הגדרת היחידה (חלק מהשלב)

האילוצים שהמנהל כותב בהגדרת היחידה הראשונית מתורגמים **מיד כשהם נשמרים**, ולא בבנייה
הראשונה. כך הבנייה הראשונה כבר חינמית, והמנהל רואה עוד לפני כל בנייה מה הקוד הבין ומה ידרוש AI.

**מה נכנס.** כל מקור קבוע ש־`semantic_sources` מוצא בפרופיל:

| שדה בהגדרה | `kind` |
|---|---|
| `rules` (כללים, `hard`/`soft`) | `rule` |
| `dependencies`, `rest_policy`, `weekend_policy`, `fairness_policy`, `conflict_policy`, `casual_worker_policy` | שם השדה |
| `workplace.general_exit_schedule` | `general_exit_schedule` |
| `training_policy` | `training_policy` |
| לכל עובד: `notes`, `availability`, `workload`, `trainers`, `is_trainee` | `employee_*` |
| לכל עובד: `recurring_constraints` שנכתבו כמשפט | `recurring_constraint` |

`recurring_constraints` מובנים (עם `days`/`shifts`/`available`) **לא** נכנסים: הקוד כבר
מבין אותם בלי מודל (`honoring.py`).
העדפות (D21) מקומפלות באותו מנגנון כשהן מאושרות (`PreferenceService`).

**הזרימה:**

1. `ProfileService.update` נשאר **סינכרוני ובלי מודל**, כמו שה־README מבטיח: "zero-token setup".
   אחרי שמירה מוצלחת הוא קורא ל־`compile_hook(team_id)`.
2. ה־hook מחשב את המקורות ואת המפתחות (§4), ומוציא את אלה שכבר נמצאים במטמון.
   אם נשאר משהו, הוא מכניס לתור הקיים (`copilot_jobs`) משימה
   `kind="compile_sources"` עם `dedupe_key = "compile:" + vocab_key`.
   כמה שמירות רצופות יוצרות משימה אחת בלבד.
3. `worker.py`: ענף חדש ב־`_execute` לסוג `compile_sources`, שמריץ את `SourceCompiler.compile(team_id)`:
   - קורא את הפרופיל **העדכני** ולא את זה מרגע השמירה, ומחשב שוב את ה־misses.
   - מריץ את `DirectiveAgent` במצב compile, ב**קבוצות של עד 12 מקורות** לקריאה.
     זה שומר על payload קטן ועל ה־bounds הקיימים.
   - **תקופת ייחוס** ל־`list_slots`/`check`/`dry_run` היא השבוע הקרוב (ראשון עד שבת).
     הפלט עצמו לא תלוי בתקופה, לפי §3.
   - שומר כל מקור לחוד: `compiled` או `unresolved`.
   - כשאין מודל מוגדר, המשימה מסתיימת בלי כלום. אין שגיאה ואין retry, והבנייה תתנהג כמו היום.
4. כשלון רשת או מודל עובר דרך ה־retry הרגיל של `finish_copilot_job`. מקור שלא קומפל פשוט יקומפל בבנייה (lazy, §6.3).

**מה המנהל רואה (מינימלי בשלב 1).** בהגדרת היחידה, ליד כל כלל, מדיניות או הערת עובד יש תג:
- "מתורגם לקוד ✓"
- "ידרוש AI", עם ה־`reason` (מקור מחייב מסוג `unresolved`)
- "משאלה שלא תילקח בחשבון בקוד", כשמדובר במשאלה מסוג `unresolved`
- "מתרגם…", כשאין עדיין רשומה במטמון

הנתונים מגיעים מ־endpoint לקריאה בלבד, `GET /profile/compiled`, שמחזיר לכל מקור
`{kind, context, text, status, reason, requests}`. התצוגה המלאה ("כך הבנתי את הכלל", עריכה ואישור) היא שלב 3.

**ניקוי.** בכל סבב `scan` ה־worker מריץ גם את `prune_compiled_sources`.

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
9. **זמן יחסי:** "עודד חולה 3 או 4 ימים", מעוגן ל־20.10.2026, יוצר avoid קשיח ל־20–22.10 ו־avoid רך ל־23.10,
   יחד עם `question`. בנייה של 19–25.10 לא משבצת את עודד ב־20–22.
9א. **העיגון לא זז:** קומפילציה מחדש אחרי שינוי ברוסטר (שבוע אחר כך) נותנת אותם תאריכים בדיוק.
9ב. **רשת ביטחון:** `timing: none` עם `dates` לא נשמר. `relative` עם תאריך לפני העיגון או אחרי 90 יום מסומן `unresolved`.
   `absolute` עם תאריך שלא כתוב בטקסט נדחה.
9ג. **פג תוקף:** מקור מחייב שה־`expires_on` שלו עבר לא שולח את הבנייה ל־AI.
10. **`per_source`:** `read_partial` נותן אותה תוצאה כמו לפני הפיצול. הטסטים הקיימים ב־`test_directive_agent.py` עוברים בלי שינוי.
11. **שמירה מכניסה לתור ולא קוראת למודל:** `ProfileService.update` עם כלל חדש לא מבצע
    קריאת מודל, ומכניס משימת `compile_sources` אחת. שתי שמירות רצופות יוצרות משימה אחת.
12. **ה־worker מקמפל את ההגדרה הראשונית:** פרופיל עם כלל, `rest_policy` והערת עובד.
    אחרי `compile_sources` יש 3 רשומות, והבנייה הראשונה רצה עם `compiled_hits == 3` ואפס קריאות תרגום.
13. **בלי מודל:** המשימה מסתיימת בלי רשומות ובלי retry, והבנייה עובדת כמו היום.
14. **אילוץ חוזר מובנה לא נשלח לקומפילציה.**

`tests/test_admin_postgres.py`/Postgres: טסט round-trip ל־repository, בתבנית של הטסטים הקיימים מול Postgres.

`docs/scheduler-comparison`: להוסיף תרחיש של "4 בנייות רצופות עם אותם כללים" ולהציג את `total_tokens` לכל בנייה.

## 9. סדר עבודה (commits)

1. `per_source` מתוך `partial.py`. ריפקטור טהור, הטסטים הקיימים ירוקים.
2. `keys.py` + `shape.py` + `timing.py` (רשת הביטחון של §3.1) + טסטים טהורים.
3. DDL + repository + טסט מול Postgres.
4. `TranslationCache`/`NullCache` + החיבור ב־`DirectiveAgent` (hits, misses, מטמון שלילי).
5. Compile mode בפרומפט ובאימות, כולל `timing` ועיגון (`source_anchors`).
6. העברת המטמון דרך `Scheduler` וכל הקוראים, + metrics.
7. `SourceCompiler`, ה־hook ב־`ProfileService.update` ובאישור העדפה, וענף `compile_sources` ב־worker.
8. `GET /profile/compiled` + תגי סטטוס בהגדרת היחידה (frontend).
9. D32 + עדכוני `CLAUDE.md`.

## 10. שאלות פתוחות

- ~~**זיהוי זמן**~~: הוחלט. המודל מזהה ומעגן ("עודד חולה 3 או 4 ימים"), והקוד בודק (§3.1).
- **`instructions` שחוזרות:** אם מנהל כותב את אותה הנחיה בכל שבוע, האם לשמור גם אותן, לפי hash יחד עם התקופה? לא בשלב 1. נמדוד קודם.
- ~~**prewarm**~~: הוחלט. אילוצי ההגדרה מקומפלים בשמירה (§6.7).
