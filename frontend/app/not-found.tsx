import Link from "next/link";

import { Button } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="container-page flex min-h-[60vh] flex-col items-center justify-center py-16 text-center">
      <p className="text-sm font-medium uppercase tracking-wide text-brand-700">404</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-3 max-w-md text-ink-muted">
        The page you are looking for does not exist. If you scanned a QR code, the campaign may
        not be published yet.
      </p>
      <div className="mt-6 flex gap-3">
        <Link href="/">
          <Button variant="outline">Go home</Button>
        </Link>
        <Link href="/campaigns">
          <Button>Explore campaigns</Button>
        </Link>
      </div>
    </div>
  );
}
