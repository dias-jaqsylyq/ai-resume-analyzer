import { ChecklistIcon, GaugeIcon, ShieldIcon } from "./Icons.tsx";
import { SignIn } from "./SignIn.tsx";

const FEATURES = [
  { icon: GaugeIcon, title: "ATS score", text: "A 0 to 100 score with the reason behind it." },
  { icon: ChecklistIcon, title: "Skills and edits", text: "Matched and missing skills, plus concrete edits ranked by priority." },
  { icon: ShieldIcon, title: "Private by design", text: "Encrypted storage; your CV is deleted automatically after 7 days." },
];

/** Signed-out page: what the product does on the left, the sign-in form on the right. */
export function Landing() {
  return (
    <div className="landing">
      <section className="landing-hero">
        <p className="eyebrow">CV analyzer</p>
        <h1 className="display">See how well your CV fits the job.</h1>
        <p className="lead">
          Paste a job posting, upload your CV, and FitScore reads it the way an applicant tracking system would.
        </p>
        <ul className="features">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title}>
              <span className="feature-icon">
                <Icon />
              </span>
              <span>
                <strong>{title}</strong>
                <span className="muted">{text}</span>
              </span>
            </li>
          ))}
        </ul>
      </section>
      <SignIn />
    </div>
  );
}
