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
  Sun,
  UserCheck,
  UserMinus,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { datesBetween, localToday } from "@/components/Board/dates";
import { ViewSwitch } from "@/components/Board/ViewSwitch";
import { WeekNav } from "@/components/Board/WeekNav";
import { CrewStage } from "@/components/Crew";
import { HelpButton, useGuideSurface } from "@/components/Guide";
import { AccountMenu } from "@/components/Management/AccountMenu";
import { buildPalette } from "@/components/Management/palette";
import { useTheme } from "@/hooks/useTheme";
import { enterComplexTeam } from "@/services/api";
import type { CommanderView } from "@/types";

import { ComplexGrid } from "./ComplexGrid";
import { figuresOf, type Focus, type Unit } from "./figures";
import { FocusBar, Tile } from "./parts";
import { UnitTools, type Tool } from "./UnitTools";
import { UnitsView } from "./UnitsView";
import { useCommanderBoard } from "./useCommander";

type View = "board" | "units" | Tool;

const TOOL_COPY: Record<Tool, { title: string; lede: string }> = {
  agent: {
    title: "סוכן הסידור",
    lede: "אותו סוכן של המשמרת: שאלות, שינויים ותוכניות — שום דבר לא נשמר עד שמאשרים. כל שינוי נשלח למפקד המשמרת.",
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

/** The מכלול commander's own screen (D43), in the management area's shell:
 *  the same sidebar, top bar, board head, tiles and cards a מפקד משמרת
 *  works in, so moving between the two is moving between rooms of one
 *  building rather than between products.
 *
 *  It reads; it does not write. Each משמרת has its own rules, constraints
 *  and solver, so a change is made inside it — "כניסה לניהול" opens the
 *  משמרת with every power its commander holds. */
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
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const [view, setView] = useState<View>("board");
  const [focus, setFocus] = useState<Focus>({ unit: null, shift: null });
  useGuideSurface("commander");

  const days = useMemo(() => datesBetween(state.start, state.end), [state.start, state.end]);
  const units: Unit[] = useMemo(() => state.board?.teams ?? [], [state.board]);
  const shown = units.filter((unit) => !focus.unit || unit.id === focus.unit);
  const figures = figuresOf(shown, days, focus);
  const focusedUnit = units.find((unit) => unit.id === focus.unit) ?? null;
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
    return buildPalette(roster);
  }, [units]);

  const enter = (id: string) => void onEnter(id);
  const focusUnit = (id: string | null) => setFocus({ unit: id, shift: null });
  const tool: Tool | null = view === "agent" || view === "stats" || view === "changes" ? view : null;

  // The משמרת the agent, statistics and changes are about. Opening it signs
  // this browser into that משמרת on the commander's session — the same act
  // as "כניסה לניהול", without leaving the מכלול screen — so the tools
  // below read and write that משמרת and no other.
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
            className={`management-nav-item${view === "board" ? " is-active" : ""}`}
            aria-current={view === "board" ? "page" : undefined}
            onClick={() => setView("board")}
          >
            <LayoutGrid size={15} /> לוח המכלול
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "units" ? " is-active" : ""}`}
            aria-current={view === "units" ? "page" : undefined}
            onClick={() => setView("units")}
          >
            <Layers size={15} /> המשמרות
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "agent" ? " is-active" : ""}`}
            aria-current={view === "agent" ? "page" : undefined}
            onClick={() => setView("agent")}
          >
            <MessagesSquare size={15} /> סוכן הסידור
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "stats" ? " is-active" : ""}`}
            aria-current={view === "stats" ? "page" : undefined}
            onClick={() => setView("stats")}
          >
            <BarChart3 size={15} /> סטטיסטיקות
          </button>
          <button
            type="button"
            className={`management-nav-item${view === "changes" ? " is-active" : ""}`}
            aria-current={view === "changes" ? "page" : undefined}
            onClick={() => setView("changes")}
          >
            <ArrowLeftRight size={15} /> שינויים
          </button>
        </nav>

        <section className="workspace-conversations" aria-label="משמרות המכלול">
          <span className="sidebar-section-label">משמרות המכלול</span>
          <div className="sidebar-chat-list">
            <button
              type="button"
              className={!tool && focus.unit === null ? "is-active" : ""}
              aria-current={!tool && focus.unit === null ? "true" : undefined}
              onClick={() => { focusUnit(null); setView("board"); }}
            >
              <Network size={15} /><span>כל המשמרות</span>
            </button>
            {commander.teams.map((unit) => (
              <button
                type="button"
                key={unit.id}
                title={unit.name}
                className={(tool ? toolUnit : focus.unit) === unit.id ? "is-active" : ""}
                aria-current={(tool ? toolUnit : focus.unit) === unit.id ? "true" : undefined}
                onClick={() => {
                focusUnit(unit.id);
                if (tool) void openTool(unit.id);
                else setView("board");
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
          <button type="button" className="icon-button" onClick={state.reload} aria-label="רענון" title="רענון">
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

      <main id="main-content" className="management-workspace is-page cmd-workspace">
        <section className="manager-analytics" aria-labelledby="cmd-title">
          <header className="manager-analytics-head">
            <div>
              <span className="manager-analytics-eyebrow">המכלול שלך</span>
              <h1 id="cmd-title">
                {tool
                  ? TOOL_COPY[tool].title
                  : view === "units" ? "המשמרות" : focusedUnit ? focusedUnit.name : "לוח המכלול"}
              </h1>
              <p>
                {tool
                  ? TOOL_COPY[tool].lede
                  : view === "units"
                    ? "מצב כל משמרת בטווח שעל המסך, והכניסה לנהל אותה."
                    : "כל המשמרות זו לצד זו, עם כל החיילים. עורכים בתוך המשמרת — כל שינוי נשלח למפקד המשמרת."}
              </p>
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
                <UnitTools key={toolUnit} unitId={toolUnit} tool={tool} onTool={setView} />
              ) : commander.teams.length === 0 ? (
                <p className="cmd-empty">עדיין לא שויכו משמרות למכלול. צוות משמרות זהב משייך אותן.</p>
              ) : (
                <CrewStage label="פותח את המשמרת…" />
              )}
            </div>
          ) : (
          <div className="board">
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
            </div>

            {state.board === null ? (
              <CrewStage label="טוען את לוח המכלול…" />
            ) : view === "units" ? (
              <UnitsView
                units={units}
                days={days}
                busy={busy}
                onEnter={enter}
                onOpen={(id) => { focusUnit(id); setView("board"); }}
              />
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

                <FocusBar
                  units={units}
                  focus={focus}
                  onUnit={focusUnit}
                  onShift={(shift) => setFocus((current) => ({ ...current, shift }))}
                />

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
                    onFocusShift={(unit, shift) => setFocus({ unit, shift })}
                    onEnter={enter}
                  />
                )}
              </>
            )}
          </div>
          )}
        </section>
      </main>
    </div>
  );
}
