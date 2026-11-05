"use client";

import { Activity, ArrowLeft, CircleAlert, FlaskConical, LayoutGrid, ShieldCheck, UsersRound, X } from "lucide-react";
import { useEffect, useState } from "react";

import { shortDate } from "@/components/DateInput";
import type { ManagerChatMessage, Simulation, StaffingScenarioResult } from "@/types";

export function ScenarioResultCard({ results, disabled, onSimulation, onSend }: {
  results: NonNullable<ManagerChatMessage["payload"]["results"]>;
  disabled: boolean;
  onSimulation: (simulation: Simulation | null) => void;
  onSend: (message: string) => void;
}) {
  const scenarios = results.filter(isStaffingScenario);
  const [selected, setSelected] = useState(0);
  const [showing, setShowing] = useState(false);
  const active = scenarios[Math.min(selected, Math.max(0, scenarios.length - 1))];

  useEffect(() => {
    if (showing && active) onSimulation(toSimulation(active));
  }, [active, showing, onSimulation]);
  useEffect(() => () => onSimulation(null), [onSimulation]);

  if (!active) return null;
  const extra = active.scenario.extra_days;
  const gaps = active.gap_summary;
  const totalMoves = active.board_delta.from_current.operations.length;
  return <section className="scenario-card" aria-label="תוצאת סימולציה">
    <header>
      <span><FlaskConical size={15} /> סימולציה</span>
      <small><ShieldCheck size={12} /> לא נשמר שום שינוי</small>
    </header>

    {scenarios.length > 1 ? <div className="scenario-variants" role="tablist" aria-label="תרחישים להשוואה">
      {scenarios.map((scenario, index) => <button type="button" role="tab" key={`${scenario.scenario.scope}:${scenario.scenario.employee}:${index}`}
        aria-selected={index === selected} onClick={() => setSelected(index)}>
        {scopeLabel(scenario)}
      </button>)}
    </div> : null}

    <div className="scenario-summary">
      <strong>{scenarioTitle(active)}</strong>
      <span>{extra ? `התקרה גדלה בעד ${extra} ימים; אין חובה לנצל את כולם.` : "הסידור נפתר מחדש לפי כל הכללים השמורים."}</span>
    </div>

    <div className="scenario-stages" aria-label="השוואת שלבי התרחיש">
      <Stage label="הלוח עכשיו" value={active.coverage.current_percent} detail={`${active.coverage.current_assigned}/${active.coverage.required}`} />
      <ArrowLeft size={14} aria-hidden="true" />
      <Stage label="איזון קיים" value={active.coverage.after_rebalance_percent} detail={`${active.coverage.after_rebalance}/${active.coverage.required}`} />
      <ArrowLeft size={14} aria-hidden="true" />
      <Stage label="עם התרחיש" value={active.coverage.after_scenario_percent} detail={`${active.coverage.after_scenario}/${active.coverage.required}`} strong />
    </div>

    <div className="scenario-metrics">
      <Metric label="מקומות שנוספו בזכות התרחיש" value={signed(active.coverage.scenario_gain)} />
      <Metric label="חוסרים אחרי התרחיש" value={String(gaps.after_scenario.people_short)} detail={`${signed(gaps.after_scenario.people_short - gaps.current.people_short)} מול הלוח`} />
      <Metric label="שינויים בלוח" value={String(totalMoves)} />
    </div>

    {active.reserve_changes.length ? <details className="scenario-details" open>
      <summary><UsersRound size={14} /> השפעה על אנשי המילואים</summary>
      <div className="scenario-reservists">
        {active.reserve_changes.map((row) => <div key={row.employee}>
          <strong>{row.employee}</strong>
          <span>{cap(row.cap_before)} → {cap(row.cap_after)} מותר</span>
          <span>{row.days_in_baseline} → {row.days_in_scenario} ימים בפועל</span>
          <em className={row.extra_days_used > 0 ? "is-positive" : ""}>{signed(row.extra_days_used)} נוצלו</em>
          {row.capped_at_seven ? <small>הבקשה הגיעה ל־{row.requested_cap}; התקרה נחתכה ל־7</small> : null}
          {row.reason ? <small>{row.reason}</small> : null}
        </div>)}
      </div>
    </details> : null}

    {active.additional_staff.length ? <details className="scenario-details" open>
      <summary><UsersRound size={14} /> כוח האדם ההיפותטי</summary>
      <ul>{active.additional_staff.map((group, index) => <li key={index}>
        {group.count} אנשי {serviceLabel(group.service_type)} · {group.eligible_shifts.join(", ")}
      </li>)}</ul>
    </details> : null}

    <BoardChanges result={active} />
    <Findings result={active} />

    <div className="scenario-actions">
      <button type="button" disabled={disabled || !totalMoves} onClick={() => {
        const next = !showing; setShowing(next); onSimulation(next ? toSimulation(active) : null);
      }}>{showing ? <X size={14} /> : <LayoutGrid size={14} />}{showing ? "הסר מהלוח" : "הצג על הלוח"}</button>
      <button type="button" disabled={disabled} onClick={() => onSend("אני רוצה לשנות את היקף תרחיש כוח האדם האחרון")}>שנה תרחיש</button>
      <button type="button" className="is-primary" disabled={disabled} onClick={() => onSend(planSentence(active))}>צור תוכנית</button>
    </div>
  </section>;
}

