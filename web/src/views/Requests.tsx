import { useState } from "react";
import { Link } from "react-router-dom";
import { requestsApi } from "../api/endpoints";
import type { RequestSummary } from "../api/types";
import { int, shortTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Kpi, PageHead, StatusChip } from "../ui/Bits";
import { IconPlus } from "../ui/Icons";
import { EmptyState, ErrorState, Loading } from "../ui/States";

type Tab = "all" | "open" | "decided";

export default function Requests() {
  const q = useApi((s) => requestsApi.list(s), []);
  const [tab, setTab] = useState<Tab>("all");
  const newButton = (
    <Link className="btn btn-primary" to="/capability">
      <IconPlus /> New request
    </Link>
  );
  return (
    <>
      <PageHead
        trail={["Requests", "Staffing pipeline"]}
        title="Requests"
        lede="Staffing requests you own. Rankings are stored exactly as the engine returned them."
        aside={newButton}
      />
      {q.status === "loading" && <Loading label="Loading requests" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && <RequestsBody requests={q.data.requests} tab={tab} setTab={setTab} />}
    </>
  );
}

function RequestsBody({ requests, tab, setTab }: { requests: RequestSummary[]; tab: Tab; setTab: (t: Tab) => void }) {
  const open = requests.filter((r) => r.status === "open");
  const decided = requests.filter((r) => r.status !== "open");
  const shown = tab === "open" ? open : tab === "decided" ? decided : requests;
  if (requests.length === 0) {
    return (
      <EmptyState
        title="No staffing requests yet"
        action={
          <Link className="btn btn-primary" to="/capability">
            Find capability
          </Link>
        }
      >
        Rank candidates for a set of required skills to create your first request.
      </EmptyState>
    );
  }
  const tabs: [Tab, string, number][] = [
    ["all", "All", requests.length],
    ["open", "Open", open.length],
    ["decided", "Decided", decided.length],
  ];
  return (
    <>
      <section className="kpis" aria-label="Request figures">
        <Kpi label="Requests" value={int(requests.length)} />
        <Kpi label="Awaiting decision" value={int(open.length)} />
        <Kpi label="Decided" value={int(decided.length)} />
      </section>
      <div className="section">
        <div className="tabs" role="tablist">
          {tabs.map(([key, label, count]) => (
            <button key={key} role="tab" className="tab" aria-selected={tab === key} onClick={() => setTab(key)}>
              {label}
              <span className="count">{count}</span>
            </button>
          ))}
        </div>
        <div className="panel table-wrap">
          <table className="data" aria-label="Staffing requests">
            <thead>
              <tr>
                <th>Request</th>
                <th>Capability scope</th>
                <th className="right">Candidates</th>
                <th className="right">Excluded</th>
                <th>Status</th>
                <th>Decision</th>
                <th>Created</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No requests in this view.
                  </td>
                </tr>
              )}
              {shown.map((r) => (
                <tr key={r.request_id} data-testid={`request-${r.request_id}`}>
                  <td>
                    <div className="mono" style={{ fontWeight: 500 }}>
                      {r.request_id}
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      Owner {r.owner}
                    </div>
                  </td>
                  <td>
                    <div className="chips">
                      {Object.entries(r.requirements.required_skills ?? {}).map(([skill, lvl]) => (
                        <span key={skill} className={`chip ${r.requirements.critical_skills?.includes(skill) ? "chip-crimson" : ""}`}>
                          {skill} · L{lvl}
                        </span>
                      ))}
                      {!r.requirements.required_skills && <span className="muted">Not recorded</span>}
                    </div>
                  </td>
                  <td className="right num">{int(r.candidate_count)}</td>
                  <td className="right num">{int(r.excluded_count)}</td>
                  <td>
                    <StatusChip status={r.status} />
                  </td>
                  <td>
                    {r.decision.status ? (
                      <span className="mono">{r.decision.chosen_coded_identity ?? "No candidate"}</span>
                    ) : (
                      <span className="muted">Awaiting owner</span>
                    )}
                  </td>
                  <td className="num muted">{shortTime(r.created_at)}</td>
                  <td className="right">
                    <Link className="btn btn-sm" to={`/requests/${encodeURIComponent(r.request_id)}`}>
                      Inspect
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
