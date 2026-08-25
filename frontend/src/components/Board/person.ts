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
 *  the editor had to offer both.
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
  const name = PATTERN_LABELS[text(pattern)] ?? "";
  const arm = text(group);
  if (!name) return arm ? `סבב ${arm}` : "";
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
};
