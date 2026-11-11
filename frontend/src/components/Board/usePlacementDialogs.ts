import { useCallback, useRef, useState } from "react";

import type { Assignment, PlacementCheck } from "@/types";

import type { EditorTarget } from "./ShiftEditor";
import type { useBoard } from "./useBoard";

type BoardCheck = ReturnType<typeof useBoard>["check"];

/** The two placement dialogs — a dropped move and the shift editor — and
 *  the one placement check they share.
 *
 *  `boardCheck` must be `board.check`, not anything derived from `board`:
 *  `useBoard` returns a fresh object every render, and `ShiftEditor`
 *  re-checks whenever `onCheck` changes — so depending on `board` made
 *  every answer trigger the next request, and the verdict flickered
 *  between "checking" and the result forever. */
export function usePlacementDialogs(boardCheck: BoardCheck, scheduleId: string | undefined) {
  // A drop parks the intended move here and opens the confirmation. Nothing
  // has reached the server at this point — the dialog is what writes (D12).
  const [pendingMove, setPendingMove] = useState<{
    assignment: Assignment;
    shift_name: string;
    slot_date: string;
  } | null>(null);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [check, setCheck] = useState<PlacementCheck | null>(null);
  const [checking, setChecking] = useState(false);
  // Every check is answered against the request that is still the newest.
  // Without this, a manager clicking through a dropdown gets whichever
  // response happens to land last, which may describe a choice they already
  // moved past.
  const checkToken = useRef(0);

  const runCheck = useCallback(
    async (input: {
      employee: string;
      shift_name: string;
      slot_date: string;
      moving_assignment_id?: string;
    }) => {
      const token = ++checkToken.current;
      setChecking(true);
      const result = await boardCheck({
        ...input,
        schedule_id: scheduleId,
      });
      if (token !== checkToken.current) return;
      setCheck(result);
      setChecking(false);
    },
    [boardCheck, scheduleId],
  );

  /** Open the confirmation for a proposed move, and check it.
   *
   *  Both halves happen here rather than in an effect watching `pendingMove`:
   *  a check is a *consequence of the gesture*, not a synchronisation with
   *  something outside React, and clearing the stale verdict is part of
   *  opening the dialog rather than a second render's job. */
  const openMove = useCallback(
    (move: {
      assignment: Assignment;
      shift_name: string;
      slot_date: string;
    }) => {
      setPendingMove(move);
      setCheck(null);
      void runCheck({
        employee: move.assignment.employee,
        shift_name: move.shift_name,
        slot_date: move.slot_date,
        moving_assignment_id: move.assignment.id,
      });
    },
    [runCheck],
  );

  /** Close whichever dialog is open, and drop its verdict with it.
   *
   *  One function for both because a verdict outliving the dialog that
   *  produced it is the bug: reopening the editor on a different cell would
   *  flash the previous cell's warning before the new check answers. The
   *  token bump makes any in-flight check land as stale. */
  const closeDialogs = useCallback(() => {
    checkToken.current += 1;
    setPendingMove(null);
    setEditor(null);
    setCheck(null);
    setChecking(false);
  }, []);

  return {
    pendingMove, editor, setEditor, check, setCheck, checking,
    runCheck, openMove, closeDialogs,
  };
}
