import { apiFetch } from "./http";
import type {
  BulkItem,
  CertEntry,
  ChangeRequest,
  CustomRoleBody,
  DecideBody,
  Goal,
  Inbox,
  MyWorkflow,
  SubmitBody,
  TeamGrid,
  TimelineEvent,
  Dashboard,
  DataQuality,
  DecisionBody,
  ExcelSunset,
  FitnessResult,
  GapResult,
  IdentityDirectory,
  MeResult,
  Overview,
  RankBody,
  RequestDetail,
  RequestSummary,
  ResolvedIdentity,
  RoleProfile,
  SkillDetail,
  SkillReview,
  SkillSummaryRow,
  SurveyMatrix,
  TaxonomyPending,
  Workforce,
  HoiAudit,
  HoiBenchmark,
  HoiDocument,
  HoiMarketAnalysis,
  HoiOpportunity,
  HoiParam,
  HoiRequirements,
  HoiRole,
  HoiScenario,
  HoiShortlist,
  HoiStatus,
} from "./types";

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });
const enc = encodeURIComponent;

export const overviewApi = {
  get: (s?: AbortSignal) => apiFetch<Overview>("/api/overview", {}, s),
};

export const dataQualityApi = {
  get: (s?: AbortSignal) => apiFetch<DataQuality>("/api/data-quality", {}, s),
};

export const workforceApi = {
  get: (s?: AbortSignal) => apiFetch<Workforce>("/api/workforce", {}, s),
  directReports: (s?: AbortSignal) => apiFetch<{ identities: string[] }>("/api/identities", {}, s),
};

export const skillsApi = {
  list: (s?: AbortSignal) => apiFetch<{ skills: SkillSummaryRow[] }>("/api/skills", {}, s),
  get: (id: string, s?: AbortSignal) => apiFetch<SkillDetail>(`/api/skills/${enc(id)}`, {}, s),
  roles: (s?: AbortSignal) => apiFetch<{ roles: RoleProfile[] }>("/api/roles", {}, s),
};

export const matrixApi = {
  dashboard: (s?: AbortSignal) => apiFetch<Dashboard>("/api/dashboard", {}, s),
  runs: (s?: AbortSignal) => apiFetch<{ runs: string[] }>("/api/matrix/runs", {}, s),
  survey: (s?: AbortSignal) => apiFetch<SurveyMatrix>("/api/baseline/matrix", {}, s),
};

export const taxonomyApi = {
  pending: (s?: AbortSignal) => apiFetch<TaxonomyPending>("/api/taxonomy/pending", {}, s),
  resolve: (alias: string, body: { decision: "approve" | "reject"; skill_id?: string }) =>
    apiFetch<{ alias_label: string; mapped_by: string; skill_id: string }>(
      `/api/taxonomy/aliases/${enc(alias)}/resolve`,
      json(body),
    ),
};

export const excelSunsetApi = {
  get: (s?: AbortSignal) => apiFetch<ExcelSunset>("/api/excel-sunset", {}, s),
};

export const requestsApi = {
  list: (s?: AbortSignal) => apiFetch<{ requests: RequestSummary[] }>("/api/staffing/requests", {}, s),
  get: (id: string, s?: AbortSignal) => apiFetch<RequestDetail>(`/api/staffing/requests/${enc(id)}`, {}, s),
  rank: (body: RankBody) => apiFetch<FitnessResult>("/api/fitness/rank", json(body)),
  decide: (id: string, body: DecisionBody) =>
    apiFetch<Record<string, unknown>>(`/api/staffing/${enc(id)}/decision`, json(body)),
  resolve: (id: string, s?: AbortSignal) =>
    apiFetch<{ resolved: ResolvedIdentity[] }>("/api/identity/resolve", json({ request_id: id }), s),
};

export const learningApi = {
  gaps: (codedIdentity: string, role: { role_id: string; role_name: string; required_skills: Record<string, number> }) =>
    apiFetch<GapResult>("/api/fitness/gaps", json({ coded_identity: codedIdentity, ...role })),
};

export const directoryApi = {
  get: (s?: AbortSignal) => apiFetch<IdentityDirectory>("/api/identity/directory", {}, s),
};

