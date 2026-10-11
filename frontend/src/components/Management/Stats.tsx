"use client";

import {
  AlertTriangle,
  BarChart3,
  CalendarRange,
  ChevronDown,
  ClipboardList,
  Moon,
  Repeat,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";

import type { ManagementOverview, ShiftStats, WarningCount } from "@/types";
import { localToday } from "@/components/Board/dates";
import { rotationLabel } from "@/components/Board/person";
import { displayDate } from "@/components/DateInput";

import { StatsFilter } from "./StatsFilter";
import type { DateRange, StatsFilter as Filter } from "./statsRange";
import { rangeOf } from "./statsRange";
import { useStats } from "./useStats";


/** The schedule in numbers: coverage, shifts per person, and what collides.
 *
 *  **Every figure here is rendered, never computed.** The arithmetic is
 *  `bl/audit.py`'s — the same code the warnings under the calendar come from
 *  — for the reason `HoursPanel` states on the employee's side: a chart drawn
 *  from a second implementation of the count would eventually disagree with
 *  the warning printed beside it, and nobody looking at the two can tell
 *  which one is lying. If a number is wanted that the backend does not send,
 *  the fix is a field on `shift_stats`, not a reduce in this file.
 *
 *  That holds for the filter too. A day, a month or one person is a question
 *  put to `/api/schedule/stats`, not a `.filter()` over the rows on screen —
 *  the rows on screen are one period, and a month is several.
 *
 *  **Load is counted in shifts.** Hours are weighted — an on-call night may
 *  count as half — so two people on equal hours can have stood a very
 *  different number of shifts, and the number a manager balances a team by
 *  is how many times each person was put on, and how many of those were
 *  nights.
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
  overview,
  expanded = false,
}: {
  overview: ManagementOverview;
  /** A dedicated analytics page shows the full report immediately. The
   *  compact drawer keeps the existing disclosure so it does not bury the
   *  schedule tools under charts. */
  expanded?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const showCharts = expanded || open;

  const base = overview.stats;
  const today = overview.today || localToday();
  const startsOn = overview.schedule?.starts_on ?? "";
  const endsOn = overview.schedule?.ends_on ?? "";
  const period = useMemo<DateRange | null>(
    () => (startsOn && endsOn ? { start: startsOn, end: endsOn } : null),
    [startsOn, endsOn],
  );
  const built = overview.periods.length > 0;

  // The manager's own choice, or nothing yet. Kept apart from the default so
  // an untouched panel keeps following the period on the board as it changes.
  const [chosen, setChosen] = useState<Filter | null>(null);
  const filter = currentFilter(chosen, today, Boolean(period));
  const range = rangeOf(filter, period);
  // The overview already answered "the current period, everybody".
  const filtered = filter.span !== "period" || Boolean(filter.employee);
  const { stats, loading, error } = useStats(
    base,
    range,
    filter.employee,
    filtered && built,
  );

  const people = useMemo(
    () => rosterNames(overview.employees, base, filter.employee),
    [overview.employees, base, filter.employee],
  );

  // Nothing built anywhere, so there is nothing to filter either. An empty
  // period returns well-formed zeros rather than nothing, so this is a
  // deliberate check and not a null guard.
  if (!built && !base.total_shifts && !base.coverage.required) {
    return expanded ? (
      <section
        className="stats stats-page stats-empty"
        aria-label="נתוני התקופה"
      >
        <BarChart3 size={20} aria-hidden="true" />
        <div>
          <h2>הנתונים יופיעו אחרי השיבוץ הראשון</h2>
          <p>כשהתקופה תתמלא, יוצגו כאן איוש, משמרות לכל חייל/ת והתנגשויות.</p>
        </div>
      </section>
    ) : null;
  }

  const nothingHere = stats
    ? !stats.total_shifts && !stats.coverage.required
    : false;

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
            <p>
              איוש, משמרות לכל חייל/ת והתנגשויות — מאותו חישוב שמזין את
              ההתראות.
            </p>
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

      {/* Above the tiles, not inside the disclosure: the tiles are filtered
          too, and numbers narrowed by a control the manager cannot see are
          numbers they will misread. */}
      <StatsFilter
        filter={filter}
        range={range}
        today={today}
        people={people}
        hasPeriod={Boolean(period)}
        isDefault={chosen === null}
        onChange={setChosen}
        onReset={() => setChosen(null)}
      />

      <div
        className={loading ? "stats-body is-loading" : "stats-body"}
        aria-busy={loading}
      >
        {error ? (
          <p className="stats-notice is-error" role="alert">
            {error}
          </p>
        ) : !stats ? (
          <p className="stats-notice">
            {loading
              ? "טוען את הנתונים…"
              : "בחרו תאריך התחלה ותאריך סיום כדי לראות את הנתונים."}
          </p>
        ) : nothingHere ? (
          <p className="stats-notice">לא נבנה סידור בתאריכים האלה.</p>
        ) : (
          <>
            {/* The headline numbers stay visible whether or not the charts
                are open: they are the glance, and the charts are the
                follow-up. */}
            <div className="stats-tiles">
              {filter.employee ? (
                <PersonTiles stats={stats} name={filter.employee} />
              ) : (
                <TeamTiles stats={stats} />
              )}
              <ConflictTiles stats={stats} />
            </div>

            {showCharts ? (
              <div className="stats-charts">
                <DayChart days={stats.by_day} />
                <EmployeeChart people={stats.by_employee} />
                <ShiftChart shifts={stats.by_shift} />
                <WarningChart counts={stats.warning_counts} />
                {/* Said out loud, in the same voice the warnings use. A wall
                    of charts invites being read as a scorecard; this is the
                    line that says it is not one. */}
                <p className="stats-footnote">
                  המספרים כאן הם תיאור של התקופה, לא ציון — הם מחושבים מאותו
                  חישוב שממנו נגזרות ההתראות, ואינם חוסמים שום פעולה.
                </p>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}

/** The filter in force: the manager's choice, or the default while they
 *  have made none.
 *
 *  The default is the stored period when there is one — the numbers the
 *  overview already carries — and this week otherwise. A choice of "התקופה"
 *  outliving the period it meant (the period was deleted) falls back the
 *  same way, keeping the person, rather than leaving the panel filtered to
 *  nothing. */
function currentFilter(
  chosen: Filter | null,
  today: string,
  hasPeriod: boolean,
): Filter {
  if (chosen && (chosen.span !== "period" || hasPeriod)) return chosen;
  return {
    span: hasPeriod ? "period" : "week",
    focus: today,
    from: "",
    to: "",
    employee: chosen?.employee ?? "",
  };
}

/** Everyone the filter can name, alphabetically.
 *
 *  The roster first, then anybody the current period still shows who has
 *  since left it — their past shifts are exactly what a manager looks up —
 *  and the person already chosen, so the select can never be showing a name
 *  it does not list. */
function rosterNames(
  employees: Record<string, unknown>[],
  base: ShiftStats,
  chosen: string,
): string[] {
  const names = new Set<string>();
  for (const row of employees) {
    if (typeof row.name === "string" && row.name.trim()) {
      names.add(row.name.trim());
    }
  }
  for (const row of base.by_employee) names.add(row.employee);
  if (chosen) names.add(chosen);
  return [...names].sort((a, b) => a.localeCompare(b, "he"));
}

/** The whole team's glance: how covered, how many shifts, by how many. */
function TeamTiles({ stats }: { stats: ShiftStats }) {
  return (
    <>
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
        icon={<ClipboardList size={15} />}
        label="משמרות"
        value={String(stats.total_shifts)}
        note={
          stats.total_shifts
            ? `${stats.total_nights} מתוכן לילה`
            : "אין שיבוצים"
        }
      />
      <Tile
        icon={<Users size={15} />}
        label="חיילים בסידור"
        value={String(stats.people_working)}
        note={`מתוך ${stats.by_employee.length} ברשימה`}
      />
    </>
  );
}

/** One person's glance: their rotation, their shifts, their nights.
 *
 *  Coverage has no tile here on purpose. A seat belongs to the slot, and
 *  one person's share of the week's seats would read as a week barely
 *  covered to a manager who filled every one of them. */
function PersonTiles({ stats, name }: { stats: ShiftStats; name: string }) {
  const person = stats.by_employee.find((row) => row.employee === name);
  const rotation = rotationLabel(person?.exit_pattern, person?.rotation_group);
  const days = person?.days ?? 0;

  return (
    <>
      <Tile
        icon={<Repeat size={15} />}
        label="סבב"
        value={rotation || "—"}
        note={rotation ? "לפי רשימת הצוות" : "לא נרשם סבב"}
      />
      <Tile
        icon={<ClipboardList size={15} />}
        label="משמרות"
        value={String(stats.total_shifts)}
        note={stats.total_shifts ? `ב־${days} ימים` : "אין שיבוצים"}
      />
      <Tile
        icon={<Moon size={15} />}
        label="לילות"
        value={String(stats.total_nights)}
        note={`מתוך ${stats.total_shifts} משמרות`}
      />
    </>
  );
}

/** What collides, for the team or for the one person chosen.
 *
 *  Two tiles because they are two different facts. "התנגשויות" is every
 *  finding the manager has to look at — the number on the board's own tile.
 *  "אילוצים" is how much the schedule was working around, including the
 *  constraints it respected, which raise no warning and so appear nowhere
 *  else. */
function ConflictTiles({ stats }: { stats: ShiftStats }) {
  const pressure = stats.constraint_pressure;

  return (
    <>
      <Tile
        icon={<AlertTriangle size={15} />}
        label="התנגשויות"
        value={String(stats.conflicts)}
        note={stats.conflicts ? "פירוט לפי סוג בתרשימים" : "לא נמצאו"}
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
    </>
  );
}

/** Headcount per day across the period.
 *
 *  Days with nobody on them arrive as zeros and are drawn as empty columns
 *  rather than skipped — the gap is the finding. */
function DayChart({ days }: { days: ShiftStats["by_day"] }) {
  // One day is a single column with nothing to compare it against; the
  // tiles above already say everything it would.
  if (days.length < 2) return null;
  const peak = Math.max(...days.map((day) => day.count), 1);
  // Past a fortnight the columns are too narrow to carry a figure each. The
  // count moves to the hover and the axis marks only where a week begins.
  const dense = days.length > 14;

  return (
    <figure className="stats-chart">
      <figcaption>שיבוצים לפי יום</figcaption>
      <div className={dense ? "day-bars is-dense" : "day-bars"} role="list">
        {days.map((day) => (
          <div
            className="day-bar"
            key={day.date}
            role="listitem"
            title={`${day.weekday} ${displayDate(day.date)} · ${
              day.count
            } שיבוצים · ${formatHours(day.hours)}`}
          >
            <span className="day-bar-value">
              {dense ? "" : day.count || ""}
            </span>
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
            <span className="day-bar-label">
              {dense ? weekMark(day) : shortWeekday(day.weekday)}
            </span>
          </div>
        ))}
      </div>
    </figure>
  );
}

/** Shifts per person, most first, with the nights among them.
 *
 *  Everyone on the roster is drawn, including people at zero. That bar is
 *  the most informative one on the chart — it is the person the manager is
 *  looking for — and dropping it is what would make this decorative.
 *
 *  The night share is stacked inside the bar rather than drawn as a second
 *  one: "five shifts, two of them nights" is one fact about one person, and
 *  two bars would invite comparing a count against its own part. Each name
 *  carries its rotation in the words the board's cards use. */
function EmployeeChart({ people }: { people: ShiftStats["by_employee"] }) {
  if (!people.length) return null;
  const peak = Math.max(...people.map((row) => row.shifts), 1);

  return (
    <figure className="stats-chart">
      <figcaption>
        משמרות לפי חייל/ת
        <span className="stats-legend">
          <span className="stats-legend-swatch is-night" aria-hidden="true" />
          מתוכן לילה
        </span>
      </figcaption>
      <ul className="load-rows">
        {people.map((row) => {
          const rotation = rotationLabel(row.exit_pattern, row.rotation_group);
          return (
            <li
              className="load-row is-person"
              key={row.employee}
              title={personSummary(row)}
            >
              <span className="load-name">
                <span className="load-person">{row.employee}</span>
                {rotation ? (
                  <span className="load-rotation">{rotation}</span>
                ) : null}
              </span>
              <span className="load-track">
                <span
                  className={row.shifts ? "load-fill" : "load-fill is-empty"}
                  style={{ width: `${(row.shifts / peak) * 100}%` }}
                >
                  {row.nights ? (
                    <span
                      className="load-fill-night"
                      style={{
                        width: `${(row.nights / Math.max(row.shifts, 1)) * 100}%`,
                      }}
                    />
                  ) : null}
                </span>
              </span>
              <span className="load-value">
                {row.shifts ? row.shifts : "—"}
                {row.nights ? (
                  <span className="load-night"> · {row.nights} לילה</span>
                ) : null}
                {row.conflicts ? (
                  <span className="load-conflict">
                    <AlertTriangle size={11} aria-hidden="true" />
                    {row.conflicts}
                    <span className="visually-hidden"> התנגשויות</span>
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
    </figure>
  );
}

/** One person's row in a sentence, for the hover and for a screen reader.
 *  Hours live here and not on the row: they are still true and still the
 *  audit's, but they are no longer what the chart is drawn in. */
function personSummary(row: ShiftStats["by_employee"][number]): string {
  const parts = [
    `${row.shifts} משמרות`,
    `${row.nights} מתוכן לילה`,
    `${row.days} ימים`,
    formatHours(row.hours),
  ];
  if (row.on_call) parts.push(`${row.on_call} כוננויות`);
  if (row.conflicts) parts.push(`${row.conflicts} התנגשויות`);
  return `${row.employee} · ${parts.join(" · ")}`;
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
  missing_role: "תפקיד חסר",
  missing_commander: "אין אחראי משמרת",
  cross_rotation: "שיבוץ מחוץ לסבב",
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

/** The axis mark for one column of a long span: the day of the month where
 *  a week begins, nothing elsewhere. The weekday is the backend's own word
 *  for the date, so this reads it rather than recomputing it. */
function weekMark(day: ShiftStats["by_day"][number]): string {
  return day.weekday === "יום ראשון" ? String(Number(day.date.slice(8))) : "";
}

/** Trailing `.0` dropped, matching `HoursPanel` — "38 ש׳" over "38.0 ש׳". */
function formatHours(hours: number): string {
  return `${formatNumber(hours)} ש׳`;
}

function formatNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}
