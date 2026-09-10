import type { ReactNode } from "react";
export function NarrateBanner({ children }: { children?: ReactNode }) {
  return (
    <div className="banner" role="note">
      {children ??
        "Rules decide. Rules compute. Hermes recommends only — manager approval is required before any staffing decision."}
    </div>
  );
}
