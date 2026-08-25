/** Mirrors `backend/app/api/contracts.py`. */

/** A clickable answer. `label` captions the button; `answer` is the full
 *  sentence sent verbatim as the boss's own message when it is clicked. */
export interface Option {
  label: string;
  answer: string;
}

/** The single question a turn asks, with the agent's own recommendation. */
export interface Question {
  topic_id: string;
  question: string;
  recommendation: string;
  why: string;
  options: Option[];
}

export interface Message {
  role: "assistant" | "user";
  content: string;
  question: Question | null;
  options: Option[];
  recommendation: string | null;
  mode?: "" | "answer" | "correction";
}

/** Facts inferred from an existing schedule before the first question. */
export interface InterviewSeed {
  workplace_name?: string;
  source_files?: string[];
  employees?: Record<string, string[]>;
  shifts?: Record<string, string[]>;
  starts_on?: string;
  ends_on?: string;
}

/** The workplace profile as it stands. Only the fields the summary screen
 *  reads are named — the rest is shown as JSON, since the interview owns the
 *  full shape and duplicating it here would drift. */
export interface WorkplaceProfile {
  workplace?: {
    name?: string;
    mission?: string;
    summary?: string;
    planning_horizon?: string;
    operating_days?: string[];
    rotation_mode?: "round" | "triplet";
    first_closure_group?: string;
    first_closure_date?: string;
    general_exit_schedule?: string;
    enabled_exit_patterns?: Array<"triplet" | "hamshushim" | "shushim">;
    rotation_a_unavailability?: Array<{
      days: string[];
      shifts: string[];
      start_time: string;
      end_time: string;
      reason: string;
    }>;
  };
  employees?: unknown[];
  shifts?: unknown[];
  rules?: unknown[];
  summary?: string;
  /** Present only on a profile whose interview was ended early. Its absence
   *  means the interview was confirmed the ordinary way, so nothing is
   *  outstanding — written by `interview_service.end`, read here and by
   *  `bl/tools.py`'s `profile_gaps`. */
  completeness?: ProfileCompleteness;
  [key: string]: unknown;
}

/** What an interview ended early still owes.
 *
 *  Two lists because they answer different questions. `missing_topics` is
 *  what the scheduler cannot run without; `open_points` is what the agent
 *  itself flagged as unsettled — real, but a manager can schedule around
 *  them. */
export interface ProfileCompleteness {
  complete: boolean;
  missing_topics: string[];
  open_points: string[];
  resolved?: string[];
}

export interface InterviewTurn {
  session_id: string;
  status: "processing" | "question" | "complete" | "error";
  /** What the agent says this turn, above the question. */
  reply: string;
  question: Question | null;
  /** What is settled, and what still is not — the interview's own state,
   *  rendered beside the conversation so progress is visible. */
  resolved: string[];
  open_points: string[];
  /** The summary is on screen awaiting a yes. `ready` follows on the turn
   *  after the boss confirms it. */
  awaiting_confirmation: boolean;
  ready: boolean;
  /** The profile so far. Present on every turn, so the summary panel fills
   *  in as the interview proceeds. */
  draft: WorkplaceProfile | null;
  turns: Message[];
  /** The confirmed result. Null until the interview is complete — `draft` is
   *  a proposal, this is the durable answer. */
  profile: WorkplaceProfile | null;
  error?: string | null;
}

/** Mirrors `RuntimeSettings` in `backend/app/common/runtime_settings/`.
 *
 *  Secrets arrive masked (`"********"`) when one is stored and `""` when none
 *  is, and sending the mask back means "unchanged" — so the panel treats these
 *  as opaque strings rather than values it may display or diff. */
export interface RuntimeSettings {
  database_url: string;
  database_user: string;
  database_password: string;
  database_host: string;
  database_port: number | null;
  database_name: string;
  database_schema: string;
  llm_model: string;
  /** Per-role model ids and endpoints. Empty values fall back to the general
   *  model/URL, keeping a single-model deployment unchanged. */
  llm_model_fast: string;
  llm_model_default: string;
  llm_model_advanced: string;
  llm_base_url_fast: string | null;
  llm_base_url_default: string | null;
  llm_base_url_advanced: string | null;
  llm_diet_mode: boolean;
  llm_repetition_penalty: number;
  llm_timeout_seconds: number;
  llm_queue_seconds: number;
  llm_base_url: string | null;
  openai_api_key: string;
}

