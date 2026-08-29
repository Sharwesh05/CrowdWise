"use client";

import Link from "next/link";
import {
  Activity,
  ArrowRight,
  BadgeCheck,
  HeartHandshake,
  Plus,
  Star,
  TrendingUp,
} from "lucide-react";

import {
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
import { formatCompactCurrency, formatNumber } from "@/lib/format";
import { CAMPAIGN_STATUS_META, cn, healthTone, riskTone } from "@/lib/utils";
import { useCreatorDashboard, useKycStatus, useSession } from "@/hooks";

export default function CreatorDashboardPage() {
  return (
    <RequireRole roles={["CREATOR", "ADMIN"]}>
      <DashboardContent />
    </RequireRole>
  );
}

function DashboardContent() {
  const { data: user } = useSession();
  const { data, isLoading, isError, refetch } = useCreatorDashboard();
  const { data: kyc } = useKycStatus();

  const needsKyc = kyc && kyc.status !== "VERIFIED";

  return (
    <div className="container-page py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Creator dashboard</h1>
          <p className="mt-1.5 text-ink-muted">
            Welcome back{user ? `, ${user.name.split(" ")[0]}` : ""}. Here is how your campaigns
            are doing.
          </p>
        </div>
        <Link href="/creator/campaigns/new">
          <Button leadingIcon={<Plus className="h-4 w-4" />}>New campaign</Button>
        </Link>
      </header>

      {needsKyc && (
        <Card className="mb-6 border-caution/30 bg-caution-soft/30">
          <CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
            <div className="flex items-start gap-3">
              <BadgeCheck className="mt-0.5 h-5 w-5 text-caution-strong" aria-hidden />
              <div>
                <p className="text-sm font-medium text-ink">Complete identity verification</p>
                <p className="mt-0.5 text-sm text-ink-muted">
                  Your campaigns cannot be reviewed until verification is complete. Status:{" "}
                  {kyc.status.replace("_", " ").toLowerCase()}.
                </p>
              </div>
            </div>
            <Link href="/creator/kyc">
              <Button size="sm" variant="outline">
                Verify now
              </Button>
            </Link>
          </CardContent>
        </Card>
      )}

      {isError ? (
        <ErrorState title="Could not load your dashboard" onRetry={() => refetch()} />
      ) : isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-28 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Active campaigns"
              value={data!.cards.active_campaigns}
              sublabel={`${data!.cards.total_campaigns} total`}
              icon={<Activity className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Total raised"
              value={formatCompactCurrency(data!.cards.total_raised)}
              sublabel="Verified contributions only"
              icon={<TrendingUp className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Contributors"
              value={formatNumber(data!.cards.contributors)}
              sublabel={
                data!.cards.average_rating
                  ? `${data!.cards.average_rating.toFixed(1)} / 5 average rating`
                  : "No ratings yet"
              }
              icon={<HeartHandshake className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Campaign health"
              value={data!.cards.average_health ?? "—"}
              tone={healthTone(data!.cards.average_health)}
              sublabel={
                data!.cards.ai_risk_level
                  ? `AI risk: ${data!.cards.ai_risk_level}`
                  : "Awaiting AI analysis"
              }
              icon={<Star className="h-4 w-4" aria-hidden />}
            />
          </div>

          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Your campaigns</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {data!.campaigns.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    title="No campaigns yet"
                    description="Create your first campaign to start raising from the community."
                    action={
                      <Link href="/creator/campaigns/new">
                        <Button size="sm">Create a campaign</Button>
                      </Link>
                    }
                  />
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-surface-border text-left">
                        {[
                          "Campaign",
                          "Raised / target",
                          "Progress",
                          "Backers",
                          "Sentiment",
                          "Status",
                          "Days left",
                          "",
                        ].map((heading) => (
                          <th
                            key={heading}
                            scope="col"
                            className="whitespace-nowrap px-4 py-3 text-xs font-medium uppercase tracking-wide text-ink-faint"
                          >
                            {heading}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {data!.campaigns.map((campaign) => {
                        const status = CAMPAIGN_STATUS_META[campaign.status];
                        return (
                          <tr key={campaign.id} className="hover:bg-surface-subtle">
                            <td className="max-w-[240px] px-4 py-3">
                              <p className="truncate font-medium text-ink">{campaign.title}</p>
                              <p className="font-mono text-2xs text-ink-faint">
                                {campaign.public_id}
                              </p>
                            </td>
                            <td className="whitespace-nowrap px-4 py-3 tabular-nums text-ink-soft">
                              {formatCompactCurrency(campaign.raised_amount)}
                              <span className="text-ink-faint">
                                {" "}
                                / {formatCompactCurrency(campaign.target_amount)}
                              </span>
                            </td>
                            <td className="w-32 px-4 py-3">
                              <Progress value={campaign.funding_percentage} className="h-1.5" />
                              <span className="mt-1 block text-2xs text-ink-muted">
                                {campaign.funding_percentage}%
                              </span>
                            </td>
                            <td className="px-4 py-3 tabular-nums text-ink-soft">
                              {campaign.contributor_count}
                            </td>
                            <td className="px-4 py-3">
                              {campaign.feedback_count > 0 ? (
                                <span className="text-ink-soft">
                                  {campaign.positive_percentage}% positive
                                  <span className="block text-2xs text-ink-faint">
                                    {campaign.feedback_count} review
                                    {campaign.feedback_count === 1 ? "" : "s"}
                                  </span>
                                </span>
                              ) : (
                                <span className="text-ink-faint">—</span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <Badge tone={status.tone}>{status.label}</Badge>
                            </td>
                            <td className="px-4 py-3 tabular-nums text-ink-soft">
                              {campaign.days_remaining}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <Link
                                href={`/creator/campaigns/${campaign.id}`}
                                className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
                              >
                                Manage
                                <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
