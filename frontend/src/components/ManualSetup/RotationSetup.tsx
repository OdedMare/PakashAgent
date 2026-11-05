/** The lettered weekend cycles and how a stored anchor is read.
 *
 *  Which group closes which weekend is the server's arithmetic
 *  (`bl/rotation`), from one anchor per cycle: the weekend group א closes. */

import { addDays } from "./closureShapes";

export const CYCLES = {
  round: { label: "סבב", groups: ["א", "ב"] },
  triplet: { label: "תלתון", groups: ["א", "ב", "ג"] },
  quad: { label: "רבעון", groups: ["א", "ב", "ג", "ד"] },
  quint: { label: "חמישון", groups: ["א", "ב", "ג", "ד", "ה"] },
} as const;
export type Cycle = keyof typeof CYCLES;

/** The weekend group א closes, from an anchor stated for any group.
 *
 *  An older profile may anchor on whichever group the manager happened to
 *  name. Moving that to א's next turn describes the same cycle. */
export function firstGroupAnchor(pattern: Cycle, date: string, group: string): string {
  const groups: readonly string[] = CYCLES[pattern].groups;
  const index = groups.indexOf(group);
  return index > 0 ? addDays(date, 7 * (groups.length - index)) : date;
}
