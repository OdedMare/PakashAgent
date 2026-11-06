"use client";

import { CalendarDays, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { shortDate } from "@/components/DateInput";
import { rotationPreview } from "@/services/api";
import type { RotationWeekend } from "@/types";

import { DAY_NAMES } from "./closureShapes";
import { CYCLES } from "./RotationSetup";
import type { Cycle } from "./RotationSetup";

/** A small calendar button beside the closure fields that opens the coming weekends.
 *
 *  The weekends are not on the screen by default: a manager sets the hours
 *  and the group count, and asks to see who closes when only if they want
 *  to. Nothing is derived in the browser — which group closes and from when
 *  is arithmetic `bl/rotation` owns, asked once per opening (and again while
 *  open, a moment after the fields change), so the list cannot disagree with
 *  the board. */
export function RotationPreviewButton({ cycle, workplace, shifts }: {
  cycle: Cycle;
  workplace: Record<string, unknown>;
  shifts: Record<string, unknown>[];
}) {
  const [open, setOpen] = useState(false);
  const [weekends, setWeekends] = useState<RotationWeekend[] | undefined>();
  const [error, setError] = useState("");
  const [answered, setAnswered] = useState("");
  const panel = useId();
  const box = useRef<HTMLDivElement>(null);
  const key = JSON.stringify([workplace, shifts, cycle]);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      const [place, rows, pattern] = JSON.parse(key) as [Record<string, unknown>, Record<string, unknown>[], Cycle];
      rotationPreview({ workplace: place, shifts: rows, weeks: 8 }, controller.signal)
        .then((result) => { setWeekends(result.cycles[pattern]); setError(result.error); })
        .catch((reason) => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "התצוגה אינה זמינה"); })
        .finally(() => { if (!controller.signal.aborted) setAnswered(key); });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [open, key]);

  // Escape or a click elsewhere closes it, as any popover does.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    const onDown = (event: PointerEvent) => { if (box.current && !box.current.contains(event.target as Node)) setOpen(false); };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onDown);
    return () => { document.removeEventListener("keydown", onKey); document.removeEventListener("pointerdown", onDown); };
  }, [open]);

  const loading = answered !== key;
  const { label } = CYCLES[cycle];

  return (
    <div className="rotation-peek" ref={box}>
      <button
        type="button"
        className={`rotation-peek-button${open ? " is-open" : ""}`}
        aria-expanded={open}
        aria-controls={panel}
        aria-label={`הצגת ה${label} בסופ״שים הקרובים`}
        title={`מי סוגר בכל סופ״ש — ${label}`}
        onClick={() => setOpen((value) => !value)}
      ><CalendarDays size={18} aria-hidden="true" /></button>
      {open ? (
        <div id={panel} className="rotation-peek-panel" role="dialog" aria-label={`ה${label} בסופ״שים הקרובים`}>
          <header>
            <strong>מי סוגר בסופ״שים הקרובים</strong>
            <button type="button" className="icon-button subtle" aria-label="סגירה" onClick={() => setOpen(false)}><X size={15} /></button>
          </header>
          {error ? <p className="rotation-derived-note is-warning" role="status">{error}</p> : null}
          {weekends?.length ? (
            <ol className="rotation-preview" aria-busy={loading}>
              {weekends.map((weekend) => (
                <li key={weekend.saturday} className={`is-${weekend.kind}`}>
                  <span className="rotation-preview-date">שבת {shortDate(weekend.saturday)}</span>
                  <strong>{weekend.label}׳</strong>
                  <span className="rotation-preview-span">{span(weekend)}</span>
                  {weekend.kind === "exception" ? <em>{weekend.note || "חריג"}</em> : null}
                </li>
              ))}
            </ol>
          ) : !error ? <p className="rotation-hint">{loading ? "מחשבים את הסופ״שים הקרובים…" : "אין סופ״שים להצגה."}</p> : null}
        </div>
      ) : null}
    </div>
  );
}

function span(weekend: RotationWeekend): string {
  const from = `${day(weekend.start_date)} ${shortDate(weekend.start_date)}${weekend.start_time ? ` ${weekend.start_time}` : ""}`;
  const handover = weekend.handover_shifts.length ? ` (אחרי ${weekend.handover_shifts.join(" / ")})` : "";
  const until = `${day(weekend.end_date)} ${shortDate(weekend.end_date)}${weekend.end_time ? ` ${weekend.end_time}` : handover}`;
  return `${from} ← ${until}`;
}

function day(iso: string): string {
  const index = new Date(`${iso}T00:00:00Z`).getUTCDay();
  return Number.isNaN(index) ? "" : DAY_NAMES[index];
}
