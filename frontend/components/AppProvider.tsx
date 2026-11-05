"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiClient } from "@/lib/api.ts";
import { Auth } from "@/lib/auth.ts";
import { loadConfig } from "@/lib/config.ts";

type App = {
  auth: Auth;
  api: ApiClient;
  email: string | null;
  refresh: () => Promise<void>;
  signOut: () => void;
};

const AppContext = createContext<App | null>(null);

export function useApp(): App {
  const app = useContext(AppContext);
  if (!app) throw new Error("useApp outside AppProvider");
  return app;
}

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; auth: Auth; api: ApiClient; email: string | null };

/** Loads /config.json, then shows `signedOut` or `children` depending on the Cognito session. */
export function AppProvider({ children, signedOut }: { children: ReactNode; signedOut: ReactNode }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const init = useCallback(async () => {
    try {
      const config = await loadConfig();
      const auth = new Auth(config);
      const api = new ApiClient(config.apiUrl, () => auth.accessToken());
      const session = await auth.session();
      setState({ kind: "ready", auth, api, email: session ? auth.currentEmail() : null });
    } catch {
      setState({ kind: "error", message: "The app is not configured yet (config.json is missing or invalid)." });
    }
  }, []);

  useEffect(() => {
    void init();
  }, [init]);

  const app = useMemo<App | null>(() => {
    if (state.kind !== "ready") return null;
    return {
      auth: state.auth,
      api: state.api,
      email: state.email,
      refresh: async () => {
        const session = await state.auth.session();
        setState({ ...state, email: session ? state.auth.currentEmail() : null });
      },
      signOut: () => {
        state.auth.signOut();
        setState({ ...state, email: null });
      },
    };
  }, [state]);

  if (state.kind === "loading")
    return (
      <div className="page-status" aria-busy="true">
        <div className="spinner" aria-hidden="true" />
        <p className="muted">Loading…</p>
      </div>
    );
  if (state.kind === "error")
    return (
      <div className="page-status">
        <p className="alert">{state.message}</p>
      </div>
    );
  return <AppContext.Provider value={app}>{app?.email ? children : signedOut}</AppContext.Provider>;
}
