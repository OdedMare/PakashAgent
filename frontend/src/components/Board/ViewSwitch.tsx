"use client";

import type { BoardView } from "./views";
import { BOARD_VIEWS } from "./views";

/** Day, week, two weeks, month.
 *
 *  A row of four rather than a dropdown: there are few enough to see at
 *  once, and the one in force should be readable without opening anything.
 *  Each is a real button with `aria-pressed`, so the choice is announced as
 *  a state and not as four unrelated commands.
 *
 *  Switching keeps the day the board is anchored on. Going from a month to a
 *  week lands on the week the manager was already in, never back on today —
 *  the view is how wide to look, not where.
 */
export function ViewSwitch({
  view,
  onChange,
}: {
  view: BoardView;
  onChange: (view: BoardView) => void;
}) {
  return (
    <div
      className="board-views"
      role="group"
      aria-label="תצוגת הלוח"
      data-tour="board-views"
    >
      {BOARD_VIEWS.map((row) => (
        <button
          key={row.id}
          type="button"
          className={`board-view${row.id === view ? " is-on" : ""}`}
          aria-pressed={row.id === view}
          onClick={() => onChange(row.id)}
        >
          {row.label}
        </button>
      ))}
    </div>
  );
}
