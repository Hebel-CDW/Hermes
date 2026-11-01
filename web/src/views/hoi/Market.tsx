import { useState } from "react";
import { hoiApi } from "../../api/endpoints";
import type { HoiBenchmark, HoiMarketAnalysis } from "../../api/types";
import { useApi, useStale } from "../../lib/useApi";
import { Kpi, PageHead } from "../../ui/Bits";
import { useToasts } from "../../ui/Fx";
import { EmptyState, ErrorState, InlineError, Loading } from "../../ui/States";
import { Chip, OppPicker, SyntheticBanner, pretty, useRoles, useSelectedOpp } from "./common";

const BASIS: Record<string, string> = { salary: "Salary (permanent)", contractor_cost: "Contractor cost", bill_rate: "Customer bill rate" };
const TEMPLATE =
  "role,geography,seniority,engagement_type,basis,currency,unit,p25,p50,p75,sample_count,source,as_of,time_to_fill_weeks,synthetic\n";

export default function Market() {
  const { has } = useRoles();
  const [basis, setBasis] = useState("");
  const [role, setRole] = useState("");
  const q = useApi((s) => hoiApi.benchmarks({ basis: basis || undefined, role: role || undefined }, s), [basis, role]);
  const data = useStale(q);
  const sel = useSelectedOpp();
  const rows = data?.benchmarks ?? [];
  const synthetic = rows.filter((r) => r.is_synthetic).length;
  return (
    <>
      <PageHead
        trail={["Opportunity Intelligence", "Market Intelligence"]}
        title="Market Intelligence"
        lede="Curated external benchmarks for build-versus-buy. Salary, contractor cost and customer bill rate are separate bases and are never blended."
      />
      <div className="notice" role="note" style={{ marginBottom: 12 }}>
        Benchmarks are <b>manually imported</b>, with source, sample size and as-of date. There is no live salary, ATS or vendor feed in this
        prototype. Rows marked synthetic are invented demonstration data, not market prices.
      </div>
      <section className="kpis" aria-label="Benchmark coverage">
        <Kpi label="Benchmarks" value={rows.length} />
        <Kpi label="Synthetic rows" value={synthetic} note={synthetic ? "demo data" : "none"} />
        <Kpi label="Thin samples (<5)" value={rows.filter((r) => r.coverage === "weak").length} />
      </section>
      <div className="chip-row">
        <label className="field compact"><span className="label">Basis</span>
          <select className="select" value={basis} onChange={(e) => setBasis(e.target.value)} aria-label="Basis">
            <option value="">All bases</option>
            {Object.entries(BASIS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
        <label className="field compact"><span className="label">Role</span>
          <input className="input" value={role} placeholder="exact role name" onChange={(e) => setRole(e.target.value)} />
        </label>
      </div>
      {q.status === "loading" && !data && <Loading label="Loading benchmarks" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data && !rows.length && <EmptyState title="No benchmarks">{has("finance", "admin") ? "Import a curated CSV below." : "Finance imports curated benchmark files."}</EmptyState>}
      {rows.length > 0 && <BenchTable rows={rows} />}
      {has("finance", "admin") && <ImportPanel onDone={q.reload} />}
      <h2 style={{ margin: "24px 0 8px" }}>Analysis for an opportunity</h2>
      {sel.opps.length > 0 ? <Analysis sel={sel} /> : <EmptyState title="No opportunity">Create one in the RFP/SOW Workspace.</EmptyState>}
    </>
  );
}

function BenchTable({ rows }: { rows: HoiBenchmark[] }) {
  return (
    <section className="panel table-wrap" aria-label="Benchmarks">
      <table className="data">
        <thead><tr><th>Role</th><th>Geography</th><th>Seniority</th><th>Basis</th><th>P25</th><th>P50</th><th>P75</th><th>Samples</th><th>Source</th><th>As of</th><th>Time to fill</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.benchmark_id}>
              <td>{r.role}</td><td>{r.geography}</td><td>{r.seniority}</td>
              <td>{BASIS[r.basis]} <span className="muted">· {r.engagement_type}</span></td>
              <td>{r.p25}</td><td><b>{r.p50}</b></td><td>{r.p75}</td>
              <td>{r.sample_count ?? "n/a"} {r.coverage !== "ok" && <Chip tone={r.coverage}>{r.coverage}</Chip>}</td>
              <td>{r.source}</td><td>{r.as_of}</td>
              <td>{r.time_to_fill_weeks != null ? `${r.time_to_fill_weeks} wk` : "unknown"}</td>
              <td className="muted">{r.currency}/{r.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function ImportPanel({ onDone }: { onDone: () => void }) {
  const [csv, setCsv] = useState(TEMPLATE);
  const [syn, setSyn] = useState<boolean | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const { push, host } = useToasts();
  const submit = async () => {
    setErr(null);
    try {
      const r = await hoiApi.importBenchmarks(csv, Boolean(syn));
      push(`Imported ${r.rows} rows (${r.synthetic_rows} synthetic)`, "ok");
      onDone();
    } catch (e) {
      setErr(e as Error);
    }
  };
  return (
    <section className="panel" style={{ marginTop: 16 }} aria-label="Import benchmarks">
      {host}
      <div className="panel-head"><h2>Import curated benchmarks (CSV)</h2></div>
      <div className="panel-body" style={{ display: "grid", gap: 10 }}>
        <input type="file" accept=".csv,text/csv" aria-label="CSV file" onChange={async (e) => { const f = e.target.files?.[0]; if (f) setCsv(await f.text()); }} />
        <textarea className="textarea mono" rows={6} value={csv} onChange={(e) => setCsv(e.target.value)} aria-label="CSV text" />
        <fieldset style={{ border: 0, padding: 0 }}>
          <legend className="label">Provenance (required)</legend>
          <label style={{ marginRight: 16 }}><input type="radio" name="prov" checked={syn === false} onChange={() => setSyn(false)} /> Real licensed or surveyed data</label>
          <label><input type="radio" name="prov" checked={syn === true} onChange={() => setSyn(true)} /> Synthetic / illustrative</label>
        </fieldset>
        <InlineError error={err} />
        <div><button className="btn btn-primary" disabled={syn === null} onClick={submit}>Import (all-or-nothing)</button></div>
      </div>
    </section>
  );
}

function Analysis({ sel }: { sel: ReturnType<typeof useSelectedOpp> }) {
  const [res, setRes] = useState<HoiMarketAnalysis | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const { has } = useRoles();
  const run = async () => {
    setBusy(true); setErr(null);
    try { setRes(await hoiApi.marketAnalysis(sel.selected)); } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div className="chip-row"><OppPicker opps={sel.opps} selected={sel.selected} select={(id) => { sel.select(id); setRes(null); }} />
        {has("manager", "finance", "hr", "admin") && <button className="btn btn-primary" disabled={busy} onClick={run}>Generate benchmark snapshot</button>}
      </div>
      <SyntheticBanner show={Boolean(sel.current?.is_synthetic)} />
      <InlineError error={err} />
      {res && (
        <>
          <div className="muted">{res.note} Snapshot <span className="mono">{res.snapshot_hash.slice(0, 12)}…</span></div>
          {res.roles.map((r) => (
            <section className="panel" key={r.requirement_id} aria-label={`Market for ${r.role_name}`}>
              <div className="panel-head"><h2>{r.role_name}</h2><Chip>{r.geography ?? "no geography"}</Chip></div>
              <div className="panel-body" style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))" }}>
                {Object.entries(r.bases).map(([b, v]) => (
                  <div key={b}>
                    <div className="label">{BASIS[b] ?? pretty(b)}</div>
                    {Array.isArray(v) ? v.map((x) => (
                      <div key={x.benchmark_id}>
                        P25 {x.p25} · <b>P50 {x.p50}</b> · P75 {x.p75} <span className="muted">{x.currency}/{x.unit} · n={x.sample_count ?? "n/a"} · {x.as_of}</span>{" "}
                        {x.coverage !== "ok" && <Chip tone={x.coverage}>{x.coverage}</Chip>}
                      </div>
                    )) : <span className="muted">Unavailable — {v.detail}</span>}
                  </div>
                ))}
              </div>
            </section>
          ))}
        </>
      )}
    </div>
  );
}
