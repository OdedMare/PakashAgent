import type {
  AdminComplex,
  AdminOverview,
  CommanderNotice,
  CommanderView,
  ComplexBoard,
  ComplexSummary,
  ComplexDuty,
  DutyBoard,
  DutyConflict,
  DutyRosterTeam,
  DutyType,
  AdminTeam,
  AdminTeamDetail,
  ChangeLearning,
  Constraint,
  ConstraintRequestRow,
  EmployeeView,
  ImportedRow,
  ImportOptions,
  ImportPreview,
  ManagementOverview,
  PlacementCheck,
  Preference,
  PreferenceKind,
  PreferenceStatus,
  RosterName,
  RuntimeSettings,
  Schedule,
  ScheduleProgress,
  ShiftStats,
  SwapRow,
  TeamSummary,
  TeamView,
  Workspace,
  ManagerChatSummary,
  ManagerConversation,
  ReplacementOptions,
} from "@/types";

export const listManagerChats = () => request<ManagerChatSummary[]>("/api/agent/chats");
export const createManagerChat = () => request<ManagerConversation>("/api/agent/chats", { method: "POST" });
// `fromMessage` asks for that message and everything after it, not the whole thread.
export const readManagerChat = (id: string, fromMessage?: string) => request<ManagerConversation>(
  `/api/agent/chats/${encodeURIComponent(id)}${fromMessage ? `?from_message=${encodeURIComponent(fromMessage)}` : ""}`);
export const deleteManagerChat = (id: string) => request(`/api/agent/chats/${encodeURIComponent(id)}`, { method: "DELETE" });
export const sendManagerMessage = (id: string, input: { content: string; request_id: string; schedule_id?: string; visible_week?: string; focus_date?: string; approval_message_id?: string; displayed_plan_id?: string; replaces_message_id?: string }) =>
  request<ManagerConversation>(`/api/agent/chats/${encodeURIComponent(id)}/messages`, { method: "POST", body: JSON.stringify(input) });
// Answer the last request again, replacing the last answer in the thread.
export const regenerateManagerReply = (id: string, input: { request_id: string; schedule_id?: string; visible_week?: string; focus_date?: string }) =>
  request<ManagerConversation>(`/api/agent/chats/${encodeURIComponent(id)}/regenerate`, { method: "POST", body: JSON.stringify(input) });
export const applyManagerPlan = (id: string, messageId: string, acceptExceptions: boolean) =>
  request<ManagerConversation>(`/api/agent/chats/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/apply`, {
    method: "POST", body: JSON.stringify({ accept_exceptions: acceptExceptions }),
  });
export const dismissManagerPlan = (id: string, messageId: string) =>
  request<ManagerConversation>(`/api/agent/chats/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/dismiss`, { method: "POST" });
// Who could cover one person's absence, fairest first. Reads only: the picks
// become a plan by being sent to the conversation.
export const getReplacementOptions = (employee: string, startsOn: string, endsOn: string) =>
  request<ReplacementOptions>(`/api/agent/replacements?${new URLSearchParams({ employee, starts_on: startsOn, ends_on: endsOn })}`);
export const stopManagerReply = (id: string) =>
  request<ManagerConversation>(`/api/agent/chats/${encodeURIComponent(id)}/stop`, { method: "POST" });

/** Routes whose 401 is an answer rather than a symptom: the probes that
 *  ask "who am I". */
const EXPECTED_401 = ["/api/workspace/me", "/api/employee/me", "/api/complex/me"];

const sessionLostListeners = new Set<() => void>();

/** Hear about a read refused for want of a session.
 *
 *  The pollers behind the management area (requests inbox, chat) run
 *  until they are unmounted, and nothing unmounted them when the cookie
 *  died under them — a backend restart with no fixed session secret, a
 *  suspended team, an expired session. Each kept asking every few seconds
 *  and filled the server log with 401s while the screen still looked
 *  signed in. `useWorkspace` listens here and re-asks `/me`, which is
 *  what returns the browser to the login gate and stops them all. */
export function onSessionLost(listener: () => void): () => void {
  sessionLostListeners.add(listener);
  return () => {
    sessionLostListeners.delete(listener);
  };
}

