"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowLeft,
  Brain,
  CheckCircle2,
  CreditCard,
  Download,
  ExternalLink,
  Printer,
  QrCode,
  Send,
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
  Stat,
  Tabs,
  useToast,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { AIAnalysisPanel } from "@/features/campaign/ai-analysis-panel";
import { BlockchainPanel } from "@/features/campaign/blockchain-panel";
import { DocumentsPanel } from "@/features/campaign/documents-panel";
import { EditProposalPanel } from "@/features/campaign/edit-proposal-panel";
import { CommunityInsightsPanel, FeedbackList, SentimentPanel } from "@/features/campaign/community-panel";
import { UpdatesPanel } from "@/features/campaign/updates-panel";
import { FundingChart } from "@/features/campaign/funding-chart";
import { API_URL, ApiError } from "@/lib/api";
import { formatCompactCurrency, formatDateTime, titleCase } from "@/lib/format";
import { CAMPAIGN_STATUS_META, cn, healthTone } from "@/lib/utils";
import {
  useApplicationFeeOrder,
  useCampaign,
  useCampaignAnalytics,
  useCampaignQr,
  useRunAnalysis,
  useSimulatePayment,
  useSubmitCampaign,
} from "@/hooks";

export default function CreatorCampaignPage({ params }: { params: { id: string } }) {
  const { id } = params;
  return (
    <RequireRole roles={["CREATOR", "ADMIN"]}>
      <CampaignManager campaignId={Number(id)} />
    </RequireRole>
  );
}

