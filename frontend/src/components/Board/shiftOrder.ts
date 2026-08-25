"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

/** What order the shift rows run in, and who decides it.
 *
 *  The board used to draw its rows in the order the *slots* happened to
 *  declare them, which is the order the generator wrote them and carries no
 *  meaning a manager can see: a week could open with צהריים above בוקר, or
 *  with כונן לילה in the middle, and the same workplace could read
 *  differently from one period to the next. A board whose rows move around
 *  is one that has to be re-read every time it is opened.
 *
 *  So the default is now **the clock**: rows run by the hour their shift
 *  starts, which is the sequence a day actually happens in and the one the
 *  manager already has in their head. It is not alphabetical — alphabetising
 *  would scramble that sequence just as badly ([D9](../../../docs/DECISIONS.md#d9--shift-vocabulary-is-per-workplace)).
 *  A shift the vocabulary gave no hours to cannot be placed on a clock, so
 *  those keep their declared order and sit after the timed ones rather than
 *  being guessed at.
 *
 *  And the clock is a **default, not a rule**. A workplace whose day reads
 *  better in some other sequence can drag the rows into it, and that choice
 *  is remembered. What it is not is a change to the schedule: nothing in
 *  this file reaches the server, and reordering rows moves nobody between
 *  shifts. It is the same week, read in a different order — which is why it
 *  is allowed on a published board, where every write is refused.
 */

/** Distinguishes reordering a shift row from every other drag on the board. */
export const SHIFT_DRAG_TYPE = "application/x-pakash-shift";

/** The manager's own row order, when they have set one.
 *
 *  `localStorage` rather than the session store the displayed week uses: a
 *  week is something you are in the middle of today, but the order the rows
 *  read best in is a property of the workplace and holds tomorrow too.
 *  Stored under one key because a browser is signed in to one workspace at a
 *  time; a manager who switches workspaces sees the clock order again for
 *  any shift the other workplace did not name. */
const ORDER_KEY = "pakash.board.shift-order";

export interface ShiftOrder {
  /** The rows to draw, in the order to draw them. */
  shifts: string[];
  /** Whether a manager's own order is in force rather than the clock. */
  custom: boolean;
  /** Move a shift one row earlier (-1) or later (+1). The keyboard and touch
   *  path to what a drag does, and the only one that works on a phone. */
  nudge: (shift: string, direction: -1 | 1) => void;
  /** Drop `shift` onto `before`'s position, as a drag does. */
  moveTo: (shift: string, before: string) => void;
  /** Give the rows back to the clock. */
  reset: () => void;
}

/** The remembered order as a store the board subscribes to.
 *
 *  A store rather than component state, for two reasons that are not taste.
 *  This page is server-rendered and `localStorage` does not exist there, so
 *  reading it during render would throw — and reading it in an effect would
 *  set state during the first commit, which is the cascading render the lint
 *  rule names. `useSyncExternalStore` is the shape React provides for
 *  exactly this: a server snapshot of "no stored order" that hydrates
 *  cleanly into whatever the browser actually holds.
 *
 *  The value lives in memory and is *mirrored* to storage rather than read
 *  back out of it, so a browser refusing to persist costs the manager the
 *  memory of their order between visits, never the ability to set one now.
 */
let current: string[] | null | undefined;
const listeners = new Set<() => void>();

function announce(): void {
  for (const listener of listeners) listener();
}

/** Another tab changed the order. Re-read rather than trust the event's
 *  payload, so the parse and the validation stay in one place. */
function onStorageEvent(event: StorageEvent): void {
  if (event.key !== null && event.key !== ORDER_KEY) return;
  current = readStoredOrder();
  announce();
}

function subscribeToOrder(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", onStorageEvent);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorageEvent);
  };
}

/** The stored order, read once and then held. The identity has to be stable
 *  between calls or `useSyncExternalStore` re-renders forever. */
function orderSnapshot(): string[] | null {
  if (current === undefined) current = readStoredOrder();
  return current;
}

/** What the server renders against: nobody's stored order, so the clock. */
function serverOrderSnapshot(): string[] | null {
  return null;
}

function writeOrder(next: string[] | null): void {
  current = next;
  try {
    if (next) window.localStorage.setItem(ORDER_KEY, JSON.stringify(next));
    else window.localStorage.removeItem(ORDER_KEY);
  } catch {
    // Best effort. The store above already holds it for this visit.
  }
  announce();
}

