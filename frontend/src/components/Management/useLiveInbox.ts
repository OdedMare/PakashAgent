"use client";

import { useEffect, useRef } from "react";

import { managerEvents } from "@/services/api";

type Handlers = { requests?: () => void; swaps?: () => void };

/** Re-read an inbox the moment an employee touches it.
 *
 *  The server pushes a bare "the requests (or swaps) inbox moved" over
 *  Server-Sent Events; the handlers re-read through the ordinary routes. So
 *  the pop-up appears within a second of an employee pressing send, instead
 *  of on the next 15-second poll — which stays in place underneath as the
 *  backstop for a dropped stream.
 *
 *  `EventSource` reconnects on its own, including after the server closes
 *  the stream every few minutes to re-check the session. A reconnect also
 *  re-reads both inboxes, since anything sent while the line was down
 *  produced no event to hear. */
export function useLiveInbox(handlers: Handlers) {
  // The stream outlives renders; always call the latest handlers.
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const source = managerEvents();
    const requests = () => latest.current.requests?.();
    const swaps = () => latest.current.swaps?.();
    let opened = false;
    const onOpen = () => {
      // The first open is not a reconnect: the inboxes just loaded.
      if (opened) {
        requests();
        swaps();
      }
      opened = true;
    };
    source.addEventListener("open", onOpen);
    source.addEventListener("requests", requests);
    source.addEventListener("swaps", swaps);
    return () => source.close();
  }, []);
}
