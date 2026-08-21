import type {
  AgentAnswer,
  Briefing,
  BriefingTrigger,
  ChangeEntry,
  ChangeLearning,
  Constraint,
  ConstraintRequestRow,
  CopilotAuditEvent,
  CopilotInboxData,
  CopilotItem,
  CopilotMode,
  EmployeeIdentity,
  EmployeeView,
  ImportedConstraint,
  ImportPreview,
  InterviewTurn,
  ManagementOverview,
  Operation,
  PlacementCheck,
  Preference,
  PreferenceKind,
  PreferenceStatus,
  Proposal,
  RosterName,
  RuntimeSettings,
  Schedule,
  Simulation,
  SwapRow,
  TeamSummary,
  TeamView,
  Workspace,
} from "@/types";

/**
 * Every backend call is traced to the browser console.
 *
 * Failures are logged with the request body that caused them, because the
 * Hebrew message the UI shows is deliberately short and a 4xx/5xx is only
 * diagnosable next to what was actually sent.
 */
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const method = options?.method ?? "GET";
  const label = `${method} ${path}`;
  const started = performance.now();
  console.debug(`[api] → ${label}`, options?.body);

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      // The workspace session is an HttpOnly cookie. Without this the browser
      // withholds it on anything it treats as cross-origin, and every guarded
      // route answers 401 while the user is plainly logged in.
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch (reason) {
    // A network-level failure never reaches the code below, so it would
    // otherwise surface as a bare "Failed to fetch" with no route attached.
    console.error(`[api] ✗ ${label} network error`, reason);
    throw new Error("לא ניתן להתחבר לשרת");
  }

  const elapsed = performance.now() - started;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`[api] ✗ ${label} → ${response.status}`, data);
    throw apiError(data, response.status);
  }
  console.debug(`[api] ✓ ${label} (${elapsed.toFixed(0)}ms)`, data);
  return data as T;
}

/** A refusal the manager can act on rather than only read.
 *
 *  The backend raises this when the interview finished without a shift
 *  vocabulary: there is no grid to build, but the fix is a conversation
 *  rather than a bug report. It carries the missing topics so the UI can
 *  name them and offer the way back in, which is the whole difference
 *  between this and the dead-end 502 it replaced. */
export class ProfileIncompleteError extends Error {
  readonly gaps: string[];
  readonly blocks: string[];

  constructor(message: string, gaps: string[], blocks: string[]) {
    super(message);
    this.name = "ProfileIncompleteError";
    this.gaps = gaps;
    this.blocks = blocks;
  }
}

/** The thrown value for a failed response.
 *
 *  Every caller catches `Error` and reads `.message`, so the ordinary case is
 *  unchanged. Only the resumable refusal gets a richer type, and only the
 *  screens that know what to do with it look for one. */
function apiError(data: unknown, status: number): Error {
  const message = errorDetail(data, status);
  const body = data as {
    can_resume_interview?: unknown;
    gaps?: unknown;
    blocks?: unknown;
  };
  if (body?.can_resume_interview === true) {
    return new ProfileIncompleteError(
      message,
      lines(body.gaps),
      lines(body.blocks),
    );
  }
  return new Error(message);
}

function lines(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

/** The backend's `AppError` handler sends Hebrew copy in `detail`; a
 *  validation error sends a list. Anything else gets a generic Hebrew line —
 *  a raw status code means nothing to the boss. */
function errorDetail(data: unknown, status: number): string {
  const detail = (data as { detail?: unknown })?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0] as { msg?: string };
    if (first?.msg) return first.msg;
  }
  return `שגיאת שרת (${status})`;
}

export function startInterview(): Promise<InterviewTurn> {
  return request<InterviewTurn>("/api/interview", { method: "POST" });
}

export function resumeInterview(sessionId: string): Promise<InterviewTurn> {
  return request<InterviewTurn>(`/api/interview/${sessionId}`);
}

export function answerInterview(
  sessionId: string,
  content: string,
): Promise<InterviewTurn> {
  return request<InterviewTurn>(`/api/interview/${sessionId}/answer`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function retryInterview(sessionId: string): Promise<InterviewTurn> {
  return request<InterviewTurn>(`/api/interview/${sessionId}/retry`, {
    method: "POST",
  });
}

/** Close the interview now, keeping whatever has been collected.
 *
 *  Costs no model call on the server — this is the way out of an interview
 *  the manager does not have time to finish, and a way out that needs the
 *  model is not one. What the profile still owes is recorded on it. */
export function endInterview(sessionId: string): Promise<InterviewTurn> {
  return request<InterviewTurn>(`/api/interview/${sessionId}/end`, {
    method: "POST",
  });
}

/** Current settings, with every secret already masked by the backend. */
export function getSettings(): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/api/settings");
}

/** Save a partial patch. A masked secret sent back means "unchanged", so a
 *  field the boss did not retype keeps its stored value. */
export function updateSettings(
  patch: Record<string, unknown>,
): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
}

