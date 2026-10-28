"use client";

import { Plus, Trash2 } from "lucide-react";

import { DateInput } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";
import type { RotationClosureWindow, RotationPresenceRule } from "@/types";

import { CheckboxGrid, Field } from "./fields";
import { RotationCalendar } from "./RotationCalendar";

export const CYCLES = {
  round: { label: "סבב", groups: ["א", "ב"], span: "מחזור של שני סופי־שבוע" },
  triplet: { label: "תלתון", groups: ["א", "ב", "ג"], span: "מחזור של שלושה סופי־שבוע, בנפרד מהסבב" },
} as const;
export type Cycle = keyof typeof CYCLES;

const DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];
// Closure days are stored as offsets from the closing Saturday: a closure
// may open as early as the Sunday before it (-6) and end as late as the
// Friday after it (6).
const START_DAYS = [-3, -2, -1, 0];
const DEFAULT_START_DAY = -2;
const END_DAYS = ["שבת", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי"];

type Rows<T> = React.Dispatch<React.SetStateAction<T[]>>;

/** One cycle, stated once.
 *
 *  The manager anchors and times group א only. Whose weekend it is, and the
 *  hours every other group closes on, are derived from that by the server
 *  (`bl/rotation`); the calendar is a preview of the one weekend clicked
 *  into it, not a second cycle. Presence rules are the exception
 *  and stay per group — "ב is out on Tuesdays" says nothing about א. */
export function CycleSetup({
  pattern,
  anchor,
  onAnchor,
  needsAnchor,
  windows,
  onWindows,
  presence,
  onPresence,
  shiftNames,
  handoverEnd,
}: {
  pattern: Cycle;
  anchor: string;
  onAnchor: (iso: string) => void;
  needsAnchor: boolean;
  windows: RotationClosureWindow[];
  onWindows: Rows<RotationClosureWindow>;
  presence: RotationPresenceRule[];
  onPresence: Rows<RotationPresenceRule>;
  shiftNames: string[];
  /** When the Sunday handover shift ends — where a new closure row stops. */
  handoverEnd: string;
}) {
  const { label, groups, span } = CYCLES[pattern];
  const [first, ...derived] = groups;
  const others = derived.map((group) => `${group}׳`).join(" ו");
  const overridden = [...new Set(
    windows.filter((row) => row.pattern === pattern && row.group !== first).map((row) => row.group),
  )];
  const hasWindow = windows.some((row) => row.pattern === pattern && row.group === first);
  const hasPresence = presence.some((row) => row.pattern === pattern);
  const editWindow = (index: number, patch: Partial<RotationClosureWindow>) => onWindows((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  // Days on base are set by the day the closure opens: the group not closing
  // is home from then until the Sunday handover. Without a row the server's
  // default applies, which opens on Thursday.
  const regular = windows.findIndex((row) => row.pattern === pattern && row.group === first && !row.starts_on && !row.ends_on);
  const startDay = regular >= 0 ? windows[regular].start_day : DEFAULT_START_DAY;
  const setStartDay = (day: number) => {
    if (regular >= 0) editWindow(regular, { start_day: day });
    else if (day !== DEFAULT_START_DAY) onWindows((rows) => [...rows, { pattern, group: first, start_day: day, start_time: "00:00", end_day: 1, end_time: handoverEnd || "00:00", starts_on: "", ends_on: "" }]);
  };
  const editPresence = (index: number, patch: Partial<RotationPresenceRule>) => onPresence((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));

  return (
    <article className={`rotation-cycle-card${pattern === "triplet" ? " is-triplet" : ""}`}>
      <header><strong>{label} {groups.join(" / ")}</strong><span>{span}</span></header>

      <div className="rotation-days day-cycle-presets" role="group" aria-label="ימים בבסיס ובבית">
        <span>ימים בבסיס / בבית</span>
        {START_DAYS.map((day) => {
          const base = 7 * groups.length - (groups.length - 1) * (1 - day);
          return (
            <button type="button" key={day} className={`chip-button${day === startDay ? " is-selected" : ""}`}
              title={`הקבוצה שלא סוגרת יוצאת הביתה ב${DAYS[day + 6]}`} onClick={() => setStartDay(day)}>
              {base}/{7 * groups.length - base}
            </button>
          );
        })}
      </div>
      <RotationCalendar label={label} groups={groups} anchor={anchor} startDay={startDay} onAnchor={onAnchor} />
      {needsAnchor && !anchor
        ? <p className="rotation-derived-note is-warning" role="status">יש אנשי צוות ב{label}, ובלי עוגן אי אפשר לבנות להם סידור. לחצו על סופ״ש שבו {label} {first}׳ סוגר.</p>
        : <p className="rotation-hint">{anchor ? `לחיצה על סופ״ש אחר מעבירה אליו את ${first}׳; ${others} נגזר${derived.length > 1 ? "ות" : "ת"} לבד.` : `לחצו על סופ״ש שבו ${label} ${first}׳ סוגר — השאר נצבע לבד.`}</p>}

      <section className="rotation-block">
        <header><strong>שעות הסגירה</strong><span>מגדירים פעם אחת, ל{label} {first}׳. {others} סוגר{derived.length > 1 ? "ות" : "ת"} באותן שעות, בסופ״ש שלה{derived.length > 1 ? "ן" : ""}.</span></header>
        {windows.map((row, index) => {
          if (row.pattern !== pattern || row.group !== first) return null;
          const dated = Boolean(row.starts_on || row.ends_on);
          return (
            <article className="manual-row rotation-rule" key={index}>
              <div className="rotation-rule-head">
                <div><strong>{dated ? "שינוי זמני" : "שעות קבועות"}</strong><span>{dated ? "גובר על השעות הקבועות בסגירות שהשבת שלהן בטווח התאריכים." : "חלות על כל סגירה, של כל קבוצה. תאריכי תחולה הופכים אותן לשינוי זמני."}</span></div>
                <button type="button" className="icon-button subtle" aria-label="הסרת שעות הסגירה" onClick={() => onWindows((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={15} /></button>
              </div>
              <div className="manual-grid rotation-window-grid">
                <Field label="תחילת הסגירה"><select value={row.start_day} onChange={(event) => editWindow(index, { start_day: Number(event.target.value) })}>{DAYS.map((day, i) => <option key={day} value={i - 6}>{day}</option>)}</select></Field>
                <Field label="שעת התחלה"><TimeInput value={row.start_time} onChange={(time) => editWindow(index, { start_time: time })} /></Field>
                <Field label="סיום הסגירה"><select value={row.end_day} onChange={(event) => editWindow(index, { end_day: Number(event.target.value) })}>{END_DAYS.map((day, i) => <option key={day} value={i}>{day}</option>)}</select></Field>
                <Field label="שעת חילוף / יציאה"><TimeInput value={row.end_time} onChange={(time) => editWindow(index, { end_time: time })} /></Field>
              </div>
              <DateRange startsOn={row.starts_on} endsOn={row.ends_on} onChange={(patch) => editWindow(index, patch)} />
            </article>
          );
        })}
        {hasWindow ? null : <p className="rotation-empty">ברירת המחדל: מחמישי בתחילת היום עד סוף המשמרת הראשונה בראשון.</p>}
        <button type="button" className="ghost-button" onClick={() => onWindows((rows) => [...rows, { pattern, group: first, start_day: -2, start_time: "12:00", end_day: 1, end_time: "12:00", starts_on: "", ends_on: "" }])}><Plus size={16} /> {hasWindow ? "הוספת שינוי זמני בשעות" : "הגדרת שעות הסגירה"}</button>
        {overridden.length ? (
          <p className="rotation-derived-note">
            ל{label} {overridden.map((group) => `${group}׳`).join(" ו")} נשמרו בעבר שעות נפרדות, והן גוברות אצל{overridden.length > 1 ? "ן" : "ה"} על השעות של {first}׳.{" "}
            <button type="button" className="rotation-link" onClick={() => onWindows((rows) => rows.filter((row) => row.pattern !== pattern || row.group === first))}>הסרה — כל הקבוצות לפי {first}׳</button>
          </p>
        ) : null}
      </section>

      <section className="rotation-block">
        <header><strong>נוכחות חריגה של קבוצה</strong><span>רשות. כלל כזה שייך לקבוצה אחת בלבד, אינו נגזר לאחרות, ומחייב בשיבוץ.</span></header>
        {presence.map((row, index) => row.pattern === pattern ? (
          <article className="manual-row rotation-rule" key={index}>
            <div className="rotation-rule-head">
              <div><strong>{label} {row.group}׳ · {row.available ? "נוכחות" : "אי־נוכחות"}</strong><span>ללא ימים = כל הימים · ללא שעות = כל היום · ללא משמרות = כל המשמרות.</span></div>
              <button type="button" className="icon-button subtle" aria-label="הסרת כלל הנוכחות" onClick={() => onPresence((rows) => rows.filter((_, i) => i !== index))}><Trash2 size={15} /></button>
            </div>
            <div className="manual-grid three">
              <Field label="קבוצה"><select value={row.group} onChange={(event) => editPresence(index, { group: event.target.value })}>{groups.map((group) => <option key={group} value={group}>{label} {group}׳</option>)}</select></Field>
              <Field label="נוכחות"><select value={String(row.available)} onChange={(event) => editPresence(index, { available: event.target.value === "true" })}><option value="false">לא נמצאת — חסומה לשיבוץ</option><option value="true">נמצאת רק בשעות האלה</option></select></Field>
              <Field label="הערה"><input value={row.reason} onChange={(event) => editPresence(index, { reason: event.target.value })} /></Field>
            </div>
            <CheckboxGrid label="ימים" values={DAYS} selected={row.days} onChange={(days) => editPresence(index, { days })} />
            {shiftNames.length ? <CheckboxGrid label="משמרות" values={shiftNames} selected={row.shifts} onChange={(shifts) => editPresence(index, { shifts })} /> : null}
            <div className="manual-grid rotation-window-grid">
              <Field label="משעה (רשות)"><TimeInput value={row.start_time} onChange={(time) => editPresence(index, { start_time: time })} /></Field>
              <Field label="עד שעה (רשות)"><TimeInput value={row.end_time} onChange={(time) => editPresence(index, { end_time: time })} /></Field>
            </div>
            <DateRange startsOn={row.starts_on} endsOn={row.ends_on} onChange={(patch) => editPresence(index, patch)} />
          </article>
        ) : null)}
        <button type="button" className="ghost-button" onClick={() => onPresence((rows) => [...rows, { pattern, group: first, available: false, days: [], shifts: [], start_time: "", end_time: "", starts_on: "", ends_on: "", reason: "" }])}><Plus size={16} /> הוספת נוכחות / אי־נוכחות</button>
        {hasPresence ? <p className="rotation-hint">״נמצאת רק בשעות האלה״ מחליף את הסגירה בימים שנבחרו, ומשמרת חייבת להתאים במלואה לשעות. אי־נוכחות גוברת על נוכחות כששני כללים חלים יחד, וכלל עם תאריכי תחולה גובר על כלל קבוע.</p> : null}
      </section>
    </article>
  );
}

function DateRange({ startsOn, endsOn, onChange }: { startsOn: string; endsOn: string; onChange: (patch: { starts_on?: string; ends_on?: string }) => void }) {
  return (
    <div className="manual-grid rotation-window-grid">
      <Field label="בתוקף מתאריך (רשות)"><DateInput value={startsOn} max={endsOn || undefined} onChange={(iso) => onChange({ starts_on: iso })} /></Field>
      <Field label="בתוקף עד תאריך (רשות)"><DateInput value={endsOn} min={startsOn || undefined} onChange={(iso) => onChange({ ends_on: iso })} /></Field>
    </div>
  );
}

/** The weekend group א closes on, from an anchor stated for any group.
 *
 *  An older profile may anchor on whichever group the
 *  manager happened to name. Moving that to א's next turn describes the same
 *  cycle, and lets this screen ask for one date instead of a date and a group. */
export function firstGroupAnchor(pattern: Cycle, date: string, group: string): string {
  const groups: readonly string[] = CYCLES[pattern].groups;
  const index = groups.indexOf(group);
  return index > 0 ? addDays(date, 7 * (groups.length - index)) : date;
}

function addDays(iso: string, days: number): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return "";
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + days)).toISOString().slice(0, 10);
}
