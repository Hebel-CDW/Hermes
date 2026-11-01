import { FormEvent, useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { copilotApi } from "../api/endpoints";
import { useAuth } from "../lib/auth";
import { Thinking } from "./Loader";

type Msg = { from: "you" | "hermes"; text: string; source?: "model" | "offline"; model?: string | null };

const MANAGER_ASKS = [
  "Who should I pick for my latest request, and why?",
  "Why was someone not shortlisted?",
  "Which skills have only one person who can do them?",
  "Which skills does nobody on the team have proof of?",
  "Are there any disputes waiting for me?",
];
const EMPLOYEE_ASKS = [
  "What should I learn next?",
  "Which role am I closest to, and what is missing?",
  "Why is my confidence not higher?",
  "Do I have a dispute waiting?",
];

/** Floating copilot: plain-English answers grounded in the signed-in person's own data. Advisory only. */
export default function Copilot() {
  const { session } = useAuth();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const isManager = !!session?.roles.includes("manager");
  const allowed = isManager || !!session?.roles.includes("employee");
  const requestId = decodeURIComponent(
    location.pathname.match(/^\/requests\/([^/]+)/)?.[1] ?? new URLSearchParams(location.search).get("request") ?? "",
  );

  useEffect(() => {
    if (!open || !allowed) return;
    const ctrl = new AbortController();
    copilotApi.status(ctrl.signal).then(
      (s) => setOnline(s.online),
      () => setOnline(false),
    );
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      ctrl.abort();
      window.removeEventListener("keydown", onKey);
    };
  }, [open, allowed]);
  useEffect(() => {
    // Block body on purpose: an effect must return nothing or a cleanup function.
    end.current?.scrollIntoView?.({ block: "end" });
  }, [msgs, pending]);

  if (!allowed) return null;

  const ask = async (q: string) => {
    const question = q.trim();
    if (!question || pending) return;
    setMsgs((m) => [...m, { from: "you", text: question }]);
    setText("");
    setPending(true);
    try {
      const r = await copilotApi.ask(question, requestId || undefined);
      setMsgs((m) => [...m, { from: "hermes", text: r.answer, source: r.source, model: r.model }]);
    } catch (err) {
      setMsgs((m) => [...m, { from: "hermes", text: `I could not answer that: ${(err as Error).message}`, source: "offline" }]);
    } finally {
      setPending(false);
    }
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    void ask(text);
  };
  const asks = isManager ? MANAGER_ASKS : EMPLOYEE_ASKS;

  return (
    <>
      {!open && (
        <button className="copilot-fab" onClick={() => setOpen(true)} aria-label="Ask Hermes">
          <span aria-hidden>✦</span> Ask Hermes
        </button>
      )}
      {open && (
        <aside className="copilot" aria-label="Hermes copilot" role="dialog">
          <header>
            <div>
              <strong>Hermes Copilot</strong>
              <div className="muted" style={{ fontSize: 12 }}>
                {online === null ? "Checking…" : online ? "AI model online · answers use your data only" : "AI model offline · answering from your data"}
              </div>
            </div>
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close copilot">
              ✕
            </button>
          </header>
          <div className="copilot-body">
            {msgs.length === 0 && (
              <div className="copilot-intro">
                <p>
                  Ask me anything about {isManager ? "who fits, why, and where the gaps are" : "your skills and how to grow"}. I only use the data you can already see, and I explain
                  it in plain English. You decide; I advise.
                </p>
                <div className="label">Try asking</div>
                {asks.map((a) => (
                  <button key={a} className="copilot-ask" onClick={() => void ask(a)}>
                    {a}
                  </button>
                ))}
              </div>
            )}
            {msgs.map((m, i) => (
              <div key={i} className={`copilot-msg copilot-${m.from}`}>
                <div style={{ whiteSpace: "pre-wrap" }}>{m.text}</div>
                {m.from === "hermes" && (
                  <div className="copilot-src">
                    {m.source === "model" ? `AI answer · ${m.model ?? "local model"} · based on your data` : "Answered directly from your data (model offline)"}
                  </div>
                )}
              </div>
            ))}
            {pending && (
              <div className="copilot-msg copilot-hermes">
                <Thinking
                  steps={["Reading your data…", "Checking the evidence…", "Working out the answer…", "Writing it in plain English…"]}
                />
              </div>
            )}
            <div ref={end} />
          </div>
          {msgs.length > 0 && (
            <div className="copilot-chips">
              {asks.slice(0, 3).map((a) => (
                <button key={a} className="chip" onClick={() => void ask(a)} disabled={pending}>
                  {a}
                </button>
              ))}
            </div>
          )}
          <form onSubmit={submit}>
            <input
              className="input"
              placeholder="Ask in your own words…"
              value={text}
              maxLength={600}
              onChange={(e) => setText(e.target.value)}
              aria-label="Ask Hermes a question"
            />
            <button className="btn btn-primary" type="submit" disabled={pending || !text.trim()}>
              Ask
            </button>
          </form>
          <footer className="muted">Advisory only. Hermes explains; people decide.</footer>
        </aside>
      )}
    </>
  );
}
