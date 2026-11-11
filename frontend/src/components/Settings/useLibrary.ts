"use client";

import { useCallback, useEffect, useState } from "react";

import {
  deleteDocument, getLibrary, resetPrompt, saveDocument, savePrompt,
} from "@/services/api";
import type { PromptLibrary } from "@/types";

/** The organization's documents and the editable prompts (D54), for the two
 *  settings sections that show them. Every write answers with the whole
 *  library, so what is on screen is always what the server holds.
 *
 *  `run` reports success as a boolean rather than throwing: the editor keeps
 *  its draft open when a save is refused, and the reason is in `error`. */
export function useLibrary(password: string) {
  const [library, setLibrary] = useState<PromptLibrary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const run = useCallback(
    async (call: () => Promise<PromptLibrary>, done: string) => {
      setBusy(true);
      setError("");
      setMessage("");
      try {
        setLibrary(await call());
        setMessage(done);
        return true;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "הפעולה נכשלה");
        return false;
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  // The first read sets state only once the server answers, so it does not
  // go through `run`, whose "busy" flag would be set inside the effect.
  useEffect(() => {
    let current = true;
    getLibrary(password)
      .then((loaded) => { if (current) setLibrary(loaded); })
      .catch((reason) => {
        if (current) setError(reason instanceof Error ? reason.message : "הטעינה נכשלה");
      });
    return () => { current = false; };
  }, [password]);

  return {
    library, busy, error, message,
    saveDocument: (
      id: string, document: { title: string; content: string; enabled: boolean },
    ) => run(
      () => saveDocument(id, document, password),
      "המסמך נשמר. הסוכן יקרא אותו מהפנייה הבאה.",
    ),
    deleteDocument: (id: string) =>
      run(() => deleteDocument(id, password), "המסמך נמחק."),
    savePrompt: (name: string, text: string) => run(
      () => savePrompt(name, text, password),
      "הפרומפט נשמר ויחול על הפנייה הבאה.",
    ),
    resetPrompt: (name: string) => run(
      () => resetPrompt(name, password), "הפרומפט חזר לברירת המחדל.",
    ),
  };
}

export type LibraryController = ReturnType<typeof useLibrary>;
