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

/** What the code scheduler made of every sentence in setup. A read only:
 *  translating happens on save, and a sentence is changed where it is written. */
export function CompiledSources() {
  const [sources, setSources] = useState<CompiledSource[] | null>(null);
  const [failed, setFailed] = useState(false);

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
        if (!stopped) setFailed(true);
      }
    };
    void load();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  if (failed) return <p className="manual-compiled-empty">לא ניתן לטעון כרגע את מצב התרגום.</p>;
  if (sources === null) return <p className="manual-compiled-empty">טוען…</p>;
  if (!sources.length) {
    return <p className="manual-compiled-empty">אין כרגע כללים, מדיניות או הערות בשפה חופשית. השיבוץ בקוד לא צריך תרגום.</p>;
  }
  return (
    <ul className="manual-compiled">
      {sources.map((source, index) => (
        <li key={index}>
          <span className="manual-compiled-kind">
            {KIND_LABELS[source.kind] ?? source.kind}{source.context ? ` · ${source.context}` : ""}
          </span>
          <span className="manual-compiled-text">{readable(source.text)}</span>
          <Status source={source} />
          {source.question && !source.expired ? <span className="manual-compiled-question">צריך אישור: {source.question}</span> : null}
        </li>
      ))}
    </ul>
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
