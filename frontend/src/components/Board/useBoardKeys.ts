"use client";

import { useEffect } from "react";

/** Keyboard shortcuts for moving around the week.
 *
 *  Paging a week is the board's most repeated act and it cost a mouse trip to
 *  a specific arrow every time. These are navigation only — **nothing here
 *  writes, and nothing here opens a dialog that could write.** A shortcut
 *  that moved a shift would be a second write path around the confirmation
 *  (D12), so the bindings deliberately stop at "show me a different week".
 *
 *  **Mirrored for RTL, like the arrows themselves.** On a right-to-left board
 *  the previous week sits to the right, so `ArrowRight` goes back — the same
 *  reversal `WeekNav` applies to its chevrons. Binding them the LTR way would
 *  send the manager the wrong direction on every press.
 *
 *  Typing is never interrupted: a key pressed inside an input, a textarea, a
 *  select or anything `contenteditable` belongs to that field. Nor does a
 *  shortcut fire while a modifier is held, where it would be the browser's or
 *  the OS's chord rather than the board's.
 */
export function useBoardKeys(input: {
  onPrevious: () => void;
  onNext: () => void;
  onToday: () => void;
  /** Off while a dialog is open: the confirmation owns the keyboard then,
   *  and paging the week under an open dialog would leave it describing a
   *  cell that is no longer on screen. */
  enabled: boolean;
}): void {
  const { onPrevious, onNext, onToday, enabled } = input;

  useEffect(() => {
    if (!enabled) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target)) return;

      switch (event.key) {
        // Right is *back* — see the note above.
        case "ArrowRight":
          event.preventDefault();
          onPrevious();
          break;
        case "ArrowLeft":
          event.preventDefault();
          onNext();
          break;
        case "t":
        case "T":
        // The same physical key on a Hebrew layout, so the shortcut does not
        // stop working the moment the manager types a sentence to the agent.
        case "א":
          event.preventDefault();
          onToday();
          break;
        default:
          break;
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, onPrevious, onNext, onToday]);
}

/** Whether the event landed somewhere the manager is entering text.
 *
 *  Checked on the *event target* rather than `document.activeElement` so a
 *  key pressed inside a shadow-hosted or portalled field is still recognised
 *  as typing. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}
