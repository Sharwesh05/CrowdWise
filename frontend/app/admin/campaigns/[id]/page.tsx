"use client";

import Link from "next/link";
import { useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  BadgeCheck,
  CheckCircle2,
  CreditCard,
  FileText,
  XCircle,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Dialog,
  ErrorState,
  Skeleton,
  Textarea,
  useToast,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { AIAnalysisPanel } from "@/features/campaign/ai-analysis-panel";
import { ApiError } from "@/lib/api";
import { formatCompactCurrency, formatDateTime } from "@/lib/format";
import { CAMPAIGN_STATUS_META } from "@/lib/utils";
import { useAdminDecision, useAdminReview } from "@/hooks";

type Decision = "approve" | "reject" | "request_changes" | null;

export default function AdminReviewPage({ params }: { params: { id: string } }) {
  const { id } = params;
  return (
    <RequireRole roles={["ADMIN"]}>
      <ReviewContent publicId={id} />
    </RequireRole>
  );
}

function ReviewContent({ publicId }: { publicId: string }) {
  const { data, isLoading, isError, refetch } = useAdminReview(publicId);
  const { approve, reject, requestChanges } = useAdminDecision(publicId);
  const { notify } = useToast();

  const [decision, setDecision] = useState<Decision>(null);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="container-page space-y-4 py-10">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="container-page py-10">
        <ErrorState title="Could not load this campaign" onRetry={() => refetch()} />
      </div>
    );
  }

  const status = CAMPAIGN_STATUS_META[data.campaign.status];
  const canDecide = data.allowed_actions.length > 0;
  const pending = approve.isPending || reject.isPending || requestChanges.isPending;

  const submitDecision = async () => {
    setError(null);
    try {
      if (decision === "approve") {
        await approve.mutateAsync(notes.trim() || undefined);
        notify({ title: "Campaign approved and published", tone: "positive" });
      } else if (decision === "reject") {
        await reject.mutateAsync(notes.trim());
        notify({ title: "Campaign rejected", tone: "info" });
      } else if (decision === "request_changes") {
        await requestChanges.mutateAsync(notes.trim());
        notify({ title: "Changes requested", tone: "info" });
      }
      setDecision(null);
      setNotes("");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not record the decision.");
    }
  };

  const needsReason = decision === "reject" || decision === "request_changes";
  const reasonValid = !needsReason || notes.trim().length >= 10;

  return (
    <div className="container-page py-10">
      <Link
        href="/admin/campaigns"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden />
        Back to campaigns
      </Link>

      <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-ink-faint">{data.campaign.public_id}</span>
            <Badge tone={status.tone} dot>
              {status.label}
            </Badge>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{data.campaign.title}</h1>
          <p className="mt-1 text-sm text-ink-muted">{data.campaign.short_description}</p>
        </div>

        {canDecide && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="danger"
              leadingIcon={<XCircle className="h-4 w-4" />}
              onClick={() => setDecision("reject")}
            >
              Reject
            </Button>
            <Button
              variant="outline"
              leadingIcon={<AlertTriangle className="h-4 w-4" />}
              onClick={() => setDecision("request_changes")}
            >
              Request changes
            </Button>
            <Button
              leadingIcon={<CheckCircle2 className="h-4 w-4" />}
              onClick={() => setDecision("approve")}
            >
              Approve and publish
            </Button>
          </div>
        )}
      </header>

      {!canDecide && (
        <Alert tone="info" className="mt-5">
          This campaign is {status.label.toLowerCase()} and is not awaiting a decision.
          {data.review_notes ? ` Previous note: ${data.review_notes}` : ""}
        </Alert>
      )}

      {/* Gate checks — the things that must be true before approval */}
      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <GateCard
          title="Identity verification"
          ok={data.creator.kyc_status === "VERIFIED"}
          detail={
            data.creator.kyc_status === "VERIFIED"
              ? `Verified ${formatDateTime(data.creator.kyc_verified_at)}`
              : `Status: ${data.creator.kyc_status.replace("_", " ").toLowerCase()}`
          }
          icon={<BadgeCheck className="h-4 w-4" aria-hidden />}
        />
        <GateCard
          title="₹500 application fee"
          ok={data.application_fee_paid}
          detail={
            data.application_fee_paid
              ? data.application_fee_webhook_verified
                ? "Verified, confirmed by webhook"
                : "Verified server-side (no webhook yet)"
              : "Not paid"
          }
          icon={<CreditCard className="h-4 w-4" aria-hidden />}
        />
        <GateCard
          title="AI analysis"
          ok={Boolean(data.analysis)}
          detail={
            data.analysis
              ? `${data.analysis.risk_level} risk · feasibility ${data.analysis.feasibility_score}`
              : "Not generated"
          }
          icon={<FileText className="h-4 w-4" aria-hidden />}
        />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {data.risk_indicators.length > 0 && (
            <Card className="border-caution/30">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-caution-strong" aria-hidden />
                  Risk indicators
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {data.risk_indicators.map((indicator, index) => (
                    <li key={index} className="flex gap-2 text-sm text-ink-soft">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-caution" />
                      {indicator}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          <AIAnalysisPanel analysis={data.analysis} showQuestions />

          <Card>
            <CardHeader>
              <CardTitle>Proposal</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <Section title="Problem" body={data.problem_statement} />
              <Section title="Proposed solution" body={data.proposed_solution} />
              {data.expected_impact && <Section title="Expected impact" body={data.expected_impact} />}
              <Section title="Full description" body={data.description} />
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Creator</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Name" value={data.creator.name} />
              <Row label="Email" value={data.creator.email} />
              <Row label="Phone" value={data.creator.phone ?? "—"} />
              <Row label="KYC status" value={data.creator.kyc_status} />
              <Row label="KYC reference" value={data.creator.kyc_reference ?? "—"} mono />
              <Row label="Campaigns" value={String(data.creator.campaigns_created)} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Funding request</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <Row label="Target" value={formatCompactCurrency(data.campaign.target_amount)} />
              <Row
                label="Minimum contribution"
                value={formatCompactCurrency(data.campaign.minimum_contribution)}
              />
              <Row label="Deadline" value={formatDateTime(data.campaign.deadline)} />
              <Row label="Days" value={String(data.campaign.days_remaining)} />
              <Row label="Category" value={data.campaign.category} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Documents</CardTitle>
            </CardHeader>
            <CardContent>
              {data.documents.length === 0 ? (
                <p className="text-sm text-ink-muted">No supporting documents uploaded.</p>
              ) : (
                <ul className="space-y-2">
                  {data.documents.map((document) => (
                    <li key={document.id}>
                      <a
                        href={document.url ?? "#"}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="flex items-center gap-2 text-sm text-brand-700 hover:underline"
                      >
                        <FileText className="h-4 w-4" aria-hidden />
                        {document.file_name}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {data.recommended_questions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Questions to ask</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {data.recommended_questions.map((question, index) => (
                    <li key={index} className="text-sm text-ink-soft">
                      {index + 1}. {question}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>

      <Dialog
        open={decision !== null}
        onClose={() => setDecision(null)}
        title={
          decision === "approve"
            ? "Approve and publish this campaign"
            : decision === "reject"
              ? "Reject this campaign"
              : "Request changes"
        }
        description={
          decision === "approve"
            ? "The campaign goes live immediately, receives its QR, and its outcome rules are locked."
            : decision === "reject"
              ? "The creator will see your reason. This cannot be undone."
              : "The campaign returns to draft so the creator can revise it. The application fee is not charged again."
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setDecision(null)}>
              Cancel
            </Button>
            <Button
              variant={decision === "reject" ? "danger" : "primary"}
              loading={pending}
              disabled={!reasonValid}
              onClick={submitDecision}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          {error && <Alert tone="critical">{error}</Alert>}
          <Textarea
            rows={4}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder={
              decision === "approve"
                ? "Optional note for the creator."
                : "Explain your decision (at least 10 characters)."
            }
            aria-label="Reviewer notes"
          />
          {needsReason && notes.trim().length > 0 && notes.trim().length < 10 && (
            <p className="text-xs text-critical">Please write at least 10 characters.</p>
          )}
        </div>
      </Dialog>
    </div>
  );
}

function GateCard({
  title,
  ok,
  detail,
  icon,
}: {
  title: string;
  ok: boolean;
  detail: string;
  icon: React.ReactNode;
}) {
  return (
    <div
      className={`card p-4 ${ok ? "border-positive/30 bg-positive-soft/20" : "border-caution/30 bg-caution-soft/20"}`}
    >
      <div className="flex items-center gap-2">
        <span className={ok ? "text-positive-strong" : "text-caution-strong"}>{icon}</span>
        <p className="text-sm font-medium text-ink">{title}</p>
      </div>
      <p className="mt-1.5 text-xs text-ink-muted">{detail}</p>
      <Badge tone={ok ? "positive" : "caution"} className="mt-2">
        {ok ? "Passed" : "Not met"}
      </Badge>
    </div>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h4 className="text-sm font-medium text-ink">{title}</h4>
      <div className="prose-campaign mt-1.5">
        {body.split("\n\n").map((paragraph, index) => (
          <p key={index} className="text-sm">
            {paragraph}
          </p>
        ))}
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="shrink-0 text-ink-muted">{label}</span>
      <span className={`text-right text-ink ${mono ? "break-all font-mono text-xs" : ""}`}>
        {value}
      </span>
    </div>
  );
}
