# מפת המערכת: כל פעולה מרכזית, צעד אחר צעד

המסמך מתאר מה קורה בפועל בכל פעולה מרכזית: מה המשתמש עושה, איזה endpoint נקרא, איזה קוד רץ, האם יש קריאה ל-LLM ומה נכתב ל-DB. בסופו יש המלצות מה להשאיר, מה להסיר ומה לבדוק, ומדריך צעד אחר צעד להסרת רכיב (סעיף 14).

מקרא:
- 🤖 יש קריאה ל-LLM
- ⚙️ קוד דטרמיניסטי בלבד
- 💤 קיים ב-backend אבל ה-UI לא קורא לו

> נכון לענף `restore-llm-engine`. נתיבי הקבצים יחסיים ל-`backend/app/` אלא אם צוין אחרת.

---

## 0. הארכיטקטורה בקצרה

```
דפדפן (Next.js, frontend/)
   │  HTTP + cookie חתום (common/sessions.py)
   ▼
API (FastAPI, main.py) ── routers ב-api/routers/ ── guards ב-api/dependencies.py
   │                     │
   │  שירותים ב-bl/       │  קריאות LLM סינכרוניות: למידה משינויים
   ▼                     ▼
PostgreSQL (dal/repository/) ◄──── Worker (worker.py, בתוך תהליך ה-API או בנפרד)
   ▲                                │  כמה lanes: interactive (צ'אט מנהל)
   │                                │  ו-background (span של יצירה, compile_sources)
   └────────────── jobs ────────────┘
                                    ▼
                       פותר אילוצים OR-Tools CP-SAT (bl/solver/) ── כל השיבוץ
                       שרת מודל OpenAI-compatible (dal/llm/) ── רק תרגום ושיחה
                       תור מודל משותף: Postgres (advisory locks)

PostgreSQL הוא המצב המשותף היחיד (D35):
   טבלת login_attempts ל-throttle · LISTEN/NOTIFY לאירועי SSE · advisory locks לתור המודל
```

