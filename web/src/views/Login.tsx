import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { DEMO_PRINCIPALS } from "../api/auth";
import { useAuth } from "../lib/auth";
import { homeFor } from "../routes";
import { IconArrowRight, LogoMark } from "../ui/Icons";
import { InlineError } from "../ui/States";

const PRIMARY = new Set(["demo-manager", "demo-employee"]);
const LABELS: Record<string, string> = {
  "demo-manager": "Continue as a manager",
  "demo-employee": "View as an employee",
};

export default function Login() {
  const { session, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [more, setMore] = useState(false);
  const from = (location.state as { from?: string } | null)?.from;

  if (session) return <Navigate to={from ?? homeFor(session.roles)} replace />;

  const choose = async (sub: string) => {
    setPending(sub);
    setError(null);
    try {
      await login(sub);
      navigate(from ?? "/", { replace: true });
    } catch (e) {
      setError(e as Error);
    } finally {
      setPending(null);
    }
  };

  const primary = DEMO_PRINCIPALS.filter((p) => PRIMARY.has(p.sub));
  const extra = DEMO_PRINCIPALS.filter((p) => !PRIMARY.has(p.sub));

  const row = (p: (typeof DEMO_PRINCIPALS)[number]) => (
    <button key={p.sub} className="principal" onClick={() => choose(p.sub)} disabled={pending !== null} aria-label={`${LABELS[p.sub] ?? p.label} ${p.sub}`}>
      <span style={{ fontWeight: 500 }}>{LABELS[p.sub] ?? p.label}</span>
      {pending === p.sub ? <span className="muted">Signing in…</span> : <IconArrowRight />}
    </button>
  );

  return (
    <div className="login">
      <div className="login-card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
          <LogoMark size={40} />
          <div>
            <div className="brand-name" style={{ fontSize: 18 }}>
              HERMES
            </div>
            <div className="muted">Find who should do the work</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <h2>Sign in</h2>
          </div>
          <div>
            {primary.map(row)}
            {more ? extra.map(row) : (
              <button type="button" className="principal" onClick={() => setMore(true)}>
                <span className="muted">More roles</span>
              </button>
            )}
          </div>
        </div>
        <p className="hint" style={{ marginTop: 12 }}>
          Local demo. Choose manager to walk the path.
        </p>
        {error && <InlineError error={error} />}
      </div>
    </div>
  );
}
