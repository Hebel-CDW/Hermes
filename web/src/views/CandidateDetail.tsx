import { Link, useParams, useSearchParams } from "react-router-dom";
import { requestsApi } from "../api/endpoints";
import type { RankedCandidate, RequestDetail, SkillContribution } from "../api/types";
import { useAuth } from "../lib/auth";
import { exclusionText, fixed, pct } from "../lib/format";
import { displayName, useNames } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { useResolvedNames } from "../lib/useResolvedNames";
import { Levels, PageHead } from "../ui/Bits";
import { IconArrowLeft, IconArrowRight } from "../ui/Icons";
import { EmptyState, ErrorState, Loading } from "../ui/States";

/**
 * Candidate detail + score derivation. Everything shown is read from the ranking result
 * the server stored at rank time (GET /api/staffing/requests/{id}); nothing is recomputed.
 */
export default function CandidateDetail() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const requestId = params.get("request");
  const view = params.get("view") === "derivation" ? "derivation" : "detail";

  if (!requestId) {
    return (
      <EmptyState
        title="Open a candidate from a ranked request"
        action={
          <Link className="btn" to="/capability">
            Find people
          </Link>
        }
      >
        Candidate detail is always shown in the context of the staffing request that ranked them.
      </EmptyState>
    );
  }
  return <CandidateLoader key={`${requestId}|${id}`} requestId={requestId} codedIdentity={id} view={view} />;
}

function CandidateLoader({ requestId, codedIdentity, view }: { requestId: string; codedIdentity: string; view: "detail" | "derivation" }) {
  const { session } = useAuth();
  const { label } = useNames();
  const q = useApi((s) => requestsApi.get(requestId, s), [requestId]);
  const { names } = useResolvedNames(requestId, {
    enabled: q.status === "success" && (q.data.result?.candidates?.length ?? 0) > 0,
    auto: session?.data_classification === "synthetic",
  });
  const titleName = (coded: string) => displayName(coded, label, names);
  const back = (
    <Link className="back-link" to={`/requests/${encodeURIComponent(requestId)}`}>
      <IconArrowLeft /> Who fits
    </Link>
  );
  if (q.status === "loading") return (<>{back}<Loading label="Loading candidate" rows={4} /></>);
  if (q.status === "error") return (<>{back}<ErrorState error={q.error} onRetry={q.reload} /></>);

  const candidates = q.data.result?.candidates ?? [];
  const index = candidates.findIndex((c) => c.coded_identity === codedIdentity);
  const excluded = (q.data.result?.excluded_candidates ?? []).find((e) => e.coded_identity === codedIdentity);

  if (index < 0) {
    return (
      <>
        {back}
        <PageHead trail={["Candidate", "Not shortlisted"]} title={titleName(codedIdentity) ?? <span className="mono">{codedIdentity}</span>} />
        {excluded ? (
          <div className="state error" data-testid="candidate-excluded">
            <h3>Excluded by the engine</h3>
            <p>{exclusionText(excluded.reason)}.</p>
            <span className="code">{excluded.reason}</span>
          </div>
        ) : (
          <EmptyState title="Candidate not in this ranking">This coded identity was neither shortlisted nor excluded for this request.</EmptyState>
        )}
      </>
    );
  }

  const candidate = candidates[index];
  const link = (c: RankedCandidate, v = view) =>
    `/capability/${encodeURIComponent(c.coded_identity)}?request=${encodeURIComponent(requestId)}${v === "derivation" ? "&view=derivation" : ""}`;
  const prev = candidates[index - 1];
  const next = candidates[index + 1];

  return (
    <>
      {back}
      <PageHead
        trail={["Who fits", view === "derivation" ? "How the score was made" : "Why this person"]}
        title={titleName(candidate.coded_identity) ? <span data-testid="resolved-name">{titleName(candidate.coded_identity)}</span> : "This person"}
        lede={
          <span className="chips" style={{ marginTop: 6 }}>
            <span className="person-token" data-testid="candidate-id">
              {candidate.coded_identity}
            </span>
            <span className="chip chip-crimson">Rank #{candidate.rank}</span>
          </span>
        }
        aside={
          <div style={{ display: "flex", gap: 8 }}>
            {prev ? (
              <Link className="btn btn-sm" to={link(prev)} aria-label="Previous candidate">
                <IconArrowLeft width={14} height={14} /> #{prev.rank}
              </Link>
            ) : null}
            {next ? (
              <Link className="btn btn-sm" to={link(next)} aria-label="Next candidate">
                #{next.rank} <IconArrowRight width={14} height={14} />
              </Link>
            ) : null}
          </div>
        }
      />
      <div className="tabs" role="tablist">
        <Link role="tab" className="tab" aria-selected={view === "detail"} to={link(candidate, "detail")}>
          Why this person
        </Link>
        <Link role="tab" className="tab" aria-selected={view === "derivation"} to={link(candidate, "derivation")}>
          How the score was made
        </Link>
      </div>
      {view === "detail" ? (
        <Detail candidate={candidate} request={q.data} derivationLink={link(candidate, "derivation")} />
      ) : (
        <Derivation candidate={candidate} request={q.data} />
      )}
    </>
  );
}