function CampaignManager({ campaignId }: { campaignId: number }) {
  const { data: campaign, isLoading, isError, refetch } = useCampaign(campaignId);
  const [tab, setTab] = useState("lifecycle");

  if (isLoading) {
    return (
      <div className="container-page space-y-4 py-10">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (isError || !campaign) {
    return (
      <div className="container-page py-10">
        <ErrorState title="Could not load this campaign" onRetry={() => refetch()} />
      </div>
    );
  }

  const status = CAMPAIGN_STATUS_META[campaign.status];
  const isPublic = ["LIVE", "COMPLETED", "TARGET_MET", "TARGET_MISSED", "GOVERNANCE", "REFUND_PENDING", "CONTINUED", "CLOSED"].includes(
    campaign.status,
  );

  return (
    <div className="container-page py-10">
      <Link
        href="/creator/dashboard"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to dashboard
      </Link>

      <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-ink-faint">{campaign.public_id}</span>
            <Badge tone={status.tone} dot>
              {status.label}
            </Badge>
            {campaign.is_demo && <Badge tone="caution">DEMO</Badge>}
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{campaign.title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{status.description}</p>
        </div>

        {isPublic && (
          <Link href={`/campaign/${campaign.public_id}`}>
            <Button variant="outline" leadingIcon={<ExternalLink className="h-4 w-4" />}>
              View public page
            </Button>
          </Link>
        )}
      </header>

      {campaign.review_notes && (
        <Alert
          tone={campaign.approval_status === "REJECTED" ? "critical" : "caution"}
          title={
            campaign.approval_status === "REJECTED"
              ? "Rejected in review"
              : campaign.approval_status === "CHANGES_REQUESTED"
                ? "Changes requested"
                : "Reviewer notes"
          }
          className="mt-5"
        >
          {campaign.review_notes}
        </Alert>
      )}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Raised" value={formatCompactCurrency(campaign.raised_amount)} sublabel={`of ${formatCompactCurrency(campaign.target_amount)}`} />
        <Stat label="Progress" value={`${campaign.funding_percentage}%`} sublabel={`${campaign.contributor_count} backers`} />
        <Stat
          label="Health"
          value={campaign.health?.score ?? "—"}
          tone={healthTone(campaign.health?.score)}
          sublabel={campaign.health?.label ?? "Not yet scored"}
        />
        <Stat
          label="AI risk"
          value={campaign.analysis?.risk_level ?? "—"}
          sublabel={campaign.analysis ? `Feasibility ${campaign.analysis.feasibility_score}` : "No analysis yet"}
        />
      </div>

      <Tabs
        className="mt-8"
        tabs={[
          { id: "lifecycle", label: "Lifecycle" },
          ...(campaign.editable ? [{ id: "edit", label: "Edit proposal" }] : []),
          { id: "media", label: "Image & documents" },
          { id: "analytics", label: "Analytics" },
          { id: "updates", label: "Updates", count: campaign.update_count },
          { id: "community", label: "Community", count: campaign.sentiment?.feedback_count },
          { id: "qr", label: "QR & sharing" },
          { id: "chain", label: "Blockchain" },
          { id: "timeline", label: "Timeline", count: campaign.events.length },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="mt-6">
        {tab === "lifecycle" && <LifecyclePanel campaign={campaign} onChanged={() => refetch()} />}
        {tab === "edit" && <EditProposalPanel campaign={campaign} />}
        {tab === "media" && (
          <DocumentsPanel campaignId={campaign.id} coverImageUrl={campaign.cover_image_url} />
        )}
        {tab === "analytics" && <AnalyticsPanel publicId={campaign.public_id} />}
        {tab === "updates" && (
          <UpdatesPanel
            publicId={campaign.public_id}
            canPost
            published={Boolean(campaign.published_at)}
          />
        )}

        {tab === "community" && (
          <div className="space-y-6">
            <SentimentPanel
              sentiment={campaign.sentiment}
              publicId={campaign.public_id}
              canRefresh
            />
            <CommunityInsightsPanel publicId={campaign.public_id} canRefresh />
            <FeedbackList publicId={campaign.public_id} />
          </div>
        )}
        {tab === "qr" && <QrPanel campaignId={campaign.id} publicId={campaign.public_id} hasQr={Boolean(campaign.qr_token)} title={campaign.title} />}
        {tab === "chain" && <BlockchainPanel publicId={campaign.public_id} summary={campaign.blockchain} />}
        {tab === "timeline" && <TimelinePanel events={campaign.events} />}
      </div>
    </div>
  );
}

/** The lifecycle gates, presented as the sequence they actually are. */
function LifecyclePanel({
  campaign,
  onChanged,
}: {
  campaign: import("@/types").CreatorCampaign;
  onChanged: () => void;
}) {
  const { notify } = useToast();
  const submit = useSubmitCampaign();
  const feeOrder = useApplicationFeeOrder();
  const simulate = useSimulatePayment();
  const analyze = useRunAnalysis();
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);

  const run = async (action: () => Promise<unknown>, success: string) => {
    setError(null);
    try {
      await action();
      notify({ title: success, tone: "positive" });
      onChanged();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Something went wrong.");
    }
  };

  const payFee = async () => {
    setError(null);
    setPaying(true);
    try {
      const order = await feeOrder.mutateAsync(campaign.id);
      if (order.provider === "demo") {
        await simulate.mutateAsync(order.payment_id);
        notify({ title: "Application fee verified", tone: "positive" });
        onChanged();
      } else {
        notify({
          title: "Order created",
          description: "Complete the payment in the Razorpay checkout window.",
        });
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not create the fee order.");
    } finally {
      setPaying(false);
    }
  };

  const feePaid = ["FEE_PAID", "SUBMITTED", "APPROVED"].includes(campaign.application?.status ?? "");
  const analysed = Boolean(campaign.analysis);

  const steps = [
    {
      title: "Identity verification",
      body: "Creator identity must be verified before a campaign can proceed.",
      done: campaign.status !== "DRAFT" && campaign.status !== "KYC_PENDING",
      action:
        campaign.status === "DRAFT" || campaign.status === "KYC_PENDING" ? (
          <div className="flex gap-2">
            <Link href="/creator/kyc">
              <Button size="sm" variant="outline">
                Verify identity
              </Button>
            </Link>
            <Button
              size="sm"
              loading={submit.isPending}
              leadingIcon={<Send className="h-3.5 w-3.5" />}
              onClick={() => run(() => submit.mutateAsync(campaign.id), "Campaign submitted")}
            >
              Submit for review
            </Button>
          </div>
        ) : null,
    },
    {
      title: "Application fee",
      body: "A small fee, verified server-side. The application only moves forward once the payment is confirmed.",
      done: feePaid,
      action:
        campaign.status === "FEE_PENDING" ? (
          <Button size="sm" loading={paying} leadingIcon={<CreditCard className="h-3.5 w-3.5" />} onClick={payFee}>
            Pay application fee
          </Button>
        ) : null,
    },
    {
      title: "AI campaign analysis",
      body: "Feasibility, clarity, impact and risk are scored to support the reviewer's decision.",
      done: analysed,
      action:
        campaign.status === "ANALYSIS_PENDING" ? (
          <Button
            size="sm"
            loading={analyze.isPending}
            leadingIcon={<Brain className="h-3.5 w-3.5" />}
            onClick={() => run(() => analyze.mutateAsync(campaign.id), "Analysis complete")}
          >
            Run AI analysis
          </Button>
        ) : null,
    },
    {
      title: "Admin review",
      body: "A human reviewer approves, rejects, or asks for changes. AI never approves a campaign.",
      done: campaign.approval_status === "APPROVED",
      action: null,
    },
    {
      title: "Published with a QR",
      body: "Approved campaigns go live and receive a unique QR for posters, stalls and social posts.",
      done: Boolean(campaign.qr_token),
      action: null,
    },
  ];

  return (
    <div className="space-y-6">
      {error && <Alert tone="critical">{error}</Alert>}

      <Card>
        <CardHeader>
          <CardTitle>Campaign lifecycle</CardTitle>
        </CardHeader>
        <CardContent>
          <ol className="space-y-5">
            {steps.map((step, index) => (
              <li key={step.title} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <span
                    className={cn(
                      "grid h-7 w-7 shrink-0 place-items-center rounded-full border text-xs font-semibold",
                      step.done
                        ? "border-brand-600 bg-brand-600 text-white"
                        : "border-surface-border text-ink-faint",
                    )}
                  >
                    {step.done ? <CheckCircle2 className="h-4 w-4" aria-hidden /> : index + 1}
                  </span>
                  {index < steps.length - 1 && <span className="mt-1 w-px flex-1 bg-surface-border" />}
                </div>
                <div className="flex-1 pb-1">
                  <p className={cn("text-sm font-medium", step.done ? "text-ink" : "text-ink-soft")}>
                    {step.title}
                  </p>
                  <p className="mt-0.5 text-sm text-ink-muted">{step.body}</p>
                  {step.action && <div className="mt-3">{step.action}</div>}
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>

      <AIAnalysisPanel
        analysis={campaign.analysis}
        showQuestions
        publicId={campaign.public_id}
        canRefresh
      />
    </div>
  );
}

function AnalyticsPanel({ publicId }: { publicId: string }) {
  const { data, isLoading, isError, refetch } = useCampaignAnalytics(publicId);

  if (isLoading) return <Skeleton className="h-72 w-full" />;
  if (isError || !data) return <ErrorState title="Could not load analytics" onRetry={() => refetch()} />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Funding over time</CardTitle>
        </CardHeader>
        <CardContent>
          <FundingChart
            series={data.funding_series}
            target={Number(data.campaign.target_amount)}
          />
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-3">
        <Stat label="Contributions" value={data.contribution_count} />
        <Stat
          label="Average contribution"
          value={formatCompactCurrency(
            data.contribution_count
              ? Number(data.campaign.raised_amount) / data.contribution_count
              : 0,
          )}
        />
        <Stat
          label="Anchored on chain"
          value={`${data.blockchain.recorded}/${data.blockchain.recorded + data.blockchain.pending}`}
          sublabel={data.blockchain.pending ? `${data.blockchain.pending} pending` : "All anchored"}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Health breakdown</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            { label: "Financial", value: data.health.financial_score },
            { label: "Community", value: data.health.community_score },
            { label: "AI signals", value: data.health.ai_score },
          ].map((row) => (
            <div key={row.label}>
              <div className="flex justify-between text-sm">
                <span className="text-ink-muted">{row.label}</span>
                <span className="font-medium tabular-nums text-ink">{row.value}</span>
              </div>
              <Progress value={row.value} className="mt-1 h-1.5" label={row.label} />
            </div>
          ))}
          <p className="pt-1 text-xs text-ink-faint">{data.health.note}</p>
        </CardContent>
      </Card>
    </div>
  );
}

function QrPanel({
  campaignId,
  publicId,
  hasQr,
  title,
}: {
  campaignId: number;
  publicId: string;
  hasQr: boolean;
  title: string;
}) {
  const { data, isLoading } = useCampaignQr(campaignId, hasQr);

  if (!hasQr) {
    return (
      <Alert tone="info" title="No QR yet">
        A unique QR is issued the moment an admin approves and publishes this campaign.
      </Alert>
    );
  }

  if (isLoading || !data) return <Skeleton className="h-72 w-full" />;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* min-w-0: the share panel below holds a nowrap URL, and a grid item
          defaults to min-width:auto — without this the column grows past a
          phone viewport instead of the URL truncating. */}
      <Card className="min-w-0 print-card">
        <CardContent className="space-y-4 p-6 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
            Scan to support
          </p>
          <h2 className="text-lg font-semibold text-ink">{title}</h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={data.qr_image_data_uri}
            alt={`QR code for campaign ${publicId}`}
            className="mx-auto h-56 w-56"
          />
          <p className="font-mono text-xs text-ink-muted">{publicId}</p>
          <p className="break-all text-xs text-ink-faint">{data.campaign_url}</p>
        </CardContent>
      </Card>

      <LocalhostQrWarning url={data.campaign_url} />

      <div className="min-w-0 no-print space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <QrCode className="h-4 w-4" aria-hidden />
              Share this campaign
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="label-text mb-1.5">Campaign URL</p>
              <div className="flex gap-2">
                <code className="flex-1 truncate rounded-lg border border-surface-border bg-surface-muted px-3 py-2 text-xs">
                  {data.campaign_url}
                </code>
                <CopyButton value={data.campaign_url} />
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <a href={`${API_URL}${data.download_url}`} download>
                <Button variant="outline" leadingIcon={<Download className="h-4 w-4" />}>
                  Download PNG
                </Button>
              </a>
              <Button variant="outline" onClick={() => window.print()} leadingIcon={<Printer className="h-4 w-4" />}>
                Print QR page
              </Button>
            </div>

            <div className="rounded-lg bg-surface-muted p-3 text-xs leading-relaxed text-ink-muted">
              <p className="font-medium text-ink">Where this QR works</p>
              <p className="mt-1">
                Posters, event stalls, presentation slides, product packaging, videos, social
                posts and direct links. It resolves to this campaign&apos;s public page on any
                device. The QR carries a link only — never money and never personal data.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TimelinePanel({ events }: { events: import("@/types").CampaignEvent[] }) {
  if (!events.length) {
    return <Alert tone="info">No events recorded yet.</Alert>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Campaign timeline</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="space-y-4">
          {events.map((event) => (
            <li key={event.id} className="flex gap-3">
              <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand-400" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">{titleCase(event.event_type)}</p>
                <p className="text-xs text-ink-faint">{formatDateTime(event.created_at)}</p>
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                  <details className="mt-1">
                    <summary className="cursor-pointer text-xs text-ink-muted hover:text-ink">
                      Details
                    </summary>
                    <pre className="mt-1 overflow-x-auto rounded bg-surface-muted p-2 text-2xs text-ink-soft">
                      {JSON.stringify(event.metadata, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}


/**
 * A QR encoding a localhost URL is unscannable by anything except this machine:
 * a phone resolves `localhost` to itself. The QR still renders — it is correct
 * for the configured FRONTEND_URL — so the failure is silent unless we say so.
 */
function LocalhostQrWarning({ url }: { url: string }) {
  let host = "";
  try {
    host = new URL(url).hostname;
  } catch {
    return null;
  }
  if (host !== "localhost" && host !== "127.0.0.1" && host !== "::1") return null;

  return (
    <Alert tone="caution" className="no-print lg:col-span-2">
      <p className="font-medium">This QR only works on this computer.</p>
      <p className="mt-1 text-sm">
        It encodes <code className="font-mono">{url}</code>, and a phone resolves{" "}
        <code className="font-mono">{host}</code> to itself. To scan it from another device, set{" "}
        <code className="font-mono">FRONTEND_URL</code> to this machine&apos;s network address
        (for example <code className="font-mono">http://192.168.1.18:3000</code>), restart the
        backend, and regenerate the QR.
      </p>
    </Alert>
  );
}
