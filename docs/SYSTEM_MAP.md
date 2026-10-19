# מפת המערכת: כל פעולה מרכזית, צעד אחר צעד

המסמך מתאר מה קורה בפועל בכל פעולה מרכזית: מה המשתמש עושה, איזה endpoint נקרא, איזה קוד רץ, האם יש קריאה ל-LLM ומה נכתב ל-DB. בסופו יש המלצות מה להשאיר, מה להסיר ומה לבדוק.

מקרא:
- 🤖 יש קריאה ל-LLM
- ⚙️ קוד דטרמיניסטי בלבד
- 💤 קיים ב-backend אבל ה-UI לא קורא לו

> נכון לענף `restore-llm-engine`. נתיבי הקבצים יחסיים ל-`backend/src/app/` אלא אם צוין אחרת.

---

## 0. הארכיטקטורה בקצרה

```
דפדפן (Next.js, frontend/)
   │  HTTP + cookie חתום (common/sessions.py)
   ▼
API (FastAPI, main.py) ── routers ב-api/routers/ ── guards ב-api/dependencies.py
   │                     │
   │  שירותים ב-bl/       │  קריאות LLM סינכרוניות: עוזר עובד, למידה בייבוא
   ▼                     ▼
PostgreSQL (dal/repository/) ◄──── Worker (worker.py, תהליך נפרד)
   ▲                                │  לולאה אחת: צ'אט מנהל, יצירת סידור, סריקת copilot
   └────────────── jobs ────────────┘
                                    ▼
                       שרת מודל OpenAI-compatible (dal/llm/)
                       ברירת מחדל: Ollama, gemma3:27b, מקביליות 1
```

- **שלושה תהליכים:** frontend, API ו-worker. ה-worker מושך jobs מ-Postgres (`FOR UPDATE SKIP LOCKED`) **אחד בכל פעם**.
- **שלוש דרגות מודל** (`dal/llm/model_roles.py`): `advanced` ליצירת סידור, `fast` ל-briefing, ו-`default` לכל השאר.
- **העיקרון המוביל (D3):** המודל מחליט, והקוד סופר ובודק. ה-audit לא חוסם אף פעולה.

---

## 1. כניסה והרשאות

### 1.1 כניסת מנהל לצוות ⚙️
1. במסך `Workspace/Login.tsx` נבחר צוות ומוקלדת סיסמה.
2. `POST /api/workspace/login`, דרך `bl/workspace_service.py`.
3. הסיסמה נבדקת מול hash מסוג scrypt (`dal/repository/teams.py`). ניסיונות כושלים מוגבלים ב-`common/throttle.py`, בזיכרון של התהליך.
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
4. `ProfileGapsNotice.tsx` מציג מה עוד חסר, לפי `tools.profile_gaps` ו-`completeness`.

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
3. `POST /api/schedule/generate/{id}/run` מכניס job מסוג `generation` לתור.
4. ה-worker מריץ את `generation/runner.py`, שעובר על **כל התקופה בתוך job אחד**. לכל span:
   - `stepper.generate_next()` קורא ל-`Scheduler.generate_span()`, ומשם לפי `schedule_generation_engine`:
     - `code`: `deterministic_scheduler/`, אפס טוקנים.
     - `auto` (ברירת מחדל): אם הקלט מובנה, הקוד משבץ. אם יש הנחיות חופשיות, יש קריאת LLM אחת לתרגום ההנחיות (`scheduler_directives.md`) ואז הקוד משבץ. אם התוצאה לא נקייה, עוברים למסלול ה-AI.
     - `ai`: קריאה לכל יום או לכל שבוע (`schedule_generation_mode`) עם `scheduler.md`, ועוד קריאת תיקון אחת לכל היותר.
   - כל שורה עוברת בדיקת גבולות (מי זמין, סבב), ואז audit ו-checkpoint של אותם תאריכים בלבד.
5. הדפדפן דוגם `GET /api/schedule/{id}/progress` (מונה ימים ו-heartbeat).
6. עצירה: `/generate/{id}/cancel`, וה-worker עוצר בסוף היום הנוכחי. הסתרת הבאנר: `/dismiss`. יום בודד: `/day/start`. טווח בתוך טיוטה: `/range/start` (שיבוצים ידניים נשמרים כ-pins).
7. 💤 `/generate` (המסלול הישן, בחלקים) ו-`/generate/{id}/next` לא נקראים מה-UI.