/** Who the current visitor is inside a workspace.
 *
 *  `boss` authors — the interview, the settings, the schedule.
 *
 *  `member` is the share link: it reads the published roster and carries no
 *  identity at all (D10), so nothing personal can be scoped to it.
 *
 *  `employee` is a claimed identity (D14). It reads its *own* hours and may
 *  submit a constraint **request** — and nothing else. It cannot assign,
 *  move, or publish; those still answer only to `boss`.
 *
 *  The role arrives from the signed session cookie and is never chosen by the
 *  client, so this type describes what the server said, not a preference the
 *  UI may set. */
export type Role = "boss" | "member" | "employee";

/** A team on the login picker. Deliberately carries no secrets — this list
 *  is served before anyone has authenticated. */
export interface TeamSummary {
  id: string;
  name: string;
}

/** The signed-in workspace.
 *
 *  `member_token` is the share link's secret half and is present only for a
 *  boss; a member gets null, having no reason to re-read the credential they
 *  arrived on. */
export interface Workspace {
  id: string;
  name: string;
  role: Role;
  member_token: string | null;
  /** Interviews recorded before workspaces existed, adopted by the first
   *  team created. Present only on that first creation. */
  claimed_sessions?: number | null;
}

/** A workspace plus the profile its interview produced. */
export interface TeamView extends Workspace {
  profile: WorkplaceProfile | null;
}

/** One advisory finding from `bl/audit.py`.
 *
 *  Advisory is the whole contract: a schedule carrying warnings is still a
 *  valid schedule the manager may knowingly accept, so these render as
 *  non-blocking banners and never gate a save (D3). */
export interface ScheduleWarning {
  code: string;
  severity: "warning" | "notice";
  message: string;
  employee: string;
  date: string;
  shift: string;
  details: Record<string, unknown>;
}

/** One shift on one date — the thing a person is assigned into. */
export interface Slot {
  id: string;
  shift_name: string;
  slot_date: string;
  start_time: string;
  end_time: string;
  headcount: number;
  requires_shift_manager: boolean;
  is_on_call: boolean;
}

/** A person on a slot, with the agent's reason.
 *
 *  `reason` is never empty — the backend refuses to store an assignment
 *  without one, because an assignment nobody can account for is what D8
 *  exists to prevent. */
export interface Assignment {
  id: string;
  employee: string;
  shift: string;
  date: string;
  reason: string;
  slot_id: string;
  /** Where the row came from (D18) — the agent generated it, the manager
   *  placed it by hand, or it was read out of an imported file. Provenance,
   *  not authorship: it records where the information came from, exactly as
   *  `Constraint.source` does. */
  source: AssignmentSource;
}

/** A manager-selected placement that schedule generation must preserve. */
export interface RequiredAssignment {
  employee: string;
  shift: string;
  date: string;
}

/** How an assignment got into the schedule (D18). */
export type AssignmentSource = "agent" | "manager" | "imported";

export interface GenerationDay {
  date: string;
  status: "pending" | "running" | "complete" | "failed";
  attempts: number;
  error: string;
  metrics: {
    duration_ms?: number;
    returned?: number;
    accepted?: number;
    rejected?: number;
    warnings?: number;
    repaired?: boolean;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
  };
}

export interface GenerationProgress {
  /** `cancelled` is the manager stopping the wait, not a failure — every
   *  day already built is kept and resuming continues from the next one. */
  status: "" | "running" | "complete" | "failed" | "cancelled";
  current_date: string;
  total_days: number;
  completed_days: number;
  failed_days: number;
  days: GenerationDay[];
  /** When a worker last said it was still on this job, UTC ISO-8601.
   *
   *  What separates a slow model from a hung one: with no LLM timeout
   *  configured both look like `running` forever, and only a beat that
   *  stops tells the poller the job has lost its worker. Empty on a job
   *  opened before the field existed, which reads as "cannot tell". */
  heartbeat?: string;
  /** Whether a stop has been asked for. A job can still be `running` with
   *  this true for as long as the current model call takes to answer. */
  cancel_requested?: boolean;
}

/** What the poller reads while a period is being built.
 *
 *  Deliberately not a `Schedule`: this is asked for every second or two, and
 *  the full period carries every slot, every assignment and a fresh audit
 *  over both. The grid is fetched when the counter moves. */
