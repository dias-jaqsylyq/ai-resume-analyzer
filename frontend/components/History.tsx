"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { formatDate, scoreBand, type AnalysisSummary } from "@/lib/report.ts";
import { useApp } from "./AppProvider.tsx";
import { StatusBadge } from "./StatusBadge.tsx";

const PAGE_SIZE = 10;

export function History() {
  const { api } = useApp();
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (from: string | null) => {
      setLoading(true);
      setError(null);
      try {
        const page = await api.listAnalyses(PAGE_SIZE, from);
        setItems((prev) => (from ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void load(null);
  }, [load]);

  return (
    <section className="card">
      <div className="row between">
        <h2>History</h2>
        <button type="button" className="btn btn-ghost" onClick={() => void load(null)} disabled={loading}>
          Refresh
        </button>
      </div>
      {error && <p className="alert" role="alert">{error}</p>}
      {!loading && !error && items.length === 0 && <p className="muted">No analyses yet. Start one above.</p>}
      <ul className="history">
        {items.map((item) => (
          <li key={item.analysis_id}>
            <Link href={`/analysis/?id=${encodeURIComponent(item.analysis_id)}`} className="history-item">
              <span className="history-main">
                <strong>{item.job_title || "Untitled job"}</strong>
                <span className="muted small">{formatDate(item.created_at)}</span>
              </span>
              <span className="history-side">
                {typeof item.ats_score === "number" && (
                  <span className={`score-pill band-${scoreBand(item.ats_score)}`}>{item.ats_score}</span>
                )}
                <StatusBadge status={item.status} />
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {loading && <p className="muted">Loading…</p>}
      {cursor && !loading && (
        <button type="button" className="btn btn-ghost full" onClick={() => void load(cursor)}>
          Load more
        </button>
      )}
    </section>
  );
}
