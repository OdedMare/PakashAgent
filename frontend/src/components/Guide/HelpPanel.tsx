"use client";

import {
  ArrowRight,
  BookOpen,
  Check,
  ChevronLeft,
  Compass,
  ExternalLink,
  Keyboard,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

import { glossaryFor, shortcutsFor } from "./content";
import type { Surface } from "./content";

/** One first step, derived by the surface from state it already holds.
 *  `done` is read, never set: the list reflects the workplace, and the only
 *  way to tick an item is to do the thing it names. */
export interface ChecklistItem {
  id: string;
  label: string;
  detail?: string;
  done: boolean;
  /** Where to go to do it. Navigation only. */
  actionLabel?: string;
  onAction?: () => void;
}

type View = "home" | "shortcuts" | "glossary";

const SURFACE_LABEL: Record<Surface, string> = {
  manager: "אזור הניהול",
  employee: "האזור האישי",
  member: "תצוגת הצוות",
  interview: "ראיון ההיכרות",
};

export function HelpPanel({
  surface,
  anchor,
  checklist,
  onAction,
  canTour,
  onTour,
  onClose,
}: {
  surface: Surface | null;
  anchor: HTMLElement | null;
  checklist: ChecklistItem[];
  onAction: (id: string) => void;
  canTour: boolean;
  onTour: () => void;
  onClose: () => void;
}) {
  const [view, setView] = useState<View>("home");
  const panel = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState<CSSProperties>({});

  // Open beside the button that opened it — which side depends on where the
  // drawer has pushed that button.
  useLayoutEffect(() => {
    const place = () => {
      if (!anchor || window.innerWidth < 640) {
        setPosition({});
        return;
      }
      const box = anchor.getBoundingClientRect();
      if (!box.width) {
        setPosition({});
        return;
      }
      const bottom = window.innerHeight - box.top + 10;
      setPosition(
        box.left < window.innerWidth / 2
          ? { bottom, left: Math.max(16, box.left) }
          : { bottom, right: Math.max(16, window.innerWidth - box.right) },
      );
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [anchor]);

  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
  }, [view]);

  // Esc closes; a click outside closes. The opening button is excluded so a
  // second click on it toggles instead of closing and reopening.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      if (view === "home") onClose();
      else setView("home");
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panel.current?.contains(target) || anchor?.contains(target)) return;
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [anchor, onClose, view]);

  const done = checklist.filter((item) => item.done).length;

  return (
    <div
      ref={panel}
      className="guide-panel"
      style={position}
      role="dialog"
      aria-label="עזרה ולמידה"
      tabIndex={-1}
    >
      <header className="guide-panel-head">
        {view === "home" ? (
          <div>
            <strong>עזרה ולמידה</strong>
            {surface ? <span>{SURFACE_LABEL[surface]}</span> : null}
          </div>
        ) : (
          <button type="button" className="guide-back" onClick={() => setView("home")}>
            <ArrowRight size={15} />
            {view === "shortcuts" ? "קיצורי מקלדת" : "מילון מונחים"}
          </button>
        )}
        <button type="button" className="guide-icon-button" onClick={onClose} aria-label="סגירת העזרה">
          <X size={15} />
        </button>
      </header>

      <div className="guide-panel-body">
        {view === "home" ? (
          <>
            {checklist.length ? (
              <section className="guide-checklist" aria-labelledby="guide-checklist-title">
                <div className="guide-checklist-head">
                  <h3 id="guide-checklist-title">
                    {done === checklist.length ? "הכול מוכן — אפשר לעבוד" : "צעדים ראשונים"}
                  </h3>
                  <span>
                    {done} מתוך {checklist.length}
                  </span>
                </div>
                <div
                  className="guide-progress"
                  role="progressbar"
                  aria-label="התקדמות בצעדים הראשונים"
                  aria-valuemin={0}
                  aria-valuemax={checklist.length}
                  aria-valuenow={done}
                >
                  <span style={{ width: `${(done / checklist.length) * 100}%` }} />
                </div>
                <ol>
                  {checklist.map((item) => (
                    <li key={item.id} className={item.done ? "is-done" : ""}>
                      <span className="guide-check" aria-hidden="true">
                        {item.done ? <Check size={12} strokeWidth={3} /> : null}
                      </span>
                      <span className="guide-check-copy">
                        <strong>
                          {item.label}
                          <span className="sr-only">{item.done ? " — בוצע" : " — עוד לא"}</span>
                        </strong>
                        {item.detail ? <small>{item.detail}</small> : null}
                      </span>
                      {!item.done && item.onAction ? (
                        <button type="button" className="guide-chip-button" onClick={() => onAction(item.id)}>
                          {item.actionLabel ?? "מעבר"}
                        </button>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </section>
            ) : null}

            <nav className="guide-links" aria-label="משאבי עזרה">
              {canTour ? (
                <button type="button" onClick={onTour}>
                  <Compass size={17} />
                  <span>
                    <strong>סיור מודרך במסך הזה</strong>
                    <small>כדקה, על המסך האמיתי, בלי לשנות דבר</small>
                  </span>
                  <ChevronLeft size={15} />
                </button>
              ) : null}
              <button type="button" onClick={() => setView("glossary")}>
                <BookOpen size={17} />
                <span>
                  <strong>מילון מונחים</strong>
                  <small>טיוטה, אזהרה, אילוץ, סבב — מה כל מילה אומרת</small>
                </span>
                <ChevronLeft size={15} />
              </button>
              <button type="button" onClick={() => setView("shortcuts")}>
                <Keyboard size={17} />
                <span>
                  <strong>קיצורי מקלדת</strong>
                  <small>מעבר בין שבועות ושליחה מהירה</small>
                </span>
                <ChevronLeft size={15} />
              </button>
              <Link href="/tutorial" target="_blank" rel="noopener">
                <ExternalLink size={17} />
                <span>
                  <strong>המדריך המלא</strong>
                  <small>מדריך מצולם לכל תפקיד, בלשונית חדשה</small>
                </span>
                <ChevronLeft size={15} />
              </Link>
            </nav>
            <p className="guide-panel-tip">
              טיפ: המקש <kbd>?</kbd> פותח את החלון הזה מכל מסך.
            </p>
          </>
        ) : view === "shortcuts" ? (
          <Shortcuts surface={surface} />
        ) : (
          <Glossary surface={surface} />
        )}
      </div>
    </div>
  );
}

function Shortcuts({ surface }: { surface: Surface | null }) {
  return (
    <div className="guide-shortcuts">
      {shortcutsFor(surface).map((group) => (
        <section key={group.title}>
          <h3>{group.title}</h3>
          <dl>
            {group.items.map((item) => (
              <div key={item.label}>
                <dt>
                  {item.keys.map((key, index) => (
                    <span key={key}>
                      {index ? <span className="guide-key-sep">{item.either ? "או" : "+"}</span> : null}
                      <kbd>{key}</kbd>
                    </span>
                  ))}
                </dt>
                <dd>{item.label}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

function Glossary({ surface }: { surface: Surface | null }) {
  const [query, setQuery] = useState("");
  const entries = useMemo(() => {
    const all = glossaryFor(surface);
    const needle = query.trim();
    if (!needle) return all;
    return all.filter((entry) => entry.term.includes(needle) || entry.definition.includes(needle));
  }, [surface, query]);

  return (
    <div className="guide-glossary">
      <label className="guide-search">
        <Search size={15} aria-hidden="true" />
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="חיפוש מונח"
          aria-label="חיפוש במילון המונחים"
        />
      </label>
      {entries.length ? (
        <dl>
          {entries.map((entry) => (
            <div key={entry.term}>
              <dt>{entry.term}</dt>
              <dd>{entry.definition}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="guide-empty">לא נמצא מונח כזה. נסו מילה אחרת.</p>
      )}
    </div>
  );
}
