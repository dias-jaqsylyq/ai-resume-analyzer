"use client";

import { useState, type FormEvent } from "react";
import { useApp } from "./AppProvider.tsx";

type Mode = "signin" | "signup" | "confirm";

export function SignIn() {
  const { auth, refresh } = useApp();
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      if (mode === "signup") {
        await auth.signUp(email, password);
        setMode("confirm");
        setInfo("We sent a confirmation code to your email.");
      } else if (mode === "confirm") {
        await auth.confirm(email, code);
        await auth.signIn(email, password);
        await refresh();
      } else {
        await auth.signIn(email, password);
        await refresh();
      }
    } catch (err) {
      const e2 = err as Error & { code?: string };
      if (e2.code === "UserNotConfirmedException") setMode("confirm");
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  const title = { signin: "Sign in", signup: "Create an account", confirm: "Confirm your email" }[mode];

  return (
    <section className="card auth">
      <h1>{title}</h1>
      <p className="muted">Score your CV against a job description and get concrete edits.</p>
      <form onSubmit={submit} className="stack">
        <label>
          Email
          <input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        {mode !== "confirm" || !password ? (
          <label>
            Password
            <input
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              required
              minLength={mode === "signup" ? 12 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
        ) : null}
        {mode === "signup" && <p className="small muted">At least 12 characters, with upper case, lower case and a number.</p>}
        {mode === "confirm" && (
          <label>
            Confirmation code
            <input inputMode="numeric" autoComplete="one-time-code" required value={code} onChange={(e) => setCode(e.target.value)} />
          </label>
        )}
        {info && <p className="note">{info}</p>}
        {error && <p className="alert" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Please wait…" : title}
        </button>
      </form>
      <p className="small center">
        {mode === "signin" ? (
          <button type="button" className="link" onClick={() => { setMode("signup"); setError(null); }}>
            No account yet? Create one
          </button>
        ) : (
          <button type="button" className="link" onClick={() => { setMode("signin"); setError(null); setInfo(null); }}>
            Back to sign in
          </button>
        )}
      </p>
    </section>
  );
}
