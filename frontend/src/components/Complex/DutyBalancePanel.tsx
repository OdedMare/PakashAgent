"use client";

import { AlertTriangle, Scale, X } from "lucide-react";
import { useEffect, useState } from "react";

import { displayDate } from "@/components/DateInput";
import { dutyBalance } from "@/services/api";
import type { DutyBalance } from "@/types";

type Span = "screen" | "weeks";

/** How the duties fell across the מכלול: the spread, each משמרת's average,
 *  each kind's seats against what it asked for, and every soldier -- most
 *  load first, zeros included, since the soldier at zero is the one a fair
 *  fill reaches for next. A report, never a quota (D3). */
export function DutyBalancePanel({
  start, end, today, onClose,
}: {
  start: string;
  end: string;
  today: string;
  onClose: () => void;
}) {
  const [span, setSpan] = useState<Span>("weeks");
  const [data, setData] = useState<DutyBalance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const range = span === "screen" ? { start, end } : { start: weeksBefore(today, 8), end: today };

  useEffect(() => {
    let cancelled = false;
    dutyBalance(range.start, range.end)
      .then((next) => { if (!cancelled) { setData(next); setError(null); } })
      .catch((reason) => { if (!cancelled) setError(reason instanceof Error ? reason.message : "שגיאה"); });
    return () => { cancelled = true; };
  }, [range.start, range.end]);

  const peak = Math.max(1, ...(data?.people ?? []).map((row) => row.load));

  return (
    <section className="duty-panel duty-balance" aria-label="מאזן התורנויות">
      <button type="button" className="icon-button subtle duty-panel-close" onClick={onClose}
        aria-label="סגירה"><X size={15} /></button>
      <h3><Scale size={15} /> מאזן התורנויות</h3>
      <div className="board-views" role="group" aria-label="טווח">
        <button type="button" className={`board-view${span === "weeks" ? " is-on" : ""}`}
          aria-pressed={span === "weeks"} onClick={() => setSpan("weeks")}>8 השבועות האחרונים</button>
        <button type="button" className={`board-view${span === "screen" ? " is-on" : ""}`}
          aria-pressed={span === "screen"} onClick={() => setSpan("screen")}>הטווח שעל המסך</button>
      </div>
      {error ? <div className="error" role="alert"><AlertTriangle size={16} /><span>{error}</span></div> : null}
      {data ? (
        <>
          <p className="cmd-hint">
            {displayDate(data.start)}–{displayDate(data.end)} · עומס = משמרות + ימי תורנות לפי המשקל שלהן.
          </p>
          <div className="duty-balance-tiles">
            <span><strong>{data.spread.most}</strong> הכי הרבה</span>
            <span><strong>{data.spread.least}</strong> הכי מעט</span>
            <span className={data.spread.gap > 1 ? "is-wide" : ""}><strong>{data.spread.gap}</strong> פער</span>
            {data.teams.map((team) => (
              <span key={team.team_id}><strong>{team.average}</strong> ממוצע ב{team.team_name}</span>
            ))}
          </div>
          {data.types.length ? (
            <ul className="duty-balance-kinds">
              {data.types.map((kind) => (
                <li key={kind.duty_type_id}>
                  {kind.duty}: {kind.filled} מתוך {kind.required} מקומות
                  {kind.filled < kind.required ? <em> · {kind.required - kind.filled} פתוחים</em> : null}
                </li>
              ))}
            </ul>
          ) : null}
          <ul className="load-rows">
            {data.people.map((row) => (
              <li className="load-row is-person" key={`${row.team_id}-${row.employee}`}
                title={`${row.employee} · ${row.team_name} · ${row.duties} תורנויות (${row.weekend_duties} בסופ״ש${row.recorded ? `, ${row.recorded} רישום` : ""}) · ${row.shifts} משמרות`}>
                <span className="load-name">
                  <span className="load-person">{row.employee}</span>
                  <span className="load-rotation">{row.team_name}</span>
                </span>
                <span className={row.duty_load ? "load-track has-duty" : "load-track"}>
                  <span className={row.shifts ? "load-fill" : "load-fill is-empty"}
                    style={{ width: `${(row.shifts / peak) * 100}%` }} />
                  {row.duty_load ? (
                    <span className="load-fill-duty" style={{ width: `${(row.duty_load / peak) * 100}%` }} />
                  ) : null}
                </span>
                <span className="load-value">
                  <span className="load-duty">{row.duties} תורנויות</span> · {row.shifts} משמרות
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function weeksBefore(iso: string, weeks: number): string {
  const day = new Date(`${iso}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() - weeks * 7 + 1);
  return day.toISOString().slice(0, 10);
}
