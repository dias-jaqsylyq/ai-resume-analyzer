"use client";

import Link from "next/link";
import { useApp } from "./AppProvider.tsx";

export function Header() {
  const { email, signOut } = useApp();
  return (
    <header className="header">
      <Link href="/" className="brand">
        AI Resume Analyzer
      </Link>
      {email && (
        <div className="header-user">
          <span className="muted small">{email}</span>
          <button type="button" className="btn btn-ghost" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}