/** Models available on a connection — the one typed into the form when
 *  `overrides` carries it, otherwise the saved one. Lets a base URL or key be
 *  tested before it is committed. */
export function probeModels(
  overrides: { llm_base_url?: string; openai_api_key?: string } = {},
): Promise<{ models: string[] }> {
  return request<{ models: string[] }>("/api/models", {
    method: "POST",
    body: JSON.stringify(overrides),
  });
}


/** Teams for the login picker. Served unauthenticated. */
export function listTeams(): Promise<TeamSummary[]> {
  return request<TeamSummary[]>("/api/workspace/teams");
}

/** Open a workspace and log in as its boss. */
export function createTeam(
  name: string,
  password: string,
): Promise<Workspace> {
  return request<Workspace>("/api/workspace", {
    method: "POST",
    body: JSON.stringify({ name, password }),
  });
}

export function loginTeam(
  teamId: string,
  password: string,
): Promise<Workspace> {
  return request<Workspace>("/api/workspace/login", {
    method: "POST",
    body: JSON.stringify({ team_id: teamId, password }),
  });
}

/** Exchange a share link for a member session. The token moves into an
 *  HttpOnly cookie here, so the rest of the visit does not carry it in the
 *  URL where it would land in history. */
export function openMemberLink(token: string): Promise<Workspace> {
  return request<Workspace>(`/api/workspace/member/${encodeURIComponent(token)}`, {
    method: "POST",
  });
}

/** The current workspace, shaped by the visitor's role. 401 when there is no
 *  session — the caller treats that as "show the login screen", not an error. */
export function currentWorkspace(): Promise<TeamView> {
  return request<TeamView>("/api/workspace/me");
}

export function logout(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/workspace/logout", {
    method: "POST",
  });
}

/** Revoke the outstanding share link and mint a new one. Boss only. */
export function rotateMemberLink(): Promise<Workspace> {
  return request<Workspace>("/api/workspace/member-link/rotate", {
    method: "POST",
  });
}

export function changePassword(
  current: string,
  replacement: string,
): Promise<{ status: string }> {
  return request<{ status: string }>("/api/workspace/password", {
    method: "POST",
    body: JSON.stringify({ current, replacement }),
  });
}

/** Everything the management area opens with. Served to members too — the
 *  backend shapes it by role, giving them published periods only. */
export function scheduleOverview(): Promise<ManagementOverview> {
  return request<ManagementOverview>("/api/schedule/overview");
}

/** Build a period. Omitted dates mean the current week. Stored as a draft —
 *  publishing is a separate, deliberate act. */
