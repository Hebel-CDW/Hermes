import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { requestsApi } from "../api/endpoints";
import { ApiError } from "../api/http";
import type { DecisionBody, DecisionStatus, RequestDetail as Detail } from "../api/types";
import { useAuth } from "../lib/auth";
import { exclusionText, fixed, int, pct, shortTime } from "../lib/format";
import { displayName, useNames } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { useResolvedNames } from "../lib/useResolvedNames";
import { useMotionSafe } from "../motion/PageMotion";
import { PageHead, StatusChip } from "../ui/Bits";
import { IconArrowLeft, IconLock } from "../ui/Icons";
import { rememberRequest } from "../ui/Guide";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

export default function RequestDetail() {
  const { id = "" } = useParams();
  const q = useApi((s) => requestsApi.get(id, s), [id]);
  return (
    <>
      <Link className="back-link" to="/capability">
        <IconArrowLeft /> Find people
      </Link>
      {q.status === "loading" && <Loading label="Loading request" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && <DetailBody key={q.data.request_id} data={q.data} reload={q.reload} />}
    </>
  );
}

function DetailBody({ data, reload }: { data: Detail; reload: () => void }) {
  const { session } = useAuth();
  const { label } = useNames();
  const skillName = useSkillName();
  const { fade } = useMotionSafe();
  const synthetic = session?.data_classification === "synthetic";
  const result = data.result;
  const hasResult = Array.isArray(result?.candidates);
  const candidates = hasResult ? result.candidates : [];
  const excluded = hasResult ? result.excluded_candidates : [];
  const { names, pending: resolving, error: resolveError, resolve } = useResolvedNames(data.request_id, {
    enabled: hasResult && candidates.length > 0,
    auto: synthetic,
  });
  const candidateLink = (coded: string) => `/capability/${encodeURIComponent(coded)}?request=${encodeURIComponent(data.request_id)}`;
  const shown = (coded: string) => displayName(coded, label, names);
  useEffect(() => {
    rememberRequest(data.request_id);
  }, [data.request_id]);

  return (
    <>
      <PageHead
        trail={["Find people", "Who fits"]}
        title="Who fits"
        lede="Ranked from skills they have already shown. You still choose."
        aside={<StatusChip status={data.status} />}
      />

      <div className="grid cols-3">
        <section className="panel" style={{ gridColumn: "span 2" }}>
          <div className="panel-head">
            <h2>What this role needs</h2>
          </div>
          <div className="panel-body">
            {data.requirements.required_skills ? (
              <>
                <div className="chips">
                  {Object.entries(data.requirements.required_skills).map(([skill, lvl]) => (
                    <span key={skill} className={`chip ${data.requirements.critical_skills?.includes(skill) ? "chip-crimson" : ""}`}>
                      {skillName(skill)} · L{lvl}
                      {data.requirements.critical_skills?.includes(skill) ? " · critical" : ""}
                    </span>
                  ))}
                </div>
                <details className="disclosure">
                  <summary>Advanced</summary>
                <dl className="dl" style={{ marginTop: 8, maxWidth: 420 }}>
                  <dt>Minimum coverage</dt>
                  <dd className="num">{data.requirements.min_coverage_ratio == null ? "Engine default" : pct(data.requirements.min_coverage_ratio)}</dd>
                  <dt>Shortlist size</dt>
                  <dd className="num">{data.requirements.shortlist_size ?? "—"}</dd>
                </dl>
                </details>
              </>
            ) : (
              <span className="muted">Requirements were not recorded for this request.</span>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Next</h2>
          </div>
          <div className="panel-body">
            <p className="ink-2" style={{ margin: "0 0 12px" }}>
              After you pick someone, see the whole team or what they should learn.
            </p>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Link className="btn btn-sm" to="/matrix">
                Team skills
              </Link>
              <Link className="btn btn-sm" to="/learning">
                Learning
              </Link>
            </div>
          </div>
        </section>
      </div>

      {!hasResult ? (
        <div className="section">
          <EmptyState title="No stored ranking">
            This request has no stored ranking result, so candidates cannot be shown. Re-rank it from Find people using the same request id.
          </EmptyState>
        </div>
      ) : (
        <>
          <section className="panel section">
            <div className="panel-head">
              <h2>Who fits</h2>
              <span className="muted" style={{ fontSize: 12 }}>
                Best match first
              </span>
            </div>
            {candidates.length === 0 ? (
              <div className="panel-body muted">The engine shortlisted no candidates for these requirements.</div>
            ) : (
              <div className="table-wrap">
                <p className="muted" style={{ margin: "0 0 8px", padding: "0 16px", fontSize: 13 }} data-testid="fit-explainer">
                  Fit compares people with each other. It is not a pass mark, and stays low when little proof of work is on file.
                </p>
                <table className="data" aria-label="Ranked candidates">
                  <thead>
                    <tr>
                      <th>Rank</th>
                      <th>Person</th>
                      <th className="right">Fit</th>
                      <th>
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((c, i) => (
                      <motion.tr key={c.coded_identity} data-testid="ranked-row" {...fade(i * 0.05)}>
                        <td className="num">#{c.rank}</td>
                        <td>
                          {shown(c.coded_identity) ? (
                            <div style={{ fontWeight: 600 }} data-testid="resolved-name">
                              {shown(c.coded_identity)}
                            </div>
                          ) : (
                            <span className="protected">
                              <IconLock width={12} height={12} /> Identity protected
                            </span>
                          )}
                          <div className="person-token" data-testid="ranked-identity">
                            {c.coded_identity}
                          </div>
                        </td>
                        <td className="right">
                          <div>{pct(c.fitness_score)}</div>
                          <div className="mono muted" data-testid="ranked-fitness">
                            {fixed(c.fitness_score)}
                          </div>
                          {c.calculation ? (
                            <div className="muted" style={{ fontSize: 12 }}>
                              evidence for {c.calculation.matched_skill_count} of {c.calculation.required_skill_count} skills
                            </div>
                          ) : null}
                        </td>
                        <td className="right">
                          <Link className="btn btn-sm" to={candidateLink(c.coded_identity)}>
                            Why
                          </Link>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="panel section" aria-label="Excluded candidates">
            <div className="panel-head">
              <h2>Not a fit this time</h2>
              <span className="muted" style={{ fontSize: 12 }}>
                {int(excluded.length)} not shortlisted
              </span>
            </div>
            {excluded.length === 0 ? (
              <div className="panel-body muted">No candidates were excluded.</div>
            ) : (
              <div className="table-wrap">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Person</th>
                      <th>Why not</th>
                    </tr>
                  </thead>
                  <tbody>
                    {excluded.map((e) => (
                      <tr key={e.coded_identity} data-testid="excluded-row">
                        <td>
                          {shown(e.coded_identity) ? (
                            <div style={{ fontWeight: 600 }}>{shown(e.coded_identity)}</div>
                          ) : null}
                          <div className="person-token">{e.coded_identity}</div>
                        </td>
                        <td>{exclusionText(e.reason)}</td>
                        <td className="sr-only" data-testid="excluded-reason">
                          {e.reason}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <div className={`grid ${synthetic ? "" : "cols-2"} section`}>
            {synthetic && <InlineError error={resolveError} />}
            {!synthetic && (
            <ResolvePanel
              hasShortlist={candidates.length > 0}
              names={names}
              pending={resolving}
              error={resolveError}
              onResolve={resolve}
              auto={false}
            />
            )}
            <DecisionPanel data={data} names={names} overlay={label} onDecided={reload} />
          </div>
        </>
      )}
    </>
  );
}

function ResolvePanel({
  hasShortlist,
  names,
  pending,
  error,
  onResolve,
  auto,
}: {
  hasShortlist: boolean;
  names: Record<string, string> | null;
  pending: boolean;
  error: Error | null;
  onResolve: () => Promise<void>;
  auto: boolean;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Identity resolution</h2>
        {names ? <span className="chip chip-warn">Resolved · audited</span> : <span className="chip">Protected</span>}
      </div>
      <div className="panel-body grid" style={{ gap: 12 }}>
        <p className="ink-2" style={{ margin: 0 }}>
          {auto
            ? "Synthetic demo auto-resolves the shortlist through the audited identity API. Scoring still ran on coded tokens only; names never enter the ranking payload and are not stored by the browser."
            : "Candidates stay coded until the owning manager requests resolution. Each resolution is written to the audit ledger and rate-limited. Names are held in this page only and are never stored by the browser."}
        </p>
        {!names && (
          <button className="btn" onClick={() => void onResolve()} disabled={pending || !hasShortlist} style={{ justifySelf: "start" }}>
            <IconLock width={14} height={14} /> {pending ? "Resolving…" : "Resolve shortlist identities"}
          </button>
        )}
        {!hasShortlist && <span className="hint">There is no shortlist to resolve.</span>}
        <InlineError error={error} />
      </div>
    </section>
  );
}

function DecisionPanel({
  data,
  names,
  overlay,
  onDecided,
}: {
  data: Detail;
  names: Record<string, string> | null;
  overlay: (coded: string) => string;
  onDecided: () => void;
}) {
  const shortlist = data.result.candidates;
  const [status, setStatus] = useState<DecisionStatus>("accepted");
  const [chosen, setChosen] = useState<string>(shortlist[0]?.coded_identity ?? "");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  if (data.status !== "open") {
    return (
      <section className="panel" aria-label="Decision">
        <div className="panel-head">
          <h2>Decision</h2>
          <StatusChip status={data.decision.status} />
        </div>
        <div className="panel-body">
          <dl className="dl">
            <dt>Chosen candidate</dt>
            <dd>
              {data.decision.chosen_coded_identity && displayName(data.decision.chosen_coded_identity, overlay, names) ? (
                <div data-testid="resolved-name">{displayName(data.decision.chosen_coded_identity, overlay, names)}</div>
              ) : null}
              <span className="mono">{data.decision.chosen_coded_identity ?? "None"}</span>
            </dd>
            <dt>Engine rank of choice</dt>
            <dd className="num">{data.decision.engine_rank_of_choice ?? "—"}</dd>
            <dt>Approved by</dt>
            <dd>{data.decision.approved_by ?? "—"}</dd>
            <dt>Decided at</dt>
            <dd className="num">{shortTime(data.decision.decided_at)}</dd>
          </dl>
        </div>
      </section>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    // Owner and approver are never sent: the server takes them from the verified token.
    const body: DecisionBody = { status };
    if (status !== "rejected") body.chosen_coded_identity = chosen;
    if (status === "rejected" && note) body.rejection_reason = note;
    if (status === "overridden" && note) body.override_note = note;
    try {
      await requestsApi.decide(data.request_id, body);
      onDecided();
    } catch (err) {
      setError(err as Error);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="panel" aria-label="Decision">
      <div className="panel-head">
        <h2>Choose someone</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          You decide. Hermes only ranks.
        </span>
      </div>
      <form className="panel-body" onSubmit={submit}>
        <div className="field">
          <span className="label">Outcome</span>
          <div className="radio-group">
            {(["accepted", "overridden", "rejected"] as DecisionStatus[]).map((s) => (
              <label key={s} className={`radio ${status === s ? "checked" : ""}`}>
                <input type="radio" name="status" value={s} checked={status === s} onChange={() => setStatus(s)} />
                {s === "accepted" ? "This person" : s === "overridden" ? "Someone else on the list" : "No one"}
              </label>
            ))}
          </div>
        </div>
        {status !== "rejected" && (
          <label className="field">
            <span className="label">Candidate</span>
            <select name="chosen_coded_identity" className="select" value={chosen} onChange={(e) => setChosen(e.target.value)} disabled={shortlist.length === 0}>
              {shortlist.map((c) => (
                <option key={c.coded_identity} value={c.coded_identity}>
                  #{c.rank} · {displayName(c.coded_identity, overlay, names) ?? c.coded_identity}
                </option>
              ))}
            </select>
          </label>
        )}
        {status !== "accepted" && (
          <label className="field">
            <span className="label">{status === "rejected" ? "Rejection reason" : "Override note"}</span>
            <textarea name="note" className="textarea" value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
          </label>
        )}
        <div className="field">
          <InlineError error={error} />
          {error instanceof ApiError && error.status === 409 && (
            <button type="button" className="btn btn-sm" onClick={onDecided} style={{ justifySelf: "start" }}>
              Reload request
            </button>
          )}
          <button className="btn btn-primary" type="submit" disabled={pending || (status !== "rejected" && !chosen)} style={{ justifySelf: "start" }}>
            {pending ? "Saving…" : "Choose this person"}
          </button>
          <span className="hint">Decisions are audited and never fed back into scoring.</span>
        </div>
      </form>
    </section>
  );
}
