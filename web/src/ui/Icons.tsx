import type { SVGProps } from "react";

/** 1.5px stroke icons (DESIGN.md: outlined, no fills). */
type P = SVGProps<SVGSVGElement>;
const base = (p: P) => ({
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  ...p,
});

export const IconOverview = (p: P) => (
  <svg {...base(p)}><rect x="3.5" y="3.5" width="7" height="9" rx="1" /><rect x="13.5" y="3.5" width="7" height="5" rx="1" /><rect x="13.5" y="11.5" width="7" height="9" rx="1" /><rect x="3.5" y="15.5" width="7" height="5" rx="1" /></svg>
);
export const IconWorkforce = (p: P) => (
  <svg {...base(p)}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.5 3.3-5.5 6.5-5.5s5.7 2 6.5 5.5" /><path d="M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.8c1.6.8 2.6 2.6 3 5.2" /></svg>
);
export const IconSkills = (p: P) => (
  <svg {...base(p)}><path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12l1-8Z" /></svg>
);
export const IconMatrix = (p: P) => (
  <svg {...base(p)}><rect x="3.5" y="3.5" width="17" height="17" rx="1" /><path d="M3.5 9.2h17M3.5 14.8h17M9.2 3.5v17M14.8 3.5v17" /></svg>
);
export const IconSkillUpdate = (p: P) => (
  <svg {...base(p)}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" /></svg>
);
export const IconRequests = (p: P) => (
  <svg {...base(p)}><rect x="4" y="3.5" width="16" height="17" rx="1.5" /><path d="M8 3.5v3h8v-3M8 11h8M8 15h5" /></svg>
);
export const IconCapability = (p: P) => (
  <svg {...base(p)}><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 5.5 5.5" /></svg>
);
export const IconLearning = (p: P) => (
  <svg {...base(p)}><path d="M12 6.5C10 5 7 4.5 3.5 5v13.5c3.5-.5 6.5 0 8.5 1.5 2-1.5 5-2 8.5-1.5V5C17 4.5 14 5 12 6.5Zm0 0V20" /></svg>
);
export const IconInsights = (p: P) => (
  <svg {...base(p)}><path d="M5 20V11M10 20V5M15 20v-7M20 20V8" /></svg>
);
export const IconDataQuality = (p: P) => (
  <svg {...base(p)}><path d="M4 6.5c0-1.4 3.6-2.5 8-2.5s8 1.1 8 2.5-3.6 2.5-8 2.5-8-1.1-8-2.5Z" /><path d="M4 6.5v11c0 1.4 3.6 2.5 8 2.5 1 0 2-.1 2.9-.2M20 6.5V12M4 12c0 1.4 3.6 2.5 8 2.5" /><path d="m15.5 17.5 1.8 1.8 3.2-3.8" /></svg>
);
export const IconProfile = (p: P) => (
  <svg {...base(p)}><circle cx="12" cy="8" r="4" /><path d="M4.5 20.5c1-4 3.8-6 7.5-6s6.5 2 7.5 6" /></svg>
);
export const IconSearch = (p: P) => (
  <svg {...base(p)}><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></svg>
);
export const IconBell = (p: P) => (
  <svg {...base(p)}><path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15l1.5-2ZM10 20.5a2 2 0 0 0 4 0" /></svg>
);
export const IconMenu = (p: P) => (
  <svg {...base(p)}><path d="M4 7h16M4 12h16M4 17h16" /></svg>
);
export const IconArrowLeft = (p: P) => (
  <svg {...base(p)}><path d="M19 12H5M11 6l-6 6 6 6" /></svg>
);
export const IconArrowRight = (p: P) => (
  <svg {...base(p)}><path d="M5 12h14M13 6l6 6-6 6" /></svg>
);
export const IconLock = (p: P) => (
  <svg {...base(p)}><rect x="5" y="10.5" width="14" height="10" rx="1.5" /><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" /></svg>
);
export const IconSignOut = (p: P) => (
  <svg {...base(p)}><path d="M14 4.5H6.5a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1H14M10 12h10.5M17 8.5l3.5 3.5-3.5 3.5" /></svg>
);
export const IconPlus = (p: P) => (
  <svg {...base(p)}><path d="M12 5v14M5 12h14" /></svg>
);
export const IconClose = (p: P) => (
  <svg {...base(p)}><path d="M6 6l12 12M18 6 6 18" /></svg>
);

/** Hermes mark (hermes_design/hermes_logo_mark): ink uprights, crimson crossbar with a node. */
export function LogoMark({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-label="Hermes" role="img">
      <rect x="0.5" y="0.5" width="39" height="39" rx="8" fill="#fff" stroke="#E5E7EB" />
      <path d="M13 11v18M27 11v18" stroke="#0F172A" strokeWidth="3" strokeLinecap="round" />
      <path d="M13 20h14" stroke="#B5122B" strokeWidth="3" strokeLinecap="round" />
      <circle cx="20" cy="20" r="1.6" fill="#fff" />
    </svg>
  );
}

export const IconInbox = (p: P) => (
  <svg {...base(p)}><path d="M3.5 13.5 6 5.5h12l2.5 8" /><path d="M3.5 13.5v5h17v-5h-5.2a3.3 3.3 0 0 1-6.6 0H3.5Z" /></svg>
);
export const IconGrid = (p: P) => (
  <svg {...base(p)}><rect x="3.5" y="4.5" width="17" height="15" rx="1" /><path d="M3.5 9.5h17M9 4.5v15M14.5 4.5v15" /><path d="m16.2 15.2 1.1 1.1 2-2.4" /></svg>
);
export const IconGrowth = (p: P) => (
  <svg {...base(p)}><path d="M4 19.5h16" /><path d="M6 16l4-4.5 3 2.5 5-6.5" /><path d="M14.5 7.5H18V11" /></svg>
);
export const IconLab = (p: P) => (
  <svg {...base(p)}><path d="M9.5 3.5h5M10.5 3.5v5.2L5.2 17.6a2 2 0 0 0 1.7 3h10.2a2 2 0 0 0 1.7-3l-5.3-8.9V3.5" /><path d="M7.8 14.5h8.4" /></svg>
);
