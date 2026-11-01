import { DependencyList, useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api/http";

export type ApiState<T> =
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "success"; data: T; error?: undefined }
  | { status: "error"; data?: undefined; error: ApiError | Error };

/**
 * Fetch with abort + generation guard: a response from an earlier dependency set can
 * never overwrite a later one (prevents candidate A's data showing under candidate B).
 */
export function useApi<T>(load: (signal: AbortSignal) => Promise<T>, deps: DependencyList) {
  const [state, setState] = useState<ApiState<T>>({ status: "loading" });
  const generation = useRef(0);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(load, deps);
  const reload = useCallback(() => {
    const gen = ++generation.current;
    const controller = new AbortController();
    setState({ status: "loading" });
    run(controller.signal).then(
      (data) => gen === generation.current && setState({ status: "success", data }),
      (error: Error) => {
        if (gen !== generation.current || error.name === "AbortError") return;
        setState({ status: "error", error });
      },
    );
    return () => controller.abort();
  }, [run]);
  useEffect(() => reload(), [reload]);
  return { ...state, reload } as ApiState<T> & { reload: () => void };
}

/**
 * The last successful data, kept on screen while a refresh is in flight. For views that reload after a
 * save: the page stays mounted (form state, scroll and open panels survive) instead of flashing empty.
 */
export function useStale<T>(state: ApiState<T>): T | undefined {
  const last = useRef<T | undefined>(undefined);
  if (state.status === "success") last.current = state.data;
  return state.status === "success" ? state.data : last.current;
}
