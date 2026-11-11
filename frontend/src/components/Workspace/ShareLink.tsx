"use client";

import { Check, Copy, Link2, RefreshCw } from "lucide-react";
import { useRef, useState } from "react";

import { copyText } from "@/lib/clipboard";

/** The boss's view of the member share link.
 *
 *  Rotation is presented as the destructive action it is: it is the only
 *  revocation available, since members hold a link rather than an account, so
 *  it must be obvious that everyone currently using the old link loses
 *  access. */
export function ShareLink({
  token,
  busy,
  onRotate,
}: {
  token: string;
  busy: boolean;
  onRotate: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);

  // Built from the live origin rather than a configured base URL, so the link
  // is correct on localhost, on the LAN address the team actually opens, and
  // behind a proxy — without a setting anyone has to remember to change.
  const url =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/team/${token}`;

  const field = useRef<HTMLInputElement>(null);

  const copy = async () => {
    if (await copyText(url)) {
      setCopied(true);
      setCopyFailed(false);
      window.setTimeout(() => setCopied(false), 2000);
      return;
    }
    // Both clipboard routes refused (some mobile browsers). Select the link
    // so the boss is one long-press away from copying it by hand.
    setCopied(false);
    setCopyFailed(true);
    field.current?.focus();
    field.current?.select();
  };

  return (
    <section className="share-link">
      <h3>
        <Link2 size={15} /> קישור לצוות
      </h3>
      <p className="share-lede">
        שלחו את הקישור לעובדים. הוא פותח תצוגה לצפייה בלבד — בלי סיסמה ובלי
        אפשרות לערוך.
      </p>

      <div className="share-row">
        <input ref={field} dir="ltr" value={url} readOnly onFocus={(e) => e.target.select()} />
        <button type="button" onClick={() => void copy()}>
          {copied ? <Check size={15} /> : <Copy size={15} />}
          {copied ? "הועתק" : "העתקה"}
        </button>
      </div>
      {copyFailed ? (
        <p className="share-copy-error" role="status">
          הדפדפן לא איפשר העתקה אוטומטית — הקישור מסומן, העתיקו אותו ידנית.
        </p>
      ) : null}

      {confirming ? (
        <div className="share-confirm" role="alert">
          <p>
            יצירת קישור חדש תבטל את הקישור הנוכחי. עובדים שכבר קיבלו אותו לא
            יוכלו להיכנס יותר.
          </p>
          <div className="share-confirm-actions">
            <button
              type="button"
              className="danger"
              onClick={() => {
                setConfirming(false);
                onRotate();
              }}
              disabled={busy}
            >
              כן, בטלו את הקישור
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              ביטול
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="share-rotate"
          onClick={() => setConfirming(true)}
          disabled={busy}
        >
          <RefreshCw size={14} /> יצירת קישור חדש
        </button>
      )}
    </section>
  );
}
