"use client";

import { CalendarPlus, Trash2 } from "lucide-react";
import { useState } from "react";

import { DateInput, shortDate } from "@/components/DateInput";
import { TimeInput } from "@/components/TimeInput";
import type { RotationClosureWindow, RotationPresenceRule, RotationWeekend } from "@/types";

import { ShapePicker, WindowFields } from "./ClosureShape";
import { addDays, saturdayOf, shapeOf, shapeRow, windowSentence } from "./closureShapes";
import type { Shape } from "./closureShapes";
import { CheckboxGrid, Field } from "./fields";
import { RotationPreview } from "./RotationPreview";

export const CYCLES = {
  round: { label: "סבב", groups: ["א", "ב"], span: "שתי קבוצות שסוגרות לסירוגין — כל קבוצה פעם בשבועיים." },
  triplet: { label: "תלתון", groups: ["א", "ב", "ג"], span: "שלוש קבוצות שסוגרות בתורן — כל קבוצה פעם בשלושה שבועות, בנפרד מהסבב." },
} as const;
export type Cycle = keyof typeof CYCLES;

const DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"];

type Rows<T> = React.Dispatch<React.SetStateAction<T[]>>;

/** One cycle, stated once, in three questions.
 *
 *  1. Which weekend group א closes — the anchor; every other group's turn is
 *     derived from it by the server (`bl/rotation`).
 *  2. How long a closure runs — a shape (Thursday, Friday, a whole week, or
 *     typed days) stored as the cycle's one regular window row.
 *  3. Which weekends differ — dated window rows, one weekend or a range.
 *
 *  The strip under them is the server's answer for the coming weekends, so
 *  the manager sees what they typed before saving. Presence rules stay per
 *  group and sit under "מתקדם". */
