"use client";

import {
  AlertTriangle,
  GripVertical,
  Hand,
  Move,
  ShieldCheck,
  Users,
} from "lucide-react";

import { colorStyle } from "@/components/Management/palette";
import {
  constraintHeadline,
  constraintSentence,
  warningHeadline,
} from "@/lib/warningSummary";
import type {
  Assignment,
  CardPerson,
  Constraint,
  ScheduleWarning,
  Slot,
} from "@/types";

import { STATUS_LABELS } from "./person";

/** One assignment, as a card the manager can read without hovering.
 *
 *  The card answers **who is standing here**, not why the agent put them
 *  here. Name, role, rotation, whether they can command, whether they are
 *  still being handed over to — plus the shift's hours, where the row came
 *  from, and its warning state. Those are the facts that decide whether a
 *  cell is manned or only filled, and a manager reading a week is deciding
 *  exactly that, cell by cell.
 *
 *  `assignment.reason` used to hold the last line. It is a record D8 requires
 *  and it is still written on every path and still on the card's hover — but
 *  a justification for a placement is read once, when the placement is made,
 *  and the grid is read every day. The line went to the reader who is
 *  actually there.
 *
 *  **Colour is signal, not decoration.** The person's hue is the fill (a
 *  week reads as a shape before it reads as text), but a card carrying a
 *  warning drops the hue entirely and takes the warning colour: an alarm
 *  that competes with ten decorative pastels is not an alarm. That is the
 *  same rule `Calendar.tsx` applies to `is-blocked`, applied to the whole
 *  warning set.
 *
 *  **An alarm says what it is about, on the card.** A red card with a bare
 *  triangle told the manager *that* a soldier was flagged and made them
 *  hover to learn *why* — and a hover does not exist on a phone. The card's
 *  last line now names the rule and the number that broke it ("אילוץ
 *  08:00–14:00 · מילואים", "רק 6 ש׳ מנוחה (נדרש 8)"), and the hover lists
 *  every finding in full. Still advice, never a gate (D3).
 *
 *  Clicking opens the editor; dragging proposes a move. Both are on the same
 *  element and the browser distinguishes them for us — a `click` does not
 *  fire after a drag.
 */
