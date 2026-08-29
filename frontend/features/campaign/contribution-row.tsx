"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown, RefreshCw } from "lucide-react";

import { Badge, Button, useToast } from "@/components/ui";
import { formatCurrency, formatDateTime, truncateHash } from "@/lib/format";
import { CONTRIBUTION_STATUS_META, cn } from "@/lib/utils";
import { useRetryBlockchain } from "@/hooks";
import type { Contribution } from "@/types";

export function ContributionRow({ contribution }: { contribution: Contribution }) {
  const [expanded, setExpanded] = useState(false);
  const retry = useRetryBlockchain();
  const { notify } = useToast();

  const meta = CONTRIBUTION_STATUS_META[contribution.status];
  const canRetry = contribution.status === "BLOCKCHAIN_FAILED";

  const handleRetry = async () => {
    const result = await retry.mutateAsync(contribution.id);
    notify({
      title: result.recorded ? "Anchored on chain" : "Retry queued",
      description: result.recorded
        ? "The blockchain record is now confirmed."
        : "We will keep trying. Your payment is unaffected.",
      tone: result.recorded ? "positive" : "info",
    });
  };

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1">
          <Link
            href={`/campaign/${contribution.campaign_public_id}`}
            className="truncate text-sm font-medium text-ink hover:underline"
          >
            {contribution.campaign_title ?? contribution.campaign_public_id}
          </Link>
          <p className="mt-0.5 text-xs text-ink-faint">
            {formatDateTime(contribution.created_at)}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold tabular-nums text-ink">
            {formatCurrency(contribution.amount)}
          </span>
          <Badge tone={meta.tone}>{meta.label}</Badge>
          <button
            type="button"
            onClick={() => setExpanded((open) => !open)}
            aria-expanded={expanded}
            aria-label={expanded ? "Hide details" : "Show details"}
            className="rounded p-1 text-ink-faint hover:bg-surface-muted hover:text-ink"
          >
            <ChevronDown
              className={cn("h-4 w-4 transition-transform", expanded && "rotate-180")}
              aria-hidden
            />
          </button>
        </div>
      </div>

      {expanded && (
        <dl className="mt-3 grid animate-fade-in gap-x-6 gap-y-2 rounded-lg bg-surface-muted p-3 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-ink-faint">Payment status</dt>
            <dd className="mt-0.5 font-medium text-ink">
              {contribution.payment?.status ?? "—"}
              {contribution.payment?.webhook_verified && (
                <span className="ml-1.5 text-positive-strong">· webhook verified</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">Razorpay payment id</dt>
            <dd className="mt-0.5 break-all font-mono text-ink-soft">
              {contribution.payment?.razorpay_payment_id ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">Blockchain transaction</dt>
            <dd className="mt-0.5 break-all font-mono text-ink-soft">
              {contribution.blockchain_tx ? truncateHash(contribution.blockchain_tx, 18, 12) : "Pending"}
            </dd>
          </div>
          <div>
            <dt className="text-ink-faint">Network</dt>
            <dd className="mt-0.5 text-ink-soft">
              {contribution.blockchain_record?.network ?? "—"}
              {contribution.blockchain_record?.block_number
                ? ` · block ${contribution.blockchain_record.block_number}`
                : ""}
            </dd>
          </div>

          {canRetry && (
            <div className="sm:col-span-2">
              <p className="text-ink-muted">
                The payment is verified and counted. Only the blockchain record failed.
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-2"
                loading={retry.isPending}
                onClick={handleRetry}
                leadingIcon={<RefreshCw className="h-3.5 w-3.5" />}
              >
                Retry blockchain record
              </Button>
            </div>
          )}
        </dl>
      )}
    </li>
  );
}
