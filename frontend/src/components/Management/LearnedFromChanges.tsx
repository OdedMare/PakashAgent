"use client";

import { Lightbulb, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { learnFromChanges } from "@/services/api";
import type { ChangeLearning } from "@/types";

/** Rules the manager's own corrections suggest.
 *
 *  The other end of what an import learns. Uploaded files say what the
 *  workplace *did*; the change log says what the manager **decided** — every
 *  row in it is a moment somebody overrode the schedule and wrote down why,
 *  which [D8](../../../../docs/DECISIONS.md) guaranteed would be there.
 *
 *  **Nothing here is a rule.** Each card is a candidate the manager reads and
 *  decides on, and the panel says so outright rather than implying it: the
 *  leap from "you keep fixing this" to "this is a rule" is exactly the one a
 *  person has to make, and a screen that looked like a settings page would
 *  make it for them
 *  ([D7](../../../../docs/DECISIONS.md#d7--import-infers-layout-boss-confirms)).
 *
 *  The evidence is shown beside every candidate, including the manager's own
 *  words. That is what lets them approve a claim they can check instead of
 *  one they must trust — the same reason the import screen shows counts.
 *
 *  Adding a rule is deliberately **not** a button here. Rules live on the
 *  workplace profile, which the interview owns; a second write path into it
 *  would mean two places that can define what the workplace requires. The
 *  panel names the rule in the manager's own register so it can be said to
 *  the agent or added in the interview, which is where rules are authored. */
export function LearnedFromChanges() {
  const [data, setData] = useState<ChangeLearning | null>(null);
  const [busy, setBusy] = useState(true);

  const load = useCallback(() => {
    learnFromChanges()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setBusy(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rules = data?.candidate_rules ?? [];
  const repeated = data?.corrections.repeated ?? [];
  const notes = data?.notes ?? [];

  // A workspace whose manager has not corrected anything twice yet renders
  // nothing at all. An empty-state card in a busy sidebar teaches people to
  // skip the region it lives in, and this panel only has something to say
  // once there is history behind it.
  if (repeated.length === 0 && rules.length === 0) return null;

  return (
    <section className="history learned-panel" aria-label="מה שחוזר על עצמו">
      <h3>
        <Lightbulb size={15} />
        מה שחוזר על עצמו
        <button
          type="button"
          className="icon-button"
          onClick={() => {
            setBusy(true);
            load();
          }}
          disabled={busy}
          aria-label="רענון"
          title="רענון"
        >
          <RefreshCw size={13} />
        </button>
      </h3>

      <p className="learned-intro">
        לפי התיקונים שעשית בסידור. אלה <strong>הצעות בלבד</strong> — שום דבר
        כאן לא הפך לכלל.
      </p>

      {rules.length > 0 ? (
        <ul className="learned-list">
          {rules.map((rule, index) => (
            <li key={`${rule.text}-${index}`}>
              <div className="learned-head">
                <span className={`op-badge op-${rule.kind}`}>
                  {rule.kind === "hard" ? "כלל נוקשה" : "העדפה"}
                </span>
                <span className={`learned-confidence is-${rule.confidence}`}>
                  {CONFIDENCE_LABELS[rule.confidence]}
                </span>
              </div>
              <p className="learned-text">{rule.text}</p>
              {/* The count and the manager's own words. Shown always, never
                  behind a disclosure: a candidate whose evidence is hidden is
                  one the manager approves on trust. */}
              <p className="learned-evidence">{rule.evidence}</p>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="learned-list">
          {/* The model had nothing to propose, but the counts still do. Shown
              raw rather than suppressed — "you moved Yossi off Friday evening
              three times" is useful on its own, and it is the arithmetic half
              that does not depend on a model being available. */}
          {repeated.map((row) => (
            <li key={`${row.employee}-${row.shift}-${row.weekday}`}>
              <p className="learned-text">
                {row.employee}
                {row.shift ? ` · ${row.shift}` : ""}
                {row.weekday ? ` · ${row.weekday}` : ""}
              </p>
              <p className="learned-evidence">
                תוקן {row.count} פעמים
                {row.reasons.length > 0
                  ? ` — ${row.reasons.join("; ")}`
                  : ""}
              </p>
            </li>
          ))}
        </ul>
      )}

      {notes.length > 0 ? (
        <ul className="learned-notes">
          {notes.map((note, index) => (
            <li key={`${note}-${index}`}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

const CONFIDENCE_LABELS: Record<string, string> = {
  high: "ביטחון גבוה",
  medium: "ביטחון בינוני",
  low: "ביטחון נמוך",
};
