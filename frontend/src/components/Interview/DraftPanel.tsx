"use client";

import {
  Circle,
  CircleCheck,
  Clock,
  ListTodo,
  Loader2,
  Users,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { WorkplaceProfile } from "@/types";

import { computeDraftStats, type DraftStats } from "./draftStats";

/** The profile as it stands, beside the conversation.
 *
 *  This is the point of the `plan-chat` turn shape: the agent returns the
 *  draft on every turn, so the boss watches the profile fill in as they
 *  answer instead of taking twenty questions on faith and meeting the result
 *  only at the end. `resolved` and `open_points` are the agent's own account
 *  of what is settled and what is not — including risks the boss has not
 *  raised — which is what makes the remaining work visible rather than
 *  guessable from a progress bar.
 *
 *  The numbers are **computed here, in the browser, from that draft**
 *  (`draftStats.ts`) rather than counted by the model or fetched from an
 *  endpoint. They are a reading of data the turn already carried, so they
 *  cost no round-trip and land the instant the turn does. What they add over
 *  the three array lengths this panel used to show is the arithmetic a
 *  manager is actually checking: whether the shifts they described can be
 *  staffed by the people they listed.
 */
export function DraftPanel({
  draft,
  resolved,
  openPoints,
  /** True while a turn is being generated. The panel keeps showing the last
   *  known numbers and marks itself as working, rather than blanking — the
   *  figures remain true until the answer in flight changes them, and
   *  emptying them would read as the profile having been lost. */
  busy = false,
}: {
  draft: WorkplaceProfile | null;
  resolved: string[];
  openPoints: string[];
  busy?: boolean;
}) {
  const workplace = draft?.workplace ?? {};
  const stats = computeDraftStats(draft);
  const changed = useChangedKeys(stats);

  const empty =
    !workplace.name &&
    resolved.length === 0 &&
    openPoints.length === 0 &&
    stats.shifts === 0 &&
    stats.staff === 0;
  // Nothing has been established yet, so a panel of empty counters would be
  // noise next to the first question.
  if (empty) return null;

  return (
    <aside className="draft-panel" aria-label="הפרופיל שנאסף עד כה">
      <div className="draft-head">
        {workplace.name ? (
          <h2 className="draft-name">{workplace.name}</h2>
        ) : (
          <h2 className="draft-name draft-name-pending">הפרופיל שלכם</h2>
        )}
        {busy ? (
          <span className="draft-working" role="status">
            <Loader2 size={13} className="draft-spin" aria-hidden="true" />
            מעדכן…
          </span>
        ) : null}
      </div>

      <dl className="draft-grid">
        <Stat
          label="עובדים"
          value={stats.staff}
          note={peopleNote(stats)}
          changed={changed.has("staff")}
        />
        <Stat
          label="משמרות"
          value={stats.shifts}
          note={
            stats.onCallShifts > 0
              ? `${stats.onCallShifts} בכוננות`
              : undefined
          }
          changed={changed.has("shifts")}
        />
        <Stat
          label="כללים"
          value={stats.rules}
          note={stats.hardRules > 0 ? `${stats.hardRules} חובה` : undefined}
          changed={changed.has("rules")}
        />
      </dl>

      {/* The derived half: what the drafted shifts actually demand. Hidden
          until there is a shift to demand anything, so it does not sit at
          zero through the opening questions. */}
      {stats.weeklySlots > 0 ? (
        <dl className="draft-grid draft-derived">
          <Stat
            label="משבצות בשבוע"
            value={stats.weeklySlots}
            icon={<Users size={13} />}
            changed={changed.has("weeklySlots")}
          />
          {stats.weeklyHours > 0 ? (
            <Stat
              label="שעות בשבוע"
              value={stats.weeklyHours}
              icon={<Clock size={13} />}
              // While some shifts still lack hours the total is a floor, not
              // a measurement, and saying so is the difference between a
              // number the manager can trust and one they cannot.
              note={stats.hoursComplete ? undefined : "חלקי"}
              changed={changed.has("weeklyHours")}
            />
          ) : null}
          {stats.hoursPerEmployee !== null ? (
            <Stat
              label="שעות לעובד"
              value={stats.hoursPerEmployee}
              note={stats.hoursComplete ? undefined : "חלקי"}
              changed={changed.has("hoursPerEmployee")}
            />
          ) : null}
        </dl>
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

/** Trainees and casuals sit beside the headcount rather than inside it.
 *
 *  A trainee on a shadow shift is at work and still leaves the slot needing
 *  somebody else, and a casual is only available once they have said so —
 *  folding either into the staff count would read as more coverage than the
 *  schedule actually has. */
function peopleNote(stats: DraftStats): string | undefined {
  const parts: string[] = [];
  if (stats.trainees > 0) parts.push(`${stats.trainees} מתלמדים`);
  if (stats.casuals > 0) parts.push(`${stats.casuals} מזדמנים`);
  return parts.length > 0 ? `+ ${parts.join(" · ")}` : undefined;
}

function Stat({
  label,
  value,
  note,
  icon,
  changed,
}: {
  label: string;
  value: number;
  note?: string;
  icon?: React.ReactNode;
  changed?: boolean;
}) {
  return (
    <div className={`draft-card${changed ? " draft-card-changed" : ""}`}>
      <dt>
        {icon}
        {label}
      </dt>
      <dd>{value}</dd>
      {note ? <span className="draft-note">{note}</span> : null}
    </div>
  );
}

/** Which figures moved on the latest turn, so the panel can point at them.
 *
 *  A manager answering a question about staffing wants to see *that* number
 *  move; without a cue the panel is a wall of digits where one quietly
 *  changed. The set is derived from the previous render's values rather than
 *  from the turn payload, because a figure can change for a reason the turn
 *  does not name — correcting a shift's hours moves the weekly total without
 *  the word "hours" appearing anywhere in the answer.
 */
function useChangedKeys(stats: DraftStats): Set<string> {
  const previous = useRef<DraftStats | null>(null);
  const [changed, setChanged] = useState<Set<string>>(new Set());

  useEffect(() => {
    const before = previous.current;
    previous.current = stats;
    // The first draft is not a change: everything is new at once, and
    // highlighting all of it says nothing.
    if (!before) return;

    const moved = (Object.keys(stats) as Array<keyof DraftStats>).filter(
      (key) => stats[key] !== before[key],
    );
    if (moved.length === 0) return;

    setChanged(new Set(moved as string[]));
    // Cleared on a timer so the cue marks *this* turn's movement. Left on,
    // it would accumulate until every tile was highlighted and the signal
    // meant nothing.
    const timer = window.setTimeout(() => setChanged(new Set()), 1_800);
    return () => window.clearTimeout(timer);
    // Compared by value: `stats` is rebuilt every render, so depending on the
    // object itself would fire the effect on renders where nothing moved.
  }, [JSON.stringify(stats)]); // eslint-disable-line react-hooks/exhaustive-deps

  return changed;
}
