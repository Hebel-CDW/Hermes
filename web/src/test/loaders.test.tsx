import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BootSplash, Spinner, StepLoader, Thinking } from "../ui/Loader";
import { Loading } from "../ui/States";
import { contract, EMPLOYEE_SESSION, mockApi, renderApp } from "./harness";

describe("loading screens", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("boot splash is an accessible status with the brand and a message", () => {
    render(<BootSplash message="Restoring your session" />);
    const s = screen.getByRole("status", { name: "Restoring session" });
    expect(s.textContent).toContain("HERMES");
    expect(s.textContent).toContain("Restoring your session");
  });

  it("step loader advances through its steps and keeps the last one", () => {
    render(<StepLoader title="Finding people" steps={["one", "two", "three"]} every={1000} />);
    const items = () => screen.getAllByRole("listitem").map((li) => li.className);
    expect(items()).toEqual(["now", "", ""]);
    act(() => void vi.advanceTimersByTime(1000));
    expect(items()).toEqual(["done", "now", ""]);
    act(() => void vi.advanceTimersByTime(5000));
    expect(items()).toEqual(["done", "done", "now"]);
  });

  it("thinking indicator cycles steps and explains a slow first answer", () => {
    render(<Thinking steps={["Reading your data…", "Writing it in plain English…"]} />);
    expect(screen.getByText("Reading your data…")).toBeTruthy();
    act(() => void vi.advanceTimersByTime(3000));
    expect(screen.getByText("Writing it in plain English…")).toBeTruthy();
    expect(screen.queryByText(/first answer after a restart/)).toBeNull();
    act(() => void vi.advanceTimersByTime(6000));
    expect(screen.getByText(/first answer after a restart/)).toBeTruthy();
  });

  it("page loading shows a spinner and a visible label while data loads", () => {
    render(<Loading label="Loading team skills" />);
    expect(screen.getByRole("status", { name: "Loading team skills" }).textContent).toContain("Loading team skills…");
    render(<Spinner />);
  });
});

describe("copilot thinking state", () => {
  it("shows progress steps while waiting for the answer, then the answer", async () => {
    mockApi({
      "GET /api/session": { body: EMPLOYEE_SESSION },
      "GET /api/me": { body: contract.me_employee },
      "GET /api/skills": { body: contract.skills },
      "GET /api/roles": { body: contract.roles },
      "GET /api/copilot/status": { body: { online: true, model: "m" } },
      "POST /api/copilot/ask": { body: { source: "model", answer: "Here is the answer.", model: "m" }, delay: 400 },
    });
    renderApp("/profile");
    fireEvent.click(await screen.findByRole("button", { name: "Ask Hermes" }));
    fireEvent.change(screen.getByLabelText("Ask Hermes a question"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByRole("status", { name: "Hermes is thinking" })).toBeTruthy();
    expect(await screen.findByText("Here is the answer.")).toBeTruthy();
  });
});
