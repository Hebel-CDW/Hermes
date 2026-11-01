import { createContext, ReactNode, useContext, useEffect, useMemo, useState } from "react";
import { directoryApi } from "../api/endpoints";
import type { DirectoryPerson } from "../api/types";
import { useAuth } from "./auth";

type NameCtx = {
  people: DirectoryPerson[];
  label: (coded: string) => string;
};

const NameContext = createContext<NameCtx>({ people: [], label: (coded) => coded });

/**
 * Synthetic-only overlay. Loads GET /api/identity/directory after session.
 * Failures (403 real-data, unmocked tests) fall back to coded tokens — never surface as alerts.
 */
export function NameProvider({ children }: { children: ReactNode }) {
  const { session } = useAuth();
  const [people, setPeople] = useState<DirectoryPerson[]>([]);

  useEffect(() => {
    // Deal-team-only roles never see names (the server refuses the directory); do not even ask.
    if (!session || session.data_classification !== "synthetic" || session.roles.every((r) => r === "sales" || r === "finance" || r === "hr")) {
      setPeople([]);
      return;
    }
    const ctrl = new AbortController();
    directoryApi.get(ctrl.signal).then(
      (d) => {
        if (!ctrl.signal.aborted) setPeople(d.people);
      },
      (e: Error) => {
        if (e.name !== "AbortError") setPeople([]);
      },
    );
    return () => ctrl.abort();
  }, [session?.sub, session?.data_classification]);

  const value = useMemo<NameCtx>(() => {
    const map = Object.fromEntries(people.map((p) => [p.coded_identity, p.display_name]));
    return { people, label: (coded) => map[coded] ?? coded };
  }, [people]);

  return <NameContext.Provider value={value}>{children}</NameContext.Provider>;
}

export function useNames(): NameCtx {
  return useContext(NameContext);
}

/** Resolved shortlist names win; otherwise the synthetic directory overlay. */
export function displayName(coded: string, label: (c: string) => string, resolved?: Record<string, string> | null): string | null {
  if (resolved?.[coded]) return resolved[coded];
  const overlay = label(coded);
  return overlay !== coded ? overlay : null;
}

export function PersonName({
  coded,
  resolved,
  nameTestId,
}: {
  coded: string;
  resolved?: Record<string, string> | null;
  nameTestId?: string;
}) {
  const { label } = useNames();
  const name = displayName(coded, label, resolved);
  if (!name) {
    return (
      <span className="mono" data-testid={nameTestId}>
        {coded}
      </span>
    );
  }
  return (
    <span className="person-label">
      <span data-testid={nameTestId}>{name}</span>
      <span className="person-token">{coded}</span>
    </span>
  );
}
