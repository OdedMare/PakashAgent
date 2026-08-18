import type {
  ChangeEntry,
  Constraint,
  ConstraintRequestRow,
  EmployeeIdentity,
  EmployeeView,
  InterviewTurn,
  ManagementOverview,
  Operation,
  Proposal,
  RosterName,
  RuntimeSettings,
  Schedule,
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
    throw new Error(errorDetail(data, response.status));
  }
  console.debug(`[api] ✓ ${label} (${elapsed.toFixed(0)}ms)`, data);
  return data as T;
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
  body: { starts_on?: string; ends_on?: string; instructions?: string } = {},
): Promise<Schedule> {
  return request<Schedule>("/api/schedule/generate", {
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
