"use client";

import { Sparkles } from "lucide-react";

import type { AgentTouch } from "./agentTouch";

/** The line between the conversation and the week.
 *
 *  The agent's cards live in the control room; the manager lives on this
 *  board. Without something naming the connection, a lit cell is a mystery
 *  and the sentence explaining it is one screen away with nothing pointing
 *  at it. This says what kind of attention is on the week, how much of it,
 *  and offers the one action that makes sense here — going to read it.
 *
 *  **It carries no operation and no confirm.** Approving a simulation or a
 *  proposal happens where it always did, with the manager's reason
 *  (D8/D12/D20). A shortcut from this bar to a write is precisely the
 *  second write path those decisions exist to prevent. */
export function AgentTouchBar({
  touches,
  onOpenAgent,
}: {
  touches: Map<string, AgentTouch[]>;
  onOpenAgent?: () => void;
}) {
  // Counted by origin rather than listed: a week where the agent touched
  // nine cells needs a sentence, not nine chips.
  const counts = { proposal: 0, simulation: 0, answer: 0 };
  for (const list of touches.values()) {
    const strongest = list[list.length - 1];
    counts[strongest.origin] += 1;
  }

  const said: string[] = [];
  if (counts.proposal) said.push(`מציע שינוי ב-${counts.proposal} משמרות`);
  if (counts.simulation) {
    said.push(`מדמה שינוי ב-${counts.simulation} משמרות`);
  }
  if (counts.answer) said.push(`בדק ${counts.answer} משמרות כדי לענות`);

  return (
    <div className="board-agent-bar" role="status">
      <Sparkles size={14} />
      <span className="board-agent-bar-text">
        הסוכן {said.join(", ")} — מסומן על הלוח.
      </span>
      {onOpenAgent ? (
        <button type="button" className="ghost-button" onClick={onOpenAgent}>
          מעבר לשיחה
        </button>
      ) : null}
    </div>
  );
}
