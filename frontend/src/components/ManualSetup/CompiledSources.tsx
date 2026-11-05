"use client";

import { useEffect, useState } from "react";

import { compiledSources } from "@/services/api";
import type { CompiledSource } from "@/services/api";

// While anything is still being translated in the background, look again,
// but not forever: the worker may be down, and the next build translates
// whatever is missing anyway.
const POLL_MS = 5000;
const MAX_POLLS = 24;

const KIND_LABELS: Record<string, string> = {
  rule: "כלל",
  preference: "העדפה",
  rest_policy: "מדיניות מנוחה",
  weekend_policy: "מדיניות סופ״ש",
  fairness_policy: "מדיניות הוגנות",
  conflict_policy: "מדיניות התנגשויות",
  casual_worker_policy: "מדיניות מזדמנים",
  dependencies: "תלויות",
  general_exit_schedule: "תכנית יציאות",
  training_policy: "מדיניות חניכה",
  employee_notes: "הערה",
  employee_availability: "זמינות",
  employee_workload: "עומס",
  employee_trainers: "חונכים",
  employee_is_trainee: "חניכה",
  recurring_constraint: "אילוץ קבוע",
};

const PERSON_KINDS = new Set(["employee_notes", "employee_availability", "employee_workload", "employee_trainers", "employee_is_trainee", "recurring_constraint"]);

/** What the code scheduler made of every sentence in setup, sorted to where
 *  each sentence is written: a soldier's on their card (`context` is the
 *  saved name), a rule's beside the rule, and the rest — the unit's
 *  policies — on their own. A read only: translating happens on save. */
export function useCompiledSources() {
  const [sources, setSources] = useState<CompiledSource[]>([]);

  useEffect(() => {
    let polls = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    const load = async () => {
      try {
        const rows = await compiledSources();
        if (stopped) return;
        setSources(rows);
        if (rows.some((row) => row.status === "pending") && ++polls < MAX_POLLS) {
          timer = setTimeout(() => void load(), POLL_MS);
        }
      } catch {
        // Nothing to show; the build's notes still say what was left out.
      }
    };
    void load();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const isPerson = (source: CompiledSource) => PERSON_KINDS.has(source.kind);
  return {
    forPerson: (name: string) => name ? sources.filter((source) => isPerson(source) && source.context === name) : [],
    forRule: (text: string) => text ? sources.filter((source) => source.kind === "rule" && readable(source.text).trim() === text) : [],
    rest: sources.filter((source) => !isPerson(source) && source.kind !== "rule"),
  };
}

/** A few translated sentences, each with its status. Nothing when empty. */
export function CompiledList({ sources, title, bare = false }: { sources: CompiledSource[]; title?: string; /** Status only, for a row that already shows the sentence. */ bare?: boolean }) {
  if (!sources.length) return null;
  return (
    <div className="manual-compiled-block">
      {title ? <span className="field-label">{title}</span> : null}
      <ul className="manual-compiled">
        {sources.map((source, index) => (
          <li key={index} className={bare ? "is-bare" : undefined}>
            {bare ? null : <span className="manual-compiled-kind">{KIND_LABELS[source.kind] ?? source.kind}</span>}
            {bare ? null : <span className="manual-compiled-text">{readable(source.text)}</span>}
            <Status source={source} />
            {source.question && !source.expired ? <span className="manual-compiled-question">צריך אישור: {source.question}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Status({ source }: { source: CompiledSource }) {
  if (source.expired) return <span className="manual-compiled-tag muted">פג תוקף, אפשר למחוק</span>;
  if (source.status === "pending") return <span className="manual-compiled-tag muted">מתרגם…</span>;
  if (source.status === "compiled") return <span className="manual-compiled-tag ok">מתורגם לקוד ✓</span>;
  return (
    <span className={`manual-compiled-tag ${source.binding ? "warn" : "muted"}`} title={source.reason}>
      {source.binding ? "ידרוש AI" : "משאלה שלא תילקח בחשבון בקוד"}{source.reason ? `: ${source.reason}` : ""}
    </span>
  );
}

// Rules travel as JSON ({"text": ..., "priority": ...}); show the sentence.
function readable(value: string): string {
  try {
    const parsed = JSON.parse(value);
    if (parsed && typeof parsed === "object" && typeof parsed.text === "string") return parsed.text;
  } catch {
    // A plain sentence.
  }
  return value;
}
