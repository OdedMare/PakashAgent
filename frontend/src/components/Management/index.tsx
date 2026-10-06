"use client";

import {
  AlertCircle,
  BarChart3,
  CalendarDays,
  Inbox,
  LogOut,
  LayoutGrid,
  Moon,
  MessagesSquare,
  Settings2,
  SlidersHorizontal,
  Share2,
  Sparkles,
  Sun,
  Users,
  X,
  Plus,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { Board } from "@/components/Board";
import { useTheme } from "@/components/Interview/useTheme";
import { SettingsPanel } from "@/components/Settings";
import { ShareLink } from "@/components/Workspace/ShareLink";
import type { ChatPlan, ManagementOverview, Proposal, TeamView } from "@/types";

import { AgentChat } from "./AgentChat";
import { useManagerChat } from "./useManagerChat";
import { ProfileGapsNotice } from "./ProfileGapsNotice";
import { CopilotInbox } from "./CopilotInbox";
import { History } from "./History";
import { LearnedFromChanges } from "./LearnedFromChanges";
import { ImportSchedule } from "./ImportSchedule";
import { Preferences } from "./Preferences";
import { RequestInbox } from "./RequestInbox";
import { SwapInbox } from "./SwapInbox";
import { Stats } from "./Stats";
import { TeamPanel } from "./TeamPanel";
import { Warnings } from "./Warnings";
import { useManagement } from "./useManagement";
import { displayDate } from "@/components/DateInput";

/** The manager's board-first workspace, opened once the interview is done.
 *
 *  The week remains visible while the agent and management tools open in a
 *  contextual drawer. Both render from the same `useManagement` state, so a
 *  shift moved directly or through the agent lands in one refetched world.
 *
 *  The decisions shaping every interaction are unchanged on both:
 *
 *  - **Changes are proposed, then confirmed.** Whether the manager drags a
 *    shift or types a sentence, the same two steps run and the same two
 *    reasons get recorded (D8). The drag is a nicer way to say what you want,
 *    not a way around saying why.
 *  - **Warnings inform, never block** (D3). The publish button is live
 *    regardless of what the audit found. */
export function Management({
  workspace,
  busy: workspaceBusy = false,
  onLogout,
  onRotateLink,
  onOpenInterview,
  onOpenManualSetup,
  autoGenerate = false,
  onAutoGenerateStarted,
}: {
  workspace: TeamView;
  busy?: boolean;
  onLogout?: () => void;
  onRotateLink?: () => void;
  onOpenInterview?: () => void;
  onOpenManualSetup?: () => void;
  autoGenerate?: boolean;
  onAutoGenerateStarted?: () => void;
}) {
  // The manager chat is the only agent surface; there are no automatic briefings.
  const state = useManagement();
  const generate = state.generate;
  const { theme, toggle } = useTheme();
  // The board stays put. Management tools open beside it, so the manager
  // never has to remember which cell they were discussing with the agent.
  const [view, setView] = useState<ManagerView>("board");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [chatWidth, setChatWidth] = useState(680);
  const [chatSearch, setChatSearch] = useState("");
  const [chatPreview, setChatPreview] = useState<Proposal | null>(null);
  const [chatWeek, setChatWeek] = useState<{ date: string; n: number }>();
  // The day the board opened the agent on, if any. Counted like `suggested`
  // so opening the same day twice still focuses the composer.
  const [focusDay, setFocusDay] = useState<{ date: string; n: number }>({ date: "", n: 0 });
  const refresh = state.refresh;
  const onChatApplied = useCallback(async (plan?: ChatPlan) => {
    await refresh();
    const date = plan?.starts_on || plan?.operations[0]?.date || plan?.constraints[0]?.date;
    if (date) setChatWeek((previous) => ({ date, n: (previous?.n ?? 0) + 1 }));
  }, [refresh]);
  const resizeStart = useRef<{ x: number; width: number } | null>(null);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (window.matchMedia("(min-width: 900px)").matches) setDrawerOpen(true);
      const stored = Number(localStorage.getItem("pakash-chat-width"));
      if (stored >= 340 && stored <= 760) setChatWidth(stored);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const [section, setSection] = useState<ManagerSection>("agent");
  const openAgent = useCallback((date?: string) => {
    if (date !== undefined) setFocusDay((previous) => ({ date, n: previous.n + 1 }));
    setView("board");
    setSection("agent");
    setDrawerOpen(true);
  }, []);
  // A focus day belongs to the week it was opened from. Paging to another
  // week drops it, so the agent is never told about a day off screen.
  const focusDate = focusDay.date && inWeek(focusDay.date, state.focusedWeek) ? focusDay.date : "";
  const agent = useManagerChat(workspace.id, state.focusedScheduleId, state.focusedWeek, focusDate, onChatApplied);
  const [copilotPending, setCopilotPending] = useState(0);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  // The import flow. Opening it writes nothing; the screen's own confirm
  // button is what persists (D7).
  const [importOpen, setImportOpen] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);
  const autoGenerationStarted = useRef(false);
  // A sentence the briefing offered, on its way to the composer. Held as a
  // counter alongside the text so clicking the same suggestion again re-seeds
  // the box after the manager has edited it.
  const [suggested, setSuggested] = useState<{ text: string; n: number }>({
    text: "",
    n: 0,
  });

  const overview = state.overview;
  // Which of the three banner states a build is in, or none. Read from the
  // stored job rather than from whether this browser happens to be polling:
  // a period left half-built by a closed tab is still a job, and the manager
  // needs to be told so on the next visit.
  const buildState =
    state.generation && state.generation.status !== "complete"
      ? state.generation.status
      : "";
  const buildId = overview?.schedule?.id ?? "";
  // Why the build stopped, in the manager's own language. The per-day error
  // was recorded from the first version of this feature and never rendered,
  // so a build that failed for a fixable reason — a model timeout that only
  // a setting can widen — read as an unexplained "היצירה נעצרה" and left the
  // manager with nothing to do but press retry and watch it fail again.
  const buildError =
    state.generation?.days?.find((day) => day.status === "failed")?.error ?? "";
  // How many topics the interview left unsettled. Counted from the profile's
  // own record rather than re-derived, so the badge, the board's notice and
  // what the agent says when asked are all reading one answer. Zero — and no
  // badge — is the ordinary case: a confirmed interview carries no record at
  // all, because the gate refused to let it finish owing anything.
  const completeness = overview?.profile?.completeness;
  const openTopics =
    completeness && !completeness.complete
      ? completeness.missing_topics.length + completeness.open_points.length
      : 0;
  const schedule = overview?.schedule ?? null;

  useEffect(() => {
    if (!autoGenerate || autoGenerationStarted.current) return;
    autoGenerationStarted.current = true;
    onAutoGenerateStarted?.();
    setAutoGenerating(true);
    void generate({}).finally(() => setAutoGenerating(false));
  }, [autoGenerate, generate, onAutoGenerateStarted]);

  return (
    <div className="management">
      <header className="interview-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <CalendarDays size={17} />
          </span>
          <span>
            {workspace.name}
            <span className="brand-sub"> · איזור ניהול</span>
          </span>
        </div>
        {/* The board is the workspace; management opens beside it. */}
        <nav className="management-nav" aria-label="ניווט ראשי">
          <button
            type="button"
            className={`management-nav-item${drawerOpen ? " is-active" : ""}`}
            onClick={() => openAgent()}
            aria-expanded={drawerOpen}
          >
            <MessagesSquare size={15} />
            סוכן הסידור
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "board" && !drawerOpen ? " is-active" : ""}`}
            onClick={() => {
              setView("board");
              setDrawerOpen(false);
              window.scrollTo({ top: 0 });
            }}
            aria-current={view === "board" && !drawerOpen ? "page" : undefined}
          >
            <LayoutGrid size={15} />
            לוח המשמרות
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "team" ? " is-active" : ""}`}
            onClick={() => {
              setView("team");
              setDrawerOpen(false);
              window.scrollTo({ top: 0 });
            }}
            aria-current={view === "team" ? "page" : undefined}
          >
            <Users size={15} />
            כוח אדם
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "analytics" ? " is-active" : ""}`}
            onClick={() => {
              setView("analytics");
              setDrawerOpen(false);
              window.scrollTo({ top: 0 });
            }}
            aria-current={view === "analytics" ? "page" : undefined}
          >
            <BarChart3 size={15} />
            נתונים
          </button>

        </nav>

        <section className="workspace-conversations" aria-label="השיחות שלך">
          <button type="button" className="sidebar-new-chat" disabled={agent.busy || agent.working || agent.loading}
            onClick={() => { void agent.newChat(); openAgent(); }}><Plus size={18} />שיחה חדשה</button>
          <label className="sidebar-search"><Search size={15} aria-hidden="true" />
            <input type="search" aria-label="חיפוש שיחות" placeholder="חיפוש שיחות" value={chatSearch}
              onChange={(event) => setChatSearch(event.target.value)} /></label>
          <span className="sidebar-section-label">השיחות שלך</span>
          <div className="sidebar-chat-list">
            {agent.chats.filter((chat) => chat.title.includes(chatSearch)).map((chat) =>
              <button type="button" key={chat.id} title={chat.title} disabled={agent.busy || agent.working}
                className={agent.chat?.id === chat.id ? "is-active" : ""}
                aria-current={agent.chat?.id === chat.id ? "true" : undefined}
                onClick={() => { void agent.select(chat.id); openAgent(); }}><MessagesSquare size={15} /><span>{chat.title}</span></button>)}
            {chatSearch && !agent.chats.some((chat) => chat.title.includes(chatSearch)) ? <p>לא נמצאו שיחות</p> : null}
          </div>
        </section>

        <div className="header-actions">
          {onOpenManualSetup ? (
            <button
              type="button"
              className="icon-button"
              onClick={onOpenManualSetup}
              aria-label="הגדרה ידנית של היחידה"
              title="הגדרה ידנית של היחידה"
            >
              <SlidersHorizontal size={17} />
            </button>
          ) : null}
          {onOpenInterview ? (
            <button
              type="button"
              className={
                openTopics ? "icon-button has-badge" : "icon-button"
              }
              onClick={onOpenInterview}
              aria-label={
                openTopics
                  ? `ראיון היכרות — ${openTopics} נושאים פתוחים`
                  : "ראיון היכרות"
              }
              title={
                openTopics
                  ? `הראיון לא הושלם — ${openTopics} נושאים עוד לא סוכמו`
                  : "ראיון היכרות"
              }
            >
              <Sparkles size={17} />
              {openTopics ? (
                <span className="icon-badge" aria-hidden="true">
                  {openTopics > 9 ? "9+" : openTopics}
                </span>
              ) : null}
            </button>
          ) : null}
          {workspace.member_token ? (
            <button
              type="button"
              className="icon-button"
              onClick={() => setShareOpen((open) => !open)}
              aria-label="קישור לצוות"
              title="קישור לצוות"
              aria-expanded={shareOpen}
            >
              <Share2 size={17} />
            </button>
          ) : null}
          <button
            type="button"
            className="icon-button"
            onClick={() => setSettingsOpen(true)}
            aria-label="הגדרות מערכת"
            title="הגדרות מערכת"
          >
            <Settings2 size={17} />
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={toggle}
            aria-label={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          {onLogout ? (
            <button
              type="button"
              className="icon-button"
              onClick={onLogout}
              aria-label="יציאה"
              title="יציאה"
            >
              <LogOut size={17} />
            </button>
          ) : null}
        </div>
      </header>

      {shareOpen && workspace.member_token ? (
        <ShareLink
          token={workspace.member_token}
          busy={workspaceBusy}
          onRotate={() => onRotateLink?.()}
        />
      ) : null}

      {/* What a build is doing, and the way out of one.
          The banner is the *only* thing a build occupies: the board below it
          stays writable throughout (D18), so a manager can keep placing
          shifts by hand while the agent works — and can stop it. Stopping
          keeps every day already built; the period is an ordinary draft the
          moment it returns, and "המשך" picks the rest up from the first day
          that is not finished. */}
      {autoGenerating || buildState ? (
        <div className="schedule-generation" role="status" aria-live="polite">
          <div className="schedule-generation-copy">
            <strong>
              {buildState === "failed"
                ? `היצירה נעצרה בתאריך ${state.generation?.current_date ?? ""}`
                : buildState === "cancelled"
                ? `היצירה הופסקה — ${state.generation?.completed_days ?? 0} מתוך ${state.generation?.total_days ?? 7} ימים נשמרו`
                : `בונים את הסידור — ${state.generation?.completed_days ?? 0} מתוך ${state.generation?.total_days ?? 7} ימים`}
            </strong>
            {/* Which width this build is running at. Worth saying on the
                banner and not only in the settings panel: it is the single
                biggest factor in how long the manager is about to wait, and
                the setting that governs it lives two screens away. */}
            {state.generation?.mode === "week" ? (
              <span className="schedule-generation-mode">
                בנייה שבועית — עד שבוע בכל פנייה למודל
              </span>
            ) : null}
            {buildState === "failed" && buildError ? (
              <span className="schedule-generation-why">{buildError}</span>
            ) : null}
            <span className="schedule-generation-actions">
              {buildId && (buildState === "failed" || buildState === "cancelled") ? (
                <button
                  type="button"
                  className="ghost-button"
                  disabled={state.generating}
                  onClick={() => void state.resumeGeneration(buildId)}
                >
                  {buildState === "failed"
                    ? "ניסיון חוזר מהיום שנכשל"
                    : "המשך יצירה מהיום הבא"}
                </button>
              ) : null}
              {buildId && buildState === "running" && state.generating ? (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => void state.cancelGeneration()}
                >
                  עצירת היצירה
                </button>
              ) : null}
              {/* A job the database still calls running that nobody in this
                  browser is watching — left behind by a closed tab or a
                  restarted backend. Picking it up is one click. */}
              {buildId && buildState === "running" && !state.generating ? (
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => void state.resumeGeneration(buildId)}
                >
                  המשך יצירה מהיום הבא
                </button>
              ) : null}
              <span className="schedule-generation-note">
                הסוכן בונה כל יום בנפרד ומתחשב במה שכבר שובץ — אפשר לשבץ ידנית
                בזמן שהוא עובד.
              </span>
            </span>
          </div>
          <div
            className="schedule-generation-track"
            role="progressbar"
            aria-label="בניית סידור המשמרות"
            aria-valuemin={0}
            aria-valuemax={state.generation?.total_days || 7}
            aria-valuenow={state.generation?.completed_days || 0}
            aria-valuetext={`${state.generation?.completed_days || 0} מתוך ${state.generation?.total_days || 7}`}
          >
            <span
              className={buildState === "failed" ? "is-failed" : ""}
              style={state.generation?.total_days ? {
                width: `${Math.max(4, state.generation.completed_days / state.generation.total_days * 100)}%`,
                animation: "none",
              } : undefined}
            />
          </div>
        </div>
      ) : null}

      {state.error ? (
        <div className="error" role="alert">
          <AlertCircle size={16} />
          <span>{state.error}</span>
          <button type="button" onClick={state.clearError}>
            סגירה
          </button>
        </div>
      ) : null}

      {/* A build refused for a reason the manager can close. Above the board
          because it is about the board they are looking at not existing, and
          beside the error rather than inside it: nothing here is a fault. */}
      {state.gaps ? (
        <ProfileGapsNotice
          gaps={state.gaps}
          onOpenInterview={onOpenInterview}
          onDiscuss={() => {
            // Seed the composer and move to the room. The question is
            // written for the manager rather than sent for them — the agent
            // answers questions and writes nothing (D15), so the point of
            // arriving here is to work out what the interview is owed
            // before going and answering it.
            setSuggested((previous) => ({
              text: "אני רוצה לבנות סידור לשבוע הקרוב. מה חסר לך כדי לבנות אותו, ואיך נשלים את זה?",
              n: previous.n + 1,
            }));
            setSection("agent");
            setDrawerOpen(true);
          }}
          onDismiss={state.dismissGaps}
        />
      ) : null}

      <main
        id="main-content"
        className={`management-workspace${drawerOpen ? " has-drawer" : ""}${view !== "board" ? " is-page" : ""}`}
        style={{ "--chat-width": `${chatWidth}px` } as CSSProperties}
      >
        {view === "analytics" ? (
          <ManagerAnalytics overview={overview} />
        ) : view === "team" ? (
          <section className="manager-analytics" aria-labelledby="manager-team-title">
            <header className="manager-analytics-head">
              <div>
                <span className="manager-analytics-eyebrow">היחידה שלך</span>
                <h1 id="manager-team-title">כוח אדם ותקינה</h1>
                <p>אנשי צוות, מעמד, סבב או תלתון, סוגי משמרות ואילוצים במקום אחד.</p>
              </div>
              {overview ? (
                <span className="manager-analytics-status">
                  {overview.employees.length} אנשי צוות
                </span>
              ) : null}
            </header>
            {overview ? (
              <TeamPanel
                today={overview.today}
                employees={overview.employees}
                shifts={overview.shifts}
                constraints={overview.availability}
                stats={overview.stats}
                dark={theme === "dark"}
                rotationMode={overview.profile?.workplace?.rotation_mode}
                onAdd={state.addConstraint}
                onRemove={state.removeConstraint}
                onSaveProfile={state.saveProfile}
              />
            ) : (
              <div className="manager-analytics-loading" aria-busy="true">
                טוען את פרטי הצוות…
              </div>
            )}
          </section>
        ) : (
          <Board
            overview={overview}
            busy={state.busy}
            generating={state.generating}
            dark={theme === "dark"}
            onGenerate={state.generate}
            onOpenDay={(date) => openAgent(date)}
            onOpenBlank={state.openBlank}
            onAssign={state.assign}
            onUnassign={state.unassign}
            onMove={state.move}
            onClear={state.clearShifts}
            onDelete={state.removeSchedule}
            onPublish={state.publish}
            onExport={state.exportSchedule}
            onPeriodChange={state.focusPeriod}
            navigateToWeek={chatWeek}
            onOpenAgent={() => openAgent()}
            // What the agent is currently saying, so the board can show
            // *where* on the week it applies. The same state the cards in the
            // control room render — one source, so the two screens can never
            // point at different cells. Read-only: the board produces no
            // operations and there is no path from a highlight to a write.
            agent={{
              simulation: null,
              proposal: chatPreview,
              answer: null,
            }}
          />
        )}
        <button
          type="button"
          className="manager-drawer-backdrop"
          hidden={!drawerOpen}
          onClick={() => setDrawerOpen(false)}
          aria-label="סגירת אזור הניהול"
        />
        <aside
          className={`manager-drawer${drawerOpen ? " is-open" : ""}`}
          aria-label="אזור ניהול"
          hidden={!drawerOpen}
        >
          <div className="manager-chat-resizer" role="separator" tabIndex={0}
            aria-label="שינוי רוחב חלונית השיחה" aria-orientation="vertical"
            aria-valuemin={340} aria-valuemax={760} aria-valuenow={chatWidth}
            onPointerDown={(event) => {
              resizeStart.current = { x: event.clientX, width: chatWidth };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!resizeStart.current) return;
              const delta = (event.clientX - resizeStart.current.x) * (document.documentElement.dir === "rtl" ? -1 : 1);
              setChatWidth(Math.max(340, Math.min(760, resizeStart.current.width + delta)));
            }}
            onPointerUp={() => { resizeStart.current = null; localStorage.setItem("pakash-chat-width", String(chatWidth)); }}
            onLostPointerCapture={() => { resizeStart.current = null; }}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                event.preventDefault();
                const width = Math.max(340, Math.min(760, chatWidth + (event.key === "ArrowRight" ? 20 : -20)));
                setChatWidth(width); localStorage.setItem("pakash-chat-width", String(width));
              }
            }} />
          <div className="manager-drawer-head">
            <div>
              <strong>ניהול הסידור</strong>
              <span>{schedule?.status === "published" ? "הסידור מפורסם" : "מרחב עבודה"}</span>
            </div>
            <button type="button" className="icon-button" onClick={() => setDrawerOpen(false)} aria-label="סגירה">
              <X size={17} />
            </button>
          </div>
          <div className="manager-tabs" role="group" aria-label="כלי ניהול">
            <ManagerTab
              active={section === "agent"}
              icon={<Sparkles size={15} />}
              label="סוכן"
              onClick={() => setSection("agent")}
            />
            <ManagerTab
              active={section === "requests"}
              icon={<Inbox size={15} />}
              label="בקשות"
              onClick={() => setSection("requests")}
            />
            <ManagerTab
              active={section === "team"}
              icon={<Users size={15} />}
              label="צוות"
              onClick={() => setSection("team")}
            />
            <ManagerTab
              active={section === "overview"}
              icon={<BarChart3 size={15} />}
              label="סקירה"
              count={copilotPending}
              onClick={() => setSection("overview")}
            />
          </div>

          <div className={`manager-drawer-content${section === "agent" ? " is-conversation" : ""}`}>
          {section === "agent" ? <>
          {schedule?.status === "published" ? (
            <PublishedNotice
              onUnlock={() => state.publish(schedule.id, false)}
              busy={state.busy}
            />
          ) : null}
          </> : null}
          <AgentChat
            hidden={section !== "agent"}
            agent={agent}
            visibleWeek={state.focusedWeek}
            focusDate={focusDate}
            focusKey={focusDay.n}
            onClearFocus={() => setFocusDay((previous) => ({ date: "", n: previous.n }))}
            employees={overview?.employees.map((person) => String(person.name ?? "")).filter(Boolean) ?? []}
            boardBusy={state.busy}
            draft={suggested.text}
            draftKey={suggested.n}
            onPreview={setChatPreview}
            onOpenReceipt={(date) => setChatWeek((previous) => ({ date, n: (previous?.n ?? 0) + 1 }))}
            onImport={() => setImportOpen(true)}
          />

          <div hidden={section !== "overview"}>
          <CopilotInbox
            onOpenInterview={onOpenInterview}
            onPendingChange={setCopilotPending}
            onAct={(text) => {
              setSuggested((previous) => ({ text, n: previous.n + 1 }));
              setSection("agent");
            }}
          />
          </div>

          {section === "requests" ? <>
          {schedule?.status === "published" ? (
            <PublishedNotice
              onUnlock={() => state.publish(schedule.id, false)}
              busy={state.busy}
            />
          ) : null}
          <RequestInbox onDecided={state.refresh} />
          <SwapInbox
            onDecided={state.refresh}
            writeLocked={schedule?.status === "published"}
          />
          </> : null}

          {section === "team" ? <>
          <Preferences busy={state.busy} />
          <TeamPanel
            today={overview?.today}
            employees={overview?.employees ?? []}
            shifts={overview?.shifts ?? []}
            constraints={overview?.availability ?? []}
            stats={overview?.stats}
            dark={theme === "dark"}
            rotationMode={overview?.profile?.workplace?.rotation_mode}
            draggable={schedule?.status === "draft" && !state.busy}
            onAdd={state.addConstraint}
            onRemove={state.removeConstraint}
            onSaveProfile={state.saveProfile}
          />
          </> : null}

          {section === "overview" ? <>
            {schedule?.notes?.length ? <ul className="schedule-notes">{schedule.notes.map((note, index) => <li key={index}>{note}</li>)}</ul> : null}
            {schedule ? <Warnings warnings={schedule.warnings} /> : null}
            {overview?.stats ? <Stats stats={overview.stats} /> : null}
            <History entries={overview?.changes ?? []} />
            <LearnedFromChanges />
          </> : null}
          </div>
        </aside>
      </main>

      {/* Reading the files writes nothing; this screen's own confirm button
          is the only thing that persists (D7). */}
      {importOpen ? (
        <ImportSchedule
          shiftNames={(overview?.shifts ?? [])
            .map((shift) => String((shift as { name?: unknown }).name ?? ""))
            .filter(Boolean)}
          onClose={() => setImportOpen(false)}
          onImported={() => {
            setImportOpen(false);
            void state.refresh();
          }}
        />
      ) : null}

      {settingsOpen ? (
        <SettingsPanel onClose={() => setSettingsOpen(false)} />
      ) : null}
    </div>
  );
}

type ManagerView = "board" | "team" | "analytics";

/** Whether `date` falls in the seven days starting `weekStart`. An unknown
 *  week keeps the day: nothing on screen contradicts it yet. */
function inWeek(date: string, weekStart: string): boolean {
  if (!weekStart) return true;
  const offset = (new Date(`${date}T00:00:00`).getTime() - new Date(`${weekStart}T00:00:00`).getTime()) / 86_400_000;
  return offset >= 0 && offset < 7;
}
type ManagerSection = "agent" | "requests" | "team" | "overview";

function ManagerAnalytics({
  overview,
}: {
  overview: ManagementOverview | undefined;
}) {
  const schedule = overview?.schedule;

  return (
    <section className="manager-analytics" aria-labelledby="manager-analytics-title">
      <header className="manager-analytics-head">
        <div>
          <span className="manager-analytics-eyebrow">חדר הנתונים</span>
          <h1 id="manager-analytics-title">תמונת מצב של הצוות</h1>
          <p>
            {schedule
              ? `${displayDate(schedule.starts_on)}–${displayDate(schedule.ends_on)} · ${schedule.status === "published" ? "סידור מפורסם" : "טיוטה בעבודה"}`
              : "כשתיפתח תקופת שיבוץ, הנתונים שלה יופיעו כאן."}
          </p>
        </div>
        {schedule ? (
          <span className={`manager-analytics-status ${schedule.status}`}>
            {schedule.status === "published" ? "מפורסם" : "טיוטה"}
          </span>
        ) : null}
      </header>

      {overview ? <Stats stats={overview.stats} expanded /> : (
        <div className="manager-analytics-loading" aria-busy="true">
          טוען את נתוני התקופה…
        </div>
      )}

      {schedule?.warnings.length ? (
        <section className="manager-analytics-warnings">
          <div className="manager-analytics-section-head">
            <div>
              <span>מה דורש מבט</span>
              <h2>התראות התקופה</h2>
            </div>
            <strong>{schedule.warnings.length}</strong>
          </div>
          <Warnings warnings={schedule.warnings} />
        </section>
      ) : null}
    </section>
  );
}

function ManagerTab({
  active,
  icon,
  label,
  count,
  onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={`manager-tab${active ? " is-active" : ""}`}
      onClick={onClick}
    >
      {icon}
      {label}
      {count ? <span className="manager-tab-badge">{count > 9 ? "9+" : count}</span> : null}
    </button>
  );
}

function PublishedNotice({
  onUnlock,
  busy,
}: {
  onUnlock: () => void;
  busy: boolean;
}) {
  return (
    <div className="manager-published-notice">
      <span>
        הסידור מפורסם. אפשר לקרוא ולשאול, אבל שינוי דורש החזרה לטיוטה.
      </span>
      <button
        type="button"
        className="ghost-button"
        onClick={onUnlock}
        disabled={busy}
      >
        החזרה לטיוטה
      </button>
    </div>
  );
}
