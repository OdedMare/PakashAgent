"use client";

import { Lightbulb } from "lucide-react";

import type { Message, Option } from "@/types";

interface Props {
  message: Message;
  /** Options are live only on the question still awaiting an answer. Past
   *  turns keep rendering theirs, disabled, so the boss can see what was
   *  offered without being able to answer a question twice. */
  live?: boolean;
  onSelect?: (label: string) => void;
}

export function Turn({ message, live = false, onSelect }: Props) {
  const assistant = message.role === "assistant";
  return (
    <article className={`turn ${message.role}`}>
      <div className="avatar" aria-hidden="true">
        {assistant ? "פ" : "א"}
      </div>
      <div className="turn-body">
        <div className="turn-name">{assistant ? "פקש" : "אתם"}</div>
        <p className="turn-text">{message.content}</p>

        {assistant && message.recommendation ? (
          <div className="recommendation">
            <Lightbulb size={15} />
            <span>{message.recommendation}</span>
          </div>
        ) : null}

        {assistant && message.options.length > 0 ? (
          <div className="options" role="group" aria-label="אפשרויות תשובה">
            {message.options.map((option) => (
              <OptionButton
                key={option.id}
                option={option}
                disabled={!live}
                onSelect={onSelect}
              />
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function OptionButton({
  option,
  disabled,
  onSelect,
}: {
  option: Option;
  disabled: boolean;
  onSelect?: (label: string) => void;
}) {
  return (
    <button
      type="button"
      className="option"
      disabled={disabled}
      // The label is sent, not the id and not an index. The prompt treats a
      // bare number as ambiguous — it may be a choice or a real value like a
      // headcount — so the answer has to arrive as the words the boss saw.
      onClick={() => onSelect?.(option.label)}
    >
      <span className="option-dot" aria-hidden="true" />
      <span className="option-label">{option.label}</span>
      {option.recommended ? (
        <span className="option-badge">מומלץ</span>
      ) : null}
    </button>
  );
}
