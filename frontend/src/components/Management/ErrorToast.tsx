"use client";

import { AlertCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

/** A refused or failed action, said over the board instead of above it.
 *
 *  It used to be an unstyled line at the top of the page that pushed the
 *  whole board down. It now floats at the bottom of the screen in the same
 *  card shape as the request pop-up, leaves on its own after a while, and
 *  stays while the pointer or focus is on it so a long sentence can be read
 *  to the end. A new message restarts the timer. */
export function ErrorToast({
  message,
  onClose,
}: {
  message: string | null;
  onClose: () => void;
}) {
  const [held, setHeld] = useState(false);

  useEffect(() => {
    if (!message || held) return;
    const timer = window.setTimeout(onClose, 9000);
    return () => window.clearTimeout(timer);
  }, [message, held, onClose]);

  if (!message) return null;

  return (
    <div
      className="system-toast is-error"
      role="alert"
      onMouseEnter={() => setHeld(true)}
      onMouseLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <span className="system-toast-icon" aria-hidden="true">
        <AlertCircle size={17} />
      </span>
      <div className="system-toast-body">
        <strong>הפעולה לא בוצעה</strong>
        <span>{message}</span>
      </div>
      <button
        type="button"
        className="icon-button system-toast-close"
        onClick={onClose}
        aria-label="סגירת ההודעה"
      >
        <X size={15} />
      </button>
    </div>
  );
}
