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
