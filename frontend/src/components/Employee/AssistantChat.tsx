"use client";

import { ArrowLeftRight, Check, LoaderCircle, MessageCircle, RotateCcw, Send, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Markdown } from "@/components/Markdown";
import type { AssistantShift, AssistantSuggestion } from "@/types";
import { shortDate } from "@/components/DateInput";

import type { AssistantMessage, useAssistant } from "./useAssistant";

const STARTERS = [
  "עם מי אפשר להחליף משמרת?",
  "איך אפשר לשפר את השבוע שלי?",
  "יש לי בעיה במשמרת הקרובה, מה אפשר לעשות?",
];

/** The employee's assistant: ask about swaps and about one's own week (D27).
 *
 *  Deliberately small next to the manager's chat: no history list, no plans,
 *  no approvals. It answers, and it may attach swaps the audit already found
 *  clean. The one button on a swap sends the **ordinary swap offer** — the
 *  same request the form under "בקשות והחלפות" sends — so the colleague
 *  still answers and the manager still decides (D14). The card says that at
 *  the moment of the click. */
export function AssistantChat({
  assistant,
  busy,
  onOffer,
}: {
  assistant: ReturnType<typeof useAssistant>;
  busy: boolean;
  onOffer: (body: {
    assignment_id: string;
    counterparty: string;
    counterparty_assignment_id: string;
  }) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const log = useRef<HTMLDivElement>(null);
  const { messages, asking, error } = assistant;

  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [messages.length, asking]);

  const send = async (value: string) => {
    if (await assistant.ask(value)) setText("");
  };

  return (
    <section className="employee-panel assistant" aria-label="עוזר החלפות">
      <header className="assistant-head">
        <h2>
          <MessageCircle size={15} /> שאלו על החלפות
        </h2>
        {messages.length > 0 ? (
          <button type="button" className="ghost-button" onClick={assistant.reset} disabled={asking}>
            <RotateCcw size={13} /> שיחה חדשה
          </button>
        ) : null}
      </header>

      <div className="assistant-log" ref={log} aria-live="polite">
        {messages.length === 0 ? (
          <div className="assistant-empty">
            <p>
              אפשר לשאול עם מי להחליף משמרת, או איך לסדר את השבוע שלך טוב יותר.
              אני מציע רק החלפות שנבדקו ושלא יוצרות בעיה לאף אחד.
            </p>
            <div className="conversation-starters">
              {STARTERS.map((starter) => (
                <button key={starter} type="button" disabled={asking} onClick={() => void send(starter)}>
                  {starter}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message, index) => (
            <Message key={index} message={message} busy={busy} onOffer={onOffer} />
          ))
        )}
        {asking ? (
          <p className="assistant-thinking">
            <LoaderCircle size={14} className="spin" aria-hidden="true" /> בודק את הסידור…
          </p>
        ) : null}
        {messages.length > 0 && !asking ? (
          <div className="assistant-restart">
            <button type="button" className="ghost-button" onClick={assistant.reset}>
              <Trash2 size={13} /> מחיקת השיחה ומעבר לשיחה חדשה
            </button>
          </div>
        ) : null}
      </div>

      {error ? <p className="assistant-error" role="alert">{error}</p> : null}

      <form
        className="assistant-composer"
        onSubmit={(event) => {
          event.preventDefault();
          if (!asking) void send(text);
        }}
      >
        <label className="sr-only" htmlFor="assistant-input">שאלה לעוזר</label>
        <textarea
          id="assistant-input"
          value={text}
          rows={2}
          maxLength={1000}
          placeholder="למשל: אני לא יכול ביום שלישי, עם מי אפשר להחליף?"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              if (!asking) void send(text);
            }
          }}
        />
        <button type="submit" className="primary-button" disabled={asking || !text.trim()} aria-label="שליחה">
          <Send size={16} />
        </button>
      </form>
    </section>
  );
}

function Message({
  message,
  busy,
  onOffer,
}: {
  message: AssistantMessage;
  busy: boolean;
  onOffer: Parameters<typeof AssistantChat>[0]["onOffer"];
}) {
  if (message.role === "employee") {
    return <p className="assistant-message is-mine">{message.text}</p>;
  }
  return (
    <div className="assistant-message is-assistant">
      <Markdown text={message.text} />
      {(message.suggestions ?? []).map((option) => (
        <SwapCard key={option.id} option={option} busy={busy} onOffer={onOffer} />
      ))}
    </div>
  );
}

/** One checked swap, and the button that offers it.
 *
 *  `sent` is local: the authoritative state is the swap list the page
 *  reloads after the offer, and this only keeps the card from inviting a
 *  second identical offer the server would refuse anyway. */
function SwapCard({
  option,
  busy,
  onOffer,
}: {
  option: AssistantSuggestion;
  busy: boolean;
  onOffer: Parameters<typeof AssistantChat>[0]["onOffer"];
}) {
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  const offer = async () => {
    setState("sending");
    const done = await onOffer({
      assignment_id: option.mine.assignment_id,
      counterparty: option.colleague,
      counterparty_assignment_id: option.theirs.assignment_id,
    });
    setState(done ? "sent" : "failed");
  };

  return (
    <div className="assistant-swap">
      <p className="assistant-swap-what">
        <span>המשמרת שלך: <strong>{describe(option.mine)}</strong></span>
        <ArrowLeftRight size={14} aria-hidden="true" />
        <span>של {option.colleague}: <strong>{describe(option.theirs)}</strong></span>
      </p>
      {option.fixes.length > 0 ? (
        <p className="assistant-swap-fixes">משפר: {option.fixes.join(" · ")}</p>
      ) : null}
      {state === "sent" ? (
        <p className="assistant-swap-sent">
          <Check size={13} /> נשלח. עכשיו {option.colleague} צריך/ה לאשר, ואחר כך המנהל.
        </p>
      ) : (
        <div className="assistant-swap-actions">
          <button
            type="button"
            className="ghost-button"
            disabled={busy || state === "sending"}
            onClick={() => void offer()}
          >
            <ArrowLeftRight size={13} /> להציע החלפה ל{option.colleague}
          </button>
          <span>
            {state === "failed"
              ? "לא הצלחתי לשלוח. אולי כבר יש הצעה פתוחה על המשמרת הזו."
              : "שום דבר לא משתנה עד ש" + option.colleague + " והמנהל מאשרים."}
          </span>
        </div>
      )}
    </div>
  );
}

function describe(shift: AssistantShift): string {
  return `${shift.weekday} ${shortDate(shift.date)} · ${shift.shift}`;
}
