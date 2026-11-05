import Link from "next/link";

export default function NotFound() {
  return (
    <main className="container page-status">
      <h1>Page not found</h1>
      <p className="muted">The page you are looking for does not exist.</p>
      <Link href="/" className="btn btn-primary">Go to the dashboard</Link>
    </main>
  );
}
