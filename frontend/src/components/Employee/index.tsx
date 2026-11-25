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

import { CrewLoading } from "@/components/Crew";
import { HelpButton, useGuideSurface } from "@/components/Guide";
import { useTheme } from "@/hooks/useTheme";
import { Calendar, hebrewWeekday } from "@/components/Management/Calendar";
import type { EmployeeView } from "@/types";

import { ConstraintForm } from "./ConstraintForm";
import { IdentityGate } from "./IdentityGate";
import { MyShifts } from "./MyShifts";
import { SWAP_THEIRS_ID, SwapPanel } from "./SwapPanel";
import { useEmployee } from "./useEmployee";
import { shortDate } from "@/components/DateInput";

/** The employee's personal area.
 *
 *  What [D14](../../../../docs/DECISIONS.md) added, and the boundary of what
 *  it added: this screen shows one person their own shifts and changes, and
 *  lets them **ask** not to be scheduled or to swap. Charts of hours against
 *  the team are the manager's (D27). It has no control that edits a schedule — the calendar below is the same
 *  `readOnly` grid the team view renders, taking no `onDrop`, because the
 *  manager remains the sole decider.
 *
 *  Everything shown is scoped server-side by the name in the signed cookie.
 *  There is no name parameter anywhere in this component tree, which is what
 *  keeps one employee out of another's hours and stated reasons. */
