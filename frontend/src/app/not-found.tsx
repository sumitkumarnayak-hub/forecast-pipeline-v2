import Link from "next/link";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="not-found-page">
      <div className="card not-found-card">
        <FileQuestion size={44} className="not-found-icon" />
        <h1>Page not found</h1>
        <p>The page you are looking for does not exist or has been moved.</p>
        <div className="not-found-actions">
          <Link href="/dashboard" className="btn btn-primary btn-sm">
            Go to Dashboard
          </Link>
          <Link href="/about" className="btn btn-secondary btn-sm">
            User guide
          </Link>
        </div>
      </div>
    </div>
  );
}
