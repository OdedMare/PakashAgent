"use client";

import {
  ArrowLeftRight,
  BellRing,
  CalendarDays,
  CalendarClock,
  Check,
  ClipboardList,
  LayoutGrid,
  LogOut,
  Moon,
  Sun,
  UserCircle,
} from "lucide-react";
import { useState } from "react";

import { useTheme } from "@/components/Interview/useTheme";
import { Calendar } from "@/components/Management/Calendar";
import type { EmployeeView } from "@/types";

import { ConstraintForm } from "./ConstraintForm";
import { HoursPanel } from "./HoursPanel";
import { IdentityGate } from "./IdentityGate";
import { SwapPanel } from "./SwapPanel";
import { useEmployee } from "./useEmployee";

/** The employee's personal area.
 *
 *  What [D14](../../../../docs/DECISIONS.md) added, and the boundary of what
 *  it added: this screen shows one person their own hours, their own shifts
 *  and their own warnings, and lets them **ask** not to be scheduled. It has
 *  no control that edits a schedule — the calendar below is the same
 *  `readOnly` grid the team view renders, taking no `onDrop`, because the
 *  manager remains the sole decider.
 *
 *  Everything shown is scoped server-side by the name in the signed cookie.
 *  There is no name parameter anywhere in this component tree, which is what
 *  keeps one employee out of another's hours and stated reasons. */