export interface ScheduleProgress {
  id: string;
  status: "draft" | "published";
  generation: GenerationProgress;
}

/** One living period (D4) — edited in place, never versioned. */
export interface Schedule {
  id: string;
  starts_on: string;
  ends_on: string;
  status: "draft" | "published";
  slots: Slot[];
  assignments: Assignment[];
  warnings: ScheduleWarning[];
  notes: string[];
  summary: string;
  generation: GenerationProgress;
  /** The id a manual assignment landed on. Empty on every other response.
   *  Placing the same person on the same slot twice conflicts silently, so
   *  this is how the client tells "placed" from "was already there". */
  assigned?: string;
}

export interface SchedulePeriod {
  id: string;
  starts_on: string;
  ends_on: string;
  status: "draft" | "published";
}

/** Somebody else who could take the slot the manager was aiming at.
 *
 *  `hours` is what they already carry in this period, which is why the list
 *  arrives sorted by it: the lightest week is offered first. `why` is the
 *  Hebrew sentence the backend wrote — assembling it here from fragments is
 *  the one place a Latin-script assumption creeps back into an RTL product. */
export interface AlternativeEmployee {
  employee: string;
  hours: number;
  why: string;
}

/** Somewhere else this same person could go, near the date that was wanted. */
export interface AlternativeSlot {
  shift_name: string;
  slot_date: string;
  distance: number;
  why: string;
}

/** Deterministic ways out of a placement that warns. */
export interface Alternatives {
  employees: AlternativeEmployee[];
  slots: AlternativeSlot[];
}

/** What `bl/placement.py` makes of a placement the manager has not made yet.
 *
 *  Computed by pure Python arithmetic with **no model call**, which is what
 *  lets the board validate a drag, explain it in Hebrew, and offer a way out
 *  while the agent is slow or unavailable.
 *
 *  `blocking` is always false and the field exists to say so: the audit
 *  advises and never gates (D3). A manager may place somebody this reports
 *  on, and the write that follows will store it — checking first only moves
 *  the warning to before the click, where it is cheaper to act on. */
export interface PlacementCheck {
  ok: boolean;
  blocking: boolean;
  reasons: string[];
  warnings: ScheduleWarning[];
  eligible: boolean;
  alternatives: Alternatives;
  candidates: PlacementCandidate[];
}

export interface PlacementCandidate {
  employee: string;
  available: boolean;
  reasons: string[];
  hours: number;
  is_shift_manager: boolean;
  can_train: boolean;
}

/** A recorded availability constraint.
 *
 *  An empty `shift_name` covers the whole day. `source` says where the
 *  information came from — employees have no account and never write here
 *  themselves (D5/D10), so `employee_reported` means the manager wrote down
 *  what someone told them. */
export interface Constraint {
  id: string;
  employee: string;
  constraint_date: string;
  shift_name: string;
  available: boolean;
  start_time: string;
  end_time: string;
  is_hard: boolean;
  reason: string;
  source: "manager" | "agent" | "employee_reported" | "interview";
}

/** One append-only change-log row. Both reasons are present because they
 *  answer different questions (D8). */
export interface ChangeEntry {
  id: string;
  action: string;
  employee: string;
  replaced_employee: string;
  slot_date: string | null;
  shift_name: string;
  reason: string;
  agent_reason: string;
  created_at: string | null;
}

/* -- the period in numbers ------------------------------------------------
 *
 * Every figure below is computed by `bl/audit.py` and rendered as given.
 * None of it is recomputed in the browser, for the same reason the employee's
 * hours are not: a chart derived from a second implementation would
 * eventually disagree with the warning printed beneath it, and a manager
 * cannot tell by eye which of the two is lying.
 *
 * All of it reports and none of it grades. There is no score here, no target,
 * and no threshold a period passes or fails — coverage at 80% is a fact about
 * the week, not a verdict on it (D3).
 */

/** Filled seats against required seats.
 *
 *  Seats rather than slots: a shift needing three people with two on it is
 *  two thirds covered, and rounding that up to "filled" would hide exactly
 *  the understaffing the number exists to reveal. */
export interface Coverage {
  required: number;
  assigned: number;
  unfilled_slots: number;
  percent: number;
}

