import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { overviewApi, requestsApi, skillsApi } from "../api/endpoints";
import type { Overview } from "../api/types";
import { useAuth } from "../lib/auth";
import { shortTime } from "../lib/format";
import { PageMotion } from "../motion/PageMotion";
import { NAV } from "../routes";
import { IconBell, IconClose, IconMenu, IconSearch, IconSignOut, LogoMark } from "./Icons";

/** Label for the database the server says it is serving; never inferred client-side. */
export const classificationLabel = (c: string | null) =>
  c === "real" ? "Real workforce data" : c === "synthetic" ? "Synthetic demo data" : "Unclassified database";

function crumbLabel(fallback?: string) {
  return fallback ?? "Workspace";
}

const initials = (sub: string) =>
  sub
    .replace(/^demo-/, "")
    .split(/[-_]/)
    .map((s) => s[0]?.toUpperCase() ?? "")
    .join("")
    .slice(0, 2);

export function Shell({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();
  const location = useLocation();
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const roles = session?.roles ?? [];
  const items = NAV.filter((n) => n.primary && n.roles.some((r) => roles.includes(r)));
  const current = NAV.find((n) => location.pathname.startsWith(n.path));

  useEffect(() => setNavOpen(false), [location.pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={`shell ${navOpen ? "nav-open" : ""}`}>
      <aside className="sidebar" aria-label="Primary">
        <div className="brand">
          <LogoMark />
          <div>
            <div className="brand-name">HERMES</div>
            <div className="brand-sub">Who should do the work</div>
          </div>
        </div>
        <nav className="nav">
          {(["Start here", "Explore", "System"] as const).map((group) => {
            const groupItems = items.filter((n) => n.group === group);
            if (groupItems.length === 0) return null;
            return (
            <div className="nav-group" key={group}>
              <span className="label">{group}</span>
              {groupItems.map(({ path, label, icon: Icon }) => (
                  <NavLink key={path} to={path} end className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                    <Icon />
                    {label}
                  </NavLink>
                ))}
            </div>
            );
          })}
        </nav>
        <div className="sidebar-foot">
          <span data-testid="data-classification">{classificationLabel(session?.data_classification ?? null)}</span>
          <span className={`dot ${session?.data_classification === "real" ? "dot-real" : ""}`} aria-hidden />
        </div>
      </aside>
      <div className="scrim" onClick={() => setNavOpen(false)} aria-hidden />
      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" aria-label="Open navigation" onClick={() => setNavOpen(true)}>
            <IconMenu />
          </button>
          <div className="crumbs">
            <span>Hermes</span>/<strong>{crumbLabel(current?.label)}</strong>
          </div>
          <button className="search-trigger" onClick={() => setPaletteOpen(true)} aria-label="Search">
            <IconSearch />
            <span>Search pages, skills, requests…</span>
            <kbd>⌘K</kbd>
          </button>
          {session?.data_classification === "real" && <span className="chip chip-crimson">Real data · coded identities</span>}
          <div className="topbar-right">
            {session && (session.roles.includes("manager") || session.roles.includes("admin")) && <Notifications />}
            {session && <ProfileMenu sub={session.sub} coded={session.coded_identity} roles={session.roles} onSignOut={logout} />}
          </div>
        </header>
        <main className="page">
          <PageMotion>{children}</PageMotion>
        </main>
      </div>
      {paletteOpen && <CommandPalette onClose={() => setPaletteOpen(false)} />}
    </div>
  );
}

function useDismiss(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && close();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

/** Recent audit-ledger events from /api/overview (event type + time only; payloads are never shown). */
function Notifications() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<Overview["recent_activity"] | null>(null);
  const [failed, setFailed] = useState(false);
  const ref = useDismiss(open, () => setOpen(false));
  useEffect(() => {
    if (!open) return;
    const c = new AbortController();
    setFailed(false);
    overviewApi.get(c.signal).then(
      (o) => setData(o.recent_activity),
      (e: Error) => e.name !== "AbortError" && setFailed(true),
    );
    return () => c.abort();
  }, [open]);
  return (
    <div className="anchor" ref={ref}>
      <button className="icon-btn" aria-label="Activity" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <IconBell />
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Recent activity">
          <div className="popover-head label">Audit ledger · recent events</div>
          <div className="popover-body">
            {failed && <div className="popover-row muted">Activity could not be loaded.</div>}
            {!failed && data === null && <div className="popover-row muted">Loading…</div>}
            {data?.length === 0 && <div className="popover-row muted">No recorded activity.</div>}
            {data?.map((a) => (
              <div className="popover-row" key={a.seq}>
                <span>{a.event_type.replace(/_/g, " ")}</span>
                <span className="muted num">{shortTime(a.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ProfileMenu({ sub, coded, roles, onSignOut }: { sub: string; coded: string | null; roles: string[]; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const ref = useDismiss(open, () => setOpen(false));
  return (
    <div className="anchor" ref={ref}>
      <button className="icon-btn" aria-label="Account" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="avatar">{initials(sub)}</span>
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Account">
          <div className="popover-head">
            <div style={{ fontWeight: 600 }}>{sub}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {roles.join(", ")} · {coded ?? "no coded identity"}
            </div>
          </div>
          <div className="popover-body">
            <button className="principal" onClick={() => navigate("/profile")}>
              Profile
            </button>
            <button
              className="principal"
              onClick={() => {
                onSignOut();
                navigate("/login");
              }}
            >
              Sign out <IconSignOut />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

type Command = { label: string; hint: string; to: string };

/** Search over navigation, governed skills (/api/skills) and the manager's own requests. */
function CommandPalette({ onClose }: { onClose: () => void }) {
  const { session } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const [remote, setRemote] = useState<Command[]>([]);
  const roles = session?.roles ?? [];
  const isStaff = roles.includes("manager") || roles.includes("admin");

  useEffect(() => {
    const c = new AbortController();
    const load = async () => {
      const out: Command[] = [];
      if (isStaff) {
        const { skills } = await skillsApi.list(c.signal);
        out.push(...skills.map((s) => ({ label: s.name, hint: `Skill · ${s.skill_id}`, to: `/skills?skill=${encodeURIComponent(s.skill_id)}` })));
      }
      if (roles.includes("manager")) {
        const { requests } = await requestsApi.list(c.signal);
        out.push(...requests.map((r) => ({ label: r.request_id, hint: `Request · ${r.status}`, to: `/requests/${encodeURIComponent(r.request_id)}` })));
      }
      setRemote(out);
    };
    load().catch(() => undefined);
    return () => c.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const results = useMemo(() => {
    const pages = NAV.filter((n) => n.primary && n.roles.some((r) => roles.includes(r))).map((n) => ({ label: n.label, hint: "Page", to: n.path }));
    const needle = q.trim().toLowerCase();
    return [...pages, ...remote].filter((c) => !needle || `${c.label} ${c.hint}`.toLowerCase().includes(needle)).slice(0, 12);
  }, [q, remote, roles]);

  const go = (c: Command | undefined) => {
    if (!c) return;
    navigate(c.to);
    onClose();
  };

  return (
    <div className="overlay" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <input
            autoFocus
            name="search"
            placeholder="Search pages, skills, requests…"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") setCursor((c) => Math.min(c + 1, results.length - 1));
              if (e.key === "ArrowUp") setCursor((c) => Math.max(c - 1, 0));
              if (e.key === "Enter") go(results[cursor]);
            }}
            aria-label="Search query"
          />
          <button className="icon-btn" aria-label="Close search" onClick={onClose} style={{ marginRight: 8 }}>
            <IconClose />
          </button>
        </div>
        <ul role="listbox">
          {results.length === 0 && <li className="muted" style={{ padding: "8px 10px" }}>No matches.</li>}
          {results.map((c, i) => (
            <li key={c.hint + c.to}>
              <button role="option" aria-selected={i === cursor} onMouseEnter={() => setCursor(i)} onClick={() => go(c)}>
                <span>{c.label}</span>
                <span className="muted" style={{ fontSize: 12 }}>
                  {c.hint}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
