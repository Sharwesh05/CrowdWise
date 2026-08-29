"use client";

import { useState } from "react";
import Link from "next/link";
import Script from "next/script";
import {
  BadgeCheck,
  Clock,
  Download,
  HeartHandshake,
  MessageSquarePlus,
  QrCode,
  Target,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CopyButton,
  ErrorState,
  Progress,
  Skeleton,
  StarRating,
  Tabs,
} from "@/components/ui";
import { AIAnalysisPanel } from "@/features/campaign/ai-analysis-panel";
import { BlockchainPanel } from "@/features/campaign/blockchain-panel";
import {
  CommunityInsightsPanel,
  FeedbackList,
  SentimentPanel,
} from "@/features/campaign/community-panel";
import { ContributeDialog } from "@/features/campaign/contribute-dialog";
import { FeedbackDialog } from "@/features/campaign/feedback-dialog";
import { GovernancePanel } from "@/features/governance/governance-panel";
import { API_URL } from "@/lib/api";
import { formatCompactCurrency, formatCurrency, formatNumber, formatTimeRemaining } from "@/lib/format";
import { CAMPAIGN_STATUS_META, CATEGORY_LABELS, cn, healthTone } from "@/lib/utils";
import { useCampaignContributions, usePublicCampaign, useSession } from "@/hooks";

const FUNDABLE = new Set(["LIVE", "CONTINUED"]);

