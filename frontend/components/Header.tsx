"use client";

import Link from "next/link";
import { useApp } from "./AppProvider.tsx";
import { BrandMark } from "./Icons.tsx";

export function Header({ wide = false }: { wide?: boolean }) {
  const { email, signOut } = useApp();
  return (
    <header className="header">
      <div className={wide ? "header-inner wide" : "header-inner"}>
        <Link href="/" className="brand">
          <BrandMark />
          FitScore
        </Link>
        {email && (
          <div className="header-user">
            <span className="muted small">{email}</span>
            <button type="button" className="btn btn-ghost" onClick={signOut}>
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
