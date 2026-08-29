"use client";

import Link from "next/link";
import { HeartHandshake } from "lucide-react";

import { Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { ContributionRow } from "@/features/campaign/contribution-row";
import { useMyContributions } from "@/hooks";

export default function ContributionsPage() {
  return (
    <RequireRole roles={["CONTRIBUTOR", "CREATOR", "ADMIN"]}>
      <Contributions />
    </RequireRole>
  );
}

function Contributions() {
  const { data, isLoading, isError, refetch } = useMyContributions();

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">All contributions</h1>
        <p className="mt-1.5 text-ink-muted">
          Every contribution with its payment reference and blockchain record.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>
            {data ? `${data.total} contribution${data.total === 1 ? "" : "s"}` : "Contributions"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <ErrorState title="Could not load contributions" onRetry={() => refetch()} />
          ) : isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              icon={<HeartHandshake className="h-6 w-6" />}
              title="No contributions yet"
              description="Back a campaign and its full record will appear here."
              action={
                <Link href="/campaigns">
                  <Button size="sm">Explore campaigns</Button>
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-surface-border">
              {data.items.map((contribution) => (
                <ContributionRow key={contribution.id} contribution={contribution} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