### 4.3 ייבוא מאקסל ⚙️ + 🤖 אופציונלי
1. `ImportSchedule.tsx` שולח קבצים ל-`POST /api/schedule/import/preview?learn_rules=true`.
2. `bl/importer/` קורא את הגריד ומזהה את הפריסה (shift_major, person_major או date_only) **בלי מודל**.
3. `bl/learn/observe()` סופר דפוסים בין הקבצים, בלי מודל.
4. 🤖 אם `learn_rules=true` (ברירת המחדל), `RuleLearner` מנסח כללים מוצעים: קריאת LLM אחת.
5. המנהל מתקן במסך ומאשר. `POST /api/schedule/import/confirm` הוא **היחיד שכותב**, והוא שומר את מה שחזר מהמסך ולא קורא את הקובץ מחדש.

### 4.4 ייצוא ⚙️
`GET /api/schedule/export/{id}` מריץ את `bl/export.py` ומחזיר xlsx בפריסת Sample A, שאפשר לייבא בחזרה.

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

כל אלה הוחלפו בפועל בצ'אט המנהל, וה-UI לא קורא להם. הפונקציות `proposeChange`, `applyChange`, `askAgent`, `briefManager`, `simulateChange` ו-`generateScheduleDay` ב-`frontend/src/services/api.ts` לא בשימוש.

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
3. `events.publish(team, "requests")` מעיר את ה-SSE של המנהל (`GET /api/schedule/requests/events`). יש גם polling כל 15 שניות כגיבוי.
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
- ההגדרות נשמרות **בקובץ JSON אחד גלובלי** (`runtime-settings.json`): מודלים לכל role, URL ומפתח, timeout, מנוע ומצב יצירה, diet mode.
- `GET` ו-`POST /api/models`: בדיקת שרת מודלים ורשימת המודלים שלו.
- `llm_max_concurrency` נקבע רק כשהתהליך עולה.

---

## 11. מפת ה-LLM המלאה

כל הקריאות עוברות דרך `dal/llm/openai_client.py`: `complete_json`. מעליו יש סולם fallback (schema, json mode, plain, merged system), retry, הגבלת מקביליות (`ModelSlots`, בזיכרון התהליך), לוג טוקנים ו-Opik.

| זרימה | פעולה ב-UI | role | prompt | קריאות | איפה רץ |
|---|---|---|---|---|---|
| צ'אט מנהל (`bl/chat_reply.py`) | AgentChat | default | `manager_chat.md` (כ-21K תווים) | 1–7 לכל הודעה, ועוד יצירה פנימית | worker |
| יצירה (ai) | GenerateDialog / צ'אט | advanced | `scheduler.md` | 1–2 לכל יום או שבוע | worker |
| תרגום הנחיות (auto) | GenerateDialog / צ'אט | advanced | `scheduler_directives.md` | 1 | worker |
| עוזר עובד | AssistantChat | default | `employee_assistant.md` | 1 | API |
| למידה בייבוא | ImportSchedule | default | `learn.md` | 1 לכל preview | API |
| למידה משינויים | LearnedFromChanges | default | `learn_changes.md` | 1 | API |
| 💤 propose | – | default | `changes.md` | 1 | API |
| 💤 ask | – | default | `planner.md` | עד 3 | API |
| 💤 brief | – | fast | `briefing.md` | 1 | API |

### איך להוזיל (לפי סדר השפעה)
1. **למדוד:** הטוקנים נשמרים היום רק בלוג `pakash.llm` וב-`_usage` של הודעת הצ'אט. צריך טבלת `llm_usage(team_id, flow, model, tokens, rounds, ts)`.
2. **צ'אט מנהל:**
   - להעביר את רשימת `tools`, שהיא סטטית, ל-system prompt כדי שה-prefix יישמר ב-cache.
   - לשלוח רק את השבוע הנראה במקום את כל הסידור.
   - להרחיב את המסלול המהיר ו-`bl/intent` לפני המודל.
   - למדוד את `model_rounds` ולשקול להוריד את `_ROUNDS`, שעומד כרגע על 7.
   - שאלות קריאה בלבד להריץ על role `fast`.
3. **יצירה:** לשמור על `auto` או לעבור ל-`code`. לשקול מצב `week`. לקצר את ה-reason לכל שיבוץ (טוקני פלט) או להפעיל `llm_diet_mode`. לשמור במטמון את תרגום ההנחיות.
4. **ייבוא:** להפוך את `learn_rules` ל-opt-in, או לשמור במטמון לפי hash של הקבצים.
5. **להסיר את ה-endpoints הישנים** שעולים כסף ולא בשימוש.

---

## 12. מה חוסם ריבוי משתמשים

