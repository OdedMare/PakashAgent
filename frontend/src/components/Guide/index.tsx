"use client";

import { usePathname } from "next/navigation";
import { CircleHelp } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { TOURS } from "./content";
import type { Surface } from "./content";
import { HelpPanel } from "./HelpPanel";
import type { ChecklistItem } from "./HelpPanel";
import { Tour } from "./Tour";

export type { ChecklistItem } from "./HelpPanel";
export type { Surface } from "./content";

/** The in-app guide: a help button on every screen, a guided tour of the
 *  screen behind it, a first-steps checklist for the manager, keyboard
 *  shortcuts and a glossary.
 *
 *  **It writes nothing.** Every action a surface hands the guide is
 *  navigation — open a drawer, switch a view. The checklist reads state the
 *  surface already has; a checklist that could tick itself by doing the
 *  work would be a write path nobody reviewed.
 *
 *  What the browser remembers here — that a tour was seen, that the checklist
 *  was hidden — is a convenience for this one viewer, kept in `localStorage`
 *  and allowed to vanish. Nothing about the workplace lives in it. */

interface Registration {
  checklist?: ChecklistItem[];
  actions?: Record<string, () => void>;
}

interface GuideApi {
  enter: (surface: Surface) => void;
  leave: (surface: Surface) => void;
  update: (surface: Surface, registration: Registration) => void;
}

const GuideContext = createContext<GuideApi | null>(null);

const SEEN_KEY = (surface: Surface) => `pakash-guide-seen:${surface}`;

export function GuideProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [surface, setSurface] = useState<Surface | null>(null);
  const registration = useRef<Registration>({});
  // The checklist's visible shape. Callbacks live in the ref; this string is
  // what makes the panel re-render when an item is ticked.
  const [signature, setSignature] = useState("");
  const [panelOpen, setPanelOpen] = useState(false);
  const [touring, setTouring] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const fab = useRef<HTMLButtonElement>(null);

  const api = useMemo<GuideApi>(
    () => ({
      enter: (next) => setSurface(next),
      leave: (previous) => {
        setSurface((current) => (current === previous ? null : current));
        registration.current = {};
        setSignature("");
      },
      update: (_surface, next) => {
        registration.current = next;
        const sig = (next.checklist ?? [])
          .map((item) => `${item.id}:${item.done ? 1 : 0}:${item.detail ?? ""}`)
          .join("|");
        setSignature((previous) => (previous === sig ? previous : sig));
      },
    }),
    [],
  );

  const steps = surface ? TOURS[surface] : undefined;

  // Offer the tour once per surface per browser, a beat after the screen
  // settles so the targets exist. An offer, not a takeover: a manager who
  // came to fix tonight's shift should not have to dismiss a walkthrough.
  useEffect(() => {
    setWelcome(false);
    if (!surface || !steps?.length) return;
    if (readSeen(surface)) return;
    const timer = window.setTimeout(() => setWelcome(true), 1200);
    return () => window.clearTimeout(timer);
  }, [surface, steps]);

  const startTour = useCallback(() => {
    setPanelOpen(false);
    setWelcome(false);
    setTouring(true);
  }, []);

  const endTour = useCallback(
    (finished: boolean) => {
      setTouring(false);
      if (surface) writeSeen(surface, finished ? "done" : "skipped");
      fab.current?.focus({ preventScroll: true });
    },
    [surface],
  );

  const prepare = useCallback((action: string) => {
    registration.current.actions?.[action]?.();
  }, []);

  // `?` opens help from anywhere that is not a text field.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key !== "?") return;
      if (isTyping(event.target)) return;
      event.preventDefault();
      setPanelOpen((open) => !open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const checklist = useMemo(
    () => registration.current.checklist ?? [],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the signature is what tracks the ref
    [signature],
  );
  const remaining = checklist.filter((item) => !item.done).length;
  const onTutorialPage = pathname?.startsWith("/tutorial");

  return (
    <GuideContext.Provider value={api}>
      {children}
      {onTutorialPage ? null : (
        <>
          <button
            ref={fab}
            type="button"
            className={`tutorial-fab${panelOpen ? " is-open" : ""}`}
            onClick={() => setPanelOpen((open) => !open)}
            aria-expanded={panelOpen}
            aria-haspopup="dialog"
            aria-label={remaining ? `עזרה ולמידה — ${remaining} צעדים ראשונים פתוחים` : "עזרה ולמידה"}
            data-tour="help"
          >
            <CircleHelp size={19} />
            <span>עזרה</span>
            {remaining ? <em className="guide-fab-badge" aria-hidden="true">{remaining}</em> : null}
          </button>

          {panelOpen ? (
            <HelpPanel
              surface={surface}
              anchor={fab.current}
              checklist={checklist}
              canTour={Boolean(steps?.length)}
              onTour={startTour}
              onClose={() => setPanelOpen(false)}
            />
          ) : null}

          {welcome && !panelOpen && !touring && surface ? (
            <WelcomePrompt
              surface={surface}
              onStart={startTour}
              onDismiss={() => {
                setWelcome(false);
                writeSeen(surface, "skipped");
              }}
            />
          ) : null}

          {touring && steps?.length ? (
            <Tour steps={steps} onPrepare={prepare} onClose={endTour} />
          ) : null}
        </>
      )}
    </GuideContext.Provider>
  );
}

