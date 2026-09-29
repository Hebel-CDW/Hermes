import type { ReactNode } from "react";
import { ApiError } from "../api/http";

export function Loading({ label = "Loading", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="grid" style={{ gap: 10 }}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: i === 0 ? 72 : 44 }} />
      ))}
    </div>
  );
}

const TITLES: Record<number, string> = {
  401: "Session required",
  403: "Not authorized",
  404: "Not found",
  409: "Conflict",
  422: "Invalid request",
  429: "Rate limit reached",
  503: "Service unavailable",
};

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  const status = error instanceof ApiError ? error.status : 0;
  const title = TITLES[status] ?? (status >= 500 ? "Server error" : "Could not load data");
  const message = error instanceof ApiError ? error.message : "The API could not be reached. Check that the Hermes server is running.";
  return (
    <div className="state error" role="alert">
      <h3>{title}</h3>
      <p>{message}</p>
      {error instanceof ApiError && (
        <span className="code">
          HTTP {error.status}
          {error.code ? ` · ${error.code}` : ""}
        </span>
      )}
      {onRetry && status !== 403 && status !== 404 && (
        <button className="btn btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state empty">
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function InlineError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div className="inline-error" role="alert">
      {error.message}
      {error instanceof ApiError && (
        <span className="mono" style={{ marginLeft: 8, opacity: 0.8 }}>
          ({error.status}
          {error.code ? ` ${error.code}` : ""})
        </span>
      )}
    </div>
  );
}
