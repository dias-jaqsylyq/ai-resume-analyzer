import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

const DESCRIPTION = "See how well your CV fits the job: an ATS score, matched and missing skills, and concrete edits.";

export const metadata: Metadata = {
  title: "FitScore · CV analyzer",
  description: DESCRIPTION,
  applicationName: "FitScore",
  openGraph: { title: "FitScore", description: DESCRIPTION, type: "website" },
  twitter: { card: "summary", title: "FitScore", description: DESCRIPTION },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f5f7" },
    { media: "(prefers-color-scheme: dark)", color: "#000000" },
  ],
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
