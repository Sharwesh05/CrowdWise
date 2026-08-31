"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight, ClipboardCheck } from "lucide-react";

import {
  Badge,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  Progress,
  Select,
  Skeleton,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { formatCompactCurrency, formatDate } from "@/lib/format";
import { CAMPAIGN_STATUS_META } from "@/lib/utils";
import { useAdminCampaigns } from "@/hooks";

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "UNDER_REVIEW", label: "Under review" },
  { value: "LIVE", label: "Live" },
  { value: "GOVERNANCE", label: "In governance" },
  { value: "TARGET_MET", label: "Target met" },
  { value: "TARGET_MISSED", label: "Target missed" },
  { value: "REFUND_PENDING", label: "Refund pending" },
  { value: "REJECTED", label: "Rejected" },
  { value: "DRAFT", label: "Draft" },
];

export default function AdminCampaignsPage() {
  return (
    <RequireRole roles={["ADMIN"]}>
      <Suspense fallback={<div className="container-page py-10"><Skeleton className="h-64 w-full" /></div>}>
        <CampaignsTable />
      </Suspense>
    </RequireRole>
  );
}

function CampaignsTable() {
  const params = useSearchParams();
  const [status, setStatus] = useState(params.get("status") ?? "");
  const { data, isLoading, isError, refetch } = useAdminCampaigns(status);

  return (
    <div className="container-page py-10">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
          <p className="mt-1.5 text-ink-muted">
            Every campaign on the platform, at every stage of the lifecycle.
          </p>
        </div>
        <div className="w-full sm:w-56">
          <Select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter by status"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </div>
      </header>

      <Card>
        <CardContent className="p-0">
          {isError ? (
            <div className="p-5">
              <ErrorState title="Could not load campaigns" onRetry={() => refetch()} />
            </div>
          ) : isLoading ? (
            <div className="space-y-2 p-5">
              {Array.from({ length: 5 }).map((_, index) => (
                <Skeleton key={index} className="h-12 w-full" />
              ))}
            </div>
          ) : !data || data.items.length === 0 ? (
            <div className="p-5">
              <EmptyState
                icon={<ClipboardCheck className="h-6 w-6" />}
                title="No campaigns match that filter"
                description="Try a different status."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-surface-border text-left">
                    {["Campaign", "Creator", "Raised / target", "Progress", "Status", "Deadline", ""].map(
                      (heading) => (
                        <th
                          key={heading}
                          scope="col"
                          className="whitespace-nowrap px-4 py-3 text-xs font-medium uppercase tracking-wide text-ink-faint"
                        >
                          {heading}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {data.items.map((campaign) => {
                    const meta = CAMPAIGN_STATUS_META[campaign.status];
                    return (
                      <tr key={campaign.id} className="hover:bg-surface-subtle">
                        <td className="max-w-[260px] px-4 py-3">
                          <p className="truncate font-medium text-ink">{campaign.title}</p>
                          <p className="font-mono text-2xs text-ink-faint">{campaign.public_id}</p>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-ink-soft">{campaign.creator.name}</span>
                          {campaign.creator.is_verified && (
                            <Badge tone="positive" className="ml-2">
                              KYC
                            </Badge>
                          )}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 tabular-nums text-ink-soft">
                          {formatCompactCurrency(campaign.raised_amount)}
                          <span className="text-ink-faint">
                            {" "}
                            / {formatCompactCurrency(campaign.target_amount)}
                          </span>
                        </td>
                        <td className="w-28 px-4 py-3">
                          <Progress value={campaign.funding_percentage} className="h-1.5" />
                          <span className="mt-1 block text-2xs text-ink-muted">
                            {campaign.funding_percentage}%
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <Badge tone={meta.tone}>{meta.label}</Badge>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-ink-muted">
                          {formatDate(campaign.deadline)}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link
                            href={`/admin/campaigns/${campaign.public_id}`}
                            className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
                          >
                            Review
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
    </div>
  );
}
