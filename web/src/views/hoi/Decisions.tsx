import { hoiApi } from "../../api/endpoints";
import { useApi, useStale } from "../../lib/useApi";
import { Kpi, PageHead } from "../../ui/Bits";
import { EmptyState, ErrorState, Loading } from "../../ui/States";
import { Chip, OppGate, OppPicker, SyntheticBanner, pretty, useRoles, useSelectedOpp } from "./common";

export default function Decisions() {
  const sel = useSelectedOpp();
  const { has } = useRoles();
  return (
    <>
      <PageHead
        trail={["System", "Decisions & Audit"]}
        title="Decisions & Audit"
        lede="Every upload, extraction, approval, match, scenario and export is an attributable, hash-chained event. Audit details never contain compensation."
      />
      <OppGate sel={sel}>
        {(opp) => (
          <>
            <div className="chip-row"><OppPicker opps={sel.opps} selected={sel.selected} select={sel.select} /></div>
            <SyntheticBanner show={opp.is_synthetic} />
            <Trail oid={opp.opportunity_id} />
            {has("finance", "hr", "admin") && <AccessLog />}
          </>
        )}
      </OppGate>
    </>
  );
}

function Trail({ oid }: { oid: string }) {
  const q = useApi((s) => hoiApi.audit(oid, s), [oid]);
  const data = useStale(q);
  if (q.status === "loading" && !data) return <Loading label="Loading audit trail" />;
  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  if (!data) return null;
  return (
    <>
      <section className="kpis" aria-label="Audit integrity">
        <Kpi label="Events" value={data.events.length} />
        <Kpi label="Hash chain" value={<Chip tone={data.chain_valid ? "ok" : "fail"}>{data.chain_valid ? "valid" : "BROKEN"}</Chip>} note="recomputed on every read" />
        <Kpi label="Head hash" value={<span className="mono">{data.head_hash.slice(0, 12)}…</span>} />
      </section>
      <section className="panel table-wrap" style={{ marginTop: 12 }} aria-label="Audit events">
        {!data.events.length ? <EmptyState title="No events" /> : (
          <table className="data">
            <thead><tr><th>#</th><th>Time</th><th>Actor</th><th>Action</th><th>Object</th><th>Details</th></tr></thead>
            <tbody>
              {[...data.events].reverse().map((e) => (
                <tr key={e.seq}>
                  <td>{e.seq}</td><td className="mono">{e.created_at.replace("T", " ").slice(0, 19)}</td><td>{e.actor}</td>
                  <td>{pretty(e.event_type)}</td><td className="mono">{e.object}{e.version ? ` v${e.version}` : ""}</td>
                  <td className="muted">{Object.entries(e.detail).map(([k, v]) => `${pretty(k)}: ${String(v)}`).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </>
  );
}

function AccessLog() {
  const q = useApi((s) => hoiApi.accessLog(s), []);
  return (
    <section className="panel table-wrap" style={{ marginTop: 16 }} aria-label="Finance data access log">
      <div className="panel-head"><h2>Finance data access log</h2><span className="muted">who touched compensation data — never the values</span></div>
      {q.status === "loading" && <Loading label="Loading access log" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && (q.data.events.length === 0 ? <EmptyState title="No finance data access yet" /> : (
        <table className="data">
          <thead><tr><th>Time</th><th>Actor</th><th>Action</th><th>Context</th></tr></thead>
          <tbody>{q.data.events.map((e) => <tr key={e.access_id}><td className="mono">{e.created_at.slice(0, 19)}</td><td>{e.actor}</td><td>{pretty(e.action)}</td><td>{e.context}</td></tr>)}</tbody>
        </table>
      ))}
    </section>
  );
}