export function Employee({ onLeave }: { onLeave?: () => void }) {
  const { theme, toggle } = useTheme();
  const state = useEmployee();
  const { view } = state;
  const [section, setSection] = useState<EmployeeSection>("mine");

  // Not asked yet. Rendering the gate here would flash a claim screen at
  // someone who is already signed in.
  if (view === undefined) {
    return <div className="workspace-gate" aria-busy="true" />;
  }

  if (view === null) {
    return (
      <IdentityGate
        roster={state.roster}
        busy={state.busy}
        error={state.error}
        onClaim={state.claim}
        onLogin={state.login}
        onDismissError={state.clearError}
      />
    );
  }

  const shiftNames = readShiftNames(view.shifts);

  return (
    <div className="interview">
      <header className="interview-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <UserCircle size={17} />
          </span>
          <span>
            {view.employee}
            <span className="brand-sub"> · האזור שלי</span>
          </span>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="icon-button"
            onClick={toggle}
            aria-label={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={() => {
              void state.logout();
              onLeave?.();
            }}
            aria-label="יציאה"
            title="יציאה"
          >
            <LogOut size={17} />
          </button>
        </div>
      </header>

      <main id="main-content" className="employee-main">
        {/* What moved since this person last looked (D16). Above everything
            because it is the reason to open the app at all — an employee
            whose shift changed should not have to spot it by comparing the
            grid against memory. */}
        <ChangeAlert
          unseen={view.unseen}
          onAcknowledge={() => void state.acknowledge()}
        />
        {/* A colleague waiting on an answer is its own alert, not part of
            the change count: one says "something moved", the other says
            "somebody is waiting on you", and only the second has a person
            on the other end of it. */}
        <SwapAlert waiting={view.swaps_awaiting_me ?? 0} />

        <nav className="employee-tabs" role="tablist" aria-label="האזור שלי">
          <EmployeeTab
            active={section === "mine"}
            icon={<CalendarDays size={16} />}
            label="המשמרות שלי"
            onClick={() => setSection("mine")}
          />
          <EmployeeTab
            active={section === "requests"}
            icon={<ClipboardList size={16} />}
            label="בקשות והחלפות"
            badge={pendingCount(view)}
            onClick={() => setSection("requests")}
          />
          <EmployeeTab
            active={section === "schedule"}
            icon={<LayoutGrid size={16} />}
            label="הלוח המלא"
            onClick={() => setSection("schedule")}
          />
        </nav>

        <div className="employee-tab-panel" role="tabpanel">
          {section === "mine" ? (
            view.schedule ? (
              <>
                <HoursPanel summary={view.summary} fairness={view.fairness} />
                <MyShifts view={view} />
                <MyChanges view={view} />
              </>
            ) : (
              <NoPublishedSchedule />
            )
          ) : null}

          {section === "requests" ? (
            <>
              <ConstraintForm
                shiftNames={shiftNames}
                requests={view.requests}
                busy={state.busy}
                onSubmit={state.submit}
                onWithdraw={state.withdraw}
              />
              {view.schedule ? (
                <SwapPanel
                  view={view}
                  busy={state.busy}
                  onOffer={state.offerSwap}
                  onAnswer={(id, agreed) => void state.answer(id, agreed)}
                  onCancel={(id) => void state.cancelSwap(id)}
                />
              ) : null}
            </>
          ) : null}

          {section === "schedule" ? (
            view.schedule ? (
              <section className="employee-panel">
                <h2>הסידור המלא</h2>
                {/* `readOnly`, no `onDrop`: there is no gesture here that could
                    change anything. The same component the manager uses, so the
                    team never sees a second rendering that could drift. */}
                {/* No roster is loaded once signed in — it is fetched only
                    for the identity gate — so colours fall back to the hashed
                    hue here. Stable per name, which is what this view needs:
                    the employee is looking for themselves in the grid. */}
                <Calendar
                  schedule={view.schedule}
                  constraints={view.summary.constraints}
                  dark={theme === "dark"}
                  readOnly
                />
              </section>
            ) : (
              <NoPublishedSchedule />
            )
          ) : null}
        </div>
      </main>
    </div>
  );
}

type EmployeeSection = "mine" | "requests" | "schedule";

function EmployeeTab({
  active,
  icon,
  label,
  badge = 0,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  badge?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={active ? "is-active" : undefined}
      onClick={onClick}
    >
      {icon}
      <span>{label}</span>
      {badge > 0 ? <strong>{badge > 9 ? "9+" : badge}</strong> : null}
    </button>
  );
}

function pendingCount(view: EmployeeView): number {
  return view.requests.filter((row) => row.status === "pending").length
    + (view.swaps_awaiting_me ?? 0);
}

function NoPublishedSchedule() {
  return (
    <section className="employee-panel employee-empty-schedule">
      <span className="brand-mark" aria-hidden="true">
        <CalendarClock size={17} />
      </span>
      <div>
        <h2>הסידור עוד לא פורסם</h2>
        <p>
          כשהמנהל יפרסם אותו, המשמרות והשעות יופיעו כאן. אפשר לשלוח בקשות
          כבר עכשיו מהטאב “בקשות והחלפות”.
        </p>
      </div>
    </section>
  );
}

/** This person's shifts, each with who else is on it.
 *
 *  The teammate list needs no new data — the roster is already visible to the
 *  whole team — and it answers a question people actually ask before a
 *  shift. */
function MyShifts({ view }: { view: EmployeeView }) {
  const withMe = new Map(
    view.teammates.map((row) => [`${row.date}|${row.shift}`, row.with]),
  );

  if (view.summary.shifts.length === 0) {
    return (
      <section className="employee-panel">
        <h2>המשמרות שלי</h2>
        <p className="employee-note">
          אין לך משמרות בתקופה הזו. אם זו טעות — כדאי לדבר עם המנהל.
        </p>
      </section>
    );
  }

  return (
    <section className="employee-panel">
      <h2>המשמרות שלי</h2>
      <ul className="shift-list">
        {view.summary.shifts.map((shift) => {
          const others = withMe.get(`${shift.date}|${shift.shift}`) ?? [];
          return (
            <li key={`${shift.date}-${shift.shift}`}>
              <div className="shift-when">
                <strong>{shift.weekday}</strong>
                <span>{formatDate(shift.date)}</span>
              </div>
              <div className="shift-what">
                <span className="shift-name">{shift.shift}</span>
                {shift.is_on_call ? (
                  <span className="shift-oncall">כוננות</span>
                ) : null}
                {others.length > 0 ? (
                  <span className="shift-with">עם {others.join(", ")}</span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/** Changes that touched this person, with the manager's reason.
 *
 *  Read from the append-only change log (D4) and filtered server-side to
 *  entries naming them. Showing the reason is what turns an arbitrary-looking
 *  move into something explained — which is the reason D8 required it be
 *  recorded in the first place. */
function MyChanges({ view }: { view: EmployeeView }) {
  if (view.changes.length === 0) return null;

  return (
    <section className="employee-panel">
      <h2>
        שינויים שנגעו לי
        {view.unseen > 0 ? (
          <span className="change-badge">{view.unseen} חדשים</span>
        ) : null}
      </h2>
      <ul className="change-list">
        {view.changes.map((entry) => (
          <li key={entry.id} className={entry.is_new ? "is-new" : undefined}>
            <span className="change-when">
              {entry.is_new ? (
                <span className="change-dot" aria-label="חדש" />
              ) : null}
              {entry.slot_date ? formatDate(entry.slot_date) : ""}
              {entry.shift_name ? ` · ${entry.shift_name}` : ""}
            </span>
            {entry.reason ? (
              <span className="change-reason">{entry.reason}</span>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The banner that says something moved.
 *
 *  Renders nothing when there is nothing new — this is the common case, and
 *  a permanent "no changes" strip would train people to stop reading the one
 *  place a real change appears.
 *
 *  Dismissing is what acknowledges: the badge clears because the employee
 *  looked, not because time passed. */
function ChangeAlert({
  unseen,
  onAcknowledge,
}: {
  unseen: number;
  onAcknowledge: () => void;
}) {
  if (unseen <= 0) return null;

  return (
    <section className="change-alert" role="status">
      <span className="brand-mark" aria-hidden="true">
        <BellRing size={16} />
      </span>
      <div className="change-alert-body">
        <strong>
          {unseen === 1
            ? "יש שינוי אחד שנוגע אליך"
            : `יש ${unseen} שינויים שנוגעים אליך`}
        </strong>
        <p>מאז הפעם האחרונה שהיית כאן. הפירוט למטה, תחת &rdquo;שינויים שנגעו לי&rdquo;.</p>
      </div>
      <button type="button" className="ghost-button" onClick={onAcknowledge}>
        <Check size={14} />
        ראיתי
      </button>
    </section>
  );
}

/** The banner that says a colleague is waiting on an answer.
 *
 *  Deliberately not acknowledgeable, unlike `ChangeAlert`: there is nothing
 *  to mark as read here, only something to answer. It clears when the
 *  employee accepts or declines, which is the action it exists to prompt. */
function SwapAlert({ waiting }: { waiting: number }) {
  if (waiting <= 0) return null;

  return (
    <section className="change-alert" role="status">
      <span className="brand-mark" aria-hidden="true">
        <ArrowLeftRight size={16} />
      </span>
      <div className="change-alert-body">
        <strong>
          {waiting === 1
            ? "יש בקשת החלפה שממתינה לתשובה שלך"
            : `יש ${waiting} בקשות החלפה שממתינות לתשובה שלך`}
        </strong>
        <p>הפירוט למטה, תחת &rdquo;החלפות משמרות&rdquo;.</p>
      </div>
    </section>
  );
}

/** Shift names as the profile recorded them.
 *
 *  Read defensively: the profile is model-produced JSON whose shape the
 *  interview owns, so anything unexpected degrades to an empty list rather
 *  than throwing. Never hardcode shift names — they are per-workplace data
 *  (D9). */
function readShiftNames(shifts: EmployeeView["shifts"]): string[] {
  if (!Array.isArray(shifts)) return [];
  return shifts
    .map((shift) =>
      typeof shift === "string"
        ? shift
        : ((shift as { name?: unknown })?.name ?? ""),
    )
    .filter((name): name is string => typeof name === "string" && name !== "");
}

function formatDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getDate()}.${date.getMonth() + 1}`;
}

export { useEmployee };
