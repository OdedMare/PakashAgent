"use client";

import { ArrowUp, LoaderCircle, MessagesSquare, Network, Sparkles, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Guard } from "@/components/Crew";
import type { Who } from "@/components/Crew";
import { Markdown } from "@/components/Markdown";
import { AgentChat } from "@/components/Management/AgentChat";
import { ChatPlanCard } from "@/components/Management/ChatPlanCard";
import { Thinking } from "@/components/Management/ChatLive";
import { useManagerChat } from "@/components/Management/useManagerChat";
import { commanderChatRoutes, routeCommanderMessage } from "@/services/api";
import type { ComplexTeam } from "@/types";

/** Where the chat is pointed: the whole מכלול, or one משמרת's own agent. */
export type ChatTarget = "all" | string;

/** A sentence the commander sent from the מכלול tab, and where it went. */
interface Dispatch {
  n: number;
  text: string;
  ids: string[];
  by: "team" | "soldier" | "all" | "chosen";
}

export interface UnitChatStatus {
  working: boolean;
  pending: boolean;
}

const STARTERS = [
  "מי חסר השבוע בכל המשמרות?",
  "מה חסר לפני פרסום השבוע?",
  "מי עבד הכי הרבה החודש?",
];

/** The מכלול commander's one conversation pane (D43).
 *
 *  Every משמרת keeps its own agent — its own roster, rules and solver — so
 *  the pane holds one conversation per משמרת, side by side, over
 *  `/api/complex/teams/<id>/chats`. The "כל המכלול" tab is where the
 *  commander speaks to all of them at once: the sentence is routed in code
 *  (`POST /api/complex/route` — a משמרת it names, else a soldier's own
 *  משמרת, else every משמרת) or to the משמרות the commander picked, and each
 *  agent answers in its own conversation. Each answer, and each plan, shows
 *  under its משמרת here; approving a plan applies it in that משמרת only,
 *  and its commander is told, as for any commander write. */
