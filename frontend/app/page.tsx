import { History } from "@/components/History.tsx";
import { NewAnalysis } from "@/components/NewAnalysis.tsx";
import { Shell } from "@/components/Shell.tsx";

export default function Home() {
  return (
    <Shell>
      <div className="stack">
        <NewAnalysis />
        <History />
      </div>
    </Shell>
  );
}
