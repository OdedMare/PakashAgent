"use client";

import { useCallback, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const STORAGE_KEY = "pakash.theme";

/** Light/dark toggle backed by `data-theme` on the root, which is what
 *  `tokens.css` keys its dark palette off. Falls back to the OS preference
 *  when the boss has never chosen.
 *
 *  The DOM attribute is the source of truth rather than React state: it is
 *  read by CSS, it is what the toggle actually has to change, and holding a
 *  second copy in state meant seeding it from `localStorage` inside an
 *  effect — a synchronous setState that cascades a render on every load. */
export function useTheme() {
  const theme = useSyncExternalStore(subscribe, current, () => "light" as Theme);

  const toggle = useCallback(() => {
    const next: Theme = current() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    window.localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return { theme, toggle };
}

const CHANGE_EVENT = "pakash:theme";

function current(): Theme {
  const applied = document.documentElement.dataset.theme as Theme | undefined;
  if (applied) return applied;
  // First paint: adopt the stored choice, or the OS preference, and write it
  // to the DOM so CSS and every later read agree.
  const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
  const initial =
    stored ??
    (window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light");
  document.documentElement.dataset.theme = initial;
  return initial;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => window.removeEventListener(CHANGE_EVENT, onChange);
}
