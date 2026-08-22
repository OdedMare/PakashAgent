"use client";

import {
  AlertTriangle,
  BarChart3,
  CalendarDays,
  Clock,
  Moon,
  Scale,
} from "lucide-react";

import type { Fairness, PersonalSummary } from "@/types";

/** The employee's hours, broken down so the total is legible.
 *
 *  Every number here comes from `bl/audit.py` — the same arithmetic the
 *  manager's warnings are computed from, never a second calculation in the
 *  browser. An employee reading 38 where their manager reads 41 would be
 *  worse than showing nothing, so the totals are rendered, not derived.
 *
 *  The on-call split is given its own tile because it is the number that
 *  looks like a mistake when it is right: an eight-hour on-call counting as
 *  four is the `hour_weight` the interview collected doing its job (D9). */
export function HoursPanel({
  summary,
  fairness,
}: {
  summary: PersonalSummary;
  fairness: Fairness;
}) {
  const mine = fairness.people.find(
    (row) => row.employee === summary.employee,
  );

  return (
    <section
      className="employee-panel employee-analytics"
      aria-labelledby="personal-analytics-title"
    >
      <header className="employee-analytics-head">
        <div>
          <span>התקופה הנוכחית</span>
          <h1 id="personal-analytics-title">הנתונים שלי</h1>
          <p>השעות, סוגי המשמרות וההשוואה לצוות — רק הנתונים שלך.</p>
        </div>
        <span className="employee-analytics-mark" aria-hidden="true">
          <BarChart3 size={20} />
        </span>
      </header>

      <div className="employee-stats">
        <Stat
          icon={<Clock size={15} />}
          label="סך השעות"
          value={formatHours(summary.total_hours)}
          note="לפי משקל השעות שהוגדר לכל משמרת"
        />
        <Stat
          icon={<BarChart3 size={15} />}
          label="משמרות"
          value={String(summary.shift_count)}
          note="שיבוצים בתקופה הזו"
        />
        <Stat
          icon={<CalendarDays size={15} />}
          label="ימי עבודה"
          value={String(summary.days_worked)}
          note="יום עם שתי משמרות נספר פעם אחת"
        />
        {/* Only when there is on-call to explain. Showing a zeroed tile to a
            workplace with no on-call shift would be noise about a concept
            that does not apply to them. */}
        {summary.on_call_count > 0 ? (
          <Stat
            icon={<Moon size={15} />}
            label="מתוכן כוננות"
            value={formatHours(summary.on_call_hours)}
            note={`${summary.on_call_count} כוננויות · עבודה בפועל ${formatHours(
              summary.worked_hours,
            )}`}
          />
        ) : null}
        {mine ? (
          <Stat
            icon={<Scale size={15} />}
            label="מול ממוצע הצוות"
            value={formatDelta(mine.delta)}
            note={`ממוצע הצוות ${formatHours(fairness.average_hours)}`}
          />
        ) : null}
      </div>

      <div className="employee-chart-grid">
        <WeeklyChart weeks={summary.by_week} />
        <ShiftChart shifts={summary.by_shift} />
        {mine ? (
          <TeamComparison
            mine={mine.hours}
            average={fairness.average_hours}
          />
        ) : null}
      </div>

      {/* Only warnings naming this person reach here — the backend filters
          them, and team-wide ones stay the manager's. Advisory, exactly as
          everywhere else: this is a thing to look at, not a blocked state. */}
      {summary.warnings.length > 0 ? (
        <div className="employee-warnings">
          <h2>
            <AlertTriangle size={14} /> שווה לשים לב
          </h2>
          <ul>
            {summary.warnings.map((warning, index) => (
              <li key={`${warning.code}-${index}`} className={warning.severity}>
                {warning.message}
              </li>
            ))}
          </ul>
          <p className="employee-note">
            ההתראות האלה מוצגות לידיעה בלבד — הסידור עצמו נקבע מול המנהל.
          </p>
        </div>
      ) : null}

      <p className="employee-analytics-footnote">
        הנתונים מחושבים מאותו מקור שמציג למנהל את עומס הצוות. הם מתארים את
        התקופה ואינם ציון אישי.
      </p>
    </section>
  );
}