/** One shift name's share of the period, in the workplace's own vocabulary
 *  (D9). Shifts nobody was put on are present at zero — an absent bar reads
 *  as "no such shift" rather than "nobody scheduled". */
export interface ShiftLoad {
  shift: string;
  count: number;
  hours: number;
  is_on_call: boolean;
}

/** One date's load. Days nobody worked are present as zeros so the chart
 *  shows the gap instead of closing it up. */
export interface DayLoad {
  date: string;
  weekday: string;
  count: number;
  hours: number;
  on_call: number;
}

/** One person's load, with the counts behind the hours — so two people on
 *  equal hours who are not carrying an equal week are distinguishable. */
export interface EmployeeLoad {
  employee: string;
  hours: number;
  shifts: number;
  on_call: number;
  days: number;
}

/** How many audit findings of one code. A count, never a score. */
export interface WarningCount {
  code: string;
  severity: "warning" | "notice";
  count: number;
}

/** How constrained the period was, and how often that was overridden.
 *
 *  `honored` is the figure the warning list structurally cannot give: a
 *  constraint the schedule respected produces no warning, so it leaves no
 *  trace there at all. */
export interface ConstraintPressure {
  blocked: number;
  people: number;
  conflicts: number;
  honored: number;
}

/** The current period in numbers, for the control room's charts. */
export interface ShiftStats {
  total_hours: number;
  total_shifts: number;
  people_working: number;
  coverage: Coverage;
  by_shift: ShiftLoad[];
  by_day: DayLoad[];
  by_employee: EmployeeLoad[];
  warning_counts: WarningCount[];
  constraint_pressure: ConstraintPressure;
}

/** Everything the management area opens with, in one call. */
export interface ManagementOverview {
  profile: WorkplaceProfile | null;
  employees: Record<string, unknown>[];
  shifts: Record<string, unknown>[];
  schedule: Schedule | null;
  periods: SchedulePeriod[];
  availability: Constraint[];
  changes: ChangeEntry[];
  /** The charts' numbers, for the period in `schedule`. Part of the same
   *  call so the figures and the calendar they describe can never be one
   *  refresh apart. */
  stats: ShiftStats;
}

/** One concrete move inside a proposal. */
export interface Operation {
  action: "assign" | "remove" | "swap";
  employee: string;
  shift: string;
  date: string;
  reason: string;
  with_employee?: string;
  with_shift?: string;
  with_date?: string;
}

export interface ProfileOperation {
  action: "add_employee" | "update_employee" | "add_shift" | "update_shift";
  target: string;
  item: Record<string, unknown>;
}

/** What the agent would do, and why. **Nothing has been applied.**
 *
 *  `needs_reason` true means the agent asked the manager why the change is
 *  happening and is deliberately proposing nothing until they answer — a
 *  missing reason is met with a question, never a rejection (D8). */
export interface Proposal {
  schedule_id: string;
  reply: string;
  needs_reason: boolean;
  agent_reason: string;
  stated_reason: string;
  operations: Operation[];
  profile_operations: ProfileOperation[];
  constraints: Record<string, unknown>[];
  warnings: ScheduleWarning[];
}

/* -- the agent speaking first (D15) ---------------------------------------
 *
 * Note what a briefing does NOT carry: operations. There is no field here a
 * confirmation could read, because nothing in a briefing is ever applied. A
 * `suggestion` is text for the composer — the manager still says it, and the
 * ordinary propose-then-confirm path still runs.
 */

export type BriefingKind =
  | "risk"
  | "fairness"
  | "gap"
  | "request"
  | "pattern";

/** Why the agent is speaking. The backend branches on these by name. */
export type BriefingTrigger =
  | "opened"
  | "changed"
  | "publishing"
  | "periodic";

export interface BriefingItem {
  text: string;
  kind: BriefingKind;
  /** The sentence the manager could send. Empty when there is nothing to do. */
  suggestion: string;
}

export interface Briefing {
  headline: string;
  items: BriefingItem[];
  /** The honest all-clear, and the common case by design. */
  quiet: boolean;
}

/* -- the employee's own area (D14) ----------------------------------------
 *
 * Note what these types do NOT carry: the employee's own name on any request
 * body. It is taken from the signed session cookie server-side, so there is
 * no field here for a client to put a colleague's name in.
 */

/** One shift as it appears in a personal list. */
export interface PersonalShift {
  date: string;
  shift: string;
  hours: number;
  is_on_call: boolean;
  weekday: string;
}

