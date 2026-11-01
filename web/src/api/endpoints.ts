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
