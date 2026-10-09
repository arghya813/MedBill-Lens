import { Link } from "react-router-dom";
import { Compass } from "lucide-react";

export default function NotFoundPage() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-20 text-center sm:px-6">
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-ink-100 text-ink-500">
        <Compass className="h-6 w-6" aria-hidden="true" />
      </span>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-ink-900">
        We couldn't find that page
      </h1>
      <p className="mt-2 text-ink-600">
        The link may be out of date. Start from the beginning, or jump straight to your bill.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-3">
        <Link to="/" className="btn-primary">
          Go to the home page
        </Link>
        <Link to="/upload" className="btn-secondary">
          Check a bill
        </Link>
        <Link to="/demo" className="btn-ghost">
          See a demo
        </Link>
      </div>
    </div>
  );
}