/** Skills in the order the request declared them, then any extra keys the engine reported. */
function orderedSkills(candidate: RankedCandidate, request: RequestDetail): SkillContribution[] {
  const declared = Object.keys(request.requirements.required_skills ?? {});
  const keys = [...declared.filter((k) => k in candidate.reasoning_detail), ...Object.keys(candidate.reasoning_detail).filter((k) => !declared.includes(k))];
  return keys.map((k) => candidate.reasoning_detail[k]);
}

const STATUS_CHIP: Record<string, string> = { matched: "chip-ok", adjacent: "chip-warn", missing: "chip-crimson" };

function Detail({ candidate, request, derivationLink }: { candidate: RankedCandidate; request: RequestDetail; derivationLink: string }) {
  const calc = candidate.calculation;
  const skills = orderedSkills(candidate, request);
  const skillName = useSkillName();
  const STATUS_LABEL: Record<string, string> = { matched: "Has it", adjacent: "Close", missing: "Missing" };
  return (
    <>
      <div className="grid cols-3">
        <section className="panel">
          <div className="panel-body">
            <div className="label">How well they fit</div>
            <div className="fitness-hero" style={{ marginTop: 8 }}>
              <span className="fitness-value" data-testid="fitness" data-value={candidate.fitness_score}>
                {fixed(candidate.fitness_score)}
              </span>
            </div>
            <div className="kpi-note" data-testid="fitness-plain">
              {pct(candidate.fitness_score)} — for comparing people, not a pass mark
            </div>
            <Link className="btn btn-primary" to={derivationLink} style={{ marginTop: 16 }}>
              See how this score was made
            </Link>
          </div>
        </section>
        <section className="panel">
          <div className="panel-body">
            <div className="label">Skills they have</div>
            <div className="kpi-value">{calc ? pct(calc.coverage_ratio) : "—"}</div>
            <div className="kpi-note">
              {calc ? `Evidence for ${calc.matched_skill_count} of ${calc.required_skill_count} skills` : "Not reported"}
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-body">
            <div className="label">What to do next</div>
            <Link className="btn" to="/learning" style={{ marginTop: 12 }}>
              What should they learn?
            </Link>
          </div>
        </section>
      </div>

      <section className="panel section">
        <div className="panel-head">
          <h2>Skills in plain English</h2>
          <span className="muted" style={{ fontSize: 12 }}>
            Needed vs what they have shown
          </span>
        </div>
        <div className="table-wrap">
          <table className="data" aria-label="Capability delta">
            <thead>
              <tr>
                <th>Capability</th>
                <th>Status</th>
                <th>Required</th>
                <th>Demonstrated</th>
                <th className="right">Confidence</th>
                <th className="right">Freshness</th>
              </tr>
            </thead>
            <tbody>
              {skills.map((s) => (
                <tr key={s.skill_id} data-testid="delta-row">
                  <td>
                    <div style={{ fontWeight: 500 }}>{skillName(s.skill_id)}</div>
                  </td>
                  <td>
                    <span className={`chip ${STATUS_CHIP[s.status] ?? ""}`}>{STATUS_LABEL[s.status] ?? s.status}</span>
                  </td>
                  <td>
                    <Levels level={s.required_level} required /> <span className="num muted">L{s.required_level ?? "—"}</span>
                  </td>
                  <td>
                    {s.actual_level ? (
                      <>
                        <Levels level={s.actual_level} /> <span className="num muted">L{s.actual_level}</span>
                        {s.required_level && s.actual_level < s.required_level && (
                          <span className="gap-tag" style={{ marginLeft: 8 }}>
                            Below required
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="gap-tag">No evidence</span>
                    )}
                  </td>
                  <td className="right num">{pct(s.confidence)}</td>
                  <td className="right num">{pct(s.freshness)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

function Operand({ label, value, testid }: { label: string; value: string; testid?: string }) {
  return (
    <div className="operand">
      <div className="label">{label}</div>
      <div className="v" data-testid={testid}>
        {value}
      </div>
    </div>
  );
}

function Derivation({ candidate, request }: { candidate: RankedCandidate; request: RequestDetail }) {
  const calc = candidate.calculation;
  const skills = orderedSkills(candidate, request);
  const skillName = useSkillName();
  if (!calc) {
    return <EmptyState title="No calculation envelope">The stored ranking for this candidate does not include a calculation trace.</EmptyState>;
  }
  // Substitution uses the exact backend numbers (no rounding, no arithmetic).
  const terms = skills.map((s) => String(s.contribution ?? 0)).join(" + ");
  const stages: [string, string, string][] = [
    ["01", "Evidence records", String(candidate.evidence_ids.length)],
    ["02", "Skills evidenced", `${calc.matched_skill_count} / ${calc.required_skill_count}`],
    ["03", "Coverage", `${pct(calc.coverage_ratio)} (floor ${pct(calc.min_coverage_ratio)})`],
    ["04", "Contribution sum", fixed(calc.contribution_sum)],
    ["05", "Mean contribution", fixed(calc.mean_contribution)],
    ["06", "× Allocation", fixed(calc.allocation_multiplier)],
  ];

  return (
    <>
      <div className="grid cols-3">
        <section className="panel" style={{ gridColumn: "span 2" }}>
          <div className="panel-body">
            <div className="label">Final fitness</div>
            <div className="fitness-hero" style={{ marginTop: 8 }}>
              <span className="fitness-value" data-testid="derivation-fitness" data-value={calc.fitness_score}>
                {fixed(calc.fitness_score)}
              </span>
              <span className="mono muted">({calc.fitness_score})</span>
            </div>
            {calc.excluded && (
              <div className="inline-error" style={{ marginTop: 12 }}>
                Excluded: {exclusionText(calc.exclusion_reason ?? "")}
              </div>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-body">
            <dl className="dl">
              <dt>Run id</dt>
              <dd className="mono" data-testid="run-id">
                {calc.computation_run_id || "not recorded"}
              </dd>
              <dt>Config version</dt>
              <dd className="mono" data-testid="config-version">
                {calc.scoring_config_version}
              </dd>
              <dt>Computed at</dt>
              <dd className="num">{request.result.computed_at}</dd>
            </dl>
          </div>
        </section>
      </div>

      <div className="pipeline section" aria-label="Derivation pipeline">
        {stages.map(([n, label, value]) => (
          <div className="stage" key={n}>
            <div className="n">{n}</div>
            <div className="label">{label}</div>
            <div className="v">{value}</div>
          </div>
        ))}
      </div>

      <section className="section">
        <div className="panel-head" style={{ padding: "0 0 10px", border: 0 }}>
          <span className="label">Capability ledger</span>
          <span className="mono muted" style={{ fontSize: 12 }}>
            contribution = level_ratio × confidence × volume × freshness × adjacency
          </span>
        </div>
        <div className="ledger">
          {skills.map((s) => (
            <div className="ledger-row" key={s.skill_id} data-testid={`ledger-${s.skill_id}`}>
              <div>
                <div style={{ fontWeight: 600 }}>{skillName(s.skill_id)}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  {s.status}
                  {s.adjacency_source_skill ? ` via ${s.adjacency_source_skill}` : ""} · level ratio {fixed(s.level_ratio)}
                  {s.half_life_days !== null ? ` · half-life ${s.half_life_days}d` : ""}
                </div>
              </div>
              <Operand label="Required" value={s.required_level === null ? "—" : `L${s.required_level}`} />
              <Operand label="Demonstrated" value={s.actual_level === null ? "—" : `L${s.actual_level}`} />
              <Operand label="Confidence" value={fixed(s.confidence)} testid={`confidence-${s.skill_id}`} />
              <Operand label="Volume" value={fixed(s.volume_score)} testid={`volume-${s.skill_id}`} />
              <Operand label="Freshness" value={fixed(s.freshness)} testid={`freshness-${s.skill_id}`} />
              <Operand label="Adjacency" value={fixed(s.adjacency_discount)} testid={`adjacency-${s.skill_id}`} />
              <div className="contribution">
                <div className="label">Contribution</div>
                <div className="v crimson" data-testid={`contribution-${s.skill_id}`} data-value={s.contribution ?? ""}>
                  {s.contribution === null ? "0 (missing)" : fixed(s.contribution, 6)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel section">
        <div className="panel-head">
          <h2>Composite formula</h2>
          <button
            className="btn btn-sm"
            onClick={() => {
              const blob = new Blob([JSON.stringify(candidate, null, 2)], { type: "application/json" });
              const a = document.createElement("a");
              a.href = URL.createObjectURL(blob);
              a.download = `${request.request_id}-${candidate.coded_identity}-derivation.json`;
              a.click();
              URL.revokeObjectURL(a.href);
            }}
          >
            Export JSON
          </button>
        </div>
        <div className="panel-body grid" style={{ gap: 12 }}>
          <pre className="formula">{calc.formula}</pre>
          <pre className="formula" data-testid="formula-substituted">
            {`mean    = (${terms}) / ${calc.required_skill_count} = ${calc.mean_contribution}\nfitness = ${calc.mean_contribution} × ${calc.allocation_multiplier} = ${calc.fitness_score}`}
          </pre>
          <details>
            <summary className="label" style={{ cursor: "pointer" }}>
              Raw calculation payload
            </summary>
            <pre className="formula" style={{ marginTop: 8, maxHeight: 360 }}>
              {JSON.stringify(candidate, null, 2)}
            </pre>
          </details>
        </div>
      </section>
    </>
  );
}