function WeeklyChart({
  weeks,
}: {
  weeks: PersonalSummary["by_week"];
}) {
  if (!weeks.length) return null;
  const peak = Math.max(...weeks.map((week) => week.hours), 1);

  return (
    <figure className="employee-chart employee-week-chart">
      <figcaption>
        <strong>שעות לפי שבוע</strong>
        <span>העמודה מציגה שעות משוקללות</span>
      </figcaption>
      <div className="employee-week-bars" role="list">
        {weeks.map((week) => (
          <div
            className="employee-week-bar"
            key={week.week}
            role="listitem"
            aria-label={`${formatWeek(week.week)}: ${formatHours(week.hours)}`}
          >
            <span>{formatHours(week.hours)}</span>
            <div>
              <i style={{ height: `${(week.hours / peak) * 100}%` }} />
            </div>
            <small>{formatWeek(week.week)}</small>
          </div>
        ))}
      </div>
    </figure>
  );
}

function ShiftChart({
  shifts,
}: {
  shifts: PersonalSummary["by_shift"];
}) {
  if (!shifts.length) return null;
  const peak = Math.max(...shifts.map((shift) => shift.hours), 1);

  return (
    <figure className="employee-chart">
      <figcaption>
        <strong>חלוקה לפי משמרת</strong>
        <span>כמה פעמים וכמה שעות מכל סוג</span>
      </figcaption>
      <ul className="employee-shift-bars">
        {shifts.map((shift) => (
          <li key={shift.shift}>
            <span>{shift.shift}</span>
            <span className="employee-shift-track" aria-hidden="true">
              <i style={{ width: `${(shift.hours / peak) * 100}%` }} />
            </span>
            <strong>{formatHours(shift.hours)}</strong>
            <small>{shift.count}×</small>
          </li>
        ))}
      </ul>
    </figure>
  );
}

function TeamComparison({ mine, average }: { mine: number; average: number }) {
  const peak = Math.max(mine, average, 1);

  return (
    <figure className="employee-chart employee-comparison">
      <figcaption>
        <strong>מול ממוצע הצוות</strong>
        <span>השוואה בלבד, בלי יעד או מכסה</span>
      </figcaption>
      <div className="employee-comparison-row">
        <span>אני</span>
        <span className="employee-shift-track">
          <i style={{ width: `${(mine / peak) * 100}%` }} />
        </span>
        <strong>{formatHours(mine)}</strong>
      </div>
      <div className="employee-comparison-row is-average">
        <span>ממוצע</span>
        <span className="employee-shift-track">
          <i style={{ width: `${(average / peak) * 100}%` }} />
        </span>
        <strong>{formatHours(average)}</strong>
      </div>
    </figure>
  );
}

function Stat({
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
    <div className="employee-stat">
      <span className="stat-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      <span className="stat-note">{note}</span>
    </div>
  );
}

/** Trailing `.0` dropped: "38 שעות" reads better than "38.0 שעות", and the
 *  half-hours that matter still show. */
function formatHours(hours: number): string {
  const rounded = Math.round(hours * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} ש׳`;
}

function formatDelta(delta: number): string {
  const rounded = Math.round(delta * 10) / 10;
  if (rounded === 0) return "בדיוק בממוצע";
  const sign = rounded > 0 ? "+" : "−";
  return `${sign}${Math.abs(rounded)} ש׳`;
}

function formatWeek(week: string): string {
  const match = /^(\d{4})-W(\d{2})$/.exec(week);
  return match ? `שבוע ${Number(match[2])} · ${match[1]}` : week;
}