/** Hours grouped by shift name, so a total is legible rather than disputable. */
export interface ShiftBreakdown {
  shift: string;
  count: number;
  hours: number;
}

/** One person's own totals, computed by `bl/audit.py` — the same arithmetic
 *  the manager's warnings come from, so the two can never disagree. */
export interface PersonalSummary {
  employee: string;
  total_hours: number;
  shift_count: number;
  days_worked: number;
  /** On-call is split out because it is the number that surprises people: an
   *  eight-hour on-call may count as four, which looks like a bug unless the
   *  breakdown says otherwise (D9). */
  on_call_count: number;
  on_call_hours: number;
  worked_hours: number;
  by_shift: ShiftBreakdown[];
  by_week: { week: string; hours: number }[];
  shifts: PersonalShift[];
  /** Only warnings naming this person. Team-wide ones are the manager's. */
  warnings: ScheduleWarning[];
  constraints: Constraint[];
}

/** Hours against the team average — the number that answers "why is it
 *  always me". A report, never a rule (D3). */
export interface Fairness {
  average_hours: number;
  people: { employee: string; hours: number; delta: number }[];
}

/** A constraint an employee asked for. **Pending changes nothing** — it is
 *  invisible to the audit until a manager approves it (D14). */
export interface ConstraintRequestRow {
  id: string;
  employee: string;
  constraint_date: string;
  shift_name: string;
  available: boolean;
  reason: string;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  /** The manager's answer. Required on a rejection — a refusal that says
   *  nothing is how a submission channel stops being used. */
  decided_reason: string;
  decided_at: string | null;
  created_at?: string | null;
}

/** A proposed trade of shifts between two employees.
 *
 *  Its lifecycle has one more state than a constraint request:
 *  `awaiting_counterparty` precedes `pending`, because a swap is not the
 *  manager's to rule on until the *other* employee has agreed. `declined` is
 *  that colleague's refusal, kept apart from the manager's `rejected` so the
 *  requester can tell who said no and whether it is worth asking again. */
export interface SwapRow {
  id: string;
  schedule_id: string;
  requester: string;
  requester_date: string;
  requester_shift: string;
  counterparty: string;
  counterparty_date: string;
  counterparty_shift: string;
  reason: string;
  status:
    | "awaiting_counterparty"
    | "pending"
    | "approved"
    | "rejected"
    | "declined"
    | "withdrawn";
  /** null while the colleague has not replied — distinct from false, which
   *  is a decline. "Has not answered" and "said no" are different states. */
  counterparty_agreed: boolean | null;
  counterparty_replied_at: string | null;
  decided_reason: string;
  decided_at: string | null;
  created_at?: string | null;
  /** Which side of the swap the reader is on. Computed server-side: one row
   *  serves two people asking different questions, and deciding it here
   *  would mean comparing names in every component that renders one. */
  is_requester?: boolean;
  is_counterparty?: boolean;
}

/** Who is on shift alongside this person, read off the same assignments as
 *  the grid so it cannot drift from it. */
export interface Teammates {
  date: string;
  shift: string;
  with: string[];
}

/** Everything the personal area opens with, in one call. */
export interface EmployeeView {
  employee: string;
  schedule: Schedule | null;
  summary: PersonalSummary;
  fairness: Fairness;
  teammates: Teammates[];
  requests: ConstraintRequestRow[];
  /** Swaps naming this person on either side. */
  swaps: SwapRow[];
  /** How many are waiting on *their* answer. Kept separate from `unseen`:
   *  "something moved" and "somebody is waiting on you" are different, and
   *  one badge for both hides the half that has a deadline. */
  swaps_awaiting_me: number;
  /** Only log entries naming this person — the full log is the manager's and
   *  carries other people's stated reasons. Each carries `is_new` (D16). */
  changes: EmployeeChange[];
  /** How many of those landed since this person last acknowledged. The
   *  screen leads with it: an employee whose shift moved yesterday should
   *  not have to compare a grid against memory to find out. */
  unseen: number;
  shifts: Record<string, unknown>[];
}

/** A change-log entry as the employee sees it — the manager's row plus
 *  whether it has been read yet.
 *
 *  `is_new` is computed server-side against the employee's own
 *  acknowledgement, never in the browser: local state could disagree with
 *  what the server holds and would reset on every device. */