export function Employee({ onLeave, openRequests = false }: { onLeave?: () => void; openRequests?: boolean }) {
  const { theme, toggle } = useTheme();
  const state = useEmployee();
  const { view } = state;
  const [section, setSection] = useState<EmployeeSection>(openRequests ? "requests" : "mine");
  const [initial, setInitial] = useState<{ date: string; shift: string }>();
  // My assignment the swap form opens on, when "החלפה" was pressed on a shift.
  const [swapFrom, setSwapFrom] = useState<string>();
  // Only once signed in: the claim gate has none of what the tour points at.
  useGuideSurface(view ? "employee" : null);

  // Not asked yet. Rendering the gate here would flash a claim screen at
  // someone who is already signed in.
  if (view === undefined) {
    return <CrewLoading label="פותחים את האזור האישי…" />;
  }

  if (view === null) {
    return (
      <IdentityGate
        requests={openRequests}
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

  /** Open "בקשות והחלפות", optionally with a form filled in and brought into
   *  view. Every way in resets both presets, so a shortcut used once does
   *  not linger into the next plain visit to the tab. */
  const goToRequests = (to: {
    initial?: { date: string; shift: string };
    swapFrom?: string;
    scrollTo?: string;
    focus?: string;
  }) => {
    setInitial(to.initial);
    setSwapFrom(to.swapFrom);
    setSection("requests");
    if (to.scrollTo) showOnceRendered(to.scrollTo, to.focus);
  };

  return (
    <div className="workspace-surface">
      <header className="workspace-sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <UserCircle size={17} />
          </span>
          <span className="brand-text">
            <span className="brand-name">משמרות זהב</span>
            <span>
              {view.employee}
              <span className="brand-sub"> · האזור שלי</span>
            </span>
          </span>
        </div>
        <div className="header-actions">
          <HelpButton />
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

      {/* The full board gets the whole window: a week of shifts squeezed into
          the reading column hides most of it behind a sideways scroll. */}
      <main
        id="main-content"
        className={section === "schedule" ? "employee-main is-wide" : "employee-main"}
      >
        {/* What moved since this person last looked (D16). Above everything
            because it is the reason to open the app at all — an employee
            whose shift changed should not have to spot it by comparing the
            grid against memory. */}
        <ChangeAlert
          unseen={view.unseen}
          onAcknowledge={() => void state.acknowledge()}
          onShow={section === "mine" ? undefined : () => setSection("mine")}
        />
        {/* A colleague waiting on an answer is its own alert, not part of
            the change count: one says "something moved", the other says
            "somebody is waiting on you", and only the second has a person
            on the other end of it. */}
        <SwapAlert
          waiting={view.swaps_awaiting_me ?? 0}
          onShow={() => goToRequests({ scrollTo: SWAP_PANEL_ID })}
        />

        <nav className="employee-tabs" role="tablist" aria-label="האזור שלי" data-tour="employee-tabs">
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
            tour="employee-requests-tab"
            onClick={() => goToRequests({})}
          />
          <EmployeeTab
            active={section === "schedule"}
            icon={<LayoutGrid size={16} />}
            label="הלוח המלא"
            onClick={() => setSection("schedule")}
          />
        </nav>

        <div className="employee-tab-panel" role="tabpanel">
          {/* The next shift leads (it is inside `MyShifts`); duties follow,
              since they are whole days set by the מכלול, read less often. */}
          {section === "mine" ? (
            view.schedule ? (
              <>
                <MyShifts
                  view={view}
                  onCantMake={(date, shift) =>
                    goToRequests({ initial: { date, shift }, scrollTo: CONSTRAINT_FORM_ID })}
                  onSwap={(assignmentId) =>
                    goToRequests({ swapFrom: assignmentId, scrollTo: SWAP_PANEL_ID, focus: SWAP_THEIRS_ID })}
                />
                <MyDuties view={view} />
                <MyChanges view={view} />
              </>
            ) : (
              <>
                <MyDuties view={view} />
                <NoPublishedSchedule />
              </>
            )
          ) : null}

          {section === "requests" ? (
            <>
              {state.error && <p role="alert">{state.error}</p>}
              <ConstraintForm
                id={CONSTRAINT_FORM_ID}
                initial={initial}
                shiftNames={shiftNames}
                requests={view.requests}
                busy={state.busy}
                onSubmit={state.submit}
                onWithdraw={state.withdraw}
              />
              {view.schedule ? (
                <SwapPanel
                  id={SWAP_PANEL_ID}
                  preset={swapFrom}
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
              <section className="employee-panel employee-board">
                <h2>הסידור המלא</h2>
                <p className="employee-note">המשמרות שלך מסומנות במסגרת וברקע צבעוני.</p>
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
                  onRequest={(date, shift) =>
                    goToRequests({ initial: { date, shift }, scrollTo: CONSTRAINT_FORM_ID })}
                  highlight={view.employee}
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

const SWAP_PANEL_ID = "employee-swaps";
const CONSTRAINT_FORM_ID = "employee-constraint-form";

/** Bring a form into view after the requests tab has rendered, and
 *  optionally put focus on its next empty field.
 *
 *  Switching tabs keeps the scroll position, so a button pressed low on
 *  "המשמרות שלי" — or the swap panel, which sits below the constraint form —
 *  would otherwise open its form off-screen on a phone, the very thing the
 *  button was pressed to reach. */
function showOnceRendered(id: string, focus?: string) {
  window.requestAnimationFrame(() => {
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.getElementById(id)?.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
    if (focus) document.getElementById(focus)?.focus({ preventScroll: true });
  });
}

function EmployeeTab({
  active,
  icon,
  label,
  badge = 0,
  tour,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  badge?: number;
  tour?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-tour={tour}
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

/** Their own מכלול duties (D44): a whole day each, set by the מכלול
 *  commander, which no shift of theirs can fall on. Nothing renders for a
 *  soldier with none -- most of them, and every team outside a מכלול. */
function MyDuties({ view }: { view: EmployeeView }) {
  const duties = view.duties ?? [];
  if (!duties.length) return null;
  return (
    <section className="employee-panel">
      <h2>התורנויות שלי</h2>
      <ul className="shift-list">
        {duties.map((duty) => (
          <li key={duty.duty_date}>
            <div className="shift-when">
              <strong>{hebrewWeekday(duty.duty_date)}</strong>
              <span>{shortDate(duty.duty_date)}</span>
            </div>
            <div className="shift-what">
              <span className="shift-name">{duty.duty_type}</span>
              <span className="shift-with">
                {duty.blocks ? "כל היום · תורנות מכלול" : "נרשמה כתורנות שנעשתה"}
              </span>
            </div>
          </li>
        ))}
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
              {entry.slot_date ? shortDate(entry.slot_date) : ""}
              {entry.shift_name ? ` · ${entry.shift_name}` : ""}
            </span>
            <strong className="change-what">{changeLabel(entry, view.employee)}</strong>
            {entry.reason || entry.action.startsWith("complex_duty") ? (
              <span className="change-reason">
                {entry.action.startsWith("complex_duty") ? entry.agent_reason : entry.reason}
              </span>
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
  onShow,
}: {
  unseen: number;
  onAcknowledge: () => void;
  /** Absent when the list is already on screen ("המשמרות שלי"). */
  onShow?: () => void;
}) {
  if (unseen <= 0) return null;

  return (
    <section className="change-alert" role="status" data-tour="change-alert">
      <span className="brand-mark" aria-hidden="true">
        <BellRing size={16} />
      </span>
      <div className="change-alert-body">
        <strong>
          {unseen === 1
            ? "יש שינוי אחד שנוגע אליך"
            : `יש ${unseen} שינויים שנוגעים אליך`}
        </strong>
        <p>
          {onShow
            ? "מאז הפעם האחרונה שהיית כאן. הפירוט בטאב “המשמרות שלי”."
            : "מאז הפעם האחרונה שהיית כאן. הפירוט למטה, תחת “שינויים שנגעו לי”."}
        </p>
      </div>
      {onShow ? (
        <button type="button" className="ghost-button" onClick={onShow}>
          להצגה
        </button>
      ) : null}
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
function SwapAlert({ waiting, onShow }: { waiting: number; onShow: () => void }) {
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
        <p>הבקשה נמצאת בטאב “בקשות והחלפות”, תחת “החלפות משמרות”.</p>
      </div>
      <button type="button" className="ghost-button" onClick={onShow}>
        <ArrowLeftRight size={14} />
        לתשובה
      </button>
    </section>
  );
}

/** What a change-log row did to *this* person, in a few words.
 *
 *  The date and the manager's reason were already shown; without this line
 *  a row cannot tell "you were given a shift" from "you were taken off one".
 *  Worded from the reader's side, which matters for the two-person actions:
 *  a swap names this person on either column, and the
 *  sentence differs by which. Unknown actions fall back to a neutral word
 *  rather than the raw code. */
function changeLabel(entry: EmployeeView["changes"][number], me: string): string {
  const other = entry.employee === me ? entry.replaced_employee : entry.employee;
  switch (entry.action) {
    case "assigned":
      return "שובצת למשמרת";
    case "removed":
      return entry.slot_date ? "הוסרת מהמשמרת" : "הוסרת מהצוות";
    case "moved":
      return "הועברת למשמרת אחרת";
    case "swapped":
      return other ? `הוחלפה משמרת עם ${other}` : "הוחלפה משמרת";
    case "constraint":
      return "נרשם לך אילוץ";
    case "request_rejected":
      return "בקשת האילוץ נדחתה";
    case "swap_rejected":
      return "בקשת ההחלפה נדחתה";
    case "complex_duty":
      return "שובצת לתורנות מכלול";
    case "complex_duty_cancelled":
      return "תורנות המכלול בוטלה";
    case "complex_duty_recorded":
      return "נרשמה לך תורנות";
    case "renamed":
      return "השם שלך עודכן";
    default:
      return entry.action.endsWith("_approved") ? "שינוי שהמנהל אישר" : "שינוי בסידור";
  }
}

/** Shift names as the profile recorded them.
 *
 *  Read defensively: the profile is model-produced JSON whose shape the
 *  profile owns, so anything unexpected degrades to an empty list rather
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
