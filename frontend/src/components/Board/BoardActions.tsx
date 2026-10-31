"use client";

import { Download, Eraser, Eye, EyeOff, Sparkles, Trash2, Upload } from "lucide-react";

import type { Schedule } from "@/types";

import type { RemovalTarget } from "./ConfirmRemoval";

/** The board's own actions on the period on screen.
 *
 *  `period` is null under a two-week or month view: publish, clear, delete
 *  and export have no one period to mean there, so they are not offered
 *  (`views.ts`). Clearing and deleting are also withheld while the period
 *  is not `writable` — a published week refuses every write, and a running
 *  build owns the days it has not reached. Nothing here writes on its own:
 *  removal opens `ConfirmRemoval`, which is what asks and writes. */
export function BoardActions({
  period,
  busy,
  writable,
  touchCount,
  onOpenAgent,
  onExport,
  onImport,
  onPublish,
  onRemove,
}: {
  period: Schedule | null;
  busy: boolean;
  writable: boolean;
  /** How many shifts on screen the agent's conversation is about. */
  touchCount: number;
  onOpenAgent?: () => void;
  onExport: (scheduleId: string) => void;
  onImport?: () => void;
  onPublish: (scheduleId: string, published: boolean) => void;
  onRemove: (target: RemovalTarget) => void;
}) {
  return (
    <div className="board-head-actions" data-tour="board-actions">
      {period ? (
        <span className={`board-status is-${period.status}`}>
          {period.status === "published" ? "פורסם" : "טיוטה"}
        </span>
      ) : null}
      {onOpenAgent ? (
        <button
          type="button"
          className={`ghost-button${touchCount ? " is-live" : ""}`}
          onClick={onOpenAgent}
          title={
            touchCount
              ? `הסוכן מתייחס ל-${touchCount} משמרות בשבוע הזה`
              : "שיחה עם הסוכן על הסידור"
          }
        >
          <Sparkles size={14} />
          הסוכן
          {/* The count is what connects the two screens. The panels
              themselves live in the control room, so without it a
              manager on the board can see cells lit and have no idea
              where the sentence explaining them is. */}
          {touchCount ? (
            <span className="board-agent-count">{touchCount}</span>
          ) : null}
        </button>
      ) : null}
      {period ? (
        <button
          type="button"
          className="ghost-button"
          onClick={() => onExport(period.id)}
          disabled={busy}
          title="הורדת הסידור כקובץ אקסל"
        >
          <Download size={14} />
          אקסל
        </button>
      ) : null}
      {onImport ? (
        <button
          type="button"
          className="ghost-button"
          onClick={onImport}
          disabled={busy}
          title="ייבוא סידור קיים מקובץ — כל צורה של טבלה"
        >
          <Upload size={14} />
          ייבוא
        </button>
      ) : null}
      {/* Taking the week back. Two buttons because they undo two
          different things: clearing empties the grid the manager is
          looking at, deleting removes the period that grid belongs to.
          Both are withheld while the board is not writable — a published
          week refuses every write, and a running build owns the days it
          has not reached. */}
      {period && writable ? (
        <button
          type="button"
          className="ghost-button"
          onClick={() =>
            onRemove({ mode: "week", count: period.assignments.length })
          }
          title="מחיקת כל השיבוצים בשבוע, בלי למחוק את שורות המשמרות"
        >
          <Eraser size={14} />
          ניקוי השבוע
        </button>
      ) : null}
      {period && writable ? (
        <button
          type="button"
          className="ghost-button is-danger"
          onClick={() =>
            onRemove({
              mode: "period",
              count: period.assignments.length,
            })
          }
          title="מחיקת הסידור לשבוע הזה, כולל שורות המשמרות"
        >
          <Trash2 size={14} />
          מחיקת הסידור
        </button>
      ) : null}
      {period ? (
        <button
          type="button"
          className="ghost-button"
          onClick={() =>
            onPublish(period.id, period.status !== "published")
          }
          disabled={busy}
        >
          {period.status === "published" ? (
            <>
              <EyeOff size={14} />
              החזרה לטיוטה
            </>
          ) : (
            <>
              <Eye size={14} />
              פרסום לצוות
            </>
          )}
        </button>
      ) : null}
    </div>
  );
}
