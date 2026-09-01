"use client";

import Link from "next/link";
import { ArrowRight, CreditCard } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { CAMPAIGN_STATUS_META } from "@/lib/utils";
import { useKycStatus, useMyCampaigns } from "@/hooks";

/** One view of where every application stands, and which gate it is waiting on. */
export default function ApplicationPage() {
  return (
    <RequireRole roles={["CREATOR", "ADMIN"]}>
      <ApplicationStatus />
    </RequireRole>
  );
}

function ApplicationStatus() {
  const { data: campaigns, isLoading } = useMyCampaigns();
  const { data: kyc } = useKycStatus();

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Your applications</h1>
        <p className="mt-1.5 text-ink-muted">
          Every campaign application and exactly which gate it is waiting on.
        </p>
      </header>

      {kyc && (
        <Alert tone={kyc.status === "VERIFIED" ? "positive" : "caution"} className="mb-6">
          Identity verification: <strong>{kyc.status.replace("_", " ").toLowerCase()}</strong>.
          {kyc.status !== "VERIFIED" && (
            <>
              {" "}
              <Link href="/creator/kyc" className="font-medium underline">
                Complete verification
              </Link>{" "}
              before submitting a campaign.
            </>
          )}
        </Alert>
      )}

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : !campaigns || campaigns.length === 0 ? (
        <EmptyState
          icon={<CreditCard className="h-6 w-6" />}
          title="No applications yet"
          description="Create a campaign to start the application process."
          action={
            <Link href="/creator/campaigns/new">
              <Button size="sm">Create a campaign</Button>
            </Link>
          }
        />
      ) : (
        <div className="space-y-4">
          {campaigns.map((campaign) => {
            const status = CAMPAIGN_STATUS_META[campaign.status];
            return (
              <Card key={campaign.id}>
                <CardHeader className="flex-row items-start justify-between gap-3">
                  <div>
                    <CardTitle>{campaign.title}</CardTitle>
                    <p className="mt-1 font-mono text-xs text-ink-faint">{campaign.public_id}</p>
                  </div>
                  <Badge tone={status.tone} dot>
                    {status.label}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-ink-muted">{status.description}</p>
                  <dl className="grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <dt className="text-xs text-ink-faint">Application fee</dt>
                      <dd className="mt-0.5 font-medium text-ink">
                        {campaign.application
                          ? campaign.application.status.replace(/_/g, " ").toLowerCase()
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-ink-faint">Approval</dt>
                      <dd className="mt-0.5 font-medium text-ink">
                        {campaign.approval_status.replace(/_/g, " ").toLowerCase()}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs text-ink-faint">AI analysis</dt>
                      <dd className="mt-0.5 font-medium text-ink">
                        {campaign.analysis ? `${campaign.analysis.risk_level} risk` : "Not run"}
                      </dd>
                    </div>
                  </dl>
                  {campaign.review_notes && (
                    <Alert tone="caution" title="Reviewer notes">
                      {campaign.review_notes}
                    </Alert>
                  )}
                  <Link
                    href={`/creator/campaigns/${campaign.id}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
                  >
                    Manage this application
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden />
                  </Link>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
