import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { hoiApi, requestsApi } from "../../api/endpoints";
import type { HoiRequirements, HoiRole, HoiShortlist, ResolvedIdentity } from "../../api/types";
import { useApi, useStale } from "../../lib/useApi";
import { Kpi, PageHead } from "../../ui/Bits";
import { useToasts } from "../../ui/Fx";
import { EmptyState, ErrorState, InlineError, Loading } from "../../ui/States";
import { Chip, OppGate, OppPicker, SyntheticBanner, pretty, useRoles, useSelectedOpp } from "./common";

type Tab = "upload" | "requirements" | "matches" | "summary";
const TABS: [Tab, string][] = [
  ["upload", "1 · Upload & extract"],
  ["requirements", "2 · Validate requirements"],
  ["matches", "3 · Internal matches"],
  ["summary", "4 · Decision summary"],
];

export default function Rfp() {
  const sel = useSelectedOpp();
  const [tab, setTab] = useState<Tab>("upload");
  const [creating, setCreating] = useState(false);
  const { has } = useRoles();
  return (
    <>
      <PageHead
        trail={["Opportunity Intelligence", "RFP/SOW Workspace"]}
        title="RFP/SOW Workspace"
        lede="Turn a customer document into a reviewed, approved requirement package. Extraction is a draft; a person approves it before anything is matched."
        aside={
          has("sales", "manager") ? (
            <button className="btn btn-primary" onClick={() => setCreating((c) => !c)}>
              {creating ? "Close" : "New opportunity"}
            </button>
          ) : undefined
        }
      />
      {creating && (
        <NewOpportunity
          onDone={(id) => {
            sel.select(id);
            setCreating(false);
            sel.q.reload();
          }}
        />
      )}
      <OppGate sel={sel}>
        {(opp) => (
          <>
            <div className="chip-row">
              <OppPicker opps={sel.opps} selected={sel.selected} select={sel.select} />
              <Chip>{pretty(opp.stage)}</Chip>
              <Chip>{pretty(opp.contract_type)}</Chip>
              <Chip>
                {opp.duration_months} months · {opp.currency}
              </Chip>
              {opp.geography && <Chip>{opp.geography}</Chip>}
            </div>
            <SyntheticBanner show={opp.is_synthetic} />
            <div className="tabs" role="tablist">
              {TABS.map(([k, label]) => (
                <button key={k} role="tab" aria-selected={tab === k} className="tab" onClick={() => setTab(k)}>
                  {label}
                </button>
              ))}
            </div>
            {tab === "upload" && <UploadTab oid={opp.opportunity_id} onExtracted={() => { sel.q.reload(); setTab("requirements"); }} />}
            {tab === "requirements" && <RequirementsTab oid={opp.opportunity_id} onChanged={sel.q.reload} />}
            {tab === "matches" && <MatchesTab oid={opp.opportunity_id} onChanged={sel.q.reload} />}
            {tab === "summary" && <SummaryTab oid={opp.opportunity_id} readiness={opp.readiness} />}
          </>
        )}
      </OppGate>
    </>
  );
}

