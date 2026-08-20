"use client";

import { Circle, CircleCheck, CircleAlert, ListTodo } from "lucide-react";

import type { WorkplaceProfile } from "@/types";

/** The profile as it stands, beside the conversation.
 *
 *  This is the point of the `plan-chat` turn shape: the agent returns the
 *  draft on every turn, so the boss watches the profile fill in as they
 *  answer instead of taking twenty questions on faith and meeting the result
 *  only at the end. `resolved` and `open_points` are the agent's own account
 *  of what is settled and what is not — including risks the boss has not
 *  raised — which is what makes the remaining work visible rather than
 *  guessable from a progress bar. */
export function DraftPanel({
  draft,
  resolved,
  openPoints,
  gaps = [],
}: {
  draft: WorkplaceProfile | null;
  resolved: string[];
  openPoints: string[];
  /** What blocks a schedule, passed only once the boss has asked to stop
   *  and been told they cannot yet. Distinct from `openPoints`, which is
   *  everything the interview would still like to know: these few are the
   *  ones standing between here and a schedule. */
  gaps?: string[];
}) {
  const workplace = draft?.workplace ?? {};
  const empty =
    !workplace.name &&
    resolved.length === 0 &&
    openPoints.length === 0 &&
    gaps.length === 0;
  // Nothing has been established yet, so a panel of empty counters would be
  // noise next to the first question.
  if (empty) return null;

  return (
    <aside className="draft-panel" aria-label="הפרופיל שנאסף עד כה">
      {workplace.name ? <h2 className="draft-name">{workplace.name}</h2> : null}

      <dl className="draft-grid">
        <Stat label="עובדים" value={count(draft?.employees)} />
        <Stat label="משמרות" value={count(draft?.shifts)} />
        <Stat label="כללים" value={count(draft?.rules)} />
      </dl>

      {gaps.length > 0 ? (
        <section className="draft-section">
          <h3 className="draft-blocking">
            <CircleAlert size={15} />
            חסר כדי לשבץ
          </h3>
          <ul className="draft-list gaps">
            {gaps.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {resolved.length > 0 ? (
        <section className="draft-section">
          <h3>
            <CircleCheck size={15} />
            סוכם
          </h3>
          <ul className="draft-list resolved">
            {resolved.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {openPoints.length > 0 ? (
        <section className="draft-section">
          <h3>
            <ListTodo size={15} />
            נשאר לסגור
          </h3>
          <ul className="draft-list open">
            {openPoints.map((line) => (
              <li key={line}>
                <Circle size={9} aria-hidden="true" />
                <span>{line}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </aside>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="draft-card">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function count(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}
