"use client";

import { History as HistoryIcon } from "lucide-react";

import type { ChangeEntry } from "@/types";

import { formatDate } from "./Calendar";

/** The append-only change log — the only history the system has.
 *
 *  There is no versioning and no rollback
 *  ([D4](../../../docs/DECISIONS.md#d4--living-schedule-not-versioned)): the
 *  schedule is edited in place and this is what answers "why did Yossi get
 *  moved". Both reasons are rendered because they answer different
 *  questions — the manager's is why the change happened, the agent's is why
 *  it chose this particular move. */
export function History({ entries }: { entries: ChangeEntry[] }) {
  if (!entries.length) return null;

  return (
    <section className="history" aria-label="יומן השינויים">
      <h3>
        <HistoryIcon size={15} />
        יומן השינויים
      </h3>
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <div className="history-head">
              <span className={`op-badge op-${entry.action}`}>
                {ACTION_LABELS[entry.action] ?? entry.action}
              </span>
              {entry.employee ? (
                <span className="history-who">{entry.employee}</span>
              ) : null}
              {entry.slot_date ? (
                <span className="history-when">
                  {formatDate(entry.slot_date)}
                  {entry.shift_name ? ` · ${entry.shift_name}` : ""}
                </span>
              ) : null}
            </div>
            {entry.reason ? (
              <p className="history-reason">
                <span className="history-label">הסיבה</span>
                {entry.reason}
              </p>
            ) : null}
            {entry.agent_reason ? (
              <p className="history-reason agent">
                <span className="history-label">נימוק הסוכן</span>
                {entry.agent_reason}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

const ACTION_LABELS: Record<string, string> = {
  generated: "נבנה",
  published: "פורסם",
  moved: "הועבר",
  assigned: "שובץ",
  removed: "הוסר",
  swapped: "הוחלף",
  constraint: "אילוץ",
};