export function CycleSetup({
  pattern, anchor, onAnchor, needsAnchor, windows, onWindows, presence, onPresence,
  shiftNames, handoverEnd, preview, previewLoading,
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
  /** When Sunday's first shift ends — where a closure set here stops. */
  handoverEnd: string;
  preview: RotationWeekend[] | undefined;
  previewLoading: boolean;
}) {
  const { label, groups, span } = CYCLES[pattern];
  const [first] = groups;
  const mine = (row: RotationClosureWindow) => row.pattern === pattern && row.group === first;
  const dated = (row: RotationClosureWindow) => Boolean(row.starts_on || row.ends_on);
  // The server reads the last undated row as the cycle's hours.
  const regularIndex = windows.findLastIndex((row) => mine(row) && !dated(row));
  const regular = regularIndex >= 0 ? windows[regularIndex] : undefined;
  // "ימים ושעות אחרים" stays chosen even while its values match a shape.
  const [custom, setCustom] = useState(false);
  const shape = custom && regular ? "custom" : shapeOf(regular, handoverEnd);
  const overridden = [...new Set(windows.filter((row) => row.pattern === pattern && row.group !== first).map((row) => row.group))];
  const base = { pattern, group: first, starts_on: "", ends_on: "" } as const;

  const setShape = (next: Shape) => { setCustom(next === "custom"); onWindows((rows) => {
    const row = shapeRow(next, handoverEnd, regular && next === "custom" ? regular : base);
    const kept = rows.filter((item) => !(mine(item) && !dated(item)));
    return row ? [...kept, row as RotationClosureWindow] : kept;
  }); };
  const editRow = (index: number, patch: Partial<RotationClosureWindow>) => onWindows((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  const addException = () => {
    const next = preview?.find((weekend) => weekend.saturday >= todayIso())?.saturday ?? saturdayOf(todayIso());
    onWindows((rows) => [...rows, { ...(shapeRow("friday", handoverEnd, base) as RotationClosureWindow), starts_on: next, ends_on: next, note: "" }]);
  };

  return (
    <article className={`rotation-cycle-card${pattern === "triplet" ? " is-triplet" : ""}`}>
      <header><strong>{label} {groups.map((group) => `${group}׳`).join(" / ")}</strong><span>{span}</span></header>

      <section className="rotation-step">
        <header><b>1</b><div><strong>מתי {label} {first}׳ סוגר?</strong><span>בחרו תאריך כלשהו מסופ״ש אחד שבו {label} {first}׳ בבסיס — השבת, או חמישי/שישי של אותו סופ״ש. משם הקבוצות מתחלפות כל שבוע לבד.</span></div></header>
        <Field label={`סופ״ש של ${label} ${first}׳`}><DateInput value={anchor} onChange={onAnchor} /></Field>
        {needsAnchor && !anchor ? <p className="rotation-derived-note is-warning" role="status">יש אנשי צוות ב{label}, ובלי התאריך הזה אי אפשר לבנות להם סידור.</p> : null}
      </section>

      <section className="rotation-step">
        <header><b>2</b><div><strong>{pattern === "round" ? "איזה סוג סבב?" : "כמה זמן נמשכת סגירה רגילה?"}</strong><span>ימים בבסיס / ימים בבית. חל על כל הקבוצות, כל אחת בתורה.</span></div></header>
        <ShapePicker name={`shape-${pattern}`} value={shape} groups={groups.length} onChange={setShape} />
        {regular ? (
          <>
            <p className="rotation-sentence">{label} {first}׳ (וכל קבוצה בתורה) בבסיס <b>{windowSentence(regular)}</b>.</p>
            <WindowFields row={regular} showDays={shape === "custom"} onChange={(patch) => editRow(regularIndex, patch)} />
          </>
        ) : <p className="rotation-sentence">ברירת המחדל: הסגירה מחמישי עד אחרי המשמרת הראשונה של יום ראשון.</p>}
        {overridden.length ? (
          <p className="rotation-derived-note">
            ל{label} {overridden.map((group) => `${group}׳`).join(" ו")} נשמרו בעבר שעות נפרדות, והן גוברות על השעות של {first}׳.{" "}
            <button type="button" className="rotation-link" onClick={() => onWindows((rows) => rows.filter((row) => row.pattern !== pattern || row.group === first))}>הסרה — כל הקבוצות לפי {first}׳</button>
          </p>
        ) : null}
      </section>

      <section className="rotation-step">
        <header><b>3</b><div><strong>סופ״שים חריגים</strong><span>חג, אירוע או סופ״ש שבו יוצאים בשעה אחרת. הסבב לא זז — רק השעות של אותו סופ״ש משתנות.</span></div></header>
        {windows.map((row, index) => mine(row) && dated(row)
          ? <ExceptionRow key={index} row={row} handoverEnd={handoverEnd} groups={groups.length} preview={preview} onChange={(patch) => editRow(index, patch)} onRemove={() => onWindows((rows) => rows.filter((_, i) => i !== index))} />
          : null)}
        <button type="button" className="ghost-button" onClick={addException}><CalendarPlus size={16} /> הוספת סופ״ש חריג</button>
      </section>

      <section className="rotation-step is-preview">
        <header><div><strong>כך ייראו הסופ״שים הקרובים</strong><span>מחושב בשרת מההגדרות שעל המסך, עוד לפני השמירה.</span></div></header>
        <RotationPreview weekends={preview} loading={previewLoading} />
      </section>

      <PresenceRules pattern={pattern} label={label} groups={groups} presence={presence} onPresence={onPresence} shiftNames={shiftNames} />
    </article>
  );
}

function ExceptionRow({ row, handoverEnd, groups, preview, onChange, onRemove }: {
  row: RotationClosureWindow; handoverEnd: string; groups: number; preview: RotationWeekend[] | undefined;
  onChange: (patch: Partial<RotationClosureWindow>) => void; onRemove: () => void;
}) {
  const single = row.starts_on === row.ends_on;
  const [custom, setCustom] = useState(false);
  const shape = custom ? "custom" : shapeOf(row, handoverEnd);
  const owner = single ? preview?.find((weekend) => weekend.saturday === row.starts_on) : undefined;
  return (
    <article className="manual-row rotation-rule">
      <div className="rotation-rule-head">
        <div>
          <strong>{row.note || "סופ״ש חריג"}{single && row.starts_on ? ` · שבת ${shortDate(row.starts_on)}` : ""}</strong>
          <span>{owner ? `${owner.label}׳ סוגר/ת את הסופ״ש הזה, ` : ""}{windowSentence(row)}.</span>
        </div>
        <button type="button" className="icon-button subtle" aria-label="הסרת הסופ״ש החריג" onClick={onRemove}><Trash2 size={15} /></button>
      </div>
      <div className="manual-grid three">
        {single
          ? <Field label="תאריך כלשהו בסופ״ש"><DateInput value={row.starts_on} onChange={(iso) => { const saturday = saturdayOf(iso); onChange({ starts_on: saturday, ends_on: saturday }); }} /></Field>
          : <>
              <Field label="מסופ״ש של תאריך"><DateInput value={row.starts_on} max={row.ends_on || undefined} onChange={(iso) => onChange({ starts_on: iso ? saturdayOf(iso) : "" })} /></Field>
              <Field label="עד סופ״ש של תאריך"><DateInput value={row.ends_on} min={row.starts_on || undefined} onChange={(iso) => onChange({ ends_on: iso ? saturdayOf(iso) : "" })} /></Field>
            </>}
        <Field label="שם (רשות)"><input value={row.note ?? ""} placeholder="לדוגמה: פסח" onChange={(event) => onChange({ note: event.target.value })} /></Field>
      </div>
      <button type="button" className="rotation-link" onClick={() => onChange(single ? { ends_on: row.starts_on ? addDays(row.starts_on, 14) : "" } : { ends_on: row.starts_on })}>
        {single ? "להחיל על כמה סופ״שים ברצף" : "רק סופ״ש אחד"}
      </button>
      <ShapePicker name={`exception-${row.starts_on}-${row.note}`} value={shape} groups={groups} onChange={(next) => { setCustom(next === "custom"); onChange(shapeRow(next, handoverEnd, row, true) ?? {}); }} />
      <WindowFields row={row} showDays={shape === "custom"} onChange={onChange} />
    </article>
  );
}

function PresenceRules({ pattern, label, groups, presence, onPresence, shiftNames }: {
  pattern: Cycle; label: string; groups: readonly string[]; presence: RotationPresenceRule[];
  onPresence: Rows<RotationPresenceRule>; shiftNames: string[];
}) {
  const count = presence.filter((row) => row.pattern === pattern).length;
  const editPresence = (index: number, patch: Partial<RotationPresenceRule>) => onPresence((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  return (
    <details className="rotation-advanced" open={count > 0}>
      <summary>מתקדם: קבוצה שנמצאת או לא נמצאת בימים קבועים{count ? ` (${count})` : ""}</summary>
      <p className="rotation-hint">למשל ״{label} ב׳ לא נמצאת בימי שלישי״. כלל כזה שייך לקבוצה אחת בלבד ומחייב בשיבוץ. ״נמצאת רק בשעות האלה״ מחליף את הסגירה בימים שנבחרו; אי־נוכחות גוברת על נוכחות, וכלל עם תאריכים גובר על כלל קבוע.</p>
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
            <Field label="בתוקף מתאריך (רשות)"><DateInput value={row.starts_on} max={row.ends_on || undefined} onChange={(iso) => editPresence(index, { starts_on: iso })} /></Field>
            <Field label="בתוקף עד תאריך (רשות)"><DateInput value={row.ends_on} min={row.starts_on || undefined} onChange={(iso) => editPresence(index, { ends_on: iso })} /></Field>
          </div>
        </article>
      ) : null)}
      <button type="button" className="ghost-button" onClick={() => onPresence((rows) => [...rows, { pattern, group: groups[0], available: false, days: [], shifts: [], start_time: "", end_time: "", starts_on: "", ends_on: "", reason: "" }])}>הוספת כלל נוכחות</button>
    </details>
  );
}

/** The weekend group א closes, from an anchor stated for any group.
 *
 *  An older profile may anchor on whichever group the
 *  manager happened to name. Moving that to א's next turn describes the same
 *  cycle, and lets this screen ask for one date instead of a date and a group. */
export function firstGroupAnchor(pattern: Cycle, date: string, group: string): string {
  const groups: readonly string[] = CYCLES[pattern].groups;
  const index = groups.indexOf(group);
  return index > 0 ? addDays(date, 7 * (groups.length - index)) : date;
}

function todayIso(): string {
  const now = new Date();
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())).toISOString().slice(0, 10);
}
