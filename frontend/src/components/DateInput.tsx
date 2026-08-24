"use client";

import { useRef, useState } from "react";

/** A controlled ISO date with a fixed Israeli display format (DD/MM/YYYY).
 * Native date inputs follow the browser locale and may show MM/DD even in an
 * RTL screen, so this keeps the visible order explicit while APIs still get
 * YYYY-MM-DD. */
export function DateInput({
  value,
  onChange,
  required = false,
  min,
  max,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange" | "min" | "max"> & {
  value: string;
  onChange: (iso: string) => void;
  min?: string;
  max?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState(() => displayDate(value));
  const [editing, setEditing] = useState(false);

  const validate = (text: string): string => {
    const iso = parseDisplayDate(text);
    if (!text && !required) return "";
    if (!iso) return "יש להזין תאריך בפורמט יום/חודש/שנה";
    if (min && iso < min) return `התאריך המוקדם ביותר הוא ${displayDate(min)}`;
    if (max && iso > max) return `התאריך המאוחר ביותר הוא ${displayDate(max)}`;
    return "";
  };

  return (
    <input
      {...props}
      ref={input}
      type="text"
      dir="ltr"
      inputMode="numeric"
      autoComplete="off"
      placeholder="DD/MM/YYYY"
      value={editing ? draft : displayDate(value)}
      required={required}
      maxLength={10}
      onChange={(event) => {
        const next = dateDraft(event.target.value);
        setDraft(next);
        input.current?.setCustomValidity("");
        const iso = parseDisplayDate(next);
        if (iso && (!min || iso >= min) && (!max || iso <= max)) onChange(iso);
        if (!next) onChange("");
      }}
      onBlur={(event) => {
        const message = validate(draft);
        event.currentTarget.setCustomValidity(message);
        setEditing(false);
        props.onBlur?.(event);
      }}
      onFocus={(event) => {
        setDraft(displayDate(value));
        setEditing(true);
        props.onFocus?.(event);
      }}
      aria-label={props["aria-label"] ?? "תאריך בפורמט יום/חודש/שנה"}
    />
  );
}

export function displayDate(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}

function parseDisplayDate(value: string): string {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value);
  if (!match) return "";
  const day = Number(match[1]);
  const month = Number(match[2]);
  const year = Number(match[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) return "";
  return `${match[3]}-${match[2]}-${match[1]}`;
}

function dateDraft(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 8);
  if (digits.length <= 2) return digits;
  if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
  return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
}
