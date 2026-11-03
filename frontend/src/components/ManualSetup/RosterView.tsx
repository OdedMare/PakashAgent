"use client";

import { ChevronDown, ChevronsDownUp, ChevronsUpDown } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { GROUPINGS, groupRoster } from "./rosterGroups";
import type { RosterGrouping, RosterPerson } from "./rosterGroups";

const STORE = "pakash.setup.roster";

type Stored = { grouping: RosterGrouping; services: string[] };

/** The roster's toolbar and groups. It decides what is on screen; every
 *  card is still the form's own, rendered through `card`. */
export function RosterView({
  people,
  services,
  shiftNames,
  card,
  actions,
  onFilter,
}: {
  people: RosterPerson[];
  services: Record<string, string>;
  shiftNames: string[];
  card: (index: number, groupKey: string) => React.ReactNode;
  /** More buttons for the toolbar, such as folding every card. */
  actions?: React.ReactNode;
  /** The statuses being shown, so a soldier added now can take one of them. */
  onFilter?: (services: string[]) => void;
}) {
  // A habit, remembered per browser; the page renders without it. Setup
  // mounts only after the session check, so this never runs on the server.
  const [stored] = useState(() => readStored(services));
  const [grouping, setGrouping] = useState<RosterGrouping>(stored.grouping);
  const [shownServices, setShownServices] = useState<string[]>(stored.services);
  const [closed, setClosed] = useState<Set<string>>(new Set());

  useEffect(() => {
    try { window.localStorage.setItem(STORE, JSON.stringify({ grouping, services: shownServices })); } catch { /* storage unavailable */ }
    onFilter?.(shownServices);
  }, [grouping, shownServices, onFilter]);

  const groups = useMemo(
    () => groupRoster(people, grouping, services, shiftNames, (person) => !shownServices.length || shownServices.includes(person.service)),
    [people, grouping, services, shiftNames, shownServices],
  );
  const shownCount = new Set(groups.flatMap((group) => group.indices)).size;
  const counts = useMemo(() => {
    const result: Record<string, number> = {};
    people.forEach((person) => { result[person.service] = (result[person.service] ?? 0) + 1; });
    return result;
  }, [people]);

  const toggleService = (value: string) => setShownServices((current) =>
    current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  const toggleGroup = (key: string) => setClosed((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const allClosed = grouping !== "none" && groups.every((group) => closed.has(group.key));

  return (
    <>
      <div className="roster-toolbar" role="toolbar" aria-label="תצוגת כוח האדם">
        <label className="roster-grouping">
          <span>קיבוץ לפי</span>
          <select value={grouping} onChange={(event) => { setGrouping(event.target.value as RosterGrouping); setClosed(new Set()); }}>
            {Object.entries(GROUPINGS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
        <div className="roster-filter" role="group" aria-label="הצגה לפי מעמד">
          <button type="button" className={`chip-button${shownServices.length ? "" : " is-selected"}`} aria-pressed={!shownServices.length} onClick={() => setShownServices([])}>
            כולם · {people.length}
          </button>
          {Object.entries(services).map(([value, label]) => (
            <button key={value} type="button" className={`chip-button${shownServices.includes(value) ? " is-selected" : ""}`} aria-pressed={shownServices.includes(value)} onClick={() => toggleService(value)}>
              {label} · {counts[value] ?? 0}
            </button>
          ))}
        </div>
        {grouping !== "none" && groups.length > 1 ? (
          <button type="button" className="ghost-button roster-fold-all" onClick={() => setClosed(allClosed ? new Set() : new Set(groups.map((group) => group.key)))}>
            {allClosed ? <ChevronsUpDown size={15} /> : <ChevronsDownUp size={15} />} {allClosed ? "פתיחת כל הקבוצות" : "סגירת כל הקבוצות"}
          </button>
        ) : null}
        {actions}
      </div>

      {shownServices.length && shownCount < people.length ? (
        <p className="roster-filter-note" role="status">מוצגים {shownCount} מתוך {people.length}. השאר לא נמחקו — הם רק מוסתרים, ונשמרים כרגיל.</p>
      ) : null}

      {groups.map((group) => grouping === "none" ? (
        <div className="manual-list" key={group.key}>{group.indices.map((index) => card(index, group.key))}</div>
      ) : (
        <section className={`roster-group${closed.has(group.key) ? " is-closed" : ""}`} key={group.key}>
          <button type="button" className="roster-group-head" aria-expanded={!closed.has(group.key)} onClick={() => toggleGroup(group.key)}>
            <ChevronDown size={16} aria-hidden="true" />
            <strong>{group.label}</strong>
            <span>{group.indices.length}</span>
          </button>
          {closed.has(group.key) ? null : <div className="manual-list">{group.indices.map((index) => card(index, group.key))}</div>}
        </section>
      ))}
      {!groups.length ? <p className="roster-filter-note">אין אנשי צוות במעמד שנבחר.</p> : null}
    </>
  );
}

function readStored(services: Record<string, string>): Stored {
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORE) ?? "null") as Partial<Stored> | null;
    return {
      grouping: stored?.grouping && stored.grouping in GROUPINGS ? stored.grouping : "none",
      services: Array.isArray(stored?.services) ? stored.services.filter((value) => value in services) : [],
    };
  } catch {
    return { grouping: "none", services: [] };
  }
}
