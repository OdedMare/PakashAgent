"use client";

import { Activity, CircleAlert, FlaskConical, LayoutGrid, ShieldCheck, UsersRound, X } from "lucide-react";
import { useEffect, useState } from "react";

import { shortDate } from "@/components/DateInput";
import type { ChangeSimulationResult, ManagerChatMessage, Simulation } from "@/types";

export function ChangeSimulationCard({ results, disabled, onSimulation, onSend }: {
  results: NonNullable<ManagerChatMessage["payload"]["results"]>;
  disabled: boolean;
  onSimulation: (simulation: Simulation | null) => void;
  onSend: (message: string) => void;
}) {
  const result = results.find(isChangeSimulation);
  const [showing, setShowing] = useState(false);
  useEffect(() => () => onSimulation(null), [onSimulation]);
  if (!result) return null;
  return <section className="scenario-card change-simulation-card" aria-label="סימולציית שינוי">
    <header><span><FlaskConical size={15} /> סימולציית שינוי</span><small><ShieldCheck size={12} /> לא נשמר שום שינוי</small></header>
    <div className="scenario-summary">
      <strong>{result.coverage.delta > 0 ? "הכיסוי משתפר" : result.coverage.delta < 0 ? "הכיסוי נפגע" : "הכיסוי נשאר ללא שינוי"}</strong>
      <span>{result.operations.length} פעולות נבדקו עבור {result.affected.length} אנשים.</span>
    </div>
    <div className="scenario-stages is-two">
      <div><span>לפני</span><strong>{Math.round(result.coverage.percent_before)}%</strong><small>{result.coverage.assigned_before}/{result.coverage.required} מקומות</small></div>
      <Activity size={14} aria-hidden="true" />
      <div className="is-strong"><span>אחרי</span><strong>{Math.round(result.coverage.percent_after)}%</strong><small>{result.coverage.assigned_after}/{result.coverage.required} מקומות</small></div>
    </div>
    {result.workload.length ? <details className="scenario-details" open>
      <summary><UsersRound size={14} /> שינוי בעומס</summary>
      <ul>{result.workload.map((row) => <li key={row.employee}>{row.employee}: {row.hours_before} → {row.hours_after} שעות ({signed(row.delta)})</li>)}</ul>
    </details> : null}
    <details className="scenario-details" open>
      <summary><Activity size={14} /> השינויים שנבדקו</summary>
      <ul>{result.operations.map((row, index) => <li key={index}>{operationLabel(row.action)} {row.employee} · {row.shift} · {shortDate(row.date)}</li>)}</ul>
      {result.skipped.length ? <><strong>פעולות שלא ניתן היה לבדוק</strong><ul>{result.skipped.map((row, index) => <li key={index}>{row.employee}: {row.why}</li>)}</ul></> : null}
    </details>
    <details className="scenario-details">
      <summary><CircleAlert size={14} /> אזהרות</summary>
      {result.introduced.length ? <><strong>נוספו</strong><ul>{result.introduced.map((row, index) => <li key={index}>{row.message}</li>)}</ul></> : <p>לא נוספו אזהרות.</p>}
      {result.resolved.length ? <><strong>נפתרו</strong><ul>{result.resolved.map((row, index) => <li key={index}>{row.message}</li>)}</ul></> : null}
    </details>
    <div className="scenario-actions">
      <button type="button" disabled={disabled || !result.operations.length} onClick={() => {
        const next = !showing; setShowing(next); onSimulation(next ? result : null);
      }}>{showing ? <X size={14} /> : <LayoutGrid size={14} />}{showing ? "הסר מהלוח" : "הצג על הלוח"}</button>
      <button type="button" className="is-primary" disabled={disabled || !result.operations.length}
        onClick={() => onSend("צור תוכנית מהסימולציה האחרונה והצג אותה לאישור בלי לבצע שינוי עדיין")}>צור תוכנית</button>
    </div>
  </section>;
}

function isChangeSimulation(value: unknown): value is ChangeSimulationResult {
  const row = value as Partial<ChangeSimulationResult> | null;
  return row?.tool === "simulate_changes" && row.simulated === true && Array.isArray(row.operations);
}

const operationLabel = (action: string) => action === "assign" ? "הוספת" : action === "remove" ? "הסרת" : "החלפת";
const signed = (value: number) => value > 0 ? `+${value}` : String(value);
