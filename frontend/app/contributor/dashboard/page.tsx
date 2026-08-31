"use client";

import Link from "next/link";
import { Blocks, HeartHandshake, Vote, Wallet } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  Progress,
  Skeleton,
  Stat,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { ContributionRow } from "@/features/campaign/contribution-row";
import { formatCompactCurrency, formatTimeRemaining } from "@/lib/format";
import { useContributorDashboard } from "@/hooks";

export default function ContributorDashboardPage() {
  return (
    <RequireRole roles={["CONTRIBUTOR", "CREATOR", "ADMIN"]}>
      <DashboardContent />
    </RequireRole>
  );
}

function DashboardContent() {
  const { data, isLoading, isError, refetch } = useContributorDashboard();

  if (isError) {
    return (
      <div className="container-page py-10">
        <ErrorState title="Could not load your dashboard" onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="container-page py-10">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Your contributions</h1>
        <p className="mt-1.5 text-ink-muted">
          Everything you have funded, its verification status, and the votes you can cast.
        </p>
      </header>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Total contributed"
              value={formatCompactCurrency(data!.cards.total_contributed)}
              sublabel="Verified payments only"
              icon={<Wallet className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Campaigns supported"
              value={data!.cards.campaigns_supported}
              sublabel={`${data!.cards.contributions} contribution${data!.cards.contributions === 1 ? "" : "s"}`}
              icon={<HeartHandshake className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Anchored on chain"
              value={`${data!.cards.blockchain_recorded}/${data!.cards.contributions}`}
              sublabel="Tamper-evident records"
              icon={<Blocks className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Votes open to you"
              value={data!.cards.open_votes}
              sublabel={data!.cards.open_votes ? "Action needed" : "Nothing pending"}
              icon={<Vote className="h-4 w-4" aria-hidden />}
            />
          </div>

          {data!.active_votes.length > 0 && (
            <Card className="mt-6 border-accent-300/40">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Vote className="h-4 w-4 text-accent-600" aria-hidden />
                  Governance votes open to you
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {data!.active_votes.map((item) => (
                  <div
                    key={item.public_id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border p-4"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{item.title}</p>
                      <p className="mt-0.5 text-xs text-ink-muted">
                        {formatCompactCurrency(item.raised_amount)} of{" "}
                        {formatCompactCurrency(item.target_amount)} raised ·{" "}
                        {formatTimeRemaining(item.closes_at)}
                      </p>
                      <Progress
                        value={
                          (Number(item.raised_amount) / Number(item.target_amount || 1)) * 100
                        }
                        className="mt-2 h-1.5"
                      />
                    </div>
                    <Link href={`/campaign/${item.public_id}`}>
                      <Button size="sm" variant={item.has_voted ? "outline" : "primary"}>
                        {item.has_voted ? "View result" : "Cast your vote"}
                      </Button>
                    </Link>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card className="mt-6">
            <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
              <CardTitle>Recent contributions</CardTitle>
              <Link
                href="/contributor/contributions"
                className="text-sm font-medium text-brand-700 hover:underline"
              >
                View all →
              </Link>
            </CardHeader>
            <CardContent>
              {data!.recent_contributions.length === 0 ? (
                <EmptyState
                  icon={<HeartHandshake className="h-6 w-6" />}
                  title="You have not contributed yet"
                  description="Find a campaign worth backing and your record will appear here."
                  action={
                    <Link href="/campaigns">
                      <Button size="sm">Explore campaigns</Button>
                    </Link>
                  }
                />
              ) : (
                <ul className="divide-y divide-surface-border">
                  {data!.recent_contributions.map((contribution) => (
                    <ContributionRow key={contribution.id} contribution={contribution} />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {data!.past_votes.length > 0 && (
            <Card className="mt-6">
              <CardHeader>
                <CardTitle>Your voting record</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="divide-y divide-surface-border">
                  {data!.past_votes.map((vote) => (
                    <li key={vote.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium text-ink">
                          {vote.campaign_title ?? vote.campaign_public_id}
                        </p>
                        <p className="mt-0.5 font-mono text-2xs text-ink-faint">
                          {vote.blockchain_tx
                            ? `Anchored ${vote.blockchain_tx.slice(0, 14)}…`
                            : "Anchor pending"}
                        </p>
                      </div>
                      <Badge tone={vote.choice === "REFUND" ? "critical" : "positive"}>
                        Voted {vote.choice === "REFUND" ? "refund" : "continue"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <Alert tone="info" className="mt-6">
            Your contributions are recorded in CrowdWise the moment the payment is verified.
            Blockchain anchoring runs separately — a pending anchor never means your payment is
            in doubt.
          </Alert>
        </>
      )}
    </div>
  );
}