/** A GET is a read the session should have covered. A refused POST is
 *  usually a wrong password or passcode, which is the form's to answer, and
 *  the operator console's cookie is a separate session whose loss says
 *  nothing about the team's. */
function signalsSessionLost(method: string, path: string): boolean {
  if (method !== "GET") return false;
  if (path.startsWith("/api/admin/")) return false;
  // The commander's own cookie, like the operator's, is a separate session.
  if (path.startsWith("/api/complex/")) return false;
  return !EXPECTED_401.some((probe) => path === probe || path.startsWith(`${probe}?`));
}

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
  console.debug(`[api] → ${label}`);

  let response: Response;
  try {
    response = await fetch(path, {
      ...options,
      cache: "no-store",
      // The workspace session is an HttpOnly cookie. Without this the browser
      // withholds it on anything it treats as cross-origin, and every guarded
      // route answers 401 while the user is plainly logged in.
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
  } catch (reason) {
    if (options?.signal?.aborted) throw reason;
    // A network-level failure never reaches the code below, so it would
    // otherwise surface as a bare "Failed to fetch" with no route attached.
    console.error(`[api] ✗ ${label} network error`, reason);
    throw new Error("לא ניתן להתחבר לשרת");
  }

  const elapsed = performance.now() - started;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && signalsSessionLost(method, path)) {
      sessionLostListeners.forEach((listener) => listener());
    }
    if (!(response.status === 401 && EXPECTED_401.includes(path))) console.error(`[api] ✗ ${label} → ${response.status}`);
    throw apiError(data, response.status);
  }
  console.debug(`[api] ✓ ${label} (${elapsed.toFixed(0)}ms)`);
  return data as T;
}

/** A refusal the manager can act on rather than only read.
 *
 *  The backend raises this when the profile has no shift
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
    can_edit_profile?: unknown;
    gaps?: unknown;
    blocks?: unknown;
  };
  if (body?.can_edit_profile === true) {
    return new ProfileIncompleteError(
      message,
      lines(body.gaps),
      lines(body.blocks),
    );
  }
  return Object.assign(new Error(message), { status });
}

/** The HTTP status a failed `request` answered with, when there was one. */
export function errorStatus(reason: unknown): number | undefined {
  const status = (reason as { status?: unknown } | null)?.status;
  return typeof status === "number" ? status : undefined;
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

/** The settings password travels as a header on every settings call. It is
 *  held in the panel's memory only -- never stored -- so closing the panel
 *  locks it again. */
function settingsHeaders(password: string): Record<string, string> {
  return { "X-Settings-Password": password };
}

/** Current settings, with every secret already masked by the backend. A
 *  wrong password answers 403, which is how the panel checks it. */
export function getSettings(password: string): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/api/settings", {
    headers: settingsHeaders(password),
  });
}

/** Save a partial patch. A masked secret sent back means "unchanged", so a
 *  field the boss did not retype keeps its stored value. */
export function updateSettings(
  patch: Record<string, unknown>,
  password: string,
): Promise<RuntimeSettings> {
  return request<RuntimeSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(patch),
    headers: settingsHeaders(password),
  });
}

/** Models available on a connection — the one typed into the form when
 *  `overrides` carries it, otherwise the saved one. Lets a base URL or key be
 *  tested before it is committed.
 *
 *  `role` says which saved connection an omitted field falls back to, so a
 *  role pointing at another provider is probed against its own server rather
 *  than against the general one. */
export function probeModels(
  overrides: {
    llm_base_url?: string;
    openai_api_key?: string;
    role?: string;
    llm_verify_ssl?: boolean;
  },
  password: string,
): Promise<{ models: string[] }> {
  return request<{ models: string[] }>("/api/models", {
    method: "POST",
    body: JSON.stringify(overrides),
    headers: settingsHeaders(password),
  });
}


// --- the צוות משמרות זהב console (D28) --------------------------------------
// Its own HttpOnly cookie (`pakash_admin`), so it never disturbs a team
// session in the same browser. Opening a team happens only here.

export const adminLogin = (password: string) =>
  request<{ role: string }>("/api/admin/login", { method: "POST", body: JSON.stringify({ password }) });
