"use client";

import { TimeInput } from "@/components/TimeInput";
import type { RotationClosureWindow } from "@/types";

import { DAY_NAMES, SHAPES, shapeLabel } from "./closureShapes";
import type { Shape } from "./closureShapes";
import { Field } from "./fields";

// Closure days are stored as offsets from the closing Saturday: a closure
// may open as early as the Sunday before it (-6) and end as late as the
// Friday after it (6).
const START_DAYS = DAY_NAMES.map((day, index) => ({ value: index - 6, label: day }));
const END_DAYS = [{ value: 0, label: "שבת" }, ...DAY_NAMES.slice(0, 6).map((day, index) => ({ value: index + 1, label: `${day} שאחרי` }))];

/** The round types as large choices instead of four bare fields. */
export function ShapePicker({ name, value, groups, onChange }: { name: string; value: Shape; groups: number; onChange: (shape: Shape) => void }) {
  return (
    <div className="closure-shapes" role="radiogroup" aria-label="סוג הסבב">
      {SHAPES.map((shape) => {
        const { title, detail } = shapeLabel(shape, groups);
        return (
          <label key={shape} className={`closure-shape${value === shape ? " is-selected" : ""}`}>
            <input type="radio" name={name} checked={value === shape} onChange={() => onChange(shape)} />
            <strong>{title}</strong>
            <span>{detail}</span>
          </label>
        );
      })}
    </div>
  );
}

type Window = Pick<RotationClosureWindow, "start_day" | "start_time" | "end_day" | "end_time">;

/** The day and clock a closure opens and ends on. Every shape is editable
 *  here; days are shown only for "ימים ושעות אחרים", since the other shapes
 *  are defined by their days. */
export function WindowFields({ row, showDays, onChange }: { row: Window; showDays: boolean; onChange: (patch: Partial<Window>) => void }) {
  return (
    <div className={`manual-grid closure-clock${showDays ? " has-days" : ""}`}>
      {showDays ? <Field label="נכנסים לסגירה ביום"><select value={row.start_day} onChange={(event) => onChange({ start_day: Number(event.target.value) })}>{START_DAYS.map((day) => <option key={day.value} value={day.value}>{day.label}</option>)}</select></Field> : null}
      <Field label={showDays ? "בשעה" : "שעת כניסה לסגירה"}><TimeInput value={row.start_time} onChange={(time) => onChange({ start_time: time })} /></Field>
      {showDays ? <Field label="יוצאים ביום"><select value={row.end_day} onChange={(event) => onChange({ end_day: Number(event.target.value) })}>{END_DAYS.map((day) => <option key={day.value} value={day.value}>{day.label}</option>)}</select></Field> : null}
      <Field label={showDays ? "בשעה" : "שעת יציאה / חילוף ביום ראשון"}><TimeInput value={row.end_time} onChange={(time) => onChange({ end_time: time })} /></Field>
    </div>
  );
}
