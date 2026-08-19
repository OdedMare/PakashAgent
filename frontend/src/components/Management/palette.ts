/** A stable colour per employee, for reading a grid at a glance.
 *
 *  The calendar's job is to answer "who is on tonight" and "is anyone on
 *  five days running" without reading a single name. Colour is what makes
 *  the second question answerable at a glance — a person's shifts become a
 *  shape on the grid rather than a string to scan for.
 *
 *  Three properties this has to have, in order:
 *
 *  1. **Distinct within one team.** Ten people must get ten different
 *     hues, because two people sharing a colour is precisely the confusion
 *     the colour was added to remove. That rules out hashing the name:
 *     ten names into ten buckets collide about two thirds of the time by
 *     the birthday bound, however good the hash is. Hues come from position
 *     in the roster instead, and a name the roster does not carry falls back
 *     to a hash — see `buildPalette`.
 *  2. **Legible in both themes.** Each hue carries a light-mode and a
 *     dark-mode pair, chosen so the text clears 4.5:1 on its own fill in the
 *     theme it belongs to. A palette tuned only for the cream ground goes
 *     muddy the moment the manager hits the moon button.
 *  3. **Not the alarm colours.** `--warning` and `--danger` mean something
 *     specific in this product — a person assigned against a constraint, a
 *     slot short of headcount. An employee whose personal colour happened to
 *     be alarm-red would read as a problem on every cell they appear in, so
 *     the hues here stay clear of both.
 *
 *  Deliberately *not* stored anywhere. A colour is a rendering of a name,
 *  not a fact about a person: persisting it would mean a table, a migration,
 *  and a per-team colour setting for something the manager never asked to
 *  choose. If picking colours by hand is ever wanted, this is the seam — the
 *  lookup stays, and only where the index comes from changes.
 */

export interface EmployeeColor {
  /** Cell fill behind the name. */
  bg: string;
  /** The name itself. Clears 4.5:1 on `bg` in its theme. */
  fg: string;
  /** Chip border, and the spine on a person's row in the month view. */
  border: string;
}

/** Ten hues, evenly spread and none of them alarm-coloured.
 *
 *  Ten rather than more because a hue is only useful while it is
 *  *distinguishable* from its neighbours — past ten the palette starts
 *  answering "which teal was Dana" instead of the question the colour was
 *  there for. Teams larger than ten wrap, and two people sharing a hue is
 *  recoverable in a way twenty indistinguishable teals is not: the name is
 *  still written on the chip.
 *
 *  Each entry is `[light, dark]`. The dark variants are not the light ones
 *  dimmed — a dark fill needs a *lighter* foreground, so the pair is
 *  inverted rather than scaled. */
const HUES: Array<[EmployeeColor, EmployeeColor]> = [
  [
    { bg: "#dbeafe", fg: "#1e3a5f", border: "#93c5fd" },
    { bg: "#1e3a5f", fg: "#bfdbfe", border: "#3b6ea5" },
  ],
  [
    { bg: "#d7f0e3", fg: "#14532d", border: "#86d0a9" },
    { bg: "#1b4332", fg: "#a7e8c4", border: "#2f7355" },
  ],
  [
    { bg: "#ede0f7", fg: "#4c1d95", border: "#c4a7e7" },
    { bg: "#3c2a5e", fg: "#d8c2f0", border: "#6b4ba3" },
  ],
  [
    { bg: "#fde8d3", fg: "#7c3a06", border: "#f5bf82" },
    { bg: "#4d2f13", fg: "#fbd7ab", border: "#8a5a26" },
  ],
  [
    { bg: "#d5f2f4", fg: "#134e52", border: "#84cdd4" },
    { bg: "#123f43", fg: "#a5e4ea", border: "#2b7a82" },
  ],
  [
    { bg: "#fbe0ee", fg: "#831843", border: "#f0a6c9" },
    { bg: "#4d1730", fg: "#f7c2da", border: "#8c3560" },
  ],
  [
    { bg: "#e6eed4", fg: "#3f4d13", border: "#b9cd86" },
    { bg: "#333f14", fg: "#d3e3a8", border: "#5e7328" },
  ],
  [
    { bg: "#dfe2f7", fg: "#2b2f6b", border: "#a3aae4" },
    { bg: "#262a5c", fg: "#c3c8ef", border: "#4950a0" },
  ],
  [
    { bg: "#f7e6d0", fg: "#6b4310", border: "#dfb47a" },
    { bg: "#453017", fg: "#ecd0a8", border: "#7d5a2b" },
  ],
  [
    { bg: "#d9ecec", fg: "#264d4d", border: "#8cc2c2" },
    { bg: "#1d4040", fg: "#aadada", border: "#357070" },
  ],
];

/** Stable fallback hash, for a name the roster does not carry.
 *
 *  djb2. Only used when there is no roster to take a position from — an
 *  assignment left behind by somebody since removed from the profile, or
 *  the first render before the overview lands. Collisions are likelier here
 *  than in the roster path (ten names into ten buckets collide by the
 *  birthday bound however good the hash is), which is exactly why the
 *  roster path exists and this is the fallback rather than the rule.
 *
 *  `>>> 0` keeps it unsigned. Without it a name that overflows into a
 *  negative gets a negative modulus and indexes outside the array, which
 *  renders as one unlucky person having no colour at all rather than as
 *  anything that looks like a bug.
 */
function hashIndex(name: string): number {
  let hash = 5381;
  for (let i = 0; i < name.length; i += 1) {
    hash = ((hash << 5) + hash + name.charCodeAt(i)) >>> 0;
  }
  return hash % HUES.length;
}

/** Hue per person, assigned by position in the roster.
 *
 *  Position rather than a hash of the name, because ten names hashed into
 *  ten buckets collide about two-thirds of the time — the birthday bound,
 *  not a weakness in the hash, so a better hash does not fix it. Walking the
 *  roster in order gives the first ten people ten *different* hues, which is
 *  the property the colour was for.
 *
 *  The cost is that inserting somebody mid-roster shifts the hues below
 *  them. That is the right trade: the profile's employee list is appended to
 *  far more often than it is inserted into, appending shifts nothing, and a
 *  team that reshuffles its roster has bigger changes on screen than a
 *  recoloured chip. A name absent from the roster keeps a hashed hue, so a
 *  person removed from the profile does not blank out the shifts they
 *  already worked.
 */
export function buildPalette(roster: string[]): (name: string) => number {
  const byName = new Map<string, number>();
  roster.forEach((name) => {
    const key = (name || "").trim();
    if (key && !byName.has(key)) byName.set(key, byName.size % HUES.length);
  });
  return (name: string) => {
    const key = (name || "").trim();
    const seat = byName.get(key);
    return seat === undefined ? hashIndex(key) : seat;
  };
}

/** The colour for one person, given their hue index. */
export function colorFor(index: number, dark: boolean): EmployeeColor {
  const pair = HUES[((index % HUES.length) + HUES.length) % HUES.length];
  return dark ? pair[1] : pair[0];
}

/** The colour as inline style properties, ready for a chip.
 *
 *  Returned as a style object rather than a class because the hue depends on
 *  the roster at render time — there is no fixed set of class names to
 *  write, and generating ten CSS rules per theme would put the palette in
 *  two places that could disagree.
 */
export function colorStyle(
  index: number,
  dark: boolean,
): React.CSSProperties {
  const color = colorFor(index, dark);
  return {
    background: color.bg,
    color: color.fg,
    borderColor: color.border,
  };
}
