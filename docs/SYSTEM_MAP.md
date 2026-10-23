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
   │  שירותים ב-bl/       │  קריאות LLM סינכרוניות: עוזר עובד, למידה משינויים
   ▼                     ▼
PostgreSQL (dal/repository/) ◄──── Worker (worker.py, תהליך נפרד)
   ▲                                │  כמה lanes: interactive (צ'אט מנהל)
   │                                │  ו-background (span של יצירה, scan, compile_sources)
   └────────────── jobs ────────────┘
                                    ▼
                       שרת מודל OpenAI-compatible (dal/llm/)
                       תור מודל משותף: Redis אם מוגדר, אחרת Postgres (advisory locks)

Redis (אופציונלי, common/redis_hub.py) ◄── API ו-worker
   throttle של כניסות · pub/sub לאירועי SSE · תור המודל
```

- **Redis אופציונלי (D33).** אם לא הוגדר URL, או ש-Redis לא זמין, כל רכיב חוזר להתנהגות שהייתה לו בלעדיו: throttle ואירועים בזיכרון התהליך, ותור המודל ב-Postgres. `RedisHub.client()` מחזיר `None` במצב כזה, ו-`failed()` גורם לכולם לחכות כמה שניות לפני ניסיון חוזר.
- **שלושה תהליכים:** frontend, API ו-worker. ה-worker מושך jobs מ-Postgres (`FOR UPDATE SKIP LOCKED`) ב-`PAKASH_WORKER_CONCURRENCY` threads (ברירת מחדל 4). `PAKASH_CHAT_WORKERS` מהם (ברירת מחדל 1) שמורים ל-lane `interactive`, שמושך רק `manager_chat`, כך שבנייה ארוכה לא תופסת את כל ה-workers.
- **סוגי jobs:** `manager_chat`, `generation` (job לכל span), `scan` ו-`compile_sources`.
- **שלוש דרגות מודל** (`dal/llm/model_roles.py`): `advanced` ליצירת סידור, `fast` ל-briefing, ו-`default` לכל השאר.
- **העיקרון המוביל (D3):** המודל מחליט, והקוד סופר ובודק. ה-audit לא חוסם אף פעולה.

---

## 1. כניסה והרשאות

### 1.1 כניסת מנהל לצוות ⚙️
1. במסך `Workspace/Login.tsx` נבחר צוות ומוקלדת סיסמה.
2. `POST /api/workspace/login`, דרך `bl/workspace_service.py`.
3. הסיסמה נבדקת מול hash מסוג scrypt (`dal/repository/teams.py`). ניסיונות כושלים מוגבלים ב-`common/throttle.py`: נעילה ל-15 דקות אחרי 5 טעויות, לפי חשבון ולא לפי IP. עם Redis המונה משותף לכל התהליכים, ובלעדיו הוא בזיכרון של כל תהליך בנפרד.
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

1. המנהל ממלא את `ManualSetup/` ו-`RotationSetup.tsx`: עובדים, משמרות ושעותיהן, תקן, כללים, סבבים ותלתונים.
2. `PUT /api/profile`, דרך `bl/profile_service/`: ולידציה, נרמול והשלמת ברירות מחדל.
3. הפרופיל נשמר כ-JSON על הצוות (`update_team_profile`).
4. 🤖 השמירה מכניסה job מסוג `compile_sources` לתור (`compiled_sources.queue`). ה-worker מתרגם ברקע כללים, מדיניות, הערות על עובדים והעדפות, ושומר את התרגום (פירוט ב-4.2.3). גם שמירה או אישור של העדפה מכניסים את אותו job.
5. `ManualSetup/CompiledSources.tsx` קורא ל-`GET /api/profile/compiled` ומציג מה הקוד עשה מכל משפט: `compiled`, `unresolved` או `pending`.
6. `ProfileGapsNotice.tsx` מציג מה עוד חסר, לפי `tools.profile_gaps` ו-`completeness`.

> ה-CLAUDE.md מזכיר ריאיון פתיחה (`bl/interview/`), **אבל התיקייה לא קיימת בקוד.** הפרופיל נבנה רק בטופס הידני, וכדאי לעדכן את התיעוד.

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
1. `Board/GenerateDialog.tsx`: המנהל בוחר טווח ומוסיף הנחיות חופשיות.
2. `POST /api/schedule/generate/start`, דרך `generation/builder.py`: נוצרת טיוטה עם כל הרשת ו-checkpoint ב-JSON. **אין עדיין קריאה למודל.**
3. `POST /api/schedule/generate/{id}/run` מכניס לתור **job מסוג `generation` לכל span** (`queue_generation_job`).
4. ה-worker מריץ כל job דרך `runner.run_durable()`, שמריץ span אחד בלבד. אחרי כל checkpoint התור מתעדכן, כי פיצול אדפטיבי יכול ליצור spans חדשים. לכל span:
   - `stepper.generate_next()` קורא ל-`Scheduler.generate_span()`, ומשם לפי `schedule_generation_engine`:
     - `code`: `deterministic_scheduler/`, אפס טוקנים.
     - `auto` (ברירת מחדל): אם הקלט מובנה, הקוד משבץ. אם יש הנחיות חופשיות, `bl/directive_agent/` מתרגם אותן ואז הקוד משבץ. אם התוצאה לא נקייה, עוברים למסלול ה-AI. פירוט התרגום ב-4.2.1.
     - `ai`: קריאה לכל יום או לכל שבוע (`schedule_generation_mode`) עם `scheduler.md`, ועוד קריאת תיקון אחת לכל היותר.
   - כל שורה עוברת בדיקת גבולות (מי זמין, סבב), ואז audit ו-checkpoint של אותם תאריכים בלבד.
5. הדפדפן דוגם `GET /api/schedule/{id}/progress` (מונה ימים ו-heartbeat).
6. עצירה: `/generate/{id}/cancel`, וה-worker עוצר בסוף ה-span הנוכחי. כל מה שהסתיים נשמר. הסתרת הבאנר: `/dismiss`. יום בודד: `/day/start`. טווח בתוך טיוטה: `/range/start` (שיבוצים ידניים נשמרים כ-pins).
7. span שנכשל מנוסה שוב מספר מוגבל של פעמים, ולא מפיל את כל התקופה.
8. 💤 `/generate` (המסלול הישן, בחלקים) ו-`/generate/{id}/next` לא נקראים מה-UI.

#### 4.2.1 תרגום ההנחיות במצב `auto` 🤖 (`bl/directive_agent/`)
1. `semantic_sources()` (`bl/scheduler/directives.py`) אוסף כל קלט שהקוד לא יודע לקרוא: ההנחיה החופשית, העדפות, כללים ומדיניות טקסטואלית. לכל מקור יש `binding`: רק כלל שסומן soft והעדפה אינם מחייבים. כל השאר, כולל ההנחיה החופשית, מחייב. כל מקור חוץ מההנחיה של הבנייה עצמה מסומן `persistent` ומקבל `key` לפי התוכן.
2. מקורות קבועים שכבר תורגמו נטענים מה-cache (4.2.3), ורק השאר נשלחים למודל. מקור מחייב שנשמר כ-`unresolved` שולח את התקופה ל-scheduler המלא בלי שום קריאה.
3. `DirectiveAgent.translate()` מריץ לולאת כלים חסומה: עד `MAX_TURNS=4` קריאות למודל עם `scheduler_directives.md`, עד 4 כלים בכל קריאה, ועד 2 הרצות `dry_run` בסך הכול.
4. הכלים (`directive_agent/tools.py`) הם Python טהור בלי repository: `resolve_employee`, `list_slots`, `employee_state`, `check` ו-`dry_run` (הרצת ה-scheduler הדטרמיניסטי בזיכרון). שום דבר לא נכתב.
5. התשובה הסופית עוברת את אותו `read_translation` כמו קודם. אם הקוד דחה אותה ונשארו סבבים, היא חוזרת למודל עם הסיבות. מקור שהמודל סימן `unresolved` מסיים את הלולאה מיד.
6. אם התרגום לא מלא, `directive_agent/partial.py` שומר כל מקור שכל הפריטים שלו עברו, ומשמיט מקור שלם (אף פעם לא חצי מקור):
   - אם מקור מחייב הושמט, התקופה עוברת ל-scheduler המלא (מסלול ה-AI), כמו קודם.
   - אם הושמטו רק משאלות רכות, הקוד בונה בלעדיהן, וכל אחת נרשמת ב-`notes` ("בקשה רכה לא נלקחה בחשבון בשיבוץ"). ב-metrics נרשמים `model_calls`, `translation_steps`, `unresolved_sources`, `compiled_hits` ו-`tokens_saved`.

#### 4.2.2 השיבוץ הדטרמיניסטי ⚙️ (`deterministic_scheduler/`)
- עובר יום אחר יום, ומכבד pins, אי-זמינות ובקשות מובנות מ-`bl/schedule_requests.py`: `avoid`, `prefer`, `max_count`, `not_together` (ב-`honoring.py`), ומאז D32 גם `min_rest`, `max_consecutive`, `balance` ו-`requires_with` (ב-`limits.py`, עם שעות המשמרות ועד 14 ימי היסטוריה). בקשה קשיחה מוציאה מועמד, ורכה מוסיפה לו עלות. `min_rest`, `max_consecutive` ו-`balance` יכולים לחול על כל הצוות, ולכן גם מדיניות מנוחה או הוגנות מתורגמת לקוד ולא נשלחת ל-scheduler המלא.
- משמרות שדורשות תפקיד נדיר (או אחמ"ש) ממולאות לפני משמרות שיש להן הרבה מועמדים (`plan.py`, `_legal_count`), כדי שבעל התפקיד הנדיר לא "יבוזבז" על משמרת אחרת.
- לילות וסגירות מאוזנים לפי מספר הלילות בתקופה ולפי `outlook.py` (חלק צפוי בששת הימים הבאים), ולא רק לפי שעות.

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
   2. **מסלול מהיר:** `ChatTools.replacement_lookup` (`bl/chat_tools.py`) עונה על "מי יכול להחליף" בלי מודל.
   3. אחרת יש עד **7 סבבים** של `complete_json(manager_chat.md)`. בכל סבב המודל מבקש עד 4 כלים (`_MAX_CALLS`) מ-`bl/tools/` ומ-`bl/chat_tools.py` (קריאה בלבד), והתוצאות נוספות לסבב הבא.
   4. כשהמודל מחזיר תוכנית, `bl/chat_planner.py` (`prepare`) מאמת ומריץ audit. התוכנית יכולה להיות שינויים, יצירה (שמריצה את ה-scheduler **בתוך** התור, עם קריאות LLM נוספות), שינוי מבנה, ניהול בקשות או אילוצים.
   5. אם יש אזהרות, התוכנית חוזרת למודל לבדיקה פעם אחת. אם הקוד דחה אותה, יש עד 2 תיקונים.
   6. בסוף ההודעה נשמרת עם התוכנית בסטטוס `pending`.
4. הדפדפן דוגם את השיחה (`useManagerChat.ts`) ומציג את השלבים בזמן אמת. עצירה: `/stop`.
5. המנהל מאשר: `POST /api/agent/chats/{id}/messages/{mid}/apply`.
   - הקוד ב-`bl/chat_apply.py`: נעילת שורה (`chat_approval`), ובדיקה שה-fingerprint של המצב לא השתנה מאז ההצעה.
   - הפעלה דרך `OperationApplier`, `create_blank`, `apply_management` ועדכון הפרופיל, ורישום ביומן.
6. דחייה: `/dismiss`.

### 5.3 מסלולים ישנים לשינוי ולשאלות 💤
| Endpoint | מה עושה | LLM |
|---|---|---|
| `POST /api/schedule/propose` | `ChangeAgent`: הצעת שינוי מטקסט | 🤖 1 |
| `POST /api/schedule/apply` | הפעלת הצעה שאושרה | ⚙️ |
| `POST /api/schedule/ask` | `ModelToolLoop`: שאלה עם כלים, ו-fallback ל-`bl/intent` | 🤖 עד 3 |
| `POST /api/schedule/brief` | `BriefingAgent`: "הסוכן מדבר ראשון" | 🤖 1 |
| `POST /api/schedule/simulate` | `bl/simulate` | ⚙️ |
| `POST /api/schedule/tool` | הרצת כלי בודד | ⚙️ |

כל אלה הוחלפו בפועל בצ'אט המנהל, וה-UI לא קורא להם. הפונקציות `proposeChange`, `applyChange`, `askAgent`, `briefManager`, `simulateChange` ו-`generateScheduleDay` ב-`frontend/src/services/api.ts` לא בשימוש. איך מסירים אותם: סעיף 14.

### 5.4 ניקוי, מחיקה, פרסום ⚙️
- `POST /{id}/publish` / `unpublish`: מעבר בין draft ל-published ורישום ביומן. חברי צוות רואים רק סידורים מפורסמים.
- `POST /{id}/clear`: מרוקן יום או תקופה ומשאיר את הרשת. כל שורה שהוסרה נרשמת.
- `DELETE /{id}`: מחיקת התקופה.

### 5.5 עזיבת עובד ⚙️
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
3. `events.publish(team, "requests")` מעיר את ה-SSE של המנהל (`GET /api/schedule/requests/events`). עם Redis האות יוצא בערוץ pub/sub של הצוות, ו-listener אחד בכל תהליך מעביר אותו ל-streams המקומיים, כך שמנהל מחובר לכל worker מקבל אותו. בלי Redis ההעברה בתוך התהליך בלבד. בכל מקרה יש polling כל 15 שניות כגיבוי.
4. המנהל ב-`RequestInbox.tsx` מאשר (`POST /api/schedule/requests/{id}/approve`), ואז נוצרת שורת `availability` עם `source=employee_reported`. דחייה: `/reject`.
5. העובד יכול למשוך את הבקשה: `/requests/{id}/withdraw`.

### 7.3 החלפת משמרות: עובד ← עמית ← מנהל ⚙️
1. `SwapPanel.tsx` שולח `POST /api/employee/swaps` (רק משמרות מסידור מפורסם).
2. העמית עונה: `POST /api/employee/swaps/{id}/answer`.
3. המנהל ב-`SwapInbox.tsx` מאשר עם סיבה (`/api/schedule/swaps/{id}/approve`), וזה מפעיל את `schedule_service.apply` עם `OP_SWAP` ונרשם ביומן.

### 7.4 עוזר העובד 🤖
1. `AssistantChat.tsx` שולח `POST /api/employee/assistant`.
2. `swap_options.py` מחשב בקוד אילו החלפות נקיות, על ידי audit מחדש לכל החלפה.
3. קריאת LLM אחת (`employee_assistant.md`), והמודל רק בוחר מזהים מתוך הרשימה. בלי מודל יש fallback.
4. לא נכתב כלום, ואילוצים של עמיתים לא מגיעים למודל.
5. **הקריאה רצה בתוך תהליך ה-API ולא ב-worker.**

---

## 8. סטטיסטיקות ⚙️
`Stats.tsx` קורא ל-`GET /api/schedule/stats?...`, דרך `audit.shift_stats` על כל טווח: שעות, משמרות, לילות והוגנות.

---

## 9. Copilot: תיבת "הסוכן שם לב" ⚙️
1. ה-worker, בכל `PAKASH_COPILOT_SCAN_SECONDS` (ברירת מחדל 30 דקות), מכניס job מסוג `scan` **לכל צוות**.
2. `CopilotService.scan()` מוצא פערים בפרופיל, פרופיל שלא עודכן 90 יום, ואזהרות בסידור הנוכחי. אין LLM.
3. נוצרים פריטים בתיבה עם fingerprint נגד כפילויות. `CopilotInbox.tsx` מציג אותם.
4. אישור, ביטול ושחזור (`/api/copilot/items/{id}/approve|dismiss|rollback`) **משנים רק סטטוס**. אין להם שום תופעת לוואי על הסידור (`check: "no_side_effect"`). `POST /api/copilot/run` מריץ סריקה ידנית, ו-`PATCH /permissions/{type}` קובע אם סוג פריט הוא תצפית או הצעה.

> **מועמד לפישוט:** מנגנון ההרשאות, האישור וה-rollback לא מבצע כלום בפועל. אפשר לצמצם לתצפיות שנסגרות, או לחבר את "אשר" לפתיחת צ'אט עם ה-suggestion.

---

## 10. הגדרות מערכת ⚙️
- `Settings/` דורש סיסמת הגדרות בכותרת, וקורא ל-`GET` ו-`PUT /api/settings`.
- ההגדרות נשמרות **בקובץ JSON אחד גלובלי** (`runtime-settings.json`): מודלים לכל role, URL ומפתח, timeout, אימות SSL (`llm_verify_ssl`), מנוע ומצב יצירה, diet mode, וחיבור Redis.
- `GET` ו-`POST /api/models`: בדיקת שרת מודלים ורשימת המודלים שלו. הבדיקה מקבלת גם `llm_verify_ssl` שלא נשמר עדיין, כדי לבדוק שרת פנימי עם תעודה בחתימה עצמית לפני השמירה.
- `llm_verify_ssl` דלוק כברירת מחדל. כיבוי שלו חושף את החיבור, כולל מפתח ה-API, ליירוט, ולכן הוא מיועד רק לשרת פנימי.
- `llm_max_concurrency` נאכף על ה-API וה-workers יחד, ונקרא מחדש בכל רכישת slot. לכל צוות מותרת קריאת מודל אחת במקביל (פירוט בסעיף 11).
- **Redis:** בפאנל יש קטע Redis (`Settings/RedisSettings.tsx`) עם URL, סיסמה ו-key prefix. אפשר גם דרך `PAKASH_REDIS_URL`, `PAKASH_REDIS_PASSWORD` ו-`PAKASH_REDIS_KEY_PREFIX`. `POST /api/settings/redis` בודק חיבור (שנשמר, או שהוקלד ועוד לא נשמר) ומחזיר מידע על השרת, המפתחות של האפליקציה, חשבונות נעולים, קריאות מודל פעילות והתור. כשל חיבור מוחזר כתשובה ולא כשגיאה. תהליכים אחרים קולטים URL חדש תוך כמה שניות, כי `RedisHub` קורא מחדש את קובץ ההגדרות.
- קונסולת המפעיל (`Admin/SystemView.tsx`) מציגה את מצב Redis.

---

## 11. מפת ה-LLM המלאה

כל הקריאות עוברות דרך `dal/llm/openai_client.py`: `complete_json`. מעליו יש סולם fallback (schema, json mode, plain, merged system), retry, הגבלת מקביליות משותפת, לוג טוקנים ו-Opik.

**תור המודל** (`dal/llm/budgets.py`, `slots_for`), לפי סדר עדיפות:
1. `RedisModelSlots` (`dal/llm/redis_slots.py`), כש-Redis רשום (`share_slots`, נקרא ב-`main.py` וב-`worker.py`) וזמין. כרטיסים מוגשים לפי עדיפות ואז לפי סדר הגעה, כך שצ'אט של מנהל עוקף יום בנייה שממתין בתור (`priority_for_flow`: רק `scheduler` הוא background). מי שמחזיק slot מחדש lease של 30 שניות, וממתינים מרעננים את הכרטיס שלהם, כך שתהליך שנהרג משחרר את מקומו תוך lease אחד.
2. `PostgresModelSlots` (advisory locks), כשאין Redis או שהוא נכשל.
3. `ModelSlots` בזיכרון, כשאין גם database (בעיקר בטסטים).

שלושתם שומרים על אותו חוזה: גבול אחד לכל ה-deployment מתוך `llm_max_concurrency`, וקריאה אחת במקביל לכל צוות.

| זרימה | פעולה ב-UI | role | prompt | קריאות | איפה רץ |
|---|---|---|---|---|---|
| צ'אט מנהל (`bl/chat_reply.py`) | AgentChat | default | `manager_chat.md` (כ-21K תווים) | 1–7 לכל הודעה, ועוד יצירה פנימית | worker |
| יצירה (ai) | GenerateDialog / צ'אט | advanced | `scheduler.md` | 1–2 לכל יום או שבוע | worker |
| תרגום הנחיות (auto, `bl/directive_agent/`) | GenerateDialog / צ'אט | advanced | `scheduler_directives.md` | 1–4 לכל span (לולאת כלים), רק למקורות שלא ב-cache | worker |
| תרגום קבוע (`bl/compiled_sources/`) | שמירת פרופיל או העדפה | advanced | `scheduler_directives.md` (`mode: compile`) | 1–4 לכל שמירה | worker |
| עוזר עובד | AssistantChat | default | `employee_assistant.md` | 1 | API |
| למידה משינויים | LearnedFromChanges | default | `learn_changes.md` | 1 | API |
| 💤 propose | – | default | `changes.md` | 1 | API |
| 💤 ask | – | default | `planner.md` | עד 3 | API |
| 💤 brief | – | fast | `briefing.md` | 1 | API |

### איך להוזיל (לפי סדר השפעה)
1. **למדוד:** הטוקנים נשמרים היום רק בלוג `pakash.llm` וב-`_usage` של הודעת הצ'אט. צריך טבלת `llm_usage(team_id, flow, model, tokens, rounds, ts)`.
2. **צ'אט מנהל:**
   - להעביר את רשימת `tools`, שהיא סטטית, ל-system prompt כדי שה-prefix יישמר ב-cache.
   - לשלוח רק את השבוע הנראה במקום את כל הסידור.
   - ✅ היעדרות ("X חולה בשני ושלישי", "X טס לחו״ל", "X לא יכולה לעבוד בשישי") נקראת ומתוכננת בקוד ב-`bl/absence/`, בתוך הבקשה עצמה, בלי סבב מודל (D34). רשימת הכלים הסטטית עברה ל-system prompt כדי שתישמר ב-cache.
   - למדוד את `model_rounds` ולשקול להוריד את `_ROUNDS`, שעומד כרגע על 7.
   - שאלות קריאה בלבד להריץ על role `fast`.
3. **יצירה:** לשמור על `auto` או לעבור ל-`code`. לשקול מצב `week`. לקצר את ה-reason לכל שיבוץ (טוקני פלט) או להפעיל `llm_diet_mode`. מקורות קבועים כבר נשמרים (4.2.3), אבל ההנחיה החופשית של הבנייה עדיין מתורגמת מחדש בכל span, עד 4 קריאות כל פעם. למדוד את `translation_steps`, `compiled_hits` ו-`tokens_saved`, ולשקול להוריד את `MAX_TURNS`.
4. **להסיר את ה-endpoints הישנים** שעולים כסף ולא בשימוש (סעיף 14).

---

## 12. מה חוסם ריבוי משתמשים

| בעיה | איפה | השפעה | כיוון פתרון |
|---|---|---|---|
| הגדרות גלובליות בקובץ | `common/runtime_settings/` | כל הצוותים על אותו מודל ומנוע. תהליכים אחרים קוראים את הקובץ מחדש, אבל זה עובד רק כשהם חולקים volume | להעביר ל-DB, עם דריסה לכל צוות או תוכנית |
| Redis לא מוגדר ב-compose | `docker-compose.yml` | אין שירות `redis`, ו-`PAKASH_REDIS_URL` לא מועבר ל-`backend` ול-`copilot`. לכן ברירת המחדל רצה בלי Redis: throttle ו-SSE בזיכרון התהליך | להוסיף שירות `redis` ולהעביר את `PAKASH_REDIS_*` לשני התהליכים, או להגדיר בפאנל |
| אין תקציב LLM לכל צוות | – | יש הגבלה של קריאה אחת במקביל לצוות, אבל אין מכסת טוקנים, וצוות אחד יכול לצרוך הרבה | מונה ומכסה לכל צוות |
| audit מלא בכל קריאת לוח | `context.view()` | CPU שגדל עם המשתמשים | cache לפי גרסת הסידור |
| Opik שולח prompts עם נתוני עובדים | `dal/llm/tracing.py` | פרטיות מול כמה לקוחות | החלטה מפורשת או מיסוך |
| `PAKASH_SESSION_SECRET` ריק כברירת מחדל ב-compose | `docker-compose.yml` | ה-sessions לא תקפים בין תהליכים | חובה להגדיר |

נפתר: יצירה מחולקת ל-job לכל span; ה-worker מפעיל כמה lanes ושומר lane לצ'אט;
מכסת המודל משותפת לכל התהליכים (Redis, ובלעדיו advisory locks של Postgres) עם quota לצוות;
ה-throttle והאירועים של SSE משותפים דרך Redis כשהוא מוגדר (D33).

---

## 13. סיכום: להשאיר, להסיר, לבדוק

### להשאיר (הליבה, בשימוש)
כניסה והרשאות · פרופיל · לוח ושיבוץ ידני · יצירה (start, run, progress, cancel, range) · צ'אט מנהל · גרירה עם סיבה · פרסום, ניקוי ומחיקה · ייצוא · עזיבת עובד · אילוצים והעדפות · אזור עובד (me, בקשות, החלפות) · סטטיסטיקות · הגדרות · קונסולת מפעיל.

### מועמדים להסרה (💤 לא נקראים מה-UI)
| Backend | Frontend (`services/api.ts`) | קוד שאולי מת איתם |
|---|---|---|
| `POST /schedule/brief` | `briefManager` | `bl/briefing.py`, `prompts/briefing.md` |
| `POST /schedule/propose` | `proposeChange` | המחלקה `ChangeAgent`, `prompts/changes.md` (שאר `changes/` בשימוש הצ'אט) |
| `POST /schedule/apply` | `applyChange` | החלפות עדיין משתמשות ב-`schedule_service.apply`, אז להסיר רק את ה-route |
| `POST /schedule/ask` | `askAgent` | `bl/planner/model_loop.py`, `prompts/planner.md` (`fallback_answers` בשימוש הצ'אט) |
| `POST /schedule/simulate`, `POST /schedule/tool` | `simulateChange` | `bl/simulate` עדיין בשימוש הצ'אט, אז להסיר רק את ה-route |
| `POST /schedule/generate`, `/generate/{id}/next` | `generateScheduleDay` | `Scheduler.generate()` הישן ו-`ChunkedRun` |
| `GET /constraints/list`, `/history/list`, `/current` | – | – |
| `GET /api/schedule/requests`, `/identities`, `/identities/release`, `GET /api/schedule/swaps` | – | לבדוק אם נחוצים לאינטגרציה חיצונית |
| `GET /api/employee/swaps/incoming` | – | – |

הפירוט המלא, כולל מה חייב להישאר ואילו טסטים מושפעים, נמצא בסעיף 14.

### לבדוק או לפשט
- **Copilot:** אישור ו-rollback בלי תופעת לוואי. לפשט, או לחבר לצ'אט.
- **תיעוד:** `backend/CLAUDE.md` מתאר את `bl/interview/` שלא קיים.
- **ה-worker:** כבר מפוצל ל-lanes ול-job לכל span, ו-SSE ו-throttle משותפים דרך Redis. לפני שמוסיפים replicas נשאר להפעיל Redis ב-compose ולהעביר את ההגדרות מהקובץ ל-DB.

---

## 14. איך מסירים רכיב לא חשוב

### הסדר הכללי (לכל רכיב)
1. **לוודא שה-UI לא קורא לו:** לחפש את שם הפונקציה ב-`frontend/src/` (למשל `grep -rn briefManager frontend/src`). אם היא מוגדרת ב-`services/api.ts` ולא מופיעה בשום מקום אחר, היא מתה.
2. **להסיר מה-frontend:** את הפונקציה מ-`services/api.ts`, ואת ה-types שרק היא השתמשה בהם מ-`types.ts`.
3. **להסיר את ה-route** מ-`api/routers/...`, ואת ה-contract מ-`api/contracts/...` אם אף route אחר לא משתמש בו.
4. **להסיר את המתודה מה-facade:** `bl/schedule_service/service.py` מעביר כל route למחלקה קטנה (`changing.py`, `answering.py`, `speaking.py`). מסירים את המתודה, ואת המחלקה עצמה אם היא נשארת ריקה.
5. **לחפש מי עוד מייבא את המודול** לפני שמוחקים קובץ: `grep -rn "from app.bl.<module>" backend/`. הטבלה למטה מסכמת מה נמצא היום.
6. **טסטים:** למחוק טסטים שבודקים רק את הרכיב שהוסר. טסט שבודק התנהגות שהצ'אט עדיין משתמש בה מעבירים לנתיב החדש ולא מוחקים.
7. **prompts:** למחוק את קובץ ה-`.md` מ-`bl/prompts/` ואת הטסט שלו ב-`tests/test_prompts.py`.
8. **להריץ בדיקות:** `cd backend && python -m pytest -q`, ובצד הלקוח `cd frontend && npx tsc --noEmit && npm run lint && npm test`.
9. **תיעוד:** לעדכן את `backend/CLAUDE.md`, את `backend/app/bl/CLAUDE.md` ואת המסמך הזה.
10. **commit אחד לכל רכיב**, כדי שיהיה קל לבטל אם משהו נשבר.

### מה מוחקים ומה חייב להישאר, לכל מועמד
| רכיב | מה מוחקים | מה **חייב להישאר** (ומי משתמש בו) | טסטים שמושפעים |
|---|---|---|---|
| **Briefing** (`/schedule/brief`) | ה-route ב-`routers/schedules/agent.py`, `briefManager`, `bl/briefing.py`, `prompts/briefing.md`, `BriefingService` ב-`speaking.py` | `WorkbookExporter` באותו קובץ (`speaking.py`) משמש לייצוא. ב-`contracts/briefing.py` יש גם את `CopilotPermissionUpdate`, אז מוחקים רק את `Briefing`, `BriefingItem` ו-`BriefingRequest` | `test_briefing.py`, הטסט של briefing ב-`test_prompts.py` |
| **Ask** (`/schedule/ask`) | ה-route, `askAgent`, `bl/planner/agent.py`, `model_loop.py`, `fallback.py`, `prompts/planner.md`, `QuestionService.ask` | `planner/schema.py` (`chat_schema.py`), `planner/shaping.py` (`chat_reply.py`), `planner/fallback_answers.py` ו-`trace.py` (`chat_tools.py`). `bl/intent/dates.py` משמש את `chat_contract.py` | `test_planner.py`, החלקים של `PlanningAgent` ב-`test_clarification.py`, ו-`test_intent.py` אם מוחקים גם את `intent/reader.py` |
| **Propose / apply** (`/schedule/propose`, `/schedule/apply`) | שני ה-routes, `proposeChange`, `applyChange`, `ChangeService.propose`, `prompts/changes.md` והמחלקה `ChangeAgent` | `changes/proposal.py`, `schema.py`, `values.py`, `targets.py`, `questions.py`, `profile_ops.py` והקבועים `OP_*` (הצ'אט, ההחלפות, `simulate`). `chat_reply.py` מייבא את `_closures_for_model` ו-`_schedule_for_model` מ-`changes/agent.py`, אז קודם מעבירים אותן ל-`changes/values.py`, ורק אחר כך מוחקים את `agent.py`. `ChangeService.apply` נשאר, כי אישור החלפה משתמש בו | `test_change_operations.py`, `test_clarification.py`, וחלק מ-`test_scheduler.py` (בערך שורות 780–900 משתמשות ב-`ChangeAgent`) |
| **Simulate / tool** (`/schedule/simulate`, `/schedule/tool`) | שני ה-routes, `simulateChange`, `QuestionService.simulate` ו-`run_tool`. אם גם Ask הוסר, אפשר למחוק את כל `answering.py` | כל `bl/simulate/`: `hypothetical.py` משמש את הצ'אט, ההחלפות ו-`swap_options.py`. כל `bl/tools/` (הצ'אט) | `test_simulate.py` נשאר, כי הוא בודק את המודול ולא את ה-route |
| **Generate הישן** (`/generate`, `/generate/{id}/next`) | שני ה-routes ו-`generateScheduleDay` | `Scheduler.generate()` ו-`ChunkedRun`: **לא למחוק בשלב הראשון.** עשרות טסטים ב-`test_scheduler.py` עוברים דרך `generate()`. קודם מעבירים אותם ל-`generate_span()`, ורק אז מוחקים את `generate()`, את `scheduler/planning.py` ואת `builder.generate` | `test_scheduler.py` |
| **Reads לא בשימוש** (`/constraints/list`, `/history/list`, `/current`, `/requests`, `/identities`, `/swaps`, `/employee/swaps/incoming`) | רק ה-routes | מתודות ה-repository, אם routes אחרים קוראים להן | לבדוק את `test_schedule_api.py`, `test_employee_api.py` ו-`test_swap_api.py` |
| **Copilot** (אם מצמצמים לתצפיות) | `approve`, `rollback`, `PATCH /permissions/{type}` ו-`CopilotPermissionUpdate` | `scan`, הפריטים בתיבה ו-`dismiss` | `test_copilot.py` |

### סדר מומלץ
1. **Briefing**, ו-**Generate הישן (רק ה-routes):** אין להם תלויות, ולכן הם הכי בטוחים.
2. **Simulate / tool:** מסירים רק routes.
3. **Ask:** מוחקים את הלולאה ומשאירים את הקבצים שהצ'אט משתמש בהם.
4. **Propose:** קודם מעבירים את שתי הפונקציות מ-`changes/agent.py`, ואז מוחקים.
5. **`Scheduler.generate`:** רק אחרי שהטסטים עברו ל-`generate_span()`.
