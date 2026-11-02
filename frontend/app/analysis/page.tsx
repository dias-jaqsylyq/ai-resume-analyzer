import { Suspense } from "react";
import { AnalysisView } from "@/components/AnalysisView.tsx";
import { Shell } from "@/components/Shell.tsx";

// Static export has no dynamic routes at runtime, so the id travels as ?id=<analysis id>.
export default function AnalysisPage() {
  return (
    <Shell>
      <Suspense fallback={<p className="muted">Loading…</p>}>
        <AnalysisView />
      </Suspense>
    </Shell>
  );
}
