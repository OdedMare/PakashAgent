"use client";

import { useCallback, useState } from "react";

import type { Assignment } from "@/types";

/** Moving a shift without a mouse.
 *
 *  HTML5 drag-and-drop is the board's primary gesture and it stays that way,
 *  but it answers to exactly one input: a pointer that can press, travel and
 *  release. It does not fire on touch at all, and it is unreachable from the
 *  keyboard. That left the board's central act — moving somebody from one
 *  cell to another — available only to a manager at a desk with a mouse,
 *  while `board.css` claimed every core action stays reachable on a phone.
 *
 *  This is the second input path to the *same* act, not a second way to
 *  write. A pick followed by a drop calls the identical `onDropCard` a drag
 *  does, which opens the identical confirmation, which collects the
 *  identical reason (**D12**). Nothing here reaches the server; nothing here
 *  skips the dialog. The gesture changed, the decision did not.
 *
 *  Two steps, deliberately: **pick** the card, then **place** it. A single
 *  keystroke that both selected and moved would be a write without a target
 *  chosen, and a touch interface where the first tap moves something is one
 *  where every mis-tap is a change the manager owes somebody an account of.
 */
export interface MoveMode {
  /** The card waiting for a destination, or null when nothing is picked. */
  picked: Assignment | null;
  /** Start moving this card. Picking a second card replaces the first. */
  pick: (assignment: Assignment) => void;
  /** Abandon the move. Nothing was written, so there is nothing to undo. */
  cancel: () => void;
  /** Whether this card is the one currently picked up. */
  isPicked: (assignment: Assignment) => boolean;
}

export function useMoveMode(): MoveMode {
  const [picked, setPicked] = useState<Assignment | null>(null);

  const pick = useCallback((assignment: Assignment) => {
    // Picking the card that is already picked puts it back down. The
    // gesture that starts a move is the one that cancels it, so a manager
    // who picked the wrong card does not have to find a different control.
    setPicked((current) => (current?.id === assignment.id ? null : assignment));
  }, []);

  const cancel = useCallback(() => setPicked(null), []);

  const isPicked = useCallback(
    (assignment: Assignment) => picked?.id === assignment.id,
    [picked],
  );

  return { picked, pick, cancel, isPicked };
}
