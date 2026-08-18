"use client";

import { Check, Copy, Link2, RefreshCw } from "lucide-react";
import { useState } from "react";

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
  const [confirming, setConfirming] = useState(false);

  // Built from the live origin rather than a configured base URL, so the link
  // is correct on localhost, on the LAN address the team actually opens, and
  // behind a proxy — without a setting anyone has to remember to change.
  const url =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/team/${token}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access is refused on insecure origins and in some mobile
      // browsers. The input beside this stays selectable, so a failed copy
      // leaves the boss with a link they can still select by hand.
      setCopied(false);
    }
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
        <input value={url} readOnly onFocus={(e) => e.target.select()} />
        <button type="button" onClick={copy} disabled={busy}>
          {copied ? <Check size={15} /> : <Copy size={15} />}
          {copied ? "הועתק" : "העתקה"}
        </button>
      </div>

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
