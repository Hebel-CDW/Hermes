import { describe, expect, it } from "vitest";
import { describeProblem } from "../views/hoi/Rfp";

const role = (name: string, skills: Array<{ skill_id: string; text: string }> = []) =>
  ({ role_name: name, skills } as unknown as Parameters<typeof describeProblem>[1][number]);

describe("describeProblem (approval blockers in plain language)", () => {
  const roles = [role("Senior Cloud Engineer"), role("Platform SRE Lead", [{ skill_id: "container_orchestration", text: "Container Orchestration" }])];

  it("names the role and what to do for an unmapped skill", () => {
    expect(describeProblem("role[2]:skill_unmapped:Quantum Compliance Mesh", roles)).toBe(
      'Platform SRE Lead: map "Quantum Compliance Mesh" to a Hermes skill, or dismiss it.');
  });
  it("uses the skill's written name when a level is missing", () => {
    expect(describeProblem("role[2]:skill_level_unknown:container_orchestration", roles)).toContain("Container Orchestration");
  });
  it("covers the other blockers and never shows raw codes", () => {
    for (const c of ["role[1]:headcount_unknown", "role[1]:fte_unknown", "role[1]:no_must_have_skill", "role[1]:role_name_missing", "no_roles"]) {
      const text = describeProblem(c, roles);
      expect(text).not.toMatch(/\[|_/);
    }
    expect(describeProblem("role[1]:headcount_unknown", roles)).toContain("Senior Cloud Engineer");
  });
  it("shows an unrecognised code as-is instead of guessing", () => {
    expect(describeProblem("something_new", roles)).toMatch(/something/i);
  });
});