export function CommanderChat({
  who,
  units,
  target,
  week,
  rosterOf,
  seed,
  onTarget,
  onApplied,
}: {
  who: Who;
  units: ComplexTeam[];
  target: ChatTarget;
  week: string;
  rosterOf: (unitId: string) => string[];
  /** A message to send to one משמרת's agent (the changes page's picks). */
  seed?: { unit: string; text: string; n: number };
  onTarget: (target: ChatTarget) => void;
  onApplied: () => void;
}) {
  const live = units.filter((unit) => unit.active);
  const [dispatch, setDispatch] = useState<Dispatch | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [routing, setRouting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Record<string, UnitChatStatus>>({});
  const report = useCallback((id: string, next: UnitChatStatus) => {
    setStatus((current) => (current[id]?.working === next.working && current[id]?.pending === next.pending
      ? current : { ...current, [id]: next }));
  }, []);
  const [direct, setDirect] = useState<{ unit: string; text: string; n: number } | null>(null);
  const [seen, setSeen] = useState(seed?.n);
  if (seed && seed.n !== seen) {
    setSeen(seed.n);
    setDirect(seed);
  }

  const send = async (text: string) => {
    const clean = text.trim();
    if (!clean || routing) return false;
    setError(null);
    setRouting(true);
    try {
      let ids = chosen.filter((id) => live.some((unit) => unit.id === id));
      let by: Dispatch["by"] = "chosen";
      if (!ids.length) {
        const routed = await routeCommanderMessage(clean);
        ids = routed.team_ids;
        by = routed.by;
      }
      if (!ids.length) {
        setError("אין משמרות פעילות במכלול לשלוח אליהן.");
        return false;
      }
      setDispatch((previous) => ({ n: (previous?.n ?? 0) + 1, text: clean, ids, by }));
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "לא ניתן לשלוח את ההודעה");
      return false;
    } finally {
      setRouting(false);
    }
  };

  const working = Object.values(status).some((row) => row.working);

  return (
    <div className="cmd-chat-pane">
      <div className="cmd-chat-targets" role="tablist" aria-label="שיחה עם">
        <TargetTab
          active={target === "all"}
          icon={<Network size={14} />}
          label="כל המכלול"
          busy={working}
          onClick={() => onTarget("all")}
        />
        {live.map((unit) => (
          <TargetTab
            key={unit.id}
            active={target === unit.id}
            icon={<Users size={14} />}
            label={unit.name}
            busy={status[unit.id]?.working}
            pending={status[unit.id]?.pending}
            onClick={() => onTarget(unit.id)}
          />
        ))}
      </div>

      {target === "all" ? (
        <BroadcastHead
          who={who}
          units={live}
          dispatch={dispatch}
          chosen={chosen}
          onChoose={setChosen}
        />
      ) : null}

      <div className={`cmd-chat-body${target === "all" ? " is-broadcast" : ""}`}>
        {live.map((unit) => (
          <UnitAgent
            key={unit.id}
            who={who}
            unit={unit}
            week={week}
            employees={rosterOf(unit.id)}
            mode={target === unit.id ? "full" : target === "all" && dispatch?.ids.includes(unit.id) ? "summary" : "hidden"}
            dispatch={dispatch}
            direct={direct?.unit === unit.id ? direct : null}
            onStatus={report}
            onApplied={onApplied}
            onOpen={() => onTarget(unit.id)}
          />
        ))}
        {target === "all" && !dispatch ? (
          <div className="conversation-empty cmd-chat-empty">
            <div className="conversation-empty-mark is-guard"><Guard who={who} /></div>
            <h3>מה נעשה היום במכלול?</h3>
            <p>
              הודעה כאן נשלחת לסוכן של כל משמרת שהיא נוגעת בה: משמרת שנקראה בשמה, המשמרת של חייל
              שנקרא בשמו, ואם לא נקראו — לכל המשמרות. כל סוכן מכין תוכנית למשמרת שלו, ושום דבר
              לא נשמר עד שמאשרים.
            </p>
            <div className="conversation-starters">
              {STARTERS.map((value) => (
                <button type="button" key={value} disabled={routing} onClick={() => void send(value)}>{value}</button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {target === "all" ? (
        <BroadcastComposer
          busy={routing}
          working={working}
          error={error}
          chosenCount={chosen.length}
          onSend={send}
        />
      ) : null}
    </div>
  );
}

function TargetTab({
  active, icon, label, busy, pending, onClick,
}: {
  active: boolean;
  icon: React.ReactNode;
  label: string;
  busy?: boolean;
  pending?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`cmd-chat-target${active ? " is-active" : ""}`}
      onClick={onClick}
      title={busy ? "הסוכן עובד" : pending ? "תוכנית ממתינה לאישור" : undefined}
    >
      {icon}
      <span>{label}</span>
      {busy ? <LoaderCircle size={12} className="cmd-chat-spin" aria-label="עובד" />
        : pending ? <span className="cmd-chat-dot" aria-label="תוכנית ממתינה" /> : null}
    </button>
  );
}

/** Which משמרות the next sentence goes to: chosen, or read from it. */
function BroadcastHead({
  who, units, dispatch, chosen, onChoose,
}: {
  who: Who;
  units: ComplexTeam[];
  dispatch: Dispatch | null;
  chosen: string[];
  onChoose: (ids: string[]) => void;
}) {
  const toggle = (id: string) => onChoose(chosen.includes(id) ? chosen.filter((row) => row !== id) : [...chosen, id]);
  const names = (ids: string[]) => units.filter((unit) => ids.includes(unit.id)).map((unit) => unit.name).join(", ");
  return (
    <div className="cmd-chat-head">
      <div className="conversation-title"><Guard who={who} face /><strong>סוכן המכלול</strong></div>
      <div className="cmd-chat-route" role="group" aria-label="למי לשלוח">
        <span className="cmd-chat-route-label">שליחה אל</span>
        <button type="button" className={`board-toggle${chosen.length === 0 ? " is-on" : ""}`}
          aria-pressed={chosen.length === 0} onClick={() => onChoose([])}
          title="לפי ההודעה: משמרת שנקראה, המשמרת של חייל שנקרא, או כל המשמרות">
          <Sparkles size={13} /> אוטומטי
        </button>
        {units.map((unit) => (
          <button key={unit.id} type="button" className={`board-toggle${chosen.includes(unit.id) ? " is-on" : ""}`}
            aria-pressed={chosen.includes(unit.id)} onClick={() => toggle(unit.id)}>
            {unit.name}
          </button>
        ))}
      </div>
      {dispatch ? (
        <p className="cmd-chat-sent">
          <MessagesSquare size={13} aria-hidden="true" />
          <span>
            &quot;{dispatch.text}&quot; נשלח ל{dispatch.ids.length === units.length ? "כל המשמרות" : names(dispatch.ids)}
            {dispatch.by === "team" ? " — לפי המשמרת שנקראה"
              : dispatch.by === "soldier" ? " — לפי החייל שנקרא"
                : dispatch.by === "all" ? " — ההודעה לא הזכירה משמרת או חייל" : ""}
          </span>
        </p>
      ) : null}
    </div>
  );
}

function BroadcastComposer({
  busy, working, error, chosenCount, onSend,
}: {
  busy: boolean;
  working: boolean;
  error: string | null;
  chosenCount: number;
  onSend: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!input.current) return;
    input.current.style.height = "auto";
    input.current.style.height = `${Math.min(200, Math.max(44, input.current.scrollHeight))}px`;
  }, [text]);
  const submit = async () => {
    const value = text;
    if (!value.trim()) return;
    setText("");
    if (!await onSend(value)) setText(value);
    input.current?.focus();
  };
  return (
    <div className="conversation-bottom">
      {error ? <p className="conversation-error" role="alert">{error}</p> : null}
      <form className="conversation-composer" onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        <label className="sr-only" htmlFor="cmd-composer-input">הודעה לסוכני המכלול</label>
        <textarea id="cmd-composer-input" ref={input} value={text} rows={1} maxLength={4000} dir="auto"
          placeholder={chosenCount ? `הודעה ל־${chosenCount} משמרות…` : "מה לעשות במכלול? למשל: ״במרכבה דנה חולה מחר״"}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void submit();
            }
          }} />
        <div className="conversation-composer-footer">
          <small>{working ? "הסוכנים עובדים — אפשר להמשיך לכתוב" : "Enter לשליחה · Shift+Enter לשורה חדשה"}</small>
          <button type="submit" className="conversation-send" aria-label="שליחת הודעה" disabled={busy || !text.trim()}>
            {busy ? <LoaderCircle size={17} /> : <ArrowUp size={19} />}
          </button>
        </div>
      </form>
      <p className="conversation-disclaimer">כל משמרת מאשרת בנפרד. בדקו כל תוכנית לפני האישור.</p>
    </div>
  );
}

