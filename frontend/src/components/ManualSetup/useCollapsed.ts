"use client";

import { useCallback, useState } from "react";

const STORAGE_KEY = "pakash-setup-collapsed";

function read(sections: readonly string[]): Set<string> {
  try {
    const stored: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]");
    return new Set(Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string" && sections.includes(id)) : []);
  } catch {
    // No window (server render), a private window or blocked storage: all open.
    return new Set();
  }
}

function write(collapsed: Set<string>) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...collapsed]));
  } catch {
    // Not remembered; the fold still applies for this visit.
  }
}

/** Which setup sections are folded away. A habit of this browser, like the
 *  shift-row order: nothing is written to the server, and a folded section
 *  keeps its fields mounted, so nothing typed into it is lost or left out of
 *  the save. The setup screen mounts only after the session check on the
 *  client, so reading storage in the initializer cannot disagree with a
 *  server render. */
export function useCollapsed(sections: readonly string[]) {
  const [collapsed, setCollapsed] = useState<Set<string>>(() => read(sections));

  const toggle = useCallback((id: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      write(next);
      return next;
    });
  }, []);

  const allCollapsed = sections.every((id) => collapsed.has(id));
  const toggleAll = useCallback(() => {
    const next = allCollapsed ? new Set<string>() : new Set(sections);
    write(next);
    setCollapsed(next);
  }, [allCollapsed, sections]);

  return { isCollapsed: (id: string) => collapsed.has(id), toggle, allCollapsed, toggleAll };
}
