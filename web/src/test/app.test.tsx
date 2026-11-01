import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { contract, EMPLOYEE_SESSION, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const navLabels = () =>
  within(screen.getByRole("complementary", { name: "Primary" }))
    .getAllByRole("link")
    .map((a) => a.textContent);

describe("routing and auth", () => {
  it("redirects signed-out users to the demo login", async () => {
    mockApi({});
    renderApp("/requests", { signedIn: false });
    expect(await screen.findByText("Sign in")).toBeTruthy();
  });

  it("login sends only the principal id; roles come from /api/session", async () => {
    const calls = mockApi({
      "POST /api/auth/token": { body: { access_token: "t", token_type: "bearer" } },
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/overview": { body: contract.overview },
      "GET /api/data-quality": { body: contract.data_quality },
    });
    renderApp("/login", { signedIn: false });
    expect(await screen.findByRole("button", { name: /Continue as a manager/ })).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: /demo-manager$/ }));
    expect(await screen.findByRole("heading", { name: "Overview" })).toBeTruthy();
    expect(calls.find((c) => c.path === "/api/auth/token")?.body).toEqual({ sub: "demo-manager" });
    expect(localStorage.length).toBe(0);
    expect(Object.keys(sessionStorage)).toEqual(["hermes.token"]);
  });

  it("shows the full navigation to a manager", async () => {
    mockApi({ "GET /api/session": { body: MANAGER_SESSION }, "GET /api/overview": { body: contract.overview }, "GET /api/data-quality": { body: contract.data_quality } });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Overview" }));
    expect(navLabels()).toEqual([
      "Overview",
      "Find people",
      "Team skills",
      "Learning",
      "Update skills",
      "Requests",
      "Approvals",
      "Workforce",
      "Skills",
      "Insights",
      "Bulk update",
      "Role lab",
    ]);
    expect(screen.queryByTestId("welcome-guide")).toBeNull();
  });

  it("limits an employee to learning and profile and guards manager routes", async () => {
    mockApi({ "GET /api/session": { body: EMPLOYEE_SESSION } });
    renderApp("/overview");
    expect(await screen.findByText("Not available for your role")).toBeTruthy();
    expect(navLabels()).toEqual(["My skills", "My growth", "Learning"]);
    expect(screen.queryByTestId("welcome-guide")).toBeNull();
  });

  it("drops an invalid stored session back to login", async () => {
    mockApi({ "GET /api/session": { status: 401, body: { detail: "bad token", error: "unauthenticated" } } });
    renderApp("/overview");
    expect(await screen.findByText("Sign in")).toBeTruthy();
    expect(sessionStorage.getItem("hermes.token")).toBeNull();
  });

  it("renders a not-found page for unknown routes", async () => {
    mockApi({ "GET /api/session": { body: MANAGER_SESSION } });
    renderApp("/does-not-exist");
    expect(await screen.findByText("Page not found")).toBeTruthy();
  });

  it.each([
    ["/overview", "Overview"],
    ["/workforce", "Workforce"],
    ["/skills", "Skills atlas"],
    ["/matrix", "Team skills"],
    ["/update-skills", "Update skills"],
    ["/requests", "Requests"],
    ["/capability", "Find people"],
    ["/learning", "Learning"],
    ["/insights", "Insights"],
    ["/data-quality", "Data quality"],
    ["/profile", "My skills"],
  ])("route %s renders its page with contract data", async (path, heading) => {
    mockApi({
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/overview": { body: contract.overview },
      "GET /api/workforce": { body: contract.workforce },
      "GET /api/skills": { body: contract.skills },
      "GET /api/skills/container_orchestration": { body: contract.skill_detail },
      "GET /api/roles": { body: contract.roles },
      "GET /api/dashboard": { body: contract.dashboard },
      "GET /api/matrix/runs": { body: { runs: [contract.overview.latest_computation_run_id] } },
      "GET /api/staffing/requests": { body: contract.requests },
      "GET /api/identities": { body: { identities: [] } },
      "GET /api/me": { body: contract.me_employee },
      "GET /api/data-quality": { body: contract.data_quality },
      "GET /api/identity/directory": { body: { people: [] } },
      [`GET /api/team/skill-review/${MANAGER_SESSION.coded_identity}`]: {
        body: { coded_identity: MANAGER_SESSION.coded_identity, matrix: [], contests: [] },
      },
    });
    renderApp(path);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("status", { name: /Loading/ })).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a first-run welcome that starts the Find people path", async () => {
    mockApi({
      "POST /api/auth/token": { body: { access_token: "t", token_type: "bearer" } },
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/overview": { body: contract.overview },
      "GET /api/data-quality": { body: contract.data_quality },
      "GET /api/skills": { body: contract.skills },
      "GET /api/roles": { body: contract.roles },
    });
    renderApp("/login", { signedIn: false });
    fireEvent.click(await screen.findByRole("button", { name: /demo-manager$/ }));
    expect(await screen.findByTestId("welcome-guide")).toBeTruthy();
    expect(Object.keys(sessionStorage)).toEqual(["hermes.token"]);
    fireEvent.click(screen.getByRole("button", { name: "Start looking" }));
    expect(sessionStorage.getItem("hermes.guide.seen")).toBe("1");
    expect(await screen.findByRole("heading", { level: 1, name: "Find people" })).toBeTruthy();
    expect(screen.queryByTestId("welcome-guide")).toBeNull();
  });

  it("shows welcome again after sign-out and a fresh manager login", async () => {
    mockApi({
      "POST /api/auth/token": { body: { access_token: "t", token_type: "bearer" } },
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/overview": { body: contract.overview },
      "GET /api/data-quality": { body: contract.data_quality },
    });
    renderApp("/login", { signedIn: false });
    fireEvent.click(await screen.findByRole("button", { name: /demo-manager$/ }));
    await screen.findByTestId("welcome-guide");
    fireEvent.click(screen.getByRole("button", { name: "Skip for now" }));
    expect(screen.queryByTestId("welcome-guide")).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: "Account" }));
    fireEvent.click(await screen.findByRole("button", { name: /Sign out/ }));
    fireEvent.click(await screen.findByRole("button", { name: /demo-manager$/ }));
    expect(await screen.findByTestId("welcome-guide")).toBeTruthy();
  });
});