function Stage({ label, value, detail, strong = false }: { label: string; value: number; detail: string; strong?: boolean }) {
  return <div className={strong ? "is-strong" : ""}><span>{label}</span><strong>{Math.round(value)}%</strong><small>{detail} מקומות</small></div>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div><span>{label}</span><strong>{value}</strong>{detail ? <small>{detail}</small> : null}</div>;
}

function BoardChanges({ result }: { result: StaffingScenarioResult }) {
  const delta = result.board_delta.caused_by_scenario;
  const rows = [
    ...delta.moves.map((row) => `${row.employee}: ${row.from_shift} ${shortDate(row.from_date)} ← ${row.to_shift} ${shortDate(row.to_date)}`),
    ...delta.assignments_added.map((row) => `${row.employee} נוסף/ה ל${row.shift} ב־${shortDate(row.date)}`),
    ...delta.assignments_removed.map((row) => `${row.employee} הוסר/ה מ${row.shift} ב־${shortDate(row.date)}`),
  ];
  return <details className="scenario-details">
    <summary><Activity size={14} /> מה השתנה בזכות התרחיש</summary>
    {rows.length ? <ul>{rows.map((row, index) => <li key={index}>{row}</li>)}</ul>
      : <p>התוספת לא שינתה שיבוצים מעבר למה שאפשר להשיג עם המכסות הקיימות.</p>}
  </details>;
}

function Findings({ result }: { result: StaffingScenarioResult }) {
  return <details className="scenario-details">
    <summary><CircleAlert size={14} /> אזהרות והנחות</summary>
    {result.introduced.length ? <><strong>אזהרות חדשות</strong><ul>{result.introduced.map((row, index) => <li key={index}>{row.message}</li>)}</ul></> : <p>לא נוספו אזהרות.</p>}
    {result.resolved.length ? <><strong>אזהרות שנפתרו</strong><ul>{result.resolved.map((row, index) => <li key={index}>{row.message}</li>)}</ul></> : null}
    <ul className="scenario-assumptions">{result.assumptions.map((row, index) => <li key={index}>{row}</li>)}</ul>
  </details>;
}

export function isStaffingScenario(value: unknown): value is StaffingScenarioResult {
  const row = value as Partial<StaffingScenarioResult> | null;
  return row?.tool === "staffing_scenario" && row.simulated === true && Boolean(row.coverage && row.board_delta);
}

export function toSimulation(result: StaffingScenarioResult): Simulation {
  return {
    simulated: true, applied: false, schedule_id: result.schedule_id,
    operations: result.board_delta.from_current.operations, skipped: [],
    introduced: result.introduced, resolved: result.resolved,
    warnings_after: result.warnings_after,
    coverage: {
      required: result.coverage.required,
      assigned_before: result.coverage.current_assigned,
      assigned_after: result.coverage.after_scenario,
      delta: result.coverage.delta_from_current,
      percent_before: result.coverage.current_percent,
      percent_after: result.coverage.after_scenario_percent,
    },
    workload: result.workload, affected: result.board_delta.from_current.affected,
  };
}

function scenarioTitle(result: StaffingScenarioResult) {
  if (result.scenario.kind === "additional_staff") return "תוספת כוח אדם היפותטי";
  const extra = result.scenario.extra_days;
  return `${extra ? `+${extra} ימי מילואים` : "שינוי מכסת מילואים"} · ${scopeLabel(result)}`;
}

function scopeLabel(result: StaffingScenarioResult) {
  return result.scenario.scope === "employee" ? `${result.scenario.employee} בלבד` : "כל אנשי המילואים";
}

function planSentence(result: StaffingScenarioResult) {
  if (result.scenario.kind !== "reserve_capacity" || !result.scenario.extra_days)
    return "צור תוכנית על בסיס תרחיש כוח האדם האחרון והצג אותה לאישור לפני כל שינוי";
  const scope = result.scenario.scope === "employee" ? `רק ל${result.scenario.employee}` : "לכל אנשי המילואים";
  return `צור תוכנית שמוסיפה ${result.scenario.extra_days} ימים לתקרת המילואים ${scope}, ומציעה את שינויי הלוח לאישור בלי לבצע אותם עדיין`;
}

const signed = (value: number) => value > 0 ? `+${value}` : String(value);
const cap = (value: number | null) => value === null ? "לא מוגדר" : String(value);
const serviceLabel = (value: string) => ({ reserve: "מילואים", civilian: "אע״צ", hatzach: "הצ״ח", standard: "סדיר" }[value] ?? value);
