import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { contract, EMPLOYEE_SESSION, MANAGER_SESSION, mockApi, renderApp } from "./harness";

describe("copilot", () => {
  it("answers an employee from their own data and labels the source", async () => {
    const calls = mockApi({
      "GET /api/session": { body: EMPLOYEE_SESSION },
      "GET /api/me": { body: contract.me_employee },
      "GET /api/skills": { body: contract.skills },
      "GET /api/roles": { body: contract.roles },
      "GET /api/copilot/status": { body: { online: true, model: "qwen2.5:7b-instruct" } },
      "POST /api/copilot/ask": { body: { source: "model", answer: "You are closest to Senior Cloud Engineer.", model: "qwen2.5:7b-instruct" } },
    });
    renderApp("/profile");
    fireEvent.click(await screen.findByRole("button", { name: "Ask Hermes" }));
    expect(await screen.findByText(/AI model online/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Which role am I closest to/ }));
    expect(await screen.findByText("You are closest to Senior Cloud Engineer.")).toBeTruthy();
    expect(screen.getByText(/AI answer · qwen2.5:7b-instruct/)).toBeTruthy();
    const ask = calls.find((c) => c.path === "/api/copilot/ask");
    expect((ask?.body as { question: string }).question).toMatch(/closest/);
  });

  it("says plainly when the model is offline", async () => {
    mockApi({
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/overview": { body: contract.overview },
      "GET /api/copilot/status": { body: { online: false, model: null } },
      "POST /api/copilot/ask": { body: { source: "offline", answer: "The AI model is not reachable right now.", model: null } },
    });
    renderApp("/overview");
    fireEvent.click(await screen.findByRole("button", { name: "Ask Hermes" }));
    expect(await screen.findByText(/AI model offline/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Ask Hermes a question"), { target: { value: "Who should I pick?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/Fixed summary from your data \(model offline\), not an AI answer/)).toBeTruthy();
  });
});
