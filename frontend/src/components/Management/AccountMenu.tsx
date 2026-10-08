"use client";

import { ChevronDown, LogOut, Settings2, UserCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/** The manager's account menu at the end of the top bar.
 *
 *  Signing out lives here rather than as a bare icon beside the theme toggle,
 *  so it cannot be hit by a click meant for the button next to it. Closes on
 *  Escape and on any pointer outside it, like the help panel. */
export function AccountMenu({
  name,
  onOpenSettings,
  onLogout,
}: {
  name: string;
  onOpenSettings: () => void;
  onLogout?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    };
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  const choose = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  return (
    <div className="account-menu" ref={root}>
      <button
        ref={trigger}
        type="button"
        className="account-menu-trigger"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="אפשרויות חשבון"
        title="אפשרויות חשבון"
      >
        <UserCircle size={18} />
        <span className="account-menu-name">{name}</span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open ? (
        <div className="account-menu-panel" role="menu" aria-label="אפשרויות חשבון">
          <div className="account-menu-head">
            <strong>{name}</strong>
            <span>מנהל/ת</span>
          </div>
          <button type="button" role="menuitem" onClick={choose(onOpenSettings)}>
            <Settings2 size={15} />
            הגדרות מערכת
          </button>
          {onLogout ? (
            <button
              type="button"
              role="menuitem"
              className="is-danger"
              onClick={choose(onLogout)}
            >
              <LogOut size={15} />
              התנתקות
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
