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

/** The saved workplace profile. Only fields read by the UI are named. */
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
    round_first_closure_group?: string;
    round_first_closure_date?: string;
    triplet_first_closure_group?: string;
    triplet_first_closure_date?: string;
    general_exit_schedule?: string;
    enabled_exit_patterns?: Array<"triplet" | "hamshushim" | "shushim">;
    rotation_closure_windows?: RotationClosureWindow[];
    rotation_presence?: RotationPresenceRule[];
    day_cycles?: DayCycle[];
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
  /** Legacy or partial setup gaps, read by the board and profile tools. */
  completeness?: ProfileCompleteness;
  [key: string]: unknown;
}

export interface RotationGroupRule {
  pattern: "round" | "triplet";
  group: string;
  starts_on: string;
  ends_on: string;
  start_time: string;
  end_time: string;
}

/** When a group leaves and comes back. `*_day` moves the nominal day
 *  (first home day / first base day) by up to three days either way; a
 *  blank time is the start of that day. A layer states only what it changes. */
export interface DayCycleTiming {
  leave_day?: number;
  leave_time?: string;
  return_day?: number;
  return_time?: string;
}

/** A dated change to one departure, matched on its nominal leave day.
 *  An empty `group` applies to every group of the cycle. */
export interface DayCycleTimeChange extends DayCycleTiming {
  group: string;
  starts_on: string;
  ends_on: string;
}

/** A day-based cycle — 11/3, 12/2, שבוע־שבוע. A person joins it with
 *  `exit_pattern = "cycle:<id>"`; the server owns the arithmetic. */
export interface DayCycle extends DayCycleTiming {
  id: string;
  name: string;
  base_days: number;
  home_days: number;
  /** The day the first group starts its stretch on base. */
  anchor_date: string;
  groups: string[];
  /** Days after the anchor each group starts; missing = spread evenly. */
  offsets: Record<string, number>;
  group_times: Record<string, DayCycleTiming>;
  time_changes: DayCycleTimeChange[];
}

export interface RotationClosureWindow extends RotationGroupRule {
  start_day: number;
  end_day: number;
  /** An exception's name, like "פסח". Shown in setup only. */
  note?: string;
}

/** One coming closure of a cycle, as the server will build it. `kind` says
 *  where its hours come from: the default Thursday-to-Sunday, the cycle's
 *  own hours, or a dated exception. Default rows carry no clock; they run
 *  until `handover_shifts` on the Sunday. */
export interface RotationWeekend {
  saturday: string;
  group: string;
  label: string;
  kind: "default" | "regular" | "exception";
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  handover_shifts: string[];
  note?: string;
}

export interface RotationPresenceRule extends RotationGroupRule {
  days: string[];
  shifts: string[];
  available: boolean;
  reason: string;
}

/** What a legacy or partial setup still owes.
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
  /** Per-role model ids, endpoints and API keys. Empty values fall back to
   *  the general model/URL/key, keeping a single-model deployment unchanged.
   *  A role's key travels with its URL, so roles may sit on different
   *  providers. Keys arrive masked, like every other secret. */
  llm_model_fast: string;
  llm_model_default: string;
  llm_model_advanced: string;
  llm_base_url_fast: string | null;
  llm_base_url_default: string | null;
  llm_base_url_advanced: string | null;
  llm_api_key_fast: string;
  llm_api_key_default: string;
  llm_api_key_advanced: string;
  llm_diet_mode: boolean;
  llm_repetition_penalty: number;
  llm_timeout_seconds: number;
  llm_queue_seconds: number;
  /** "", "off", "low", "medium" or "high": how long the model thinks. */
  llm_reasoning_effort: string;
  /** False accepts any TLS certificate from the model server. */
  llm_verify_ssl: boolean;
  llm_base_url: string | null;
  openai_api_key: string;
  /** The constraint solver: seconds per solve and parallel workers. */
  solver_time_limit_seconds: number;
  solver_workers: number;
}

/** Who the current visitor is inside a workspace.
 *
 *  `boss` authors — the profile, the settings, and the schedule.
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

/** One workspace as the צוות משמרות זהב console sees it (D28). Counts only —
 *  never a password hash; the member token only on the single-team detail. */
