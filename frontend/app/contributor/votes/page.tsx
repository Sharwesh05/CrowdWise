"use client";

import Link from "next/link";
import { Vote } from "lucide-react";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { formatDateTime, truncateHash } from "@/lib/format";
import { useMyVotes } from "@/hooks";

export default function VotesPage() {
  return (
    <RequireRole roles={["CONTRIBUTOR", "CREATOR", "ADMIN"]}>
      <Votes />
    </RequireRole>
  );
}

function Votes() {
  const { data, isLoading, isError, refetch } = useMyVotes();

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Your governance votes</h1>
        <p className="mt-1.5 text-ink-muted">
          Each vote is recorded in the database and anchored on chain for tamper-evidence.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Voting record</CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <ErrorState title="Could not load your votes" onRetry={() => refetch()} />
          ) : isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              icon={<Vote className="h-6 w-6" />}
              title="You have not voted yet"
              description="When a campaign you backed misses its target, you get a say in what happens next."
              action={
                <Link href="/contributor/dashboard">
                  <Button size="sm" variant="outline">
                    Back to dashboard
                  </Button>
                </Link>
              }
            />
          ) : (
            <ul className="divide-y divide-surface-border">
              {data.items.map((vote) => (
                <li key={vote.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <Link
                      href={`/campaign/${vote.campaign_public_id}`}
                      className="truncate text-sm font-medium text-ink hover:underline"
                    >
                      {vote.campaign_title ?? vote.campaign_public_id}
                    </Link>
                    <p className="mt-0.5 text-xs text-ink-faint">{formatDateTime(vote.created_at)}</p>
                    <p className="mt-0.5 font-mono text-2xs text-ink-faint">
                      {vote.blockchain_tx ? truncateHash(vote.blockchain_tx, 16, 10) : "Anchor pending"}
                    </p>
                  </div>
                  <Badge tone={vote.choice === "REFUND" ? "critical" : "positive"}>
                    {vote.choice === "REFUND" ? "Refund" : "Continue"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
