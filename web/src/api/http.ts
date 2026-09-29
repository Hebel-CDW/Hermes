import type { ApiErrorBody } from "./types";

const TOKEN_KEY = "hermes.token";

/** Fired when the server rejects the stored token; the auth provider signs the user out. */
export const UNAUTHORIZED_EVENT = "hermes:unauthorized";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string | undefined,
    public readonly serverDetail: string,
  ) {
    super(humanMessage(status, code, serverDetail));
  }
}

/** Governance codes returned by the API, translated for people. Unknown codes fall back to the server text. */
const CODE_MESSAGES: Record<string, string> = {
  request_not_owned: "This request belongs to another manager. Only its owner can view or act on it.",
  request_state_conflict: "A decision has already been recorded for this request.",
  request_not_found: "That staffing request does not exist.",
  candidate_not_shortlisted: "Candidate is not in the shortlist.",
  candidate_excluded: "This candidate was excluded by the engine and cannot be chosen.",
  candidate_required: "Choose a shortlisted candidate for this decision.",
  no_shortlist: "This request has no shortlisted candidates to decide on.",
  unknown_skill: "One or more skills are not in the governed ontology.",
  not_a_direct_report: "You can only update skills for yourself and your direct reports.",
  rate_limited: "Too many updates. Wait a minute and try again.",
  forged_claims: "Your session token is not valid. Sign in again.",
  unknown_principal: "That demo principal is not recognised.",
  workbook_frozen: "A Skill Matrix after 2025 cannot be ingested. Use Hermes evidence instead.",
  missing_trust_metadata: "The server refused to open an untrusted database.",
  untrusted_database: "The server refused to open an untrusted database.",
};

export function humanMessage(status: number, code: string | undefined, detail: string): string {
  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code];
  switch (status) {
    case 401:
      return "Your session has expired or is invalid. Sign in again.";
    case 403:
      return "You're not authorized to view or perform this action.";
    case 404:
      return "Not found.";
    case 409:
      return "This action conflicts with the current state of the request.";
    case 422:
      return detail ? `Invalid input: ${detail}` : "Invalid input.";
    case 429:
      return "Too many identity resolutions. Wait a minute and try again.";
    case 503:
      return "The service is unavailable: the database was not trusted by the server.";
    default:
      return status >= 500 ? "The server encountered an error." : "The request could not be completed.";
  }
}

function detailText(body: ApiErrorBody): string {
  const d = body.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const first = d[0] as { msg?: string };
    return (first.msg ?? "").replace(/^Value error, /, "");
  }
  return "";
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

/** The single HTTP entry point. Only the bearer token is attached; no role or identity state. */
export async function apiFetch<T>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, signal, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as ApiErrorBody;
    if (res.status === 401 && token) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    throw new ApiError(res.status, body.error, detailText(body));
  }
  return (await res.json()) as T;
}
