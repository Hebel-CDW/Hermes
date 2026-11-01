import type { ComponentType, SVGProps } from "react";
import type { Role } from "./api/types";
import {
  IconArchitecture,
  IconAudit,
  IconCapability,
  IconCommercial,
  IconDataQuality,
  IconGrid,
  IconGrowth,
  IconInbox,
  IconInsights,
  IconLab,
  IconLearning,
  IconMarket,
  IconMatrix,
  IconOverview,
  IconProfile,
  IconRequests,
  IconRfp,
  IconScenario,
  IconSkills,
  IconSkillUpdate,
  IconWorkforce,
} from "./ui/Icons";

export type NavItem = {
  path: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  /** Mirrors the API's role gate so navigation hides what the server would refuse. The server still enforces. */
  roles: Role[];
  group: "Start here" | "Explore" | "Opportunity Intelligence" | "System";
  /** Primary demo nav. Hidden items stay routed and searchable. */
  primary?: boolean;
};

export const NAV: NavItem[] = [
  // "Start here" mirrors the demo path; everything analytical sits under "Explore".
  { path: "/profile", label: "My skills", icon: IconProfile, roles: ["employee"], group: "Start here", primary: true },
  { path: "/growth", label: "My growth", icon: IconGrowth, roles: ["employee"], group: "Start here", primary: true },
  { path: "/overview", label: "Executive Overview", icon: IconOverview, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/capability", label: "Staffing & Fitment", icon: IconCapability, roles: ["manager"], group: "Start here", primary: true },
  { path: "/matrix", label: "Team skills", icon: IconMatrix, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/learning", label: "Learning & Gaps", icon: IconLearning, roles: ["employee", "manager", "admin"], group: "Start here", primary: true },
  { path: "/update-skills", label: "Update skills", icon: IconSkillUpdate, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/requests", label: "Requests", icon: IconRequests, roles: ["manager"], group: "Start here", primary: true },
  { path: "/inbox", label: "Approvals", icon: IconInbox, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/workforce", label: "Workforce", icon: IconWorkforce, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/skills", label: "Skills Intelligence", icon: IconSkills, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/insights", label: "Insights", icon: IconInsights, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/team-grid", label: "Bulk update", icon: IconGrid, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/role-lab", label: "Role lab", icon: IconLab, roles: ["manager"], group: "Explore", primary: true },
  { path: "/data-quality", label: "Data Quality", icon: IconDataQuality, roles: ["manager", "admin"], group: "Explore" },
  { path: "/rfp", label: "RFP/SOW Workspace", icon: IconRfp, roles: ["sales", "manager", "finance", "hr", "admin"], group: "Opportunity Intelligence", primary: true },
  { path: "/commercial", label: "Commercial Simulator", icon: IconCommercial, roles: ["manager", "finance", "hr", "admin"], group: "Opportunity Intelligence", primary: true },
  { path: "/market", label: "Market Intelligence", icon: IconMarket, roles: ["sales", "manager", "finance", "hr", "admin"], group: "Opportunity Intelligence", primary: true },
  { path: "/scenarios", label: "Scenario Optimizer", icon: IconScenario, roles: ["sales", "manager", "finance", "hr", "admin"], group: "Opportunity Intelligence", primary: true },
  { path: "/architecture", label: "Architecture & Workflow", icon: IconArchitecture, roles: ["employee", "manager", "admin", "sales", "finance", "hr"], group: "System", primary: true },
  { path: "/decisions", label: "Decisions & Audit", icon: IconAudit, roles: ["sales", "manager", "finance", "hr", "admin"], group: "System", primary: true },
  { path: "/profile", label: "Profile", icon: IconProfile, roles: ["employee", "manager", "admin"], group: "System" },
];

export const homeFor = (roles: Role[]): string =>
  roles.includes("manager") || roles.includes("admin")
    ? "/overview"
    : roles.some((r) => r === "sales" || r === "finance" || r === "hr")
      ? "/rfp"
      : "/profile";