// ---------------------------------------------------------------- create
function NewOpportunity({ onDone }: { onDone: (id: string) => void }) {
  const [f, setF] = useState({ client_alias: "", name: "", currency: "USD", contract_type: "time_and_materials", duration_months: "6", geography: "", bid_deadline: "", start_date: "", is_synthetic: false });
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: string | boolean) => setF((x) => ({ ...x, [k]: v }));
  const submit = async () => {
    setBusy(true);
    setErr(null);
    try {
      const o = await hoiApi.create({
        ...f,
        duration_months: Number(f.duration_months),
        geography: f.geography || null,
        bid_deadline: f.bid_deadline || null,
        start_date: f.start_date || null,
      });
      onDone(o.opportunity_id);
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel" aria-label="New opportunity" style={{ marginBottom: 16 }}>
      <div className="panel-head"><h2>New opportunity</h2></div>
      <div className="panel-body" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))" }}>
        <Field label="Customer alias"><input className="input" value={f.client_alias} onChange={(e) => set("client_alias", e.target.value)} /></Field>
        <Field label="Opportunity name"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Currency"><input className="input" maxLength={3} value={f.currency} onChange={(e) => set("currency", e.target.value.toUpperCase())} /></Field>
        <Field label="Contract type">
          <select className="select" value={f.contract_type} onChange={(e) => set("contract_type", e.target.value)}>
            {["time_and_materials", "fixed_fee", "managed_service", "blended"].map((c) => <option key={c} value={c}>{pretty(c)}</option>)}
          </select>
        </Field>
        <Field label="Duration (months)"><input className="input" type="number" min={1} max={120} value={f.duration_months} onChange={(e) => set("duration_months", e.target.value)} /></Field>
        <Field label="Geography"><input className="input" value={f.geography} onChange={(e) => set("geography", e.target.value)} /></Field>
        <Field label="Bid deadline"><input className="input" type="date" value={f.bid_deadline} onChange={(e) => set("bid_deadline", e.target.value)} /></Field>
        <Field label="Planned start"><input className="input" type="date" value={f.start_date} onChange={(e) => set("start_date", e.target.value)} /></Field>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={f.is_synthetic} onChange={(e) => set("is_synthetic", e.target.checked)} /> Mark as synthetic demo data
        </label>
      </div>
      <div className="panel-body">
        <InlineError error={err} />
        <button className="btn btn-primary" disabled={busy || !f.client_alias || !f.name} onClick={submit}>{busy ? "Creating…" : "Create opportunity"}</button>
      </div>
    </section>
  );
}

const Field = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <label className="field compact"><span className="label">{label}</span>{children}</label>
);

