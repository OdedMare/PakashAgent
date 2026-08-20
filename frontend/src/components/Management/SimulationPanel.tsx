"use client";

import {
  AlertTriangle,
  ArrowLeftRight,
  Check,
  CheckCircle2,
  FlaskConical,
  TrendingDown,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { useState } from "react";

import type { Simulation } from "@/types";

import { formatDate } from "./Calendar";

/** A change the manager is only *considering*, and what it would do.
 *
 *  Deliberately its own card, its own colour, and its own vocabulary. The
 *  screen already distinguishes four states — insight, proposal awaiting
 *  approval, confirmed change, error — and a simulation is a fifth that must
 *  never be mistaken for any of them. It is dashed rather than solid, marked
 *  "סימולציה" in its header, and every number on it is labelled *would*
 *  rather than *is*.
 *
 *  **Nothing has been written and nothing is queued.** `bl/simulate.py` is
 *  handed no repository, so the impact below was computed in memory over a
 *  copy of the stored week. The database is untouched whether the manager
 *  approves this or walks away from it.
 *
 *  **Approving is not a shortcut.** The approve button runs the ordinary
 *  `apply` call with the manager's reason, which is the same path a typed
 *  sentence and a dragged shift take
 *  ([D8](../../../docs/DECISIONS.md#d8--two-reasons-both-required),
 *  [D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)).
 *  It stays disabled until there is a reason, so the requirement is visible
 *  rather than arriving as a server error afterwards — mirroring
 *  `ConfirmMove` and `RequestInbox`.
 *
 *  **Warnings do not disable approval** (D3). A manager may knowingly accept
 *  a week the audit complains about; what this screen guarantees is that
 *  they saw the complaint first. */
export function SimulationPanel({
  simulation,
  busy,
  onApprove,
  onDiscard,
}: {
  simulation: Simulation | null;
  busy: boolean;
  onApprove: (reason: string) => void;
  onDiscard: () => void;
}) {
  const [reason, setReason] = useState("");

  if (!simulation) return null;

  const coverage = simulation.coverage;
  const coverageMoved = coverage.delta !== 0;

  return (
    <section className="simulation" aria-label="סימולציה">
      <header className="simulation-header">
        <span className="simulation-mark" aria-hidden="true">
          <FlaskConical size={15} />
        </span>
        <div>
          <h3>סימולציה — עוד לא בוצע דבר</h3>
          <p>
            כך היה נראה השבוע אם השינוי היה מתבצע. שום דבר לא נשמר במסד
            הנתונים.
          </p>
        </div>
      </header>

      {/* An operation that could not be applied is reported rather than
          dropped: the manager asked what would happen, and "that shift is
          not in this week" is the answer to that. */}
      {simulation.skipped.length ? (
        <ul className="simulation-skipped">
          {simulation.skipped.map((row, index) => (
            <li key={index}>
              <AlertTriangle size={13} />
              <span>
                {row.employee ? `${row.employee} · ` : ""}
                {row.shift ? `${row.shift} · ` : ""}
                {row.date ? `${formatDate(row.date)} — ` : ""}
                {row.why}
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      {simulation.applied ? (
        <>
          <div className="simulation-metrics">
            <Metric
              label="איוש"
              value={`${coverage.percent_after}%`}
              hint={`${coverage.assigned_after} מתוך ${coverage.required} מקומות`}
              delta={coverageMoved ? coverage.delta : undefined}
            />
            <Metric
              label="אזהרות חדשות"
              value={String(simulation.introduced.length)}
              hint={
                simulation.introduced.length
                  ? "השינוי יוצר אותן"
                  : "השינוי לא יוצר אזהרות"
              }
              tone={simulation.introduced.length ? "bad" : "good"}
            />
            <Metric
              label="אזהרות שייסגרו"
              value={String(simulation.resolved.length)}
              hint={
                simulation.resolved.length
                  ? "השינוי פותר אותן"
                  : "אין אזהרות שנפתרות"
              }
              tone={simulation.resolved.length ? "good" : undefined}
            />
          </div>

          {/* Everybody the change touches, including the person it takes a
              shift *away* from — half an answer to "who does this affect"
              is the failure mode this list exists to avoid. */}
          {simulation.workload.length ? (
            <div className="simulation-people">
              <h4>
                <Users size={13} />
                <span>מי מושפע</span>
              </h4>
              <ul>
                {simulation.workload.map((row) => (
                  <li key={row.employee}>
                    <span className="simulation-person">{row.employee}</span>
                    <span className="simulation-hours">
                      {pretty(row.hours_before)} ← {pretty(row.hours_after)} שעות
                    </span>
                    <span
                      className={`simulation-delta${
                        row.delta > 0 ? " is-up" : row.delta < 0 ? " is-down" : ""
                      }`}
                    >
                      {row.delta > 0 ? (
                        <TrendingUp size={12} />
                      ) : row.delta < 0 ? (
                        <TrendingDown size={12} />
                      ) : (
                        <ArrowLeftRight size={12} />
                      )}
                      {row.delta > 0 ? "+" : ""}
                      {pretty(row.delta)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {simulation.introduced.length ? (
            <ul className="simulation-warnings">
              {simulation.introduced.map((warning, index) => (
                <li key={index}>
                  <AlertTriangle size={13} />
                  <span>{warning.message}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {simulation.resolved.length ? (
            <ul className="simulation-resolved">
              {simulation.resolved.map((warning, index) => (
                <li key={index}>
                  <CheckCircle2 size={13} />
                  <span>{warning.message}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="simulation-empty">
          אף אחת מהפעולות לא ניתנת לביצוע על התקופה הזאת, ולכן אין מה להשוות.
        </p>
      )}

      {/* Approving runs the ordinary apply path. The reason is required
          exactly as it is for a typed change or a dragged shift (D8). */}
      {simulation.applied ? (
        <form
          className="simulation-approve"
          onSubmit={(event) => {
            event.preventDefault();
            if (!reason.trim() || busy) return;
            onApprove(reason.trim());
          }}
        >
          <label>
            <span>סיבת השינוי</span>
            <input
              type="text"
              value={reason}
              maxLength={200}
              onChange={(event) => setReason(event.target.value)}
              placeholder="מחלה, חופשה, בקשת העובד…"
            />
          </label>
          <div className="simulation-actions">
            <button
              type="button"
              className="ghost-button"
              onClick={onDiscard}
              disabled={busy}
            >
              <X size={14} />
              ביטול הסימולציה
            </button>
            <button
              type="submit"
              className="primary-button"
              disabled={busy || !reason.trim()}
            >
              <Check size={14} />
              {busy ? "מחיל…" : "אישור וביצוע"}
            </button>
          </div>
        </form>
      ) : (
        <div className="simulation-actions">
          <button
            type="button"
            className="ghost-button"
            onClick={onDiscard}
            disabled={busy}
          >
            <X size={14} />
            סגירה
          </button>
        </div>
      )}
    </section>
  );
}

/** One figure with what it would become.
 *
 *  `delta` is rendered only when it moved: a `±0` beside every number is
 *  noise that makes the one figure that *did* change harder to find. */
function Metric({
  label,
  value,
  hint,
  delta,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  delta?: number;
  tone?: "good" | "bad";
}) {
  return (
    <div className={`simulation-metric${tone ? ` is-${tone}` : ""}`}>
      <span className="simulation-metric-label">{label}</span>
      <span className="simulation-metric-value">
        {value}
        {delta !== undefined ? (
          <span
            className={`simulation-metric-delta${
              delta > 0 ? " is-up" : delta < 0 ? " is-down" : ""
            }`}
          >
            {delta > 0 ? "+" : ""}
            {delta}
          </span>
        ) : null}
      </span>
      <span className="simulation-metric-hint">{hint}</span>
    </div>
  );
}

/** A round number without its trailing zero. 8.0 reads as 8. */
function pretty(hours: number): string {
  return String(Math.round(hours * 10) / 10);
}
