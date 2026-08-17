import type { InterviewTurn, RuntimeSettings } from "@/types";

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
