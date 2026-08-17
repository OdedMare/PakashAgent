/** Mirrors `backend/app/api/contracts.py`. */

export interface Option {
  id: string;
  label: string;
  recommended: boolean;
}

export interface Message {
  role: "assistant" | "user";
  content: string;
  options: Option[];
  recommendation: string | null;
}

/** The confirmed workplace profile. Only the fields the summary screen
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
  question_id: string | null;
  question: string | null;
  recommendation: string | null;
  options: Option[];
  allow_free_text: boolean;
  turns: Message[];
  profile: WorkplaceProfile | null;
}