/** The rows in clock order, overridden by the manager's own when they set one. */
export function useShiftOrder({
  shifts,
  startTimes,
}: {
  /** The shift vocabulary as the schedule declares it. */
  shifts: string[];
  /** Shift name -> `HH:MM` start, for whichever shifts carry hours. */
  startTimes: Record<string, string>;
}): ShiftOrder {
  const stored = useSyncExternalStore(
    subscribeToOrder,
    orderSnapshot,
    serverOrderSnapshot,
  );

  const byHours = useMemo(
    () => orderByHours(shifts, startTimes),
    [shifts, startTimes],
  );

  // A stored order that no longer describes this week is repaired rather
  // than dropped: shifts the workplace stopped running fall out, and ones it
  // started running are cut into the clock position they belong at instead
  // of being tacked on the end where they would read as a mistake.
  const ordered = useMemo(
    () => (stored ? mergeOrder(byHours, stored, startTimes) : byHours),
    [byHours, stored, startTimes],
  );

  const nudge = useCallback(
    (shift: string, direction: -1 | 1) => {
      const from = ordered.indexOf(shift);
      if (from < 0) return;
      const to = from + direction;
      // The ends are ends. Wrapping a row from the top of the board to the
      // bottom is never what somebody pressing "up" meant.
      if (to < 0 || to >= ordered.length) return;
      writeOrder(withMoved(ordered, from, to));
    },
    [ordered],
  );

  const moveTo = useCallback(
    (shift: string, before: string) => {
      const from = ordered.indexOf(shift);
      const to = ordered.indexOf(before);
      if (from < 0 || to < 0 || from === to) return;
      writeOrder(withMoved(ordered, from, to));
    },
    [ordered],
  );

  const reset = useCallback(() => writeOrder(null), []);

  return {
    shifts: ordered,
    // Custom only while the stored order actually differs from the clock's.
    // A manager who nudged a row back where it started is not owed a banner
    // telling them their board is out of its default order.
    custom: Boolean(stored) && !sameOrder(ordered, byHours),
    nudge,
    moveTo,
    reset,
  };
}

/** The shift names in the order their day runs.
 *
 *  Stable in both halves: timed shifts sort by the clock and ties keep the
 *  order they were declared in, and untimed ones keep it outright. Sorting
 *  the whole list with an unknown-goes-last comparator would be shorter and
 *  wrong — `Array.prototype.sort` is only stable for a *consistent*
 *  comparator, and "unknown is greater than everything" is not one. */
export function orderByHours(
  shifts: string[],
  startTimes: Record<string, string>,
): string[] {
  const timed: string[] = [];
  const untimed: string[] = [];
  for (const name of shifts) {
    if (minutesOf(startTimes[name]) === null) untimed.push(name);
    else timed.push(name);
  }
  timed.sort((a, b) => {
    const left = minutesOf(startTimes[a]) ?? 0;
    const right = minutesOf(startTimes[b]) ?? 0;
    if (left !== right) return left - right;
    return shifts.indexOf(a) - shifts.indexOf(b);
  });
  return [...timed, ...untimed];
}

/** `HH:MM` as minutes past midnight, or null when it is not a time.
 *
 *  A start time is a wall clock, not an instant: a shift starting at 23:00
 *  sorts to the bottom of the board because that is where the eye expects
 *  the night to be, even though it ends on the following date. */
export function minutesOf(value: string | undefined): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec((value ?? "").trim());
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

/** A stored order re-fitted to the shifts this week actually has.
 *
 *  A name the schedule no longer carries is dropped, and a name the stored
 *  order never heard of is cut in *after the last row that starts no later
 *  than it does*. Appending instead would put a new morning shift under the
 *  night one, which reads as a bug rather than as a row nobody has placed
 *  yet.
 *
 *  "After the last earlier row" rather than "before the first later one",
 *  because a stored order is the manager's and need not run by the clock at
 *  all: on a board they have already shuffled, the two rules disagree, and
 *  only this one puts the newcomer next to the shift it actually follows. */
export function mergeOrder(
  byHours: string[],
  stored: string[],
  startTimes: Record<string, string>,
): string[] {
  const present = new Set(byHours);
  const merged: string[] = [];
  for (const name of stored) {
    if (present.has(name) && !merged.includes(name)) merged.push(name);
  }
  for (const name of byHours) {
    if (merged.includes(name)) continue;
    const at = minutesOf(startTimes[name]);
    if (at === null) {
      merged.push(name);
      continue;
    }
    let after = -1;
    for (let row = merged.length - 1; row >= 0; row -= 1) {
      const theirs = minutesOf(startTimes[merged[row]]);
      if (theirs !== null && theirs <= at) {
        after = row;
        break;
      }
    }
    // Nothing on the board starts earlier, so the newcomer opens the day.
    merged.splice(after + 1, 0, name);
  }
  return merged;
}

function withMoved(order: string[], from: number, to: number): string[] {
  const next = [...order];
  const [row] = next.splice(from, 1);
  next.splice(to, 0, row);
  return next;
}

function sameOrder(left: string[], right: string[]): boolean {
  return (
    left.length === right.length && left.every((name, at) => name === right[at])
  );
}

/** The remembered order, or null when there is none to trust.
 *
 *  Anything on the origin can write to `localStorage`, so a stored value
 *  that is not a list of strings is discarded rather than rendered — the
 *  board would otherwise draw rows for shifts that do not exist. */
function readStoredOrder(): string[] | null {
  try {
    const raw = window.localStorage.getItem(ORDER_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return null;
    const names = parsed.filter(
      (row): row is string => typeof row === "string" && row.trim() !== "",
    );
    return names.length ? names : null;
  } catch {
    return null;
  }
}
