import { hoiApi } from "../../api/endpoints";
import { useApi } from "../../lib/useApi";
import { PageHead } from "../../ui/Bits";
import { ErrorState, Loading } from "../../ui/States";
import { Chip, pretty } from "./common";

const FLOW: [string, string][] = [
  ["1 · Sales uploads RFP / SOW / JD", "Encrypted, versioned, checksummed. Validated on the way in."],
  ["2 · Extraction → human validation", "Rules (and optional local model) draft roles and skills with source quotes. A person edits and approves."],
  ["3A · Internal fitness", "Existing Hermes engine over coded identities, plus separate eligibility checks."],
  ["3B · Finance cost service", "Separate encrypted store. Only Finance reads individual cost; others see aggregates."],
  ["3C · Market benchmarks", "Curated CSV imports with source, sample size and as-of date."],
  ["4 · Scenario comparison", "Internal / external / hybrid, qualification first. Nothing is assigned."],
  ["5 · Approvals → report", "Delivery, Finance (and HR where individual pay is used) approve. Redacted export."],
];

const LAYERS: [string, string[]][] = [
  ["Experience", ["React workspace", "Role-based navigation", "Server-enforced permissions"]],
  ["API & access", ["FastAPI", "RBAC + deal-team membership", "Rate limits · audit"]],
  ["Existing Hermes core (unchanged)", ["Identity abstraction / resolution", "Skill inference · evidence merge", "Fitness & gap engine"]],
  ["Opportunity services (new)", ["Document intelligence", "Costing · market · scenarios", "Approvals · export"]],
  ["Governed data", ["Skills / evidence", "Finance vault (encrypted)", "Opportunities · market · audit"]],
];

export default function Architecture() {
  const q = useApi((s) => hoiApi.status(s), []);
  return (
    <>
      <PageHead
        trail={["System", "Architecture & Workflow"]}
        title="Architecture & Workflow"
        lede="How the existing Hermes engine and the Opportunity Intelligence services fit together, and what is and is not connected."
      />
      <section className="panel" aria-label="Workflow">
        <div className="panel-head"><h2>End-to-end opportunity workflow</h2></div>
        <ol className="panel-body" style={{ display: "grid", gap: 8, paddingLeft: 20 }}>
          {FLOW.map(([t, d]) => <li key={t}><b>{t}</b><div className="muted">{d}</div></li>)}
        </ol>
      </section>
      <section className="panel" style={{ marginTop: 16 }} aria-label="Layers">
        <div className="panel-head"><h2>Layered architecture</h2></div>
        <div className="panel-body" style={{ display: "grid", gap: 8 }}>
          {LAYERS.map(([l, items]) => (
            <div key={l} style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
              <span className="label" style={{ minWidth: 220 }}>{l}</span>
              {items.map((i) => <Chip key={i}>{i}</Chip>)}
            </div>
          ))}
        </div>
      </section>
      <section className="panel" style={{ marginTop: 16 }} aria-label="Integration status">
        <div className="panel-head"><h2>Implementation status</h2></div>
        {q.status === "loading" && <Loading label="Loading status" />}
        {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
        {q.status === "success" && (
          <div className="panel-body" style={{ display: "grid", gap: 12 }}>
            <div>
              <div className="label">Implemented in this build (calc {q.data.calc_version})</div>
              <div className="chips">{q.data.implemented.map((i) => <Chip key={i} tone="ok">{pretty(i)}</Chip>)}</div>
            </div>
            <div>
              <div className="label">Pending — needs enterprise access, not simulated</div>
              {Object.entries(q.data.pending_integrations).map(([k, v]) => (
                <div key={k}><Chip tone="unknown">{pretty(k)}</Chip> <span className="muted">{v}</span></div>
              ))}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
