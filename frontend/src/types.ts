/** Mirrors `backend/app/api/contracts.py`. */

/** A clickable answer. `label` captions the button; `answer` is the full
 *  sentence sent verbatim as the boss's own message when it is clicked. */
export interface Option {
  label: string;
  answer: string;
}

/** The single question a turn asks, with the agent's own recommendation. */
export interface Question {
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
}

/** The workplace profile as it stands. Only the fields the summary screen
 *  reads are named — the rest is shown as JSON, since the interview owns the
 *  full shape and duplicating it here would drift. */
export interface WorkplaceProfile {
  workplace?: {
    name?: string;
    mission?: string;
    summary?: string;
  };
  employees?: unknown[];
  shifts?: unknown[];
  rules?: unknown[];
  summary?: string;
  [key: string]: unknown;
}

export interface InterviewTurn {
  session_id: string;
  status: "question" | "complete";
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
  llm_diet_mode: boolean;
  llm_repetition_penalty: number;
  llm_timeout_seconds: number;
  llm_base_url: string | null;
  openai_api_key: string;
}

/** Who the current visitor is inside a workspace.
 *
 *  `boss` authors — the interview, the settings, the schedule. `member` only
 *  reads (D5). The role arrives from the signed session cookie and is never
 *  chosen by the client, so this type describes what the server said, not a
 *  preference the UI may set. */
export type Role = "boss" | "member";

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
}

export interface SchedulePeriod {
  id: string;
  starts_on: string;
  ends_on: string;
  status: "draft" | "published";
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

/** Everything the management area opens with, in one call. */
export interface ManagementOverview {
  profile: WorkplaceProfile | null;
  employees: Record<string, unknown>[];
  shifts: Record<string, unknown>[];
  schedule: Schedule | null;
  periods: SchedulePeriod[];
  availability: Constraint[];
  changes: ChangeEntry[];
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
  constraints: Record<string, unknown>[];
  warnings: ScheduleWarning[];
}