export default function CampaignPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const { data: user } = useSession();
  const { data: campaign, isLoading, isError, error, refetch } = usePublicCampaign(id);
  const { data: backers } = useCampaignContributions(id);

  const [tab, setTab] = useState("about");
  const [contributeOpen, setContributeOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [qrOpen, setQrOpen] = useState(false);

  if (isLoading) return <CampaignSkeleton />;

  if (isError || !campaign) {
    return (
      <div className="container-page py-16">
        <ErrorState
          title="Campaign not found"
          message={
            error instanceof Error
              ? error.message
              : "This campaign may not be published yet, or the link may be incorrect."
          }
          onRetry={() => refetch()}
        />
        <div className="mt-6 text-center">
          <Link href="/campaigns" className="text-sm font-medium text-brand-700 hover:underline">
            Browse all campaigns →
          </Link>
        </div>
      </div>
    );
  }

  const status = CAMPAIGN_STATUS_META[campaign.status];
  const canFund = FUNDABLE.has(campaign.status);
  const isCreator = user?.id === campaign.creator.id;

  return (
    <>
      {/* Razorpay checkout is only needed when real keys are configured. */}
      <Script src="https://checkout.razorpay.com/v1/checkout.js" strategy="lazyOnload" />

      <div className="border-b border-surface-border bg-surface">
        <div className="container-page py-8">
          <div className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
            <Link href="/campaigns" className="hover:text-ink">
              Campaigns
            </Link>
            <span aria-hidden>/</span>
            <span className="font-mono text-xs">{campaign.public_id}</span>
            {campaign.is_demo && <Badge tone="caution">DEMO DATA</Badge>}
          </div>

          <div className="mt-4 grid gap-8 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="brand">
                  {CATEGORY_LABELS[campaign.category] ?? campaign.category}
                </Badge>
                <Badge tone={status.tone} dot>
                  {status.label}
                </Badge>
              </div>

              <h1 className="mt-3 text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
                {campaign.title}
              </h1>
              <p className="mt-3 max-w-2xl text-lg leading-relaxed text-ink-muted">
                {campaign.short_description}
              </p>

              <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-3 text-sm">
                <span className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700">
                    {campaign.creator.name.charAt(0)}
                  </span>
                  <span>
                    <span className="font-medium text-ink">{campaign.creator.name}</span>
                    {campaign.creator.is_verified && (
                      <span className="ml-1.5 inline-flex items-center gap-1 text-xs text-brand-700">
                        <BadgeCheck className="h-3.5 w-3.5" aria-hidden />
                        Verified creator
                      </span>
                    )}
                  </span>
                </span>
                {campaign.average_rating !== null && (
                  <span className="flex items-center gap-1.5">
                    <StarRating value={campaign.average_rating} readOnly size={14} />
                    <span className="text-ink-muted">
                      {campaign.average_rating.toFixed(1)} / 5
                    </span>
                  </span>
                )}
              </div>
            </div>

            {/* Funding panel */}
            <aside className="lg:col-span-1">
              <Card className="lg:sticky lg:top-24">
                <CardContent className="space-y-5 p-5">
                  <div>
                    <div className="flex items-baseline justify-between">
                      <span className="text-2xl font-semibold tracking-tight text-ink">
                        {formatCurrency(campaign.raised_amount)}
                      </span>
                      <span className="text-sm font-medium text-brand-700">
                        {campaign.funding_percentage}%
                      </span>
                    </div>
                    <p className="mt-0.5 text-sm text-ink-muted">
                      raised of {formatCurrency(campaign.target_amount)} target
                    </p>
                    <Progress
                      value={campaign.funding_percentage}
                      className="mt-3 h-2.5"
                      label={`${campaign.funding_percentage}% funded`}
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-3 border-y border-surface-border py-4 text-center">
                    <div>
                      <p className="text-lg font-semibold tabular-nums text-ink">
                        {formatNumber(campaign.contributor_count)}
                      </p>
                      <p className="text-2xs uppercase tracking-wide text-ink-faint">Backers</p>
                    </div>
                    <div>
                      <p className="text-lg font-semibold tabular-nums text-ink">
                        {campaign.days_remaining}
                      </p>
                      <p className="text-2xs uppercase tracking-wide text-ink-faint">Days left</p>
                    </div>
                    <div>
                      <p
                        className={cn(
                          "text-lg font-semibold tabular-nums",
                          healthTone(campaign.health?.score),
                        )}
                      >
                        {campaign.health?.score ?? "—"}
                      </p>
                      <p className="text-2xs uppercase tracking-wide text-ink-faint">Health</p>
                    </div>
                  </div>

                  {canFund ? (
                    <Button
                      className="w-full"
                      size="lg"
                      onClick={() => setContributeOpen(true)}
                      disabled={isCreator}
                      leadingIcon={<HeartHandshake className="h-4 w-4" />}
                    >
                      {isCreator ? "This is your campaign" : "Contribute"}
                    </Button>
                  ) : (
                    <Alert tone="info">{status.description}</Alert>
                  )}

                  <p className="text-center text-xs text-ink-muted">
                    Minimum {formatCurrency(campaign.minimum_contribution)} ·{" "}
                    {formatTimeRemaining(campaign.deadline)}
                  </p>

                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => setFeedbackOpen(true)}
                      leadingIcon={<MessageSquarePlus className="h-4 w-4" />}
                    >
                      Feedback
                    </Button>
                    <Button
                      variant="outline"
                      className="flex-1"
                      onClick={() => setQrOpen((open) => !open)}
                      leadingIcon={<QrCode className="h-4 w-4" />}
                    >
                      QR
                    </Button>
                  </div>

                  {qrOpen && (
                    <div className="animate-fade-in space-y-3 rounded-lg border border-surface-border p-4 text-center">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`${API_URL}/api/public/campaigns/${campaign.public_id}/qr.png`}
                        alt={`QR code linking to campaign ${campaign.public_id}`}
                        className="mx-auto h-40 w-40"
                      />
                      <p className="break-all text-xs text-ink-muted">{campaign.qr_url}</p>
                      <div className="flex justify-center gap-2">
                        <CopyButton value={campaign.qr_url} label="Copy link" />
                        <a
                          href={`${API_URL}/api/public/campaigns/${campaign.public_id}/qr.png`}
                          download
                        >
                          <Button variant="outline" size="sm" leadingIcon={<Download className="h-3.5 w-3.5" />}>
                            Download
                          </Button>
                        </a>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </aside>
          </div>
        </div>
      </div>

      <div className="container-page grid gap-8 py-8 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <GovernancePanel publicId={campaign.public_id} />

          <Tabs
            tabs={[
              { id: "about", label: "About" },
              { id: "insights", label: "AI insights" },
              { id: "community", label: "Community", count: campaign.sentiment?.feedback_count },
              { id: "chain", label: "Verification" },
            ]}
            active={tab}
            onChange={setTab}
          />

          {tab === "about" && (
            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>The problem</CardTitle>
                </CardHeader>
                <CardContent className="prose-campaign">
                  <p>{campaign.problem_statement}</p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>The proposed solution</CardTitle>
                </CardHeader>
                <CardContent className="prose-campaign">
                  <p>{campaign.proposed_solution}</p>
                </CardContent>
              </Card>

              {campaign.expected_impact && (
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Target className="h-4 w-4 text-brand-600" aria-hidden />
                      Expected impact
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="prose-campaign">
                    <p>{campaign.expected_impact}</p>
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader>
                  <CardTitle>Full proposal</CardTitle>
                </CardHeader>
                <CardContent className="prose-campaign">
                  {campaign.description.split("\n\n").map((paragraph, index) => (
                    <p key={index}>{paragraph}</p>
                  ))}
                </CardContent>
              </Card>

              {campaign.outcome_rules && (
                <Card>
                  <CardHeader>
                    <CardTitle>What happens if the target is missed</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm leading-relaxed text-ink-soft">
                      {campaign.outcome_rules.outcome_type === "CONTRIBUTOR_VOTE"
                        ? "Contributors vote on the outcome. The available options were fixed before funding opened and cannot be changed once voting begins."
                        : campaign.outcome_rules.outcome_type === "AUTOMATIC_REFUND"
                          ? "All contributions are refunded automatically through payment infrastructure."
                          : "The creator keeps what was raised."}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {campaign.outcome_rules.options.map((option) => (
                        <Badge key={option} tone="neutral">
                          {option === "REFUND" ? "Refund contributors" : "Continue campaign"}
                        </Badge>
                      ))}
                    </div>
                    <p className="text-xs text-ink-faint">{campaign.outcome_rules.note}</p>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {tab === "insights" && (
            <div className="space-y-6">
              <AIAnalysisPanel analysis={campaign.analysis} />
              <CommunityInsightsPanel
                publicId={campaign.public_id}
                canRefresh={Boolean(user && (isCreator || user.role === "ADMIN"))}
              />
            </div>
          )}

          {tab === "community" && (
            <div className="space-y-6">
              <SentimentPanel sentiment={campaign.sentiment} />
              <div>
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-base font-semibold text-ink">Contributor feedback</h3>
                  <Button size="sm" variant="outline" onClick={() => setFeedbackOpen(true)}>
                    Leave feedback
                  </Button>
                </div>
                <FeedbackList publicId={campaign.public_id} />
              </div>
            </div>
          )}

          {tab === "chain" && (
            <BlockchainPanel publicId={campaign.public_id} summary={campaign.blockchain} />
          )}
        </div>

        {/* Sidebar */}
        <aside className="space-y-6">
          {campaign.health && (
            <Card>
              <CardHeader>
                <CardTitle>CrowdWise Campaign Health</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-baseline gap-2">
                  <span className={cn("text-3xl font-semibold", healthTone(campaign.health.score))}>
                    {campaign.health.score}
                  </span>
                  <span className="text-sm text-ink-muted">/ 100 · {campaign.health.label}</span>
                </div>
                <div className="space-y-2.5">
                  {[
                    { label: "Financial signals", value: campaign.health.financial_score },
                    { label: "Community signals", value: campaign.health.community_score },
                    { label: "AI signals", value: campaign.health.ai_score },
                  ].map((row) => (
                    <div key={row.label}>
                      <div className="flex justify-between text-xs">
                        <span className="text-ink-muted">{row.label}</span>
                        <span className="font-medium tabular-nums text-ink">{row.value}</span>
                      </div>
                      <Progress value={row.value} className="mt-1 h-1.5" label={row.label} />
                    </div>
                  ))}
                </div>
                <p className="text-xs leading-relaxed text-ink-faint">{campaign.health.note}</p>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-4 w-4" aria-hidden />
                Recent backers
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!backers || backers.items.length === 0 ? (
                <p className="text-sm text-ink-muted">No contributions yet.</p>
              ) : (
                <ul className="divide-y divide-surface-border">
                  {backers.items.slice(0, 6).map((backer) => (
                    <li key={backer.id} className="flex items-center justify-between py-2 text-sm">
                      <span className="text-ink-soft">{backer.contributor_name}</span>
                      <span className="font-medium tabular-nums text-ink">
                        {formatCompactCurrency(backer.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>

      <ContributeDialog
        campaign={campaign}
        open={contributeOpen}
        onClose={() => setContributeOpen(false)}
      />
      <FeedbackDialog
        publicId={campaign.public_id}
        campaignTitle={campaign.title}
        open={feedbackOpen}
        onClose={() => setFeedbackOpen(false)}
      />
    </>
  );
}

function CampaignSkeleton() {
  return (
    <div className="container-page py-10">
      <div className="grid gap-8 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-10 w-3/4" />
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="mt-8 h-48 w-full" />
        </div>
        <Skeleton className="h-80 w-full" />
      </div>
    </div>
  );
}
