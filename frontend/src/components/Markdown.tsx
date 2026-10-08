"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Render Markdown as React elements. Raw HTML and remote images are excluded. */
export function Markdown({ text }: { text: string }) {
  return <div className="conversation-text is-rich" dir="auto"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
    components={{
      img: ({ alt }) => <span>{alt}</span>,
      a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
      table: ({ children }) => <div className="conversation-table" tabIndex={0} role="region" aria-label="טבלה בתשובה"><table>{children}</table></div>,
      pre: ({ children }) => <CodeBlock>{children}</CodeBlock>,
    }}>{text}</ReactMarkdown></div>;
}

function CodeBlock({ children }: { children: React.ReactNode }) {
  const code = useRef<HTMLPreElement>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => { if (copied) { const timer = setTimeout(() => setCopied(false), 2000); return () => clearTimeout(timer); } }, [copied]);
  return <div className="conversation-code"><header><span>קוד</span><button type="button" onClick={async () => {
    try { await navigator.clipboard.writeText(code.current?.textContent ?? ""); setCopied(true); setError(false); }
    catch { setError(true); }
  }}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "הועתק" : "העתקת קוד"}</button></header>
    <pre ref={code} dir="ltr">{children}</pre>{error ? <small role="status">אפשר לבחור ולהעתיק את הקוד ידנית.</small> : null}</div>;
}

