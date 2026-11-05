"use client";

import { Check, ChevronDown } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

/** A dropdown that picks any number of values from a scrolling list. The
 * closed field reads back what is chosen; the open list keeps its own height
 * and scrolls, so a unit with many shifts no longer pushes the form down with
 * a wall of checkboxes. Clicking an option toggles it and leaves the list
 * open; Escape or a click outside closes it.
 *
 * The closed field says *how much* is chosen — the one name, "הכל", or
 * "N נבחרו" — never every name joined: a soldier on many shifts made that
 * line longer than the field. The full choice is on the hover and in the
 * list, which opens on "בחירת הכל" and "ניקוי". */
export function MultiSelect({
  label,
  values,
  selected,
  onChange,
  placeholder = "לא נבחר",
  className = "",
}: {
  label: string;
  values: string[];
  selected: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  className?: string;
}) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [flip, setFlip] = useState(false);
  const [active, setActive] = useState(0);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const close = (event: Event) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape, true);
    };
  }, [open]);

  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const toggle = (value: string) => onChange(selected.includes(value)
    ? selected.filter((item) => item !== value)
    : values.filter((item) => item === value || selected.includes(item)));

  const show = () => {
    const box = trigger.current?.getBoundingClientRect();
    setFlip(Boolean(box && window.innerHeight - box.bottom < 240 && box.top > window.innerHeight - box.bottom));
    setActive(Math.max(0, values.findIndex((value) => selected.includes(value))));
    setOpen(true);
  };

  const keys = (event: React.KeyboardEvent) => {
    if (!open) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        show();
      }
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current) => (current + step + values.length) % values.length);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setActive(event.key === "Home" ? 0 : values.length - 1);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (values[active] !== undefined) toggle(values[active]);
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  };

  const chosen = values.filter((value) => selected.includes(value));
  const all = values.length > 1 && chosen.length === values.length;
  const summary = !chosen.length ? placeholder
    : chosen.length === 1 ? chosen[0]
    : all ? `הכל (${chosen.length})`
    : `${chosen.length} נבחרו`;
  const bulk = (next: string[]) => { onChange(next); trigger.current?.focus(); };

  return (
    <div className={`multi-select ${className}`.trim()} ref={root}>
      <span className="field-label" id={`${id}-label`}>{label}</span>
      <button
        ref={trigger}
        type="button"
        className="multi-select-trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-list`}
        aria-labelledby={`${id}-label`}
        aria-activedescendant={open ? `${id}-option-${active}` : undefined}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={keys}
        title={chosen.length > 1 ? chosen.join(", ") : undefined}
      >
        <span className={chosen.length ? "multi-select-value" : "multi-select-value is-empty"}>
          {summary}
        </span>
        <ChevronDown size={15} aria-hidden="true" />
      </button>
      {open ? (
        <div
          ref={list}
          id={`${id}-list`}
          className={flip ? "multi-select-list is-flipped" : "multi-select-list"}
          role="listbox"
          aria-multiselectable="true"
          aria-labelledby={`${id}-label`}
        >
          {values.length > 1 ? (
            <div className="multi-select-bulk" role="presentation">
              <button type="button" disabled={all} onPointerDown={(event) => event.preventDefault()} onClick={() => bulk([...values])}>
                בחירת הכל
              </button>
              <button type="button" disabled={!chosen.length} onPointerDown={(event) => event.preventDefault()} onClick={() => bulk([])}>
                ניקוי
              </button>
            </div>
          ) : null}
          {values.length ? values.map((value, index) => {
            const on = selected.includes(value);
            return (
              <div
                key={value}
                id={`${id}-option-${index}`}
                data-index={index}
                role="option"
                aria-selected={on}
                className={index === active ? "multi-select-option is-active" : "multi-select-option"}
                onPointerDown={(event) => event.preventDefault()}
                onPointerEnter={() => setActive(index)}
                onClick={() => {
                  setActive(index);
                  toggle(value);
                  trigger.current?.focus();
                }}
              >
                <span className="multi-select-box" aria-hidden="true">{on ? <Check size={13} /> : null}</span>
                <span>{value}</span>
              </div>
            );
          }) : <div className="multi-select-none">אין אפשרויות</div>}
          {values.length === 1 && chosen.length ? (
            <button type="button" className="multi-select-clear" onPointerDown={(event) => event.preventDefault()} onClick={() => bulk([])}>
              ניקוי הבחירה
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
