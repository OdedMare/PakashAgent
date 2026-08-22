"use client";

import {
  BarChart3,
  CalendarRange,
  ChevronDown,
  Clock,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useState } from "react";

import type { ShiftStats, WarningCount } from "@/types";

import { formatDate } from "./Calendar";

/** The period in numbers: coverage, load per day, and load per person.
 *
 *  **Every figure here is rendered, never computed.** The arithmetic is
 *  `bl/audit.py`'s — the same code the warnings under the calendar come from
 *  — for the reason `HoursPanel` states on the employee's side: a chart drawn
 *  from a second implementation of the hours would eventually disagree with
 *  the warning printed beside it, and nobody looking at the two can tell
 *  which one is lying. If a number is wanted that the backend does not send,
 *  the fix is a field on `shift_stats`, not a reduce in this file.
 *
 *  **It reports; it does not grade** ([D3](../../../docs/DECISIONS.md#d3--the-agent-decides-code-only-audits-)).
 *  There is no score, no target, and no pass mark: coverage at 80% is a fact
 *  about the week, not a verdict on it, and nothing here gates publishing.
 *  That is also why the coverage bar is not painted red below some threshold
 *  — a colour that says "bad" is a judgment the audit deliberately does not
 *  make.
 *
 *  Collapsed by default. The calendar is what the manager came for, and a
 *  screenful of charts above it would push the actual schedule below the
 *  fold to answer a question nobody asked yet. */
