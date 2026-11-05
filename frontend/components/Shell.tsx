"use client";

import type { ReactNode } from "react";
import { AppProvider } from "./AppProvider.tsx";
import { Header } from "./Header.tsx";
import { SignIn } from "./SignIn.tsx";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <AppProvider
      signedOut={
        <>
          <Header />
          <main className="container auth-wrap">
            <SignIn />
          </main>
        </>
      }
    >
      <Header />
      <main className="container">{children}</main>
    </AppProvider>
  );
}
