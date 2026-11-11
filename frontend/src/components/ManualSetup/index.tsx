"use client";

import {
  ChevronDown,
  ChevronsDownUp,
  ChevronsUpDown,
  Clock3,
  Cpu,
  Plus,
  Repeat2,
  Save,
  Scale,
  ShieldCheck,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { Fragment, useCallback, useMemo, useState } from "react";

import { DateInput } from "@/components/DateInput";
import { MultiSelect } from "@/components/MultiSelect";
import { TimeInput } from "@/components/TimeInput";
import { HelpButton, useGuideSurface } from "@/components/Guide";
import { deleteShiftType, previewDeparture, updateProfile } from "@/services/api";
import { blockedDaysOf, withBlockedDays } from "@/lib/blockedDays";
import { cyclePattern, isDayCycle } from "@/lib/dayCycles";
import { LoadWeightSelect, STATUS_LABELS, ShiftLevelSelect, SoldierFields, daysCapOf, loadWeightOf, loadWeightValue, shiftCount, statusFields, statusOf } from "@/components/Management/SoldierFields";
import { ExitPatternFields } from "@/components/Management/ExitPatternFields";
import type { UnitPolicy } from "@/services/api";
import type { DayCycle, RotationClosureWindow, RotationPresenceRule, TeamView } from "@/types";

import { CompiledList, useCompiledSources } from "./CompiledSources";
import { DayCycleSetup } from "./DayCycleSetup";
import { ExitKinds } from "./ExitKinds";
import { Field } from "./fields";
import { CYCLES, firstGroupAnchor } from "./RotationSetup";
import { RosterView } from "./RosterView";
import type { RosterPerson } from "./rosterGroups";
import type { Cycle } from "./RotationSetup";
import { PersonStandard } from "./UnitStandard";
import { useCollapsed } from "./useCollapsed";
import { useQualification } from "./useQualification";
import { ImportUnit } from "./ImportUnit";
import { reserveFutureWarning } from "./reserveWarning";

const DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
const WEEKEND = ["שישי", "שבת"];
const SHIFT_TYPES = {
  regular: "רגילה",
  overlap: "חפיפה",
  on_call: "כוננות",
} as const;
const EXIT_PATTERNS = {
  none: "בלי יציאות",
  daily: "יומי — הביתה כל יום",
  personal: "סגירה אישית 1 ל־N",
  round: "סבב א / ב",
  triplet: "תלתון א / ב / ג",
  quad: "רבעון א / ב / ג / ד — שבת אחת מכל ארבע",
  quint: "חמישון א–ה — 1ל5, שבת אחת מכל חמש",
  hamshushim: "חמשושים",
  shushim: "שושים",
} as const;

type Row = Record<string, unknown>;

// A saved soldier or shift keeps the name it was loaded under in `SAVED`, so
// an edited name is sent as an explicit rename (`renamed_employees` /
// `renamed_shifts`) rather than read as one row gone and a new one added.
// A shift also keeps `REF`, the name the roster's shift picks and the
// rotation rules currently use for it; neither key is ever saved.
const SAVED = "_saved";
const REF = "_ref";

/** Full first-time or follow-up setup. Saving calls no model. */
export function ManualSetup({
  workspace,
  onDone,
  onCancel,
}: {
  workspace: TeamView;
  onDone: () => void | Promise<void>;
  onCancel?: () => void;
}) {
  const profile = workspace.profile ?? {};
  const initialWorkplace = record(profile.workplace);
  // The unit's name, horizon and operating days are not edited in setup;
  // what the profile holds is saved back unchanged.
  const unitName = text(initialWorkplace.name) || workspace.name;
  // Soldiers' notes as something to read on the board only: the build is
  // then not told about them at all.
  const [notesVisualOnly, setNotesVisualOnly] = useState(initialWorkplace.notes_visual_only === true);
  const planningHorizon = text(initialWorkplace.planning_horizon) || "שבוע";
  const operatingDays = strings(initialWorkplace.operating_days).length
    ? strings(initialWorkplace.operating_days)
    : DAYS;
  const [rotationMode] = useState<"round" | "triplet">(
    initialWorkplace.rotation_mode === "triplet" ? "triplet" : "round",
  );
  // Each cycle is anchored on the weekend its group א closes; an anchor that
  // was stored for another group is read as א's next turn in the same cycle.
  const [anchors] = useState<Record<Cycle, string>>(() => {
    const stored = (pattern: Cycle) => firstGroupAnchor(
      pattern,
      text(initialWorkplace[`${pattern}_first_closure_date`])
        || (rotationMode === pattern ? text(initialWorkplace.first_closure_date) : ""),
      text(initialWorkplace[`${pattern}_first_closure_group`])
        || (rotationMode === pattern ? text(initialWorkplace.first_closure_group) : ""),
    );
    return { round: stored("round"), triplet: stored("triplet"), quad: stored("quad"), quint: stored("quint") };
  });
  const [closureWindows, setClosureWindows] = useState<RotationClosureWindow[]>(
    profile.workplace?.rotation_closure_windows ?? [],
  );
  const [rotationPresence, setRotationPresence] = useState<RotationPresenceRule[]>(() =>
    (profile.workplace?.rotation_presence ?? []).map((row) => ({
      ...row,
      days: strings(row.days),
      shifts: strings(row.shifts),
      start_time: inputText(row.start_time),
      end_time: inputText(row.end_time),
      reason: inputText(row.reason),
    })),
  );
  const [dayCycles, setDayCycles] = useState<DayCycle[]>(() =>
    (profile.workplace?.day_cycles ?? []).map((cycle) => ({
      ...cycle,
      groups: strings(cycle.groups),
      offsets: { ...(cycle.offsets ?? {}) },
      group_times: { ...(cycle.group_times ?? {}) },
      time_changes: [...(cycle.time_changes ?? [])],
    })),
  );
  const [employees, setEmployees] = useState<Row[]>(() =>
    rows(profile.employees).map((person) => ({ ...person, [SAVED]: text(person.name) })),
  );
  const [shifts, setShifts] = useState<Row[]>(() =>
    rows(profile.shifts).map((shift) => ({
      ...shift,
      weekend_headcount: weekendHeadcount(shift),
      [SAVED]: text(shift.name),
      [REF]: text(shift.name),
    })),
  );
  const [enabledExitPatterns, setEnabledExitPatterns] = useState<string[]>(() => {
    const configured = strings(initialWorkplace.enabled_exit_patterns);
    const used = rows(profile.employees)
      .map((person) => exitPattern(person, rotationMode))
      .filter((pattern) => !isDayCycle(pattern));
    // A round was always on before the kinds were asked; keep it for a unit
    // that anchored one.
    const round = text(initialWorkplace.round_first_closure_date) || text(initialWorkplace.first_closure_date) ? ["round"] : [];
    return [...new Set([...configured, ...used, ...round])];
  });
  const [reserveOn, setReserveOn] = useState(() =>
    typeof initialWorkplace.reserve_enabled === "boolean"
      ? initialWorkplace.reserve_enabled
      : rows(profile.employees).some((person) => person.service_type === "reserve"),
  );
  const [reserveChecking, setReserveChecking] = useState(false);
  const [rotationAUnavailability, setRotationAUnavailability] = useState<Row[]>(
    rows(initialWorkplace.rotation_a_unavailability),
  );
  const [rules, setRules] = useState<Row[]>(rows(profile.rules));
  const audit = record(profile.audit_policy);
  const [maxWeeklyHours, setMaxWeeklyHours] = useState(number(audit.max_weekly_hours, 168));
  const [maxConsecutiveDays, setMaxConsecutiveDays] = useState(number(audit.max_consecutive_days, 11));
  const [minRestHours, setMinRestHours] = useState(number(audit.min_rest_hours, 8));
  // The rest of the unit standard is not edited here and is carried through
  // a save untouched; only the weekly shifts of סדיר and מילואים are.
  const [unitPolicy, setUnitPolicy] = useState<UnitPolicy>(() => record(profile.unit_policy) as UnitPolicy);
  // Saved shift types the manager deleted here. They are archived by their
  // own call after the save, which also cleans them out of the roster.
  const [removedShifts, setRemovedShifts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState(false);
  // Folded soldier cards, by name; a new, unnamed row is always open.
  const [foldedPeople, setFoldedPeople] = useState<Set<string>>(new Set());
  // Folded shift cards, by name, the same way.
  const [foldedShifts, setFoldedShifts] = useState<Set<string>>(new Set());
  const sections = useCollapsed(SECTION_IDS);
  const [rosterServices, setRosterServices] = useState<string[]>([]);
  const onRosterFilter = useCallback((value: string[]) => setRosterServices(value), []);

  const compiled = useCompiledSources();
  const shiftNames = useMemo(
    () => shifts.map((shift) => text(shift.name)).filter(Boolean),
    [shifts],
  );
  // What this save renames and deletes, worked out from the rows' saved names.
  const renamedEmployees = renames(employees);
  const renamedShifts = renames(shifts);
  const removedEmployees = useMemo(() => {
    const kept = new Set(employees.map((person) => text(person[SAVED])));
    return rows(profile.employees).map((row) => text(row.name)).filter((name) => name && !kept.has(name));
  }, [employees, profile.employees]);
  const toggleReserve = async (on: boolean) => {
    if (on) return setReserveOn(true);
    if (reserveChecking) return;
    const reservists = employees
      .filter((person) => person.service_type === "reserve" && !person.inactive_from && text(person[SAVED]))
      .map((person) => text(person[SAVED]));
    if (!reservists.length) return setReserveOn(false);
    setReserveChecking(true);
    setError("");
    try {
      const warning = reserveFutureWarning(await Promise.all(
        reservists.map((employee) => previewDeparture({ employee })),
      ));
      if (!warning || window.confirm(`${warning}\n\nלכבות את המילואים בכל זאת?`)) setReserveOn(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "לא ניתן לבדוק שיבוצים עתידיים של מילואימניקים");
    } finally {
      setReserveChecking(false);
    }
  };
  const usedExitPatterns = useMemo<Set<string>>(
    () => new Set(employees.filter(named).map((person) => exitPattern(person, rotationMode)).filter((pattern) => !isDayCycle(pattern))),
    [employees, rotationMode],
  );
  const usedDayCycles = useMemo(
    () => new Set(employees.map((person) => exitPattern(person, rotationMode)).filter(isDayCycle).map((pattern) => pattern.slice("cycle:".length))),
    [employees, rotationMode],
  );
  const groupsOf = (pattern: string) => rotationGroups(pattern, dayCycles);
  const rosterPeople = useMemo<RosterPerson[]>(() => employees.map((person) => {
    const pattern = exitPattern(person, rotationMode);
    const groups = rotationGroups(pattern, dayCycles);
    const group = groups.includes(text(person.rotation_group)) ? text(person.rotation_group) : groups[0] ?? "";
    return {
      service: statusOf(text(person.service_type), text(person.rank_group)),
      counts: person.counts_toward_staffing !== false,
      shifts: strings(person.eligible_shifts),
      exitKey: `${pattern}|${group}`,
      exitLabel: [patternLabel(pattern, dayCycles), group && `קבוצה ${group}`].filter(Boolean).join(" · "),
      searchText: text(person.name) ? [
        text(person.name),
        text(person.role),
        text(person.competence),
        STATUS_LABELS[statusOf(text(person.service_type), text(person.rank_group))] ?? "",
        patternLabel(pattern, dayCycles),
        group && `קבוצה ${group}`,
        ...strings(person.eligible_shifts),
        ...rows(person.qualifications).map((row) => text(row.role)),
        person.is_shift_manager ? "מפקד משמרת" : "",
        person.can_train ? "חופף" : "",
        text(person.notes),
      ].join(" ") : "",
    };
  }), [employees, rotationMode, dayCycles]);
  const namedShifts = shifts.map((shift) => text(shift.name)).filter(Boolean);
  const allShiftsFolded = namedShifts.length > 0 && namedShifts.every((key) => foldedShifts.has(key));
  const toggleShiftFold = (key: string) => setFoldedShifts((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const section = (id: SectionId) => ({ open: !sections.isCollapsed(id), onToggle: () => sections.toggle(id) });
  const foldKey = (person: Row) => text(person.name);
  const namedKeys = employees.map(foldKey).filter(Boolean);
  const allFolded = namedKeys.length > 0 && namedKeys.every((key) => foldedPeople.has(key));
  const toggleFold = (key: string) => setFoldedPeople((current) => {
    const next = new Set(current);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  // A closure runs to the end of Sunday's first shift by the clock — the
  // handover the server's default closure ends on.
  const handoverEnd = useMemo(() => {
    const timed = shifts.filter((shift) => text(shift.start_time) && text(shift.end_time));
    timed.sort((a, b) => text(a.start_time).localeCompare(text(b.start_time)));
    return timed.length ? text(timed[0].end_time) : "";
  }, [shifts]);
  const availableExitPatterns = useMemo(
    () => new Set([...enabledExitPatterns, ...usedExitPatterns]),
    [enabledExitPatterns, usedExitPatterns],
  );
  // A new soldier starts on the first kind the unit chose, or on none.
  const defaultPattern = Object.keys(EXIT_PATTERNS).find((pattern) => availableExitPatterns.has(pattern))
    ?? (dayCycles[0] ? cyclePattern(dayCycles[0]) : "none");
  // The weekend groups run one cycle: the count of groups chosen on screen,
  // else the first one enabled (a soldier still on another stays on it).
  const enabledCycles = (Object.keys(CYCLES) as Cycle[]).filter((pattern) => availableExitPatterns.has(pattern));
  const [chosenCycle, setChosenCycle] = useState<Cycle | undefined>(undefined);
  const weekendCycle = chosenCycle && enabledCycles.includes(chosenCycle) ? chosenCycle : enabledCycles[0];
  const isRegular = (pattern: string) => (row: RotationClosureWindow) => row.pattern === pattern && row.group === "א" && !row.starts_on && !row.ends_on;
  // The closure stated once: group א's undated window row, which the server
  // applies to every group in turn. No row is its default, Thursday to the
  // Sunday handover.
  const defaultClosure: ClosureBounds = { start_day: -2, start_time: "00:00", end_day: 1, end_time: handoverEnd || "00:00" };
  const closureOf = (pattern: string | undefined): ClosureBounds => {
    const row = pattern ? closureWindows.findLast(isRegular(pattern)) : undefined;
    return row ? { start_day: row.start_day, start_time: row.start_time, end_day: row.end_day, end_time: row.end_time } : defaultClosure;
  };
  const setClosure = (patch: Partial<ClosureBounds>) => {
    if (!weekendCycle) return;
    const next = { ...closureOf(weekendCycle), ...patch };
    setClosureWindows((current) => [...current.filter((row) => !isRegular(weekendCycle)(row)), { pattern: weekendCycle, group: "א", starts_on: "", ends_on: "", ...next } as RotationClosureWindow]);
  };
  const chooseCycle = (next: Cycle) => {
    const hours = closureOf(weekendCycle);
    setChosenCycle(next);
    setEnabledExitPatterns((current) => [...current.filter((pattern) => !Object.keys(CYCLES).includes(pattern) || usedExitPatterns.has(pattern)), next]);
    // The closure hours follow the count; a cycle somebody is still on keeps its own.
    setClosureWindows((current) => [
      ...current.filter((row) => !isRegular(next)(row) && !(weekendCycle && !usedExitPatterns.has(weekendCycle) && isRegular(weekendCycle)(row))),
      { pattern: next, group: "א", starts_on: "", ends_on: "", ...hours } as RotationClosureWindow,
    ]);
  };
  // The weekend a shift's weekend headcount applies to is the groups'
  // closure — the days one group is home — so it follows the hours above
  // rather than a fixed Friday and Saturday.
  const closure: ClosureBounds = closureOf(weekendCycle ?? "round");
  // No date is asked any more: a cycle with no stored anchor starts with
  // group א closing the coming weekend.
  const [defaultAnchor] = useState(() => comingSaturday());
  const anchorOf = (pattern: Cycle) => anchors[pattern] || (availableExitPatterns.has(pattern) ? defaultAnchor : "");
  const ready = Boolean(unitName.trim() && employees.some(named) && shifts.some(named));
  // Every anchor is saved as group א's weekend; the server derives the other
  // groups' turns from it. The old pair stays readable by older deployments
  // while the two cycles keep independent anchors.
  const rotation = {
    rotation_mode: rotationMode,
    first_closure_group: "א",
    first_closure_date: anchorOf(rotationMode),
    round_first_closure_group: "א",
    round_first_closure_date: anchorOf("round"),
    triplet_first_closure_group: "א",
    triplet_first_closure_date: anchorOf("triplet"),
    quad_first_closure_group: "א",
    quad_first_closure_date: anchorOf("quad"),
    quint_first_closure_group: "א",
    quint_first_closure_date: anchorOf("quint"),
    rotation_closure_windows: closureWindows,
  };
  // Coloured by the server, from the dates typed here and the shifts worked.
  // Asked by the saved name: until the save, a renamed soldier's worked
  // shifts are still stored under it.
  const historyName = (person: Row) => text(person[SAVED]) || text(person.name);
  const qualifications = useQualification(employees.map((person) => ({
    name: historyName(person),
    qualifications: (Array.isArray(person.qualifications) ? person.qualifications as Row[] : [])
      .map((row) => ({ role: text(row.role), last_active: text(row.last_active) })),
  })));
  const qualificationClass = (person: Row) => {
    const standing = qualifications[historyName(person)];
    return standing ? ` qualification-${standing.status}` : "";
  };

  useGuideSurface("setup");

  /** A shift's name typed anew. What names the shift elsewhere on the form
   *  follows, but only to a name no other shift has: two shifts briefly
   *  sharing one would make their references indistinguishable. */
  const renameShift = (index: number, value: string) => {
    const from = text(shifts[index]?.[REF]);
    const to = value.trim();
    const free = Boolean(to) && !shifts.some((shift, row) => row !== index && text(shift.name) === to);
    setShifts((current) => current.map((shift, row) => row === index
      ? { ...shift, name: value, ...(free ? { [REF]: to } : {}) }
      : shift));
    if (!free || !from || from === to) return;
    const swap = (names: unknown) => strings(names).map((name) => name === from ? to : name);
    setEmployees((current) => current.map((person) => ({ ...person, eligible_shifts: swap(person.eligible_shifts) })));
    setRotationPresence((current) => current.map((rule) => ({ ...rule, shifts: swap(rule.shifts) })));
    setRotationAUnavailability((current) => current.map((rule) => ({ ...rule, shifts: swap(rule.shifts) })));
  };

  const removeEmployee = (index: number) => {
    const saved = text(employees[index]?.[SAVED]);
    if (saved && !window.confirm(
      `למחוק את ${saved}? המחיקה מיועדת לחייל/ת שנוסף/ה בטעות: השיבוצים שלו/ה בטיוטות, האילוצים והבקשות יימחקו בשמירה. `
      + "מי שמשובץ/ת בסידור מפורסם לא יימחק/ה — במקרה כזה אפשר לתקן את השם, או להוציא מהסגל במסך הצוות.",
    )) return;
    setEmployees((current) => current.filter((_, row) => row !== index));
  };

  const save = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError("");
    try {
      await updateProfile({
        workplace: {
          ...initialWorkplace,
          name: unitName.trim(),
          planning_horizon: planningHorizon.trim() || "שבוע",
          operating_days: operatingDays,
          ...rotation,
          rotation_presence: rotationPresence,
          day_cycles: dayCycles,
          // The free-text "general exits" field is gone from the form; an
          // old one is cleared so text nobody can see no longer steers builds.
          general_exit_schedule: "",
          notes_visual_only: notesVisualOnly,
          enabled_exit_patterns: [...availableExitPatterns],
          reserve_enabled: reserveOn,
          rotation_a_unavailability: rotationAUnavailability.map((rule) => ({
            days: strings(rule.days),
            shifts: strings(rule.shifts),
            start_time: text(rule.start_time),
            end_time: text(rule.end_time),
            reason: text(rule.reason),
          })),
        },
        employees: employees.filter(named).map(({ [SAVED]: _saved, ...person }) => ({
          ...person,
          name: text(person.name),
          role: text(person.role),
          exit_pattern: exitPattern(person, rotationMode),
          rotation_group: groupsOf(exitPattern(person, rotationMode)).includes(text(person.rotation_group))
            ? text(person.rotation_group)
            : groupsOf(exitPattern(person, rotationMode))[0] ?? "",
          service_type: text(person.service_type) || "standard",
          rank_group: text(person.service_type) && text(person.service_type) !== "standard" ? "" : text(person.rank_group),
          counts_toward_staffing: person.counts_toward_staffing !== false,
          eligible_shifts: strings(person.eligible_shifts),
          is_shift_manager: Boolean(person.is_shift_manager),
          can_train: Boolean(person.can_train),
          notes: text(person.notes),
          competence: text(person.competence),
          reserve_days_per_week: daysCapOf(statusOf(person.service_type, person.rank_group), person.reserve_days_per_week),
          reserve_min_days: typeof person.reserve_min_days === "number" ? person.reserve_min_days : null,
          reserve_consecutive: person.reserve_consecutive === true,
          reserve_call: text(person.reserve_call),
          ...(Array.isArray(person.qualifications)
            ? { qualifications: rows(person.qualifications).filter((row) => text(row.role)) }
            : {}),
        })),
        // A deleted saved shift is still sent here: names are identity keys
        // the profile save refuses to drop, so it leaves through
        // `deleteShiftType` below.
        shifts: [...shifts, ...rows(profile.shifts).filter((row) => removedShifts.includes(text(row.name)))]
          .filter(named).map(({ weekend_headcount: weekend, [SAVED]: _saved, [REF]: _ref, ...shift }) => ({
          ...shift,
          name: text(shift.name),
          purpose: text(shift.purpose),
          shift_type: text(shift.shift_type) || "regular",
          start_time: text(shift.start_time),
          end_time: text(shift.end_time),
          starts_on: text(shift.starts_on),
          ends_on: text(shift.ends_on),
          days: strings(shift.days),
          headcount: number(shift.headcount, headcount(shift)),
          staffing: staffingFor(shift, weekend, closureDays(shift, closure)),
          requires_shift_manager: Boolean(shift.requires_shift_manager),
          // Role limits are no longer set in setup; a save clears any stored.
          allowed_roles: [],
          min_competence: text(shift.min_competence),
          load_weight: loadWeightOf(loadWeightValue(shift.load_weight)),
        })),
        rules: rules
          .filter((rule) => text(rule.text))
          .map((rule) => ({
            text: text(rule.text),
            priority: rule.priority === "soft" ? "soft" : "hard",
          })),
        audit_policy: {
          max_weekly_hours: maxWeeklyHours,
          max_consecutive_days: maxConsecutiveDays,
          min_rest_hours: minRestHours,
        },
        unit_policy: unitPolicy,
        summary: "יחידה צבאית עם מבנה יציאות אישי לכל חייל/ת",
        renamed_employees: renamedEmployees,
        renamed_shifts: renamedShifts,
        removed_employees: removedEmployees,
        expected_revision: workspace.profile_revision,
      });
      for (const name of removedShifts) {
        await deleteShiftType(name);
      }
      setRemovedShifts([]);
      await onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "לא ניתן לשמור את ההגדרות");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="manual-setup">
      <header className="manual-setup-header">
        <div>
          <span className="manual-kicker">הגדרה ידנית · ללא שימוש במודל</span>
          <h1>בונים את שיטת השיבוץ של היחידה</h1>
          <p>כל מה שמוגדר כאן נכנס ישירות לפרופיל שממנו נבנים הסידורים.</p>
        </div>
        <div className="manual-header-actions">
          <HelpButton />
          <button type="button" className="ghost-button" onClick={sections.toggleAll} aria-pressed={sections.allCollapsed}>
            {sections.allCollapsed ? <ChevronsUpDown size={16} /> : <ChevronsDownUp size={16} />} {sections.allCollapsed ? "פתיחת הכל" : "כיווץ הכל"}
          </button>
          <button type="button" className="ghost-button" disabled={busy} onClick={() => setImporting(true)}>ייבוא הגדרה מאקסל</button>
          {onCancel ? (
            <button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>
              <X size={16} /> ביטול
            </button>
          ) : null}
          <button type="button" className="primary-button" onClick={() => void save()} disabled={!ready || busy}>
            <Save size={16} /> {busy ? "שומר…" : "שמירת ההגדרות"}
          </button>
        </div>
      </header>

      {error ? <div className="manual-error" role="alert">{error}</div> : null}

      <main id="main-content" className="manual-sections">
        {importing && <ImportUnit teamId={workspace.id} onClose={() => setImporting(false)} onApply={(people, importedShifts) => {
          setEmployees((current) => {
            const names = new Set(current.map((p) => text(p.name)));
            return [...current, ...people.filter((p) => {
              const name = text(p.name);
              if (names.has(name)) return false;
              names.add(name);
              return true;
            })];
          });
          setShifts((current) => {
            const merged = [...current];
            for (const shift of importedShifts) {
              const index = merged.findIndex((s) => text(s.name) === text(shift.name));
              if (index < 0) merged.push(shift);
              else merged[index] = { ...merged[index], ...shift };
            }
            return merged;
          });
          setImporting(false);
        }} />}
        <SetupSection {...section("rotations")} summary={[...Object.entries(EXIT_PATTERNS).filter(([value]) => availableExitPatterns.has(value)).map(([, label]) => label.split(" — ")[0]), ...dayCycles.map((cycle) => cycle.name || `${cycle.base_days}/${cycle.home_days}`)].join(" · ") || "לא נבחרו יציאות"} tour="setup-rotations" icon={<Repeat2 />} title="יציאות" hint="קודם בוחרים אילו סוגי יציאות יש ביחידה, ואז עונים רק על השאלות שלהם. את המבנה של כל חייל/ת בוחרים בכוח אדם. ההגדרות חלות על השיבוץ הבא — סידור קיים לא נבנה מחדש.">
          <ExitKinds
            enabled={availableExitPatterns}
            used={usedExitPatterns}
            dayCycles={dayCycles}
            dayCyclesUsed={usedDayCycles}
            reserveOn={reserveOn}
            reserveBusy={reserveChecking}
            cycle={weekendCycle}
            window={closureOf(weekendCycle)}
            handoverEnd={handoverEnd}
            onEnabled={(next) => setEnabledExitPatterns([...next])}
            onDayCycles={setDayCycles}
            onReserve={(on) => void toggleReserve(on)}
            onCycle={chooseCycle}
            onWindow={setClosure}
          />

          {dayCycles.length ? <DayCycleSetup cycles={dayCycles} onChange={setDayCycles} used={usedDayCycles} /> : null}
          {reserveOn ? <p className="rotation-derived-note">מילואים: בכוח אדם בוחרים מעמד ״מילואים״ לכל מילואימניק/ית, ומסמנים באילו ימים הוא/היא חסום/ה, ואפשר גם מינימום ימים והאם ברצף. את הימים עצמם בוחר הסידור.</p> : null}
          {availableExitPatterns.has("personal") ? <p className="rotation-derived-note">סגירה אישית: בכוח אדם בוחרים ״סגירה אישית 1 ל־N״ ומגדירים כל כמה שבתות ומתי הסגירה הראשונה.</p> : null}
          {availableExitPatterns.has("daily") ? <p className="rotation-derived-note">יומי: בכוח אדם בוחרים ״יומי״ ומגדירים לכל אחד/ת ימי הגעה ושעות.</p> : null}

          {/* The older fixed א/ב presence schedule: shown only to a unit that
              still has one, so a new manager meets one way to say "absent". */}
          {rotationAUnavailability.length ? (
            <>
              <div className="rotation-pair" aria-label="הקשר בין סבב א לסבב ב">
                <div><strong>סבב א׳</strong><span>אתם מגדירים את זמני אי־הזמינות.</span></div>
                <Repeat2 aria-hidden="true" />
                <div className="is-derived"><strong>סבב ב׳</strong><span>מחושב בשרת ואינו ניתן לעריכה נפרדת.</span></div>
              </div>

              <div className="manual-list">
                {rotationAUnavailability.map((rule, index) => (
                  <article className="manual-row rotation-rule" key={`rotation-a-${index}`}>
                    <div className="rotation-rule-head">
                      <div><strong>תקופת אי־זמינות {index + 1}</strong><span>השארת ימים או משמרות ללא בחירה תחיל את הכלל על כולם.</span></div>
                      <button type="button" className="icon-button subtle" aria-label={`מחיקת תקופת אי־זמינות ${index + 1}`} onClick={() => setRotationAUnavailability((current) => current.filter((_, row) => row !== index))}><Trash2 size={15} /></button>
                    </div>
                    <MultiSelect label="ימים שבהם סבב א׳ אינו זמין" values={DAYS} selected={strings(rule.days)} onChange={(value) => edit(setRotationAUnavailability, index, "days", value)} placeholder="כל הימים" />
                    {shiftNames.length ? <MultiSelect label="משמרות" values={shiftNames} selected={strings(rule.shifts)} onChange={(value) => edit(setRotationAUnavailability, index, "shifts", value)} placeholder="כל המשמרות" /> : null}
                    <div className="manual-grid three">
                      <Field label="משעה (רשות)"><TimeInput value={inputText(rule.start_time)} onChange={(time) => edit(setRotationAUnavailability, index, "start_time", time)} /></Field>
                      <Field label="עד שעה (רשות)"><TimeInput value={inputText(rule.end_time)} onChange={(time) => edit(setRotationAUnavailability, index, "end_time", time)} /></Field>
                      <Field label="סיבה / תיאור"><input value={inputText(rule.reason)} onChange={(event) => edit(setRotationAUnavailability, index, "reason", event.target.value)} placeholder="לדוגמה: יציאה קבועה" /></Field>
                    </div>
                  </article>
                ))}
              </div>
              <button type="button" className="ghost-button" onClick={() => setRotationAUnavailability((current) => [...current, { days: [], shifts: [], start_time: "", end_time: "", reason: "" }])}><Plus size={16} /> הוספת זמן שבו סבב א׳ אינו זמין</button>
              <p className="rotation-derived-note">הגדרה ישנה: סבב ב׳ זמין בדיוק בזמנים שסבב א׳ אינו זמין. מחיקת כל התקופות תחזיר את הסבב לחישוב לפי העוגן והשעות שלמעלה.</p>
            </>
          ) : null}
        </SetupSection>

        <SetupSection {...section("people")} summary={`${employees.filter(named).length} אנשי צוות`} tour="setup-people" icon={<Users />} title="כוח אדם" hint="לכל אדם מגדירים יציאות משלו, יכולות, מעמד והערות.">
          <label className="manual-check">
            <input type="checkbox" checked={notesVisualOnly} onChange={(e) => setNotesVisualOnly(e.target.checked)} />
            <span>הערות לחייל/ת לתצוגה בלבד — מוצגות בלוח כסימן קריאה (!) ולא נלקחות בחשבון בשיבוץ</span>
          </label>
          <RosterView
            people={rosterPeople}
            services={STATUS_LABELS}
            shiftNames={shiftNames}
            onFilter={onRosterFilter}
            card={(index, groupKey) => {
              const person = employees[index];
              const key = foldKey(person);
              if (key && foldedPeople.has(key)) {
                return (
                  <article className={`manual-row is-folded${qualificationClass(person)}`} key={`employee-${index}-${groupKey}`}>
                    <button type="button" className="manual-row-summary" aria-expanded={false} onClick={() => toggleFold(key)}>
                      <ChevronDown size={15} aria-hidden="true" />
                      <strong>{key}</strong>
                      <span>{[text(person.role), rosterPeople[index].exitLabel, STATUS_LABELS[rosterPeople[index].service]].filter(Boolean).join(" · ")}</span>
                    </button>
                  </article>
                );
              }
              return (
              <article className={`manual-row${qualificationClass(person)}`} key={`employee-${index}-${groupKey}`}>
                {key ? (
                  <button type="button" className="manual-row-summary is-open" aria-expanded onClick={() => toggleFold(key)}>
                    <ChevronDown size={15} aria-hidden="true" /><strong>{key}</strong><span>סגירת הכרטיס</span>
                  </button>
                ) : null}
                <div className="manual-grid employee-grid">
                  <Field label="שם *"><input value={inputText(person.name)} onChange={(e) => edit(setEmployees, index, "name", e.target.value)} /><RenameNote saved={text(person[SAVED])} name={text(person.name)} /></Field>
                  <Field label="תפקיד"><input value={inputText(person.role)} onChange={(e) => edit(setEmployees, index, "role", e.target.value)} /></Field>
                  <Field label="מבנה יציאות">
                    <select value={exitPattern(person, rotationMode)} onChange={(e) => {
                      edit(setEmployees, index, "exit_pattern", e.target.value);
                      edit(setEmployees, index, "rotation_group", groupsOf(e.target.value)[0] ?? "");
                    }}>{Object.entries(EXIT_PATTERNS).filter(([value]) => availableExitPatterns.has(value) || value === "none").map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      {dayCycles.map((cycle) => <option key={cycle.id} value={cyclePattern(cycle)}>{cycle.name || "מחזור"} · {cycle.groups.join(" / ")}</option>)}
                    </select>
                  </Field>
                  {groupsOf(exitPattern(person, rotationMode)).length ? <Field label="קבוצה"><select value={text(person.rotation_group) || groupsOf(exitPattern(person, rotationMode))[0]} onChange={(e) => edit(setEmployees, index, "rotation_group", e.target.value)}>{groupsOf(exitPattern(person, rotationMode)).map((group) => <option key={group}>{group}</option>)}</select></Field> : null}
                  <Field label="מעמד">
                    <select value={rosterPeople[index].service} onChange={(e) => {
                      const fields = statusFields(e.target.value);
                      edit(setEmployees, index, "service_type", fields.service_type);
                      edit(setEmployees, index, "rank_group", fields.rank_group);
                      edit(setEmployees, index, "counts_toward_staffing", e.target.value !== "overlap");
                    }}>{Object.entries(STATUS_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
                  </Field>
                </div>
                <div className="manual-row-foot">
                  <label className="manual-check" title="כבוי/ה — לא נלקח/ת בחשבון בשיבוץ כלל"><input type="checkbox" checked={person.on_duty !== false} onChange={(e) => edit(setEmployees, index, "on_duty", e.target.checked)} /><span>דולק/ת בשיבוץ</span></label>
                  <label className="manual-check"><input type="checkbox" checked={person.counts_toward_staffing !== false} onChange={(e) => edit(setEmployees, index, "counts_toward_staffing", e.target.checked)} /><span>נספר/ת בתקן</span></label>
                  <label className="manual-check"><input type="checkbox" checked={Boolean(person.is_shift_manager)} onChange={(e) => edit(setEmployees, index, "is_shift_manager", e.target.checked)} /><span>מוסמך/ת כמפקד/ת משמרת</span></label>
                  <label className="manual-check"><input type="checkbox" checked={Boolean(person.can_train)} onChange={(e) => edit(setEmployees, index, "can_train", e.target.checked)} /><span>מוסמך/ת לחפוף</span></label>
                  {shiftNames.length ? <MultiSelect className="manual-shift-picks" label="משמרות מותרות" values={shiftNames} selected={strings(person.eligible_shifts)} onChange={(value) => edit(setEmployees, index, "eligible_shifts", value)} placeholder="לא נבחרו משמרות" /> : null}
                  <button type="button" className="icon-button subtle" aria-label={`מחיקת ${text(person.name) || "איש צוות"}`} title="מחיקה — לחייל/ת שנוסף/ה בטעות" onClick={() => removeEmployee(index)}><Trash2 size={15} /></button>
                </div>
                <ExitPatternFields pattern={exitPattern(person, rotationMode)} person={person} onChange={(field, value) => edit(setEmployees, index, field, value)} />
                <SoldierFields
                  serviceType={rosterPeople[index].service}
                  competence={text(person.competence)}
                  reserveDays={typeof person.reserve_days_per_week === "number" ? person.reserve_days_per_week : null}
                  reserveMinDays={typeof person.reserve_min_days === "number" ? person.reserve_min_days : null}
                  reserveConsecutive={person.reserve_consecutive === true}
                  reserveCall={text(person.reserve_call)}
                  blockedDays={blockedDaysOf(person.recurring_constraints)}
                  onBlockedDays={(days) => edit(setEmployees, index, "recurring_constraints", withBlockedDays(person.recurring_constraints, days))}
                  minShifts={typeof person.min_weekly_shifts === "number" ? person.min_weekly_shifts : null}
                  maxShifts={typeof person.max_weekly_shifts === "number" ? person.max_weekly_shifts : null}
                  onChange={(field, value) => edit(setEmployees, index, field, value)}
                />
                <PersonStandard person={person} standing={qualifications[historyName(person)]} onChange={(key, value) => edit(setEmployees, index, key, value)} />
                <Field label="הערות לחייל/ת"><textarea value={inputText(person.notes)} onChange={(e) => edit(setEmployees, index, "notes", e.target.value)} rows={2} placeholder={notesVisualOnly ? "מוצג בלוח בלבד, לא משפיע על השיבוץ" : "מידע קבוע שכדאי לקחת בחשבון בשיבוץ"} /></Field>
                <CompiledList title="מה הקוד הבין" sources={compiled.forPerson(text(person[SAVED]))} />
              </article>
              );
            }}
            actions={namedKeys.length ? (
              <button type="button" className="ghost-button roster-fold-all" onClick={() => setFoldedPeople(allFolded ? new Set() : new Set(namedKeys))}>
                {allFolded ? <ChevronsUpDown size={15} /> : <ChevronsDownUp size={15} />} {allFolded ? "פתיחת כל הכרטיסים" : "כיווץ כל הכרטיסים"}
              </button>
            ) : null}
          />
          <button type="button" className="ghost-button" onClick={() => {
            // Added while one status is shown, the soldier takes it, so the
            // new row does not vanish behind the filter.
            const service = rosterServices.length === 1 ? rosterServices[0] : "standard";
            setEmployees((current) => [...current, { name: "", role: "", exit_pattern: defaultPattern, rotation_group: rotationGroups(defaultPattern, dayCycles)[0] ?? "", ...statusFields(service), counts_toward_staffing: service !== "overlap", eligible_shifts: [], is_shift_manager: false, can_train: false, notes: "" }]);
          }}><Plus size={16} /> {rosterServices.length === 1 ? `הוספת ${STATUS_LABELS[rosterServices[0]]}` : "הוספת איש/אשת צוות"}</button>
        </SetupSection>

        <SetupSection {...section("shifts")} summary={namedShifts.join(" · ") || "אין משמרות"} tour="setup-shifts" icon={<Clock3 />} title="סוגי משמרות ותקינה" hint="תאריכי תוקף ריקים = משמרת קבועה; מילוי שניהם יוצר משמרת זמנית שנעלמת מהלוח מחוץ לטווח. משמרת חפיפה מוצגת בנפרד; מי שלא נספר בתקן לא ממלא את המכסה. תקן סופ״ש חל כשאחד הסבבים בבית — לפי ימים בבסיס/בבית בסעיף הסבבים.">
          <div className="manual-list">
            {shifts.map((shift, index) => {
              const key = text(shift.name);
              if (key && foldedShifts.has(key)) {
                return (
                  <article className="manual-row is-folded" key={`shift-${index}`}>
                    <button type="button" className="manual-row-summary" aria-expanded={false} onClick={() => toggleShiftFold(key)}>
                      <ChevronDown size={15} aria-hidden="true" />
                      <strong>{key}</strong>
                      <span>{[text(shift.start_time) && text(shift.end_time) ? `${text(shift.start_time)}–${text(shift.end_time)}` : "", `תקן ${number(shift.headcount, headcount(shift))}`, text(shift.purpose)].filter(Boolean).join(" · ")}</span>
                    </button>
                  </article>
                );
              }
              return (
              <article className="manual-row" key={`shift-${index}`}>
                {key ? (
                  <button type="button" className="manual-row-summary is-open" aria-expanded onClick={() => toggleShiftFold(key)}>
                    <ChevronDown size={15} aria-hidden="true" /><strong>{key}</strong><span>סגירת הכרטיס</span>
                  </button>
                ) : null}
                <div className="manual-grid shift-grid">
                  <Field label="שם המשמרת *"><input value={inputText(shift.name)} onChange={(e) => renameShift(index, e.target.value)} /><RenameNote saved={text(shift[SAVED])} name={text(shift.name)} /></Field>
                  <Field label="סוג"><select value={text(shift.shift_type) || (shift.is_on_call ? "on_call" : "regular")} onChange={(e) => edit(setShifts, index, "shift_type", e.target.value)}>{Object.entries(SHIFT_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
                  <Field label="התחלה"><TimeInput value={text(shift.start_time)} onChange={(time) => edit(setShifts, index, "start_time", time)} /></Field>
                  <Field label="סיום"><TimeInput value={text(shift.end_time)} onChange={(time) => edit(setShifts, index, "end_time", time)} /></Field>
                  <Field label="פעילה מתאריך (לזמנית)"><DateInput value={text(shift.starts_on)} max={text(shift.ends_on) || undefined} required={Boolean(text(shift.ends_on))} onChange={(date) => edit(setShifts, index, "starts_on", date)} /></Field>
                  <Field label="פעילה עד תאריך (לזמנית)"><DateInput value={text(shift.ends_on)} min={text(shift.starts_on) || undefined} required={Boolean(text(shift.starts_on))} onChange={(date) => edit(setShifts, index, "ends_on", date)} /></Field>
                  <Field label="תקן א׳–ה׳"><input type="number" min={0} max={100} value={number(shift.headcount, headcount(shift))} onChange={(e) => edit(setShifts, index, "headcount", seats(e.target.value))} /></Field>
                  <Field label="תקן סופ״ש"><input title={`חל על: ${closureDays(shift, closure).join(", ")}`} type="number" min={0} max={100} value={shift.weekend_headcount === "" || shift.weekend_headcount === undefined ? "" : String(shift.weekend_headcount)} placeholder="כמו באמצע השבוע" onChange={(e) => edit(setShifts, index, "weekend_headcount", e.target.value === "" ? "" : seats(e.target.value))} /></Field>
                  <Field label="ייעוד"><input value={inputText(shift.purpose)} onChange={(e) => edit(setShifts, index, "purpose", e.target.value)} placeholder="סיור, חמ״ל, חפיפה…" /></Field>
                  <Field label="משמרת חזקה (רמה מקצועית)"><ShiftLevelSelect value={text(shift.min_competence)} onChange={(level) => edit(setShifts, index, "min_competence", level)} /></Field>
                  <Field label="משקל עומס"><LoadWeightSelect value={loadWeightValue(shift.load_weight)} onChange={(weight) => edit(setShifts, index, "load_weight", loadWeightOf(weight))} /></Field>
                </div>
                {text(shift.starts_on) && text(shift.ends_on) ? <p className="manual-zero-note">משמרת זמנית: תופיע בסידור רק בטווח התאריכים שנבחר.</p> : null}
                {offNote(number(shift.headcount, headcount(shift)), shift.weekend_headcount) ? <p className="manual-zero-note">{offNote(number(shift.headcount, headcount(shift)), shift.weekend_headcount)}</p> : null}
                <label className="manual-check"><input type="checkbox" checked={Boolean(shift.requires_shift_manager)} onChange={(e) => edit(setShifts, index, "requires_shift_manager", e.target.checked)} /><span>נדרש/ת מפקד/ת משמרת מוסמך/ת</span></label>
                <MultiSelect className="manual-day-picks" label="ימים" values={DAYS} selected={strings(shift.days)} onChange={(value) => edit(setShifts, index, "days", value)} placeholder="לא נבחרו ימים" />
                <button type="button" className="icon-button subtle manual-delete" aria-label="מחיקת סוג משמרת" title={text(shift[SAVED]) ? "סידורים קיימים נשארים כפי שהם; הבנייה הבאה לא תכלול את המשמרת" : undefined} onClick={() => {
                  const name = text(shift[SAVED]);
                  if (name) {
                    if (!window.confirm(`למחוק את סוג המשמרת ${name}? סידורים שכבר נבנו נשארים כפי שהם, והמחיקה תיכנס לתוקף בשמירה.`)) return;
                    setRemovedShifts((current) => [...current, name]);
                  }
                  setShifts((current) => current.filter((_, row) => row !== index));
                }}><Trash2 size={15} /></button>
              </article>
              );
            })}
          </div>
          {namedShifts.length ? (
            <button type="button" className="ghost-button roster-fold-all" onClick={() => setFoldedShifts(allShiftsFolded ? new Set() : new Set(namedShifts))}>
              {allShiftsFolded ? <ChevronsUpDown size={15} /> : <ChevronsDownUp size={15} />} {allShiftsFolded ? "פתיחת כל המשמרות" : "כיווץ כל המשמרות"}
            </button>
          ) : null}
          <button type="button" className="ghost-button" onClick={() => setShifts((current) => [...current, { name: "", shift_type: "regular", start_time: "", end_time: "", headcount: 1, purpose: "", days: DAYS }])}><Plus size={16} /> הוספת סוג משמרת</button>
        </SetupSection>

        <SetupSection {...section("rules")} summary={`${rules.filter((rule) => text(rule.text)).length} כללים`} tour="setup-rules" icon={<ShieldCheck />} title="כללים קבועים" hint="כלל קשיח הוא חובה; כלל רך הוא העדפה שהמערכת מנסה לכבד.">
          <div className="manual-list compact">
            {rules.map((rule, index) => (
              <div className="manual-rule" key={index}>
                <input aria-label="ניסוח הכלל" value={inputText(rule.text)} onChange={(e) => edit(setRules, index, "text", e.target.value)} placeholder="לדוגמה: אין לשבץ חפיפה מיד אחרי לילה" />
                <select aria-label="עוצמת הכלל" value={rule.priority === "soft" ? "soft" : "hard"} onChange={(e) => edit(setRules, index, "priority", e.target.value)}><option value="hard">קשיח</option><option value="soft">העדפה</option></select>
                <button type="button" className="icon-button subtle" aria-label="מחיקת כלל" onClick={() => setRules((current) => current.filter((_, row) => row !== index))}><Trash2 size={15} /></button>
                <CompiledList bare sources={compiled.forRule(text(rule.text))} />
              </div>
            ))}
          </div>
          <button type="button" className="ghost-button" onClick={() => setRules((current) => [...current, { text: "", priority: "hard" }])}><Plus size={16} /> הוספת כלל קבוע</button>
        </SetupSection>

        <SetupSection {...section("limits")} summary={`עד ${maxWeeklyHours} שעות בשבוע · עד ${maxConsecutiveDays} ימים רצופים · ${minRestHours} שעות מנוחה`} tour="setup-limits" icon={<Scale />} title="גבולות עומס ומנוחה" hint="בדיקות אלה מציפות חריגות ומסייעות לשיבוץ; הן אינן חוסמות החלטת מפקד.">
          <div className="manual-grid three">
            <Field label="מקסימום שעות בשבוע"><input type="number" min={1} value={maxWeeklyHours} onChange={(e) => setMaxWeeklyHours(Number(e.target.value) || 1)} /></Field>
            <Field label="מקסימום ימים רצופים"><input type="number" min={1} value={maxConsecutiveDays} onChange={(e) => setMaxConsecutiveDays(Number(e.target.value) || 1)} /></Field>
            <Field label="מינימום מנוחה בין משמרות"><input type="number" min={0} value={minRestHours} onChange={(e) => setMinRestHours(Number(e.target.value) || 0)} /></Field>
          </div>
          <WeeklyShifts policy={unitPolicy} onChange={setUnitPolicy} />
        </SetupSection>

        {compiled.rest.length ? (
          <SetupSection {...section("compiled")} icon={<Cpu />} title="מה הקוד הבין — מדיניות כללית" hint="מה שלא שייך לחייל/ת או לכלל מסוים. מה שקשור לחייל/ת מופיע על הכרטיס שלו/ה, ומה שקשור לכלל — ליד הכלל.">
            <CompiledList sources={compiled.rest} />
          </SetupSection>
        ) : null}
      </main>

      <footer className="manual-savebar" data-tour="setup-save">
        <span>{employees.filter(named).length} אנשי צוות · {shifts.filter(named).length} סוגי משמרות · {rules.filter((rule) => text(rule.text)).length} כללים</span>
        <button type="button" className="primary-button" onClick={() => void save()} disabled={!ready || busy}><Save size={16} /> {busy ? "שומר…" : "שמירה ומעבר ללוח"}</button>
      </footer>
    </div>
  );
}

const SECTION_IDS = ["rotations", "people", "shifts", "rules", "limits", "compiled"] as const;
type SectionId = (typeof SECTION_IDS)[number];

/** Shifts a week (Sunday–Saturday) for סדיר and for מילואים, the unit
 *  standard's `weekly_shifts_regular` and `weekly_shifts`. A standard
 *  officer or NCO takes the regulars' unless the standard names their own;
 *  a soldier's own numbers in כוח אדם win over both. */
const WEEKLY_SHIFT_GROUPS = [
  { key: "weekly_shifts_regular", label: "סדיר" },
  { key: "weekly_shifts", label: "מילואים" },
] as const;

function WeeklyShifts({ policy, onChange }: { policy: UnitPolicy; onChange: React.Dispatch<React.SetStateAction<UnitPolicy>> }) {
  const set = (key: (typeof WEEKLY_SHIFT_GROUPS)[number]["key"], bound: "min" | "max", value: number | null) =>
    onChange((current) => {
      const block: { min?: number; max?: number } = { ...(current[key] ?? {}) };
      if (value === null) delete block[bound];
      else block[bound] = value;
      return { ...current, [key]: block };
    });
  return (
    <fieldset className="weekly-shifts">
      <legend>משמרות בשבוע לפי מעמד</legend>
      <div className="manual-grid limits-grid">
        {WEEKLY_SHIFT_GROUPS.map(({ key, label }) => (
          <Fragment key={key}>
            <Field label={`${label} · מינימום`}>
              <input type="number" min={0} max={14} inputMode="numeric" value={policy[key]?.min ?? ""} placeholder="ללא" onChange={(e) => set(key, "min", shiftCount(e.target.value))} />
            </Field>
            <Field label={`${label} · מקסימום`}>
              <input type="number" min={1} max={14} inputMode="numeric" value={policy[key]?.max ?? ""} placeholder="ללא" onChange={(e) => set(key, "max", shiftCount(e.target.value, 1))} />
            </Field>
          </Fragment>
        ))}
      </div>
      <small>שבוע ראשון–שבת. המקסימום נאכף בשיבוץ; המינימום מועדף על פני איזון ובקשות רכות, ומה שלא הושג מופיע בהערות הבנייה. מספר שמוגדר לחייל/ת בכוח אדם גובר. ריק = ללא מגבלה.</small>
    </fieldset>
  );
}

type SetupSectionProps = {
  tour?: string;
  icon: React.ReactNode;
  title: string;
  hint: string;
  /** One line said in place of the hint while the section is folded. */
  summary?: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
};

/** One part of the form. Folding it only hides it: its fields stay in
 *  state and are saved with the rest. Whether it is folded is held by the
 *  screen (`useCollapsed`), so one header button can fold them all. The
 *  whole header toggles; the button is what the keyboard reaches. */
/** Under a saved name that was edited: what the save will do with it. */
function RenameNote({ saved, name }: { saved: string; name: string }) {
  if (!saved || !name || saved === name) return null;
  return <small className="manual-rename-note" role="status">שם קודם: {saved} · בשמירה השם יתעדכן גם בסידורים, באילוצים ובבקשות</small>;
}

function SetupSection({ tour, icon, title, hint, summary, open, onToggle, children }: SetupSectionProps) {
  return (
    <section className={`manual-section${open ? "" : " is-closed"}`}>
      <header onClick={onToggle}>
        <span>{icon}</span>
        <div data-tour={tour}><h2>{title}</h2>{open ? <p>{hint}</p> : summary ? <p className="manual-section-summary">{summary}</p> : null}</div>
        <button type="button" className="icon-button subtle manual-section-toggle" aria-expanded={open} aria-label={open ? `סגירת ${title}` : `פתיחת ${title}`} title={open ? "סגירה" : "פתיחה"}>
          <ChevronDown size={16} aria-hidden="true" />
        </button>
      </header>
      <div className="manual-section-body" hidden={!open}>{children}</div>
    </section>
  );
}

/** Which roles may stand a shift. A role no longer on the roster stays
 *  listed while selected, so it can still be cleared. */
/** `{saved name: new name}` for every saved row whose name was edited. */
function renames(list: Row[]): Record<string, string> {
  const result: Record<string, string> = {};
  for (const row of list) {
    const saved = text(row[SAVED]);
    const name = text(row.name);
    if (saved && name && saved !== name) result[saved] = name;
  }
  return result;
}

function edit(setter: React.Dispatch<React.SetStateAction<Row[]>>, index: number, key: string, value: unknown) {
  setter((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row));
}

function record(value: unknown): Row { return value && typeof value === "object" && !Array.isArray(value) ? value as Row : {}; }
function rows(value: unknown): Row[] { return Array.isArray(value) ? value.filter((item): item is Row => Boolean(item) && typeof item === "object" && !Array.isArray(item)) : []; }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim())) : []; }
function text(value: unknown): string { return typeof value === "string" ? value.trim() : ""; }
function inputText(value: unknown): string { return typeof value === "string" ? value : ""; }
function exitPattern(row: Row, fallback: "round" | "triplet" = "round"): string {
  const value = text(row.exit_pattern);
  // A day cycle is checked against the workplace's cycles on save.
  if (isDayCycle(value)) return value;
  return value in EXIT_PATTERNS ? value : fallback;
}
function patternLabel(pattern: string, cycles: DayCycle[]): string {
  if (pattern in EXIT_PATTERNS) return EXIT_PATTERNS[pattern as keyof typeof EXIT_PATTERNS];
  return cycles.find((cycle) => cyclePattern(cycle) === pattern)?.name || "מחזור";
}
function rotationGroups(pattern: string, cycles: DayCycle[]): string[] {
  if (pattern in CYCLES) return [...CYCLES[pattern as Cycle].groups];
  return cycles.find((cycle) => cyclePattern(cycle) === pattern)?.groups ?? [];
}
function number(value: unknown, fallback: number): number { return typeof value === "number" && Number.isFinite(value) ? value : fallback; }
/** A headcount typed into a field: a whole number from 0 to 100. */
function seats(value: string): number { return Math.min(100, Math.max(0, Math.floor(Number(value)) || 0)); }
/** What a headcount of 0 means, said under the shift: it does not run then. */
function offNote(weekday: number, weekend: unknown): string {
  const weekendOff = weekend === 0 || (weekend === "" || weekend === undefined ? weekday === 0 : false);
  if (weekday === 0 && weekendOff) return "תקן 0 בכל הימים: המשמרת לא תיבנה עד שיוגדר לה תקן.";
  if (weekday === 0) return "תקן 0 באמצע השבוע: המשמרת פועלת רק בסופ״ש.";
  if (weekend === 0) return "תקן 0 בסופ״ש: המשמרת לא פועלת בסופ״ש.";
  return "";
}
function named(row: Row): boolean { return Boolean(text(row.name)); }
/** The weekend's own headcount, or "" when it takes the weekday number.
 *  Read off the staffing group marked as the closure's, or an older one
 *  naming exactly Friday and Saturday. */
function weekendHeadcount(shift: Row): number | "" {
  const group = rows(shift.staffing).find(isWeekendGroup);
  return typeof group?.headcount === "number" ? group.headcount : "";
}

function isWeekendGroup(group: Row): boolean {
  if (group.closure === true) return true;
  const days = strings(group.days);
  return days.length === WEEKEND.length && WEEKEND.every((day) => days.includes(day));
}

/** The staffing groups to save: the weekday default, any other per-day
 *  groups already stored, and the weekend's when one is set. The weekend
 *  group carries the default's required roles, since it replaces it on
 *  those days (`scheduler/slots.staffing_requirements`). */
function staffingFor(shift: Row, weekend: unknown, weekendDays: string[]): Row[] {
  const groups = rows(shift.staffing);
  const base = groups.find((group) => strings(group.days).length === 0);
  // The role composition is no longer set in setup; a save clears it.
  const roles: string[] = [];
  const others = groups.filter((group) => strings(group.days).length > 0 && !isWeekendGroup(group)).map((group) => ({ ...group, required_roles: [] }));
  return [
    { days: [], headcount: number(shift.headcount, headcount(shift)), required_roles: roles },
    ...others,
    ...(typeof weekend === "number" ? [{ days: weekendDays, headcount: weekend, required_roles: roles, closure: true }] : []),
  ];
}

type ClosureBounds = Pick<RotationClosureWindow, "start_day" | "start_time" | "end_day" | "end_time">;

/** The weekdays `shift` falls inside the weekend closure, when one group is
 *  home. Mirrors `rotation/closures`: the closure opens on `start_day` at
 *  `start_time` and ends at the handover, so the first day counts only for a
 *  shift still running at the opening and the last only for one starting
 *  before the handover. Offsets are from Saturday. */
function closureDays(shift: Row, window: ClosureBounds): string[] {
  const start = text(shift.start_time);
  const end = text(shift.end_time);
  const timed = Boolean(start && end);
  const days: string[] = [];
  for (let offset = window.start_day; offset <= window.end_day; offset += 1) {
    if (timed && offset === window.start_day && end > start && end <= window.start_time) continue;
    if (offset === window.end_day && offset > 0 && !(timed && start < window.end_time)) continue;
    days.push(DAYS[(offset + 13) % 7]);
  }
  // A closure opening on Sunday (שבוע־שבוע) meets the last one's handover.
  return [...new Set(days)];
}

function headcount(shift: Row): number {
  const staffing = rows(shift.staffing);
  const base = staffing.find((group) => strings(group.days).length === 0);
  return number(base?.headcount, 1);
}

/** The Saturday ending this week (today, when today is Saturday). */
function comingSaturday(): string {
  const now = new Date();
  const today = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
  today.setUTCDate(today.getUTCDate() + (6 - today.getUTCDay()));
  return today.toISOString().slice(0, 10);
}
