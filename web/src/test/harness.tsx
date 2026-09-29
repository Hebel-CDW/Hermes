import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App";
import { AuthProvider } from "../lib/auth";
import contract from "./fixtures/api-contract.json";

export { contract };

export type Call = { method: string; path: string; body: unknown; headers: Record<string, string> };
type Reply = { status?: number; body: unknown; delay?: number };
type Handler = Reply | ((call: Call) => Reply);

/**
 * Stubs window.fetch with a route table keyed by "METHOD /path" (query string ignored unless
 * the key includes it). Unmatched requests fail the test loudly with a 599.
 */
export function mockApi(routes: Record<string, Handler>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = new URL(String(input), "http://hermes.test");
    const method = (init.method ?? "GET").toUpperCase();
    const call: Call = {
      method,
      path: url.pathname + url.search,
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers ?? {}) as Record<string, string>,
    };
    calls.push(call);
    const handler = routes[`${method} ${url.pathname}${url.search}`] ?? routes[`${method} ${url.pathname}`];
    if (!handler) return new Response(JSON.stringify({ detail: `unmocked ${method} ${call.path}` }), { status: 599 });
    const reply = typeof handler === "function" ? handler(call) : handler;
    if (reply.delay) {
      await new Promise<void>((resolve, reject) => {
        const t = setTimeout(resolve, reply.delay);
        init.signal?.addEventListener("abort", () => {
          clearTimeout(t);
          reject(new DOMException("aborted", "AbortError"));
        });
      });
    }
    return new Response(JSON.stringify(reply.body), { status: reply.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export const MANAGER_SESSION = contract.session_manager;
export const EMPLOYEE_SESSION = contract.session_employee;

/** Synthetic vault overlay used by GET /api/identity/directory in UI tests. */
export const DIRECTORY = {
  people: [
    { coded_identity: "EMP-fd8efec3", display_name: "Alex Rivera" },
    { coded_identity: "EMP-c775791c", display_name: "Jordan Lee" },
    { coded_identity: "EMP-f232ab6e", display_name: "Sam Patel" },
    { coded_identity: "EMP-666c8943", display_name: "Casey Nguyen" },
    { coded_identity: "EMP-9a4bf2f6", display_name: "Riley Brooks" },
  ],
};

/** Renders the real App at `path` with a stored token; the session itself comes from the mocked /api/session. */
export function renderApp(path: string, { signedIn = true, guide = false }: { signedIn?: boolean; guide?: boolean } = {}) {
  if (signedIn) sessionStorage.setItem("hermes.token", "opaque.test.token");
  if (signedIn && !guide) sessionStorage.setItem("hermes.guide.seen", "1");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const fixed4 = (v: number) => v.toFixed(4);
