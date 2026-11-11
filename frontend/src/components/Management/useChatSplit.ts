"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";

/** How the desktop workspace divides between the agent and the board.
 *
 *  Kept as a share of the workspace, not pixels: a width chosen on a wide
 *  monitor would leave no board at all on a laptop, while "the agent gets a
 *  third" means the same thing on both. Each side keeps a floor in pixels so
 *  neither can be dragged into something unusable. A per-browser
 *  convenience, like the shift-row order — nothing about it is stored on the
 *  server. */
const SHARE_KEY = "pakash-chat-share";
const DEFAULT_SHARE = 0.45;
const MIN_CHAT_PX = 340;
const MIN_BOARD_PX = 320;
const STEP = 0.02;

function read(): number | null {
  try {
    const value = Number(window.localStorage.getItem(SHARE_KEY));
    return value > 0 && value < 1 ? value : null;
  } catch {
    return null;
  }
}

function write(share: number | null) {
  try {
    if (share === null) window.localStorage.removeItem(SHARE_KEY);
    else window.localStorage.setItem(SHARE_KEY, share.toFixed(4));
  } catch {
    // Private windows and blocked storage just forget the split.
  }
}

export function useChatSplit() {
  const workspace = useRef<HTMLElement>(null);
  const [share, setShareState] = useState(DEFAULT_SHARE);
  const [resizing, setResizing] = useState(false);
  // Pointer and key handlers read the share between renders.
  const latest = useRef(DEFAULT_SHARE);
  const setShare = useCallback((value: number) => {
    latest.current = value;
    setShareState(value);
  }, []);

  /** Keep a share inside both floors for the workspace as it is now. */
  const clamp = useCallback((value: number) => {
    const width = workspace.current?.getBoundingClientRect().width ?? 0;
    if (width <= MIN_CHAT_PX + MIN_BOARD_PX) return 0.5;
    const low = MIN_CHAT_PX / width;
    const high = 1 - MIN_BOARD_PX / width;
    return Math.min(high, Math.max(low, value));
  }, []);

  /** The share that puts the divider under the pointer. The agent sits on the
   *  inline-start side, so in RTL its width is measured from the right edge. */
  const shareAt = useCallback((clientX: number) => {
    const node = workspace.current;
    if (!node) return latest.current;
    const rect = node.getBoundingClientRect();
    const rtl = getComputedStyle(node).direction === "rtl";
    const chat = rtl ? rect.right - clientX : clientX - rect.left;
    return clamp(chat / rect.width);
  }, [clamp]);

  useEffect(() => {
    // Storage only exists after mount (the page is server-rendered). A share
    // saved on a wide monitor must not squeeze the board on a laptop, so what
    // is shown is re-fitted on resize while what was chosen stays stored.
    const fit = () => {
      const stored = read() ?? DEFAULT_SHARE;
      setShare(clamp(stored));
    };
    const frame = requestAnimationFrame(fit);
    window.addEventListener("resize", fit);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", fit);
    };
  }, [clamp, setShare]);

  const commit = useCallback((value: number) => {
    setShare(value);
    write(value);
  }, [setShare]);

  const reset = useCallback(() => {
    setShare(DEFAULT_SHARE);
    write(null);
  }, [setShare]);

  const handle = {
    onPointerDown(event: PointerEvent<HTMLElement>) {
      if (event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      setResizing(true);
    },
    onPointerMove(event: PointerEvent<HTMLElement>) {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      setShare(shareAt(event.clientX));
    },
    onPointerUp(event: PointerEvent<HTMLElement>) {
      if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
      event.currentTarget.releasePointerCapture(event.pointerId);
    },
    onLostPointerCapture() {
      setResizing(false);
      write(latest.current);
    },
    onDoubleClick: reset,
    onKeyDown(event: KeyboardEvent<HTMLElement>) {
      // Arrows move the divider the way it looks like it moves: in RTL the
      // agent is on the right, so ArrowLeft widens it.
      const rtl = workspace.current ? getComputedStyle(workspace.current).direction === "rtl" : true;
      const widen = rtl ? "ArrowLeft" : "ArrowRight";
      const narrow = rtl ? "ArrowRight" : "ArrowLeft";
      if (event.key === widen) commit(clamp(latest.current + STEP));
      else if (event.key === narrow) commit(clamp(latest.current - STEP));
      else if (event.key === "Home") commit(clamp(0));
      else if (event.key === "End") commit(clamp(1));
      else if (event.key === "Enter") reset();
      else return;
      event.preventDefault();
    },
  };

  return { workspace, share, resizing, handle };
}
