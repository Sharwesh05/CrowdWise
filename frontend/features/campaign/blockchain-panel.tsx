"use client";

import { Blocks, ExternalLink, ShieldCheck } from "lucide-react";

import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
} from "@/components/ui";
import { formatRelative, truncateHash } from "@/lib/format";
import { titleCase } from "@/lib/format";
import { useCampaignBlockchain } from "@/hooks";
import type { BlockchainSummary } from "@/types";

const RECORD_LABELS: Record<string, string> = {
  CAMPAIGN_REGISTERED: "Campaign registered",
  CONTRIBUTION: "Contribution recorded",
  VOTING_OPENED: "Voting opened",
  VOTE: "Vote recorded",
  VOTING_CLOSED: "Voting closed",
  OUTCOME: "Outcome recorded",
};

export function BlockchainPanel({
  publicId,
  summary,
}: {
  publicId: string;
  summary: BlockchainSummary | null;
}) {
  const { data: records, isLoading } = useCampaignBlockchain(publicId);

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Blocks className="h-4 w-4 text-accent-600" aria-hidden />
            Blockchain verification
          </CardTitle>
          <p className="mt-1 text-sm text-ink-muted">
            {summary?.recorded ?? 0} record{summary?.recorded === 1 ? "" : "s"} anchored
            {summary?.pending ? ` · ${summary.pending} pending` : ""}
          </p>
        </div>
        {summary?.simulated && <Badge tone="caution">Simulated chain</Badge>}
      </CardHeader>

      <CardContent className="space-y-4">
        <dl className="grid gap-3 rounded-lg bg-surface-muted p-3 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-ink-faint">Network</dt>
            <dd className="mt-0.5 font-medium text-ink">{summary?.network ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-ink-faint">Contract</dt>
            <dd className="mt-0.5 break-all font-mono text-ink-soft">
              {summary?.contract_address ?? "—"}
            </dd>
          </div>
        </dl>

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : !records || records.length === 0 ? (
          <EmptyState
            title="Nothing anchored yet"
            description="Records appear here as contributions and governance events are written on chain."
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {records.slice(0, 8).map((record) => (
              <li key={record.id} className="flex items-start justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">
                    {RECORD_LABELS[record.record_type] ?? titleCase(record.record_type)}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-xs text-ink-muted">
                    {truncateHash(record.tx_hash, 14, 10)}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs text-ink-muted">
                    {record.block_number ? `Block ${record.block_number}` : record.status}
                  </p>
                  <p className="text-2xs text-ink-faint">{formatRelative(record.created_at)}</p>
                  {record.explorer_url && (
                    <a
                      href={record.explorer_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="mt-0.5 inline-flex items-center gap-1 text-2xs text-brand-700 hover:underline"
                    >
                      Explorer
                      <ExternalLink className="h-2.5 w-2.5" aria-hidden />
                    </a>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        <p className="flex items-start gap-2 text-xs leading-relaxed text-ink-faint">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          Only hashes, amounts and timestamps are written on chain. Names, contact details,
          identity documents and raw payment identifiers stay in the database and are never
          published. The blockchain does not hold funds.
        </p>
      </CardContent>
    </Card>
  );
}