export interface AdminTeam {
  id: string;
  name: string;
  created_at: string;
  active: boolean;
  notes: string;
  /** Employees the manager listed who have not left. How many there are is
   *  the manager's decision; the console only reports it. */
  employees: number;
  roster_total: number;
  has_profile: boolean;
  shifts: number;
  identities: number;
  periods: number;
  published: number;
  pending_requests: number;
  pending_swaps: number;
  last_activity: string | null;
}

export interface AdminTeamDetail extends AdminTeam {
  member_token: string;
  profile_employees: {
    name: string;
    role: string;
    service_type?: string;
    inactive_from: string | null;
  }[];
  identities_list: {
    employee: string;
    created_at: string;
    last_seen_at: string | null;
  }[];
  periods_list: {
    id: string;
    starts_on: string;
    ends_on: string;
    status: "draft" | "published";
    updated_at: string;
    assignments: number;
  }[];
  recent_changes: {
    action: string;
    employee: string;
    replaced_employee: string;
    slot_date: string | null;
    shift_name: string;
    reason: string;
    created_at: string;
  }[];
}

export interface AdminOverview {
  totals: {
    teams?: number;
    active_teams?: number;
    identities?: number;
    periods?: number;
    assignments?: number;
    changes?: number;
    pending_requests?: number;
    database_bytes?: number;
  };
  database: "ok" | "error";
  model: Record<string, string>;
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
}