| בעיה | איפה | השפעה | כיוון פתרון |
|---|---|---|---|
| ה-worker מעבד job אחד בכל פעם, ויצירה רצה כ-job אחד ארוך | `worker.py`, `generation/runner.py:119` | יצירה של חודש חוסמת את הצ'אט של **כל** הצוותים | job לכל span, כמה workers, תורים נפרדים לצ'אט וליצירה |
| מקביליות ה-LLM רק בזיכרון התהליך, וברירת המחדל 1 | `dal/llm/budgets.py`, `model_slots.py` | API ו-worker לא מתואמים, ואין הוגנות בין צוותים | limiter משותף ב-Postgres או Redis, מכסה לכל צוות, ושרת שמעבד במקביל (vLLM או API מתארח) |
| הגדרות גלובליות בקובץ | `common/runtime_settings/` | כל הצוותים על אותו מודל ומנוע, ולא מסתנכרן בין replicas | להעביר ל-DB, עם דריסה לכל צוות או תוכנית |
| SSE ו-throttle בזיכרון התהליך | `common/events.py`, `common/throttle.py` | נשבר עם יותר מ-replica אחד | `LISTEN/NOTIFY` או Redis |
| אין תקציב LLM לכל צוות | – | צוות אחד יכול לצרוך הכול | מונה ומכסה לכל צוות |
| audit מלא בכל קריאת לוח | `context.view()` | CPU שגדל עם המשתמשים | cache לפי גרסת הסידור |
| Opik שולח prompts עם נתוני עובדים | `dal/llm/tracing.py` | פרטיות מול כמה לקוחות | החלטה מפורשת או מיסוך |
| `PAKASH_SESSION_SECRET` ריק כברירת מחדל ב-compose | `docker-compose.yml` | ה-sessions לא תקפים בין תהליכים | חובה להגדיר |

---

## 13. סיכום: להשאיר, להסיר, לבדוק

### להשאיר (הליבה, בשימוש)
כניסה והרשאות · פרופיל · לוח ושיבוץ ידני · יצירה (start, run, progress, cancel, range) · צ'אט מנהל · גרירה עם סיבה · פרסום, ניקוי ומחיקה · ייבוא וייצוא · עזיבת עובד · אילוצים והעדפות · אזור עובד (me, בקשות, החלפות) · סטטיסטיקות · הגדרות · קונסולת מפעיל.

### מועמדים להסרה (💤 לא נקראים מה-UI)
| Backend | Frontend (`services/api.ts`) | קוד שאולי מת איתם |
|---|---|---|
| `POST /schedule/brief` | `briefManager` | `bl/briefing.py`, `prompts/briefing.md` |
| `POST /schedule/propose` | `proposeChange` | `bl/changes/agent.py`, `prompts/changes.md` (לבדוק מה הצ'אט עדיין מייבא מ-`changes/`) |
| `POST /schedule/apply` | `applyChange` | החלפות עדיין משתמשות ב-`schedule_service.apply`, אז להסיר רק את ה-route |
| `POST /schedule/ask` | `askAgent` | `bl/planner/model_loop.py`, `prompts/planner.md` (`fallback_answers` בשימוש הצ'אט) |
| `POST /schedule/simulate`, `POST /schedule/tool` | `simulateChange` | `bl/simulate` עדיין בשימוש הצ'אט, אז להסיר רק את ה-route |
| `POST /schedule/generate`, `/generate/{id}/next` | `generateScheduleDay` | `Scheduler.generate()` הישן ו-`_ChunkedRun` |
| `GET /constraints/list`, `/history/list`, `/current` | – | – |
| `GET /api/schedule/requests`, `/identities`, `/identities/release`, `GET /api/schedule/swaps` | – | לבדוק אם נחוצים לאינטגרציה חיצונית |
| `GET /api/employee/swaps/incoming` | – | – |

לפני מחיקה צריך לבדוק שאף טסט ב-`backend/tests/` ואף מודול אחר לא תלוי בהם. למשל `bl/chat_reply.py` מייבא מ-`bl/changes/agent.py` ומ-`bl/planner/shaping.py`, `bl/chat_tools.py` מייבא מ-`bl/planner/fallback_answers.py`, ו-`bl/chat_schema.py` מייבא מ-`bl/planner/schema.py`.

### לבדוק או לפשט
- **Copilot:** אישור ו-rollback בלי תופעת לוואי. לפשט, או לחבר לצ'אט.
- **למידה בייבוא:** מופעלת כברירת מחדל ועולה קריאת LLM בכל preview.
- **תיעוד:** `backend/CLAUDE.md` מתאר את `bl/interview/` שלא קיים.
- **ה-worker:** לפצל לפני שמוסיפים צוותים.
