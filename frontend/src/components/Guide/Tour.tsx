"use client";

import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

import type { TourStep } from "./content";

/** A spotlight walk through the real screen.
 *
 *  The tour points at live elements by `data-tour` and never at a picture of
 *  them, so it cannot describe a layout the manager is not looking at. It is
 *  strictly a viewer: the overlay swallows every click, so nothing under it
 *  can be pressed by accident mid-tour, and the only things a step may do
 *  before showing are the navigation actions a surface registered.
 *
 *  Keys mirror the board's own: on a right-to-left screen ← is forward. The
 *  listener runs in the capture phase and marks the event handled, which is
 *  what `useBoardKeys` checks before paging the week underneath. */
export function Tour({
  steps,
  onPrepare,
  onClose,
}: {
  steps: TourStep[];
  onPrepare: (action: string) => void;
  onClose: (finished: boolean) => void;
}) {
  const [index, setIndex] = useState(-1);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [cardHeight, setCardHeight] = useState(DEFAULT_CARD_HEIGHT);
  // The latest callbacks, read at call time. Depending on them directly
  // would restart the tour from step one whenever the parent re-rendered.
  const prepareRef = useRef(onPrepare);
  const closeRef = useRef(onClose);
  useEffect(() => {
    prepareRef.current = onPrepare;
    closeRef.current = onClose;
  });
  const close = useCallback((finished: boolean) => closeRef.current(finished), []);
  const element = useRef<HTMLElement | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLButtonElement>(null);
  // Bumped on every navigation so a slow lookup for a step the visitor
  // already moved past cannot land on top of the current one.
  const token = useRef(0);

  const go = useCallback(
    async (target: number, direction: 1 | -1) => {
      const mine = ++token.current;
      let next = target;
      while (next >= 0 && next < steps.length) {
        const step = steps[next];
        if (step.prepare) prepareRef.current(step.prepare);
        const found = await waitFor(step.target, step.prepare ? 700 : 250);
        if (mine !== token.current) return;
        if (found || !step.optional) {
          element.current = found;
          if (found) reveal(found);
          setRect(found ? found.getBoundingClientRect() : null);
          setIndex(next);
          return;
        }
        next += direction;
      }
      // Ran off the end going forward: that is finishing. Off the start
      // going back cannot happen from a shown step, but stay put if it does.
      if (next >= steps.length) close(true);
    },
    [steps, close],
  );

  // Begin on the next frame, once the screen behind the tour has painted.
  useEffect(() => {
    const frame = requestAnimationFrame(() => void go(0, 1));
    return () => {
      cancelAnimationFrame(frame);
      token.current += 1;
    };
  }, [go]);

  // Follow the element while it scrolls, resizes or re-renders. A frame loop
  // rather than observers: the target can move for reasons no single
  // observer sees — a drawer sliding open, a banner appearing above it.
  useEffect(() => {
    if (index < 0) return;
    let frame = 0;
    const tick = () => {
      const node = element.current;
      if (node && node.isConnected) {
        const next = node.getBoundingClientRect();
        setRect((previous) => (sameRect(previous, next) ? previous : next));
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [index]);

  useLayoutEffect(() => {
    if (index < 0) return;
    primary.current?.focus({ preventScroll: true });
    if (card.current) setCardHeight(card.current.offsetHeight);
  }, [index]);

  const isLast = index === steps.length - 1;
  const next = useCallback(() => {
    if (isLast) close(true);
    else void go(index + 1, 1);
  }, [go, index, isLast, close]);
  const back = useCallback(() => {
    if (index > 0) void go(index - 1, -1);
  }, [go, index]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        close(false);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        event.stopPropagation();
        next();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        event.stopPropagation();
        back();
      } else if (event.key === "Tab") {
        // Keep focus inside the card: everything behind it is inert.
        const focusable = card.current?.querySelectorAll<HTMLElement>("button");
        if (!focusable?.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [next, back, close]);

  if (index < 0) return null;
  const step = steps[index];
  const spot = rect ? clampToViewport(rect) : null;

  return (
    <div className="guide-tour" role="presentation">
      {/* Swallows every click: a tour is read, not operated. */}
      <div className="guide-tour-catcher" aria-hidden="true" />
      {spot ? (
        <div className="guide-tour-spot" aria-hidden="true" style={spot} />
      ) : (
        <div className="guide-tour-dim" aria-hidden="true" />
      )}
      <div
        ref={card}
        className={`guide-tour-card${spot ? "" : " is-centered"}`}
        style={spot ? placeCard(spot, cardHeight) : undefined}
        role="dialog"
        aria-modal="true"
        aria-labelledby="guide-tour-title"
        aria-describedby="guide-tour-body"
      >
        <header>
          <span className="guide-tour-count" aria-live="polite">
            {index + 1} / {steps.length}
          </span>
          <button
            type="button"
            className="guide-icon-button"
            onClick={() => close(false)}
            aria-label="יציאה מהסיור"
          >
            <X size={15} />
          </button>
        </header>
        <h2 id="guide-tour-title">{step.title}</h2>
        <p id="guide-tour-body">{step.body}</p>
        <div className="guide-tour-dots" aria-hidden="true">
          {steps.map((item, dot) => (
            <span key={item.target} className={dot === index ? "is-active" : dot < index ? "is-done" : ""} />
          ))}
        </div>
        <footer>
          <button type="button" className="guide-link-button" onClick={() => close(false)}>
            דילוג על הסיור
          </button>
          <span className="guide-tour-nav">
            {index > 0 ? (
              <button type="button" className="guide-ghost-button" onClick={back}>
                <ArrowRight size={14} />
                הקודם
              </button>
            ) : null}
            <button ref={primary} type="button" className="guide-primary-button" onClick={next}>
              {isLast ? "סיום" : "הבא"}
              {isLast ? null : <ArrowLeft size={14} />}
            </button>
          </span>
        </footer>
      </div>
    </div>
  );
}

/** The element for a step, once it is in the document and has a size.
 *  Polled briefly because a prepare action (opening the drawer) renders on
 *  the next frame, not synchronously. */
async function waitFor(target: string, timeout: number): Promise<HTMLElement | null> {
  const deadline = performance.now() + timeout;
  for (;;) {
    const node = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
    if (node && isVisible(node)) return node;
    if (performance.now() > deadline) return null;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}

function isVisible(node: HTMLElement): boolean {
  if (node.closest("[hidden]")) return false;
  const box = node.getBoundingClientRect();
  return box.width > 0 && box.height > 0;
}

function reveal(node: HTMLElement) {
  const box = node.getBoundingClientRect();
  const inView = box.top >= 0 && box.bottom <= window.innerHeight;
  if (inView) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  node.scrollIntoView({ block: box.height > window.innerHeight * 0.7 ? "start" : "center", behavior: reduce ? "auto" : "smooth" });
}

function sameRect(a: DOMRect | null, b: DOMRect): boolean {
  return Boolean(a) && a!.top === b.top && a!.left === b.left && a!.width === b.width && a!.height === b.height;
}

const PAD = 6;

interface Spot {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** The highlight, padded and kept on screen — a board taller than the
 *  window would otherwise put its outline where nobody can see it. */
function clampToViewport(rect: DOMRect): Spot {
  const top = Math.max(4, rect.top - PAD);
  const left = Math.max(4, rect.left - PAD);
  const bottom = Math.min(window.innerHeight - 4, rect.bottom + PAD);
  const right = Math.min(window.innerWidth - 4, rect.right + PAD);
  return { top, left, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}

const CARD_WIDTH = 340;
const DEFAULT_CARD_HEIGHT = 250;
const GAP = 12;

/** Below the highlight if it fits, above if not, and over its lower edge
 *  when neither does. Phones dock the card to the bottom in CSS instead. */
function placeCard(spot: Spot, height: number): CSSProperties {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw < 640) return {};
  const width = Math.min(CARD_WIDTH, vw - 32);
  const center = spot.left + spot.width / 2;
  const left = Math.min(Math.max(16, center - width / 2), vw - width - 16);
  const below = spot.top + spot.height + GAP;
  if (below + height < vh) return { top: below, left, width };
  const above = spot.top - GAP - height;
  if (above > 0) return { top: above, left, width };
  // Neither side has room: a sidebar or a grid filling the window. Sit
  // beside it when there is width for that, else over its bottom edge.
  const spaceLeft = spot.left;
  const spaceRight = vw - spot.left - spot.width;
  if (spaceLeft > width + 2 * GAP) return { top: Math.max(16, Math.min(spot.top, vh - height - 16)), left: spot.left - width - GAP, width };
  if (spaceRight > width + 2 * GAP) return { top: Math.max(16, Math.min(spot.top, vh - height - 16)), left: spot.left + spot.width + GAP, width };
  return { top: vh - height - 16, left, width };
}
