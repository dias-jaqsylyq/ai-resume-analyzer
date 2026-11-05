const REPO_URL = "https://github.com/dias-jaqsylyq/ai-resume-analyzer";

export function Footer({ wide = false }: { wide?: boolean }) {
  return (
    <footer className={wide ? "footer wide" : "footer"}>
      <span>FitScore</span>
      <span aria-hidden="true">·</span>
      <span>
        Built by <a href="https://github.com/dias-jaqsylyq">Dias</a> on AWS serverless
      </span>
      <span aria-hidden="true">·</span>
      <a href={REPO_URL}>Source on GitHub</a>
    </footer>
  );
}
