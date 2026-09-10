const TOKEN_KEY = "hermes_jwt";

const headers = async (): Promise<HeadersInit> => {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const key = import.meta.env.VITE_HERMES_API_KEY as string | undefined;
  if (key) h["x-api-key"] = key;
  const token = await ensureAuth();
  h["Authorization"] = `Bearer ${token}`;
  return h;
};

export async function ensureAuth(opts?: {
  coded_identity?: string;
  force?: boolean;
  sub?: string;
  roles?: string[];
}): Promise<string> {
  const existing = sessionStorage.getItem(TOKEN_KEY);
  if (existing && !opts?.force && !opts?.coded_identity) {
    return existing;
  }
  const body = {
    sub: opts?.sub ?? "mgr-ui",
    roles: opts?.roles ?? ["manager", "admin"],
    ...(opts?.coded_identity ? { coded_identity: opts.coded_identity } : {}),
  };
  const res = await fetch("/api/auth/token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || err.error || `Auth failed (${res.status})`);
  }
  const data = (await res.json()) as { access_token: string };
  sessionStorage.setItem(TOKEN_KEY, data.access_token);
  return data.access_token;
}

export function clearAuth(): void {
  sessionStorage.removeItem(TOKEN_KEY);
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { ...(await headers()), ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export type Skill = {
  skill_id: string;
  name: string;
  description: string;
  domain_id: string;
  domain_name: string;
};

export type Role = {
  role_id: string;
  role_name: string;
  required_skills: Record<string, number>;
};

export type SkillReasoningDetail = {
  status?: string;
  level?: number;
  required?: number;
  confidence?: number;
  volume_score?: number;
  freshness?: number;
  adjacency_discount?: number;
  evidence_ids?: string[];
  [key: string]: unknown;
};

export type RankedCandidate = {
  coded_identity: string;
  fitness_score: number;
  rank: number;
  per_skill_reasoning: Record<string, string>;
  reasoning_detail: Record<string, SkillReasoningDetail | number | string | unknown>;
  evidence_ids: string[];
};

export type FitnessResult = {
  request_id: string;
  candidates: RankedCandidate[];
  scoring_config_version: string;
};

export type GapItem = {
  skill_id: string;
  required_level: number;
  current_level: number | null;
  demand_impact: number;
  reasoning: string;
  evidence_ids: string[];
};

export type GapResult = {
  coded_identity: string;
  role_id: string;
  gaps: GapItem[];
};

export type Resolved = {
  coded_identity: string;
  display_name: string;
  rank: string;
  fitness_score: string;
};

export type Dashboard = {
  coverage: { pilot_size: number; with_demonstrated: number; coverage_pct: number };
  avg_freshness_by_skill: Record<string, number>;
  skill_distribution: Array<{
    coded_identity: string;
    skill_id: string;
    proficiency: number;
    confidence: number;
    freshness: number;
  }>;
};

export type MatrixRunRecord = {
  coded_identity: string;
  skill_id: string;
  proficiency: number;
  confidence?: number;
  freshness: number;
  volume_score?: number;
  computation_run_id?: string;
  [key: string]: unknown;
};

export type DecisionStatus = "accepted" | "rejected" | "overridden";

export type DecisionBody = {
  status: DecisionStatus;
  chosen_coded_identity?: string;
  rejection_reason?: string;
  override_note?: string;
};

export type MeResult = {
  coded_identity: string;
  skills: Array<{
    skill_id: string;
    proficiency: number;
    confidence: number;
    freshness: number;
    volume_score?: number;
    evidence_ids?: string[];
  }>;
  evidence: Array<{
    evidence_id: string;
    skill_id: string;
    evidence_type: string;
    source_ref: string;
    occurred_at: string;
    payload: Record<string, unknown>;
  }>;
};

export const api = {
  skills: () => req<{ skills: Skill[] }>("/api/skills"),
  roles: () => req<{ roles: Role[] }>("/api/roles"),
  identities: () => req<{ identities: string[] }>("/api/identities"),
  dashboard: () => req<Dashboard>("/api/dashboard"),
  matrixRuns: () => req<{ runs: string[] }>("/api/matrix/runs"),
  matrixRun: (runId: string) =>
    req<{ computation_run_id: string; records: MatrixRunRecord[] }>(
      `/api/matrix/runs/${encodeURIComponent(runId)}`
    ),
  me: () => req<MeResult>("/api/me"),
  contest: (body: { reason: string; skill_id?: string }) =>
    req<{ contest_id: string; status: string }>("/api/me/contest", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rank: (body: {
    request_id: string;
    required_skills: Record<string, number>;
    shortlist_size?: number;
  }) =>
    req<FitnessResult>("/api/fitness/rank", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  gaps: (body: {
    coded_identity: string;
    role_id: string;
    role_name: string;
    required_skills: Record<string, number>;
  }) =>
    req<GapResult>("/api/fitness/gaps", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resolve: (body: { request_id: string }) =>
    req<{ resolved: Resolved[] }>("/api/identity/resolve", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  decision: (requestId: string, body: DecisionBody) =>
    req<Record<string, unknown>>(`/api/staffing/${encodeURIComponent(requestId)}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
