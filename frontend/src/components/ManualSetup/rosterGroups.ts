/** How the setup roster is grouped and narrowed. Pure: the setup form owns
 *  the rows, this only decides which of them are shown and under which
 *  heading. Nothing here is saved — it is a way of reading the list. */

export type RosterGrouping = "none" | "service" | "staffing" | "shift" | "exit";

export const GROUPINGS: Record<RosterGrouping, string> = {
  none: "ללא",
  service: "מעמד",
  staffing: "נספר בתקן",
  shift: "משמרת",
  exit: "מבנה יציאות",
};

/** What the grouping reads off one person. The form passes these in so the
 *  defaults (an unset `service_type` is תקן, an unset exit pattern is the
 *  unit's) stay where they are already decided. */
export type RosterPerson = {
  service: string;
  counts: boolean;
  shifts: string[];
  exitKey: string;
  exitLabel: string;
};

export type RosterGroup = { key: string; label: string; indices: number[] };

export const NO_SHIFT = "ללא משמרות מותרות";

export function groupRoster(
  people: RosterPerson[],
  grouping: RosterGrouping,
  services: Record<string, string>,
  shiftNames: string[],
  visible: (person: RosterPerson) => boolean,
): RosterGroup[] {
  const shown = people.map((person, index) => ({ person, index })).filter(({ person }) => visible(person));
  if (grouping === "none") return [{ key: "all", label: "", indices: shown.map(({ index }) => index) }];

  const groups = new Map<string, RosterGroup>();
  const add = (key: string, label: string, index: number) => {
    const group = groups.get(key) ?? { key, label, indices: [] };
    group.indices.push(index);
    groups.set(key, group);
  };
  // Headings in a fixed, meaningful order, so a group does not jump when the
  // first person in it changes.
  if (grouping === "service") Object.entries(services).forEach(([value, label]) => groups.set(value, { key: value, label, indices: [] }));
  if (grouping === "staffing") {
    groups.set("counts", { key: "counts", label: "נספרים בתקן", indices: [] });
    groups.set("extra", { key: "extra", label: "לא נספרים בתקן", indices: [] });
  }
  if (grouping === "shift") shiftNames.forEach((name) => groups.set(name, { key: name, label: name, indices: [] }));

  for (const { person, index } of shown) {
    if (grouping === "service") add(person.service, services[person.service] ?? person.service, index);
    else if (grouping === "staffing") add(person.counts ? "counts" : "extra", "", index);
    else if (grouping === "exit") add(person.exitKey, person.exitLabel, index);
    else {
      // A person allowed on several shifts is listed under each of them.
      const theirs = person.shifts.filter((name) => shiftNames.includes(name));
      if (!theirs.length) add(NO_SHIFT, NO_SHIFT, index);
      theirs.forEach((name) => add(name, name, index));
    }
  }
  return [...groups.values()].filter((group) => group.indices.length);
}