export const adminLogout = () => request<{ status: string }>("/api/admin/logout", { method: "POST" });
export const adminMe = () => request<{ role: string; expires: number }>("/api/admin/me");
export const adminOverview = () => request<AdminOverview>("/api/admin/overview");
export const adminTeams = () => request<AdminTeam[]>("/api/admin/teams");
export const adminTeam = (id: string) => request<AdminTeamDetail>(`/api/admin/teams/${encodeURIComponent(id)}`);
/** A name and the first manager password — the roster is the manager's. */
export const adminCreateTeam = (input: { name: string; password: string }) =>
  request<AdminTeamDetail>("/api/admin/teams", { method: "POST", body: JSON.stringify(input) });
/** Only the keys present are applied. */
export const adminUpdateTeam = (id: string, patch: Partial<{ name: string; active: boolean; notes: string }>) =>
  request<AdminTeamDetail>(`/api/admin/teams/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
export const adminResetPassword = (id: string, password: string) =>
  request<{ status: string }>(`/api/admin/teams/${encodeURIComponent(id)}/password`, { method: "POST", body: JSON.stringify({ password }) });
export const adminRotateLink = (id: string) =>
  request<AdminTeamDetail>(`/api/admin/teams/${encodeURIComponent(id)}/member-link/rotate`, { method: "POST" });
export const adminReleaseIdentity = (id: string, employee: string) =>
  request<AdminTeamDetail>(`/api/admin/teams/${encodeURIComponent(id)}/identities/release`, { method: "POST", body: JSON.stringify({ employee }) });
/** Irreversible. The team's name must be typed back. */
export const adminDeleteTeam = (id: string, confirmName: string) =>
  request<{ status: string }>(`/api/admin/teams/${encodeURIComponent(id)}/delete`, { method: "POST", body: JSON.stringify({ confirm_name: confirmName }) });

// --- a מכלול (D43) ---------------------------------------------------------
// The operator links existing teams and issues the commander's password; the
// commander signs in on a cookie of their own and enters a workplace, which
// hands them an ordinary manager session for it.

export const adminComplexes = () => request<AdminComplex[]>("/api/admin/complexes");
export const adminCreateComplex = (input: { name: string; password: string; team_ids: string[] }) =>
  request<AdminComplex>("/api/admin/complexes", { method: "POST", body: JSON.stringify(input) });
/** Only the keys present are applied; `team_ids` is the whole membership. */
export const adminUpdateComplex = (id: string, patch: Partial<{ name: string; active: boolean; notes: string; team_ids: string[] }>) =>
  request<AdminComplex>(`/api/admin/complexes/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
export const adminResetComplexPassword = (id: string, password: string) =>
  request<{ status: string }>(`/api/admin/complexes/${encodeURIComponent(id)}/password`, { method: "POST", body: JSON.stringify({ password }) });
/** Removes the grouping only; the teams stay. The name is typed back. */
export const adminDeleteComplex = (id: string, confirmName: string) =>
  request<{ status: string }>(`/api/admin/complexes/${encodeURIComponent(id)}/delete`, { method: "POST", body: JSON.stringify({ confirm_name: confirmName }) });

export const listComplexes = () => request<ComplexSummary[]>("/api/complex/list");
export const commanderLogin = (complexId: string, password: string) =>
  request<ComplexSummary>("/api/complex/login", { method: "POST", body: JSON.stringify({ complex_id: complexId, password }) });
export const commanderLogout = () => request<{ status: string }>("/api/complex/logout", { method: "POST" });
export const commanderMe = () => request<CommanderView>("/api/complex/me");
export const complexBoard = (start: string, end: string) =>
  request<ComplexBoard>(`/api/complex/board?${new URLSearchParams({ start, end })}`);
export const enterComplexTeam = (teamId: string) =>
  request<ComplexSummary>(`/api/complex/teams/${encodeURIComponent(teamId)}/enter`, { method: "POST" });
export const leaveComplexTeam = () => request<{ status: string }>("/api/complex/leave", { method: "POST" });
/** For the workplace's own manager: what the commander changed, unseen. */
export const commanderNotices = () =>
  request<{ complex: ComplexSummary | null; notices: CommanderNotice[] }>("/api/complex/notices");
export const markCommanderNoticesSeen = () =>
  request<{ status: string }>("/api/complex/notices/seen", { method: "POST" });

/** Teams for the login picker. Served unauthenticated. */
export function listTeams(): Promise<TeamSummary[]> {
  return request<TeamSummary[]>("/api/workspace/teams");
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

/** Everything the management area opens with. Served to members too — the
 *  backend shapes it by role, giving them published periods only. */
export function scheduleOverview(): Promise<ManagementOverview> {
  return request<ManagementOverview>("/api/schedule/overview");
}

/** The stats panel's numbers for a span of dates, optionally one person's.
 *
 *  The same shape the overview carries for the current period, counted by
 *  the same code — the span may be a day inside a period or a month across
 *  several. Manager only. */
export function scheduleStats(
  start: string,
  end: string,
  employee = "",
): Promise<ShiftStats> {
  const query = new URLSearchParams({ start, end });
  if (employee) query.set("employee", employee);
  return request<ShiftStats>(`/api/schedule/stats?${query}`);
}

/** Create or patch the workplace profile manually, without a model call.
 * Existing schedule rows stay untouched; the profile shapes future periods. */
export function updateProfile(body: {
  workplace?: Record<string, unknown>;
  employees?: Record<string, unknown>[];
  shifts?: Record<string, unknown>[];
  rules?: Record<string, unknown>[];
  dependencies?: string[];
  training_policy?: Record<string, unknown>;
  audit_policy?: Record<string, unknown>;
  availability_process?: string;
  constraint_deadline?: string;
  casual_worker_policy?: string;
  rest_policy?: string;
  weekend_policy?: string;
  fairness_policy?: string;
  conflict_policy?: string;
  existing_schedule_source?: string;
  summary?: string;
  /** The `profile_revision` the form was loaded at: a save over somebody
   *  else's newer one is refused (409) instead of silently undoing it. */
  expected_revision?: number | null;
}): Promise<import("@/types").WorkplaceProfile & { absorbed?: ProfileAbsorption | null }> {
  return request("/api/profile", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** What a profile save fit into the drafts already built: the new soldiers
 *  and shifts, each draft ahead of today now being refit while keeping its
 *  rows, and the weeks left alone (published, or busy) with the reason. */
export interface ProfileAbsorption {
  employees: string[];
  shifts: string[];
  schedules: { schedule_id: string; starts_on: string; ends_on: string }[];
  skipped: { schedule_id: string; starts_on: string; ends_on: string; reason: string }[];
}

/** One rule, policy or note as the code scheduler understood it (D32).
 *  `pending` means not translated yet: the worker does it after a save. */
export interface CompiledSource {
  kind: string;
  context: string;
  text: string;
  binding: boolean;
  status: "compiled" | "unresolved" | "pending";
  reason: string;
  question: string;
  expires_on: string | null;
  expired: boolean;
  items: number;
}

/** The coming weekends of each cycle, computed by the server from the setup
 *  screen's unsaved rotation. Writes nothing; `error` names a row that would
 *  not save. */
export const rotationPreview = (
  body: { workplace: Record<string, unknown>; shifts: Record<string, unknown>[]; weeks?: number },
  signal?: AbortSignal,
) => request<{ error: string; cycles: Partial<Record<"round" | "triplet" | "quad" | "quint", import("@/types").RotationWeekend[]>> }>(
  "/api/profile/rotation-preview",
  { method: "POST", body: JSON.stringify(body), signal },
);

export const compiledSources = () =>
  request<{ sources: CompiledSource[] }>("/api/profile/compiled").then((body) => body.sources);

/** Build a date range one checkpointed day per HTTP/model request.
 *
 *  `build_from`/`build_through` ask the agent for part of the period only.
 *  The period itself stays whole weeks, because the board reads a week by
 *  its Sunday and a period beginning mid-week would not be found by it. */
export async function generateSchedule(
  body: {
    starts_on?: string;
    ends_on?: string;
    build_from?: string;
    build_through?: string;
    instructions?: string;
    required_assignments?: import("@/types").RequiredAssignment[];
    /** Only these shift types are built; empty or absent means all. */
    shifts?: string[];
  } = {},
  onProgress?: (schedule: Schedule) => void,
  options?: { signal?: AbortSignal },
): Promise<Schedule> {
  const schedule = await request<Schedule>("/api/schedule/generate/start", {
    method: "POST",
    body: JSON.stringify(body),
  });
  onProgress?.(schedule);
  return resumeScheduleGeneration(schedule.id, onProgress, options);
}

/** Thrown when the caller aborted the wait rather than the job failing.
 *
 *  A manager who pressed "stop" is not looking at an error, so this is a
 *  distinct type: the hook that started the wait swallows it and leaves the
 *  board exactly as the last poll found it. */
export class GenerationStoppedError extends Error {
  constructor() {
    super("היצירה נעצרה");
    this.name = "GenerationStoppedError";
  }
}

/** Continue a persisted range after a failed request or browser refresh.
 *
 * The POST only launches background work. The browser then polls short GETs,
 * so a proxy timeout cannot turn a completed model answer into a fake network
 * failure.
 *
 * **Three things make the poll survivable rather than merely repeated.**
 *
 * - It reads `/progress`, not the whole period. The counter is the entire
 *   question being asked once a second; the grid is fetched only when the
 *   counter moves, so a twelve-day build stops re-auditing twelve days of
 *   assignments to learn that the agent is still on Tuesday.
 * - It backs off while nothing is happening, up to a few seconds, and drops
 *   straight back to a tight interval the moment a day lands.
 * - It watches the job's heartbeat. A job whose worker went away — a
 *   restarted backend, a killed thread — stays `running` in the database
 *   forever with nobody on it, and that is indistinguishable from a slow
 *   model until the beat stops. When it does, this re-POSTs `/run`, which
 *   relaunches from the first day that is not already complete. A handful of
 *   those without the beat recovering is reported as a failure rather than
 *   polled forever.
 *
 * `signal` aborts the *wait*, not the job: the server keeps building unless
 * `cancelScheduleGeneration` is called too. */
export async function resumeScheduleGeneration(
  scheduleId: string,
  onProgress?: (schedule: Schedule) => void,
  options?: { signal?: AbortSignal },
): Promise<Schedule> {
  const signal = options?.signal;
  let schedule = await request<Schedule>(
    `/api/schedule/generate/${scheduleId}/run`,
    { method: "POST" },
  );
  onProgress?.(schedule);

  let completed = schedule.generation.completed_days;
  let beat = schedule.generation.heartbeat ?? "";
  let beatSeenAt = Date.now();
  let relaunches = 0;
  let failedPolls = 0;
  let delay = POLL_MIN_MS;

  while (schedule.generation.status === "running") {
    await waitForGenerationPoll(delay, signal);

    let progress: ScheduleProgress;
    try {
      progress = await scheduleProgress(scheduleId);
      failedPolls = 0;
    } catch (reason) {
      // A poll is a read and is safe to repeat. Brief network blips should
      // not fail a model job that is still progressing on the server.
      if (++failedPolls < MAX_FAILED_POLLS) continue;
      throw reason;
    }

    const moved =
      progress.generation.completed_days !== completed ||
      progress.generation.status !== "running";
    completed = progress.generation.completed_days;
    if (moved) {
      // A day landed, or the job ended. Now the grid is worth re-reading.
      schedule = await getSchedule(scheduleId);
      delay = POLL_MIN_MS;
    } else {
      // Same day still in flight: report the counter without paying for the
      // period, and ask less often the longer it goes on.
      schedule = { ...schedule, generation: progress.generation };
      delay = Math.min(Math.round(delay * POLL_BACKOFF), POLL_MAX_MS);
    }
    onProgress?.(schedule);
    if (progress.generation.status !== "running") break;

    const said = progress.generation.heartbeat ?? "";
    if (!said) continue;
    if (said !== beat || moved) {
      beat = said;
      beatSeenAt = Date.now();
      relaunches = 0;
      continue;
    }
    if (Date.now() - beatSeenAt < STALE_HEARTBEAT_MS) continue;
    // The job says it is running and nothing has touched it in minutes. The
    // worker is gone; POST /run adopts it. A process that still owns the job
    // answers this without starting a second worker.
    beatSeenAt = Date.now();
    if (++relaunches > MAX_RELAUNCHES) {
      throw new Error(
        "בניית הסידור נתקעה. הימים שהושלמו נשמרו — אפשר לנסות להמשיך שוב",
      );
    }
    schedule = await request<Schedule>(
      `/api/schedule/generate/${scheduleId}/run`,
      { method: "POST" },
    );
    beat = schedule.generation.heartbeat ?? beat;
    onProgress?.(schedule);
  }
  return schedule;
}

/** How far a build has got. The cheap read the poll above is built on. */
function scheduleProgress(
  scheduleId: string,
): Promise<ScheduleProgress> {
  return request<ScheduleProgress>(`/api/schedule/${scheduleId}/progress`);
}

/** Stop a build, keeping every day already finished.
 *
 *  Cooperative on the server: a model call already in flight cannot be
 *  interrupted, so the worker stops at the next day boundary. The period is
 *  an ordinary draft the moment this returns. */
export function cancelScheduleGeneration(
  scheduleId: string,
): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/generate/${scheduleId}/cancel`, {
    method: "POST",
  });
}

/** Hide the banner of a stopped or failed build. Keeps every day built,
 *  and the build can still be resumed. */
export function dismissScheduleGeneration(
  scheduleId: string,
): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/generate/${scheduleId}/dismiss`, {
    method: "POST",
  });
}

/** Build a run of dates in an existing draft — "from this day until
 *  Saturday". What the agent built there is replaced; what the manager
 *  placed there is kept, and every other date is left alone. `shifts`
 *  narrows it to those shift types ("only the nights"); the rest stand. */
export async function generateScheduleRange(
  body: {
    schedule_id: string;
    starts_on: string;
    ends_on: string;
    instructions?: string;
    shifts?: string[];
    keep_existing?: boolean;
  },
  onProgress?: (schedule: Schedule) => void,
  options?: { signal?: AbortSignal },
): Promise<Schedule> {
  const schedule = await request<Schedule>(
    `/api/schedule/generate/${body.schedule_id}/range/start`,
    {
      method: "POST",
      body: JSON.stringify({
        starts_on: body.starts_on,
        ends_on: body.ends_on,
        instructions: body.instructions ?? "",
        shifts: body.shifts ?? [],
        keep_existing: body.keep_existing ?? false,
      }),
    },
  );
  onProgress?.(schedule);
  return resumeScheduleGeneration(body.schedule_id, onProgress, options);
}

/** The tight interval a poll returns to whenever a day lands. */
const POLL_MIN_MS = 1_000;
/** The slowest it gets while one day is still in flight. A build spends most
 *  of its life here, and a day takes far longer than a second either way. */
const POLL_MAX_MS = 5_000;
const POLL_BACKOFF = 1.5;
/** Consecutive failed polls tolerated before the wait gives up. A poll is a
 *  read, so repeating it is free; a job still progressing on the server must
 *  not be failed by a blip on the way to it. */
const MAX_FAILED_POLLS = 10;
/** How long a heartbeat may stand still before the job is presumed
 *  worker-less. The backend beats every 20s, so this is four missed beats —
 *  long enough that a slow database write is never mistaken for a death. */
const STALE_HEARTBEAT_MS = 90_000;
/** How many times a stalled job is relaunched before it is called stuck. */
const MAX_RELAUNCHES = 3;

/** Wait between polls, giving up early if the caller aborted. */
function waitForGenerationPoll(
  ms: number,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) return Promise.reject(new GenerationStoppedError());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", stop);
      resolve();
    }, ms);
    function stop() {
      clearTimeout(timer);
      reject(new GenerationStoppedError());
    }
    signal?.addEventListener("abort", stop, { once: true });
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
 *  Ordinary findings advise and never gate (D3). A duty overlap returns
 *  `blocking: true`, and the write endpoint independently enforces it. */
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
export function scheduleAt(day: string, signal?: AbortSignal): Promise<Schedule | null> {
  return request<Schedule | null>(
    `/api/schedule/at?day=${encodeURIComponent(day)}`,
    { signal },
  );
}

