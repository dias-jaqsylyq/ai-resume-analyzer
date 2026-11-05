"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api.ts";
import { failureMessage, formatDate, isTerminal, type AnalysisDetail } from "@/lib/report.ts";
import { useApp } from "./AppProvider.tsx";
import { Chevron } from "./Icons.tsx";
import { ReportView } from "./ReportView.tsx";
import { StatusBadge } from "./StatusBadge.tsx";
import { Steps } from "./Steps.tsx";

const POLL_MS = 3000;
const MAX_POLLS = 100; // ~5 minutes; the pipeline normally finishes in well under a minute

export function AnalysisView() {
  const { api } = useApp();
  const id = useSearchParams().get("id");
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!id) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let polls = 0;

    async function tick() {
      try {
        const detail = await api.getAnalysis(id as string);
        if (stopped) return;
        setAnalysis(detail);
        setError(null);
        if (isTerminal(detail.status)) return;
      } catch (err) {
        if (stopped) return;
        if (err instanceof ApiError && (err.status === 404 || err.status === 401)) {
          setError(err.status === 404 ? "Analysis not found." : err.message);
          return;
        }
        setError((err as Error).message); // transient: keep polling
      }
      polls += 1;
      if (polls >= MAX_POLLS) setTimedOut(true);
      else timer = setTimeout(tick, POLL_MS);
    }

    void tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [api, id]);

  if (!id)
    if (!id)
    return (
      <p className="alert">
        No analysis selected. <Link href="/">Back</Link>
      </p>
    );

  return (
    <div className="stack">
      <div className="row between wrap">
        <Link href="/" className="back">
          <Chevron direction="left" />
          <span>All analyses</span>
        </Link>
        {analysis && <StatusBadge status={analysis.status} />}
      </div>
      {analysis && (
        <div className="page-title">
          <h1>{analysis.job_title || "Untitled job"}</h1>
          <p className="muted small">{formatDate(analysis.created_at)}</p>
        </div>
      )}
      {error && <p className="alert" role="alert">{error}</p>}
      {!analysis && !error && <p className="muted">Loading…</p>}
      {analysis && !isTerminal(analysis.status) && (
        <section className="card processing center">
          <Steps status={analysis.status} />
          <div className="spinner" aria-hidden="true" />
          <p className="score-verdict">
            {analysis.status === "PENDING" ? "Waiting for your CV to arrive…" : "Reading your CV and scoring it…"}
          </p>
          <p className="muted small">This page updates by itself.{timedOut && " It is taking longer than usual; refresh later."}</p>
        </section>
      )}
      {analysis?.status === "FAILED" && (
        <section className="card stack">
          <Steps status={analysis.status} />
          <p className="alert">{failureMessage(analysis.error)}</p>
          <div>
            <Link href="/" className="btn btn-primary">Try again</Link>
          </div>
        </section>
      )}
      {analysis?.status === "DONE" && analysis.report && <ReportView report={analysis.report} />}
      {analysis?.job_description && (
        <details className="card">
          <summary>Job description</summary>
          <p className="pre">{analysis.job_description}</p>
        </details>
      )}
    </div>
  );
}
