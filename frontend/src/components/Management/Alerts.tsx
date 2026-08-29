"use client";

import { MessageSquareWarning, Sparkles } from "lucide-react";

import type { ScheduleAlert } from "@/types";

/** What the agent flagged while it built the period.
 *
 *  Rendered beside the audit's warnings and deliberately not merged into
 *  them. The two answer different questions: a warning is what is true of
 *  the schedule as it stands, an alert is a decision the agent made — or one
 *  it is handing back to the manager — while building it
 *  ([D25](../../../docs/DECISIONS.md#d25--the-agent-assigns-the-tools-count-and-the-engine-is-the-floor-)).
 *  A manager reading "דנה עוברת את התקרה" wants to know whether that is a
 *  fact about the grid or a trade somebody made on purpose, and folding the
 *  lists together loses exactly that.
 *
 *  Advisory like everything else here: nothing below blocks a publish (D3).
 *  `warning` is what to look at before publishing; `info` is the agent
 *  explaining itself, and it is kept quieter for that reason. */
export function Alerts({ alerts }: { alerts: ScheduleAlert[] }) {
  if (!alerts.length) return null;

  const decisions = alerts.filter((row) => row.severity === "warning");
  const notes = alerts.filter((row) => row.severity !== "warning");

  return (
    <section className="alerts" aria-label="התרעות הסוכן על השיבוץ">
      <h3>
        <Sparkles size={15} />
        מה הסוכן מבקש שתחליט
        <span className="warnings-count">{alerts.length}</span>
      </h3>
      <p className="warnings-lead">
        אלה החלטות שהסוכן לקח או משאיר לך — הסידור תקף ואפשר לפרסם אותו כמו
        שהוא.
      </p>
      <ul>
        {decisions.map((alert, index) => (
          <li key={`${alert.code}-${index}`} className="alert-row">
            <MessageSquareWarning size={14} />
            <span>
              {alert.message}
              {alert.date ? <em className="alert-where">{alert.date}</em> : null}
            </span>
          </li>
        ))}
        {notes.map((alert, index) => (
          <li key={`${alert.code}-n-${index}`} className="alert-row notice">
            <Sparkles size={14} />
            <span>
              {alert.message}
              {alert.date ? <em className="alert-where">{alert.date}</em> : null}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
