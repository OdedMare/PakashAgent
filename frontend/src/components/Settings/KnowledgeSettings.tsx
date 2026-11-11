"use client";

import { FilePlus2, FileUp, Save, Trash2 } from "lucide-react";
import { ChangeEvent, useRef, useState } from "react";

import type { KnowledgeDocument } from "@/types";

import { LibraryLoading, LibraryStatus } from "./LibraryStatus";
import { useLibrary } from "./useLibrary";
import type { LibraryController } from "./useLibrary";

type Draft = { id: string; title: string; content: string; enabled: boolean };

const BLANK: Draft = { id: "", title: "", content: "", enabled: true };

/** The organization's own documents (D54): its terms, roles, abbreviations
 *  and tone. Every switched-on document is read by every agent after its
 *  instructions, so the agent speaks the organization's language.
 *
 *  Each document saves with its own button; nothing here waits for the
 *  form's footer. */
export function KnowledgeSettings({ password }: { password: string }) {
  const state = useLibrary(password);
  // The document open in the editor: one already saved, or a new one.
  const [draft, setDraft] = useState<Draft | null>(null);
  const { library } = state;

  if (!library) {
    return (
      <section className="settings-section">
        <h3>מידע ארגוני</h3>
        {state.error ? <LibraryStatus state={state} /> : <LibraryLoading />}
      </section>
    );
  }

  const full = library.documents.length >= library.limits.documents;
  return (
    <section className="settings-section">
      <h3>מידע ארגוני</h3>
      <p className="settings-hint library-intro">
        כתבו כאן את מה שהסוכן צריך לדעת על הארגון: מונחים וראשי תיבות, תפקידים, נהלים וסגנון
        הפנייה. הסוכן קורא כל מסמך פעיל בכל פנייה, ומדבר במונחים שלכם.
      </p>

      {library.documents.length ? (
        <ul className="library-list">
          {library.documents.map((document) => (
            <li key={document.id}>
              <button
                type="button"
                className={draft?.id === document.id ? "is-open" : ""}
                onClick={() => setDraft({ ...document })}
              >
                <strong dir="auto">{document.title}</strong>
                <small>
                  {document.content.length.toLocaleString("he-IL")} תווים
                  {document.enabled ? "" : " · כבוי"}
                </small>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="models-status library-empty">עדיין אין מסמכים.</p>
      )}

      <div className="library-actions">
        <button
          type="button"
          className="models-refresh"
          onClick={() => setDraft({ ...BLANK })}
          disabled={full}
        >
          <FilePlus2 size={14} aria-hidden="true" /> מסמך חדש
        </button>
        <span className="library-count">
          {library.knowledge_chars.toLocaleString("he-IL")} מתוך{" "}
          {library.limits.knowledge_chars.toLocaleString("he-IL")} תווים פעילים
        </span>
      </div>

      {draft ? (
        <DocumentEditor
          // A different document is a different editor, not the same one
          // with its fields swapped under the cursor.
          key={draft.id || "new"}
          draft={draft}
          saved={library.documents.find((row) => row.id === draft.id)}
          limit={library.limits.document_chars}
          state={state}
          onChange={setDraft}
          onClose={() => setDraft(null)}
        />
      ) : null}
      <LibraryStatus state={state} />

      <p className="settings-note">
        המסמכים משותפים לכל הצוותים ונשלחים למודל עם כל פנייה, ולכן כדאי לשמור אותם קצרים
        וענייניים. הם רקע בלבד: מסמך לא משנה את כללי הסידור ולא מאשר שינוי. אחרי שמירה,
        כללים שכבר תורגמו לבנייה יתורגמו מחדש בבנייה הבאה, לפי ההגדרות המעודכנות.
      </p>
    </section>
  );
}

function DocumentEditor({
  draft, saved, limit, state, onChange, onClose,
}: {
  draft: Draft;
  saved: KnowledgeDocument | undefined;
  limit: number;
  state: LibraryController;
  onChange: (draft: Draft) => void;
  onClose: () => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const tooLong = draft.content.length > limit;

  /** A text file read in the browser into the editor; nothing is uploaded
   *  until the document is saved. */
  const readFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    const content = await chosen.text();
    onChange({
      ...draft,
      content,
      title: draft.title || chosen.name.replace(/\.[^.]+$/, ""),
    });
  };

  const save = async () => {
    const { id, ...document } = draft;
    if (await state.saveDocument(id, document)) onClose();
  };

  const remove = async () => {
    if (!window.confirm(`למחוק את המסמך "${saved?.title ?? draft.title}"?`)) return;
    if (await state.deleteDocument(draft.id)) onClose();
  };

  return (
    <div className="library-editor">
      <label className="field-label" htmlFor="library-title">שם המסמך</label>
      <input
        id="library-title"
        className="settings-input"
        dir="auto"
        maxLength={120}
        placeholder="למשל: מילון מונחים של היחידה"
        value={draft.title}
        onChange={(event) => onChange({ ...draft, title: event.target.value })}
      />
      <div className="model-field-header">
        <label className="field-label" htmlFor="library-content">תוכן</label>
        <button
          type="button"
          className="models-refresh"
          onClick={() => file.current?.click()}
        >
          <FileUp size={14} aria-hidden="true" /> טעינה מקובץ טקסט
        </button>
        <input
          ref={file}
          type="file"
          accept=".txt,.md,.csv,text/plain,text/markdown"
          hidden
          onChange={(event) => void readFile(event)}
        />
      </div>
      <textarea
        id="library-content"
        className="settings-input library-text"
        dir="auto"
        rows={12}
        placeholder={"סד״כ = מצבת כוח האדם של המשמרת\nמ״מ = מפקד משמרת\nפונים למפקדים בגוף שני, בקצרה וללא סלנג."}
        value={draft.content}
        onChange={(event) => onChange({ ...draft, content: event.target.value })}
      />
      <p className={`models-status${tooLong ? " error" : ""}`}>
        {draft.content.length.toLocaleString("he-IL")} מתוך{" "}
        {limit.toLocaleString("he-IL")} תווים
      </p>
      <label className="field-label library-toggle">
        <input
          type="checkbox"
          checked={draft.enabled}
          onChange={(event) => onChange({ ...draft, enabled: event.target.checked })}
        />
        פעיל: הסוכן קורא את המסמך
      </label>
      <div className="library-buttons">
        <button
          type="button"
          className="primary-button"
          onClick={() => void save()}
          disabled={state.busy || tooLong || !draft.title.trim() || !draft.content.trim()}
        >
          <Save size={16} aria-hidden="true" /> {state.busy ? "שומר…" : "שמירת המסמך"}
        </button>
        <button type="button" className="ghost-button" onClick={onClose}>
          ביטול
        </button>
        {draft.id ? (
          <button
            type="button"
            className="danger-button"
            onClick={() => void remove()}
            disabled={state.busy}
          >
            <Trash2 size={15} aria-hidden="true" /> מחיקה
          </button>
        ) : null}
      </div>
    </div>
  );
}
