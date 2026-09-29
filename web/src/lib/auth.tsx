import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { fetchSession, signIn, signOut } from "../api/auth";
import { getToken, UNAUTHORIZED_EVENT } from "../api/http";
import type { Role, Session } from "../api/types";

type AuthState = {
  /** undefined = still checking the stored token; null = signed out. */
  session: Session | null | undefined;
  login: (sub: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

/**
 * Roles and coded identity come only from GET /api/session (server-derived).
 * Nothing about the principal is persisted client-side except the opaque token.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(getToken() ? undefined : null);

  useEffect(() => {
    if (!getToken()) return;
    const controller = new AbortController();
    fetchSession(controller.signal).then(setSession, (e: Error) => {
      if (e.name === "AbortError") return;
      signOut();
      setSession(null);
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const onUnauthorized = () => {
      signOut();
      setSession(null);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const login = useCallback(async (sub: string) => {
    setSession(await signIn(sub));
  }, []);
  const logout = useCallback(() => {
    signOut();
    setSession(null);
  }, []);

  return <AuthContext.Provider value={{ session, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export const hasRole = (session: Session | null | undefined, ...roles: Role[]) =>
  !!session && session.roles.some((r) => roles.includes(r));
