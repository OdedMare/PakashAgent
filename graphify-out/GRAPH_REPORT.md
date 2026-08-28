# Graph Report - PakashAgent  (2026-08-28)

## Corpus Check
- 232 files · ~293,209 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4300 nodes · 9643 edges · 207 communities (164 shown, 43 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 229 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `14cbf903`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Import and Layout Inference
- Conversational Schedule Changes
- Scheduling Runtime Architecture
- URL and Schema Normalization
- Backend Error Hierarchy
- Product Capabilities
- Advisory Rules and UI
- Layered Backend Build Plan
- Application Settings
- Live Runtime Settings
- Employee Read-Only Access
- API Routers Package
- Business Logic Package
- Agent Error Concept
- Runtime Settings Package
- Database Package
- LLM Package
- Repository Package
- Backend Project Configuration
- test_intent.py
- types.ts
- scheduler.py
- api.ts
- ConflictError
- tools.py
- test_workspace.py
- test_interview_api.py
- test_clarification.py
- test_workspace_api.py
- ProfileService
- interview_service.py
- _ScriptedLlm
- routers/schedules.py
- BaseModel
- test_export.py
- ScheduleRepository
- test_agent_api.py
- Interview/index.tsx
- test_llm_client.py
- changes.py
- openai_client.py
- rotation.py
- shift_stats
- simulate
- test_model_roles.py
- .get
- PlanningAgent
- test_background_learning.py
- test_rotation.py
- BriefingAgent
- schedule_service.py
- contracts.py
- test_importer.py
- Board/index.tsx
- SettingsSections.tsx
- build_slots
- test_runtime_settings.py
- devDependencies
- Employee/index.tsx
- _FakeScheduleRepo
- planner.py
- CopilotService
- simulate.py
- importer.py
- ScheduleService
- Management/index.tsx
- infer
- personal_summary
- deterministic_scheduler.py
- .get
- compilerOptions
- OpenAIJsonClient
- ChangeAgent
- test_swap_api.py
- test_tools.py
- Workspace/index.tsx
- Calendar.tsx
- formatDate
- CopilotInbox.tsx
- useBoard.ts
- draftStats.ts
- employee.py
- EmployeeService
- _read_shift_major
- WorkspaceService
- test_settings_api.py
- ManualSetup/index.tsx
- CopilotRepository
- ._view
- worker.py
- TeamPanel.tsx
- briefing.py
- test_scheduler.py
- employee_service.py
- BoardGrid.tsx
- ._remember_patterns
- _ScriptedLlm
- _week_profile
- sample_a
- test_error_handlers.py
- load
- .start_generation
- shiftOrder.ts
- _iso_date
- _Repo
- _Repo
- _require_rotation_placement
- DateInput.tsx
- test_a_generated_schedule_carries_its_warnings_and_still_returns_200
- test_worker_guard.py
- Stats.tsx
- changes.md
- ._requeue_failed_span
- extract_model_ids
- _Repo
- HoursPanel.tsx
- routers/interview.py
- Interpretation
- read_grids
- _FakeRepository
- _NoModel
- test_deterministic_scheduler.py
- test_a_hand_placed_shift_lands_on_the_period_it_names
- Preferences.tsx
- .apply
- extract_json
- _RepoWithPreferences
- _ended_early
- תוצאת חיקוי ראיון הפתיחה
- scheduler.md
- devsandbox
- SwapInbox.tsx
- routers/copilot.py
- profile.py
- .claim
- learn.md
- learn_changes.md
- planner.md
- tutorial/page.tsx
- briefing.md
- interview.md
- merge_system_into_user
- _NoModel
- Q: hey i want to start work the agent init interview here some qusetions that give as the base the do interview from that mock the missing question that you miss then we implament this part
- Q: in the pakash agent app
- Q: איך לייעל את כמות הטוקנים שאני מעביר בראיון זה מגיע לכמויות גדולות שגודל המידע
- Q: זה לא יפגע באיכות?
- Q: בוא נתכנן איך לממש את זה
- Q: תממש את זה ואני רוצה שזה יהיה בpolling ולא בstream כמו שעכשוי
- Q: i want cllckable questions and theres alweys place that he say somthing like רשמתי את רשימת העובדים ואת ימי הפעילות (ראשון עד חמישי). but does nothing
- Q: תעצב לי tutorial למערכת עם סקרינשוטים והכל לכל פונקציונליות
- Q: הראיון ארוך וחוזר על שאלות, ויצירת לוח המשמרות הראשוני לפעמים טועה
- Q: בוא נחשוב איך נשפר את חווית הראיון היא משמעותית מאוד
- Q: תבנה
- Q: היום הבעיה החמורה היא שהמידע שנשמר בראיון לא עובר במצב לטוב לתהליך בניית הסידור איך אתה מציע שנעשה את זה ונמקסם על זה
- Q: עכשיו יש לי בעיה אני יוצר סידור אוטומטי אבל המודל מחזיר תשובה חיובית ו200 api אבל ui מחזיר שגיאת רשת 500
- Q: אני רוצה לשנות את ההמשגות ואת היכולות של המערכת אני רוצה לשנות את המערכת לשיבוצים צבאים תוסיף סבב א או ב או תלתון א ב ג ומתי סבב או תלתון סוגרים בפעם הראשונה אילוצים קבוע או זמני סוג משמרת חפיפה כמה תקינה תקן מוזר נחפף/מילואים אני רוצה להגדיר את כל המערכת ידנית
- Q: I want fulley working co pilot better at the ui better the ability’s
- Q: בשיבוץ למשמרות התשובה מהמודל מגיעה תוך 120 עד 300 שניות תוודא שהui לא מחזיר לי timeout כי עכשיו הוא מחזיר
- Q: היום אני חוטף שגיאות של שגיאות רשת אבל המודל חוזר ומחזיר תשובה תעשה את זה לא בסטרימינג אלא בפולינג ככה שהכל יעבוד כמו שצריך בנוסף אני רוצה ממש אופציה לפתוח ולשבץ יום ספציפי כמו כפתור על יום ואז לתת הנחיות על הלוח אני רוצה שסוכן וקופיילוט יתאחדו אני רוצה שתשפר את הפרומפטים לסגירות ליציאות היום הוא מאזן בין הסבבים אבל לא מבין שזה סגירות שבתות סבבים
- Q: היי היום תהליך בניית הסידור על ידי llm עובד לסירוגין כבד ואיטי ספר לי איך הוא עובד ונחשוב על איך לתקן אותו זה הפונקצינואליות הראשית למערכת
- ApplyRequest
- ConstraintRequest
- ModelsProbeRequest
- interview_method.md
- test_literal_paths_are_not_read_as_schedule_ids
- test_a_member_cannot_reach_any_mutation
- context
- layout.tsx
- AskRequest
- BlankRequest
- ClearRequest
- ConstraintPressure
- Coverage
- GenerationProgress
- MoveRequest
- Option
- PlacementCandidate
- PreferenceRequest
- Warning
- WarningCount
- hebrew.md
- untrusted.md
- .generate_day
- test_a_generated_assignment_is_marked_as_the_agents
- test_generating_without_any_shift_is_an_error_not_an_empty_schedule
- test_no_tool_writes_anything
- test_no_schedule_at_all_is_an_answer_not_an_error
- test_an_unknown_employee_is_not_invented
- test_coverage_gaps_finds_the_empty_slots
- test_a_trainee_shadowing_a_shift_does_not_close_its_gap
- test_validate_placement_never_blocks
- test_validate_placement_reports_an_ineligible_shift
- test_a_candidate_who_would_warn_is_never_offered
- test_publish_readiness_is_descriptive_not_a_gate
- test_another_workspace_period_reads_as_missing
- test_unknown_arguments_are_dropped_rather_than_crashing
- test_a_confirmed_profile_reports_nothing_outstanding
- test_a_gap_is_not_listed_twice
- test_a_missing_shift_vocabulary_blocks_even_manual_building
- eslint.config.mjs
- next.config.ts

## God Nodes (most connected - your core abstractions)
1. `AgentError` - 187 edges
2. `_build_app()` - 110 edges
3. `_client()` - 106 edges
4. `ScheduleService` - 92 edges
5. `request()` - 80 edges
6. `audit()` - 68 edges
7. `_ScriptedLlm` - 54 edges
8. `PlanningAgent` - 53 edges
9. `NotFoundError` - 53 edges
10. `IntroInterview` - 51 edges

## Surprising Connections (you probably didn't know these)
- `PakashAgent` --references--> `Agent Decides; Code Audits`  [EXTRACTED]
  README.md → backend/app/bl/CLAUDE.md
- `Pure Python Advisory Audit` --references--> `D3 Agent Decides; Code Only Audits`  [EXTRACTED]
  backend/CLAUDE.md → docs/DECISIONS.md
- `Confirm Before Import Persistence` --references--> `D7 Import Infers Layout, Boss Confirms`  [EXTRACTED]
  backend/CLAUDE.md → docs/DECISIONS.md
- `Two-Step Import Contract` --references--> `D7 Import Infers Layout, Boss Confirms`  [EXTRACTED]
  backend/app/api/CLAUDE.md → docs/DECISIONS.md
- `Two-Step Change Contract` --references--> `D8 Two Reasons, Both Required`  [EXTRACTED]
  backend/app/api/CLAUDE.md → docs/DECISIONS.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **PakashAgent Four-Step Product Flow** — readme_intro_interview, readme_shift_loading_and_generation, readme_schedule_import, readme_conversational_changes [EXTRACTED 1.00]
- **Agent Judgment with Advisory Audit Flow** — backend_app_bl_claude_schedule_generation, backend_app_bl_claude_advisory_checker, backend_app_api_claude_advisory_warning_response, frontend_claude_non_blocking_warning_banners [INFERRED 0.95]
- **Importer Layout Evidence and Mechanisms** — docs_file_formats_sample_a_shift_major_dense, docs_file_formats_sample_b_person_major_sparse, docs_file_formats_axis_semantics_inference, docs_file_formats_cell_classification, docs_file_formats_confirmation_interpretation [EXTRACTED 1.00]

## Communities (207 total, 43 thin omitted)

### Community 0 - "Import and Layout Inference"
Cohesion: 0.05
Nodes (49): Advisory Warning Response, HTTP Layer, Two-Step Import Contract, Advisory Checker, Agent Decides; Code Audits, Interview Workflow, Layout Inference Importer, Cross-Cutting Infrastructure (+41 more)

### Community 1 - "Conversational Schedule Changes"
Cohesion: 0.18
Nodes (13): Two-Step Change Contract, Conversational Change Workflow, Schedule Generation, Assignments with Agent Reason, Living Schedule, complete_json, Response-Format Degradation Ladder, Invalid JSON Parse Retry (+5 more)

### Community 2 - "Scheduling Runtime Architecture"
Cohesion: 0.05
Nodes (99): _already_asked(), _as_dict(), _asked_questions(), _bounded(), _draft_update_schema(), empty_draft(), IntroInterview, _is_ready() (+91 more)

### Community 3 - "URL and Schema Normalization"
Cohesion: 0.09
Nodes (28): extract_url_schema(), normalize_database_schema(), normalize_database_url(), normalize_http_url(), normalize_llm_base_url(), Accept a pasted endpoint, not just the base.      Users copy the URL they see in, The schema a JDBC-style URL asks for, or "" when it names none.      Lets a past, Validate a schema name. Empty means "use the server default". (+20 more)

### Community 4 - "Backend Error Hierarchy"
Cohesion: 0.05
Nodes (44): The durable copilot's deterministic observation and action boundary., NotFoundError, Error types leaving the backend.  Messages are Hebrew: they reach a Hebrew-speak, _configure_for(), connect(), _credentials(), _pool_for(), Pooled PostgreSQL connections driven by live runtime settings.  The store is rea (+36 more)

### Community 5 - "Product Capabilities"
Cohesion: 0.04
Nodes (102): _build_app(), _client(), The management area's HTTP contract, over a fake repository and model.  Three th, No profile means no shift vocabulary, and guessing one is exactly     the hardco, The state the management screen opens in.      The panel renders whatever arrive, The authoring half of D6. `_ScriptedLlm` raises if it is called at     all, so a, Skipping the agent does not mean skipping the interview: without the     shift v, D8 is answered by a different voice, not relaxed. The row says a     person plac (+94 more)

### Community 6 - "Advisory Rules and UI"
Cohesion: 0.05
Nodes (83): _bounded(), _bounded_rows(), _candidates(), _coverage(), _date(), _declared_shifts(), _iso_or_blank(), observe() (+75 more)

### Community 7 - "Layered Backend Build Plan"
Cohesion: 0.06
Nodes (80): check(), _clean(), closure_of(), _cycle_of(), _effective_availability(), employee_options(), _employees(), _explain() (+72 more)

### Community 8 - "Application Settings"
Cohesion: 0.13
Nodes (20): Environment defaults; UI overrides are applied by RuntimeSettingsStore., Env-derived DEFAULTS. Values the boss can edit in the UI live in     common.runt, Settings, RuntimeSettingsStore, fixture, The backward-compatibility case: a file written before the role     fields exist, store(), test_a_bad_value_in_a_saved_file_does_not_stop_startup() (+12 more)

### Community 9 - "Live Runtime Settings"
Cohesion: 0.06
Nodes (71): _consecutive_days(), constraint_conflicts(), _constraint_pressure(), _constraint_window(), _coverage(), _cycle_of(), _double_booked(), _empty_load() (+63 more)

### Community 12 - "API Routers Package"
Cohesion: 0.05
Nodes (36): Guards, Dependency factories bound to the process's signing secret., Any authenticated visitor -- boss, member, or employee., The boss of a workspace, and nobody else.          Every route that touches a *s, A signed-in employee, acting as themselves.          The narrow counterpart to `, build_router(), APIRouter, Live settings, and the model probe the settings panel uses.  The store is the si (+28 more)

### Community 13 - "Business Logic Package"
Cohesion: 0.12
Nodes (6): _fresh_cache(), fixture, Prompt loading and include resolution.  The loader gained includes so the interv, Every test reads from disk, so one test's load cannot serve another., The includes are additions to the domain wording, not a replacement     for it —, test_the_interview_prompt_keeps_its_own_body()

### Community 16 - "Runtime Settings Package"
Cohesion: 0.05
Nodes (69): _as(), _change(), _claim(), client(), fixture, The employee area's HTTP boundary: identity, isolation, and scope.  The isolatio, Act as a given role.      Clears first: a preceding `claim` or `login` left a se, The upgrade path D14 describes: a member session becomes a personal     one. The (+61 more)

### Community 17 - "Database Package"
Cohesion: 0.09
Nodes (24): close_pool(), Release every pooled connection. For shutdown and for tests., Create the schema and tables if they are not there yet.      A database that is, Return every pooled connection before the process goes away.      Without this t, shutdown(), startup(), fake_pool(), _FakePool (+16 more)

### Community 19 - "LLM Package"
Cohesion: 0.11
Nodes (32): create_with_retry(), _delay(), _out_of_time(), Bounded retry for transient OpenAI-compatible failures.  Only the transient fami, `Retry-After` in seconds, when the response carried one., One completion, retried through the transient failures.      `deadline` is a `ti, How long to wait before the next attempt.      A server that said `Retry-After`, _retry_after() (+24 more)

### Community 20 - "Repository Package"
Cohesion: 0.07
Nodes (66): audit(), Every warning the countable facts support, most severe first.      `assignments`, _assign(), _by_code(), _codes(), _load(), The advisory checker: arithmetic over a roster, no model.  Table-driven per BUIL, A constraint row with no shift name rules out the entire day.      This is the q (+58 more)

### Community 23 - "test_intent.py"
Cohesion: 0.06
Nodes (63): _any_in(), _bounded(), _classify(), _date_in(), _employee_in(), _explicit_date(), _iso(), _parse() (+55 more)

### Community 24 - "types.ts"
Cohesion: 0.04
Nodes (62): AgentAnswer(), TOOL_LABELS, ACTION_LABELS, AgentChat(), PROFILE_ACTION_LABELS, PROFILE_QUESTIONS, profileOperationSummary(), SCHEDULE_QUESTIONS (+54 more)

### Community 25 - "scheduler.py"
Cohesion: 0.07
Nodes (61): _assignments(), _audit_for_span(), _availability_for_dates(), _bounded(), _bounded_rows(), _candidates(), _chunks(), _closures_for_model() (+53 more)

### Community 26 - "api.ts"
Cohesion: 0.10
Nodes (56): useEmployee(), inclusiveDays(), useManagement(), acknowledgeChanges(), allRequests(), allSwaps(), answerSwap(), apiError() (+48 more)

### Community 27 - "ConflictError"
Cohesion: 0.05
Nodes (21): ConflictError, IdentityRepository, Mark everything up to now as seen by this employee.          Separate from `last, Which names are already taken.          Feeds the claim screen so it can grey ou, Every claim in the team, for the manager's roster panel., Drop a claim so the name can be claimed again.          The manager's tool for s, Record a submission. Changes nothing about the schedule.          `employee` is, Requests, newest first.          The manager reads this unfiltered by employee; (+13 more)

### Community 28 - "tools.py"
Cohesion: 0.09
Nodes (42): _arguments_for(), _assignment_id(), _audit_assignments(), _blocked_by(), _closure_schedule(), _eligible(), _employees(), _find_person() (+34 more)

### Community 29 - "test_workspace.py"
Cohesion: 0.04
Nodes (33): AuthError, The identity if the passcode matches, `AuthError` otherwise.          Mirrors `a, hash_password(), The team if the password matches, `AuthError` if it does not.          The same, The team a share link points at. Possession of the token is the         credenti, `scrypt$<salt-hex>$<hash-hex>`.      The salt travels with the hash: it is not a, Constant-time compare against a stored `hash_password` value.      A malformed o, verify_password() (+25 more)

### Community 30 - "test_interview_api.py"
Cohesion: 0.09
Nodes (50): build_router(), APIRouter, Liveness, plus a database round-trip., _answer_required_questions(), _client(), _complete(), _completion_responses(), _confirming() (+42 more)

### Community 31 - "test_clarification.py"
Cohesion: 0.06
Nodes (49): Which roster person a manager's word means — or that it is unclear.      Exact m, resolve_employee(), _change(), fixture, Asking instead of guessing, on both halves of the agent.  The rule is one senten, The specific guess this whole change exists to refuse.      Returning `DANIEL_C`, A name that exists is never ambiguous, whatever else it prefixes., Two different questions: "which one" versus "who is that".      Kept apart becau (+41 more)

### Community 32 - "test_workspace_api.py"
Cohesion: 0.07
Nodes (42): Route guards: who is asking, and may they.  FastAPI dependencies rather than mid, build_router(), APIRouter, _b64(), generate_secret(), issue(), Signed workspace session cookies.  The cookie carries the team id and a role, si, URL-safe base64 without padding -- `=` is legal in a cookie value but     routin (+34 more)

### Community 33 - "ProfileService"
Cohesion: 0.10
Nodes (41): _audit_policy(), _employee_item(), _employees(), _keep_existing_names(), _named_rows(), _pattern_anchor(), ProfileService, Any (+33 more)

### Community 34 - "interview_service.py"
Cohesion: 0.08
Nodes (36): _answered_topic_ids(), _completed(), _completeness(), _correction_topic_id(), _failed(), _fallback_content(), InterviewService, _last_assistant_was_awaiting() (+28 more)

### Community 35 - "_ScriptedLlm"
Cohesion: 0.10
Nodes (43): Build one period's assignments from the workplace profile., Scheduler, `candidate_employees` is the roster; `profile.employees` repeated it., Widening the call does not widen what is accepted back., Command qualification is independent of each person's exit cycle., Returns the next scripted answer and records what it was asked., D8 enforced in code, not left to the prompt.      An assignment nobody can accou, A name nobody declared cannot be rostered onto a real shift. (+35 more)

### Community 36 - "routers/schedules.py"
Cohesion: 0.05
Nodes (43): AgentAnswer, AssignRequest, Briefing, BriefingRequest, CheckRequest, GenerateDayRequest, GenerateRequest, ImportConfirmRequest (+35 more)

### Community 37 - "BaseModel"
Cohesion: 0.05
Nodes (43): AgentStep, Alternatives, Assignment, BriefingItem, ChangeEntry, ClosingGroup, Closure, Constraint (+35 more)

### Community 38 - "test_export.py"
Cohesion: 0.10
Nodes (41): as_workbook(), _by_day(), filename(), _human_date(), _iso(), _ordered_shifts_across(), _parse(), _period() (+33 more)

### Community 39 - "ScheduleRepository"
Cohesion: 0.06
Nodes (18): Every period this team has, newest first. Rows only, no slots., The period in play: the one covering today, else the newest.          `published, Persist resumable per-day generation progress on the schedule., Remove a period and everything hanging off it.          The `change_log` rows su, Rebuild this schedule's slot grid in one transaction.          Generation produc, Every assignment, joined to the slot that gives it a date.          Shaped the w, Rebuild the whole roster for this schedule, in one transaction.          Every r, Rewrite the rows on these dates. **Every other date is untouched.**          Wha (+10 more)

### Community 40 - "test_agent_api.py"
Cohesion: 0.12
Nodes (42): _build_app(), _client(), The HTTP contract for asking, simulating, and remembering.  Reuses the fake repo, A two-day period with both shifts on each day., The product's promise, at the HTTP boundary., There is no field here `apply` could read (the D15 property)., Transparency is the requirement, not debugging output., The answering path reads drafts and stated reasons — boss only. (+34 more)

### Community 41 - "Interview/index.tsx"
Cohesion: 0.07
Nodes (31): Composer(), Props, ConfirmEnd(), INTERVIEW_STAGES, InterviewProgress(), Thinking(), THINKING_PHASES, useThinkingPhase() (+23 more)

### Community 42 - "test_llm_client.py"
Cohesion: 0.13
Nodes (39): _bad_request(), _client(), LLM client: the degradation ladder, the parse retry, and the helpers.  Driven by, Every rung sends the same oversized messages, so stepping down cannot     help —, No automatic failover. Retrying a timed-out generation on a second     model can, End to end: with no timeout the ladder runs every rung it needs.      Guards the, The wiring, not the arithmetic: `complete_json` must hand the flow's     own cei, _Response (+31 more)

### Community 43 - "changes.py"
Cohesion: 0.09
Nodes (38): _ask_which_person(), _ask_which_shift(), _bounded(), _closures_for_model(), _constraints(), _date(), _day_generation_proposal(), _json_default() (+30 more)

### Community 44 - "openai_client.py"
Cohesion: 0.07
Nodes (33): ModelBusy, ModelSlots, priority_for_flow(), Exception, Fair access to the process-wide model concurrency limit., Schedule generation is polled; every other flow has a person waiting., No model slot became available before an interactive wait expired., A priority-aware, FIFO replacement for ``threading.Semaphore``.      A semaphore (+25 more)

### Community 45 - "rotation.py"
Cohesion: 0.11
Nodes (38): _cross_rotation(), Assignments that put somebody in on another rotation's closure.      A closure b, by_date(), closing_group(), closure_days(), configuration_errors(), cycle(), _cycle_of_group() (+30 more)

### Community 46 - "shift_stats"
Cohesion: 0.10
Nodes (38): The period in numbers: coverage, load, distribution, and pressure.      The mana, Load per shift name, in the workplace's own vocabulary (D9).      Every shift th, shift_stats(), _stats_by_shift(), _assignment(), The period in numbers, as the control room's charts read it.  Table-driven for t, The unstaffed shift, which leaves no assignment row to notice.      Same trap `a, Three people on a two-person shift is 100%, not 150%.      The extra body is a n (+30 more)

### Community 47 - "simulate"
Cohesion: 0.13
Nodes (38): The period as these operations would leave it. Persists nothing.      `operation, simulate(), _assign(), parametrize, What `bl/simulate.py` says a change would do, without doing it.  Pure functions, The field the UI colours off. It is never false., The manager asked what would happen; "that shift is not here" is it., take דנה off Thursday" is a sentence the product accepts elsewhere. (+30 more)

### Community 48 - "test_model_roles.py"
Cohesion: 0.10
Nodes (36): Which model, endpoint and credential serve each kind of work.  Every role may na, The role a flow runs on. An unmapped or missing flow gets DEFAULT —     a new ca, The model id to send, resolved against the live settings.      Order: an explici, The role endpoint, falling back to the existing shared endpoint., The credential for this role's endpoint.      Falls back to `openai_api_key`, wh, resolve_api_key(), resolve_base_url(), resolve_model() (+28 more)

### Community 49 - ".get"
Cohesion: 0.10
Nodes (34): _DeferredLauncher, _FakeSettings, _generation(), The charts' figures ride along on the overview the screen already     fetches, s, A draft is the manager's working state; publishing makes it the team's., The share link is how the team reads the roster. A file is a copy that     leave, The runtime-settings store, reduced to the one field this reads., Including their ids.      Rewriting the whole period per day minted a fresh id f (+26 more)

### Community 50 - "PlanningAgent"
Cohesion: 0.11
Nodes (33): PlanningAgent, A manager's question, answered by running read-only tools., _NoModel, The planning loop, with a fake model and with none at all.  Two halves, and the, A model that is not configured — what an empty deployment has.      Raises exact, Replays prepared turns, recording what it was asked., A model that keeps asking for one more tool must still terminate., A suggested preference is inert until approved — including here. (+25 more)

### Community 51 - "test_background_learning.py"
Cohesion: 0.09
Nodes (35): _corrections(), What the agent notices on its own, and where the board says it noticed.  Three t, One is not a pattern; it is a Tuesday., Otherwise every refresh of the screen adds another identical row., A decision the manager made is not overruled by a background pass., `ask()` reads only active rows, so a suggestion authorises nothing., Wording is a model's job; a *pattern* is arithmetic, and only     arithmetic may, The whole path runs off a read. (+27 more)

### Community 52 - "test_rotation.py"
Cohesion: 0.08
Nodes (37): _profile(), The closure cycle: whose weekend it is, computed rather than guessed.  A closure, No group means every weekend -- "יוצא כל חמישי לסופ״ש"., חמשושים goes in on Thursday, שושים on Friday, both out Sunday morning.      The, `round` sets *who* closes; the span it sets is the Israeli weekend.      A cycle, The last date is a morning, not a day.      Which shift that is comes off the de, With no anchor there is no phase, and guessing one moves everybody.      A perso, A manager naming the Thursday of a חמשוש means that same closure. (+29 more)

### Community 53 - "BriefingAgent"
Cohesion: 0.13
Nodes (31): BriefingAgent, What the agent says when nobody asked it anything., _answer(), _item(), parametrize, The agent speaking first, against a fake model.  What is pinned here is not the, And the reverse: claiming urgency while listing nothing., An item with no text is a row the manager can neither read nor act on. (+23 more)

### Community 54 - "schedule_service.py"
Cohesion: 0.11
Nodes (27): _completed_dates(), _constraint_time(), _iso(), _manager_rows_in(), _manager_rows_on(), _merged_required_rows(), _model_assignment(), _persisted_generation_rows() (+19 more)

### Community 55 - "contracts.py"
Cohesion: 0.07
Nodes (32): AlternativeEmployee, AlternativeSlot, CandidateRule, CreateTeamRequest, ImportFailure, LoginRequest, Operation, PasswordChangeRequest (+24 more)

### Community 56 - "test_importer.py"
Cohesion: 0.11
Nodes (32): The two real layouts from `FILE_FORMATS.md`, rebuilt as `.xlsx`.  Built in code, Person-major, sparse, nested `date x shift` header from merged cells.      The d, sample_b(), _grid(), _interpret(), Layout inference over the two real files, which disagree structurally.  `BUILD_O, `לא זמינה` shares the grid with names and is not one., Sample B's last lane holds a marker and no name at all.      The file does not s (+24 more)

### Community 57 - "Board/index.tsx"
Cohesion: 0.10
Nodes (24): AgentTouch, collectTouches(), fromAnswer(), fromProposal(), fromSimulation(), operationNote(), stringArg(), touchKey() (+16 more)

### Community 58 - "SettingsSections.tsx"
Cohesion: 0.09
Nodes (18): SettingsPanel(), FieldProps, inputValue(), SettingsField(), SettingsSelect(), SettingsToggle(), GENERATION_MODES, MODEL_ROLES (+10 more)

### Community 59 - "build_slots"
Cohesion: 0.11
Nodes (32): build_slots(), One slot per shift per day the shift actually runs.      Built in code rather th, A shift with no `days` runs every day.      An empty list means "not restricted", 2026-08-23 is a Sunday; the evening shift runs only on Sundays., Natural interview answers usually say ``ראשון``, not ``יום ראשון``.      Both sp, test_a_shift_restricted_to_a_weekday_only_appears_on_it(), test_an_inverted_or_oversized_period_is_refused(), test_headcount_follows_the_matching_day_group() (+24 more)

### Community 60 - "test_runtime_settings.py"
Cohesion: 0.06
Nodes (12): parametrize, Settings store: env defaults, UI overrides, secret masking, normalization., 0 must survive the save. It used to be clamped to 1 on the grounds     that "a 0, Both mean "no ceiling" and there is nothing else a negative could     mean, so i, The exemption is for the timeout alone. A 0 here would mean a     semaphore admi, A width nobody chose is the one outcome this setting exists to stop.      Quietl, A per-role key is a credential like any other — it must never leave     the API, test_a_negative_timeout_folds_to_no_limit() (+4 more)

### Community 61 - "devDependencies"
Cohesion: 0.06
Nodes (32): eslint, eslint-config-next, @eslint/eslintrc, dependencies, lucide-react, next, react, react-dom (+24 more)

### Community 62 - "Employee/index.tsx"
Cohesion: 0.09
Nodes (23): ConstraintForm(), formatDate(), IdentityGate(), Employee(), EmployeeSection, formatDate(), MyChanges(), MyShifts() (+15 more)

### Community 63 - "_FakeScheduleRepo"
Cohesion: 0.10
Nodes (5): build_router(), APIRouter, _FakeScheduleRepo, In-memory stand-in that filters by team exactly as the SQL does., test_a_model_that_never_answers_cannot_hold_generation_open()

### Community 64 - "planner.py"
Cohesion: 0.11
Nodes (22): _bounded(), _calls(), _employees(), _is_question(), _iso(), _period_for_model(), _preferences_for_model(), _pretty() (+14 more)

### Community 65 - "CopilotService"
Cohesion: 0.09
Nodes (13): CopilotService, _key(), _older_than(), Read one workspace and leave durable, deduplicated inbox items., _Interviews, The copilot observes durably and keeps every write behind a boundary., _Repo, _Schedules (+5 more)

### Community 66 - "simulate.py"
Cohesion: 0.11
Nodes (29): counts_toward_staffing(), Whether this person fills one of a slot's seats.      The one definition of what, _apply_all(), _coverage(), _employees(), _find(), _iso(), _key() (+21 more)

### Community 67 - "importer.py"
Cohesion: 0.12
Nodes (29): _declared_shift(), _deduplicated(), _has_yearless_dates(), _match_shift(), _mostly_shifts(), _normalise(), _parse_date(), _parse_hours() (+21 more)

### Community 68 - "ScheduleService"
Cohesion: 0.08
Nodes (12): Whether a stop was asked for while a day was being generated.          Re-read r, Empty a day's shifts, or the whole period's. Keeps the grid.          The counte, Record a constraint for an employee.          Written by the manager or by the a, One named tool, run directly. Reads only.          Exposed so the board can ask, What a set of changes would do. **Persists nothing.**          The safe way to a, Remember an operational preference for this team.          `suggested` is what s, Reword a preference, approve a suggested one, or archive it.          Editable b, One period as `.xlsx`, plus the filename to serve it under.          Exported in (+4 more)

### Community 69 - "Management/index.tsx"
Cohesion: 0.09
Nodes (20): ACTION_LABELS, History(), ManagerAnalytics(), ManagerSection, ManagerView, CONFIDENCE_LABELS, LearnedFromChanges(), ProfileGapsNotice() (+12 more)

### Community 70 - "infer"
Cohesion: 0.07
Nodes (29): _bounded(), infer(), Read a grid as a schedule, inferring what its axes mean.      Tries both layouts, parametrize, A lane whose name is written where the person is placed.      Taking the first n, D9 is unchanged where it applies: declared names are matched first., The case with no shift column at all: dates, and who worked them.      A single, An empty shift name is the question made visible (D9).      Naming it `בוקר` wou (+21 more)

### Community 71 - "personal_summary"
Cohesion: 0.13
Nodes (27): fairness(), personal_summary(), One person's own totals: hours, shifts, and the warnings about them.      Added, Hours per person against the team average.      The number that answers "why is, _assignment(), One person's own totals, and the fairness comparison beside them.  These exist f, ISO weeks, matching `_over_hours`. A person's week does not restart     because, A colleague's warning is a colleague's business.      The personal area is the o (+19 more)

### Community 72 - "deterministic_scheduler.py"
Cohesion: 0.20
Nodes (27): _already_on(), _assignment(), _candidate_key(), _counted_on(), _counts(), _cycle(), _date(), _eligible() (+19 more)

### Community 73 - ".get"
Cohesion: 0.13
Nodes (19): _applied(), _change(), _employees(), _period(), _quiet(), Read uploaded schedule files and say what they contain. Writes nothing., What the agent would do about a request. Writes nothing.          The manager co, The period in play, audited, or None when there is none yet.          A member s (+11 more)

### Community 74 - "compilerOptions"
Cohesion: 0.07
Nodes (27): compilerOptions, allowJs, esModuleInterop, incremental, isolatedModules, jsx, lib, module (+19 more)

### Community 75 - "OpenAIJsonClient"
Cohesion: 0.11
Nodes (18): _is_context_overflow(), OpenAIJsonClient, Whether a 400 means "prompt too long" rather than "bad request shape"., The only class callers use. `complete_json` is the method that matters., The ladder, in order. Adding a rung means adding it here — do not         scatte, _connection(), _FakeClient, _FakeCompletions (+10 more)

### Community 76 - "ChangeAgent"
Cohesion: 0.16
Nodes (22): ChangeAgent, Turn a manager's sentence into a proposal they can confirm., _change(), _propose(), What a proposal is allowed to carry, and what it must not swallow.  `bl/changes., One shift that day is not a guess — there was nothing else meant., The bug this file exists for: a change that went nowhere, silently.      The mod, A request that mostly works is carried out, not held behind one gap.      Puttin (+14 more)

### Community 77 - "test_swap_api.py"
Cohesion: 0.19
Nodes (25): _agreed_swap(), _as_boss(), _as_employee(), _offer(), Shift swaps between employees: consent, guards, and who may decide.  Two employe, Dana offers Yossi her morning for his evening., Walk an offer to the state the manager rules on: both agreed., Sign in as an employee, claiming the name the first time.      Going through cla (+17 more)

### Community 78 - "test_tools.py"
Cohesion: 0.13
Nodes (19): The read-only tools the agent runs, over a fake repository.  Table-driven where, A two-shift, two-day period with whoever the test puts on it., _schedule(), test_a_clean_placement_validates(), test_a_date_no_period_covers_is_not_found(), test_a_full_period_reports_no_gaps(), test_a_full_period_with_nothing_pending_is_ready(), test_a_tool_reads_only_its_own_team_roster() (+11 more)

### Community 79 - "Workspace/index.tsx"
Cohesion: 0.12
Nodes (16): Interview(), Workspace(), Login(), MemberEntry(), useWorkspace(), WorkspaceState, createTeam(), currentWorkspace() (+8 more)

### Community 80 - "Calendar.tsx"
Cohesion: 0.13
Nodes (21): BoardRow(), touchLabel(), Calendar(), EmployeePicker(), HEBREW_WEEKDAYS, isWeekend(), missingFrom(), Person() (+13 more)

### Community 81 - "formatDate"
Cohesion: 0.17
Nodes (20): ConfirmDrop(), PlacementVerdict(), addDays(), dateRange(), GenerateDialog(), newRow(), Row, ShiftOption (+12 more)

### Community 82 - "CopilotInbox.tsx"
Cohesion: 0.12
Nodes (22): ACTION_DESCRIPTIONS, ACTION_LABELS, actorLabel(), ConsoleTab, CopilotCard(), CopilotInbox(), eventLabel(), formatDate() (+14 more)

### Community 83 - "useBoard.ts"
Cohesion: 0.15
Nodes (19): FilterBar(), addDays(), BoardFilters, BoardState, EMPTY_FILTERS, isoOf(), localToday(), readRememberedWeek() (+11 more)

### Community 84 - "draftStats.ts"
Cohesion: 0.16
Nodes (20): closureAnchors(), displayDate(), DraftPanel(), peopleNote(), useChangedKeys(), asArray(), asNumber(), asStrings() (+12 more)

### Community 85 - "employee.py"
Cohesion: 0.10
Nodes (22): ClaimRequest, ConstraintSubmission, EmployeeLoginRequest, Claim a roster name and set a personal passcode.      Requires a valid share-lin, Sign in as a claimed identity., An employee asking not to be scheduled (or offering to be).      A *request*, no, The manager ruling on a submission.      `reason` is required to reject and opti, One employee offering another a trade of shifts.      Both shifts are named by * (+14 more)

### Community 86 - "EmployeeService"
Cohesion: 0.09
Nodes (9): EmployeeService, Mark what the employee was just shown as read (D16).          Called by the pers, Submit a constraint request. Writes no constraint.          Returns the stored r, Requests awaiting a decision, for the manager's inbox., The colleague accepting or declining. Still moves nothing.          Accepting is, Swaps both employees agreed to, awaiting the manager., Verify a claim. Raises `AuthError` when it does not match., Every claim, for the manager's roster panel. (+1 more)

### Community 87 - "_read_shift_major"
Cohesion: 0.13
Nodes (23): _carried_date(), _find_date_row(), _find_nested_header(), _is_unavailable(), _is_weekday_row(), _lane_from_cells(), _lane_label(), Sample A: dates across the top, shifts down the side, people in cells.      The (+15 more)

### Community 88 - "WorkspaceService"
Cohesion: 0.11
Nodes (13): _public(), Workspace decisions: who may open a team, and in which role.  The repository own, The safe projection of a team row.      Built by naming what goes IN rather than, Open a workspace and return it with a boss session.          The first team crea, Verify the boss password. Raises `AuthError` if it does not match., Resolve a share link to its team, as a member.          Never returns the member, Names and ids only -- this is served before anyone has logged in., The workspace as the current visitor is allowed to see it.          The member t (+5 more)

### Community 89 - "test_settings_api.py"
Cohesion: 0.09
Nodes (13): The settings HTTP boundary: masking, partial saves, and the model probe., All of it or none of it — otherwise the live settings and the file on     disk d, Empty and masked both mean "use what is stored", so the panel can test     a typ, A role's fields may both be empty while its endpoint is not the     general one, The panel needs the keys present to render the selectors, and empty     so it ca, The panel offers the ids `/v1/models` returned and saves one verbatim     — a vL, An empty mask would make the panel show "(saved)" for nothing., test_a_rejected_patch_changes_nothing() (+5 more)

### Community 90 - "ManualSetup/index.tsx"
Cohesion: 0.16
Nodes (18): DAYS, edit(), EXIT_PATTERNS, exitPattern(), headcount(), inputText(), ManualSetup(), named() (+10 more)

### Community 91 - "CopilotRepository"
Cohesion: 0.12
Nodes (6): CopilotRepository, Any, Small operational snapshot for the manager's copilot console., Delete an untouched follow-up session; answered ones are history., Atomically claim one due job across any number of workers., Return work abandoned by a dead process to the queue.

### Community 92 - "._view"
Cohesion: 0.10
Nodes (12): _dated(), _now(), Park a job the manager stopped, keeping every finished day., Make a draft the team's. Members read only published periods., The stored period containing `day`, or None when none does.          What the bo, The audited period, or just its progress. See `generate_next`., A schedule with its warnings attached.          Warnings ride along on every res, Which of this period's dates belong to a closure, and to whom.          Rides al (+4 more)

### Community 93 - "worker.py"
Cohesion: 0.14
Nodes (13): configure_logging(), Console logging configuration.  Uvicorn configures only its own loggers, so with, Attach one stdout handler to the root logger, exactly once., A logger under the shared ``pakash`` prefix., Log how long a block took, and whether it raised.      Used around external call, _suffix(), Timed, trace() (+5 more)

### Community 94 - "TeamPanel.tsx"
Cohesion: 0.15
Nodes (17): Management(), EmployeeForm(), EXIT_PATTERN_LABELS, exitPatternLabel(), formatHours(), formatWindow(), rawText(), record() (+9 more)

### Community 95 - "briefing.py"
Cohesion: 0.20
Nodes (18): _bounded(), _briefing(), _date(), _items(), _profile_for_model(), Any, The agent speaking first — what it noticed, without being asked.  Every other mo, One briefing. Persists nothing and changes nothing. (+10 more)

### Community 96 - "test_scheduler.py"
Cohesion: 0.15
Nodes (19): plan_spans(), The date ranges a range job will ask the model for, one call each.      Returned, _change(), The scheduler and the change agent, against a fake model.  Both are stateless by, A week is a ceiling, not a promise. Staffing volume splits it., D8: the answer to a missing reason is a question, not a rejection., A change with neither reason cannot land in the append-only log.      Enforced h, דנה חולה ביום חמישי" is both a change and a fact about Thursday.      Storing th (+11 more)

### Community 97 - "employee_service.py"
Cohesion: 0.17
Nodes (15): _employees(), _mark_side(), _mark_unseen(), _names(), Any, The employee's own area: their identity, their hours, their requests.  The busin, Everything the personal area opens with, in one call.          `employee` comes, Every swap naming this person, on either side.          Both sides read the same (+7 more)

### Community 98 - "BoardGrid.tsx"
Cohesion: 0.24
Nodes (15): BoardGrid(), buildScheduleIndex(), NO_ASSIGNMENTS, NO_WARNINGS, push(), ScheduleIndex, ariaWho(), identityTitle() (+7 more)

### Community 99 - "._remember_patterns"
Cohesion: 0.12
Nodes (13): _pattern_evidence(), _pattern_key(), _pattern_sentence(), Candidate rules from what the manager kept correcting by hand.          The othe, Count the corrections and record what repeats. No model call.          The backg, Write repeated corrections down as suggestions, once each.          The gap this, Answer a question about the schedule by running read-only tools.          The mu, What this workplace has taught the agent, beyond one-off decisions. (+5 more)

### Community 100 - "_ScriptedLlm"
Cohesion: 0.14
Nodes (16): _asking(), _proposing(), A change turn that asks rather than proposes., The acceptance criterion, end to end.      The model is scripted to be confident, The other half of the same gate: a name the workplace does not have.      Separa, The manager answers the question, not the whole sentence again., The infinite-loop guard, at the boundary that would show it.      Two turns: the, Existing behaviour, unchanged. The regression that would matter most. (+8 more)

### Community 101 - "_week_profile"
Cohesion: 0.14
Nodes (18): _covering(), A one-shift workplace, so the slot count tracks the day count., The common case must not pay for the long one: a single week is built     in exa, Half a Tuesday in one request and half in another is how one person     ends up, A scheduler that cannot see week one gives week two to the same     people -- tu, Week two must see week one's shifts as shifts already worked., The later call is the one working from incomplete information, so the     earlie, A slot left short in week one is not the manager's problem only until     week t (+10 more)

### Community 102 - "sample_a"
Cohesion: 0.16
Nodes (17): Shift-major, dense, `d/M/yy` dates with a Hebrew weekday row beneath., sample_a(), _preview(), A file may name a shift the interview never heard of (D7).      Sample A has a `, D7's whole point: inference is not a write.      The confirmation is only real i, A folder of a year's sheets will contain one stray document., A candidate becomes a rule only when the manager says so (D7)., A pattern is by definition what one period cannot show. (+9 more)

### Community 103 - "test_error_handlers.py"
Cohesion: 0.12
Nodes (15): client(), fixture, What leaves the API when something fails.  Asserted against the real `app.main.a, The specific handler keeps winning. `AgentError` is a 502 with the     sentence, Starlette's own 404, not the catch-all: registering a handler for     `Exception, The field the frontend actually reads.      Without a `detail` the UI can only p, `str(exc)` on a database error can carry a connection string, a query     with e, The id on the screen and the id in the log are the same string.      That corres (+7 more)

### Community 104 - "load"
Cohesion: 0.17
Nodes (11): clear_cache(), _compose(), load(), _normalized(), _path(), Load prompt text from disk, resolve includes, and cache the result.  Prompts are, The composed prompt registered under `name`, without its extension.      `reload, Drop every cached prompt, so the next `load` reads from disk. (+3 more)

### Community 105 - ".start_generation"
Cohesion: 0.13
Nodes (11): _has_shifts(), An empty period the manager fills in themselves (D18).          The other half o, How wide one persisted checkpoint is for the next build.          Read live from, Whether this profile can produce a grid at all.      Deliberately the same test, The profile, or a refusal that says what is still missing.          Both buildin, Open a persistent range job; each later request generates one day., ProfileIncompleteError, The interview finished, but not with enough to build a grid.      Its own type r (+3 more)

### Community 106 - "shiftOrder.ts"
Cohesion: 0.25
Nodes (15): announce(), listeners, mergeOrder(), minutesOf(), onStorageEvent(), orderByHours(), orderSnapshot(), readStoredOrder() (+7 more)

### Community 107 - "_iso_date"
Cohesion: 0.13
Nodes (10): _assignment(), _iso_date(), Approve a request and promote it into a real constraint.          Two writes, in, Reject a request, with a reason the employee will read.          The reason is r, Offer a swap to a colleague. Moves nothing.          Both shifts are named by *a, Approve a swap and perform it.          The ruling first, then the swap itself t, Refuse a swap, with a reason both employees will read.          Required for the, What the change log records as the agent's half of the reason.      A swap the e (+2 more)

### Community 108 - "_Repo"
Cohesion: 0.13
Nodes (4): fixture, An in-memory repository that filters by team exactly as the SQL does.      Count, _Repo, tools()

### Community 109 - "_Repo"
Cohesion: 0.14
Nodes (3): fixture, _Repo, tools()

### Community 110 - "_require_rotation_placement"
Cohesion: 0.15
Nodes (10): _find_assignment(), _generation_required_rows(), _moved_from(), Place one person on one slot, by hand. No model call (D18).          This writes, Take one person off a slot, by hand (D18).          Removing somebody *does* tak, Move one assignment — what a confirmed drag resolves to.          The gesture ha, Validate and persist manager-pinned rows before generation starts., Hard write-boundary guard for every manual or conversational move. (+2 more)

### Community 111 - "DateInput.tsx"
Cohesion: 0.26
Nodes (11): DayHead(), shortDate(), ConfirmRemoval(), describe(), RemovalTarget, title(), BoardLoading(), dateDraft() (+3 more)

### Community 112 - "test_a_generated_schedule_carries_its_warnings_and_still_returns_200"
Cohesion: 0.14
Nodes (12): _days(), _preview_grid(), D3: warnings are advisory. A schedule that breaks a rule still renders.      Eig, The audit reads a constraint with no shift as covering the whole day., An ad-hoc `.xlsx` from a list of rows, for one-off layouts., D9 where it applies: the vocabulary's spelling wins., No shift column at all — the plainest file a manager keeps., _sheet() (+4 more)

### Community 113 - "test_worker_guard.py"
Cohesion: 0.23
Nodes (11): _boot(), parametrize, The multi-worker session-secret guard.  `main.py` is a composition root that run, Import `app.main` in a fresh interpreter under the given environment., Generating one per process is fine when there is only one process --     session, Each worker would sign with its own key and reject the others'     cookies. The, `WEB_CONCURRENCY` is what uvicorn and gunicorn read; the others are     what a c, test_a_single_worker_starts_without_a_secret() (+3 more)

### Community 114 - "Stats.tsx"
Cohesion: 0.26
Nodes (8): DayChart(), EmployeeChart(), formatHours(), formatNumber(), shortWeekday(), Stats(), WARNING_LABELS, WarningCount

### Community 115 - "changes.md"
Cohesion: 0.18
Nodes (10): Continue what you were asked about, Do not ask when you can already tell, Operations, The two things you must produce, What you are given, What you do not do, When the manager gave no reason, ask for one, When you cannot tell what the request refers to, ask (+2 more)

### Community 116 - "._requeue_failed_span"
Cohesion: 0.18
Nodes (6): Exception, Put a failed span back in the queue. False when it is out of tries.          Bou, Back off before re-asking. See `_RETRY_BASE_SECONDS`., Finish a range behind the short POST that launched it., Say "still here" every few seconds. Returns the way to stop.          A separate, Stamp liveness on a running job without rewriting the document.          A singl

### Community 117 - "extract_model_ids"
Cohesion: 0.18
Nodes (9): extract_model_ids(), Pull model IDs out of a `/models` response.  Compatible servers disagree on the, Probe `/models` over raw httpx rather than the SDK, so the admin UI         can, _overflow(), parametrize, A 400 of the kind a server returns for a prompt past its context., test_model_ids_are_read_from_every_envelope_servers_use(), test_model_ids_of_an_unexpected_payload_is_empty_not_an_error() (+1 more)

### Community 119 - "HoursPanel.tsx"
Cohesion: 0.29
Nodes (9): formatDelta(), formatHours(), formatWeek(), HoursPanel(), ShiftChart(), TeamComparison(), WeeklyChart(), Fairness (+1 more)

### Community 120 - "routers/interview.py"
Cohesion: 0.20
Nodes (9): AnswerRequest, InterviewSeed, InterviewTurn, One answer from the boss.      A clicked option and free text arrive on the same, Facts read from an existing schedule before the interview starts., One conversational turn, shaped like the reference `plan-chat` reply.      `draf, build_router(), APIRouter (+1 more)

### Community 121 - "Interpretation"
Cohesion: 0.22
Nodes (5): _human(), Interpretation, object, The one sentence D7 asks for, in Hebrew, for the confirm screen., What the importer believes a file says, before anyone approves it.      Delibera

### Community 122 - "read_grids"
Cohesion: 0.22
Nodes (10): A file's first sheet (or its tables) as a rectangular grid of strings.      Merg, Every usable worksheet/table in one upload.      A workbook often opens on a sum, read_grid(), read_grids(), `export.py` writes Sample A's shape precisely so this round-trips., test_an_exported_week_can_be_imported_back(), test_every_visible_worksheet_is_returned_for_inference(), test_old_xls_gets_an_actionable_error() (+2 more)

### Community 124 - "_NoModel"
Cohesion: 0.22
Nodes (8): _NoModel, What an unconfigured deployment has. Raises the real failure., The model being unreachable is not the manager having been unclear.      An unco, No model, a question about a person, and no person named.      `employee_state`, Nothing was understood, so there is no intent for an answer to continue.      Ec, test_a_technical_failure_is_not_a_clarification(), test_an_unreadable_sentence_leaves_nothing_to_resume(), test_the_fallback_asks_who_rather_than_picking_somebody()

### Community 125 - "test_deterministic_scheduler.py"
Cohesion: 0.33
Nodes (7): _profile(), parametrize, The central scheduler is code: fast, repeatable and rotation-safe., test_agent_understands_day_generation_without_a_model(), test_declared_rotation_without_an_anchor_blocks_generation(), test_saturday_uses_the_round_and_triplet_groups_that_close_it(), _UnavailableModel

### Community 126 - "test_a_hand_placed_shift_lands_on_the_period_it_names"
Cohesion: 0.22
Nodes (9): The fallback stays, for any client that predates the field., An older period and a newer one. The newer is what the server calls     "current, The board is not always on the week that covers today.      Every hand-write car, `move` had no `schedule_id` at all -- it resolved the current period     uncondi, test_a_drag_on_another_period_is_not_refused(), test_a_hand_placed_shift_lands_on_the_period_it_names(), test_a_write_naming_no_period_still_means_the_current_one(), test_removing_a_shift_names_its_period_too() (+1 more)

### Community 127 - "Preferences.tsx"
Cohesion: 0.33
Nodes (8): KIND_LABELS, Preferences(), addPreference(), deletePreference(), listPreferences(), updatePreference(), Preference, PreferenceKind

### Community 128 - ".apply"
Cohesion: 0.25
Nodes (6): _match(), _nothing_applied(), Apply a proposal the manager confirmed, and log it.          The manager's reaso, One operation against the stored schedule. Returns rows changed., Why a confirmed proposal changed nothing, as the manager reads it.      One oper, The stored assignment an operation names, if it is there.

### Community 129 - "extract_json"
Cohesion: 0.29
Nodes (7): extract_json(), Pull one JSON object out of a model reply.  Servers that are only approximately, _strip_fence(), test_extract_json_finds_an_object_inside_prose(), test_extract_json_keeps_hebrew_intact(), test_extract_json_rejects_a_bare_array(), test_extract_json_strips_a_markdown_fence()

### Community 131 - "_ended_early"
Cohesion: 0.25
Nodes (8): _ended_early(), A profile shaped like one `interview_service.end` wrote.      The escape hatch i, The bug this guard exists for.      An interview ended early leaves a profile th, Both building paths ask one question, so they give one answer.      They differ, The gate applies the builder's own test, not a laxer one.      `build_slots` nee, test_a_blank_period_over_a_profile_with_no_shifts_says_what_is_missing(), test_a_shift_the_grid_builder_would_skip_counts_as_no_vocabulary(), test_generating_over_a_profile_with_no_shifts_fails_the_same_way()

### Community 132 - "תוצאת חיקוי ראיון הפתיחה"
Cohesion: 0.25
Nodes (7): אילוצים וכללי שיבוץ, לקחים שנכנסו לפרומפט, מה נשאר פתוח לסשן הבא, משמרות ותקינה, עובדים, פרופיל שאושר בשיחה, תוצאת חיקוי ראיון הפתיחה

### Community 133 - "scheduler.md"
Cohesion: 0.29
Nodes (6): Notes, Shift names, The rules you are working under, What you are given, What you produce, סגירות, שבתות וסבבי יציאות

### Community 134 - "devsandbox"
Cohesion: 0.29
Nodes (6): devsandbox, Notes, Run it, Tests, The model, What is where

### Community 135 - "SwapInbox.tsx"
Cohesion: 0.52
Nodes (6): describeShift(), formatDate(), SwapInbox(), approveSwap(), pendingSwaps(), rejectSwap()

### Community 136 - "routers/copilot.py"
Cohesion: 0.33
Nodes (5): CopilotPermissionUpdate, How independently one class of copilot action may operate., build_router(), APIRouter, Boss-only control surface for the durable copilot.

### Community 137 - "profile.py"
Cohesion: 0.33
Nodes (5): ProfileUpdate, A manual profile patch, including first-time setup without a model., build_router(), APIRouter, Boss-only manual editing of employees and shift types.

### Community 138 - ".claim"
Cohesion: 0.33
Nodes (4): Employee names as the interview recorded them.      Read defensively: the profil, Names available to claim, and which are taken.          Served to a share-link v, Bind a roster name to a passcode.          The name is checked against the workp, _roster_names()

### Community 139 - "learn.md"
Cohesion: 0.33
Nodes (5): How to judge, Untrusted input, What you are given, What you are not doing, What you produce

### Community 140 - "learn_changes.md"
Cohesion: 0.33
Nodes (5): How to judge, Untrusted input, What you are given, What you are not doing, What you produce

### Community 141 - "planner.md"
Cohesion: 0.33
Nodes (5): Choosing tools, The rules you may not break, What a good answer looks like, What you are given, What you produce

### Community 143 - "briefing.md"
Cohesion: 0.40
Nodes (4): What is worth speaking about, What you are given, What you are not doing, What you produce

### Community 144 - "interview.md"
Cohesion: 0.40
Nodes (4): Facts, rules, and preferences, Numbers code must enforce, Understanding shifts, What you are building

### Community 145 - "merge_system_into_user"
Cohesion: 0.40
Nodes (4): merge_system_into_user(), Fold the system prompt into the user turn.  The last rung of the degradation lad, test_merge_leaves_messages_without_a_system_turn_alone(), test_merge_system_into_user_folds_the_system_turn()

### Community 146 - "_NoModel"
Cohesion: 0.40
Nodes (4): _NoModel, It is a side effect of a screen that must render regardless., No model configured -- the deployment default here., test_background_learning_never_raises()

### Community 147 - "Q: hey i want to start work the agent init interview here some qusetions that give as the base the do interview from that mock the missing question that you miss then we implament this part"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: hey i want to start work the agent init interview here some qusetions that give as the base the do interview from that mock the missing question that you miss then we implament this part, Source Nodes

### Community 148 - "Q: in the pakash agent app"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: in the pakash agent app, Source Nodes

### Community 149 - "Q: איך לייעל את כמות הטוקנים שאני מעביר בראיון זה מגיע לכמויות גדולות שגודל המידע"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: איך לייעל את כמות הטוקנים שאני מעביר בראיון זה מגיע לכמויות גדולות שגודל המידע, Source Nodes

### Community 150 - "Q: זה לא יפגע באיכות?"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: זה לא יפגע באיכות?, Source Nodes

### Community 151 - "Q: בוא נתכנן איך לממש את זה"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: בוא נתכנן איך לממש את זה, Source Nodes

### Community 152 - "Q: תממש את זה ואני רוצה שזה יהיה בpolling ולא בstream כמו שעכשוי"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: תממש את זה ואני רוצה שזה יהיה בpolling ולא בstream כמו שעכשוי, Source Nodes

### Community 153 - "Q: i want cllckable questions and theres alweys place that he say somthing like רשמתי את רשימת העובדים ואת ימי הפעילות (ראשון עד חמישי). but does nothing"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: i want cllckable questions and theres alweys place that he say somthing like רשמתי את רשימת העובדים ואת ימי הפעילות (ראשון עד חמישי). but does nothing, Source Nodes

### Community 154 - "Q: תעצב לי tutorial למערכת עם סקרינשוטים והכל לכל פונקציונליות"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: תעצב לי tutorial למערכת עם סקרינשוטים והכל לכל פונקציונליות, Source Nodes

### Community 155 - "Q: הראיון ארוך וחוזר על שאלות, ויצירת לוח המשמרות הראשוני לפעמים טועה"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: הראיון ארוך וחוזר על שאלות, ויצירת לוח המשמרות הראשוני לפעמים טועה, Source Nodes

### Community 156 - "Q: בוא נחשוב איך נשפר את חווית הראיון היא משמעותית מאוד"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: בוא נחשוב איך נשפר את חווית הראיון היא משמעותית מאוד, Source Nodes

### Community 157 - "Q: תבנה"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: תבנה, Source Nodes

### Community 158 - "Q: היום הבעיה החמורה היא שהמידע שנשמר בראיון לא עובר במצב לטוב לתהליך בניית הסידור איך אתה מציע שנעשה את זה ונמקסם על זה"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: היום הבעיה החמורה היא שהמידע שנשמר בראיון לא עובר במצב לטוב לתהליך בניית הסידור איך אתה מציע שנעשה את זה ונמקסם על זה, Source Nodes

### Community 159 - "Q: עכשיו יש לי בעיה אני יוצר סידור אוטומטי אבל המודל מחזיר תשובה חיובית ו200 api אבל ui מחזיר שגיאת רשת 500"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: עכשיו יש לי בעיה אני יוצר סידור אוטומטי אבל המודל מחזיר תשובה חיובית ו200 api אבל ui מחזיר שגיאת רשת 500, Source Nodes

### Community 160 - "Q: אני רוצה לשנות את ההמשגות ואת היכולות של המערכת אני רוצה לשנות את המערכת לשיבוצים צבאים תוסיף סבב א או ב או תלתון א ב ג ומתי סבב או תלתון סוגרים בפעם הראשונה אילוצים קבוע או זמני סוג משמרת חפיפה כמה תקינה תקן מוזר נחפף/מילואים אני רוצה להגדיר את כל המערכת ידנית"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: אני רוצה לשנות את ההמשגות ואת היכולות של המערכת אני רוצה לשנות את המערכת לשיבוצים צבאים תוסיף סבב א או ב או תלתון א ב ג ומתי סבב או תלתון סוגרים בפעם הראשונה אילוצים קבוע או זמני סוג משמרת חפיפה כמה תקינה תקן מוזר נחפף/מילואים אני רוצה להגדיר את כל המערכת ידנית, Source Nodes

### Community 161 - "Q: I want fulley working co pilot better at the ui better the ability’s"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: I want fulley working co pilot better at the ui better the ability’s, Source Nodes

### Community 162 - "Q: בשיבוץ למשמרות התשובה מהמודל מגיעה תוך 120 עד 300 שניות תוודא שהui לא מחזיר לי timeout כי עכשיו הוא מחזיר"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: בשיבוץ למשמרות התשובה מהמודל מגיעה תוך 120 עד 300 שניות תוודא שהui לא מחזיר לי timeout כי עכשיו הוא מחזיר, Source Nodes

### Community 163 - "Q: היום אני חוטף שגיאות של שגיאות רשת אבל המודל חוזר ומחזיר תשובה תעשה את זה לא בסטרימינג אלא בפולינג ככה שהכל יעבוד כמו שצריך בנוסף אני רוצה ממש אופציה לפתוח ולשבץ יום ספציפי כמו כפתור על יום ואז לתת הנחיות על הלוח אני רוצה שסוכן וקופיילוט יתאחדו אני רוצה שתשפר את הפרומפטים לסגירות ליציאות היום הוא מאזן בין הסבבים אבל לא מבין שזה סגירות שבתות סבבים"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: היום אני חוטף שגיאות של שגיאות רשת אבל המודל חוזר ומחזיר תשובה תעשה את זה לא בסטרימינג אלא בפולינג ככה שהכל יעבוד כמו שצריך בנוסף אני רוצה ממש אופציה לפתוח ולשבץ יום ספציפי כמו כפתור על יום ואז לתת הנחיות על הלוח אני רוצה שסוכן וקופיילוט יתאחדו אני רוצה שתשפר את הפרומפטים לסגירות ליציאות היום הוא מאזן בין הסבבים אבל לא מבין שזה סגירות שבתות סבבים, Source Nodes

### Community 164 - "Q: היי היום תהליך בניית הסידור על ידי llm עובד לסירוגין כבד ואיטי ספר לי איך הוא עובד ונחשוב על איך לתקן אותו זה הפונקצינואליות הראשית למערכת"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: היי היום תהליך בניית הסידור על ידי llm עובד לסירוגין כבד ואיטי ספר לי איך הוא עובד ונחשוב על איך לתקן אותו זה הפונקצינואליות הראשית למערכת, Source Nodes

### Community 165 - "ApplyRequest"
Cohesion: 0.50
Nodes (3): ApplyRequest, Confirm a proposal. The manager's reason is required by now., model_validator

### Community 166 - "ConstraintRequest"
Cohesion: 0.50
Nodes (3): ConstraintRequest, Record a constraint for an employee.      `source` distinguishes the manager ent, field_validator

### Community 169 - "test_literal_paths_are_not_read_as_schedule_ids"
Cohesion: 0.67
Nodes (3): parametrize, `/{schedule_id}` is declared last; these must not fall into it., test_literal_paths_are_not_read_as_schedule_ids()

### Community 170 - "test_a_member_cannot_reach_any_mutation"
Cohesion: 0.67
Nodes (3): parametrize, D5, enforced by `guards.boss()` rather than by convention.      Parameterised ov, test_a_member_cannot_reach_any_mutation()

### Community 171 - "context"
Cohesion: 0.67
Nodes (3): client(), context(), fixture

## Knowledge Gaps
- **253 isolated node(s):** `pakash-backend`, `config`, `nextConfig`, `name`, `version` (+248 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **43 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Work-memory lessons

**Preferred sources** — corroborated by past sessions; start here.
- `Interview Workflow` (14× useful, score=12.086335331) _(code changed — re-verify)_
- `OpenAI-Compatible JSON Client` (9× useful, score=7.756433484)
- `Chat-First Frontend` (7× useful, score=6.26520291) _(code changed — re-verify)_
- `Schedule Generation` (6× useful, score=5.543339992) _(code changed — re-verify)_
- `Agent Decides; Code Audits` (6× useful, score=5.292172286) _(code changed — re-verify)_
- `Scheduling Persistence Schema` (4× useful, score=3.515433798)
- `Shift Loading and Generation` (3× useful, score=2.827871444) _(code changed — re-verify)_
- `Per-Workplace Shift Vocabulary` (3× useful, score=2.513635279) _(code changed — re-verify)_
- `Layout Inference Importer` (2× useful, score=1.793361595) _(code changed — re-verify)_

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentError` connect `API Routers Package` to `.apply`, `Scheduling Runtime Architecture`, `_RepoWithPreferences`, `Backend Error Hierarchy`, `Product Capabilities`, `Advisory Rules and UI`, `Application Settings`, `.claim`, `Runtime Settings Package`, `_NoModel`, `scheduler.py`, `ConflictError`, `tools.py`, `test_workspace.py`, `test_interview_api.py`, `test_clarification.py`, `ProfileService`, `interview_service.py`, `_ScriptedLlm`, `test_export.py`, `ScheduleRepository`, `test_agent_api.py`, `test_llm_client.py`, `changes.py`, `openai_client.py`, `.get`, `PlanningAgent`, `test_background_learning.py`, `BriefingAgent`, `schedule_service.py`, `test_importer.py`, `build_slots`, `_FakeScheduleRepo`, `planner.py`, `importer.py`, `ScheduleService`, `infer`, `deterministic_scheduler.py`, `.get`, `OpenAIJsonClient`, `ChangeAgent`, `EmployeeService`, `WorkspaceService`, `test_settings_api.py`, `CopilotRepository`, `._view`, `briefing.py`, `test_scheduler.py`, `employee_service.py`, `_ScriptedLlm`, `test_error_handlers.py`, `load`, `.start_generation`, `_iso_date`, `_Repo`, `_require_rotation_placement`, `extract_model_ids`, `_Repo`, `Interpretation`, `read_grids`, `_FakeRepository`, `_NoModel`, `test_deterministic_scheduler.py`?**
  _High betweenness centrality (0.251) - this node is a cross-community bridge._
- **Why does `audit()` connect `Repository Package` to `simulate.py`, `Layered Backend Build Plan`, `deterministic_scheduler.py`, `Live Runtime Settings`, `.get`, `personal_summary`, `rotation.py`, `simulate`, `test_rotation.py`, `schedule_service.py`, `scheduler.py`, `build_slots`, `tools.py`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Why does `ScheduleService` connect `ScheduleService` to `.apply`, `_RepoWithPreferences`, `Backend Error Hierarchy`, `Product Capabilities`, `Advisory Rules and UI`, `API Routers Package`, `_NoModel`, `tools.py`, `ProfileService`, `test_agent_api.py`, `.get`, `PlanningAgent`, `test_background_learning.py`, `BriefingAgent`, `schedule_service.py`, `_FakeScheduleRepo`, `.get`, `ChangeAgent`, `._view`, `worker.py`, `._remember_patterns`, `_ScriptedLlm`, `.start_generation`, `_require_rotation_placement`, `._requeue_failed_span`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `AgentError` (e.g. with `BriefingAgent` and `ChangeAgent`) actually correct?**
  _`AgentError` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `ScheduleService` (e.g. with `BriefingAgent` and `ChangeAgent`) actually correct?**
  _`ScheduleService` has 19 INFERRED edges - model-reasoned connections that need verification._
- **What connects `pakash-backend`, `config`, `nextConfig` to the rest of the system?**
  _253 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Import and Layout Inference` be split into smaller, more focused modules?**
  _Cohesion score 0.05187074829931973 - nodes in this community are weakly interconnected._