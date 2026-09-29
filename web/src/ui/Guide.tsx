import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { LogoMark } from "./Icons";

const SEEN = "hermes.guide.seen";
const LAST = "hermes.last.request";

export function rememberRequest(id: string): void {
  try {
    sessionStorage.setItem(LAST, id);
  } catch {
    /* ignore */
  }
}

export function lastRequestPath(): string | null {
  try {
    const id = sessionStorage.getItem(LAST);
    return id ? `/requests/${encodeURIComponent(id)}` : null;
  } catch {
    return null;
  }
}

export const DEMO_STEPS = [
  { n: "1", label: "Find people", to: "/capability", hint: "Pick a role" },
  { n: "2", label: "Who fits", to: "/capability", hint: "See the shortlist" },
  { n: "3", label: "Team skills", to: "/matrix", hint: "The same people" },
  { n: "4", label: "Learning", to: "/learning", hint: "What to learn next" },
] as const;

export function stepIndex(pathname: string): number {
  if (pathname.startsWith("/learning")) return 3;
  if (pathname.startsWith("/matrix")) return 2;
  if (pathname.startsWith("/requests/") || /^\/capability\/.+/.test(pathname)) return 1;
  if (pathname.startsWith("/capability")) return 0;
  return -1;
}

function seen(): boolean {
  try {
    return sessionStorage.getItem(SEEN) === "1";
  } catch {
    return true;
  }
}

function markSeen(): void {
  try {
    sessionStorage.setItem(SEEN, "1");
  } catch {
    /* ignore */
  }
}

/** First-run welcome for managers. Dismissed for the rest of the session. */
export function WelcomeGuide() {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!session?.roles.includes("manager")) return;
    if (session.data_classification !== "synthetic") return;
    if (seen()) return;
    setOpen(true);
  }, [session?.sub, session?.roles, session?.data_classification]);

  if (!open) return null;

  const close = (to?: string) => {
    markSeen();
    setOpen(false);
    if (to) navigate(to);
  };

  return (
    <div
      className="welcome-scrim"
      role="presentation"
      onKeyDown={(e) => {
        if (e.key === "Escape") close();
      }}
    >
      <div className="welcome-card" role="dialog" aria-labelledby="welcome-title" aria-modal="true" data-testid="welcome-guide">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
          <LogoMark size={36} />
          <div className="brand-name" style={{ fontSize: 16 }}>
            HERMES
          </div>
        </div>
        <h2 id="welcome-title">Welcome. Here is the path.</h2>
        <p className="ink-2">
          You are a manager. In a few clicks you will see who should do the work, why they fit, and what someone should learn next.
        </p>
        <ol className="welcome-steps">
          {DEMO_STEPS.map((s) => (
            <li key={s.n}>
              <b>
                {s.n}. {s.label}
              </b>
              <span>{s.hint}</span>
            </li>
          ))}
        </ol>
        <div className="welcome-actions">
          <button className="btn btn-primary" autoFocus onClick={() => close("/capability")}>
            Start looking
          </button>
          <button className="btn" onClick={() => close()}>
            Skip for now
          </button>
        </div>
      </div>
    </div>
  );
}

/** Compact stepper under the top bar so the four-step story stays visible. */
export function PathRail() {
  const { session } = useAuth();
  const location = useLocation();
  if (!session?.roles.includes("manager")) return null;
  const active = stepIndex(location.pathname);
  const onHome = location.pathname === "/overview" || location.pathname === "/";
  const whoFits = lastRequestPath() ?? "/capability";
  return (
    <nav className="path-rail" aria-label="Demo path">
      <Link to="/overview" className={`path-rail-step ${onHome ? "active" : ""}`}>
        <span className="n">•</span>
        <span>
          Home
          <small>Start here</small>
        </span>
      </Link>
      {DEMO_STEPS.map((s, i) => (
        <Link
          key={s.n}
          to={i === 1 ? whoFits : s.to}
          className={`path-rail-step ${i === active ? "active" : ""} ${i < active ? "done" : ""}`}
        >
          <span className="n">{s.n}</span>
          <span>
            {s.label}
            <small>{s.hint}</small>
          </span>
        </Link>
      ))}
    </nav>
  );
}
