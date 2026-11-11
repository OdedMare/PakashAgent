"use client";

import { Clock3 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** A controlled `HH:MM` time that can be typed or picked. Native time inputs
 * offer no picker at all in some browsers and follow the browser locale in
 * others (AM/PM in an Israeli screen), so this types as 24-hour text and opens
 * its own hour/minute list from the clock button. `step` is in seconds, like
 * the native input's, and sets the minutes the list offers -- a typed time is
 * kept as typed. */
export function TimeInput({
  value,
  onChange,
  required = false,
  step = 300,
  ...props
}: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange" | "step"> & {
  value: string;
  onChange: (time: string) => void;
  step?: number;
}) {
  const input = useRef<HTMLInputElement>(null);
  const field = useRef<HTMLSpanElement>(null);
  const hours = useRef<HTMLSpanElement>(null);
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);
  const [open, setOpen] = useState(false);
  const [flip, setFlip] = useState(false);

  const current = parseTime(value);
  const [hour, minute] = current ? current.split(":") : ["", ""];
  const minuteStep = Math.min(30, Math.max(1, Math.round(step / 60)));
  const minutes = Array.from({ length: Math.ceil(60 / minuteStep) }, (_, i) => pad(i * minuteStep));

  useEffect(() => {
    if (!open) return;
    hours.current?.querySelector<HTMLElement>("[aria-selected='true']")?.scrollIntoView({ block: "center" });
    const close = (event: Event) => {
      if (!field.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      input.current?.focus();
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape, true);
    };
  }, [open]);

  const choose = (nextHour: string, nextMinute: string) => {
    input.current?.setCustomValidity("");
    setEditing(false);
    onChange(`${nextHour}:${nextMinute}`);
  };

  const toggle = () => {
    if (!open && field.current) {
      // Opens upward when there is no room below, like the calendar picker.
      const rect = field.current.getBoundingClientRect();
      setFlip(window.innerHeight - rect.bottom < 230 && rect.top > window.innerHeight - rect.bottom);
    }
    setOpen(!open);
  };

  return (
    <span className="picker-field" ref={field}>
      <input
        {...props}
        className={`picker-field-text${props.className ? ` ${props.className}` : ""}`}
        ref={input}
        type="text"
        dir="ltr"
        inputMode="numeric"
        autoComplete="off"
        placeholder="HH:MM"
        value={editing ? draft : value}
        required={required}
        maxLength={5}
        onChange={(event) => {
          const next = timeDraft(event.target.value);
          setDraft(next);
          input.current?.setCustomValidity("");
          const time = parseTime(next);
          if (time) onChange(time);
          if (!next) onChange("");
        }}
        onBlur={(event) => {
          const time = parseTime(draft);
          event.currentTarget.setCustomValidity(
            draft && !time ? "יש להזין שעה בפורמט שעות:דקות, למשל 07:30" : "",
          );
          setEditing(false);
          props.onBlur?.(event);
        }}
        onFocus={(event) => {
          setDraft(value);
          setEditing(true);
          props.onFocus?.(event);
        }}
        aria-label={props["aria-label"] ?? "שעה בפורמט שעות:דקות"}
      />
      <button
        type="button"
        className="picker-field-button"
        disabled={props.disabled || props.readOnly}
        aria-label="בחירת שעה מרשימה"
        aria-expanded={open}
        title="בחירה מרשימה"
        onClick={toggle}
      >
        <Clock3 size={16} aria-hidden="true" />
      </button>
      {open ? (
        <span className={`time-picker${flip ? " is-flipped" : ""}`} dir="ltr">
          <span className="time-picker-column" ref={hours} role="listbox" aria-label="שעה">
            {Array.from({ length: 24 }, (_, i) => pad(i)).map((h) => (
              <button
                key={h}
                type="button"
                role="option"
                aria-selected={h === hour}
                className="time-picker-option"
                onClick={() => choose(h, minute || "00")}
              >
                {h}
              </button>
            ))}
          </span>
          <span className="time-picker-column" role="listbox" aria-label="דקות">
            {minutes.map((m) => (
              <button
                key={m}
                type="button"
                role="option"
                aria-selected={m === minute}
                className="time-picker-option"
                onClick={() => {
                  choose(hour || "00", m);
                  setOpen(false);
                  input.current?.focus();
                }}
              >
                {m}
              </button>
            ))}
          </span>
        </span>
      ) : null}
    </span>
  );
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** `H:MM` or `HH:MM` as a valid 24-hour `HH:MM`, or "" when it is not one. */
function parseTime(value: string): string {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value);
  if (!match) return "";
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h > 23 || m > 59) return "";
  return `${pad(h)}:${match[2]}`;
}

/** Keeps a typed colon where the user put it; otherwise adds one after the
 * second digit, so `0730` reads `07:30`. */
function timeDraft(value: string): string {
  if (value.includes(":")) {
    const [h, ...rest] = value.split(":");
    return `${h.replace(/\D/g, "").slice(0, 2)}:${rest.join("").replace(/\D/g, "").slice(0, 2)}`;
  }
  const digits = value.replace(/\D/g, "").slice(0, 4);
  return digits.length <= 2 ? digits : `${digits.slice(0, 2)}:${digits.slice(2)}`;
}
