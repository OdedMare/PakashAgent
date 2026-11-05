"use client";

/** "יציאות" — the whole rotation question, in four fields.
 *
 *  1. A closed list of every kind of exit the unit has (any number).
 *  2–5. For weekend groups only: the round type every earlier screen
 *     offered (11/3, 12/2, 10/4, שבוע־שבוע, other), which fills in when a
 *     closure starts and ends (both editable), and how many groups (סבבים)
 *     take turns — 2 = סבב, 3 = תלתון, 4 = רבעון,
 *     5 = חמישון.
 *
 *  No calendar, no exception weekends and no "which date does which group
 *  close": which group closes when is derived by the server from an anchor
 *  the screen keeps (or sets to the coming Saturday). What is chosen is saved
 *  as `enabled_exit_patterns`; a pattern somebody is on cannot be switched
 *  off here, so nobody is left on a hidden one. */

import { MultiSelect } from "@/components/MultiSelect";
import { TimeInput } from "@/components/TimeInput";
import type { RotationClosureWindow } from "@/types";

import { DAY_NAMES, SHAPES, shapeLabel, shapeOf, shapeRow } from "./closureShapes";
import type { Shape } from "./closureShapes";
import { Field } from "./fields";
import type { Cycle } from "./RotationSetup";

export type Kind = "none" | "daily" | "weekends" | "hamshushim" | "shushim" | "days" | "personal" | "reserve";

export const GROUP_CYCLES: { pattern: Cycle; groups: number; label: string }[] = [
  { pattern: "round", groups: 2, label: "2 — סבב" },
  { pattern: "triplet", groups: 3, label: "3 — תלתון" },
  { pattern: "quad", groups: 4, label: "4 — רבעון" },
  { pattern: "quint", groups: 5, label: "5 — חמישון" },
];

const KINDS: { kind: Kind; label: string; patterns: string[] }[] = [
  { kind: "none", label: "בלי יציאות", patterns: ["none"] },
  { kind: "daily", label: "הולכים הביתה כל יום", patterns: ["daily"] },
  { kind: "weekends", label: "סבבים — קבוצות שסוגרות שבתות בתורות", patterns: GROUP_CYCLES.map((item) => item.pattern) },
  { kind: "hamshushim", label: "חמשושים — כל סופ״ש בבית מחמישי", patterns: ["hamshushim"] },
  { kind: "shushim", label: "שושים — כל סופ״ש בבית משישי", patterns: ["shushim"] },
  { kind: "days", label: "ימים בבסיס / ימים בבית", patterns: [] },
  { kind: "personal", label: "סגירה אישית 1 ל־N", patterns: ["personal"] },
  { kind: "reserve", label: "מילואים", patterns: [] },
];

// Closure days are stored as offsets from the closing Saturday: a closure
// may open as early as the Sunday before it (-6) and end as late as the
// Friday after it (6).
const START_DAYS = DAY_NAMES.map((day, index) => ({ value: index - 6, label: day }));
const END_DAYS = [{ value: 0, label: "שבת" }, ...DAY_NAMES.slice(0, 6).map((day, index) => ({ value: index + 1, label: `${day} שאחרי` }))];

export type ClosureWindow = Pick<RotationClosureWindow, "start_day" | "start_time" | "end_day" | "end_time">;

