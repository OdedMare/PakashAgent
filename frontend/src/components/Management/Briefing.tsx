"use client";

import {
  CheckCircle2,
  Inbox,
  Repeat2,
  Scale,
  Sparkles,
  TrendingUp,
  TriangleAlert,
  X,
} from "lucide-react";
import type { ReactNode } from "react";

import type { Briefing as BriefingData, BriefingKind } from "@/types";

/** The agent speaking first — what it noticed without being asked
 *  ([D15](../../../docs/DECISIONS.md#d15--the-agent-speaks-first-but-still-never-writes)).
 *
 *  The whole surface is *saying*, never *doing*. A suggestion is a button
 *  that types a sentence into the conversation for the manager to send; it
 *  applies nothing, and the ordinary propose-then-confirm path still runs
 *  after it. That is why the button reads "לשאול את הסוכן" rather than
 *  anything resembling "apply" — an item the manager could click to change
 *  the schedule would reverse D3, D8 and D12 in one control.
 *
 *  A quiet briefing renders as a single calm line rather than disappearing.
 *  "בדקתי, נראה תקין" is the agent's most valuable output after a generated
 *  week, and hiding it would leave the manager unsure whether it looked at
 *  all. */
export function Briefing({
  briefing,
  busy,
  onAsk,
  onDismiss,
}: {
  briefing: BriefingData | null;
  busy: boolean;
  onAsk: (suggestion: string) => void;
  onDismiss: () => void;
}) {
  if (!briefing) return null;

  return (
    <section className="briefing" aria-label="מה הסוכן שם לב אליו" aria-busy={busy}>
      <header className="briefing-header">
        <span className="brand-mark" aria-hidden="true">
          <Sparkles size={15} />
        </span>
        <div className="briefing-headline">
          {briefing.quiet ? (
            <span className="briefing-quiet">
              <CheckCircle2 size={14} />
              {briefing.headline || "בדקתי את הסידור — לא מצאתי משהו דחוף."}
            </span>
          ) : (
            <strong>{briefing.headline}</strong>
          )}
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onDismiss}
          aria-label="סגירת התדריך"
          title="סגירת התדריך"
        >
          <X size={15} />
        </button>
      </header>

      {briefing.items.length ? (
        <ul className="briefing-items">
          {briefing.items.map((item, index) => (
            <li key={`${item.kind}-${index}`} className={`briefing-item ${item.kind}`}>
              <span className="briefing-icon" aria-hidden="true">
                {iconFor(item.kind)}
              </span>
              <div className="briefing-body">
                <p>{item.text}</p>
                {/* Sends the sentence to the composer. Nothing is applied —
                    the agent still proposes and the manager still confirms
                    with a reason, exactly as if they had typed it (D8). */}
                {item.suggestion ? (
                  <button
                    type="button"
                    className="briefing-ask"
                    onClick={() => onAsk(item.suggestion)}
                    disabled={busy}
                  >
                    {item.suggestion}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

/** Presentation only, exactly like the audit's severity. Nothing branches on
 *  `kind` beyond which glyph sits beside the line. */
function iconFor(kind: BriefingKind): ReactNode {
  if (kind === "rotation") return <Repeat2 size={14} />;
  if (kind === "fairness") return <Scale size={14} />;
  if (kind === "gap") return <TriangleAlert size={14} />;
  if (kind === "request") return <Inbox size={14} />;
  if (kind === "pattern") return <TrendingUp size={14} />;
  return <TriangleAlert size={14} />;
}