/** Tell the guide which screen is showing and what it can offer.
 *
 *  `checklist` and `actions` may be rebuilt every render; only a change in
 *  what the checklist *shows* reaches the panel. */
export function useGuideSurface(surface: Surface, registration: Registration = {}) {
  const api = useContext(GuideContext);
  useEffect(() => {
    api?.enter(surface);
    return () => api?.leave(surface);
  }, [api, surface]);
  useEffect(() => {
    api?.update(surface, registration);
  });
}

const WELCOME_COPY: Record<Surface, { title: string; body: string }> = {
  manager: {
    title: "ברוכים הבאים לאזור הניהול",
    body: "סיור של דקה יראה לכם איפה הלוח, הסוכן והכלים — על המסך האמיתי, בלי לשנות שום דבר.",
  },
  employee: {
    title: "ברוכים הבאים לאזור האישי",
    body: "סיור קצר: איפה המשמרות שלכם, מה השתנה, ואיך שולחים בקשה.",
  },
  member: {
    title: "זה הסידור של הצוות",
    body: "סיור קצר: מה רואים כאן ואיך נכנסים לאזור האישי.",
  },
  interview: {
    title: "ברוכים הבאים",
    body: "",
  },
};

function WelcomePrompt({
  surface,
  onStart,
  onDismiss,
}: {
  surface: Surface;
  onStart: () => void;
  onDismiss: () => void;
}) {
  const copy = WELCOME_COPY[surface];
  return (
    <section className="guide-welcome" role="status" aria-live="polite" aria-labelledby="guide-welcome-title">
      <span className="guide-welcome-mark" aria-hidden="true">
        <CircleHelp size={18} />
      </span>
      <div>
        <h2 id="guide-welcome-title">{copy.title}</h2>
        <p>{copy.body}</p>
        <div className="guide-welcome-actions">
          <button type="button" className="guide-primary-button" onClick={onStart}>
            התחלת הסיור
          </button>
          <button type="button" className="guide-ghost-button" onClick={onDismiss}>
            לא עכשיו
          </button>
        </div>
        <small>אפשר לחזור לסיור מכפתור ‘עזרה’ או במקש ?.</small>
      </div>
    </section>
  );
}

function readSeen(surface: Surface): boolean {
  try {
    return Boolean(window.localStorage.getItem(SEEN_KEY(surface)));
  } catch {
    // Storage blocked: offering the tour again is the harmless direction.
    return false;
  }
}

function writeSeen(surface: Surface, value: "done" | "skipped") {
  try {
    window.localStorage.setItem(SEEN_KEY(surface), value);
  } catch {
    /* A convenience; the guide works without it. */
  }
}

function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}