export interface EmployeeChange extends ChangeEntry {
  is_new: boolean;
}

/** A roster name and whether it is already claimed. Carries no last-seen
 *  time: this screen is reachable by anyone holding the share link. */
export interface RosterName {
  employee: string;
  claimed: boolean;
}

/** A claim, as the manager's panel sees it. */
export interface EmployeeIdentity {
  employee: string;
  created_at: string | null;
  last_seen_at: string | null;
}

/** One assignment as the importer read it, before anything is confirmed.
 *
 *  `shift` may be empty: a sheet of dates and people carries no shift
 *  information at all, and an empty name is how that absence stays visible
 *  rather than being answered with an invented one (D9). The confirm screen
 *  is where the manager supplies it. */
export interface ReadAssignment {
  employee: string;
  shift: string;
  date: string;
  reason?: string;
}

/** An unavailability the sheet stated outright (`לא זמינה` in a cell).
 *
 *  `employee` may be empty when the file never attributed the marker to
 *  anybody — reported as such rather than guessed at. */
export interface ImportedConstraint {
  employee: string;
  date: string;
  shift: string;
  reason: string;
}

/** A rule the history suggests, which the manager has not yet accepted.
 *
 *  `approved` is always false from the server — a candidate becomes a rule
 *  only by the manager saying so, never by having been proposed (D7). */
export interface CandidateRule {
  text: string;
  kind: "hard" | "soft";
  evidence: string;
  confidence: "high" | "medium" | "low";
  approved: boolean;
}

/** One combination the manager kept correcting by hand.
 *
 *  Keyed on person, shift and weekday rather than on the date: a rule is
 *  about Fridays, not about the 3rd of March. `reasons` are the manager's own
 *  words, verbatim and de-duplicated — they are what makes a candidate rule
 *  checkable, since a bare count says only that something happened often. */
export interface RepeatedCorrection {
  employee: string;
  shift: string;
  weekday: string;
  count: number;
  reasons: string[];
  first_seen: string;
  last_seen: string;
}

/** Rules the change log suggests, with the corrections behind them.
 *
 *  The other end of what an import learns: uploaded files say what the
 *  workplace *did*, while this says what the manager **decided** and why.
 *  Nothing here is stored — these are proposals approved one at a time (D7),
 *  exactly like the candidates an import produces. */
export interface ChangeLearning {
  corrections: {
    repeated: RepeatedCorrection[];
    totals: { changes: number; corrections: number; people: number };
    /** Combinations corrected exactly once, and therefore withheld. Shown as
     *  context, never as a rule: one correction is not a pattern. */
    single_corrections: number;
  };
  candidate_rules: CandidateRule[];
  notes: string[];
}

/** What one uploaded file was understood to say. */
export interface ImportedPeriod {
  filename: string;
  /** `shift_major`, `person_major`, or `date_only` — which axes the sheet
   *  turned out to use. Shown to the manager because a misread layout is the
   *  one error that makes everything else wrong. */
  layout: string;
  shifts: string[];
  people: string[];
  dates: string[];
  starts_on: string;
  ends_on: string;
  assignments: ReadAssignment[];
  unavailability: ImportedConstraint[];
  warnings: string[];
  summary: string;
}

/** A file that could not be read, reported beside the ones that could. */
export interface ImportFailure {
  filename: string;
  error: string;
}

/** The interpretation the manager confirms before anything is stored (D7).
 *
 *  Producing this writes nothing. `confirmImport` is the only call that
 *  persists, which is what makes the confirmation structural rather than a
 *  dialog in front of a write that already happened. */
export interface ImportPreview {
  periods: ImportedPeriod[];
  failures: ImportFailure[];
  observations: {
    periods?: { starts_on: string; ends_on: string; days: number };
    people?: {
      employee: string;
      assignments: number;
      by_shift: Record<string, number>;
      by_weekday: Record<string, number>;
      always: string[];
      never: string[];
      first_seen: string;
      last_seen: string;
      enough_data: boolean;
    }[];
    coverage?: {
      by_weekday: Record<string, number>;
      by_shift: Record<string, number>;
      weekdays_never_seen: string[];
    };
    totals?: { assignments: number; people: number; shifts: string[] };
  };
  candidate_rules: CandidateRule[];
  notes: string[];
}

