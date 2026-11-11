"use client";

import {
  AlertTriangle,
  ArrowLeftRight,
  BarChart3,
  Layers,
  LayoutGrid,
  MessagesSquare,
  Moon,
  Network,
  RefreshCw,
  Soup,
  Sun,
  UserCheck,
  UserMinus,
  Users,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import { datesBetween, localToday } from "@/components/Board/dates";
import { rangeOf } from "@/components/Board/views";
import { ViewSwitch } from "@/components/Board/ViewSwitch";
import { WeekNav } from "@/components/Board/WeekNav";
import { AgentGuard, CrewStage, randomGuard } from "@/components/Crew";
import type { Who } from "@/components/Crew";
import { HelpButton, useGuideSurface } from "@/components/Guide";
import { AccountMenu } from "@/components/Management/AccountMenu";
import { buildPalette } from "@/components/Management/palette";
import { useChatSplit } from "@/components/Management/useChatSplit";
import { useTheme } from "@/hooks/useTheme";
import { dutyBoard, enterComplexTeam } from "@/services/api";
import type { CommanderView, DutyBoard } from "@/types";

import { CommanderChat, type ChatTarget } from "./CommanderChat";
import { ComplexGrid } from "./ComplexGrid";
import { DutiesView } from "./DutiesView";
import { figuresOf, NO_FOCUS, type Focus, type Unit } from "./figures";
import { CommanderFilters, Tile } from "./parts";
import { UnitTools, type Tool } from "./UnitTools";
import { UnitsView } from "./UnitsView";
import { useCommanderBoard } from "./useCommander";

type View = "board" | "duties" | "units" | Tool;

const PAGE_COPY: Record<"units" | Tool, { title: string; lede: string }> = {
  units: {
    title: "המשמרות",
    lede: "מצב כל משמרת בטווח שעל המסך, והכניסה לנהל אותה.",
  },
  stats: {
    title: "סטטיסטיקות",
    lede: "איוש, עומס לכל חייל/ת, לילות והתנגשויות — אותם מספרים שמפקד המשמרת רואה.",
  },
  changes: {
    title: "שינויים",
    lede: "החלפת משמרת, הוספת חייל והוספת משמרת — תוך שמירה על הסידור הקיים. כל שינוי נשלח למפקד המשמרת.",
  },
};

/** The מכלול commander's own screen (D43) — the shift manager's control
 *  room, a level up. The same sidebar, top bar, board head, tiles, filter
 *  bar and cards; the same agent in a drawer beside the board, resizable,
 *  opened from the guard in the corner. What differs is what it spans:
 *  the board is every משמרת at once, and the agent speaks to all of their
 *  agents (`CommanderChat`).
 *
 *  The board reads; it does not write. Each משמרת keeps its own rules,
 *  constraints and solver, so a change is a plan its agent prepares and
 *  the commander approves, or is made inside it ("כניסה לניהול"). */
export function CommanderArea({
  commander,
  busy,
  onEnter,
  onLogout,
}: {
  commander: CommanderView;
  busy: boolean;
  onEnter: (teamId: string) => Promise<void>;
  onLogout: () => Promise<void>;
}) {
  const state = useCommanderBoard();
  const { reload } = state;
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const [view, setView] = useState<View>("board");
  const [focus, setFocus] = useState<Focus>(NO_FOCUS);
  useGuideSurface("commander");

  // The agent drawer, as in the משמרת: open beside the board on a wide
  // screen, the split the commander's to drag, the X handing the width back.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { workspace: workspaceRef, share: chatShare, resizing, handle: resizeHandle } = useChatSplit();
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      // Below 1100px the drawer is a sheet over the board, so it waits to be opened.
      if (window.matchMedia("(min-width: 1100px)").matches) setDrawerOpen(true);
    });
    return () => cancelAnimationFrame(frame);
  }, []);
  const [chatTarget, setChatTarget] = useState<ChatTarget>("all");
  const [agentWho, setAgentWho] = useState<Who>("him");
  const rollAgent = useCallback(() => setAgentWho(randomGuard()), []);
  useEffect(() => {
    if (drawerOpen) return;
    const frame = requestAnimationFrame(rollAgent);
    return () => cancelAnimationFrame(frame);
  }, [drawerOpen, rollAgent]);
  const openAgent = useCallback((target?: ChatTarget) => {
    if (target !== undefined) setChatTarget(target);
    setView((current) => (current === "board" || current === "duties" ? current : "board"));
    setDrawerOpen(true);
  }, []);
  const [seed, setSeed] = useState<{ unit: string; text: string; n: number }>();

  const days = useMemo(() => datesBetween(state.start, state.end), [state.start, state.end]);
  const week = rangeOf("week", state.focus).start;
  const units: Unit[] = useMemo(() => state.board?.teams ?? [], [state.board]);
  const shown = units.filter((unit) => !focus.unit || unit.id === focus.unit);
  // The duties of the range, for their band on the board. Re-read with the
  // board itself (a reload, a new range) and on coming back from the duties
  // tab, where they are set. A failed read leaves the board without the band.
  const [duties, setDuties] = useState<DutyBoard | null>(null);
  const boardData = state.board;
  useEffect(() => {
    if (view !== "board" || !boardData) return;
    let cancelled = false;
    dutyBoard(state.start, state.end)
      .then((next) => { if (!cancelled) setDuties(next); })
      .catch(() => { if (!cancelled) setDuties(null); });
    return () => { cancelled = true; };
  }, [view, boardData, state.start, state.end]);
  const figures = figuresOf(shown, days, focus);
  // One colour per soldier across the whole מכלול, keyed by משמרת so two
  // soldiers who share a name in different משמרות are not one person.
  const hueOf = useMemo(() => {
    const roster: string[] = [];
    for (const unit of units) {
      for (const period of unit.periods) {
        for (const row of period.assignments) {
          const key = `${unit.id}:${row.employee}`;
          if (!roster.includes(key)) roster.push(key);
        }
      }
    }
    // A soldier on duty who stands no shift in the range still gets a
    // colour of their own, after everyone the shifts already placed.
    for (const duty of duties?.duties ?? []) {
      const key = `${duty.team_id}:${duty.employee}`;
      if (!roster.includes(key)) roster.push(key);
    }
    return buildPalette(roster);
  }, [units, duties]);
  const rosterOf = useCallback((id: string) => {
    const names = new Set<string>();
    for (const period of units.find((unit) => unit.id === id)?.periods ?? []) {
      for (const row of period.assignments) names.add(row.employee);
    }
    return [...names];
  }, [units]);

  const enter = (id: string) => void onEnter(id);
  const page = view === "units" || view === "stats" || view === "changes" ? view : null;
  const tool: Tool | null = view === "stats" || view === "changes" ? view : null;
  const go = (next: View) => {
    setView(next);
    // A page takes the whole width, as in the משמרת; the board and the
    // duties keep the agent beside them.
    if (next !== "board" && next !== "duties") setDrawerOpen(false);
    window.scrollTo({ top: 0 });
  };

  // The משמרת statistics and changes are about. Opening it signs this
  // browser into that משמרת on the commander's session — the same act as
  // "כניסה לניהול", without leaving the מכלול screen.
  const [toolUnit, setToolUnit] = useState<string | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const [toolError, setToolError] = useState<string | null>(null);
  const openTool = async (id: string) => {
    if (id === toolUnit || opening) return;
    setOpening(id);
    setToolError(null);
    try {
      await enterComplexTeam(id);
      setToolUnit(id);
    } catch (reason) {
      setToolError(reason instanceof Error ? reason.message : "לא ניתן לפתוח את המשמרת");
    } finally {
      setOpening(null);
    }
  };
  const firstActive = commander.teams.find((unit) => unit.active)?.id ?? null;
  const wanted = focus.unit ?? firstActive;
  useEffect(() => {
    if (!tool || toolUnit || !wanted) return;
    let cancelled = false;
    enterComplexTeam(wanted)
      .then(() => { if (!cancelled) setToolUnit(wanted); })
      .catch((reason) => {
        if (!cancelled) setToolError(reason instanceof Error ? reason.message : "לא ניתן לפתוח את המשמרת");
      });
    return () => { cancelled = true; };
  }, [tool, toolUnit, wanted]);

  const sidebarUnit = tool ? toolUnit : focus.unit;
  const navItem = (id: View, icon: React.ReactNode, label: string, tour?: string) => (
    <button
      type="button"
      className={`management-nav-item${view === id && !(id === "board" && drawerOpen) ? " is-active" : ""}`}
      aria-current={view === id ? "page" : undefined}
      onClick={() => go(id)}
      data-tour={tour}
    >
      {icon} {label}
    </button>
  );

  const head = (
    <div className="board-head">
      <div className="board-head-nav">
        <WeekNav
          view={state.view}
          focus={state.focus}
          rangeStart={state.start}
          rangeEnd={state.end}
          isCurrent={state.isCurrent}
          onPrevious={state.previous}
          onNext={state.next}
          onToday={state.goToToday}
        />
        <ViewSwitch view={state.view} onChange={state.setView} />
      </div>
      <div className="cmd-head-title">
        <span className="manager-analytics-eyebrow">{commander.name}</span>
        <strong>{view === "duties" ? "תורנויות המכלול" : "לוח המכלול"}</strong>
      </div>
    </div>
  );

  return (
    <div className="management cmd-management">
      <header className="workspace-sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true"><Network size={17} /></span>
          <span className="brand-text">
            <span className="brand-name">משמרות זהב</span>
            <span>
              {commander.name}
              <span className="brand-sub"> · מפקד מכלול</span>
            </span>
          </span>
        </div>
        <nav className="management-nav" aria-label="ניווט ראשי" data-tour="cmd-nav">
          <button
            type="button"
            className={`management-nav-item${drawerOpen ? " is-active" : ""}`}
            aria-expanded={drawerOpen}
            onClick={() => openAgent()}
          >
            <MessagesSquare size={15} /> סוכן המכלול
          </button>
          {navItem("board", <LayoutGrid size={15} />, "לוח המכלול")}
          {navItem("duties", <Soup size={15} />, "תורנויות", "cmd-duties")}
          {navItem("units", <Layers size={15} />, "המשמרות")}
          {navItem("stats", <BarChart3 size={15} />, "סטטיסטיקות")}
          {navItem("changes", <ArrowLeftRight size={15} />, "שינויים")}
        </nav>

        <section className="workspace-conversations" aria-label="משמרות המכלול">
          <span className="sidebar-section-label">משמרות המכלול</span>
          <div className="sidebar-chat-list">
            <button
              type="button"
              className={!tool && focus.unit === null ? "is-active" : ""}
              aria-current={!tool && focus.unit === null ? "true" : undefined}
              onClick={() => { setFocus(NO_FOCUS); if (!tool) go(view === "duties" ? "duties" : "board"); }}
            >
              <Network size={15} /><span>כל המשמרות</span>
            </button>
            {commander.teams.map((unit) => (
              <button
                type="button"
                key={unit.id}
                title={unit.name}
                className={sidebarUnit === unit.id ? "is-active" : ""}
                aria-current={sidebarUnit === unit.id ? "true" : undefined}
                onClick={() => {
                  setFocus({ ...NO_FOCUS, unit: unit.id });
                  if (tool) void openTool(unit.id);
                  else go("board");
                }}
              >
                <Users size={15} /><span>{unit.name}</span>
              </button>
            ))}
          </div>
        </section>
      </header>

      <div className="management-topbar">
        <div className="header-actions">
          <button type="button" className="icon-button" onClick={reload} aria-label="רענון" title="רענון">
            <RefreshCw size={17} />
          </button>
          <button type="button" className="icon-button" onClick={toggle}
            aria-label={dark ? "מצב בהיר" : "מצב כהה"}>
            {dark ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <HelpButton />
          <AccountMenu name={commander.name} role="מפקד/ת מכלול" onLogout={() => void onLogout()} />
        </div>
      </div>

      {state.error ? (
        <div className="error" role="alert"><AlertTriangle size={16} /><span>{state.error}</span></div>
      ) : null}

      <main
        id="main-content"
        ref={workspaceRef}
        className={`management-workspace cmd-workspace${drawerOpen && !page ? " has-drawer" : ""}${page ? " is-page" : ""}${resizing ? " is-resizing" : ""}`}
        style={{ "--chat-share": `${(chatShare * 100).toFixed(2)}%` } as CSSProperties}
      >
        {page ? (
          <section className="manager-analytics" aria-labelledby="cmd-title">
            <header className="manager-analytics-head">
              <div>
                <span className="manager-analytics-eyebrow">{commander.name}</span>
                <h1 id="cmd-title">{PAGE_COPY[page].title}</h1>
                <p>{PAGE_COPY[page].lede}</p>
              </div>
              <span className="manager-analytics-status">{commander.teams.length} משמרות</span>
            </header>
            {tool ? (
              <div className="cmd-tools">
                <div className="board-views" role="group" aria-label="המשמרת">
                  {commander.teams.map((unit) => (
                    <button
                      key={unit.id}
                      type="button"
                      className={`board-view${toolUnit === unit.id ? " is-on" : ""}`}
                      aria-pressed={toolUnit === unit.id}
                      disabled={!unit.active || Boolean(opening)}
                      onClick={() => void openTool(unit.id)}
                    >
                      {unit.name}
                    </button>
                  ))}
                </div>
                {toolError ? (
                  <div className="error" role="alert"><AlertTriangle size={16} /><span>{toolError}</span></div>
                ) : null}
                {toolUnit && !opening ? (
                  <UnitTools
                    key={toolUnit}
                    tool={tool}
                    onPrepare={(text) => {
                      // The picks become a plan in that משמרת's conversation,
                      // where approving it is the one write path (D12).
                      setSeed((previous) => ({ unit: toolUnit, text, n: (previous?.n ?? 0) + 1 }));
                      openAgent(toolUnit);
                    }}
                  />
                ) : commander.teams.length === 0 ? (
                  <p className="cmd-empty">עדיין לא שויכו משמרות למכלול. צוות משמרות זהב משייך אותן.</p>
                ) : (
                  <CrewStage label="פותח את המשמרת…" />
                )}
              </div>
            ) : state.board === null ? (
              <CrewStage label="טוען את המשמרות…" />
            ) : (
              <>
                {head}
                <UnitsView
                  units={units}
                  days={days}
                  busy={busy}
                  onEnter={enter}
                  onOpen={(id) => { setFocus({ ...NO_FOCUS, unit: id }); go("board"); }}
                />
              </>
            )}
          </section>
        ) : (
          <div className="board cmd-board">
            {head}
            {view === "duties" ? (
              <DutiesView days={days} today={localToday()} units={commander.teams} dark={dark} />
            ) : state.board === null ? (
              <CrewStage label="טוען את לוח המכלול…" />
            ) : (
              <>
                <div className="board-coverage" role="group" aria-label="מצב המכלול" data-tour="cmd-coverage">
                  <Tile
                    icon={<UserCheck size={15} />}
                    label="איוש"
                    value={figures.seats ? `${Math.round((figures.assigned / figures.seats) * 100)}%` : "—"}
                    detail={`${figures.assigned} מתוך ${figures.seats} מקומות`}
                    tone={figures.seats && figures.open === 0 ? "good" : "plain"}
                  />
                  <Tile
                    icon={<UserMinus size={15} />}
                    label="מקומות פתוחים"
                    value={`${figures.open}`}
                    detail={figures.open ? "בכל מה שעל המסך" : "אין חוסרים"}
                    tone={figures.open ? "attention" : "good"}
                  />
                  <Tile
                    icon={<Layers size={15} />}
                    label="משמרות שפורסמו"
                    value={`${figures.published}/${figures.units}`}
                    detail={figures.planned < figures.units
                      ? `${figures.units - figures.planned} לא תוכננו`
                      : `${figures.warnings} אזהרות`}
                    tone={figures.published === figures.units ? "good" : "plain"}
                  />
                  <Tile
                    icon={<Users size={15} />}
                    label="חיילים משובצים"
                    value={`${figures.soldiers}`}
                    detail={`ב־${shown.length} משמרות`}
                    tone="plain"
                  />
                </div>

                <CommanderFilters units={units} focus={focus} onChange={setFocus} />

                {shown.length === 0 ? (
                  <p className="cmd-empty">עדיין לא שויכו משמרות למכלול. צוות משמרות זהב משייך אותן.</p>
                ) : (
                  <ComplexGrid
                    units={shown}
                    days={days}
                    today={localToday()}
                    focus={focus}
                    dark={dark}
                    hueOf={hueOf}
                    busy={busy}
                    duties={duties}
                    onDuties={() => go("duties")}
                    onFocusShift={(unit, shift) => setFocus({ ...focus, unit, shift })}
                    onEnter={enter}
                    onChat={(unit) => openAgent(unit)}
                  />
                )}
              </>
            )}
          </div>
        )}

        {drawerOpen || page ? null : (
          <AgentGuard who={agentWho} onOpen={() => openAgent()} onSwap={rollAgent} />
        )}
        <button
          type="button"
          className="manager-drawer-backdrop"
          hidden={!drawerOpen || Boolean(page)}
          onClick={() => setDrawerOpen(false)}
          aria-label="סגירת הסוכן"
        />
        <aside
          className={`manager-drawer cmd-drawer${drawerOpen && !page ? " is-open" : ""}`}
          aria-label="סוכן המכלול"
          hidden={!drawerOpen || Boolean(page)}
        >
          <div
            className="manager-chat-resizer"
            role="separator"
            tabIndex={0}
            aria-label="גודל הסוכן מול הלוח — גרירה או חיצים, לחיצה כפולה לאיפוס"
            title="גרירה לשינוי הגודל · לחיצה כפולה לאיפוס"
            aria-orientation="vertical"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(chatShare * 100)}
            {...resizeHandle}
          />
          <div className="manager-drawer-head">
            <div>
              <strong>סוכן המכלול</strong>
              <span>{commander.teams.length} משמרות</span>
            </div>
            <button type="button" className="icon-button" onClick={() => setDrawerOpen(false)} aria-label="סגירה">
              <X size={17} />
            </button>
          </div>
          <button
            type="button"
            className="icon-button manager-tabs-close cmd-drawer-close"
            onClick={() => setDrawerOpen(false)}
            aria-label="סגירת הסוכן"
            title="סגירת הסוכן — הלוח יתרחב"
          >
            <X size={16} />
          </button>
          {/* Mounted once and kept: closing the drawer hides it, so a
              sentence still being answered in four משמרות keeps going. */}
          <CommanderChat
            who={agentWho}
            units={commander.teams}
            target={chatTarget}
            week={week}
            rosterOf={rosterOf}
            seed={seed}
            onTarget={setChatTarget}
            onApplied={reload}
          />
        </aside>
      </main>
    </div>
  );
}
