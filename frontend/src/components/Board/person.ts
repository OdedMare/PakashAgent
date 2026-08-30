import type { CardPerson } from "@/types";

/** How the roster's rotation fields read on a board card.
 *
 *  The profile stores a person's rotation as two fields — `exit_pattern`
 *  (which cycle they are on) and `rotation_group` (which arm of it) — and
 *  `bl/rotation.py` is clear that the group is what makes somebody rotate at
 *  all: a חמשושים person *with* a group goes out on their group's weekends,
 *  and the same person without one goes out every week. So the two are one
 *  fact to a manager and are rendered as one phrase, never as two chips that
 *  have to be mentally joined.
 *
 *  The wording matches `TeamPanel`'s `EXIT_PATTERN_LABELS`, minus the option
 *  list's "א / ב" — a card names the group somebody is actually in, where
 *  the editor had to offer both. Empty when the roster records neither
 *  field, so the card stays silent rather than guessing.
 */
const PATTERN_LABELS: Record<string, string> = {
  round: "סבב",
  triplet: "תלתון",
  hamshushim: "חמשושים",
  shushim: "שושים",
};

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function rotationLabel(pattern: unknown, group: unknown): string {
  const arm = text(group);
  // Nothing recorded means nothing said. The fallback below reads a rotation
  // out of a partial row; it must not invent one out of an empty row, or
  // every person the roster is silent about would be labelled "סבב".
  if (!text(pattern) && !arm) return "";
  // The same fallback `TeamPanel.exitPatternLabel` applies to a row whose
  // pattern was never written: a "ג" arm only exists in a triplet, so the
  // group names the cycle when the cycle does not name itself. Anything else
  // is the default round.
  const name =
    PATTERN_LABELS[text(pattern)] ??
    (arm === "ג" ? PATTERN_LABELS.triplet : PATTERN_LABELS.round);
  return arm ? `${name} ${arm}` : name;
}

/** What a card says about somebody the roster has never heard of.
 *
 *  Reachable: a schedule outlives the roster it was generated against, and a
 *  person removed from the team afterwards is still standing on last week's
 *  Tuesday. The card then shows the name and nothing else, which is the
 *  truth — inventing a role for them would be worse than the silence.
 */
export const EMPTY_PERSON: CardPerson = {
  role: "",
  rotation: "",
  is_shift_manager: false,
  is_overlap: false,
  // Somebody the roster no longer carries is still standing on that Tuesday
  // and still one of the people who were on it. Counting them out would make
  // a past week that was fully staffed read as short of the people who
  // actually worked it.
  counts_toward_staffing: true,
};

/** Whether a roster row fills one of a slot's seats.
 *
 *  Mirrors `bl/audit.counts_toward_staffing`, in the same order and for the
 *  same reason: the explicit field is the manager's answer and wins, and
 *  `service_type === "overlap"` is only the fallback for a row that never
 *  got one. Someone shadowing a shift is at work and still leaves it needing
 *  the people it asked for.
 */
export function fillsASeat(row: {
  counts_toward_staffing?: unknown;
  service_type?: unknown;
}): boolean {
  if (typeof row.counts_toward_staffing === "boolean") {
    return row.counts_toward_staffing;
  }
  return row.service_type !== "overlap";
}
