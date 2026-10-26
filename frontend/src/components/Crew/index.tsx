/** The two crossing guards, drawn as small animated
 *  characters. They patrol whatever the app is waiting on — a build, an agent
 *  reply, a screen still loading — so a wait reads as "someone is on it"
 *  rather than as a frozen page.
 *
 *  Pure SVG and CSS (`styles/crew.css`): no images to fetch, and the motion
 *  stops under `prefers-reduced-motion`. */

import { useEffect, useState } from "react";

import { Guard } from "./Guard";
import type { Who } from "./Guard";

export { Guard };
export type { Who };

/** Either guard, at random — which of the two is the agent this time. */
export function randomGuard(): Who {
  return Math.random() < 0.5 ? "him" : "her";
}

/** The pair patrolling a strip, with an optional line of what they wait on.
 *
 *  `size` picks the stage height: `sm` sits inside a chat bubble or a banner,
 *  `lg` fills a screen that is still loading. */
export function CrewStage({
  label,
  size = "md",
  only,
  className = "",
}: {
  label?: React.ReactNode;
  size?: "sm" | "md" | "lg";
  /** Just this guard — the one who is the agent right now. */
  only?: Who;
  className?: string;
}) {
  return (
    <div className={`crew-stage crew-stage--${size} ${className}`.trim()} role={label ? "status" : undefined}>
      <div className="crew-track" aria-hidden="true">
        <div className={`crew-walker${only ? " is-solo" : ""}`}>
          {only ? <Guard who={only} /> : <><Guard who="him" /><Guard who="her" /></>}
        </div>
      </div>
      {label ? <p className="crew-label">{label}</p> : null}
    </div>
  );
}

/** A whole screen that has not answered yet. Replaces the bare `aria-busy`
 *  placeholders, so a slow first load shows the crew instead of a blank page. */
export function CrewLoading({ label = "רגע, מכינים הכול…", className = "workspace-gate" }: {
  label?: string;
  className?: string;
}) {
  return (
    <div className={`${className} crew-loading`} aria-busy="true">
      <CrewStage size="lg" label={label} />
    </div>
  );
}

/** The agent, standing in the corner of the board as one of the two guards.
 *  Pressing it opens the conversation. Which guard it is changes at random
 *  every so often, so the agent has both faces. */
export function AgentGuard({ who, onOpen, onSwap }: {
  who: Who;
  onOpen: () => void;
  /** Asked for a new face; the owner rolls one, so the chat that opens
   *  shows the same guard that was pressed. */
  onSwap: () => void;
}) {
  const [greeting, setGreeting] = useState(true);

  useEffect(() => {
    const quiet = window.setTimeout(() => setGreeting(false), 6000);
    const swap = window.setInterval(onSwap, 25000);
    return () => {
      window.clearTimeout(quiet);
      window.clearInterval(swap);
    };
  }, [onSwap]);

  return (
    <button
      type="button"
      className={`crew-agent${greeting ? " is-greeting" : ""}`}
      onClick={onOpen}
      aria-label="פתיחת שיחה עם סוכן הסידור"
      title="שיחה עם סוכן הסידור"
    >
      <span className="crew-agent-bubble" aria-hidden="true">
        {who === "her" ? "היי! אני כאן לכל שאלה על הסידור" : "היי! צריכים עזרה בסידור?"}
      </span>
      <span key={who} className="crew-agent-figure">
        <Guard who={who} />
      </span>
    </button>
  );
}
