"use client";

import {
  Archive,
  BookMarked,
  Check,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  addPreference,
  deletePreference,
  listPreferences,
  updatePreference,
} from "@/services/api";
import type { Preference, PreferenceKind } from "@/types";

/** What this workplace has taught the agent, beyond one-off decisions.
 *
 *  Not rules and not constraints. Rules are the boss's sentences on the
 *  profile ([D2](../../../docs/DECISIONS.md#d2--rules-stay-natural-language))
 *  and constraints are what `bl/audit.py` counts — a preference is standing
 *  *operational context*: "עדיף לשאול את יוסי לפני רון לסופ״ש", "הודעות
 *  לקבוצה קצרות ובלי הסיבה", "מאיה מעדיפה בקרים".
 *
 *  Three properties make this safe to have at all, and each is visible on
 *  the screen rather than only true in the backend:
 *
 *  - **Everything is listed.** A stored preference the manager cannot see is
 *    a rule they never agreed to. There is no hidden memory.
 *  - **A suggestion is inert.** One the agent proposed lands as `suggested`
 *    and is marked as such; the agent reads only active ones, so it changes
 *    nothing until the manager approves it. One decision is a decision — it
 *    becomes a standing preference when the manager says it is one, which is
 *    the same line D14 draws between a request and a constraint.
 *  - **Everything is editable.** Reword it, archive it, or delete it.
 *
 *  **A preference never authorises a write.** It reaches the model as
 *  reported speech — context to respect while proposing — and the
 *  confirmation step is unchanged by anything in this list. */
export function Preferences({ busy = false }: { busy?: boolean }) {
  const [rows, setRows] = useState<Preference[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [kind, setKind] = useState<PreferenceKind>("general");
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await listPreferences());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useCallback(
    async (action: () => Promise<unknown>) => {
      try {
        await action();
        setError(null);
        await load();
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
      }
    },
    [load],
  );

  const suggested = rows.filter((row) => row.status === "suggested");
  const active = rows.filter((row) => row.status === "active");
  const archived = rows.filter((row) => row.status === "archived");

  return (
    <section className="preferences" aria-label="העדפות קבועות">
      <header className="preferences-header">
        <span className="brand-mark" aria-hidden="true">
          <BookMarked size={15} />
        </span>
        <div>
          <h3>מה שהסוכן זוכר</h3>
          <p>
            העדפות תפעוליות קבועות. הן הקשר לסוכן — הן לא מאשרות שום שינוי
            בעצמן.
          </p>
        </div>
      </header>

      {error ? (
        <p className="preferences-error" role="alert">
          {error}
        </p>
      ) : null}

      <form
        className="preferences-add"
        onSubmit={(event) => {
          event.preventDefault();
          const text = draft.trim();
          if (!text) return;
          void run(() => addPreference({ text, kind })).then(() =>
            setDraft(""),
          );
        }}
      >
        <input
          type="text"
          value={draft}
          maxLength={500}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="למשל: עדיף לשאול את יוסי לפני רון לסופ״ש"
          disabled={busy}
        />
        <select
          value={kind}
          onChange={(event) => setKind(event.target.value as PreferenceKind)}
          aria-label="סוג ההעדפה"
          disabled={busy}
        >
          {(Object.keys(KIND_LABELS) as PreferenceKind[]).map((option) => (
            <option key={option} value={option}>
              {KIND_LABELS[option]}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="ghost-button"
          disabled={busy || !draft.trim()}
          aria-label="הוספה"
        >
          <Plus size={14} />
        </button>
      </form>

      {/* Suggestions first: they are the only rows that need a decision. */}
      {suggested.length ? (
        <div className="preferences-group is-suggested">
          <h4>הצעות שממתינות לאישור</h4>
          <ul>
            {suggested.map((row) => (
              <li key={row.id}>
                <div className="preferences-text">
                  <span>{row.text}</span>
                  {/* The evidence is what makes a suggestion checkable
                      rather than merely assertive. */}
                  {row.evidence ? (
                    <small className="preferences-evidence">
                      {row.evidence}
                    </small>
                  ) : null}
                </div>
                <div className="preferences-row-actions">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="אישור"
                    title="אישור — מכאן זה יישמר כהעדפה קבועה"
                    onClick={() =>
                      void run(() =>
                        updatePreference(row.id, { status: "active" }),
                      )
                    }
                  >
                    <Check size={14} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="דחייה"
                    onClick={() => void run(() => deletePreference(row.id))}
                  >
                    <X size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="preferences-group">
        <h4>בתוקף</h4>
        {active.length ? (
          <ul>
            {active.map((row) => (
              <li key={row.id}>
                {editing?.id === row.id ? (
                  <form
                    className="preferences-edit"
                    onSubmit={(event) => {
                      event.preventDefault();
                      const text = editing.text.trim();
                      if (!text) return;
                      void run(() =>
                        updatePreference(row.id, { text }),
                      ).then(() => setEditing(null));
                    }}
                  >
                    <input
                      type="text"
                      value={editing.text}
                      maxLength={500}
                      autoFocus
                      onChange={(event) =>
                        setEditing({ id: row.id, text: event.target.value })
                      }
                    />
                    <button type="submit" className="icon-button">
                      <Check size={14} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => setEditing(null)}
                    >
                      <X size={14} />
                    </button>
                  </form>
                ) : (
                  <>
                    <div className="preferences-text">
                      <span>{row.text}</span>
                      <small className="preferences-kind">
                        {KIND_LABELS[row.kind] ?? row.kind}
                        {row.subject ? ` · ${row.subject}` : ""}
                        {row.source === "agent" ? " · הסוכן הציע" : ""}
                      </small>
                    </div>
                    <div className="preferences-row-actions">
                      <button
                        type="button"
                        className="icon-button"
                        aria-label="עריכה"
                        onClick={() =>
                          setEditing({ id: row.id, text: row.text })
                        }
                      >
                        <Pencil size={13} />
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label="השבתה"
                        title="השבתה — נשמר בהיסטוריה ואפשר להחזיר"
                        onClick={() =>
                          void run(() =>
                            updatePreference(row.id, { status: "archived" }),
                          )
                        }
                      >
                        <Archive size={13} />
                      </button>
                      <button
                        type="button"
                        className="icon-button"
                        aria-label="מחיקה"
                        onClick={() => void run(() => deletePreference(row.id))}
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="preferences-empty">
            {loading
              ? "טוען…"
              : "עוד לא נשמרו העדפות. אפשר להוסיף אחת למעלה."}
          </p>
        )}
      </div>

      {archived.length ? (
        <details className="preferences-group is-archived">
          <summary>מושבתות ({archived.length})</summary>
          <ul>
            {archived.map((row) => (
              <li key={row.id}>
                <div className="preferences-text">
                  <span>{row.text}</span>
                </div>
                <div className="preferences-row-actions">
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="החזרה לתוקף"
                    onClick={() =>
                      void run(() =>
                        updatePreference(row.id, { status: "active" }),
                      )
                    }
                  >
                    <Check size={13} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="מחיקה"
                    onClick={() => void run(() => deletePreference(row.id))}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}

/** The kinds in the manager's language. Mirrors the backend's own vocabulary. */
const KIND_LABELS: Record<PreferenceKind, string> = {
  general: "כללי",
  staffing: "שיבוץ",
  notification: "הודעות",
  employee: "עובד/ת",
  shift: "משמרת",
};
