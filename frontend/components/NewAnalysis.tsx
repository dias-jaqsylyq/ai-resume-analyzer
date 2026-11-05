"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { MAX_JOB_DESCRIPTION_CHARS, validateCv, validateJob } from "@/lib/api.ts";
import { useApp } from "./AppProvider.tsx";

export function NewAnalysis() {
  const { api } = useApp();
  const router = useRouter();
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<"idle" | "creating" | "uploading">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem = validateJob(jobDescription, jobTitle) ?? (file ? validateCv(file) : "Choose your CV (PDF).");
    if (problem || !file) {
      setError(problem);
      return;
    }
    setError(null);
    try {
      setStep("creating");
      const created = await api.createAnalysis(jobDescription, jobTitle);
      setStep("uploading");
      await api.uploadCv(created.upload, file);
      router.push(`/analysis/?id=${encodeURIComponent(created.analysis_id)}`);
    } catch (err) {
      setError((err as Error).message || "Something went wrong.");
      setStep("idle");
    }
  }

  const busy = step !== "idle";
  return (
    <section className="card">
      <h2>New analysis</h2>
      <form onSubmit={submit} className="stack">
        <label>
          <span>
            Job title <span className="muted small">(optional)</span>
          </span>
          <input value={jobTitle} maxLength={200} onChange={(e) => setJobTitle(e.target.value)} placeholder="Cloud Engineer" />
        </label>
        <label>
          Job description
          <textarea
            required
            rows={8}
            value={jobDescription}
            onChange={(e) => setJobDescription(e.target.value)}
            placeholder="Paste the full job posting here"
          />
          <span className={`small ${jobDescription.length > MAX_JOB_DESCRIPTION_CHARS ? "danger" : "muted"}`}>
            {jobDescription.length.toLocaleString()} / {MAX_JOB_DESCRIPTION_CHARS.toLocaleString()}
          </span>
        </label>
        <label>
          CV (PDF, up to 5 MB)
          <input type="file" accept="application/pdf,.pdf" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {error && <p className="alert" role="alert">{error}</p>}
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {step === "creating" ? "Creating…" : step === "uploading" ? "Uploading CV…" : "Analyze my CV"}
        </button>
      </form>
    </section>
  );
}