export function ExitKinds({
  enabled, used, dayCyclesOn, dayCyclesUsed, reserveOn, reserveBusy, cycle, window, handoverEnd,
  onEnabled, onDayCycles, onReserve, onCycle, onWindow,
}: {
  enabled: Set<string>;
  /** Patterns somebody on the roster is on: locked on. */
  used: Set<string>;
  dayCyclesOn: boolean;
  /** Somebody is on a day cycle: the kind stays on. */
  dayCyclesUsed: boolean;
  reserveOn: boolean;
  reserveBusy: boolean;
  /** The weekend-groups cycle chosen, when that kind is on. */
  cycle: Cycle | undefined;
  window: ClosureWindow;
  /** When Sunday's first shift ends — where a round type's closure stops. */
  handoverEnd: string;
  onEnabled: (patterns: Set<string>) => void;
  onDayCycles: (on: boolean) => void;
  onReserve: (on: boolean) => void;
  onCycle: (pattern: Cycle) => void;
  onWindow: (patch: Partial<ClosureWindow>) => void;
}) {
  const isOn = (kind: Kind, patterns: string[]) => kind === "days" ? dayCyclesOn : kind === "reserve" ? reserveOn
    : patterns.some((pattern) => enabled.has(pattern));
  const locked = (kind: Kind, patterns: string[]) => kind === "days" ? dayCyclesUsed
    : kind === "reserve" ? reserveBusy : patterns.some((pattern) => used.has(pattern));

  const selected = KINDS.filter(({ kind, patterns }) => isOn(kind, patterns)).map(({ label }) => label);
  const lockedLabels = KINDS.filter(({ kind, patterns }) => isOn(kind, patterns) && locked(kind, patterns)).map(({ label }) => label);

  const change = (labels: string[]) => {
    const next = new Set(enabled);
    for (const { kind, label, patterns } of KINDS) {
      const want = labels.includes(label);
      if (want === isOn(kind, patterns)) continue;
      if (!want && locked(kind, patterns)) continue;
      if (kind === "days") { onDayCycles(want); continue; }
      if (kind === "reserve") { onReserve(want); continue; }
      // Turning the groups on starts at a סבב; the count below refines it.
      if (want) (kind === "weekends" ? ["round"] : patterns).forEach((pattern) => next.add(pattern));
      else patterns.filter((pattern) => !used.has(pattern)).forEach((pattern) => next.delete(pattern));
    }
    onEnabled(next);
  };

  const groups = GROUP_CYCLES.find((item) => item.pattern === cycle)?.groups ?? 2;
  const shape = shapeOf(window as RotationClosureWindow, handoverEnd);
  const pickShape = (next: Shape) => {
    if (next === "custom") return;
    const row = shapeRow(next, handoverEnd, {}, true)!;
    onWindow({ start_day: row.start_day, start_time: row.start_time, end_day: row.end_day, end_time: row.end_time });
  };
  const shapeText = (item: Shape) => {
    const { title, detail } = shapeLabel(item, groups);
    return item === "custom" ? "ימים ושעות אחרים — לפי השדות שמתחת" : `${title} — ${detail.replace(/\.$/, "")}`;
  };

  return (
    <div className="exit-setup">
      <MultiSelect label="סוגי היציאות ביחידה" values={KINDS.map(({ label }) => label)} selected={selected} onChange={change} placeholder="לא נבחרו יציאות" />
      {lockedLabels.length ? <p className="rotation-hint">יש אנשי צוות ב: {lockedLabels.join(" · ")} — אי אפשר להסיר עד שמעבירים אותם.</p> : null}

      {cycle ? (
        <div className="manual-grid exit-closure">
          <Field label="סוג סבב">
            <select value={shape} onChange={(event) => pickShape(event.target.value as Shape)}>
              {SHAPES.map((item) => <option key={item} value={item}>{shapeText(item)}</option>)}
            </select>
          </Field>
          <Field label="כמות סבבים">
            <select value={cycle} onChange={(event) => onCycle(event.target.value as Cycle)}>
              {GROUP_CYCLES.map((item) => <option key={item.pattern} value={item.pattern}>{item.label}</option>)}
            </select>
          </Field>
          <Field label="הסגירה מתחילה ביום">
            <select value={window.start_day} onChange={(event) => onWindow({ start_day: Number(event.target.value) })}>
              {START_DAYS.map((day) => <option key={day.value} value={day.value}>{day.label}</option>)}
            </select>
          </Field>
          <Field label="בשעה"><TimeInput value={window.start_time} onChange={(time) => onWindow({ start_time: time })} /></Field>
          <Field label="הסגירה נגמרת ביום">
            <select value={window.end_day} onChange={(event) => onWindow({ end_day: Number(event.target.value) })}>
              {END_DAYS.map((day) => <option key={day.value} value={day.value}>{day.label}</option>)}
            </select>
          </Field>
          <Field label="בשעה"><TimeInput value={window.end_time} onChange={(time) => onWindow({ end_time: time })} /></Field>
        </div>
      ) : null}
    </div>
  );
}