export function Stats({
  stats,
  expanded = false,
}: {
  stats: ShiftStats;
  /** A dedicated analytics page shows the full report immediately. The
   *  compact drawer keeps the existing disclosure so it does not bury the
   *  schedule tools under charts. */
  expanded?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const showCharts = expanded || open;

  // Nothing built yet. An empty period returns well-formed zeros rather than
  // nothing, so this is a deliberate check and not a null guard.
  if (!stats.total_shifts && !stats.coverage.required) {
    return expanded ? (
      <section
        className="stats stats-page stats-empty"
        aria-label="נתוני התקופה"
      >
        <BarChart3 size={20} aria-hidden="true" />
        <div>
          <h2>הנתונים יופיעו אחרי השיבוץ הראשון</h2>
          <p>כשהתקופה תתמלא, יוצגו כאן איוש, עומס, חלוקה בצוות והתראות.</p>
        </div>
      </section>
    ) : null;
  }

  const pressure = stats.constraint_pressure;

  return (
    <section
      className={`stats${expanded ? " stats-page" : ""}`}
      aria-label="בקרה וסטטיסטיקות"
    >
      <div className="stats-heading">
        <div>
          {expanded ? <span className="stats-eyebrow">תמונת התקופה</span> : null}
          {expanded ? (
            <h2>המספרים שמאחורי הסידור</h2>
          ) : (
            <h3>
              <BarChart3 size={15} /> בקרה על המשמרת
            </h3>
          )}
          {expanded ? (
            <p>איוש, עומס וחלוקה בצוות — מאותו חישוב שמזין את ההתראות.</p>
          ) : null}
        </div>
        {!expanded ? (
          <button
            type="button"
            className="stats-toggle"
            onClick={() => setOpen((value) => !value)}
            aria-expanded={open}
          >
            {open ? "הסתרה" : "הצגה"}
            <ChevronDown
              size={14}
              className={open ? "stats-chevron is-open" : "stats-chevron"}
              aria-hidden="true"
            />
          </button>
        ) : (
          <span className="stats-report-mark" aria-hidden="true">
            <BarChart3 size={20} />
          </span>
        )}
      </div>

      {/* The four headline numbers stay visible whether or not the charts
          are open: they are the glance, and the charts are the follow-up. */}
      <div className="stats-tiles">
        <Tile
          icon={<ShieldCheck size={15} />}
          label="איוש"
          value={`${formatNumber(stats.coverage.percent)}%`}
          note={
            stats.coverage.required
              ? `${stats.coverage.assigned} מתוך ${stats.coverage.required} מקומות`
              : "לא הוגדר תקן איוש"
          }
        />
        <Tile
          icon={<Clock size={15} />}
          label="סך השעות"
          value={formatHours(stats.total_hours)}
          note={`${stats.total_shifts} שיבוצים`}
        />
        <Tile
          icon={<Users size={15} />}
          label="עובדים בסידור"
          value={String(stats.people_working)}
          note={`מתוך ${stats.by_employee.length} ברשימה`}
        />
        <Tile
          icon={<CalendarRange size={15} />}
          label="אילוצים"
          value={String(pressure.blocked)}
          note={
            pressure.blocked
              ? `${pressure.honored} כובדו · ${pressure.conflicts} נעקפו`
              : "לא נרשמו אילוצים"
          }
        />
      </div>

      {showCharts ? (
        <div className="stats-charts">
          <DayChart days={stats.by_day} />
          <EmployeeChart people={stats.by_employee} />
          <ShiftChart shifts={stats.by_shift} />
          <WarningChart counts={stats.warning_counts} />
          {/* Said out loud, in the same voice the warnings use. A wall of
              charts invites being read as a scorecard; this is the line
              that says it is not one. */}
          <p className="stats-footnote">
            המספרים כאן הם תיאור של התקופה, לא ציון — הם מחושבים מאותו חישוב
            שממנו נגזרות ההתראות, ואינם חוסמים שום פעולה.
          </p>
        </div>
      ) : null}
    </section>
  );
}

/** Headcount per day across the period.
 *
 *  Days with nobody on them arrive as zeros and are drawn as empty columns
 *  rather than skipped — the gap is the finding. */
function DayChart({ days }: { days: ShiftStats["by_day"] }) {
  if (!days.length) return null;
  const peak = Math.max(...days.map((day) => day.count), 1);

  return (
    <figure className="stats-chart">
      <figcaption>שיבוצים לפי יום</figcaption>
      <div className="day-bars" role="list">
        {days.map((day) => (
          <div
            className="day-bar"
            key={day.date}
            role="listitem"
            title={`${day.weekday} ${formatDate(day.date)} · ${
              day.count
            } שיבוצים · ${formatHours(day.hours)}`}
          >
            <span className="day-bar-value">{day.count || ""}</span>
            <div className="day-bar-track">
              {/* Height carries the count; the on-call slice is stacked
                  inside it so a day that looks staffed but is mostly
                  standby reads differently from one that is not. */}
              <div
                className="day-bar-fill"
                style={{ height: `${(day.count / peak) * 100}%` }}
              >
                {day.on_call ? (
                  <div
                    className="day-bar-oncall"
                    style={{
                      height: `${(day.on_call / Math.max(day.count, 1)) * 100}%`,
                    }}
                  />
                ) : null}
              </div>
            </div>
            <span className="day-bar-label">{shortWeekday(day.weekday)}</span>
          </div>
        ))}
      </div>
    </figure>
  );
}

/** Hours per person, heaviest first.
 *
 *  Everyone on the roster is drawn, including people at zero. That bar is
 *  the most informative one on the chart — it is the person the manager is
 *  looking for — and dropping it is what would make this decorative. */
function EmployeeChart({ people }: { people: ShiftStats["by_employee"] }) {
  if (!people.length) return null;
  const peak = Math.max(...people.map((row) => row.hours), 1);

  return (
    <figure className="stats-chart">
      <figcaption>שעות לפי עובד</figcaption>
      <ul className="load-rows">
        {people.map((row) => (
          <li className="load-row" key={row.employee}>
            <span className="load-name">{row.employee}</span>
            <span className="load-track">
              <span
                className={row.hours ? "load-fill" : "load-fill is-empty"}
                style={{ width: `${(row.hours / peak) * 100}%` }}
              />
            </span>
            <span className="load-value">
              {row.hours ? formatHours(row.hours) : "—"}
              {row.on_call ? (
                <span className="load-oncall" title="מתוכן כוננויות">
                  {" "}
                  ({row.on_call} כ׳)
                </span>
              ) : null}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Load per shift name, in the workplace's own vocabulary (D9).
 *
 *  Shift names are data, never literals here — this component has no idea
 *  what shifts exist and must not acquire one. */
function ShiftChart({ shifts }: { shifts: ShiftStats["by_shift"] }) {
  if (!shifts.length) return null;
  const peak = Math.max(...shifts.map((row) => row.count), 1);

  return (
    <figure className="stats-chart">
      <figcaption>שיבוצים לפי משמרת</figcaption>
      <ul className="load-rows">
        {shifts.map((row) => (
          <li className="load-row" key={row.shift}>
            <span className="load-name">
              {row.shift}
              {row.is_on_call ? (
                <span className="load-tag">כוננות</span>
              ) : null}
            </span>
            <span className="load-track">
              <span
                className={
                  row.is_on_call ? "load-fill is-oncall" : "load-fill"
                }
                style={{ width: `${(row.count / peak) * 100}%` }}
              />
            </span>
            <span className="load-value">
              {row.count ? `${row.count}×` : "—"}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Audit findings grouped by kind.
 *
 *  A count of each, deliberately not summed into a total: six overstaffing
 *  notices are not "worse" than one double-booking, and a single number
 *  would imply an ordering the audit does not assert. */
function WarningChart({ counts }: { counts: WarningCount[] }) {
  if (!counts.length) return null;

  return (
    <figure className="stats-chart">
      <figcaption>התראות לפי סוג</figcaption>
      <ul className="warning-counts">
        {counts.map((row) => (
          <li key={row.code} className={row.severity}>
            <span className="warning-count-label">
              {WARNING_LABELS[row.code] ?? row.code}
            </span>
            <span className="warning-count-value">{row.count}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

function Tile({
  icon,
  label,
  value,
  note,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="stats-tile">
      <span className="stat-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <span className="stat-note">{note}</span>
    </div>
  );
}

/** Hebrew for the audit's codes.
 *
 *  A code with no entry renders as itself rather than being hidden: a new
 *  check added to `audit.py` must show up here without a frontend change,
 *  which is the reason the codes are strings and not an enum. */
const WARNING_LABELS: Record<string, string> = {
  over_hours: "חריגה בשעות",
  consecutive: "ימים ברצף",
  short_rest: "מנוחה קצרה",
  double_booked: "שיבוץ כפול",
  unavailable: "שיבוץ בניגוד לאילוץ",
  unfilled: "משמרת לא מאוישת",
  overstaffed: "איוש עודף",
};

/** "יום שני" → "ב׳". Falls back to the full name for anything unexpected,
 *  since the weekday is data from the backend rather than a fixed set here. */
function shortWeekday(weekday: string): string {
  const letters: Record<string, string> = {
    "יום ראשון": "א׳",
    "יום שני": "ב׳",
    "יום שלישי": "ג׳",
    "יום רביעי": "ד׳",
    "יום חמישי": "ה׳",
    "יום שישי": "ו׳",
    שבת: "ש׳",
  };
  return letters[weekday] ?? weekday;
}

/** Trailing `.0` dropped, matching `HoursPanel` — "38 ש׳" over "38.0 ש׳". */
function formatHours(hours: number): string {
  return `${formatNumber(hours)} ש׳`;
}

function formatNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}