export const profileApi = {
  me: (s?: AbortSignal) => apiFetch<MeResult>("/api/me", {}, s),
  contest: (reason: string, skill_id?: string) =>
    apiFetch<{ contest_id: string; status: string }>("/api/me/contest", json({ reason, skill_id })),
};

export const teamApi = {
  skillReview: (coded: string, s?: AbortSignal) =>
    apiFetch<SkillReview>(`/api/team/skill-review/${enc(coded)}`, {}, s),
  declare: (body: { coded_identity: string; skill_id: string; proficiency: number; note?: string }) =>
    apiFetch<{ status: string; coded_identity: string; skill_id: string; evidence_id: string }>("/api/team/declare", json(body)),
  resolveContest: (id: string, status: "confirmed" | "dismissed") =>
    apiFetch<{ contest_id: string; status: string }>(`/api/team/contests/${enc(id)}/resolve`, json({ status })),
};

export type CopilotAnswer = { source: "model" | "offline"; answer: string; model: string | null };

export const copilotApi = {
  status: (s?: AbortSignal) => apiFetch<{ online: boolean; model: string | null }>("/api/copilot/status", {}, s),
  ask: (question: string, requestId?: string, s?: AbortSignal) =>
    apiFetch<CopilotAnswer>("/api/copilot/ask", { ...json({ question, request_id: requestId ?? null }), signal: s }),
};

/** Employee self-service: proposals wait for a manager and count for nothing until approved. */
export const workflowApi = {
  mine: (s?: AbortSignal) => apiFetch<MyWorkflow>("/api/me/workflow", {}, s),
  submit: (body: SubmitBody) => apiFetch<ChangeRequest>("/api/me/requests", json(body)),
  withdraw: (id: string) => apiFetch<ChangeRequest>(`/api/me/requests/${enc(id)}/withdraw`, { method: "POST" }),
  setGoal: (role_id: string) => apiFetch<Goal>("/api/me/goal", { method: "PUT", body: JSON.stringify({ role_id }) }),
  clearGoal: () => apiFetch<{ status: string }>("/api/me/goal", { method: "DELETE" }),
  timeline: (s?: AbortSignal) => apiFetch<{ events: TimelineEvent[] }>("/api/me/timeline", {}, s),
  certCatalog: (s?: AbortSignal) => apiFetch<{ certificates: CertEntry[] }>("/api/cert-catalog", {}, s),
};