// ---------------------------------------------------------------- tab 1
async function toBase64(file: File): Promise<string> {
  const buf = new Uint8Array(await file.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(bin);
}

function UploadTab({ oid, onExtracted }: { oid: string; onExtracted: () => void }) {
  const docs = useApi((s) => hoiApi.documents(oid, s), [oid]);
  const status = useApi((s) => hoiApi.status(s), []);
  const { has } = useRoles();
  const canEdit = has("sales", "manager");
  const [docType, setDocType] = useState("sow");
  const [file, setFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const [useLlm, setUseLlm] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const { push, host } = useToasts();
  const list = useStale(docs)?.documents ?? [];

  const upload = async () => {
    if (!file) return;
    setBusy("upload");
    setErr(null);
    try {
      const d = await hoiApi.upload(oid, { doc_type: docType, filename: file.name, content_b64: await toBase64(file) });
      push(d.duplicate ? "Identical file already uploaded; nothing was added" : "Document stored (encrypted) and versioned", "ok");
      setFile(null);
      setInputKey((k) => k + 1); // clears the native file input
      docs.reload();
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(null);
    }
  };
  const extract = async () => {
    setBusy("extract");
    setErr(null);
    try {
      await hoiApi.extract(oid, useLlm);
      push("Draft requirements created. Review them before approving.", "ok");
      onExtracted();
    } catch (e) {
      setErr(e as Error);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div style={{ display: "grid", gap: 16 }}>
      {host}
      {canEdit && (
        <section className="panel">
          <div className="panel-head"><h2>Upload customer requirements</h2></div>
          <div className="panel-body" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
            <Field label="Document type">
              <select className="select" value={docType} onChange={(e) => setDocType(e.target.value)}>
                <option value="sow">SOW</option><option value="rfp">RFP</option><option value="jd">Job description</option>
              </select>
            </Field>
            <Field label={`File (${(status.status === "success" ? status.data.limits.formats : [".pdf", ".docx", ".txt"]).join(", ")})`}>
              <input key={inputKey} className="input" type="file" accept=".pdf,.docx,.txt" aria-label="Document file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </Field>
            <button className="btn" disabled={!file || busy !== null} onClick={upload}>{busy === "upload" ? "Uploading…" : "Upload"}</button>
          </div>
          <div className="panel-body muted">
            Files are validated (type, signature, size, active content), checksummed, versioned and stored encrypted. Malware scanning and OCR are not
            connected in this prototype; a file that cannot be read as text is reported, never guessed.
          </div>
        </section>
      )}
      <section className="panel table-wrap">
        <div className="panel-head"><h2>Documents</h2></div>
        {docs.status === "loading" && !list.length && <Loading label="Loading documents" />}
        {docs.status === "error" && <ErrorState error={docs.error} onRetry={docs.reload} />}
        {docs.status !== "loading" && !list.length && docs.status !== "error" && <EmptyState title="No documents yet">Upload an SOW, RFP or job description.</EmptyState>}
        {list.length > 0 && (
          <table className="data">
            <thead><tr><th>File</th><th>Type</th><th>Version</th><th>SHA-256</th><th>Malware scan</th><th>Text</th></tr></thead>
            <tbody>
              {list.map((d) => (
                <tr key={d.document_id}>
                  <td>{d.filename}</td><td>{d.doc_type.toUpperCase()}</td><td>v{d.version}</td>
                  <td className="mono">{d.checksum.slice(0, 12)}…</td>
                  <td><Chip tone={d.scan_status === "not_scanned" ? "unknown" : "ok"}>{pretty(d.scan_status)}</Chip></td>
                  <td><Chip tone={d.text_status === "ok" ? "ok" : "unknown"}>{pretty(d.text_status)}</Chip></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      {canEdit && (
        <section className="panel">
          <div className="panel-body" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <button className="btn btn-primary" disabled={!list.length || busy !== null} onClick={extract}>{busy === "extract" ? "Extracting…" : "Extract requirements"}</button>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} /> Add local-model suggestions (verified against the text)
            </label>
          </div>
        </section>
      )}
      <InlineError error={err} />
    </div>
  );
}

// ---------------------------------------------------------------- tab 2
function RequirementsTab({ oid, onChanged }: { oid: string; onChanged: () => void }) {
  const q = useApi((s) => hoiApi.requirements(oid, s), [oid]);
  const skills = useApi((s) => hoiApi.skills(s), []);
  const data = useStale(q);
  if (q.status === "loading" && !data) return <Loading label="Loading requirements" />;
  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  if (!data?.current) return <EmptyState title="No requirements yet">Upload a document and run extraction.</EmptyState>;
  return <Editor key={data.current.version_id + data.current.status} oid={oid} data={data} skillList={skills.status === "success" ? skills.data.skills : []} reload={() => { q.reload(); onChanged(); }} />;
}

function Editor({ oid, data, skillList, reload }: { oid: string; data: HoiRequirements; skillList: { skill_id: string; name: string }[]; reload: () => void }) {
  const cur = data.current!;
  const { has } = useRoles();
  const editable = cur.status === "draft" && has("sales", "manager");
  const [roles, setRoles] = useState<HoiRole[]>(cur.roles ?? []);
  const [dirty, setDirty] = useState(false);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const { push, host } = useToasts();
  const patchRole = (i: number, p: Partial<HoiRole>) => { setRoles((r) => r.map((x, j) => (j === i ? { ...x, ...p } : x))); setDirty(true); };
  const patchSkill = (i: number, k: number, p: Record<string, unknown>) => { setRoles((r) => r.map((x, j) => (j === i ? { ...x, skills: x.skills.map((s, m) => (m === k ? { ...s, ...p } as typeof s : s)) } : x))); setDirty(true); };
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setErr(null);
    try { await fn(); push(ok, "ok"); setDirty(false); reload(); } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const save = () => run(() => hoiApi.saveRequirements(oid, cur.version_id, roles), "Draft saved");
  const approve = () => run(async () => { if (dirty) await hoiApi.saveRequirements(oid, cur.version_id, roles); await hoiApi.approveRequirements(oid, cur.version_id); }, "Requirements approved and locked");
  const problems = dirty ? [] : cur.blocking_problems ?? [];
  return (
    <div style={{ display: "grid", gap: 16 }}>
      {host}
      <section className="kpis" aria-label="Requirement version">
        <Kpi label="Version" value={`v${cur.version_no}`} note={<Chip tone={cur.status}>{cur.status}</Chip>} />
        <Kpi label="Method" value={pretty(cur.extraction_method)} note={cur.parser_version} />
        <Kpi label="Approved by" value={cur.approved_by ?? "—"} note={cur.content_hash ? `hash ${cur.content_hash.slice(0, 10)}…` : "not approved"} />
      </section>
      <div className="notice warn" role="note">
        Every value below is a draft suggestion with its source quote and a heuristic confidence (rule-based, not calibrated). Anything the document did
        not state is left blank. Set missing levels yourself, map or dismiss unmapped skills, then approve.
      </div>
      {cur.notes.length > 0 && <div className="muted">Notes: {cur.notes.join(" · ")}</div>}
      {roles.map((r, i) => (
        <section className="panel" key={r.requirement_id ?? i} aria-label={`Role ${r.role_name}`}>
          <div className="panel-head"><h2>{r.role_name || "New role"}</h2><Chip>{r.origin ?? "extracted"}</Chip></div>
          <div className="panel-body" style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
            <Field label="Role"><input className="input" disabled={!editable} value={r.role_name} onChange={(e) => patchRole(i, { role_name: e.target.value })} /></Field>
            <Field label="Headcount"><input className="input" aria-label="Headcount" type="number" min={1} disabled={!editable} value={r.headcount ?? ""} placeholder="unknown" onChange={(e) => patchRole(i, { headcount: e.target.value ? Number(e.target.value) : null })} /></Field>
            <Field label="FTE per head (0–1)"><input className="input" aria-label="FTE" disabled={!editable} value={r.fte ?? ""} placeholder="unknown" onChange={(e) => patchRole(i, { fte: e.target.value || null })} /></Field>
            <Field label="Location"><input className="input" disabled={!editable} value={r.location ?? ""} placeholder="unknown" onChange={(e) => patchRole(i, { location: e.target.value || null })} /></Field>
            <Field label="Mandatory certifications (comma separated)">
              <input className="input" disabled={!editable} value={((r.constraints.mandatory_certifications as string[] | undefined) ?? []).join(", ")}
                onChange={(e) => patchRole(i, { constraints: { ...r.constraints, mandatory_certifications: e.target.value.split(",").map((x) => x.trim()).filter(Boolean) } })} />
            </Field>
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" disabled={!editable} checked={Boolean(r.constraints.location_mandatory)} onChange={(e) => patchRole(i, { constraints: { ...r.constraints, location_mandatory: e.target.checked } })} /> Location is mandatory
            </label>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Skill (as written)</th><th>Hermes taxonomy</th><th>Level</th><th>Must / preferred</th><th>Source &amp; confidence</th><th></th></tr></thead>
              <tbody>
                {r.skills.map((s, k) => (
                  <tr key={k} style={s.dismissed ? { opacity: 0.5 } : undefined}>
                    <td>{s.text}</td>
                    <td>
                      <select className="select" aria-label={`Taxonomy for ${s.text}`} disabled={!editable} value={s.skill_id ?? ""} onChange={(e) => patchSkill(i, k, { skill_id: e.target.value || null, taxonomy_status: e.target.value ? "mapped" : "unmapped" })}>
                        <option value="">Unmapped — choose…</option>
                        {skillList.map((x) => <option key={x.skill_id} value={x.skill_id}>{x.name}</option>)}
                      </select>
                    </td>
                    <td>
                      <select className="select" style={{ minWidth: 96 }} aria-label={`Level for ${s.text}`} disabled={!editable} value={s.level ?? ""} onChange={(e) => patchSkill(i, k, { level: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">Unknown</option>
                        {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
                      </select>
                    </td>
                    <td>
                      <select className="select" disabled={!editable} value={s.criticality} onChange={(e) => patchSkill(i, k, { criticality: e.target.value })}>
                        <option value="must">Must-have</option><option value="preferred">Preferred</option>
                      </select>
                    </td>
                    <td>
                      {s.source ? <span title={`doc ${s.source.document_id} [${s.source.start}:${s.source.end}]`}>“{s.source.quote}”</span> : <em className="muted">added by a person</em>}
                      {s.confidence != null && <span className="muted"> · {Math.round(s.confidence * 100)}%</span>}
                    </td>
                    <td>
                      {editable && <button className="btn btn-sm btn-ghost" onClick={() => patchSkill(i, k, { dismissed: !s.dismissed })}>{s.dismissed ? "Restore" : "Dismiss"}</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
      {problems.length > 0 && (
        <div className="inline-error" role="alert">
          <strong>Before you can approve:</strong>
          <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
            {problems.map((c) => <li key={c}>{describeProblem(c, roles)}</li>)}
          </ul>
        </div>
      )}
      <InlineError error={err} />
      {editable && (
        <p className="muted" style={{ margin: "0 0 12px" }}>
          Demo limitation: there is no separate-reviewer rule yet. Any user with write access to this opportunity, including the person who
          extracted the document, can approve these requirements. The approver is recorded in the audit trail; independent review is not enforced.
        </p>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {editable && <button className="btn" disabled={busy || !dirty} onClick={save}>Save draft</button>}
        {editable && <button className="btn btn-primary" disabled={busy || problems.length > 0} onClick={approve}>Approve requirements</button>}
        {cur.status === "approved" && has("sales", "manager") && (
          <button className="btn" disabled={busy} onClick={() => run(() => hoiApi.reviseRequirements(oid), "New draft revision created")}>Create revision</button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- tab 3
function MatchesTab({ oid, onChanged }: { oid: string; onChanged: () => void }) {
  const q = useApi((s) => hoiApi.shortlist(oid, s), [oid]);
  const { has } = useRoles();
  const [fresh, setFresh] = useState<HoiShortlist | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [names, setNames] = useState<Record<string, ResolvedIdentity[]>>({});
  const stale = useStale(q);
  const data = fresh ?? stale;
  useEffect(() => setFresh(null), [oid]);
  const run = async () => {
    setBusy(true); setErr(null);
    try { setFresh(await hoiApi.match(oid)); onChanged(); } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  const reveal = async (reqId: string, staffingId: string) => {
    setErr(null);
    try { setNames((n) => ({ ...n, [reqId]: [] })); const r = await requestsApi.resolve(staffingId); setNames((n) => ({ ...n, [reqId]: r.resolved })); } catch (e) { setErr(e as Error); }
  };
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <div className="notice" role="note">
        Fitness is the existing Hermes score (evidence, confidence, recency). Eligibility is a separate pass/fail check. Pay is never an input here, and nobody
        is assigned. Names appear only through the audited reveal.
      </div>
      {has("manager") && <div><button className="btn btn-primary" disabled={busy} onClick={run}>{busy ? "Matching…" : "Run internal match on approved requirements"}</button></div>}
      <InlineError error={err} />
      {q.status === "loading" && !data && <Loading label="Loading shortlist" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data && !data.requirements.length && <EmptyState title="No match run yet">{has("manager") ? "Approve the requirements, then run the match." : "A delivery manager runs the match once requirements are approved."}</EmptyState>}
      {data?.requirements.map((r) => (
        <section className="panel table-wrap" key={r.requirement_id} aria-label={`Matches for ${r.role_name}`}>
          <div className="panel-head">
            <h2>{r.role_name} <span className="muted">×{r.headcount} @ {r.fte} FTE</span></h2>
            <Chip>{r.eligible_count} eligible of {r.candidate_count}</Chip>
          </div>
          {!r.candidates ? (
            <div className="panel-body muted">Coded candidates are visible to the delivery manager only.</div>
          ) : (
            <>
              <table className="data">
                <thead><tr><th>Rank</th><th>Coded identity</th><th>Fitness</th><th>Eligibility</th><th>Capacity</th><th>Checks</th><th>Why</th></tr></thead>
                <tbody>
                  {r.candidates.map((c) => (
                    <tr key={c.coded_identity}>
                      <td>{c.rank}</td>
                      <td className="mono">{c.coded_identity}{names[r.requirement_id]?.find((n) => n.coded_identity === c.coded_identity) && <strong> · {names[r.requirement_id].find((n) => n.coded_identity === c.coded_identity)!.display_name}</strong>}</td>
                      <td>{c.fitness_score.toFixed(3)}</td>
                      <td><Chip tone={c.eligibility}>{c.eligibility}</Chip></td>
                      <td>{c.available_fte == null ? "unknown" : `${c.available_fte.toFixed(2)} FTE`}</td>
                      <td>{c.checks.length ? c.checks.map((k) => <div key={k.check}><Chip tone={k.status}>{k.status}</Chip> {pretty(k.check)} — {k.detail}</div>) : <span className="muted">none required</span>}</td>
                      <td>
                        <details><summary>Evidence</summary>
                          {Object.entries(c.explanation).map(([k, v]) => <div key={k}><b>{k}</b>: {v}</div>)}
                          <div className="mono muted">{c.evidence_ids.slice(0, 6).join(", ")}</div>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {r.staffing_request_id && (
                <div className="panel-body"><button className="btn btn-sm" onClick={() => reveal(r.requirement_id, r.staffing_request_id!)}>Reveal names (audited, rate-limited)</button></div>
              )}
            </>
          )}
        </section>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- tab 4
function SummaryTab({ oid, readiness }: { oid: string; readiness: { documents: number; requirements_status: string; has_approved_requirements: boolean; scenarios: number; approved_scenarios: number } }) {
  const reqs = useApi((s) => hoiApi.requirements(oid, s), [oid]);
  const roles = reqs.status === "success" ? reqs.data.current?.roles ?? [] : [];
  const positions = roles.reduce((n, r) => n + (r.headcount ?? 0), 0);
  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="kpis" aria-label="Opportunity readiness">
        <Kpi label="Documents" value={readiness.documents} />
        <Kpi label="Requirements" value={pretty(readiness.requirements_status)} note={readiness.has_approved_requirements ? "an approved version exists" : "not approved"} />
        <Kpi label="Positions (current version)" value={positions || "—"} />
        <Kpi label="Scenarios" value={readiness.scenarios} note={`${readiness.approved_scenarios} approved`} />
      </section>
      <section className="panel"><div className="panel-body" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn" to="/market">Market analysis →</Link>
        <Link className="btn" to="/commercial">Commercial simulator →</Link>
        <Link className="btn btn-primary" to="/scenarios">Compare staffing scenarios →</Link>
      </div></section>
    </div>
  );
}

/**
 * The API reports approval blockers as stable codes ("role[2]:skill_unmapped:Quantum Compliance Mesh"). Say the same
 * thing in words, naming the role, so a reviewer knows what to change. Unknown codes are shown as-is rather than guessed.
 */
export function describeProblem(code: string, roles: HoiRole[]): string {
  if (code === "no_roles") return "Add at least one role.";
  const m = /^role\[(\d+)\]:([a-z_]+)(?::(.*))?$/.exec(code);
  if (!m) return pretty(code);
  const role = roles[Number(m[1]) - 1];
  const who = role?.role_name?.trim() || `Role ${m[1]}`;
  const arg = m[3] ?? "";
  switch (m[2]) {
    case "role_name_missing": return `Role ${m[1]}: enter a role name.`;
    case "headcount_unknown": return `${who}: set the headcount (a whole number, 1 or more).`;
    case "fte_unknown": return `${who}: set FTE per head (more than 0, up to 1).`;
    case "no_must_have_skill": return `${who}: mark at least one skill as must-have.`;
    case "skill_unmapped": return `${who}: map "${arg}" to a Hermes skill, or dismiss it.`;
    case "skill_level_unknown": {
      const sk = role?.skills.find((x) => x.skill_id === arg);
      return `${who}: set the required level for ${sk?.text || pretty(arg)}; the document did not state it.`;
    }
    default: return `${who}: ${pretty(m[2])}`;
  }
}
