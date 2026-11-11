"use client";

import { RotateCcw, Save } from "lucide-react";
import { useState } from "react";

import type { EditablePrompt } from "@/types";

import { LibraryLoading, LibraryStatus } from "./LibraryStatus";
import { useLibrary } from "./useLibrary";
import type { LibraryController } from "./useLibrary";

/** The agents' own instructions, editable (D54). What ships with the
 *  release stays the default: a rewrite is kept beside it, and one press
 *  goes back. */
export function PromptSettings({ password }: { password: string }) {
  const state = useLibrary(password);
  const [name, setName] = useState("");
  // Edits not saved yet, per prompt, so looking at another prompt does not
  // throw away the one being written.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const { library } = state;

  if (!library) {
    return (
      <section className="settings-section library-wide">
        <h3>פרומפטים</h3>
        {state.error ? <LibraryStatus state={state} /> : <LibraryLoading />}
      </section>
    );
  }

  const prompt =
    library.prompts.find((row) => row.name === name) ?? library.prompts[0];
  const forget = (key: string) =>
    setDrafts(({ [key]: _dropped, ...rest }) => rest);

  return (
    <section className="settings-section library-wide">
      <h3>פרומפטים</h3>
      <p className="settings-hint library-intro">
        אלה ההנחיות שהסוכן מקבל בכל פנייה. אפשר לערוך כל אחת, ולחזור בכל רגע לנוסח המקורי.
      </p>
      <label className="field-label" htmlFor="library-prompt">פרומפט</label>
      <select
        id="library-prompt"
        className="settings-input"
        dir="auto"
        value={prompt.name}
        onChange={(event) => setName(event.target.value)}
      >
        {library.prompts.map((row) => (
          <option key={row.name} value={row.name}>
            {row.title}
            {row.overridden ? " (נערך)" : ""}
            {row.name in drafts ? " *" : ""}
          </option>
        ))}
      </select>
      <PromptEditor
        prompt={prompt}
        text={drafts[prompt.name] ?? prompt.text}
        limit={library.limits.prompt_chars}
        state={state}
        onChange={(text) =>
          text === prompt.text
            ? forget(prompt.name)
            : setDrafts((current) => ({ ...current, [prompt.name]: text }))
        }
        onSettled={() => forget(prompt.name)}
      />
      <LibraryStatus state={state} />
      <p className="settings-note">
        הפרומפטים מגדירים גם את מבנה התשובה שהמערכת מצפה לו (שמות השדות ב-JSON, הכלים
        והכללים). שינוי בחלקים האלה עלול לשבש את הסוכן, ולכן כדאי לערוך בעיקר ניסוח, טון
        והנחיות, ולבדוק את הסוכן אחרי שמירה. שורה מהצורה{" "}
        <code dir="ltr">{"<!-- include: shared/hebrew.md -->"}</code> משלבת קטע משותף. השינוי
        חל על כל הצוותים, בכל התהליכים, תוך שניות.
      </p>
    </section>
  );
}

function PromptEditor({
  prompt, text, limit, state, onChange, onSettled,
}: {
  prompt: EditablePrompt;
  text: string;
  limit: number;
  state: LibraryController;
  onChange: (text: string) => void;
  onSettled: () => void;
}) {
  const edited = text !== prompt.text;
  const tooLong = text.length > limit;

  const save = async () => {
    if (await state.savePrompt(prompt.name, text)) onSettled();
  };

  const reset = async () => {
    if (!window.confirm(
      `לשחזר את "${prompt.title}" לנוסח המקורי? העריכה שנשמרה תימחק.`,
    )) return;
    if (await state.resetPrompt(prompt.name)) onSettled();
  };

  return (
    <div className="library-editor">
      <p className="settings-hint">
        {prompt.description}{" "}
        <span className={`library-badge${prompt.overridden ? " is-edited" : ""}`}>
          {prompt.overridden ? "נוסח ערוך" : "נוסח מקורי"}
        </span>
      </p>
      {prompt.default_changed ? (
        <p className="models-status error" role="status">
          הנוסח המקורי התעדכן בגרסה חדשה של המערכת אחרי שהעריכה הזו נשמרה. ייתכן שחסרות
          בה הנחיות חדשות; כדאי לשחזר את ברירת המחדל ולערוך מחדש.
        </p>
      ) : null}
      <textarea
        aria-label={prompt.title}
        className="settings-input library-text library-prompt"
        // The prompts are written in English with Hebrew examples inside.
        dir="ltr"
        spellCheck={false}
        rows={22}
        value={text}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className={`models-status${tooLong ? " error" : ""}`}>
        {text.length.toLocaleString("he-IL")} תווים{edited ? " · יש שינויים שלא נשמרו" : ""}
      </p>
      <div className="library-buttons">
        <button
          type="button"
          className="primary-button"
          onClick={() => void save()}
          disabled={state.busy || !edited || tooLong || !text.trim()}
        >
          <Save size={16} aria-hidden="true" /> {state.busy ? "שומר…" : "שמירת הפרומפט"}
        </button>
        {edited ? (
          <button type="button" className="ghost-button" onClick={onSettled}>
            ביטול השינויים
          </button>
        ) : null}
        {prompt.overridden ? (
          <button
            type="button"
            className="danger-button"
            onClick={() => void reset()}
            disabled={state.busy}
          >
            <RotateCcw size={15} aria-hidden="true" /> שחזור ברירת המחדל
          </button>
        ) : null}
      </div>
    </div>
  );
}
