// Report contract (docs/02-architecture.md) and the API response shapes from read-analyses.

export type Status = "PENDING" | "PROCESSING" | "DONE" | "FAILED";
export type Priority = "high" | "medium" | "low";

export type Suggestion = { priority: Priority; section: string; advice: string };

export type Report = {
  ats_score: number;
  score_rationale: string;
  matched_skills: string[];
  missing_skills: string[];
  suggestions: Suggestion[];
  summary: string;
};

export type AnalysisSummary = {
  analysis_id: string;
  status: Status;
  created_at: string | null;
  updated_at: string | null;
  job_title: string | null;
  ats_score?: number;
  error?: string | null;
};

export type AnalysisDetail = Omit<AnalysisSummary, "ats_score"> & {
  job_description: string | null;
  report: Report | null;
  model_id?: string | null;
};

export type HistoryPage = { items: AnalysisSummary[]; next_cursor: string | null };

export function isTerminal(status: Status): boolean {
  return status === "DONE" || status === "FAILED";
}

export const STATUS_LABEL: Record<Status, string> = {
  PENDING: "Waiting for upload",
  PROCESSING: "Analyzing",
  DONE: "Ready",
  FAILED: "Failed",
};

export type ScoreBand = "strong" | "fair" | "weak";

export function scoreBand(score: number): ScoreBand {
  if (score >= 75) return "strong";
  if (score >= 50) return "fair";
  return "weak";
}

const PRIORITY_ORDER: Record<Priority, number> = { high: 0, medium: 1, low: 2 };

/** High priority first; stable inside one priority so the model's order is kept. */
export function sortSuggestions(items: Suggestion[]): Suggestion[] {
  return items
    .map((s, i) => ({ s, i }))
    .sort((a, b) => PRIORITY_ORDER[a.s.priority] - PRIORITY_ORDER[b.s.priority] || a.i - b.i)
    .map(({ s }) => s);
}

/** Share of the job's skills found in the CV, 0..100 (null when the report lists none). */
export function skillsCoverage(report: Pick<Report, "matched_skills" | "missing_skills">): number | null {
  const total = report.matched_skills.length + report.missing_skills.length;
  return total === 0 ? null : Math.round((report.matched_skills.length / total) * 100);
}

/** Readable message for the error code stored on a FAILED analysis (exception class name). */
export function failureMessage(code: string | null | undefined): string {
  switch (code) {
    case "InvalidUpload":
      return "The upload was rejected (it must be a PDF of at most 5 MB).";
    case "TextractJobFailed":
    case "ExtractionTimeout":
      return "No text could be read from the PDF. Is it a scanned image or password protected?";
    case "AnalysisBlocked":
      return "The analysis was blocked by the safety filter.";
    case "InvalidReport":
      return "The model returned an invalid report. Please try again.";
    default:
      return "The analysis failed. Please try again.";
  }
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export type StepState = "done" | "active" | "todo" | "failed";
export type ProgressStep = { label: string; state: StepState };

/** The three stages the dashboard shows while the pipeline runs, derived from the status alone. */
export function progressSteps(status: Status): ProgressStep[] {
  const labels = ["CV uploaded", "Reading and scoring", "Report ready"];
  const states: Record<Status, StepState[]> = {
    PENDING: ["active", "todo", "todo"],
    PROCESSING: ["done", "active", "todo"],
    DONE: ["done", "done", "done"],
    FAILED: ["done", "failed", "todo"],
  };
  return labels.map((label, i) => ({ label, state: states[status][i] }));
}