/** One משמרת's conversation: the full chat on its own tab, or its answer to
 *  the last מכלול-wide sentence on the "כל המכלול" tab. Mounted for every
 *  משמרת while the pane is open, so a sentence sent to several runs in all
 *  of them at once and each answer lands where the commander is looking. */
function UnitAgent({
  who, unit, week, employees, mode, dispatch, direct, onStatus, onApplied, onOpen,
}: {
  who: Who;
  unit: ComplexTeam;
  week: string;
  employees: string[];
  mode: "full" | "summary" | "hidden";
  dispatch: Dispatch | null;
  direct: { text: string; n: number } | null;
  onStatus: (id: string, status: UnitChatStatus) => void;
  onApplied: () => void;
  onOpen: () => void;
}) {
  const routes = useMemo(() => commanderChatRoutes(unit.id), [unit.id]);
  const applied = useCallback(async () => { onApplied(); }, [onApplied]);
  const agent = useManagerChat(unit.id, "", week, "", applied, routes);
  const messages = agent.chat?.messages ?? [];
  const last = messages[messages.length - 1];
  const working = agent.working || agent.busy;
  const pending = last?.status === "pending";
  useEffect(() => { onStatus(unit.id, { working, pending }); }, [unit.id, working, pending, onStatus]);

  // A sentence from the מכלול tab (or the changes page), sent once, when
  // this משמרת's conversation is ready for it.
  const sentDispatch = useRef(0);
  const sentDirect = useRef(0);
  const ready = Boolean(agent.chat) && !agent.loading && !agent.working && !agent.busy;
  const { send } = agent;
  useEffect(() => {
    if (!ready) return;
    if (direct && direct.n !== sentDirect.current) {
      sentDirect.current = direct.n;
      void send(direct.text);
    } else if (dispatch && dispatch.ids.includes(unit.id) && dispatch.n !== sentDispatch.current) {
      sentDispatch.current = dispatch.n;
      void send(dispatch.text);
    }
  }, [ready, send, dispatch, direct, unit.id]);

  if (mode === "hidden") return null;
  if (mode === "full") {
    return (
      <div className="manager-drawer-content is-conversation cmd-chat-full">
        <AgentChat
          who={who}
          agent={agent}
          visibleWeek={week}
          employees={employees}
          starters={[`מה חסר ב${unit.name} השבוע?`, "מי יכול להחליף מחר?", "מי עבד הכי הרבה החודש?"]}
          boardBusy={false}
          onPreview={() => undefined}
          onOpenReceipt={() => undefined}
        />
      </div>
    );
  }

  // The answer to the last sentence: everything after the last message of
  // the commander's own in this conversation.
  const lastMine = messages.map((row) => row.role).lastIndexOf("user");
  const reply = lastMine >= 0 ? messages.slice(lastMine + 1) : [];
  const waiting = agent.outgoing || (lastMine < 0 && working);
  return (
    <article className="cmd-chat-card" aria-label={`תשובת ${unit.name}`}>
      <header>
        <span className="cmd-chat-card-name"><Users size={14} /> {unit.name}</span>
        <button type="button" className="ghost-button" onClick={onOpen}>פתיחת השיחה</button>
      </header>
      {agent.loading ? <p className="conversation-loading"><LoaderCircle size={15} /> טוען…</p> : null}
      {waiting && !reply.length ? <Thinking who={who} steps={[]} /> : null}
      {reply.map((message) => (
        <div key={message.id} className={`conversation-message is-assistant${message.status === "error" ? " is-error" : ""}`}>
          {message.status === "working"
            ? <Thinking who={who} steps={message.payload.steps ?? []} activity={message.payload.activity} draft={message.payload.draft} />
            : <Markdown text={message.content} />}
          {message.payload.plan ? (
            <ChatPlanCard message={message} employees={employees} disabled={working}
              onApply={(exceptions) => void agent.apply(message.id, exceptions)}
              onDismiss={() => void agent.dismiss(message.id)}
              onAdjust={(value) => void agent.send(value)} />
          ) : null}
          {message.payload.question?.options.length ? (
            <div className="conversation-options">
              {message.payload.question.options.map((option) => (
                <button type="button" key={option.label} disabled={working || message.id !== last?.id}
                  onClick={() => void agent.send(option.answer)}>{option.label}</button>
              ))}
            </div>
          ) : null}
        </div>
      ))}
      {agent.error ? <p className="conversation-error" role="alert">{agent.error}</p> : null}
    </article>
  );
}