export function ShiftCard({
  assignment,
  person,
  slot,
  hue,
  dark,
  status,
  blocker,
  warnings,
  draggable,
  touched = null,
  dimmed = false,
  picked = false,
  onDragStart,
  onDragEnd,
  onPick,
  onRemove,
  onOpen,
}: {
  assignment: Assignment;
  /** Who this is — role, rotation, command, overlap. From the roster, so it
   *  reads the same on every shift they hold. */
  person: CardPerson;
  slot: Slot;
  hue: number;
  dark: boolean;
  status: "draft" | "published";
  /** The constraint recorded against this person on this cell, if any. */
  blocker: Constraint | null;
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
  /** Remove the focused card with Delete/Backspace. */
  onRemove?: () => void;
  onOpen?: () => void;
}) {
  const blocked = blocker !== null;
  const alarming = blocked || warnings.some((row) => row.severity === "warning");
  const reasons = alarming ? alarmReasons(assignment.employee, blocker, warnings) : [];
  const manual = assignment.source === "manager";
  // An alarm still out-shouts everything, overlap included.
  const overlap = person.is_overlap && !alarming;
  // מילואים / אע״צ / הצ״ח each wear one shared colour across the grid, the
  // same way overlap does; an alarm and overlap both still win over it.
  const tint = person.status && !alarming && !overlap ? person.status : "";

  return (
    <div
      className={[
        "board-card",
        alarming ? "is-alarming" : "",
        blocked ? "is-blocked" : "",
        manual ? "is-manual" : "",
        overlap ? "is-overlap" : "",
        tint ? `is-status is-status-${tint}` : "",
        status === "draft" ? "is-draft" : "is-published",
        touched ? `is-touched is-touched-${touched}` : "",
        dimmed ? "is-dragging" : "",
        picked ? "is-picked" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      // The hue is per-name and computed at render, so it cannot be a class.
      // A warning card gets none: the alarm styling in CSS has to out-shout
      // a decorative colour, and the cleanest way is for there to be none.
      // An overlap card gets none either: it wears one shared colour so a
      // person being handed over to reads as such across the whole grid.
      style={alarming || overlap || tint ? undefined : colorStyle(hue, dark)}
      draggable={draggable}
      onDragStart={(event) => {
        // Some browsers refuse to start a drag without transfer data set.
        event.dataTransfer.setData("text/plain", assignment.id);
        event.dataTransfer.effectAllowed = "move";
        onDragStart();
      }}
      onDragEnd={onDragEnd}
      onClick={onOpen}
      title={identityTitle(assignment, person, reasons)}
      onKeyDown={(event) => {
        // The card is a div because it is also a drag source; a button
        // inside a draggable is fought over by both behaviours. Keyboard
        // access is given back explicitly rather than lost.
        if (
          onRemove &&
          event.target === event.currentTarget &&
          (event.key === "Delete" || event.key === "Backspace")
        ) {
          event.preventDefault();
          onRemove();
          return;
        }
        if (onOpen && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onOpen();
          return;
        }
        // `M` picks the card up for a move. A letter rather than a modifier
        // chord because the board is Hebrew and a chord on a Hebrew layout
        // is a different key on every machine; a bare letter is the same
        // physical key everywhere, and the card is not a text field so
        // nothing else wants it.
        if (onPick && (event.key === "m" || event.key === "M" || event.key === "צ")) {
          event.preventDefault();
          onPick();
        }
      }}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      aria-keyshortcuts={onRemove ? "Delete Backspace" : undefined}
      // A screen reader gets the same identity a sighted manager reads off
      // the card, not just the name: the role and rotation are the point.
      aria-label={
        onOpen
          ? `${ariaWho(assignment, person)}, ${slot.shift_name}.${reasons.length ? ` אזהרה: ${reasons.map((row) => row.short).join("; ")}.` : ""} עריכה${onRemove ? ", Delete להסרה" : ""}`
          : undefined
      }
      aria-grabbed={onPick ? picked : undefined}
    >
      <div className="board-card-main">
        <span className="board-card-name">{assignment.employee}</span>
        {person.role ? (
          <span className="board-card-role">{person.role}</span>
        ) : null}
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
        {/* Command is a property of the person, not of the slot. It used to
            appear only where `requires_shift_manager` was set, which meant
            the one fact a manager most needs while reading a cell —
            *is anybody here able to run this shift* — was invisible on
            exactly the shifts where nobody had declared it needed. The
            badge now says what is true of her; whether this slot demands it
            is the audit's question and the audit already asks it. */}
        {person.is_shift_manager ? (
          <span
            className="board-card-commander"
            title={
              slot.requires_shift_manager
                ? "מפקד/ת המשמרת"
                : "מוסמך/ת לפקד על משמרת"
            }
          >
            <ShieldCheck size={11} /> מפקד/ת
          </span>
        ) : null}
        {/* A note about the soldier, kept in the roster. Visual: the card
            says there is something to know and the hover says what. */}
        {person.note ? (
          <span
            className="board-card-note"
            title={`הערה: ${person.note}`}
            aria-label={`הערה: ${person.note}`}
          >
            !
          </span>
        ) : null}
        {person.is_overlap ? (
          <span
            className="board-card-overlap"
            title="נחפף/ת — בחפיפה, לרוב אינו/ה נספר/ת בתקן המשמרת"
          >
            <Users size={11} /> נחפף/ת
          </span>
        ) : null}
        {person.status ? (
          <span className="board-card-status" title={STATUS_LABELS[person.status]}>
            {STATUS_LABELS[person.status]}
          </span>
        ) : null}
      </div>

      {/* Who she is, not why she is here.
          `assignment.reason` is a record D8 requires and it is still stored,
          still written on every path, and still one hover away — but as the
          card's own last line it answered a question that is already closed
          by the time a week is on screen. What a manager reads a grid for is
          whether each cell is *manned*, and that is a question about the
          people in it: their rotation, and whether they are counted or still
          being handed over to. Role and command sit above; this line carries
          the rotation, which is the fact that decides whether the person is
          even around next weekend. */}
      {person.rotation ? (
        <p className="board-card-identity">{person.rotation}</p>
      ) : null}

      {/* Why this card is red, in words, where the manager is already
          looking. The first finding is spelled out; any others are counted
          and listed in full on the hover. */}
      {reasons.length ? (
        <p
          className="board-card-why"
          title={reasons.map((row) => `• ${row.full}`).join("\n")}
        >
          <AlertTriangle size={11} aria-hidden="true" />
          <span className="board-card-why-text">{reasons[0].short}</span>
          {reasons.length > 1 ? (
            <span className="board-card-why-more" dir="ltr">+{reasons.length - 1}</span>
          ) : null}
        </p>
      ) : null}

      {/* The move handle, as a real button.
          The grip beside it is decoration for a gesture only a mouse can
          make; this is the same move for a finger or a keyboard. It stops
          the click from reaching the card, because the card opens the
          editor and picking up is not editing. */}
      {onPick ? (
        <button
          type="button"
          className="board-card-pick"
          onClick={(event) => {
            event.stopPropagation();
            onPick();
          }}
          aria-label={
            picked
              ? `ביטול העברת ${assignment.employee}`
              : `העברת ${assignment.employee} למשמרת אחרת`
          }
          aria-pressed={picked}
          title={picked ? "ביטול ההעברה" : "העברה למשמרת אחרת"}
        >
          <Move size={12} />
        </button>
      ) : null}

      {draggable ? (
        <span className="board-card-grip" aria-hidden="true">
          <GripVertical size={12} />
        </span>
      ) : null}
    </div>
  );
}

/** The hover on the identity line: who she is, then why she is here.
 *
 *  D8 keeps `assignment.reason` on every row and the manager must be able to
 *  reach it — it is the account of a placement, and on a hand-placed row it
 *  is the manager's own sentence. Moving it off the card's face does not
 *  mean losing it: it moves from the line that is read a hundred times a
 *  week to the one place somebody goes when they actually want to know.
 */
function identityTitle(
  assignment: Assignment,
  person: CardPerson,
  reasons: AlarmReason[],
): string {
  const who = [
    person.role,
    person.rotation,
    person.is_shift_manager ? "מפקד/ת" : "",
    person.is_overlap ? "נחפף/ת" : "",
    person.status ? STATUS_LABELS[person.status] : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const lines = [`${assignment.employee}${who ? ` — ${who}` : ""}`];
  if (person.note) lines.push(`הערה: ${person.note}`);
  if (reasons.length) {
    lines.push("", "⚠ למה הכרטיס מסומן:");
    for (const row of reasons) lines.push(`• ${row.full}`);
    lines.push("");
  }
  if (assignment.reason) lines.push(`סיבת השיבוץ: ${assignment.reason}`);
  return lines.join("\n");
}

interface AlarmReason {
  /** The rule and the number, short enough for the card's last line. */
  short: string;
  /** The audit's full sentence, for the hover. */
  full: string;
}

/** Every reason this card is red, most serious first.
 *
 *  A recorded constraint and the audit's `unavailable` finding are usually
 *  the same fact seen twice — the board checks the constraint list itself
 *  so a fresh drop is flagged before the audit re-runs. The audit's version
 *  wins when both are there, since it carries the constraint's reason;
 *  the board's own one stands in only when the audit has not spoken. */
function alarmReasons(
  employee: string,
  blocker: Constraint | null,
  warnings: ScheduleWarning[],
): AlarmReason[] {
  const ordered = [
    ...warnings.filter((row) => row.severity === "warning"),
    ...warnings.filter((row) => row.severity !== "warning"),
  ];
  const reasons = ordered.map((row) => ({
    short: warningHeadline(row),
    full: row.message,
  }));
  const audited = warnings.some((row) => row.code === "unavailable");
  if (blocker && !audited) {
    reasons.unshift({
      short: constraintHeadline(blocker),
      full: constraintSentence(employee, blocker),
    });
  }
  return reasons;
}

/** The card's identity as one spoken phrase, for `aria-label`. */
function ariaWho(assignment: Assignment, person: CardPerson): string {
  return [
    assignment.employee,
    person.role,
    person.rotation,
    person.is_shift_manager ? "מפקד/ת" : "",
    person.is_overlap ? "נחפף/ת" : "",
    person.status ? STATUS_LABELS[person.status] : "",
  ]
    .filter(Boolean)
    .join(", ");
}
