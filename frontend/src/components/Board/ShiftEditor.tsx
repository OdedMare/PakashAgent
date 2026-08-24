"use client";

import { AlertTriangle, CalendarPlus, CheckCircle2, Copy, GraduationCap, MessageSquareText, PencilLine, ShieldCheck, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { formatDate, hebrewWeekday } from "@/components/Management/Calendar";
import type { Assignment, PlacementCheck, Schedule, Slot } from "@/types";

import { PlacementVerdict } from "./ConfirmDrop";

/** What the editor was opened on.
 *
 *  Creating and editing are one panel because they are one question — "who
 *  is on this shift" — asked at two moments. Two panels would mean two
 *  layouts, two validation paths and two places for the Hebrew to drift. */
export type EditorTarget =
  | { mode: "create"; shift_name: string; slot_date: string }
  | { mode: "edit"; assignment: Assignment };

/** Creating and editing a shift assignment.
 *
 *  **Which write happens depends on what changed**, and that follows the
 *  decisions rather than convenience:
 *
 *  - Filling an empty cell **writes immediately** — it takes nothing away
 *    from anybody, so nobody is owed an explanation
 *    ([D18](../../../docs/DECISIONS.md#d18--the-boss-can-place-a-shift-without-the-agent-️-completes-d6)).
 *  - Moving somebody already placed to another day, shift or person goes
 *    through the **reason dialog**, exactly as a drag does
 *    ([D12](../../../docs/DECISIONS.md#d12--dragging-a-shift-is-a-proposal-not-an-edit)):
 *    it takes a shift away from someone, and that is a change somebody is
 *    owed an account of. The editor is a different gesture from the drag,
 *    not a different rule.
 *  - Removing somebody asks for a reason and records it when given, which
 *    is what `unassign` already does — a cell cleared seconds after being
 *    filled by mistake is a correction, not a decision.
 *
 *  Every check on this panel is `bl/placement.py`: pure arithmetic, no model
 *  call. The manager sees what a choice would cost as they make it, with the
 *  agent unavailable.
 */
export function ShiftEditor({
  target,
  schedule,
  employees,
  roles,
  busy,
  check,
  checking,
  onCheck,
  onAssign,
  onMove,
  onUnassign,
  onDuplicate,
  onClose,
}: {
  target: EditorTarget;
  schedule: Schedule;
  employees: string[];
  roles: Record<string, string>;
  busy: boolean;
  check: PlacementCheck | null;
  checking: boolean;
  /** Ask what the current selection would cost. Debounced by the caller. */
  onCheck: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
    moving_assignment_id?: string;
  }) => void;
  onAssign: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
    reason: string;
  }) => void;
  /** A change to an existing row. Routed through the reason dialog (D12). */
  onMove: (input: {
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  }) => void;
  onUnassign: (input: { assignment: Assignment; reason: string }) => void;
  /** Copy this assignment onto another date, same shift. */
  onDuplicate: (input: {
    employee: string;
    shift_name: string;
    slot_date: string;
  }) => void;
  onClose: () => void;
}) {
  const editing = target.mode === "edit" ? target.assignment : null;

  const [employee, setEmployee] = useState(editing?.employee ?? "");
  const [shiftName, setShiftName] = useState(
    editing?.shift ?? (target.mode === "create" ? target.shift_name : ""),
  );
  const [slotDate, setSlotDate] = useState(
    editing?.date ?? (target.mode === "create" ? target.slot_date : ""),
  );
  const [reason, setReason] = useState("");
  const [duplicateDate, setDuplicateDate] = useState("");

  // The vocabulary and the dates come from the stored grid, never from a
  // literal: shift names are the workplace's own (D9) and the dates are the
  // period the manager is actually looking at.
  const shifts = useMemo(() => {
    const seen = new Set<string>();
    for (const slot of schedule.slots) seen.add(slot.shift_name);
    return Array.from(seen);
  }, [schedule.slots]);

  const dates = useMemo(() => {
    const seen = new Set<string>();
    for (const slot of schedule.slots) seen.add(slot.slot_date);
    return Array.from(seen).sort();
  }, [schedule.slots]);

  /** Whether the chosen (shift, date) pair is a slot that actually runs.
   *
   *  A shift that does not run on a day is not a gap to fill — it is a day
   *  the shift does not exist. Saving into one would be refused by the
   *  server with "המשמרת לא נמצאה בסידור", so the panel says so first. */
  const slot: Slot | undefined = schedule.slots.find(
    (row) => row.shift_name === shiftName && row.slot_date === slotDate,
  );

  // Re-checked whenever the selection changes. Cheap: it is one arithmetic
  // call on the server with no model behind it.
  useEffect(() => {
    if (!shiftName || !slotDate || !slot) return;
    onCheck({
      employee,
      shift_name: shiftName,
      slot_date: slotDate,
      moving_assignment_id: editing?.id,
    });
  }, [employee, shiftName, slotDate, slot, editing?.id, onCheck]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const moved =
    editing !== null &&
    (editing.shift !== shiftName ||
      editing.date !== slotDate ||
      editing.employee !== employee);

  const canSave = Boolean(employee && shiftName && slotDate && slot && !busy);

  const save = () => {
    if (!canSave) return;
    if (!editing) {
      onAssign({
        employee,
        shift_name: shiftName,
        slot_date: slotDate,
        reason: reason.trim(),
      });
      return;
    }
    if (!moved) {
      onClose();
      return;
    }
    // A changed person is a removal plus a placement, not a move: the row
    // being dragged belongs to somebody, and handing their shift to a
    // colleague by editing a dropdown should cost the same account a drag
    // costs. Both go through the same dialog.
    onMove({ assignment: editing, shift_name: shiftName, slot_date: slotDate });
  };

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal board-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="shift-editor-title"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="modal-header">
          <h2 id="shift-editor-title">
            {editing ? <PencilLine size={17} /> : <CalendarPlus size={17} />}
            {editing ? "עריכת שיבוץ" : "שיבוץ חדש"}
          </h2>
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="סגירה"
          >
            <X size={17} />
          </button>
        </header>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            save();
          }}
        >
          <div className="board-editor-fields">
            <label className="modal-field">
              <span>עובד</span>
              <select
                value={employee}
                onChange={(event) => setEmployee(event.target.value)}
              >
                {/* Leaving a shift unassigned is a real answer, not an
                    omission: a slot with nobody on it is what the coverage
                    figures and the unfilled warning are about. */}
                <option value="">— ללא שיבוץ —</option>
                {(check?.candidates.length ? check.candidates.map((candidate) => candidate.employee) : employees).map((name) => (
                  <option key={name} value={name}>
                    {candidateOption(name, roles[name], check)}
                  </option>
                ))}
              </select>
            </label>

            <label className="modal-field">
              <span>משמרת</span>
              <select
                value={shiftName}
                onChange={(event) => setShiftName(event.target.value)}
              >
                {shifts.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>

            <label className="modal-field">
              <span>תאריך</span>
              <select
                value={slotDate}
                onChange={(event) => setSlotDate(event.target.value)}
              >
                {dates.map((date) => (
                  <option key={date} value={date}>
                    {hebrewWeekday(date)} · {formatDate(date)}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {check?.candidates.length ? (
            <div className="board-availability" aria-label="זמינות החיילים למשמרת">
              <div className="board-availability-head">
                <strong>מי פנוי למשמרת</strong>
                <span>{check.candidates.filter((candidate) => candidate.available).length} מתוך {check.candidates.length} ללא התראה</span>
              </div>
              <div className="board-candidate-list">
                {check.candidates.map((candidate) => (
                  <button
                    type="button"
                    key={candidate.employee}
                    className={`board-candidate${candidate.employee === employee ? " is-selected" : ""}${candidate.available ? " is-available" : " is-unavailable"}`}
                    onClick={() => setEmployee(candidate.employee)}
                    aria-pressed={candidate.employee === employee}
                  >
                    {candidate.available ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                    <span className="board-candidate-copy">
                      <strong>{candidate.employee}</strong>
                      <small>{candidate.available ? `פנוי/ה · ${formatHours(candidate.hours)} בתקופה` : candidate.reasons.join(" ")}</small>
                    </span>
                    {candidate.is_shift_manager ? <span className="board-candidate-badge"><ShieldCheck size={12} /> מפקד/ת</span> : null}
                    {candidate.can_train ? <span className="board-candidate-badge"><GraduationCap size={12} /> חופף/ת</span> : null}
                  </button>
                ))}
              </div>
              <small className="board-availability-note">אפשר לבחור גם חייל/ת עם התראה; הסיבה נשארת גלויה וההחלטה בידיך.</small>
            </div>
          ) : checking ? <p className="board-availability-loading" role="status">בודק מי פנוי למשמרת…</p> : null}

          {/* The hours are the shift's own, from the vocabulary. This panel
              edits one assignment; the clearly grouped time controls in the
              team settings edit the shift type for future schedules. */}
          {slot ? (
            <p className="board-editor-hours">
              {slot.start_time ? (
                <>
                  שעות המשמרת: {slot.start_time}–{slot.end_time}
                  {slot.is_on_call ? " · כוננות" : ""}
                </>
              ) : (
                "לא הוגדרו שעות למשמרת הזו"
              )}
              {" · "}
              דרושים {slot.headcount}
            </p>
          ) : (
            <p className="board-editor-hours is-missing">
              המשמרת הזו לא רצה בתאריך שנבחר. אפשר לבחור יום אחר או משמרת אחרת.
            </p>
          )}

          {employee && slot ? (
            <PlacementVerdict
              check={check}
              checking={checking}
              onPickEmployee={(name) => setEmployee(name)}
              onPickSlot={(picked) => {
                setShiftName(picked.shift_name);
                setSlotDate(picked.slot_date);
              }}
            />
          ) : null}

          {editing?.reason ? (
            <div className="board-assignment-reason">
              <MessageSquareText size={16} />
              <div><strong>למה שובץ/ה כאן</strong><p>{editing.reason}</p></div>
            </div>
          ) : null}

          {/* A reason is optional when filling an empty cell (D18) and
              required when moving somebody — which is why it is asked for
              here only in the first case, and by the move dialog in the
              second. */}
          {!editing ? (
            <label className="modal-field">
              <span>הערה לשיבוץ (רשות)</span>
              <input
                type="text"
                value={reason}
                maxLength={200}
                onChange={(event) => setReason(event.target.value)}
                placeholder="כיסוי חוסר, בקשת העובד…"
              />
            </label>
          ) : null}

          <div className="modal-actions board-editor-actions">
            {editing ? (
              <button
                type="button"
                className="danger-button"
                disabled={busy}
                onClick={() =>
                  onUnassign({ assignment: editing, reason: reason.trim() })
                }
                title="הסרת העובד מהמשמרת"
              >
                <Trash2 size={14} />
                הסרה מהמשמרת
              </button>
            ) : null}
            <button type="button" className="ghost-button" onClick={onClose}>
              ביטול
            </button>
            <button type="submit" className="primary-button" disabled={!canSave}>
              {busy ? "שומר…" : editing ? "שמירה" : "שיבוץ"}
            </button>
          </div>
        </form>

        {/* Duplication is its own row rather than a save option: it creates
            a *second* assignment and leaves this one alone, which is a
            different act from saving an edit. Same shift, another date —
            the domain model has no recurrence rule, so nothing here invents
            one (the product's periods are living schedules, D4). */}
        {editing || employee ? (
          <div className="board-duplicate">
            <span className="board-duplicate-label">
              <Copy size={13} />
              שכפול לתאריך נוסף
            </span>
            <select
              value={duplicateDate}
              onChange={(event) => setDuplicateDate(event.target.value)}
            >
              <option value="">בחירת תאריך…</option>
              {dates
                .filter((date) => date !== slotDate)
                .filter((date) =>
                  schedule.slots.some(
                    (row) =>
                      row.shift_name === shiftName && row.slot_date === date,
                  ),
                )
                .map((date) => (
                  <option key={date} value={date}>
                    {hebrewWeekday(date)} · {formatDate(date)}
                  </option>
                ))}
            </select>
            <button
              type="button"
              className="ghost-button"
              disabled={!duplicateDate || !employee || busy}
              onClick={() => {
                onDuplicate({
                  employee,
                  shift_name: shiftName,
                  slot_date: duplicateDate,
                });
                setDuplicateDate("");
              }}
            >
              שכפול
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function candidateOption(name: string, role: string, check: PlacementCheck | null): string {
  const candidate = check?.candidates.find((row) => row.employee === name);
  const status = candidate ? (candidate.available ? "פנוי/ה" : "עם התראה") : "";
  return [name, role, status].filter(Boolean).join(" · ");
}

function formatHours(hours: number): string {
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} שעות`;
}
