"use client";

import { AlertTriangle, GripVertical, Hand, Move } from "lucide-react";

import { colorStyle } from "@/components/Management/palette";
import type { Assignment, ScheduleWarning, Slot } from "@/types";

/** One assignment, as a card the manager can read without hovering.
 *
 *  The old grid's chip carried a name and hid everything else behind a
 *  `title`: the role was nowhere, the hours were on the row head, and the
 *  agent's reason needed a hover that does not exist on a touch screen. This
 *  card carries the person, their role, the shift's hours, where the row
 *  came from, and its warning state — which is what makes a week scannable
 *  rather than merely present.
 *
 *  **Colour is signal, not decoration.** The person's hue is the fill (a
 *  week reads as a shape before it reads as text), but a card carrying a
 *  warning drops the hue entirely and takes the warning colour: an alarm
 *  that competes with ten decorative pastels is not an alarm. That is the
 *  same rule `Calendar.tsx` applies to `is-blocked`, applied to the whole
 *  warning set.
 *
 *  Clicking opens the editor; dragging proposes a move. Both are on the same
 *  element and the browser distinguishes them for us — a `click` does not
 *  fire after a drag.
 */
export function ShiftCard({
  assignment,
  role,
  slot,
  hue,
  dark,
  status,
  blocked,
  warnings,
  draggable,
  touched = null,
  dimmed = false,
  picked = false,
  onDragStart,
  onDragEnd,
  onPick,
  onOpen,
}: {
  assignment: Assignment;
  role: string;
  slot: Slot;
  hue: number;
  dark: boolean;
  status: "draft" | "published";
  /** A constraint recorded against this person on this cell. */
  blocked: boolean;
  warnings: ScheduleWarning[];
  draggable: boolean;
  /** Set when the agent is currently pointing at this person in this cell.
   *  A ring, never a fill: the fill is the person's hue or the warning
   *  colour, and both of those are older claims on the card than the
   *  agent's attention is. */
  touched?: "proposal" | "simulation" | "answer" | null;
  /** The card currently being dragged, faded in place so its origin stays
   *  visible while the manager looks for somewhere to drop it. */
  dimmed?: boolean;
  /** Picked up by the keyboard or touch path, waiting for a destination.
   *  Distinct from `dimmed`: a dragged card is being carried by a pointer
   *  that will land in a moment, while a picked one is parked and stays
   *  visible until the manager chooses a cell. */
  picked?: boolean;
  onDragStart: () => void;
  onDragEnd: () => void;
  /** Start a move without a mouse. Absent on a read-only board. */
  onPick?: () => void;
  onOpen: () => void;
}) {
  const alarming = blocked || warnings.some((row) => row.severity === "warning");
  const manual = assignment.source === "manager";

  return (
    <div
      className={[
        "board-card",
        alarming ? "is-alarming" : "",
        blocked ? "is-blocked" : "",
        manual ? "is-manual" : "",
        status === "draft" ? "is-draft" : "is-published",
        touched ? `is-touched is-touched-${touched}` : "",
        dimmed ? "is-dragging" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      // The hue is per-name and computed at render, so it cannot be a class.
      // A warning card gets none: the alarm styling in CSS has to out-shout
      // a decorative colour, and the cleanest way is for there to be none.
      style={alarming ? undefined : colorStyle(hue, dark)}
      draggable={draggable}
      onDragStart={(event) => {
        // Some browsers refuse to start a drag without transfer data set.
        event.dataTransfer.setData("text/plain", assignment.id);
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      onKeyDown={(event) => {
        // The card is a div because it is also a drag source; a button
        // inside a draggable is fought over by both behaviours. Keyboard
        // access is given back explicitly rather than lost.
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`${assignment.employee}, ${slot.shift_name}. עריכה`}
    >
      <div className="board-card-main">
        <span className="board-card-name">{assignment.employee}</span>
        {role ? <span className="board-card-role">{role}</span> : null}
      </div>

      <div className="board-card-meta">
        {slot.start_time ? (
          <span className="board-card-hours">
            {slot.start_time}–{slot.end_time}
          </span>
        ) : null}
        {/* Provenance, not authorship (D18). "Did I put this here or did the
            agent" is the question a half-generated, half-edited week raises,
            and the reason text answers it only if you stop to read. */}
        {manual ? (
          <span className="board-card-manual" title="שובץ ידנית על ידי המנהל">
            <Hand size={10} />
          </span>
        ) : null}
        {alarming ? (
          <span
            className="board-card-alarm"
            title={
              blocked
                ? `${assignment.employee} — נרשם אילוץ למשמרת הזו`
                : warnings.map((row) => row.message).join("\n")
            }
          >
            <AlertTriangle size={11} />
          </span>
        ) : null}
      </div>

      {draggable ? (
        <span className="board-card-grip" aria-hidden="true">
          <GripVertical size={12} />
        </span>
      ) : null}
    </div>
  );
}
