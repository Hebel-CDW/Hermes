import type { ComponentType, SVGProps } from "react";
import type { Role } from "./api/types";
import {
  IconCapability,
  IconDataQuality,
  IconInsights,
  IconLearning,
  IconMatrix,
  IconOverview,
  IconProfile,
  IconRequests,
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
  group: "Start here" | "Explore" | "System";
  /** Primary demo nav. Hidden items stay routed and searchable. */
  primary?: boolean;
};

export const NAV: NavItem[] = [
  // "Start here" mirrors the demo path; everything analytical sits under "Explore".
  { path: "/overview", label: "Overview", icon: IconOverview, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/capability", label: "Find people", icon: IconCapability, roles: ["manager"], group: "Start here", primary: true },
  { path: "/matrix", label: "Team skills", icon: IconMatrix, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/learning", label: "Learning", icon: IconLearning, roles: ["employee", "manager", "admin"], group: "Start here", primary: true },
  { path: "/update-skills", label: "Update skills", icon: IconSkillUpdate, roles: ["manager", "admin"], group: "Start here", primary: true },
  { path: "/requests", label: "Requests", icon: IconRequests, roles: ["manager"], group: "Start here", primary: true },
  { path: "/workforce", label: "Workforce", icon: IconWorkforce, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/skills", label: "Skills", icon: IconSkills, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/insights", label: "Insights", icon: IconInsights, roles: ["manager", "admin"], group: "Explore", primary: true },
  { path: "/data-quality", label: "Data Quality", icon: IconDataQuality, roles: ["manager", "admin"], group: "Explore" },
  { path: "/profile", label: "Profile", icon: IconProfile, roles: ["employee", "manager", "admin"], group: "System" },
];

export const homeFor = (roles: Role[]): string =>
  roles.includes("manager") || roles.includes("admin") ? "/overview" : "/profile";