/** Every stored period touching a span of dates, oldest first.
 *
 *  What the board's two-week and month views read: one request for a span
 *  no single period covers. An empty list is a normal answer — a month with
 *  nothing built yet — and each period comes back whole, even where the span
 *  only clips it. */
export function schedulesBetween(
  start: string,
  end: string,
  signal?: AbortSignal,
): Promise<Schedule[]> {
  return request<Schedule[]>(
    `/api/schedule/between?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
    { signal },
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

/** What taking somebody off the roster vacates. */
export interface Departure {
  employee: string;
  effective_date: string;
  shifts: number;
  published: { id: string; starts_on: string; ends_on: string }[];
}

/** Somebody chosen to take over one shift a departure vacates. */
export interface DepartureCover {
  schedule_id: string;
  shift_name: string;
  slot_date: string;
  employee: string;
}

/** Count what a departure would vacate. **Writes nothing.** */
export function previewDeparture(body: {
  employee: string;
  effective_date?: string;
}): Promise<Departure> {
  return request<Departure>("/api/schedule/departure/preview", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Take somebody off the active roster. The name stays in the profile with
 *  an end date — it is what their history hangs on — and every shift from
 *  that date on is vacated and logged. */
export function departEmployee(body: {
  employee: string;
  effective_date?: string;
  reason?: string;
}): Promise<Departure> {
  return request<Departure>("/api/schedule/departure", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Empty a day's shifts, or the whole period's. **The grid stays.**
 *
 *  Distinct from `deleteSchedule`, which removes the period outright. Which
 *  one a manager wants depends on what they are unhappy with: the week's
 *  shape comes from the shift vocabulary, and the assignments are what a
 *  build decided. Clearing takes back the second and keeps the first, so the
 *  week is still there to fill in again — by hand or by asking the agent. */
export function clearSchedule(body: {
  schedule_id: string;
  slot_date?: string;
  reason?: string;
}): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/${body.schedule_id}/clear`, {
    method: "POST",
    body: JSON.stringify({
      slot_date: body.slot_date ?? "",
      reason: body.reason ?? "",
    }),
  });
}

