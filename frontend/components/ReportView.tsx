import { scoreBand, skillsCoverage, sortSuggestions, type Report } from "@/lib/report.ts";

function ScoreRing({ score }: { score: number }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <svg className={`ring band-${scoreBand(clamped)}`} viewBox="0 0 120 120" role="img" aria-label={`ATS score ${clamped} of 100`}>
      <circle cx="60" cy="60" r={r} className="ring-track" />
      <circle
        cx="60"
        cy="60"
        r={r}
        className="ring-value"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - clamped / 100)}
        transform="rotate(-90 60 60)"
      />
      <text x="60" y="58" textAnchor="middle" className="ring-number">{clamped}</text>
      <text x="60" y="80" textAnchor="middle" className="ring-label">ATS score</text>
    </svg>
  );
}

function Chips({ items, kind }: { items: string[]; kind: "match" | "miss" }) {
  if (items.length === 0) return <p className="muted small">None</p>;
  return (
    <ul className="chips">
      {items.map((s) => (
        <li key={s} className={`chip chip-${kind}`}>{s}</li>
      ))}
    </ul>
  );
}

export function ReportView({ report }: { report: Report }) {
  const coverage = skillsCoverage(report);
  return (
    <div className="stack">
      <section className="card score-card">
        <ScoreRing score={report.ats_score} />
        <div className="stack-sm">
          <p>{report.score_rationale}</p>
          {coverage !== null && (
            <p className="muted small">
              Skills coverage: {report.matched_skills.length} of {report.matched_skills.length + report.missing_skills.length} ({coverage}%)
            </p>
          )}
        </div>
      </section>

      {report.summary && (
        <section className="card">
          <h2>Summary</h2>
          <p>{report.summary}</p>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <h2>Matched skills</h2>
          <Chips items={report.matched_skills} kind="match" />
        </section>
        <section className="card">
          <h2>Missing skills</h2>
          <Chips items={report.missing_skills} kind="miss" />
        </section>
      </div>

      <section className="card">
        <h2>Suggestions</h2>
        {report.suggestions.length === 0 ? (
          <p className="muted">No suggestions.</p>
        ) : (
          <ol className="suggestions">
            {sortSuggestions(report.suggestions).map((s, i) => (
              <li key={i}>
                <span className={`prio prio-${s.priority}`}>{s.priority}</span>
                <span className="suggestion-body">
                  <strong>{s.section}</strong>
                  <span>{s.advice}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
