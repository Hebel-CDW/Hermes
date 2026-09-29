import { useCallback, useEffect, useState } from "react";
import { requestsApi } from "../api/endpoints";
import type { ResolvedIdentity } from "../api/types";

export function mapResolvedNames(resolved: ResolvedIdentity[]): Record<string, string> {
  return Object.fromEntries(resolved.map((r) => [r.coded_identity, r.display_name]));
}

/** Shortlist names come only from POST /api/identity/resolve. Never persisted. */
export function useResolvedNames(requestId: string, opts: { enabled: boolean; auto: boolean }) {
  const [names, setNames] = useState<Record<string, string> | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const resolve = useCallback(
    async (signal?: AbortSignal) => {
      setPending(true);
      setError(null);
      try {
        const { resolved } = await requestsApi.resolve(requestId, signal);
        if (signal?.aborted) return;
        setNames(mapResolvedNames(resolved));
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setError(e as Error);
      } finally {
        if (!signal?.aborted) setPending(false);
      }
    },
    [requestId],
  );

  useEffect(() => {
    if (!opts.enabled || !opts.auto) return;
    const ctrl = new AbortController();
    void resolve(ctrl.signal);
    return () => ctrl.abort();
  }, [opts.enabled, opts.auto, resolve]);

  return { names, pending, error, resolve };
}
