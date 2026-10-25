/** The two crossing guards from the entrance photo, drawn as small animated
 *  characters. They patrol whatever the app is waiting on — a build, an agent
 *  reply, a screen still loading — so a wait reads as "someone is on it"
 *  rather than as a frozen page.
 *
 *  Pure SVG and CSS (`styles/crew.css`): no images to fetch, and the motion
 *  stops under `prefers-reduced-motion`. */

import { useEffect, useState } from "react";

export type Who = "him" | "her";

/** Either guard, at random — which of the two is the agent this time. */
export function randomGuard(): Who {
  return Math.random() < 0.5 ? "him" : "her";
}

const SKIN: Record<Who, string> = { him: "#e9b896", her: "#c98f68" };

/** One guard, front-facing, holding the red stop sign. */
export function Guard({ who, face = false }: { who: Who; face?: boolean }) {
  const skin = SKIN[who];
  return (
    <svg
      className={`crew-guard crew-guard--${who}${face ? " crew-guard--face" : ""}`}
      viewBox={face ? "22 10 56 56" : "0 0 104 136"}
      aria-hidden="true"
    >
      {/* Legs swing from the hip while walking. */}
      <g className="crew-leg crew-leg--a">
        <rect x="40" y="100" width="8" height="26" rx="3" fill="#26262e" />
        <ellipse cx="43" cy="127" rx="6" ry="3" fill="#111" />
      </g>
      <g className="crew-leg crew-leg--b">
        <rect x="52" y="100" width="8" height="26" rx="3" fill="#26262e" />
        <ellipse cx="57" cy="127" rx="6" ry="3" fill="#111" />
      </g>

      <g className="crew-body">
        {who === "her" ? (
          <ellipse className="crew-ponytail" cx="73" cy="48" rx="6" ry="14" fill="#3b2a20" />
        ) : null}

        {/* Free arm */}
        <g className="crew-arm">
          <path d="M32 68 L26 92" stroke={skin} strokeWidth="6" strokeLinecap="round" />
          <circle cx="32" cy="68" r="6.5" fill="#f6f6f2" />
        </g>

        {/* T-shirt, then the high-visibility vest over it */}
        <rect x="30" y="62" width="40" height="44" rx="12" fill="#f6f6f2" />
        <path d="M30 72 Q30 62 42 62 L46 62 L50 80 L50 106 L36 106 Q30 106 30 100 Z" fill="#dcf51c" />
        <path d="M70 72 Q70 62 58 62 L54 62 L50 80 L50 106 L64 106 Q70 106 70 100 Z" fill="#dcf51c" />
        <rect x="30" y="88" width="40" height="3.5" fill="#b9bdc2" />
        <rect x="30" y="96" width="40" height="3.5" fill="#b9bdc2" />
        <path d="M44 62 L50 78 L56 62" fill="none" stroke="#f2c400" strokeWidth="1.6" />
        <rect className="crew-whistle" x="47.5" y="77" width="5" height="7" rx="1.5" fill="#f5c800" />

        {/* Head */}
        <rect x="45" y="54" width="10" height="10" fill={skin} />
        <circle cx="28.5" cy="40" r="4" fill={skin} />
        <circle cx="71.5" cy="40" r="4" fill={skin} />
        <circle cx="50" cy="38" r="22" fill={skin} />

        {who === "him" ? (
          <>
            <path d="M28 36 Q27 13 50 14 Q73 13 72 36 Q67 23 50 23 Q34 23 28 36 Z" fill="#6b4a2f" />
            <path d="M29 42 Q31 62 50 62 Q69 62 71 42 Q66 53 50 54 Q34 53 29 42 Z" fill="#6b4a2f" opacity="0.85" />
            <path d="M45 50 Q50 52.5 55 50" fill="none" stroke="#5a3422" strokeWidth="1.8" strokeLinecap="round" />
            <rect x="32.5" y="32" width="15" height="9" rx="2" fill="#23281f" stroke="#55654a" strokeWidth="1.6" />
            <rect x="52.5" y="32" width="15" height="9" rx="2" fill="#23281f" stroke="#55654a" strokeWidth="1.6" />
            <path d="M47.5 35 L52.5 35" stroke="#55654a" strokeWidth="1.6" />
          </>
        ) : (
          <>
            <path d="M27 40 Q25 14 50 15 Q75 14 73 40 Q70 25 56 24 Q44 30 30 30 Q28 34 27 40 Z" fill="#3b2a20" />
            <ellipse cx="42" cy="37" rx="7" ry="4.5" fill="#1e1e22" stroke="#c9a24a" strokeWidth="1.2" />
            <ellipse cx="58" cy="37" rx="7" ry="4.5" fill="#1e1e22" stroke="#c9a24a" strokeWidth="1.2" />
            <path d="M49 36 L51 36" stroke="#c9a24a" strokeWidth="1.2" />
            <path d="M42 47 Q50 56 58 47 Z" fill="#fff" stroke="#8a3b2f" strokeWidth="1.5" strokeLinejoin="round" />
            <circle cx="28.5" cy="47" r="3.5" fill="none" stroke="#d4a537" strokeWidth="1.3" />
            <circle cx="71.5" cy="47" r="3.5" fill="none" stroke="#d4a537" strokeWidth="1.3" />
          </>
        )}
        <path className="crew-glint" d="M35 34 L39 34" stroke="#fff" strokeWidth="1.2" strokeLinecap="round" />

        {/* Sign arm and the stop sign, which waves from the hand */}
        <path d="M68 68 Q80 70 86 80" fill="none" stroke={skin} strokeWidth="6" strokeLinecap="round" />
        <circle cx="68" cy="68" r="6.5" fill="#f6f6f2" />
        <g className="crew-sign">
          <rect x="84.5" y="34" width="3" height="52" rx="1.5" fill="#f6d200" />
          <circle cx="86" cy="26" r="15" fill="#d9232d" />
          <circle cx="86" cy="26" r="12" fill="none" stroke="#fff" strokeWidth="1.5" />
          <g fill="#fff" transform="translate(86 27)">
            <rect x="-4.2" y="-2" width="8.4" height="8" rx="2.4" />
            <rect x="-4.2" y="-7" width="1.8" height="7" rx="0.9" />
            <rect x="-2" y="-8.6" width="1.8" height="8.6" rx="0.9" />
            <rect x="0.2" y="-8.2" width="1.8" height="8.2" rx="0.9" />
            <rect x="2.4" y="-6.6" width="1.8" height="6.6" rx="0.9" />
            <rect x="4" y="-0.6" width="1.8" height="5" rx="0.9" transform="rotate(32 4.9 1.9)" />
          </g>
          <circle cx="86" cy="80" r="4" fill={skin} />
        </g>
      </g>
    </svg>
  );
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
