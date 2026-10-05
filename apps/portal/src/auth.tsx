import Keycloak from "keycloak-js";
import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Auth = {
  ready: boolean;
  authenticated: boolean;
  login: () => Promise<void>;
  logout: () => Promise<void>;
  /** Drop the local session without redirecting (used on 401 recovery). */
  clearSession: () => void;
  token: () => string | undefined;
};

const Context = createContext<Auth | undefined>(undefined);

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL ?? "http://127.0.0.1:8080",
  realm: import.meta.env.VITE_KEYCLOAK_REALM ?? "openclass-local",
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID ?? "openclass-portal",
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    keycloak
      .init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false })
      .then((ok) => {
        if (!cancelled) {
          setAuthenticated(ok);
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuthenticated(false);
          setReady(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const clearSession = useCallback(() => {
    queryClient.clear();
    setAuthenticated(false);
  }, [queryClient]);

  const value = useMemo<Auth>(
    () => ({
      ready,
      authenticated,
      login: async () => {
        await keycloak.login();
      },
      logout: async () => {
        clearSession();
        await keycloak.logout({ redirectUri: window.location.origin });
      },
      clearSession,
      token: () => keycloak.token,
    }),
    [ready, authenticated, clearSession],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useAuth(): Auth {
  const auth = useContext(Context);
  if (!auth) throw new Error("AuthProvider is required");
  return auth;
}
