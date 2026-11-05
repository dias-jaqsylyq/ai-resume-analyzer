import { progressSteps, type Status } from "@/lib/report.ts";
import { CheckIcon } from "./Icons.tsx";

/** Horizontal stepper that makes the async pipeline visible: upload, processing, report. */
export function Steps({ status }: { status: Status }) {
  return (
    <ol className="steps" aria-label="Progress">
      {progressSteps(status).map((step, i) => (
        <li key={step.label} className={`step step-${step.state}`} aria-current={step.state === "active" ? "step" : undefined}>
          <span className="step-dot">{step.state === "done" ? <CheckIcon size={14} /> : i + 1}</span>
          <span className="step-label">{step.label}</span>
        </li>
      ))}
    </ol>
  );
}
