import { useMemo } from "react";

import type { CardPerson, ManagementOverview } from "@/types";

import { fillsASeat, rotationLabel } from "./person";

/** The roster as the board reads it: names, each person's role, the role
 *  list the filters offer, and who each person is for the card's identity
 *  lines. Derived from the overview alone, so nothing here can disagree
 *  with the roster the server sent. */
export function useRosterMaps(overview: ManagementOverview | undefined) {
  const roster = useMemo(
    () =>
      (overview?.employees ?? [])
        .map((row) => (typeof row.name === "string" ? row.name.trim() : ""))
        .filter(Boolean),
    [overview?.employees],
  );

  const roles = useMemo(() => {
    const map: Record<string, string> = {};
    for (const row of overview?.employees ?? []) {
      const name = typeof row.name === "string" ? row.name.trim() : "";
      const role = typeof row.role === "string" ? row.role.trim() : "";
      if (name) map[name] = role;
    }
    return map;
  }, [overview?.employees]);

  const roleOptions = useMemo(
    () => Array.from(new Set(Object.values(roles).filter(Boolean))).sort(),
    [roles],
  );
  // Who each person is, for the card's identity lines. One map rather than
  // one per fact: they are read together, on the same line, about the same
  // person, and a card that had to look up four maps to describe somebody
  // would drift the moment one of them was passed and another forgotten.
  const people = useMemo(() => {
    const map: Record<string, CardPerson> = {};
    for (const row of overview?.employees ?? []) {
      const name = typeof row.name === "string" ? row.name.trim() : "";
      if (!name) continue;
      map[name] = {
        role: typeof row.role === "string" ? row.role.trim() : "",
        rotation: rotationLabel(row.exit_pattern, row.rotation_group, overview?.profile?.workplace?.day_cycles),
        is_shift_manager: Boolean(row.is_shift_manager),
        is_overlap: row.service_type === "overlap",
        counts_toward_staffing: fillsASeat(row),
      };
    }
    return map;
  }, [overview?.employees, overview?.profile?.workplace?.day_cycles]);
  return { roster, roles, roleOptions, people };
}
