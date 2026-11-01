import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hoiApi } from "../../api/endpoints";
import type { HoiOpportunity, Role } from "../../api/types";
import { useAuth } from "../../lib/auth";
import { useApi } from "../../lib/useApi";
import { EmptyState, ErrorState, Loading } from "../../ui/States";

const KEY = "hermes.hoi.opp";

export function useRoles(): { has: (...r: Role[]) => boolean; sub: string } {
  const { session } = useAuth();
  const roles = session?.roles ?? [];
  return { has: (...r: Role[]) => r.some((x) => roles.includes(x)), sub: session?.sub ?? "" };
}

/** The opportunity every Opportunity Intelligence page works on; remembered for the browser session. */
export function useSelectedOpp() {
  const q = useApi((s) => hoiApi.list(s), []);
  const [selected, setSelected] = useState<string>(() => {
    try {
      return sessionStorage.getItem(KEY) ?? "";
    } catch {
      return "";
    }
  });
  const opps = q.status === "success" ? q.data.opportunities : [];
  useEffect(() => {
    if (q.status !== "success") return;
    if (!opps.some((o) => o.opportunity_id === selected)) setSelected(opps[0]?.opportunity_id ?? "");
  }, [q.status, opps, selected]);
  const select = useCallback((id: string) => {
    setSelected(id);
    try {
      sessionStorage.setItem(KEY, id);
    } catch {
      /* ignore */
    }
  }, []);
  return { q, opps, selected, select, current: opps.find((o) => o.opportunity_id === selected) };
}

export function OppPicker({
  opps,
  selected,
  select,
}: {
  opps: HoiOpportunity[];
  selected: string;
  select: (id: string) => void;
}) {
  return (
    <label className="field compact" style={{ maxWidth: 420 }}>
      <span className="label">Opportunity</span>
      <select className="select" value={selected} onChange={(e) => select(e.target.value)} aria-label="Opportunity">
        {opps.map((o) => (
          <option key={o.opportunity_id} value={o.opportunity_id}>
            {o.opportunity_id} · {o.client_alias} · {o.name}
            {o.is_synthetic ? " (synthetic)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

/** Loading / error / empty wrapper shared by every HOI page. */
export function OppGate({
  sel,
  children,
}: {
  sel: ReturnType<typeof useSelectedOpp>;
  children: (o: HoiOpportunity) => React.ReactNode;
}) {
  const { q, current } = sel;
  if (q.status === "loading") return <Loading label="Loading opportunities" />;
  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  if (!current)
    return (
      <EmptyState title="No opportunity yet">
        Create one in the RFP/SOW Workspace, or ask the deal owner to add you to the deal team.
      </EmptyState>
    );
  return <>{children(current)}</>;
}

export const SyntheticBanner = ({ show }: { show: boolean }) =>
  show ? (
    <div className="notice" role="note" style={{ marginBottom: 12 }}>
      <b>Synthetic demo data.</b> This opportunity, its documents, costs and benchmarks are invented for demonstration.
    </div>
  ) : null;

export const STATUS_TONE: Record<string, string> = {
  approved: "chip-ok",
  eligible: "chip-ok",
  pass: "chip-ok",
  draft: "chip-warn",
  partially_approved: "chip-warn",
  unverified: "chip-warn",
  unknown: "chip-warn",
  rejected: "chip-crimson",
  ineligible: "chip-crimson",
  fail: "chip-crimson",
  high: "chip-crimson",
  medium: "chip-warn",
  low: "chip-ok",
  synthetic: "chip-warn",
  weak: "chip-warn",
  ok: "chip-ok",
};

export const Chip = ({ children, tone }: { children: React.ReactNode; tone?: string }) => (
  <span className={`chip ${tone ? STATUS_TONE[tone] ?? "" : ""}`}>{children}</span>
);

export const pretty = (s: string) => s.replace(/_/g, " ");

export function download(name: string, text: string, mime: string) {
  const url = URL.createObjectURL(new Blob([text], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}


/**
 * Executive Overview panel. Every figure is read from GET /api/opportunities (readiness counts); nothing is derived
 * here. Renders nothing while loading, when there are no opportunities, or if the call fails, so it can never break
 * the page it sits on.
 */
export function OpportunityPipeline() {
  const q = useApi((s) => hoiApi.list(s), []);
  const { select } = useSelectedOpp();
  if (q.status !== "success" || q.data.opportunities.length === 0) return null;
  return (
    <section className="panel table-wrap" aria-label="Opportunity pipeline" style={{ marginTop: 16 }}>
      <div className="panel-head">
        <h2>Opportunity pipeline</h2>
        <Link className="btn btn-sm" to="/rfp">Open RFP/SOW Workspace</Link>
      </div>
      <table className="data">
        <thead>
          <tr><th>Opportunity</th><th>Customer</th><th>Stage</th><th>Documents</th><th>Requirements</th><th>Scenarios</th></tr>
        </thead>
        <tbody>
          {q.data.opportunities.map((o) => (
            <tr key={o.opportunity_id}>
              <td><Link to="/rfp" onClick={() => select(o.opportunity_id)}>{o.opportunity_id}</Link>{o.is_synthetic && <span className="muted"> · synthetic</span>}</td>
              <td>{o.client_alias}</td>
              <td><Chip>{pretty(o.stage)}</Chip></td>
              <td>{o.readiness.documents}</td>
              <td><Chip tone={o.readiness.has_approved_requirements ? "approved" : o.readiness.requirements_status === "draft" ? "draft" : undefined}>{pretty(o.readiness.requirements_status)}</Chip></td>
              <td>{o.readiness.scenarios} ({o.readiness.approved_scenarios} approved)</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