/** One tool the agent ran while working out an answer.
 *
 *  Rendered under the answer so the manager can see which facts it rests on.
 *  Transparency is the requirement here, not debugging output: an answer
 *  whose checks are invisible has to be taken on faith, and the whole point
 *  of deterministic tools is that it does not. */
export interface AgentStep {
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
}

/** What the agent made of a question. **Carries no operations.**
 *
 *  There is no field here that `apply` could read — the same property
 *  `Briefing` has, and for the same reason (D15). A question that turns out
 *  to want a change comes back with `needs_confirmation`, and the manager
 *  still sends it through propose-then-confirm.
 *
 *  `used_model` says whether this came from the model or from the
 *  deterministic reader. Surfaced rather than hidden: the fallback answers a
 *  narrower set of questions, and saying so is what keeps that honest. */
export interface AgentAnswer {
  answer: string;
  steps: AgentStep[];
  needs_confirmation: boolean;
  /** The answer is a focused question and the conversation should continue. */
  needs_input: boolean;
  used_model: boolean;
  understood: boolean;
  schedule_id: string;
}

/** Required against assigned, before and after a simulated change. */
export interface CoverageImpact {
  required: number;
  assigned_before: number;
  assigned_after: number;
  delta: number;
  percent_before: number;
  percent_after: number;
}

/** One affected person's hours, before and after. */
export interface WorkloadImpact {
  employee: string;
  hours_before: number;
  hours_after: number;
  delta: number;
}

/** An operation the simulation could not apply, and why. */
export interface SkippedOperation {
  action: string;
  employee: string;
  shift: string;
  date: string;
  why: string;
}

/** The period as a set of operations would leave it, computed in memory.
 *
 *  **`simulated` is always true**, and the UI colours off it: a simulation
 *  must never render as something that landed. Approving one is an ordinary
 *  `applyChange` with the manager's reason — there is no shortcut from here
 *  to a write (D8/D12). */
export interface Simulation {
  simulated: boolean;
  applied: boolean;
  operations: Operation[];
  skipped: SkippedOperation[];
  introduced: ScheduleWarning[];
  resolved: ScheduleWarning[];
  warnings_after: ScheduleWarning[];
  coverage: CoverageImpact;
  workload: WorkloadImpact[];
  affected: string[];
  schedule_id: string;
}

export type PreferenceKind =
  | "staffing"
  | "notification"
  | "employee"
  | "shift"
  | "general";

export type PreferenceStatus = "suggested" | "active" | "archived";

/** One standing operational preference this workplace has taught the agent.
 *
 *  Not a rule (D1/D2 govern those) and not a constraint (`availability` is
 *  what the audit counts). Standing context the agent reads before it
 *  proposes — and a `suggested` one is inert until the manager approves it. */
export interface Preference {
  id: string;
  kind: PreferenceKind;
  subject: string;
  text: string;
  evidence: string;
  status: PreferenceStatus;
  source: string;
}

export type CopilotMode = "observe" | "suggest" | "auto";
export type CopilotItemStatus =
  | "pending"
  | "approved"
  | "dismissed"
  | "applied"
  | "failed"
  | "rolled_back";

export interface CopilotItem {
  id: string;
  kind: "observation" | "proposal" | "failure";
  action_type: string;
  status: CopilotItemStatus;
  title: string;
  detail: string;
  payload: Record<string, unknown>;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
  verification?: Record<string, unknown> | null;
  created_at?: string;
  updated_at?: string;
}

export interface CopilotPermission {
  action_type: string;
  mode: CopilotMode;
  updated_at?: string | null;
}

export interface CopilotInboxData {
  items: CopilotItem[];
  permissions: CopilotPermission[];
  health: CopilotHealth;
}

export interface CopilotHealth {
  queued_jobs: number;
  running_jobs: number;
  last_completed_at?: string | null;
  latest_job?: {
    id: string;
    status: "queued" | "running" | "complete" | "failed";
    attempts: number;
    error?: string;
    created_at?: string;
    started_at?: string | null;
    finished_at?: string | null;
  } | null;
}

export interface CopilotAuditEvent {
  id: string;
  item_id?: string | null;
  event: string;
  actor: string;
  message: string;
  before_state?: Record<string, unknown> | null;
  after_state?: Record<string, unknown> | null;
  verification?: Record<string, unknown> | null;
  created_at?: string;
}