/** A workspace plus its saved profile. */
export interface TeamView extends Workspace {
  profile: WorkplaceProfile | null;
  /** What a profile save sends back as `expected_revision`. */
  profile_revision?: number | null;
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

/** Who a person is, as the board card states it.
 *
 *  The card used to spend its last line on `Assignment.reason` — *why* the
 *  agent put this person here. That sentence is a record ([D8](docs/DECISIONS.md))
 *  and it is still stored and still readable, but it answers a question the
 *  manager has already stopped asking by the time they are looking at a
 *  week. Scanning a grid, the question is *who is this* — what they do, which
 *  rotation they are in, whether they can command, whether they are still
 *  being trained in. Those four facts are what makes a cell staffed or only
 *  filled, so those four facts are what the card carries.
 *
 *  Assembled in the board from the roster, not from the assignment: it
 *  describes the person, and it reads the same on every shift they hold. */
export interface CardPerson {
  role: string;
  /** `exit_pattern` and `rotation_group` already rendered together — "סבב א",
   *  "תלתון ג", "חמשושים" for somebody with no group. Empty when the roster
   *  says nothing. */
  rotation: string;
  is_shift_manager: boolean;
  /** `service_type === "overlap"` — נחפף/ת. Someone learning the shift, who
   *  by default does not count toward its staffing, which is exactly the
   *  thing a manager must not have to hover to discover. */
  is_overlap: boolean;
  /** Whether this person fills one of a slot's seats.
   *
   *  Usually the opposite of `is_overlap`, and deliberately its own field
   *  rather than derived from it: `counts_toward_staffing` is what the roster
   *  actually stores and the manager may set it either way — a trainee the
   *  workplace does count, or a full member held off the standard. The badge
   *  answers "who is this"; this answers "is the cell still short", and
   *  `bl/audit.counts_toward_staffing` is the backend's word for the same
   *  question. A cell counted differently here than there is a board that
   *  disagrees with the warning printed under it. */
  counts_toward_staffing: boolean;
}

/** A manager-selected placement that schedule generation must preserve. */
export interface RequiredAssignment {
  employee: string;
  shift: string;
  date: string;
}

/** How an assignment got into the schedule (D18). */
export type AssignmentSource = "agent" | "manager" | "imported";

/** One checkpoint of a build: a span of up to four weeks the solver builds
 *  in one solve (D34). `date` is its first date. */
export interface GenerationDay {
  date: string;
  /** The span's last date. Equal to `date` on a single-day checkpoint, and
   *  absent on a job opened before spans existed. */
  through?: string;
  /** Every date this checkpoint covers. Progress is counted in these rather
   *  than in checkpoints, so the bar still fills by days. */
  dates?: string[];
  status: "pending" | "running" | "complete" | "failed";
  attempts: number;
  error: string;
  metrics: {
    /** The span's last date, mirroring `through`. */
    through?: string;
    duration_ms?: number;
    returned?: number;
    accepted?: number;
    rejected?: number;
    warnings?: number;
    repaired?: boolean;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    /** `solver`, or `hybrid` when sentences were translated by the model
     *  first. Older checkpoints may still say `ai` or `code`. */
    engine?: string;
    /** The solver's verdict: `optimal`, or `feasible` at the time limit. */
    solver_status?: string;
    /** Model requests spent translating the manager's sentences. */
    model_calls?: number;
    unresolved_sources?: number;
    compiled_hits?: number;
    quality?: GenerationQuality;
  };
}

export interface GenerationQuality {
  coverage: { required: number; assigned: number; unfilled_slots: number; percent: number };
  unfilled_seats: number;
  warning_counts: { code: string; severity: string; count: number }[];
  by_employee: { employee: string; hours: number; shifts: number; on_call: number; days: number }[];
  hours_stddev: number;
  shifts_stddev: number;
}

export interface GenerationProgress {
  activity?: string;
  /** `cancelled` is the manager stopping the wait, not a failure — every
   *  day already built is kept and resuming continues from the next one. */
  status: "" | "running" | "complete" | "failed" | "cancelled";
  current_date: string;
  total_days: number;
  completed_days: number;
  failed_days: number;
  days: GenerationDay[];
  /** The shift types this build covers; empty or absent means all. */
  shifts?: string[];
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
  /** The manager closed the banner of a stopped or failed job. Cleared
   *  when the job is resumed. */
  dismissed?: boolean;
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
  /** Which of this period's dates are somebody's closure. Computed by
   *  `bl/rotation.py` and read here — the cycle is arithmetic (D3), and a
   *  second implementation of it in the browser would drift from the one the
   *  scheduler and the audit already agree on. */
  closures: Closure[];
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
interface AlternativeEmployee {
  employee: string;
  hours: number;
  why: string;
}

/** Somewhere else this same person could go, near the date that was wanted. */
interface AlternativeSlot {
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
 *  Ordinary audit findings stay advisory (D3). `blocking` is true only for
 *  an operational duty overlap; every write path refuses that physical
 *  conflict as well. */
export interface PlacementCheck {
  ok: boolean;
  blocking: boolean;
  reasons: string[];
  warnings: ScheduleWarning[];
  eligible: boolean;
  alternatives: Alternatives;
  candidates: PlacementCandidate[];
  /** Whose closure this slot falls in. Empty `groups` means the rotation has
   *  nothing to say here — an ordinary weekday, or a cycle never anchored. */
  closure?: Closure;
}

export interface PlacementCandidate {
  employee: string;
  available: boolean;
  reasons: string[];
  hours: number;
  is_shift_manager: boolean;
  can_train: boolean;
  is_overlap: boolean;
  /** Raw roster value, used to filter the manual picker without parsing Hebrew labels. */
  exit_pattern: "round" | "triplet" | "hamshushim" | "shushim" | string;
  /** The shift types the roster lets this person work. Absent from an
   *  older server, which the picker reads as "every shift". */
  eligible_shifts?: string[];
  /** Raw rotation letter ("א", "ב", "ג"), empty when ungrouped. */
  rotation_group?: string;
  /** "סבב א" / "תלתון ג", written by the backend so the two screens that
   *  show a rotation cannot word it differently. Empty when the person is
   *  not in one. */
  rotation?: string;
  /** Whether this person's own cycle holds this slot. On a closure the
   *  picker puts them first: "who is free" and "whose weekend is it" are
   *  different questions, and only one of them is on the grid. */
  closing?: boolean;
}

/** One date the rotation speaks for.
 *
 *  Closure windows may start or end partway through a day. `shifts` names
 *  the covered occurrences; empty means the whole day. `until_handover`
 *  marks the tail after Saturday. `groups` empty means no closure. */
export interface Closure {
  date: string;
  groups: { pattern: string; group: string; label: string }[];
  label: string;
  employees: string[];
  shifts: string[];
  until_handover: boolean;
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
  source: "manager" | "agent" | "employee_reported" | "setup";
  constraint_type: "availability" | "duty";
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
  /** How many of `shifts` were nights, by the audit's own definition. */
  nights: number;
  on_call: number;
  days: number;
  /** Audit findings at `warning` severity naming this person. */
  conflicts: number;
  /** The roster's two rotation fields as stored — worded for the screen by
   *  `rotationLabel`, the way a board card words them. Both empty for
   *  somebody the roster no longer lists. */
  exit_pattern: string;
  rotation_group: string;
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
  /** How many of `total_shifts` were nights. */
  total_nights: number;
  people_working: number;
  coverage: Coverage;
  by_shift: ShiftLoad[];
  by_day: DayLoad[];
  by_employee: EmployeeLoad[];
  warning_counts: WarningCount[];
  /** Audit findings at `warning` severity. Notices are left out, as the
   *  board's own tile leaves them out. */
  conflicts: number;
  constraint_pressure: ConstraintPressure;
}

/** Everything the management area opens with, in one call. */
export interface ManagementOverview {
  today?: string;
  profile: WorkplaceProfile | null;
  /** What a profile save sends back as `expected_revision`. */
  profile_revision?: number | null;
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
 *  missing reason is met with a question, never a rejection (D8).
 *
 *  `needs_input` true means it could not tell *what* the request referred to
 *  — which person, shift or date — and asked instead of picking one. Also
 *  carries no operations, and for a stronger reason: a change applied to the
 *  wrong record has to be found before it can be undone. */
export interface Proposal {
  schedule_id: string;
  reply: string;
  needs_reason: boolean;
  needs_input: boolean;
  agent_reason: string;
  stated_reason: string;
  /** The request still waiting to be carried out, echoed back beside the
   *  question. Sent with the manager's answer so the original request
   *  resumes — they answer "ערב", not "תשבץ את דניאל במשמרת ערב". Empty on a
   *  finished proposal, so there is never a stale one to send back. */
  pending_request: string;
  operations: Operation[];
  profile_operations: ProfileOperation[];
  constraints: Record<string, unknown>[];
  warnings: ScheduleWarning[];
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
 *  This says what the manager **decided** and why. Nothing here is stored —
 *  these are proposals approved one at a time (D7). */
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
 *  There is no field here that `apply` could read. A question that turns out
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
  /** One focused question with the agent's recommendation and clickable
   *  full-sentence answers. Null for a completed answer. */
  question: Question | null;
  /** What that question is a question *about*, echoed back so the manager's
   *  reply continues it rather than being read as a new question. Empty
   *  whenever the agent is not waiting on an answer. */
  pending_request: string;
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

export interface ChatPlan {
  kind: "changes" | "profile" | "generate" | "publish" | "unpublish" | "clear" | "retire" | "restructure";
  schedule_id: string;
  agent_reason: string;
  reason: string;
  operations: Operation[];
  constraints: { employee: string; date: string; shift?: string; reason?: string; available: boolean; constraint_type?: "availability" | "duty"; start_time?: string; end_time?: string }[];
  warnings: { message: string; code?: string; employee?: string; date?: string; severity?: string }[];
  exceptions: string[];
  employee?: string;
  effective_date?: string;
  copy_from_date?: string;
  coverage?: { complete: boolean; slots: { date: string; shift: string; required: number | null; assigned: number; complete: boolean; problems: string[]; start_time: string; end_time: string }[] };
  starts_on?: string;
  ends_on?: string;
  replace_existing?: boolean;
  preserved_assignments?: { employee: string; shift: string; date: string }[];
  draft_schedule_ids?: string[];
  generated?: {
    assignments: { employee: string; shift: string; date: string; reason: string }[];
    summary: string;
    notes: string[];
  };
  profile_before?: Record<string, unknown>;
  profile_after?: Record<string, unknown>;
}

export interface ManagerChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: "working" | "pending" | "complete" | "applied" | "dismissed" | "superseded" | "error" | "cancelled";
  created_at: string;
  request_id?: string;
  payload: {
    activity?: string;
    /** The reply so far, while the model is still writing it (`working` only). */
    draft?: string;
    /** Up to three next messages the agent offers as one-click follow-ups. */
    suggestions?: string[];
    plan?: ChatPlan;
    results?: { tool: string; ok?: boolean; date?: string; shift?: string; replacing?: string;
      candidates?: { employee: string; hours?: number; why?: string; requires_exception?: boolean }[] }[];
    /** Set when code answered the turn without a model round. */
    fast_path?: string;
    question?: { question: string; recommendation: string; why: string; options: { label: string; answer: string }[] } | null;
    steps?: { tool: string; ok: boolean }[];
    receipt?: { schedule_id: string; starts_on?: string; message: string };
    _usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number; model_rounds: number };
  };
}

export interface ManagerConversation {
  id: string;
  title: string;
  messages: ManagerChatMessage[];
}

export interface ManagerChatSummary {
  id: string;
  title: string;
  updated_at: string;
}

/** One shift an absent person holds, with who could cover it. */
export interface ReplacementSlot {
  date: string;
  shift: string;
  start_time: string;
  end_time: string;
  replacing: string;
  /** Fairest first: lowest hours, then shifts, then nights in the period,
   *  counting the other covers in the same absence. */
  candidates: { employee: string; hours: number; shifts: number; nights: number; why: string }[];
  pick: string;
  picked_by: "fairness" | "manager" | "";
  why: string;
}

export interface ReplacementOptions {
  employee: string;
  dates: string[];
  schedule_id: string;
  slots: ReplacementSlot[];
  /** Days in the range with no shift: only an absence is recorded for them. */
  free_dates: string[];
  /** Shifts in the range that sit in later periods: one search plans one
   *  period, so these get no candidates. */
  elsewhere?: { date: string; shift: string; schedule_id: string }[];
  error: string;
}

/** A sheet's shape as the importer reads it (`bl/importer/layout.py`).
 *  Indices are zero-based, in the sheet as oriented: with `dates_down`,
 *  `header` is a column of the file and `label` a row. */
export interface ImportLayout {
  orientation: "dates_across" | "dates_down";
  header: number;
  shift_line: number | null;
  label: number | null;
  lanes: "shifts" | "people" | "none";
  first_line: number | null;
  last_line: number | null;
  unavailable: string[];
  ignore: string[];
}

export interface ImportedRow {
  employee: string;
  shift: string;
  date: string;
  reason?: string;
}

/** What the manager can send back with the file to have it re-read. */
export interface ImportOptions {
  sheet?: string;
  layout?: ImportLayout | null;
  week_start?: string;
  hint?: string;
  names?: Record<string, string>;
  shifts?: Record<string, string>;
  use_model?: boolean;
  /** Only these dates, for a sheet holding more than one import stores. */
  date_from?: string;
  date_to?: string;
  /** The year of a sheet whose dates write none ("01-מרץ"). */
  year?: number;
}

/** What a file holds (D7/D42). **Nothing is stored** until confirm. */
export interface ImportPreview {
  filename: string;
  sheets: string[];
  sheet_name: string;
  layout: ImportLayout;
  layout_source: "detected" | "model" | "manager";
  explanation: string;
  confidence: number;
  alternatives: { layout: ImportLayout; confidence: number; explanation: string; rows: number }[];
  sheet: string[][];
  people: {
    name: string;
    employee: string;
    status: "exact" | "matched" | "ambiguous" | "unknown" | "mapped" | "skipped";
    candidates: string[];
    count: number;
  }[];
  shifts: { name: string; shift: string; declared: boolean; count: number }[];
  dates: string[];
  starts_on: string;
  ends_on: string;
  /** The dates the whole file covers, before any window. */
  file_starts_on: string;
  file_ends_on: string;
  window: string[];
  assumed_week: string;
  /** The header's dates carry no year; the screen offers to set one. */
  yearless: boolean;
  assignments: ImportedRow[];
  unavailability: ImportedRow[];
  overlaps: { id: string; starts_on: string; ends_on: string; status: string }[];
  warnings: string[];
  summary: string;
}
