import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { skillsApi } from "../api/endpoints";
import { useAuth } from "./auth";
import { humanSkill } from "./format";

const SkillContext = createContext<(id: string) => string>((id) => humanSkill(id));

/** Loads GET /api/skills names. Failures fall back to a readable skill id. */
export function SkillProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [map, setMap] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!session) {
      setMap({});
      return;
    }
    const ctrl = new AbortController();
    skillsApi.list(ctrl.signal).then(
      (d) => {
        if (!ctrl.signal.aborted) setMap(Object.fromEntries(d.skills.map((s) => [s.skill_id, s.name])));
      },
      (e: Error) => {
        if (e.name !== "AbortError") setMap({});
      },
    );
    return () => ctrl.abort();
  }, [session?.sub]);

  const label = useMemo(() => (id: string) => humanSkill(id, map), [map]);
  return <SkillContext.Provider value={label}>{children}</SkillContext.Provider>;
}

export function useSkillName(): (id: string) => string {
  return useContext(SkillContext);
}
