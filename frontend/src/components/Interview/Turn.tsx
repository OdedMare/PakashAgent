"use client";

import { Lightbulb } from "lucide-react";

import type { Message, Option } from "@/types";

interface Props {
  message: Message;
  /** Options are live only on the question still awaiting an answer. Past
   *  turns keep rendering theirs, disabled, so the boss can see what was
   *  offered without being able to answer a question twice. */
  live?: boolean;
  onSelect?: (answer: string) => void;
}

export function Turn({ message, live = false, onSelect }: Props) {
  const assistant = message.role === "assistant";
  const why = message.question?.why;
  return (
    <article className={`turn ${message.role}`}>
      <div className="avatar" aria-hidden="true">
        {assistant ? "פ" : "א"}
      </div>
      <div className="turn-body">
        <div className="turn-name">
          {assistant ? "פקש · מסייע AI" : "אתם"}
        </div>
        <p className="turn-text">{message.content}</p>

        {/* The question is kept separate from the reply above it: the reply
            reacts to the last answer, the question is what is being asked
            now, and running them together buries the ask in the prose. */}
        {assistant && message.question ? (
          <p className="turn-question">{message.question.question}</p>
        ) : null}

        {assistant && message.recommendation ? (
          <div className="recommendation">
            <Lightbulb size={15} />
            <span>
              {message.recommendation}
              {/* Why it matters, so the boss can weigh the recommendation
                  rather than only accept or reject it. */}
              {why ? <em className="recommendation-why">{why}</em> : null}
            </span>
          </div>
        ) : null}

        {assistant && message.options.length > 0 ? (
          <div className="options" role="group" aria-label="אפשרויות תשובה">
            {message.options.map((option, index) => (
              <OptionButton
                key={option.label}
                option={option}
                // The first option is the agent's recommendation, so
                // accepting it is one click.
                recommended={index === 0}
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
  recommended,
  disabled,
  onSelect,
}: {
  option: Option;
  recommended: boolean;
  disabled: boolean;
  onSelect?: (answer: string) => void;
}) {
  return (
    <button
      type="button"
      className="option"
      disabled={disabled}
      // `answer` is sent, never the label and never an index. The label is a
      // button caption; the answer is a full sentence, so a click and a typed
      // reply reach the model as the same kind of thing. Sending a number
      // would be exactly the ambiguity the prompt guards against.
      onClick={() => onSelect?.(option.answer)}
    >
      <span className="option-dot" aria-hidden="true" />
      <span className="option-label">{option.label}</span>
      {recommended ? <span className="option-badge">מומלץ</span> : null}
    </button>
  );
}