- **אין Redis (D35).** ה-throttle, האירועים ותור המודל עוברים דרך Postgres. אם מסד הנתונים לא עונה, ה-throttle והאירועים חוזרים לזיכרון התהליך.
- **תהליכים:** frontend ו-API. ה-worker רץ **בתוך תהליך ה-API כברירת מחדל** (`PAKASH_EMBEDDED_WORKER=0` מכבה), ואפשר להריץ אותו גם בנפרד כ-`python -m app.worker`; ב-`docker-compose.yml` הוא רץ בנפרד. ה-worker מושך jobs מ-Postgres (`FOR UPDATE SKIP LOCKED`) ב-`PAKASH_WORKER_CONCURRENCY` threads (ברירת מחדל 6). `PAKASH_CHAT_WORKERS` מהם (ברירת מחדל 3) שמורים ל-lane `interactive`, שמושך רק `manager_chat`, כך שבנייה ארוכה לא תופסת את כל ה-workers.
- **סוגי jobs:** `manager_chat`, `generation` (job לכל span, כולל ריענון טיוטות אחרי הוספת חייל או משמרת, D37) ו-`compile_sources`. job מסוג `scan` שנשאר מה-copilot מסתיים בלי לעשות כלום.
- **שלוש דרגות מודל** (`dal/llm/model_roles.py`): `advanced` לתרגום ההנחיות של הבנייה (flow `scheduler`), `fast` (לא בשימוש פעיל), ו-`default` לכל השאר (צ'אט המנהל הוא flow `planner`).
- **שום דבר לא יוצא מהשרת חוץ מקריאות לשרת המודל.** ה-tracing ל-Opik (D30) הוסר; הפריסה ברשת סגורה.
- **העיקרון המוביל (D34):** פותר האילוצים משבץ, המודל רק מתרגם שפה חופשית לבקשות מובנות ומנהל את השיחה. ה-audit עדיין לא חוסם אף פעולה.

---

## 1. כניסה והרשאות

### 1.1 כניסת מנהל לצוות ⚙️
1. במסך `Workspace/Login.tsx` נבחר צוות ומוקלדת סיסמה.
2. `POST /api/workspace/login`, דרך `bl/workspace_service.py`.
3. הסיסמה נבדקת מול hash מסוג scrypt (`dal/repository/teams.py`). ניסיונות כושלים מוגבלים ב-`common/throttle.py`: נעילה ל-15 דקות אחרי 5 טעויות, לפי חשבון ולא לפי IP. המונה נשמר בטבלת `login_attempts` ומשותף לכל התהליכים (D35); אם מסד הנתונים לא עונה, הוא בזיכרון התהליך.
4. נשלח cookie חתום ב-HMAC עם `team_id` ו-`role=boss`. כל קריאה אחר כך מקבלת את `team_id` **מה-cookie בלבד**.

### 1.2 כניסת חבר צוות בקישור שיתוף ⚙️
1. המנהל מעתיק קישור (`ShareLink.tsx`) בצורה `/team/{token}`.
2. `POST /api/workspace/member/{token}` מחזיר cookie בתפקיד member, עם קריאה בלבד.
3. המנהל יכול להחליף את הטוקן: `POST /api/workspace/member-link/rotate`.

### 1.3 זיהוי עובד ⚙️
1. בתוך אזור החבר, `IdentityGate.tsx` שולף את רשימת השמות: `GET /api/employee/roster`.
2. בכניסה ראשונה, `POST /api/employee/claim`: העובד בוחר שם וקובע קוד. בכניסות הבאות: `POST /api/employee/login`, או `POST /api/employee/signin` מדלת הכניסה הראשית.
3. ה-cookie מקבל את השדה `employee`, ומעכשיו כל קריאה אישית מוגבלת לשם הזה.

### 1.4 קונסולת מפעיל (`/admin`) ⚙️
- `POST /api/admin/login` עם cookie נפרד.
- פתיחת צוות, השעיה, איפוס סיסמה, החלפת קישור, שחרור זהות עובד ומחיקה, דרך `bl/admin_service.py` ו-`dal/repository/admin.py`. זה המקום היחיד שקורא נתונים חוצי-צוותים.
- 💤 `POST /api/workspace` (פתיחת צוות עצמית) חסום, אלא אם `PAKASH_OPEN_SIGNUP` פעיל.

---

## 2. הגדרת היחידה (פרופיל) ⚙️

1. המנהל ממלא את `ManualSetup/` ו-`RotationSetup.tsx`: עובדים, משמרות ושעותיהן, תקן, תפקידים מורשים לכל משמרת (`allowed_roles`; ריק = כולם), כללים, סבבים ותלתונים. כל שדה תאריך ושעה אפשר גם לבחור (`DateInput`, `TimeInput`) ולא רק להקליד.
2. `PUT /api/profile`, דרך `bl/profile_service/`: ולידציה, נרמול והשלמת ברירות מחדל.
3. הפרופיל נשמר כ-JSON על הצוות (`update_team_profile`).
4. ⚙️ אם השמירה הוסיפה חייל פעיל או משמרת, `generation/absorb.py` פותח job של `range` עם `keep_existing` על כל טיוטה מהיום והלאה (D37): הפותר משבץ את החדש ומזיז רק את מה שצריך כדי לאזן. שבוע מפורסם לא נוגע בו ורק נמנה ב-`absorbed`; טיוטה ריקה מקבלת רק את השורות הריקות של משמרת חדשה. ריענון שלא מצליח להתחיל לא מפיל את השמירה.
5. 🤖 השמירה מכניסה job מסוג `compile_sources` לתור (`compiled_sources.queue`). ה-worker מתרגם ברקע כללים, מדיניות, הערות על עובדים והעדפות, ושומר את התרגום (פירוט ב-4.2.3). גם שמירה או אישור של העדפה מכניסים את אותו job.
6. `ManualSetup/CompiledSources.tsx` קורא ל-`GET /api/profile/compiled` ומציג מה הקוד עשה מכל משפט: `compiled`, `unresolved` או `pending`.
7. `ProfileGapsNotice.tsx` מציג מה עוד חסר, לפי `tools.profile_gaps` ו-`completeness`.

8. מחיקת סוג משמרת: `DELETE /api/profile/shifts/{name}` — הבנייה הבאה כבר לא מייצרת אותה, וסידורים שמורים שומרים את השורות שלהם.

> אין ריאיון פתיחה. הפרופיל נבנה רק בטופס הזה, בלי שום קריאה למודל. שמירה חלה על הבנייה הבאה — חוץ מחייל או משמרת חדשים, שנספגים בטיוטות הקיימות (שלב 4).

---

## 3. קריאת הלוח (Board) ⚙️

1. `Board/useBoard.ts` קורא ל-`GET /api/schedule/overview`, ל-`/at?day=` ול-`/between?start=&end=`.
2. כל תשובה שמכילה סידור עוברת דרך `ScheduleContext.view()` (`bl/schedule_service/context.py`), שמריץ **audit מלא** ומחשב סגירות בכל קריאה.
3. ה-UI מציג משמרות, פס כיסוי (`CoverageBar`) ואזהרות (`Warnings.tsx`).

> **לשים לב לריבוי משתמשים:** ה-audit רץ מחדש בכל קריאת לוח. זה זול ל-LLM, אבל עולה CPU ככל שמספר הצוותים גדל. מועמד ל-cache לפי גרסת הסידור.

---

## 4. בניית סידור

### 4.1 סידור ריק ושיבוץ ידני ⚙️
1. `POST /api/schedule/blank`: `build_slots()` בונה את רשת המשמרות מהפרופיל בחשבון בלבד.
2. גרירת עובד לתא ריק:
   - קודם `POST /api/schedule/check`: `bl/placement/` מחזיר מה השיבוץ יעלה (אזהרות, סגירות, חלופות).
   - אחר כך `POST /api/schedule/assign`, כתיבה מיידית עם `source=manager`.
3. הסרה: `POST /api/schedule/unassign`.

### 4.2 יצירה אוטומטית 🤖 / ⚙️
1. `Board/GenerateDialog.tsx`: המנהל בוחר טווח, מוסיף הנחיות חופשיות, ויכול לצמצם לסוגי משמרות ("כל המשמרות" או "רק <משמרת>", נשלח כ-`shifts`; שאר המשמרות נשארות ונספרות כקבועות) ולבחור "שמירה על השיבוץ הקיים" (`keep_existing`, D37).
2. `POST /api/schedule/generate/start`, דרך `generation/builder.py`: נוצרת טיוטה עם כל הרשת ו-checkpoint ב-JSON. התקופה מחולקת ל-spans של עד 28 ימים (`plan_spans`). **אין עדיין פתרון.**
3. `POST /api/schedule/generate/{id}/run` מכניס לתור **job מסוג `generation` לכל span** (`queue_generation_job`).
4. ה-worker מריץ כל job דרך `runner.run_durable()`, שמריץ span אחד. לכל span, `stepper.generate_next()` קורא ל-`Scheduler.generate_span()`:
   - אם יש קלט בשפה חופשית (הנחיה, כללים, מדיניות, הערות, העדפות), `bl/directive_agent/` מתרגם אותו לבקשות מובנות (4.2.1). קלט מובנה לא צורך שום קריאה למודל.
   - פותר האילוצים (`bl/solver/`, 4.2.2) משבץ את כל ה-span בפתרון אחד.
   - audit ו-checkpoint של אותם תאריכים בלבד.
5. הדפדפן דוגם `GET /api/schedule/{id}/progress` (מונה ימים ו-heartbeat).
6. עצירה: `/generate/{id}/cancel`, וה-worker עוצר בסוף ה-span הנוכחי. כל מה שהסתיים נשמר. הסתרת הבאנר: `/dismiss`. יום בודד: `/day/start`. טווח בתוך טיוטה: `/range/start` (שיבוצים ידניים נשמרים כ-pins; עם `keep_existing` גם השיבוץ שנבנה נשאר איפה שהוא מתאים, `solver/stability.py`).
7. span שנכשל מנוסה שוב מספר מוגבל של פעמים, ולא מפיל את כל התקופה.
8. `POST /generate` פותר תקופה שלמה בתוך הבקשה ושומר טיוטה (ה-UI משתמש במסלול ה-job). 💤 `/generate/{id}/next` מריץ span אחד בסנכרון, ולא נקרא מה-UI.

#### 4.2.1 תרגום ההנחיות 🤖 (`bl/directive_agent/`)
1. `semantic_sources()` (`bl/scheduler/directives.py`) אוסף כל קלט שהקוד לא יודע לקרוא: ההנחיה החופשית, העדפות, כללים ומדיניות טקסטואלית. לכל מקור יש `binding`: רק כלל שסומן soft והעדפה אינם מחייבים. כל השאר, כולל ההנחיה החופשית, מחייב. כל מקור חוץ מההנחיה של הבנייה עצמה מסומן `persistent` ומקבל `key` לפי התוכן.
2. מקורות קבועים שכבר תורגמו נטענים מה-cache (4.2.3), ורק השאר נשלחים למודל. מקור שנשמר כ-`unresolved` מדווח בלי שום קריאה.
3. `DirectiveAgent.translate()` מריץ לולאת כלים חסומה: עד `MAX_TURNS=4` קריאות למודל עם `scheduler_directives.md`, עד 4 כלים בכל קריאה, ועד 2 הרצות `dry_run` בסך הכול.
4. הכלים (`directive_agent/tools.py`) הם Python טהור בלי repository: `resolve_employee`, `list_slots`, `employee_state`, `check` ו-`dry_run` (פתרון קצר של פותר האילוצים בזיכרון). שום דבר לא נכתב.
5. כל פריט בתשובה הסופית נבדק בקוד (`directive_agent/partial.py`: `per_source`, מול הרוסטר, המשמרות והרשת). אם הקוד דחה אותה ונשארו סבבים, היא חוזרת למודל עם הסיבות. מקור שהמודל סימן `unresolved` מסיים את הלולאה מיד.
6. אם התרגום לא מלא, `directive_agent/partial.py` שומר כל מקור שכל הפריטים שלו עברו, ומשמיט מקור שלם (אף פעם לא חצי מקור):
   - הפותר בונה בלי המקורות שהושמטו, וכל אחד נרשם ב-`notes`: הנחיה מחייבת כ"הנחיה מחייבת לא נאכפה בשיבוץ", ומשאלה רכה כ"בקשה רכה לא נלקחה בחשבון בשיבוץ". אין מסלול AI מלא (D34).
   - גם מודל שלא עונה לא מפיל את הבנייה: כל המקורות שלא תורגמו מדווחים באותה צורה.
   - ב-metrics נרשמים `model_calls`, `translation_steps`, `unresolved_sources`, `compiled_hits` ו-`tokens_saved`.

#### 4.2.2 פותר האילוצים ⚙️ (`bl/solver/`, D34)
- OR-Tools CP-SAT פותר span שלם בבת אחת: משתנה בוליאני לכל זוג חוקי של עובד ומשמרת. שיבוץ שסותר אי-זמינות קשיחה, סבב או סגירה, כשירות, `allowed_roles` של המשמרת או `avoid` קשיח לא נהיה משתנה בכלל (`problem.py`). חמשושים/שושים בלי קבוצה בבית בכל סוף שבוע (חמישי, או שישי בשושים, עד החילוף של ראשון).
- נחפפים (`service_type` overlap) מקבלים משתנים אבל לא תופסים תקן: רק לצד חונך (`trainers` שלהם, אחרת מי ש-`can_train`, אחרת כל מי שנספר), לא יותר נחפפים מאנשים נספרים במשמרת, ועד חלק רגיל או `shadow_shifts_per_week` של מדיניות החפיפה.
- אילוצים קשיחים (`rules.py`): תקן המשמרת, מנוחה מינימלית, ימים רצופים ותקרת שעות שבועית, לפי אותם ספים של ה-audit (`policy()`), כולל עד 14 ימי היסטוריה ושאר הטיוטה.
- בקשות מובנות (`requests.py`, מ-`bl/schedule_requests.py`): בקשה קשיחה היא אילוץ, רכה היא מחיר במטרה, ו-`prefer` הוא פרס. גם זמינות רכה מתומחרת.
- פתרון בשני שלבים (`solve.py`): קודם כיסוי (משמרות לא מאוישות, תפקידים חסרים, אחמ"ש), ואז, בלי לוותר על הכיסוי, משאלות, סוגרים בסגירה שלהם, איזון שעות ולילות, ויום חופש בין משמרות (`fairness.py`). בנייה ששומרת לוח מתחילה את השלב הראשון מהלוח הזה.
- איזון: יעד לכל אדם ב-water-filling (הביקוש מחולק שווה, לא מתחת למה שכבר יש לו ולא מעל מה שהוא יכול). המרחק מהיעד והעומס הגבוה ביותר מתומחרים לכל יחידת עומס, בלי תלות בגודל הצוות, כך שמשמרת אחת של איזון זולה ממשאלה רכה.
- כל שורה מקבלת סיבה (D8). משמרת שאי אפשר לאייש מדווחת ב-`notes` וכאזהרה, ולא נחסמת. מגבלת הזמן והמעבדים הן הגדרות (`solver_time_limit_seconds`, `solver_workers`).

#### 4.2.3 תרגום קבוע ונשמר 🤖 (`bl/compiled_sources/`, D32)
- כלל, מדיניות, הערה על עובד או העדפה אומרים אותו דבר בשבוע הבא כמו השבוע, ולכן התרגום שלהם נשמר בטבלה (`dal/repository/compiled_sources.py`). המפתח הוא המילים, הרוסטר ושמות המשמרות, וגרסת ה-compiler (`keys.py`).
- `SourceCompiler` רץ ב-worker אחרי שמירת הפרופיל או העדפה, ומפעיל את `DirectiveAgent` ב-`mode: "compile"`. במצב הזה התרגום אסור שיהיה תלוי בתקופה (ימי שבוע ולא תאריכים של השבוע הזה), כך שהבנייה הראשונה כבר לא משלמת עליו.
- זמן יחסי ("חולה 3 או 4 ימים") נספר מהיום שבו המשפט נראה לראשונה, ו-`timing.py` בודק את התאריכים של המודל לפני שמירה.
- `shape.py` בודק כל שורה שמורה מחדש מול הרוסטר של היום. התרגום הוא נגזרת שנשמרת, והוא אף פעם לא מחליף את המשפט של המנהל (D2).

### 4.3 ייצוא ⚙️
`GET /api/schedule/export/{id}` מריץ את `bl/export.py` ומחזיר xlsx בפריסת Sample A.

---

## 5. שינוי סידור קיים

### 5.1 גרירת משמרת ממקום למקום ⚙️
1. גרירה בלוח פותחת את `ConfirmDrop.tsx`, וחובה להזין סיבה (D12).
2. `POST /api/schedule/move`, דרך `ChangeService.move()`, מזיז את השיבוץ.
3. נרשמת שורה ביומן השינויים (append-only) עם הסיבה.

### 5.2 צ'אט המנהל עם הסוכן 🤖 (הפיצ'ר המרכזי)
1. `Management/AgentChat.tsx` שולח `POST /api/agent/chats/{id}/messages`.
2. `ManagerChatService.start_turn()`:
   - אם ההודעה היא אישור תוכנית ("מאשר"), היא מופעלת מיד ואין קריאה למודל.
   - אחרת נשמרת הודעה בסטטוס `working` ונכנס job מסוג `manager_chat` לתור.
3. ה-worker מריץ את `ManagerChatService.reply()`. `bl/manager_chat.py` הוא facade, והעבודה עצמה מתבצעת ב-`bl/chat_reply.py`:
   1. טוען את הסידור, הפרופיל, האילוצים מהשבוע האחרון ואילך, ההעדפות, 12 שינויים אחרונים ועד 32 הודעות שיחה.
   2. **מסלולים מהירים, בלי מודל:** היעדרות ("X חולה בשני ושלישי", "X חולה עד 31.12") נקראת ומתוכננת ב-`bl/absence/` עוד בתוך `start_turn`, כך שתשובת השליחה כבר מכילה את התוכנית (D36). "עד X" לבד מתחיל מהיום; עד 120 יום. `ChatTools.replacement_lookup` (`bl/chat_tools.py`) עונה על "מי יכול להחליף".
   3. אחרת יש עד **7 סבבים** של `complete_json(manager_chat.md)`, ב-streaming: התשובה נשמרת על ההודעה תוך כדי כתיבה ואות "chat" ב-SSE גורם לדפדפן לקרוא מיד. ה-payload מסודר מהאיטי-להשתנות למהיר (פרופיל, סידור … שיחה, בקשה) והשעון בסוף, כדי שה-prefix יישמר ב-cache של השרת. בכל סבב המודל מבקש עד 4 כלים (`_MAX_CALLS`) מ-`bl/tools/` ומ-`bl/chat_tools.py` (קריאה בלבד), והתוצאות נוספות לסבב הבא.
   4. כשהמודל מחזיר תוכנית, `bl/chat_planner.py` (`prepare`) מאמת ומריץ audit. התוכנית יכולה להיות שינויים (מושב שהסרה מפנה ממולא על ידי הפותר, `chat_vacancies.py`: שאר השורות pins, מי שיצא `avoid` קשיח, ורק השיבוצים למושבים שהתפנו נכנסים לתוכנית; `leave_vacant` משאיר ריק), יצירה (`chat_generation.py`: פותר האילוצים רץ **בתוך** התור, עם cache התרגומים והגדרות הפותר השמורות), שינוי מבנה משמרות (`chat_lifecycle.py`: הפותר בונה מחדש ושומר כל שיבוץ קיים שעדיין מתאים), ניהול בקשות או אילוצים (`chat_constraints.py`: עד 126 בתוכנית; דחייה מציינת את השורה, הערך והאפשרויות התקינות כדי שהמודל יתקן שורה אחת).
   5. אם יש אזהרות, התוכנית חוזרת למודל לבדיקה פעם אחת. אם הקוד דחה אותה, יש עד 2 תיקונים.
   6. בסוף ההודעה נשמרת עם התוכנית בסטטוס `pending`.
4. הדפדפן דוגם את השיחה (`useManagerChat.ts`) ומציג את השלבים בזמן אמת. עצירה: `/stop`. עריכת הודעה מחליפה אותה ואת מה שאחריה; "ענה שוב" הוא `POST /{id}/regenerate`. אף אחד מהם לא מבטל תוכנית שכבר הופעלה.
5. המנהל מאשר: `POST /api/agent/chats/{id}/messages/{mid}/apply`.
   - הקוד ב-`bl/chat_apply.py`: נעילת שורה (`chat_approval`), ובדיקה שה-fingerprint של המצב לא השתנה מאז ההצעה.
   - הפעלה דרך `OperationApplier`, `create_blank`, `apply_management` ועדכון הפרופיל, ורישום ביומן.
6. דחייה: `/dismiss`.

### 5.3 מסלולים ישנים לשינוי ולשאלות 💤
| Endpoint | מה עושה | LLM |
|---|---|---|
| `POST /api/schedule/propose` | `ChangeAgent`: הצעת שינוי מטקסט | 🤖 1 |
| `POST /api/schedule/apply` | הפעלת הצעה שאושרה | ⚙️ |

אלה הוחלפו בפועל בצ'אט המנהל, וה-UI לא קורא להם (הפונקציות שלהם כבר הוסרו מ-`services/api.ts`). `/ask`, `/brief`, `/simulate` ו-`/tool` כבר הוסרו (סעיף 14).

### 5.4 לשונית "שינויים" ⚙️
`Management/ChangesPanel.tsx`, שלוש פעולות:
- **החלפת משמרת** (`ReplacementPanel.tsx`): מי חסר ומתי ← `GET /api/agent/replacements` (קריאה בלבד) מחזיר מחליפים מדורגים כך שהעומס מתפזר. הבחירות נשלחות לצ'אט כתוכנית שממתינה לאישור (D36).
- **הוספת חייל** / **הוספת משמרת**: אותם טפסים של הגדרת היחידה, נשמרים ב-`PUT /api/profile`, ואז החדש נספג בטיוטות (סעיף 2, D37). הוספת משמרת שואלת מי יכול לעמוד בה (ברירת מחדל: כולם).

### 5.5 ניקוי, מחיקה, פרסום ⚙️
- `POST /{id}/publish` / `unpublish`: מעבר בין draft ל-published ורישום ביומן. חברי צוות רואים רק סידורים מפורסמים.
- `POST /{id}/clear`: מרוקן יום או תקופה ומשאיר את הרשת. כל שורה שהוסרה נרשמת.
- `DELETE /{id}`: מחיקת התקופה.

### 5.6 עזיבת עובד ⚙️
`ConfirmDeparture.tsx` קורא ל-`POST /departure/preview` (מה ייפגע, בלי לכתוב) ואחר כך ל-`POST /departure`: העובד מסומן `inactive_from` ונשאר בפרופיל בשביל ההיסטוריה. כל המשמרות שלו מהתאריך הזה והלאה מתפנות, וכל אחת נרשמת ביומן. סידור מפורסם שאיבד משמרת חוזר לטיוטה.

---

## 6. אילוצים, העדפות ויומן

| פעולה | Endpoint | מה קורה | LLM |
|---|---|---|---|
| אילוץ ידני של המנהל | `POST /constraints`, `DELETE /constraints/{id}` | שורת `availability` | ⚙️ |
| העדפות הסוכן | `/preferences` (list, create, patch, delete) | `Preferences.tsx`. הצעה של הסוכן נכנסת כ-`suggested` ולא פעילה עד אישור | ⚙️ |
| למידה משינויים | `GET /history/learn` | `LearnedFromChanges.tsx`: ספירת תיקונים חוזרים, ואז ניסוח כללים | 🤖 1 |
| היסטוריה | `History.tsx` | יומן השינויים | ⚙️ |
| 💤 | `GET /constraints/list`, `GET /history/list` | לא נקראים מה-UI | ⚙️ |

---

## 7. אזור העובד

### 7.1 התצוגה האישית ⚙️
- `GET /api/employee/me`: המשמרות של העובד, שעות (`audit.personal_summary`) ומה השתנה מאז האישור האחרון.
- `POST /api/employee/acknowledge` מסמן "ראיתי".

### 7.2 בקשת אילוץ: עובד ← מנהל ⚙️
1. העובד שולח ב-`ConstraintForm.tsx`: `POST /api/employee/requests`.
2. הבקשה נשמרת ב-`constraint_requests`, **לא** ב-`availability`, ולכן ה-audit לא רואה אותה.
3. `events.publish(team, "requests")` מעיר את ה-SSE של המנהל (`GET /api/schedule/requests/events`). האות יוצא ב-`pg_notify` (`dal/notify.py`), ו-listener אחד בכל תהליך מעביר אותו ל-streams המקומיים, כך שמנהל מחובר לכל worker מקבל אותו (D35). בכל מקרה יש polling כל 15 שניות כגיבוי.
4. המנהל ב-`RequestInbox.tsx` מאשר (`POST /api/schedule/requests/{id}/approve`), ואז נוצרת שורת `availability` עם `source=employee_reported`. דחייה: `/reject`.
5. העובד יכול למשוך את הבקשה: `/requests/{id}/withdraw`.

### 7.3 החלפת משמרות: עובד ← עמית ← מנהל ⚙️
1. `SwapPanel.tsx` שולח `POST /api/employee/swaps` (רק משמרות מסידור מפורסם).
2. העמית עונה: `POST /api/employee/swaps/{id}/answer`.
3. המנהל ב-`SwapInbox.tsx` מאשר עם סיבה (`/api/schedule/swaps/{id}/approve`), וזה מפעיל את `schedule_service.apply` עם `OP_SWAP` ונרשם ביומן.

---

## 8. סטטיסטיקות ⚙️
`Stats.tsx` קורא ל-`GET /api/schedule/stats?...`, דרך `audit.shift_stats` על כל טווח: שעות, משמרות, לילות והוגנות.

---

## 9. Copilot — הוסר
התיבה "הסוכן שם לב", הסריקות, ההרשאות וה-audit הוסרו. אישור ו-rollback לא ביצעו כלום, ומה שהן מצאו כבר מופיע בלוח ובצ'אט. התור (`copilot_jobs`) נשאר: הוא מריץ בניות, תורות צ'אט ותרגומים. job מסוג `scan` שנשאר בבסיס נתונים קיים מסתיים בלי לעשות כלום.

---

## 10. הגדרות מערכת ואבחון ⚙️
- ההגדרות נערכות רק מהלשונית "מערכת" בקונסולת המפעיל (`Admin/SystemView.tsx` ← `Settings/`), על ה-session של המפעיל. במסך הצוות אין כניסה להגדרות. ה-API עדיין מקבל גם session של מנהל עם סיסמת ההגדרות בכותרת `X-Settings-Password`. קורא ל-`GET` ו-`PUT /api/settings`.
- ההגדרות נשמרות **בקובץ JSON אחד גלובלי** (`runtime-settings.json`): מודלים לכל role, URL ומפתח, timeout, `llm_reasoning_effort` (כמה המודל חושב: off/low/medium/high), אימות SSL (`llm_verify_ssl`), מקביליות (`llm_max_concurrency`, `llm_team_concurrency`), מגבלות פותר האילוצים, ו-diet mode. כל תהליך קולט שמירה של תהליך אחר תוך כמה שניות.
- `GET` ו-`POST /api/models`: בדיקת שרת מודלים ורשימת המודלים שלו. הבדיקה מקבלת גם `llm_verify_ssl` שלא נשמר עדיין, כדי לבדוק שרת פנימי עם תעודה בחתימה עצמית לפני השמירה.
- `llm_verify_ssl` דלוק כברירת מחדל. כיבוי שלו חושף את החיבור, כולל מפתח ה-API, ליירוט, ולכן הוא מיועד רק לשרת פנימי.
- `llm_max_concurrency` נאכף על ה-API וה-workers יחד, ונקרא מחדש בכל רכישת slot. צוות יכול להחזיק את כל ה-slots אלא אם `llm_team_concurrency` מגביל (פירוט בסעיף 11).
- `llm_timeout_seconds` של 0 הוא תקרה מובנית (300 שניות, ובתרגום של בנייה 900), לא "בלי גבול": קריאה תקועה נכשלת ומשחררת את ה-slot, ו-read timeout לא מנוסה שוב (D38).
- `solver_time_limit_seconds` (ברירת מחדל 10) ו-`solver_workers` (ברירת מחדל 8) נקראים בכל בנייה. הפותר מחזיר את הפתרון הטוב ביותר שמצא עד הגבול; ב-metrics של כל span נרשם `solver_status` (`optimal` או `feasible`).
- `python -m app.diagnose` מדפיס את ההגדרות שהתהליך רואה, את תור ה-jobs, את ה-advisory locks של תור המודל, בדיקת חיבור לשרת המודל וקריאה אמיתית אחת.

---

## 11. מפת ה-LLM המלאה

כל הקריאות עוברות דרך `dal/llm/openai_client.py`: `complete_json`. מעליו יש סולם fallback (strict schema, schema, json mode, plain, merged system), retry, הגבלת מקביליות משותפת ולוג טוקנים. השלב הראשון מבקש structured output ב-`strict: true` כשהסכמה ניתנת לכך (`dal/llm/strict_schema.py`).

**תור המודל** (`dal/llm/budgets.py`, `slots_for`):
1. `PostgresModelSlots` (advisory locks) בכל פריסה עם מסד נתונים.
2. `ModelSlots` בזיכרון, כשאין database (בעיקר בטסטים).

שניהם שומרים על אותו חוזה: גבול אחד לכל ה-deployment מתוך `llm_max_concurrency` (ברירת מחדל 4; ל-Ollama מקומי להוריד ל-1), ו-`llm_team_concurrency` לכל צוות (0 = כל ה-slots, D38).

| זרימה | פעולה ב-UI | role | prompt | קריאות | איפה רץ |
|---|---|---|---|---|---|
| צ'אט מנהל (`bl/chat_reply.py`, flow `planner`) | AgentChat | default | `manager_chat.md` (כ-21K תווים) | 1–7 לכל הודעה, ועוד יצירה פנימית | worker |
| יצירה | GenerateDialog / צ'אט | – | – | 0 (פותר אילוצים) | worker |
| תרגום הנחיות (`bl/directive_agent/`) | GenerateDialog / צ'אט | advanced | `scheduler_directives.md` | 1–4 לכל span (לולאת כלים), רק למקורות שלא ב-cache | worker |
| תרגום קבוע (`bl/compiled_sources/`) | שמירת פרופיל או העדפה | advanced | `scheduler_directives.md` (`mode: compile`) | 1–4 לכל שמירה | worker |
| למידה משינויים | LearnedFromChanges | default | `learn_changes.md` | 1 | API |
| 💤 propose | – | default | `changes.md` | 1 | API |

### איך להוזיל (לפי סדר השפעה)
1. **למדוד:** הטוקנים נשמרים היום רק בלוג `pakash.llm` וב-`_usage` של הודעת הצ'אט. צריך טבלת `llm_usage(team_id, flow, model, tokens, rounds, ts)`.
2. **צ'אט מנהל:**
   - ✅ רשימת `tools` הסטטית ב-system prompt, והשעון וה-payload מסודרים כך שה-prefix נשמר ב-cache בין תורות.
   - לשלוח רק את השבוע הנראה במקום את כל הסידור.
   - ✅ היעדרות ("X חולה בשני ושלישי", "X טס לחו״ל", "X לא יכולה לעבוד בשישי") נקראת ומתוכננת בקוד ב-`bl/absence/`, בתוך הבקשה עצמה, בלי סבב מודל (D36).
   - ✅ `llm_reasoning_effort` מקצר את זמן החשיבה של gpt-oss ו-Qwen3.
   - למדוד את `model_rounds` ולשקול להוריד את `_ROUNDS`, שעומד כרגע על 7.
   - שאלות קריאה בלבד להריץ על role `fast`.
3. **יצירה:** השיבוץ עצמו לא עולה טוקנים (D34). מקורות קבועים כבר נשמרים (4.2.3), אבל ההנחיה החופשית של הבנייה עדיין מתורגמת מחדש בכל span, עד 4 קריאות כל פעם. למדוד את `translation_steps`, `compiled_hits` ו-`tokens_saved`, ולשקול להוריד את `MAX_TURNS`.

---

## 12. מה חוסם ריבוי משתמשים

| בעיה | איפה | השפעה | כיוון פתרון |
|---|---|---|---|
| הגדרות גלובליות בקובץ | `common/runtime_settings/` | כל הצוותים על אותו מודל ואותן מגבלות פותר. תהליכים אחרים קוראים את הקובץ מחדש כל כמה שניות, אבל זה עובד רק כשהם חולקים volume | להעביר את הגדרות המודל והפותר ל-DB (פרטי החיבור למסד עצמו חייבים להישאר מחוצה לו) |
| אין תקציב LLM לכל צוות | – | אפשר להגביל קריאות במקביל לצוות (`llm_team_concurrency`, כברירת מחדל לא מוגבל), אבל אין מכסת טוקנים, וצוות אחד יכול לצרוך הרבה | מונה ומכסה לכל צוות |
| audit מלא בכל קריאת לוח | `context.view()` | CPU שגדל עם המשתמשים | cache לפי גרסת הסידור |
| `PAKASH_SESSION_SECRET` ריק כברירת מחדל ב-compose | `docker-compose.yml` | ה-sessions לא תקפים בין תהליכים | חובה להגדיר |

נפתר: יצירה מחולקת ל-job לכל span; ה-worker מפעיל כמה lanes ושומר lane לצ'אט;
מכסת המודל משותפת לכל התהליכים (advisory locks של Postgres) עם quota אופציונלית לצוות; קריאה תקועה נכשלת ומשחררת את ה-slot (D38);
ה-throttle והאירועים של SSE משותפים דרך Postgres (D35).

---

## 13. סיכום: להשאיר, להסיר, לבדוק

### להשאיר (הליבה, בשימוש)
כניסה והרשאות · פרופיל · לוח ושיבוץ ידני · יצירה (start, run, progress, cancel, range) · צ'אט מנהל · גרירה עם סיבה · פרסום, ניקוי ומחיקה · ייצוא · עזיבת עובד · אילוצים והעדפות · אזור עובד (me, בקשות, החלפות) · סטטיסטיקות · הגדרות · קונסולת מפעיל.

### מועמדים להסרה (💤 לא נקראים מה-UI)
| Backend | Frontend (`services/api.ts`) | קוד שאולי מת איתם |
|---|---|---|
| `POST /schedule/propose` | – (כבר הוסר) | המחלקה `ChangeAgent`, `prompts/changes.md` (שאר `changes/` בשימוש הצ'אט) |
| `POST /schedule/apply` | – (כבר הוסר) | החלפות עדיין משתמשות ב-`schedule_service.apply`, אז להסיר רק את ה-route |
| `/generate/{id}/next` | – (כבר הוסר) | – (הטסטים משתמשים בו כדי לפתור span בסנכרון) |
| `GET /constraints/list`, `/history/list`, `/current` | – | – |
| `GET /api/schedule/requests`, `/identities`, `/identities/release`, `GET /api/schedule/swaps` | – | לבדוק אם נחוצים לאינטגרציה חיצונית |
| `GET /api/employee/swaps/incoming` | – | – |

Briefing, Ask, Simulate ו-Tool כבר הוסרו, וגם `Scheduler.generate()` הישן ו-`ChunkedRun`, ה-copilot, צ'אט העוזר של העובד ו-tracing ל-Opik. הפירוט המלא, כולל מה חייב להישאר ואילו טסטים מושפעים, נמצא בסעיף 14.

### לבדוק או לפשט
- **ה-worker:** כבר מפוצל ל-lanes ול-job לכל span, ו-SSE ו-throttle משותפים דרך Postgres. ההגדרות עדיין בקובץ, ותהליך שלא חולק את ה-volume לא יראה שמירה מהקונסולה.

---

## 14. איך מסירים רכיב לא חשוב

### הסדר הכללי (לכל רכיב)
1. **לוודא שה-UI לא קורא לו:** לחפש את שם הפונקציה ב-`frontend/src/` (למשל `grep -rn scheduleAt frontend/src`). אם היא מוגדרת ב-`services/api.ts` ולא מופיעה בשום מקום אחר, היא מתה.
2. **להסיר מה-frontend:** את הפונקציה מ-`services/api.ts`, ואת ה-types שרק היא השתמשה בהם מ-`types.ts`.
3. **להסיר את ה-route** מ-`api/routers/...`, ואת ה-contract מ-`api/contracts/...` אם אף route אחר לא משתמש בו.
4. **להסיר את המתודה מה-facade:** `bl/schedule_service/service.py` מעביר כל route למחלקה קטנה (`changing.py`, `answering.py` שמחזיק היום רק את `Simulator`, `speaking.py` שמחזיק רק את הייצוא). מסירים את המתודה, ואת המחלקה עצמה אם היא נשארת ריקה.
5. **לחפש מי עוד מייבא את המודול** לפני שמוחקים קובץ: `grep -rn "from app.bl.<module>" backend/`. הטבלה למטה מסכמת מה נמצא היום.
6. **טסטים:** למחוק טסטים שבודקים רק את הרכיב שהוסר. טסט שבודק התנהגות שהצ'אט עדיין משתמש בה מעבירים לנתיב החדש ולא מוחקים.
7. **prompts:** למחוק את קובץ ה-`.md` מ-`bl/prompts/` ואת הטסט שלו ב-`tests/test_prompts.py`.
8. **להריץ בדיקות:** `cd backend && python -m pytest -q`, ובצד הלקוח `cd frontend && npx tsc --noEmit && npm run lint && npm test`.
9. **תיעוד:** לעדכן את `backend/CLAUDE.md`, את `backend/app/bl/CLAUDE.md` ואת המסמך הזה.
10. **commit אחד לכל רכיב**, כדי שיהיה קל לבטל אם משהו נשבר.

### מה מוחקים ומה חייב להישאר, לכל מועמד
| רכיב | מה מוחקים | מה **חייב להישאר** (ומי משתמש בו) | טסטים שמושפעים |
|---|---|---|---|
| **Propose / apply** (`/schedule/propose`, `/schedule/apply`) | שני ה-routes, `ChangeService.propose`, `prompts/changes.md` והמחלקה `ChangeAgent` | `changes/proposal.py`, `schema.py`, `values.py`, `targets.py`, `questions.py`, `profile_ops.py` והקבועים `OP_*` (הצ'אט, ההחלפות, `simulate`). `chat_state.py` מייבא את `_closures_for_model` ו-`_schedule_for_model` מ-`changes/agent.py`, אז קודם מעבירים אותן ל-`changes/values.py`, ורק אחר כך מוחקים את `agent.py`. `ChangeService.apply` נשאר, כי אישור החלפה משתמש בו | `test_change_operations.py`, `test_clarification.py`, ומבחני ה-change agent ב-`test_scheduler.py` (החלק "the change agent") |
| **Reads לא בשימוש** (`/constraints/list`, `/history/list`, `/current`, `/requests`, `/identities`, `/swaps`, `/employee/swaps/incoming`) | רק ה-routes | מתודות ה-repository, אם routes אחרים קוראים להן | לבדוק את `test_schedule_api.py`, `test_employee_api.py` ו-`test_swap_api.py` |

### סדר מומלץ
Briefing, Ask, Simulate / tool ו-`Scheduler.generate` כבר הוסרו. נשאר:
1. **Propose:** קודם מעבירים את `_closures_for_model` ו-`_schedule_for_model` מ-`changes/agent.py` ל-`changes/values.py`, ואז מוחקים. מבחני שערי הסיבה (`test_clarification.py`, `test_scheduler.py`) עוברים לבדוק את `changes/proposal.py` ישירות.
2. **Reads לא בשימוש**, לפי הצורך.
