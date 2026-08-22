import type { Constraint, Slot } from "@/types";

/** Visual counterpart to the backend's availability arithmetic. Soft rows
 * never paint a cell as blocked; hard time windows do. */
export function constraintBlocksSlot(
  constraints: Constraint[],
  employee: string,
  date: string,
  slot: Slot,
): boolean {
  return constraints.some((row) => {
    if (
      !row.is_hard ||
      row.employee !== employee ||
      row.constraint_date !== date ||
      (row.shift_name !== "" && row.shift_name !== slot.shift_name)
    ) {
      return false;
    }

    const startBound = minutes(row.start_time);
    const endBound = minutes(row.end_time);
    if (startBound === null && endBound === null) return !row.available;

    const shiftStart = minutes(slot.start_time);
    let shiftEnd = minutes(slot.end_time);
    if (shiftStart === null || shiftEnd === null) return false;
    if (shiftEnd <= shiftStart) shiftEnd += 24 * 60;

    if (row.available) {
      let windowEnd = endBound;
      if (startBound !== null && windowEnd !== null && windowEnd <= startBound) {
        windowEnd += 24 * 60;
      }
      return (
        (startBound !== null && shiftStart < startBound) ||
        (windowEnd !== null && shiftEnd > windowEnd)
      );
    }

    const blockedStart = startBound ?? 0;
    let blockedEnd = endBound ?? 24 * 60;
    if (startBound !== null && endBound !== null && blockedEnd <= blockedStart) {
      blockedEnd += 24 * 60;
    }
    return shiftStart < blockedEnd && blockedStart < shiftEnd;
  });
}

function minutes(value: string): number | null {
  const match = /^(\d{2}):(\d{2})/.exec(value);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  return hour < 24 && minute < 60 ? hour * 60 + minute : null;
}
