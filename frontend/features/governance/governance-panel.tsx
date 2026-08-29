"use client";

import { useState } from "react";
import { Scale, ShieldCheck, Users, Vote as VoteIcon } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Progress,
  Skeleton,
  useToast,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { formatCurrency, formatTimeRemaining, truncateHash } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useCastVote, useCloseGovernance, useGovernance, useSession } from "@/hooks";
import type { VoteChoice } from "@/types";

const CHOICE_COPY: Record<VoteChoice, { title: string; body: string; tone: string }> = {
  REFUND: {
    title: "Refund contributors",
    body: "Return the money raised. Refunds are processed by payment infrastructure.",
    tone: "border-critical/30 bg-critical-soft/40",
  },
  CONTINUE: {
    title: "Continue the campaign",
    body: "Extend the funding window and let the campaign keep raising toward its target.",
    tone: "border-positive/30 bg-positive-soft/40",
  },
};

export function GovernancePanel({ publicId }: { publicId: string }) {
  const { data: user } = useSession();
  const { data, isLoading } = useGovernance(publicId);
  const castVote = useCastVote(publicId);
  const closeRound = useCloseGovernance(publicId);
  const { notify } = useToast();
  const [error, setError] = useState<string | null>(null);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Contributor governance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-16 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!data || data.campaign_status === "LIVE" || data.status === "NOT_APPLICABLE") {
    return null;
  }

  const viewer = data.viewer;
  const canVote = data.is_open && viewer?.is_eligible && !viewer?.has_voted;

  const submitVote = async (choice: VoteChoice) => {
    setError(null);
    try {
      await castVote.mutateAsync(choice);
      notify({ title: "Vote recorded", description: "Your vote was anchored on chain.", tone: "positive" });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not record your vote.");
    }
  };

  return (
    <Card className="border-accent-300/40">
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Scale className="h-4 w-4 text-accent-600" aria-hidden />
              Contributor governance
            </CardTitle>
            <p className="mt-1 text-sm text-ink-muted">
              This campaign closed at {formatCurrency(data.raised_amount)} of{" "}
              {formatCurrency(data.target_amount)} — {formatCurrency(data.shortfall)} short.
              Contributors decide what happens next.
            </p>
          </div>
          <Badge tone={data.is_open ? "info" : "neutral"} dot>
            {data.is_open ? "Voting open" : "Voting closed"}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {error && <Alert tone="critical">{error}</Alert>}

        <div className="grid grid-cols-3 gap-3 rounded-lg bg-surface-muted p-3 text-center">
          <div>
            <p className="text-lg font-semibold tabular-nums text-ink">{data.votes_cast}</p>
            <p className="text-2xs uppercase tracking-wide text-ink-faint">Votes cast</p>
          </div>
          <div>
            <p className="text-lg font-semibold tabular-nums text-ink">
              {data.total_eligible_voters}
            </p>
            <p className="text-2xs uppercase tracking-wide text-ink-faint">Eligible</p>
          </div>
          <div>
            <p className="text-lg font-semibold tabular-nums text-ink">
              {data.participation_percentage}%
            </p>
            <p className="text-2xs uppercase tracking-wide text-ink-faint">Participation</p>
          </div>
        </div>

        {/* Results */}
        <div className="space-y-3">
          {data.options.map((option) => {
            const result = data.results[option] ?? { votes: 0, weight: 0, percentage: 0 };
            const isLeading = data.leading_choice === option;
            return (
              <div key={option}>
                <div className="flex items-baseline justify-between">
                  <span className="flex items-center gap-2 text-sm font-medium text-ink">
                    {CHOICE_COPY[option].title}
                    {isLeading && data.votes_cast > 0 && <Badge tone="brand">Leading</Badge>}
                  </span>
                  <span className="text-sm font-semibold tabular-nums text-ink">
                    {result.percentage}%
                    <span className="ml-1.5 text-xs font-normal text-ink-muted">
                      ({result.votes} vote{result.votes === 1 ? "" : "s"})
                    </span>
                  </span>
                </div>
                <Progress
                  value={result.percentage}
                  className="mt-1.5"
                  barClassName={option === "REFUND" ? "bg-critical" : "bg-positive"}
                  label={`${CHOICE_COPY[option].title}: ${result.percentage}%`}
                />
              </div>
            );
          })}
        </div>

        {data.closes_at && data.is_open && (
          <p className="text-sm text-ink-muted">
            Voting closes {formatTimeRemaining(data.closes_at)}.
          </p>
        )}

        {/* Voting */}
        {canVote ? (
          <div className="space-y-3 border-t border-surface-border pt-4">
            <p className="text-sm font-medium text-ink">Cast your vote</p>
            <div className="grid gap-3 sm:grid-cols-2">
              {data.options.map((option) => (
                <button
                  key={option}
                  type="button"
                  disabled={castVote.isPending}
                  onClick={() => submitVote(option)}
                  className={cn(
                    "rounded-lg border p-4 text-left transition-all hover:shadow-lift disabled:opacity-60",
                    CHOICE_COPY[option].tone,
                  )}
                >
                  <span className="flex items-center gap-2 text-sm font-semibold text-ink">
                    <VoteIcon className="h-4 w-4" aria-hidden />
                    {CHOICE_COPY[option].title}
                  </span>
                  <span className="mt-1.5 block text-xs leading-relaxed text-ink-muted">
                    {CHOICE_COPY[option].body}
                  </span>
                </button>
              ))}
            </div>
            <p className="text-xs text-ink-faint">
              One vote per contributor. Your vote is recorded in the database and anchored on
              chain, and it cannot be changed.
            </p>
          </div>
        ) : viewer?.has_voted ? (
          <Alert tone="positive" title={`You voted: ${CHOICE_COPY[viewer.vote?.choice as VoteChoice]?.title ?? viewer.vote?.choice}`}>
            {viewer.vote?.blockchain_tx ? (
              <span className="font-mono text-xs">
                Anchored as {truncateHash(viewer.vote.blockchain_tx, 12, 8)}
              </span>
            ) : (
              "Your vote is recorded. The blockchain anchor is pending."
            )}
          </Alert>
        ) : !user ? (
          <Alert tone="info">Sign in as a contributor to this campaign to vote.</Alert>
        ) : !viewer?.is_eligible ? (
          <Alert tone="info" title="Not eligible to vote">
            Only contributors with at least one verified contribution to this campaign can vote.
            This rule was fixed before funding opened.
          </Alert>
        ) : null}

        {/* Outcome */}
        {data.selected_outcome && (
          <Alert tone="caution" title={`Outcome: ${CHOICE_COPY[data.selected_outcome as VoteChoice]?.title ?? data.selected_outcome}`}>
            {data.selected_outcome === "REFUND"
              ? "Refunds are being processed through payment infrastructure. The blockchain records the decision, not the money."
              : "The campaign has been continued with an extended funding window."}
          </Alert>
        )}

        {/* Admin close */}
        {user?.role === "ADMIN" && data.is_open && (
          <div className="border-t border-surface-border pt-4">
            <Button
              variant="outline"
              size="sm"
              loading={closeRound.isPending}
              onClick={() => closeRound.mutate()}
            >
              Close voting and apply the outcome
            </Button>
          </div>
        )}

        <p className="flex items-start gap-2 text-xs leading-relaxed text-ink-faint">
          <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {data.note}
        </p>

        {data.blockchain_records.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-ink-muted hover:text-ink">
              Governance records on chain ({data.blockchain_records.length})
            </summary>
            <ul className="mt-2 space-y-1">
              {data.blockchain_records.map((record) => (
                <li key={record.id} className="flex items-center justify-between gap-2">
                  <span className="text-ink-muted">{record.record_type}</span>
                  <span className="font-mono text-ink-faint">{truncateHash(record.tx_hash)}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}

export function EligibleVotersHint({ count }: { count: number }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-ink-muted">
      <Users className="h-3.5 w-3.5" aria-hidden />
      {count} eligible voter{count === 1 ? "" : "s"}
    </p>
  );
}
