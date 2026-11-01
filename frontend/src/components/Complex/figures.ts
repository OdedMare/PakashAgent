import { orderByHours } from "@/components/Board/shiftOrder";
import type { ComplexBoard, ComplexPeriod } from "@/types";

export type Unit = ComplexBoard["teams"][number];

/** Which משמרת, and which of its shift types, the board narrows to. */
export interface Focus {
  unit: string | null;
  shift: string | null;
}

/** One cell of the combined board: the seats the stored grid asks for and
 *  who stands there. `null` when no period of the משמרת covers the day. */
export interface CellReading {
  seats: number;
  names: string[];
  status: ComplexPeriod["status"];
}

export function readCell(unit: Unit, shift: string, day: string): CellReading | null {
  const period = unit.periods.find((p) => p.starts_on <= day && day <= p.ends_on);
  if (!period) return null;
  const seats = period.slots
    .filter((slot) => slot.slot_date === day && slot.shift_name === shift)
    .reduce((sum, slot) => sum + (slot.headcount || 0), 0);
  const names = period.assignments
    .filter((row) => row.date === day && row.shift === shift)
    .map((row) => row.employee);
  return { seats, names, status: period.status };
}

/** A משמרת's shift types in the order its own board reads them: by the
 *  clock, then any the stored grid has that setup no longer declares. */
export function shiftsOf(unit: Unit): string[] {
  const starts: Record<string, string> = {};
  const names: string[] = [];
  for (const shift of unit.shifts) {
    starts[shift.name] = shift.start_time;
    names.push(shift.name);
  }
  for (const period of unit.periods) {
    for (const slot of period.slots) {
      if (!names.includes(slot.shift_name)) {
        names.push(slot.shift_name);
        starts[slot.shift_name] = slot.start_time;
      }
    }
  }
  return orderByHours(names, starts);
}

export interface Figures {
  seats: number;
  assigned: number;
  open: number;
  soldiers: number;
  warnings: number;
  published: number;
  planned: number;
  units: number;
}

/** The tiles' numbers over what is on screen — the משמרות and shift types
 *  the focus leaves in, and the days the view draws. A reading of the
 *  stored grids, never a judgement: each משמרת's own audit is where
 *  coverage is decided. */
export function figuresOf(units: Unit[], days: string[], focus: Focus): Figures {
  const figures: Figures = {
    seats: 0, assigned: 0, open: 0, soldiers: 0, warnings: 0,
    published: 0, planned: 0, units: units.length,
  };
  const people = new Set<string>();
  for (const unit of units) {
    const touching = unit.periods.filter((p) => p.starts_on <= days[days.length - 1] && p.ends_on >= days[0]);
    if (touching.length) figures.planned += 1;
    if (touching.length && touching.every((p) => p.status === "published")) figures.published += 1;
    figures.warnings += touching.reduce((sum, p) => sum + p.warnings, 0);
    for (const shift of shiftsOf(unit)) {
      if (focus.shift && shift !== focus.shift) continue;
      for (const day of days) {
        const cell = readCell(unit, shift, day);
        if (!cell) continue;
        figures.seats += cell.seats;
        figures.assigned += Math.min(cell.names.length, cell.seats || cell.names.length);
        figures.open += Math.max(0, cell.seats - cell.names.length);
        cell.names.forEach((name) => people.add(`${unit.id}:${name}`));
      }
    }
  }
  figures.soldiers = people.size;
  return figures;
}
