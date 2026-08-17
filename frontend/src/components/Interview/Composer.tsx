"use client";

import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface Props {
  disabled: boolean;
  onSend: (content: string) => void;
}

/** The free-text answer path. It is a separate field from the option
 *  buttons, never an "other" option in the list — the prompt forbids that,
 *  because an option called "אחר" makes free text look like a last resort
 *  (bl/prompts/interview.md). */
export function Composer({ disabled, onSend }: Props) {
  const [value, setValue] = useState("");
  const textarea = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to the CSS max-height, then scroll.
  useEffect(() => {
    const node = textarea.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  }, [value]);

  const submit = () => {
    const content = value.trim();
    if (!content || disabled) return;
    onSend(content);
    setValue("");
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={textarea}
          rows={1}
          value={value}
          disabled={disabled}
          placeholder="כתבו תשובה משלכם…"
          aria-label="תשובה חופשית"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={(event) => {
            // Enter sends; Shift+Enter is a newline. A multi-line answer is
            // common here — a list of employees, a rule in the boss's own
            // words — so the newline has to stay reachable.
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="composer-row">
          <span className="composer-hint">
            Enter לשליחה · Shift+Enter לשורה חדשה
          </span>
          <button
            type="button"
            className="send"
            disabled={disabled || !value.trim()}
            onClick={submit}
            aria-label="שליחה"
          >
            <ArrowLeft size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
