"use client";

import { useEffect } from "react";

import { Button } from "@/components/ui";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surfaced in the console here; a real deployment would ship this to an
    // error tracker instead.
    console.error("Unhandled UI error:", error);
  }, [error]);

  return (
    <div className="container-page flex min-h-[60vh] flex-col items-center justify-center py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Something went wrong</h1>
      <p className="mt-3 max-w-md text-ink-muted">
        An unexpected error occurred while rendering this page. Trying again often resolves it.
      </p>
      {error.digest && (
        <p className="mt-2 font-mono text-xs text-ink-faint">Reference: {error.digest}</p>
      )}
      <Button className="mt-6" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