/** Remove a period entirely — its slots, its assignments, its progress.
 *
 *  The change log survives: history does not disappear because the thing it
 *  describes did (D4). The week goes back to the empty state, where both
 *  doors — the agent's build and a blank grid — are offered again. */
export function deleteSchedule(scheduleId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/schedule/${scheduleId}`, {
    method: "DELETE",
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

function getSchedule(scheduleId: string): Promise<Schedule> {
  return request<Schedule>(`/api/schedule/${scheduleId}`);
}

/** Ask the agent what it would do. **Persists nothing** — the manager
 *  confirms before anything lands, and that gap is where the agent's
 *  reasoning gets read (D8). */
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

/** A drag the manager confirmed. The gesture itself changed nothing — this
 *  is what the confirmation dialog sends once they have given a reason, so a
 *  dragged shift carries the same two reasons a spoken change does (D8). */
export function moveAssignment(body: {
  assignment_id: string;
  shift_name: string;
  slot_date: string;
  reason: string;
  agent_reason?: string;
  /** The period the drag happened on. Omitted means the one covering today,
   *  which is only ever right by coincidence. */
  schedule_id?: string;
  /** The slot the shift was dragged from: a shift somebody else moved in
   *  the meantime is refused (409) instead of being moved again. */
  from_slot_id?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/move", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Record a constraint. Boss-only: employees never write (D5). `source`
 *  distinguishes the manager entering it from the manager writing down what
 *  an employee reported. */
export function setConstraint(body: {
  employee: string;
  constraint_date: string;
  shift_name?: string;
  available?: boolean;
  start_time?: string;
  end_time?: string;
  is_hard?: boolean;
  reason?: string;
  source?: string;
  constraint_type?: "availability" | "duty";
}): Promise<Constraint> {
  return request<Constraint>("/api/schedule/constraints", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Archive a shift type. Stored schedules keep their rows; the next build
 * stops producing it, and the roster's references to it are cleaned up. */
export function deleteShiftType(name: string): Promise<import("@/types").WorkplaceProfile> {
  return request(`/api/profile/shifts/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export function deleteConstraint(rowId: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/api/schedule/constraints/${rowId}`, {
    method: "DELETE",
  });
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

/** Sign in to a claimed name from the front door, without the share link
 *  (D25). The team is named here because there is no session to carry it.
 *  Only an existing claim is reachable — claiming still needs the link. */
export function employeeSignIn(body: {
  teamId: string;
  employee: string;
  passcode: string;
}): Promise<{ employee: string }> {
  return request<{ employee: string }>("/api/employee/signin", {
    method: "POST",
    body: JSON.stringify({
      team_id: body.teamId,
      employee: body.employee,
      passcode: body.passcode,
    }),
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

/** The manager's live line (Server-Sent Events). Boss-only.
 *
 *  Each event is named for an inbox — `requests` or `swaps` — and carries no
 *  data: the screen re-reads that inbox through its usual route. Same-origin,
 *  so the session cookie rides along as it does on `fetch`. */
export function managerEvents(): EventSource {
  return new EventSource("/api/schedule/requests/events", { withCredentials: true });
}

/** Requests awaiting a decision. Boss-only. */
export function pendingRequests(): Promise<ConstraintRequestRow[]> {
  return request<ConstraintRequestRow[]>("/api/schedule/requests/pending");
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

/** Read one uploaded schedule file and say what it holds.
 *
 *  **Writes nothing** (D7): `confirmImport` is the only call that persists.
 *  `options` carries the manager's corrections -- the layout, which name
 *  means whom, which heading is which shift -- and the same file is sent
 *  again with them, so the server re-reads rather than the browser patching
 *  rows it cannot read itself. Multipart rather than through `request`,
 *  which forces a JSON content-type and would break the boundary.
 */
export async function previewImport(file: File, options: ImportOptions = {}): Promise<ImportPreview> {
  const path = "/api/schedule/import/preview";
  const body = new FormData();
  body.append("file", file);
  body.append("options", JSON.stringify(options));
  console.debug(`[api] → POST ${path}`, file.name);
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", credentials: "same-origin", body });
  } catch (reason) {
    console.error(`[api] ✗ POST ${path} network error`, reason);
    throw new Error("לא ניתן להתחבר לשרת");
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    console.error(`[api] ✗ POST ${path} → ${response.status}`);
    throw apiError(data, response.status);
  }
  return data as ImportPreview;
}

/** Store the rows the manager approved. With `schedule_id` they are merged
 *  into that draft; without it a new period is opened. */
export function confirmImport(body: {
  assignments: ImportedRow[];
  unavailability?: ImportedRow[];
  schedule_id?: string | null;
  filename?: string;
}): Promise<Schedule> {
  return request<Schedule>("/api/schedule/import/confirm", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

// The מכלול's duties (תורנויות), on the commander's cookie.
export const dutyBoard = (start: string, end: string) =>
  request<DutyBoard>(`/api/complex/duties?${new URLSearchParams({ start, end })}`);
export const dutyRoster = () => request<DutyRosterTeam[]>("/api/complex/duty-roster");
export const createDutyType = (input: { name: string; seats: number; weight: number; days: string[] }) =>
  request<DutyType>("/api/complex/duty-types", { method: "POST", body: JSON.stringify(input) });
export const updateDutyType = (id: string, patch: Partial<Omit<DutyType, "id">>) =>
  request<DutyType>(`/api/complex/duty-types/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(patch) });
export const deleteDutyType = (id: string) =>
  request<{ status: string }>(`/api/complex/duty-types/${encodeURIComponent(id)}`, { method: "DELETE" });
// `blocks: false` records a duty already stood: it counts and blocks nothing.
export const assignDuty = (input: { duty_type_id: string; team_id: string; employee: string; duty_date: string; note: string; blocks: boolean }) =>
  request<{ duty: ComplexDuty; conflicts: DutyConflict[] }>("/api/complex/duties", { method: "POST", body: JSON.stringify(input) });
export const cancelDuty = (id: string) =>
  request<ComplexDuty>(`/api/complex/duties/${encodeURIComponent(id)}`, { method: "DELETE" });
