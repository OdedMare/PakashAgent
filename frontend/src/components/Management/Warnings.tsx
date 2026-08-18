"use client";

import { AlertTriangle, Info } from "lucide-react";

import type { ScheduleWarning } from "@/types";

/** Audit findings, as non-blocking banners.
 *
 *  These never gate a save, never block a confirmation, and never present as
 *  errors ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *  A schedule with warnings is a valid schedule the manager may knowingly
 *  accept — the arithmetic is here because an LLM gets it subtly wrong, not
 *  because code gets a veto.
 *
 *  Styled as information rather than failure for the same reason: a red wall
 *  of blocked-looking text would teach the manager that a warning means
 *  "stop", when it means "look". */
export function Warnings({ warnings }: { warnings: ScheduleWarning[] }) {
  if (!warnings.length) return null;

  const serious = warnings.filter((row) => row.severity === "warning");
  const notices = warnings.filter((row) => row.severity !== "warning");

  return (
    <section className="warnings" aria-label="התראות על הסידור">
      <h3>
        <AlertTriangle size={15} />
        בדיקת הסידור
        <span className="warnings-count">{warnings.length}</span>
      </h3>
      {/* Said out loud, because a list of problems reads as a blocker unless
          it is told not to. */}
      <p className="warnings-lead">
        אלה הערות בלבד — הסידור תקף ואפשר לפרסם אותו כמו שהוא.
      </p>
      <ul>
        {serious.map((warning, index) => (
          <li key={`${warning.code}-${index}`} className="warning-row">
            <AlertTriangle size={14} />
            <span>{warning.message}</span>
          </li>
        ))}
        {notices.map((warning, index) => (
          <li key={`${warning.code}-n-${index}`} className="warning-row notice">
            <Info size={14} />
            <span>{warning.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
