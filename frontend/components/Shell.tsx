"use client";

import type { ReactNode } from "react";
import { AppProvider } from "./AppProvider.tsx";
import { Footer } from "./Footer.tsx";
import { Header } from "./Header.tsx";
import { Landing } from "./Landing.tsx";

export function Shell({ children }: { children: ReactNode }) {
  return (
    <AppProvider
      signedOut={
        <>
          <Header wide />
          <main className="container container-wide">
            <Landing />
          </main>
          <Footer wide />
        </>
      }
    >
      <Header />
      <main className="container">{children}</main>
      <Footer />
    </AppProvider>
  );
}
