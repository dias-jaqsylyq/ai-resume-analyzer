"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { MAX_JOB_DESCRIPTION_CHARS, validateCv, validateJob } from "@/lib/api.ts";
import { SAMPLE_CV_NAME, SAMPLE_CV_PATH, SAMPLE_JOB_DESCRIPTION, SAMPLE_JOB_TITLE } from "@/lib/sample.ts";
import { useApp } from "./AppProvider.tsx";

export function NewAnalysis() {
  const { api } = useApp();
  const router = useRouter();
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [step, setStep] = useState<"idle" | "creating" | "uploading">("idle");
  const [error, setError] = useState<string | null>(null);
  const [loadingSample, setLoadingSample] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  /** Fills the form with a fictional CV and job posting, so a report is one click away. */
  async function loadSample() {
    setLoadingSample(true);
    setError(null);
    try {
      const res = await fetch(SAMPLE_CV_PATH);
      if (!res.ok) throw new Error("The sample CV could not be loaded.");
      const sample = new File([await res.blob()], SAMPLE_CV_NAME, { type: "application/pdf" });
      setJobTitle(SAMPLE_JOB_TITLE);
      setJobDescription(SAMPLE_JOB_DESCRIPTION);
      setFile(sample);
      try {
        // Show the file in the native picker too; older browsers keep the state only.
        const dt = new DataTransfer();
        dt.items.add(sample);
        if (fileInput.current) fileInput.current.files = dt.files;
      } catch {
        /* the form still submits the file from state */
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingSample(false);
    }
  }

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
    <section className="stack">
      <div className="page-head">
        <div className="page-title">
          <h1>New analysis</h1>
          <p className="muted">Paste a job posting and upload your CV. You get an ATS score, a skills match and concrete edits.</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => void loadSample()} disabled={busy || loadingSample}>
          {loadingSample ? "Loading…" : "Try with a sample"}
        </button>
      </div>
      <form onSubmit={submit} className="card stack">
        <label>
          <span>
            Job title <span className="optional">(optional)</span>
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
          <span className={`small field-hint ${jobDescription.length > MAX_JOB_DESCRIPTION_CHARS ? "danger" : "muted"}`}>
            {jobDescription.length.toLocaleString()} / {MAX_JOB_DESCRIPTION_CHARS.toLocaleString()}
          </span>
        </label>
        <label>
          <span>
            CV <span className="optional">(PDF, up to 5 MB)</span>
          </span>
          <input
            ref={fileInput}
            type="file"
            accept="application/pdf,.pdf"
            required={!file}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {file?.name === SAMPLE_CV_NAME && <span className="small muted">Using the sample CV of a fictional engineer.</span>}
        </label>
        {error && <p className="alert" role="alert">{error}</p>}
        <div className="row">
          <button type="submit" className="btn btn-primary btn-lg btn-submit" disabled={busy}>
            {step === "creating" ? "Creating…" : step === "uploading" ? "Uploading CV…" : "Analyze my CV"}
          </button>
        </div>
      </form>
    </section>
  );
}