/** Manager side: approvals inbox, team grid, bulk update, what-if preview and custom roles. */
export const managerToolsApi = {
  inbox: (s?: AbortSignal) => apiFetch<Inbox>("/api/team/inbox", {}, s),
  decide: (id: string, body: DecideBody) => apiFetch<ChangeRequest>(`/api/team/inbox/${enc(id)}/decide`, json(body)),
  grid: (s?: AbortSignal) => apiFetch<TeamGrid>("/api/team/grid", {}, s),
  bulk: (items: BulkItem[]) => apiFetch<{ saved: number }>("/api/team/bulk-declare", json({ items })),
  preview: (body: RankBody, s?: AbortSignal) => apiFetch<FitnessResult>("/api/fitness/preview", { ...json(body), signal: s }),
  createRole: (body: CustomRoleBody) => apiFetch<RoleProfile>("/api/roles/custom", json(body)),
  deleteRole: (id: string) => apiFetch<{ status: string }>(`/api/roles/custom/${enc(id)}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------- Opportunity Intelligence
const put = (body: unknown): RequestInit => ({ method: "PUT", body: JSON.stringify(body) });
const opp = (id: string) => `/api/opportunities/${enc(id)}`;

export const hoiApi = {
  status: (s?: AbortSignal) => apiFetch<HoiStatus>("/api/hoi/status", {}, s),
  skills: (s?: AbortSignal) => apiFetch<{ skills: { skill_id: string; name: string }[] }>("/api/hoi/skills", {}, s),
  list: (s?: AbortSignal) => apiFetch<{ opportunities: HoiOpportunity[] }>("/api/opportunities", {}, s),
  create: (body: Record<string, unknown>) => apiFetch<HoiOpportunity>("/api/opportunities", json(body)),
  get: (id: string, s?: AbortSignal) => apiFetch<HoiOpportunity>(opp(id), {}, s),
  documents: (id: string, s?: AbortSignal) => apiFetch<{ documents: HoiDocument[] }>(`${opp(id)}/documents`, {}, s),
  upload: (id: string, body: { doc_type: string; filename: string; content_b64: string }) =>
    apiFetch<HoiDocument>(`${opp(id)}/documents`, json(body)),
  extract: (id: string, use_llm: boolean) => apiFetch<HoiRequirements>(`${opp(id)}/extract`, json({ use_llm })),
  requirements: (id: string, s?: AbortSignal) => apiFetch<HoiRequirements>(`${opp(id)}/requirements`, {}, s),
  saveRequirements: (id: string, versionId: string, roles: HoiRole[]) =>
    apiFetch<HoiRequirements>(`${opp(id)}/requirements/${enc(versionId)}`, put({ roles })),
  approveRequirements: (id: string, versionId: string) =>
    apiFetch<HoiRequirements>(`${opp(id)}/requirements/approve`, json({ version_id: versionId })),
  reviseRequirements: (id: string) => apiFetch<HoiRequirements>(`${opp(id)}/requirements/revise`, { method: "POST" }),
  match: (id: string) => apiFetch<HoiShortlist>(`${opp(id)}/internal-match`, json({})),
  shortlist: (id: string, s?: AbortSignal) => apiFetch<HoiShortlist>(`${opp(id)}/shortlist`, {}, s),
  marketAnalysis: (id: string) => apiFetch<HoiMarketAnalysis>(`${opp(id)}/market-analysis`, { method: "POST" }),
  scenarios: (id: string, s?: AbortSignal) => apiFetch<{ scenarios: HoiScenario[] }>(`${opp(id)}/scenarios`, {}, s),
  compare: (id: string, body: Record<string, unknown>) =>
    apiFetch<{ scenarios: HoiScenario[]; notes: string[] }>(`${opp(id)}/scenarios/compare`, json(body)),
  createScenario: (id: string, body: Record<string, unknown>) => apiFetch<HoiScenario>(`${opp(id)}/scenarios`, json(body)),
  approve: (id: string, body: Record<string, unknown>) => apiFetch<HoiScenario>(`${opp(id)}/approvals`, json(body)),
  exportReport: (id: string, scenario_id: string, format: "json" | "markdown") =>
    apiFetch<{ format: string; report?: unknown; content?: string }>(`${opp(id)}/export`, json({ scenario_id, format })),
  audit: (id: string, s?: AbortSignal) => apiFetch<HoiAudit>(`${opp(id)}/audit`, {}, s),
  benchmarks: (q: { role?: string; geography?: string; basis?: string }, s?: AbortSignal) => {
    const sp = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v && sp.set(k, v));
    return apiFetch<{ benchmarks: HoiBenchmark[]; note: string; synthetic_rows: number }>(`/api/market/benchmarks?${sp}`, {}, s);
  },
  importBenchmarks: (csv_text: string, declare_synthetic: boolean) =>
    apiFetch<{ import_batch: string; rows: number; synthetic_rows: number }>("/api/market/benchmarks/import", json({ csv_text, declare_synthetic })),
  policies: (s?: AbortSignal) => apiFetch<{ policies: HoiParam[] }>("/api/finance/cost-policies", {}, s),
  rateCards: (s?: AbortSignal) => apiFetch<{ rate_cards: HoiParam[] }>("/api/rate-cards", {}, s),
  putPolicy: (name: string, payload: Record<string, unknown>) =>
    apiFetch<{ version: number }>(`/api/finance/cost-policies/${enc(name)}`, put({ payload })),
  putRateCard: (name: string, payload: Record<string, unknown>) =>
    apiFetch<{ version: number }>(`/api/finance/rate-cards/${enc(name)}`, put({ payload })),
  addCosts: (rows: Record<string, unknown>[]) => apiFetch<{ rows_added: number }>("/api/finance/loaded-costs", json({ rows })),
  financeSummary: (s?: AbortSignal) =>
    apiFetch<{ loaded_cost_rows: Record<string, number>; policies: number; rate_cards: number }>("/api/finance/summary", {}, s),
  accessLog: (s?: AbortSignal) =>
    apiFetch<{ events: { access_id: string; actor: string; action: string; context: string; created_at: string }[] }>("/api/finance/access-log", {}, s),
};