export function generateSchedule(
  body: {
    starts_on?: string;
    ends_on?: string;
    instructions?: string;
    required_assignments?: import("@/types").RequiredAssignment[];
  } = {},
): Promise<Schedule> {
  return request<Schedule>("/api/schedule/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Open an empty period the manager fills in themselves (D18).
 *
 *  The authoring half of D6, and the one schedule-building path that calls
 *  no model at all: which dates fall in a period and which shifts run on
 *  them is arithmetic. The cells arrive empty. */
export function blankSchedule(
  body: { starts_on?: string; ends_on?: string } = {},
): Promise<Schedule> {
  return request<Schedule>("/api/schedule/blank", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Place one person on one slot, by hand. Writes immediately (D18).
 *
 *  Unlike a drag, this does not go through a confirmation. A drag moves
 *  somebody who is already placed, which changes a person's week and is what
 *  the reason dialog exists to account for; filling an empty cell takes
 *  nothing away from anybody. `reason` is optional and stored when given. */
export function assignEmployee(body: {
  shift_name: string;
  slot_date: string;
  employee: string;
  reason?: string;
  schedule_id?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/assign", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** What a placement would cost, before it is made. Writes nothing.
 *
 *  **No model is called on this path.** It is `bl/placement.py` — the same
 *  arithmetic `bl/audit.py` does, asked about a schedule that does not exist
 *  yet. That is what makes the board usable with the agent unavailable: a
 *  drag is validated, explained in Hebrew, and offered deterministic
 *  alternatives without a token being generated.
 *
 *  It advises and never gates. The caller is free to write anyway, and the
 *  board does exactly that when the manager confirms (D3). */
export function checkPlacement(body: {
  employee: string;
  shift_name: string;
  slot_date: string;
  schedule_id?: string;
  /** The row being dragged, when this is a move rather than a fill. It comes
   *  out of the hypothetical before the new one goes in, so a move is
   *  checked as a move and not as one person in two places at once. */
  moving_assignment_id?: string;
}): Promise<PlacementCheck> {
  return request<PlacementCheck>("/api/schedule/check", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** The stored period containing a date, or null when none does.
 *
 *  What the board opens on. Null is a normal answer — "no schedule that
 *  week" is a state the board renders as an empty week, not an error. */
export function scheduleAt(day: string): Promise<Schedule | null> {
  return request<Schedule | null>(
    `/api/schedule/at?day=${encodeURIComponent(day)}`,
  );
}

/** Take one person off a slot, by hand (D18). */
export function unassignEmployee(body: {
  assignment_id: string;
  reason?: string;
  schedule_id?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/unassign", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function publishSchedule(scheduleId: string): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/${scheduleId}/publish`, {
    method: "POST",
  });
}

export function unpublishSchedule(scheduleId: string): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/${scheduleId}/unpublish`, {
    method: "POST",
  });
}

export function getSchedule(scheduleId: string): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/${scheduleId}`);
}

/** Ask the agent what it would do. **Persists nothing** — the manager
 *  confirms before anything lands, and that gap is where the agent's
 *  reasoning gets read (D8). */
/** What the agent has to say without being asked (D15).
 *
 *  Called when the management area opens, after the state changes, and
 *  before publishing. It writes nothing and it never fails loudly: a
 *  briefing that could not be produced comes back `quiet`, because this sits
 *  beside a calendar that has to render regardless.
 *
 *  `lastSaid` is the headlines already shown this sitting, sent back so the
 *  agent does not repeat an opening the manager has read. */
export function briefManager(
  trigger: BriefingTrigger,
  lastSaid: string[] = [],
): Promise<Briefing> {
  return request<Briefing>("/api/schedule/brief", {
    method: "POST",
    body: JSON.stringify({ trigger, last_said: lastSaid.slice(-8) }),
  });
}

/** Download one period as `.xlsx` (D17).
 *
 *  Deliberately not routed through `request()`: that helper parses every
 *  response as JSON, and this one is a binary body. The browser's own
 *  download is triggered from an object URL rather than by navigating to the
 *  route, so the session cookie is sent the same way every other call sends
 *  it and a failure surfaces as a Hebrew error instead of a blank tab.
 */
export async function downloadSchedule(scheduleId: string): Promise<void> {
  const path = `/api/schedule/export/${scheduleId}`;
  console.debug(`[api] → GET ${path}`);
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    console.error(`[api] ✗ GET ${path} → ${response.status}`, data);
    throw new Error(errorDetail(data, response.status));
  }

  // The filename the server chose, so a folder of these stays readable.
  const disposition = response.headers.get("content-disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = match?.[1] ?? "schedule.xlsx";
  link.click();
  // Revoked on the next tick: revoking synchronously can race the click on
  // some browsers and produce an empty file.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function proposeChange(
  body: { request: string; schedule_id?: string; reason?: string },
): Promise<Proposal> {
  return request<Proposal>("/api/schedule/propose", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Apply a proposal the manager confirmed. The manager's reason is required
 *  by now — they have already been asked for it. */
export function applyChange(body: {
  schedule_id: string;
  operations: Operation[];
  reason: string;
  agent_reason?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/apply", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** A drag the manager confirmed. The gesture itself changed nothing — this
 *  is what the confirmation dialog sends once they have given a reason, so a
 *  dragged shift carries the same two reasons a spoken change does (D8). */
export function moveAssignment(body: {
  assignment_id: string;
  shift_name: string;
  slot_date: string;
  reason: string;
  agent_reason?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/move", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function listConstraints(params: {
  starts_on?: string;
  ends_on?: string;
  employee?: string;
} = {}): Promise<Constraint[]> {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => Boolean(value)) as [
      string,
      string,
    ][],
  ).toString();
  return request<Constraint[]>(
    `/api/schedule/constraints/list${query ? `?${query}` : ""}`,
  );
}

/** Record a constraint. Boss-only: employees never write (D5). `source`
 *  distinguishes the manager entering it from the manager writing down what
 *  an employee reported. */
export function setConstraint(body: {
  employee: string;
  constraint_date: string;
  shift_name?: string;
  available?: boolean;
  reason?: string;
  source?: string;
}): Promise<Constraint> {
  return request<Constraint>("/api/schedule/constraints", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteConstraint(rowId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/schedule/constraints/${rowId}`, {
    method: "DELETE",
  });
}

/** The append-only change log — the only history there is (D4). */
export function listChanges(scheduleId?: string): Promise<ChangeEntry[]> {
  return request<ChangeEntry[]>(
    `/api/schedule/history/list${scheduleId ? `?schedule_id=${scheduleId}` : ""}`,
  );
}

/* -- the employee's own area (D14) ----------------------------------------
 *
 * None of these send the employee's name in a body. The server reads it from
 * the signed cookie, which is what stops one employee acting or reading as
 * another — so there is deliberately no parameter for it.
 */

/** Roster names and which are taken. Reachable with a share-link session:
 *  it is the screen someone sees *before* they have an identity. */
export function employeeRoster(): Promise<{ names: RosterName[] }> {
  return request<{ names: RosterName[] }>("/api/employee/roster");
}

/** Claim a roster name and set a passcode. Signs in on success. */
export function claimIdentity(body: {
  employee: string;
  passcode: string;
}): Promise<{ employee: string }> {
  return request<{ employee: string }>("/api/employee/claim", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function employeeLogin(body: {
  employee: string;
  passcode: string;
}): Promise<{ employee: string }> {
  return request<{ employee: string }>("/api/employee/login", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function employeeLogout(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/employee/logout", {
    method: "POST",
  });
}

/** Hours, shifts, warnings, teammates and requests, in one call. */
export function employeeMe(): Promise<EmployeeView> {
  return request<EmployeeView>("/api/employee/me");
}

/** Submit a constraint request.
 *
 *  Returns a **pending** row. Nothing about the schedule has changed — the
 *  manager's approval is what turns this into a constraint (D14). */
/** Mark the changes just shown as read (D16).
 *
 *  Sent once the personal area has rendered them, never on login: the point
 *  is that a person *saw* the moves affecting them, and arriving is not
 *  seeing. The employee comes off the signed cookie, so this can only ever
 *  settle the caller's own badge. */
export function acknowledgeChanges(): Promise<{
  employee: string;
  unseen: number;
}> {
  return request("/api/employee/acknowledge", { method: "POST" });
}

export function submitConstraintRequest(body: {
  constraint_date: string;
  shift_name?: string;
  available?: boolean;
  reason?: string;
}): Promise<ConstraintRequestRow> {
  return request<ConstraintRequestRow>("/api/employee/requests", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function withdrawConstraintRequest(
  requestId: string,
): Promise<ConstraintRequestRow> {
  return request<ConstraintRequestRow>(
    `/api/employee/requests/${requestId}/withdraw`,
    { method: "POST" },
  );
}

/** Candidate rules from what the manager kept correcting by hand.
 *
 *  Read-only and boss-only. Nothing is stored: like the candidates an import
 *  produces, these are proposals the manager approves one at a time (D7).
 *  A workspace with too little history answers with empty lists and costs no
 *  model call, so this is cheap to ask on a screen that shows it. */
export function learnFromChanges(): Promise<ChangeLearning> {
  return request<ChangeLearning>("/api/schedule/history/learn");
}

/* -- swaps, employee side --------------------------------------------------- */

/** Offer a colleague a trade of shifts.
 *
 *  Both shifts are named by **assignment id**: the employee picks two cells
 *  off the published grid, and ids mean the offer can only ever name shifts
 *  that are really on it. Returns a row with status `awaiting_counterparty` —
 *  nothing has moved, and two more people have to agree before anything
 *  does (D14 — the manager remains the sole decider). */
export function proposeSwap(body: {
  assignment_id: string;
  counterparty: string;
  counterparty_assignment_id: string;
  reason?: string;
}): Promise<SwapRow> {
  return request<SwapRow>("/api/employee/swaps", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Swaps naming the caller, on either side. */
export function mySwaps(): Promise<SwapRow[]> {
  return request<SwapRow[]>("/api/employee/swaps");
}

/** Offers waiting on the caller's answer — their badge. */
export function incomingSwaps(): Promise<SwapRow[]> {
  return request<SwapRow[]>("/api/employee/swaps/incoming");
}

/** Accept or decline an offer.
 *
 *  Accepting still moves nothing: it puts the swap in the manager's inbox,
 *  which is the only place a schedule change can come from. */
export function answerSwap(
  swapId: string,
  agreed: boolean,
): Promise<SwapRow> {
  return request<SwapRow>(`/api/employee/swaps/${swapId}/answer`, {
    method: "POST",
    body: JSON.stringify({ agreed }),
  });
}

/** The requester taking back their own offer. */
export function withdrawSwap(swapId: string): Promise<SwapRow> {
  return request<SwapRow>(`/api/employee/swaps/${swapId}/withdraw`, {
    method: "POST",
  });
}

/* -- swaps, manager side ---------------------------------------------------- */

/** Swaps both employees agreed to, awaiting the manager. Boss-only.
 *
 *  One still awaiting its colleague is deliberately absent: the manager
 *  rules on arrangements, and an offer nobody has accepted is not yet one. */
export function pendingSwaps(): Promise<SwapRow[]> {
  return request<SwapRow[]>("/api/schedule/swaps/pending");
}

export function allSwaps(): Promise<SwapRow[]> {
  return request<SwapRow[]>("/api/schedule/swaps");
}

/** Approve, and perform the swap.
 *
 *  The reason is **required**, unlike a constraint approval: this one moves
 *  two assignments, and D8 does not exempt a change for having been
 *  suggested by the people it affects. */
export function approveSwap(
  swapId: string,
  reason: string,
): Promise<{ swap: SwapRow; schedule: Schedule }> {
  return request(`/api/schedule/swaps/${swapId}/approve`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Refuse a swap, with a reason both employees will read. */
export function rejectSwap(
  swapId: string,
  reason: string,
): Promise<{ swap: SwapRow }> {
  return request(`/api/schedule/swaps/${swapId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/* -- the manager's side of the same feature -------------------------------- */

/** Requests awaiting a decision. Boss-only. */
export function pendingRequests(): Promise<ConstraintRequestRow[]> {
  return request<ConstraintRequestRow[]>("/api/schedule/requests/pending");
}

export function allRequests(): Promise<ConstraintRequestRow[]> {
  return request<ConstraintRequestRow[]>("/api/schedule/requests");
}

/** Approve, which writes the constraint it becomes — with
 *  `source='employee_reported'`, keeping the provenance D13 defined. */
export function approveRequest(
  requestId: string,
  reason = "",
): Promise<{ request: ConstraintRequestRow; constraint: Constraint }> {
  return request(`/api/schedule/requests/${requestId}/approve`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/** Reject. The reason is required — the employee will read it. */
export function rejectRequest(
  requestId: string,
  reason: string,
): Promise<{ request: ConstraintRequestRow }> {
  return request(`/api/schedule/requests/${requestId}/reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function listIdentities(): Promise<EmployeeIdentity[]> {
  return request<EmployeeIdentity[]>("/api/schedule/requests/identities");
}

/** Free a claimed name. The manager's tool for a departure or a lost
 *  passcode — rotating the share link does not do this. */
export function releaseIdentity(
  employee: string,
): Promise<{ status: string }> {
  return request<{ status: string }>(
    "/api/schedule/requests/identities/release",
    { method: "POST", body: JSON.stringify({ employee }) },
  );
}

/** Read uploaded schedule files and return what they appear to say.
 *
 *  **Writes nothing.** Under D7 the manager reads the interpretation and
 *  confirms it; `confirmImport` is the only call that persists. Sent as
 *  multipart rather than through `request`, which forces a JSON
 *  content-type — setting it by hand here would break the boundary the
 *  browser generates.
 *
 *  Many files at once because that is the real case: a manager has a folder
 *  of past sheets, and a pattern worth learning is only visible across them.
 */
export async function previewImport(
  files: File[],
  learnRules = true,
): Promise<ImportPreview> {
  const path = `/api/schedule/import/preview?learn_rules=${learnRules}`;
  const body = new FormData();
  files.forEach((file) => body.append("files", file));
  console.debug(`[api] → POST ${path}`, files.map((f) => f.name));

  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      body,
    });
  } catch (reason) {
    console.error(`[api] ✗ POST ${path} network error`, reason);
    throw new Error("לא ניתן להתחבר לשרת");
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`[api] ✗ POST ${path} → ${response.status}`, data);
    throw new Error(errorDetail(data, response.status));
  }
  console.debug(`[api] ✓ POST ${path}`, data);
  return data as ImportPreview;
}

/** Store an interpretation the manager approved (D7).
 *
 *  The rows travel back from the screen rather than being re-read from the
 *  file, so a shift the manager chose or a name they corrected is what gets
 *  stored — re-inferring here would silently discard the correction.
 */
export function confirmImport(body: {
  assignments: { employee: string; shift: string; date: string }[];
  unavailability?: ImportedConstraint[];
  starts_on?: string;
  ends_on?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/import/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Ask the agent a question about the schedule. **Writes nothing.**
 *
 *  The multi-step half of the agent: the planner picks read-only tools, the
 *  backend answers each with arithmetic, and the reply is assembled from
 *  what they returned. There is no operation in the response, so nothing an
 *  answer says can be applied — a question that wants a change comes back
 *  with `needs_confirmation` and still goes through propose-then-confirm.
 *
 *  It answers with no model configured, via the deterministic reader, and
 *  says so in `used_model`. */
export function askAgent(body: {
  request: string;
  schedule_id?: string;
}): Promise<AgentAnswer> {
  return request<AgentAnswer>("/api/schedule/ask", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Run one named read-only tool directly. **Writes nothing.**
 *
 *  The same tools the agent uses, reachable without a conversation — which
 *  is what stops a board button and the agent from ever giving different
 *  answers to the same question. */
export function runAgentTool(body: {
  tool: string;
  arguments?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/schedule/tool", {
    method: "POST",
    body: JSON.stringify({ arguments: {}, ...body }),
  });
}

/** What a set of operations would do. **Persists nothing.**
 *
 *  Deliberately not `proposeChange`: a proposal is an answer with a confirm
 *  button attached, and a manager asking "what happens if" has not asked for
 *  one. Approving a simulation is an ordinary `applyChange` with their
 *  reason (D8). */
export function simulateChange(body: {
  operations: Operation[];
  schedule_id?: string;
}): Promise<Simulation> {
  return request<Simulation>("/api/schedule/simulate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** What this workplace has taught the agent.
 *
 *  Visible by design: a stored preference the manager cannot see is a rule
 *  they never agreed to. */
export function listPreferences(status?: PreferenceStatus): Promise<Preference[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<Preference[]>(`/api/schedule/preferences/list${query}`);
}

/** Record a preference, or propose one for the manager to approve.
 *
 *  `suggested: true` stores it inert — the agent reads only active ones, so
 *  a proposal changes nothing until it is approved. */
export function addPreference(body: {
  text: string;
  kind?: PreferenceKind;
  subject?: string;
  evidence?: string;
  suggested?: boolean;
}): Promise<Preference> {
  return request<Preference>("/api/schedule/preferences", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Reword a preference, approve a suggested one, or archive it. */
export function updatePreference(
  rowId: string,
  body: { text?: string; status?: PreferenceStatus },
): Promise<Preference> {
  return request<Preference>(`/api/schedule/preferences/${rowId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function deletePreference(rowId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/schedule/preferences/${rowId}`, {
    method: "DELETE",
  });
}

export function getCopilotInbox(): Promise<CopilotInboxData> {
  return request<CopilotInboxData>("/api/copilot/inbox");
}

export function getCopilotAudit(): Promise<{ events: CopilotAuditEvent[] }> {
  return request<{ events: CopilotAuditEvent[] }>("/api/copilot/audit");
}

export function runCopilotNow(): Promise<{ status: string; job_id: string }> {
  return request<{ status: string; job_id: string }>("/api/copilot/run", {
    method: "POST",
  });
}

export function setCopilotPermission(
  actionType: string,
  mode: CopilotMode,
): Promise<{ action_type: string; mode: CopilotMode }> {
  return request<{ action_type: string; mode: CopilotMode }>(
    `/api/copilot/permissions/${encodeURIComponent(actionType)}`,
    { method: "PATCH", body: JSON.stringify({ mode }) },
  );
}

export function approveCopilotItem(itemId: string): Promise<CopilotItem> {
  return request<CopilotItem>(`/api/copilot/items/${itemId}/approve`, {
    method: "POST",
  });
}

export function dismissCopilotItem(itemId: string): Promise<CopilotItem> {
  return request<CopilotItem>(`/api/copilot/items/${itemId}/dismiss`, {
    method: "POST",
  });
}

export function rollbackCopilotItem(itemId: string): Promise<CopilotItem> {
  return request<CopilotItem>(`/api/copilot/items/${itemId}/rollback`, {
    method: "POST",
  });
}
