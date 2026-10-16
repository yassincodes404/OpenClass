"use client";

import Keycloak from "keycloak-js";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ControlWorkspace } from "@openclass/sdk";
import {
  routeMockedSession,
  setWorkspaceSession,
  workspaceClient,
} from "../../lib/workspace-client";

export default function WorkspaceSession({ children }: { children: ReactNode }) {
  const client = useRef<Keycloak | null>(null);
  const initialization = useRef<Promise<boolean> | null>(null);
  // Single source of truth for the session token. Effect cleanups must not
  // clear it: React StrictMode replays effects, and child pages read the token
  // as soon as they mount. Only sign-out and expiry clear the session.
  const tokenRef = useRef<string | undefined>(undefined);
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [workspaces, setWorkspaces] = useState<ControlWorkspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const workspaceRef = useRef("");
  const [error, setError] = useState("");

  useEffect(() => {
    let disposed = false;
    const applySession = (token: string | undefined, selected?: string) => {
      tokenRef.current = token;
      setWorkspaceSession(token, selected);
    };
    async function establish(token: string | undefined) {
      applySession(token);
      setAuthenticated(Boolean(token));
      if (!token) {
        setReady(true);
        return;
      }
      try {
        const memberships = await workspaceClient.workspaces();
        if (disposed) return;
        setWorkspaces(memberships);
        // This is an actual authenticated membership, not a fabricated tenant.
        const selected = memberships.length === 1 ? memberships[0]!.id : "";
        if (selected) {
          setWorkspace(selected);
          applySession(tokenRef.current, selected);
        }
      } catch {
        if (!disposed) setError("Workspace memberships unavailable. Check the control plane.");
      } finally {
        if (!disposed) setReady(true);
      }
    }

    // Route-mocked browser checks only; see lib/workspace-client.ts.
    const mocked = routeMockedSession();
    if (mocked) {
      if (mocked.workspace) setWorkspace(mocked.workspace);
      void establish(mocked.token);
      return () => {
        disposed = true;
      };
    }

    const kc =
      client.current ??
      new Keycloak({
        url: process.env.NEXT_PUBLIC_KEYCLOAK_URL ?? "http://127.0.0.1:8080",
        realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM ?? "openclass-local",
        clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID ?? "openclass-portal",
      });
    client.current = kc;
    const expire = () => {
      applySession(undefined);
      if (!disposed) setAuthenticated(false);
    };
    kc.onAuthLogout = expire;
    kc.onAuthRefreshError = expire;
    const initial =
      initialization.current ??
      kc.init({ onLoad: "check-sso", pkceMethod: "S256", checkLoginIframe: false });
    initialization.current = initial;
    // Honest failure instead of an endless spinner when the identity provider
    // never answers; the user can still retry via the sign-in button.
    const bounded = Promise.race([
      initial,
      new Promise<boolean>((_, reject) =>
        window.setTimeout(() => reject(new Error("identity provider timeout")), 10_000),
      ),
    ]);
    void bounded
      .then((ok) => {
        if (!disposed) void establish(ok ? kc.token : undefined);
      })
      .catch(() => {
        if (disposed) return;
        setError("Secure workspace unavailable. Check your identity provider and control plane.");
        applySession(undefined);
        setAuthenticated(false);
        setReady(true);
      });
    const refresh = window.setInterval(() => {
      if (!kc.authenticated) return;
      void kc
        .updateToken(60)
        .then(() => {
          if (!disposed) applySession(kc.token, workspaceRef.current || undefined);
        })
        .catch(expire);
    }, 30_000);
    return () => {
      disposed = true;
      window.clearInterval(refresh);
    };
    // Authentication is initialized once. Workspace changes update the memory session below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    workspaceRef.current = workspace;
    if (authenticated) setWorkspaceSession(tokenRef.current, workspace || undefined);
  }, [workspace, authenticated]);

  if (!ready)
    return (
      <main>
        <p role="status">Checking secure session…</p>
      </main>
    );
  if (!authenticated)
    return (
      <main className="panel">
        <h1>Sign in to your workspace.</h1>
        <p>Projects are visible only to authorized workspace members.</p>
        {error && <p role="alert">{error}</p>}
        <button
          onClick={() => {
            void client.current
              ?.login()
              .catch(() =>
                setError("Sign-in unavailable. Try again after checking the identity provider."),
              );
          }}
        >
          Continue with Keycloak
        </button>
      </main>
    );
  return (
    <>
      <section className="panel" aria-label="Authenticated workspace">
        <label>
          Workspace for new projects
          <select value={workspace} onChange={(e) => setWorkspace(e.target.value)}>
            <option value="">Select a workspace</option>
            {workspaces.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.role}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => {
            tokenRef.current = undefined;
            setWorkspaceSession();
            setAuthenticated(false);
            void client.current
              ?.logout({ redirectUri: window.location.origin })
              .catch(() => setError("Signed out locally. Identity-provider sign-out unavailable."));
          }}
        >
          Sign out
        </button>
      </section>
      {children}
    </>
  );
}
