"use client";

import { shortDate } from "@/components/DateInput";
import type { RotationWeekend } from "@/types";

import { DAY_NAMES } from "./closureShapes";

/** The coming weekends of one cycle, as the server will build them.
 *
 *  Nothing here is derived in the browser: which group closes and from when
 *  is arithmetic `bl/rotation` owns, and the strip only renders its answer,
 *  so the setup screen cannot disagree with the board. */
export function RotationPreview({ weekends, loading }: { weekends: RotationWeekend[] | undefined; loading: boolean }) {
  if (!weekends?.length) {
    return <p className="rotation-empty">{loading ? "מחשבים את הסופ״שים הקרובים…" : "בחרו תאריך עוגן כדי לראות כאן מי סוגר בכל סופ״ש."}</p>;
  }
  return (
    <ol className="rotation-preview" aria-label="הסופ״שים הקרובים">
      {weekends.map((weekend) => (
        <li key={weekend.saturday} className={`is-${weekend.kind}`}>
          <span className="rotation-preview-date">שבת {shortDate(weekend.saturday)}</span>
          <strong>{weekend.label}׳</strong>
          <span className="rotation-preview-span">{span(weekend)}</span>
          {weekend.kind === "exception" ? <em>{weekend.note || "חריג"}</em> : null}
        </li>
      ))}
    </ol>
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
