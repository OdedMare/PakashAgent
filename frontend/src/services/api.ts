import type { InterviewTurn } from "@/types";

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
