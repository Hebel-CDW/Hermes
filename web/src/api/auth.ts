import { apiFetch, setToken } from "./http";
import type { Session } from "./types";

/**
 * Synthetic demo principals known to the local issuer (src/shared/demo_identities.py).
 * Only the id is sent; roles and coded identity are derived by the server.
 */
export const DEMO_PRINCIPALS: { sub: string; label: string }[] = [
  { sub: "demo-manager", label: "Delivery manager" },
  { sub: "demo-manager-2", label: "Second manager" },
  { sub: "demo-employee", label: "Employee" },
  { sub: "demo-employee-2", label: "Second employee" },
  { sub: "demo-admin", label: "Administrator" },
];

function clearDemoGuide(): void {
  try {
    sessionStorage.removeItem("hermes.guide.seen");
    sessionStorage.removeItem("hermes.last.request");
  } catch {
    /* ignore */
  }
}

export async function signIn(sub: string): Promise<Session> {
  setToken(null);
  clearDemoGuide();
  const { access_token } = await apiFetch<{ access_token: string }>("/api/auth/token", {
    method: "POST",
    body: JSON.stringify({ sub }),
  });
  setToken(access_token);
  return fetchSession();
}

export const fetchSession = (signal?: AbortSignal) => apiFetch<Session>("/api/session", {}, signal);

export function signOut(): void {
  setToken(null);
  clearDemoGuide();
}
