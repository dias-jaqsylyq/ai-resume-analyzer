import Link from "next/link";

export default function NotFound() {
  return (
    <main className="container center">
      <h1>Page not found</h1>
      <Link href="/" className="link">Go to the dashboard</Link>
    </main>
  );
}
