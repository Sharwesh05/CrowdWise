"use client";

import Link from "next/link";
import { useState } from "react";
import {
  BadgeCheck,
  Blocks,
  CreditCard,
  ExternalLink,
  Fuel,
  HeartHandshake,
  Mail,
  Phone,
  ShieldCheck,
  Vote as VoteIcon,
  Wallet,
} from "lucide-react";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CopyButton,
  EmptyState,
  ErrorState,
  Skeleton,
  Stat,
  Tabs,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { ContributionRow } from "@/features/campaign/contribution-row";
import { useProfile } from "@/hooks";
import { formatCurrency, formatDateTime, truncateHash } from "@/lib/format";
import type { Profile, ProfileChainRecord } from "@/types";

export default function ProfilePage() {
  return (
    <RequireRole roles={["CONTRIBUTOR", "CREATOR", "ADMIN"]}>
      <ProfileView />
    </RequireRole>
  );
}

function ProfileView() {
  const { data, isLoading, isError, refetch } = useProfile();
  const [tab, setTab] = useState("payments");

  if (isError) {
    return (
      <div className="container-page py-10">
        <ErrorState title="Could not load your profile" onRetry={() => refetch()} />
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="container-page space-y-6 py-10">
        <Skeleton className="h-32 w-full" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="container-page space-y-6 py-10">
      <IdentityCard profile={data} />
      <StatsRow profile={data} />

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "payments", label: "Payments", count: data.contributions.length },
          { id: "chain", label: "Blockchain", count: data.chain_records.length },
          { id: "votes", label: "Votes", count: data.votes.length },
        ]}
      />

      {tab === "payments" && <PaymentsPanel profile={data} />}
      {tab === "chain" && <ChainPanel records={data.chain_records} />}
      {tab === "votes" && <VotesPanel profile={data} />}
    </div>
  );
}

// --------------------------------------------------------------------------
function IdentityCard({ profile }: { profile: Profile }) {
  const { user } = profile;
  const verified = user.kyc_status === "VERIFIED";

  return (
    <Card>
      <CardContent className="flex flex-wrap items-start justify-between gap-6 pt-6">
        <div className="flex items-start gap-4">
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-brand-100 text-lg font-semibold text-brand-700">
            {user.name
              .split(" ")
              .map((part) => part[0])
              .slice(0, 2)
              .join("")
              .toUpperCase()}
          </span>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-ink">{user.name}</h1>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-muted">
              <span className="inline-flex items-center gap-1.5">
                <Mail className="h-3.5 w-3.5" aria-hidden />
                {user.email}
              </span>
              {user.phone && (
                <span className="inline-flex items-center gap-1.5">
                  <Phone className="h-3.5 w-3.5" aria-hidden />
                  {user.phone}
                </span>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge tone="neutral">{user.role.toLowerCase()}</Badge>
              {user.kyc_status ? (
                <Badge tone={verified ? "positive" : "caution"}>
                  <ShieldCheck className="mr-1 h-3 w-3" aria-hidden />
                  KYC {user.kyc_status.toLowerCase()}
                </Badge>
              ) : (
                <Badge tone="neutral">KYC not started</Badge>
              )}
              {user.created_at && (
                <span className="text-xs text-ink-faint">
                  Member since {formatDateTime(user.created_at)}
                </span>
              )}
            </div>
          </div>
        </div>

        {user.wallet_address && (
          <div className="rounded-lg border border-surface-border bg-surface-subtle px-3 py-2">
            <p className="text-2xs uppercase tracking-wide text-ink-faint">Wallet</p>
            <p className="mt-0.5 inline-flex items-center gap-2 font-mono text-xs text-ink">
              <Wallet className="h-3.5 w-3.5" aria-hidden />
              {truncateHash(user.wallet_address)}
              <CopyButton value={user.wallet_address} />
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
function StatsRow({ profile }: { profile: Profile }) {
  const s = profile.stats;
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Stat
        label="Total contributed"
        value={formatCurrency(s.total_contributed)}
        sublabel={`across ${s.campaigns_supported} campaign${s.campaigns_supported === 1 ? "" : "s"}`}
        icon={<HeartHandshake className="h-4 w-4" aria-hidden />}
      />
      <Stat
        label="Payments"
        value={String(s.contributions)}
        sublabel={s.last_contribution_at ? `last ${formatDateTime(s.last_contribution_at)}` : undefined}
        icon={<CreditCard className="h-4 w-4" aria-hidden />}
      />
      <Stat
        label="Anchored on chain"
        value={`${s.anchored_on_chain}/${s.contributions}`}
        sublabel={s.awaiting_anchor > 0 ? `${s.awaiting_anchor} awaiting` : "all confirmed"}
        icon={<Blocks className="h-4 w-4" aria-hidden />}
      />
      <Stat
        label="Votes cast"
        value={String(s.votes_cast)}
        icon={<VoteIcon className="h-4 w-4" aria-hidden />}
      />
    </div>
  );
}

// --------------------------------------------------------------------------
function PaymentsPanel({ profile }: { profile: Profile }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Payments</CardTitle>
        <CardDescription>
          Every contribution with its gateway reference and blockchain record. Expand a row for
          the full trail.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {profile.contributions.length === 0 ? (
          <EmptyState
            icon={<HeartHandshake className="h-6 w-6" />}
            title="No payments yet"
            description="Back a campaign and its full record appears here."
            action={
              <Link href="/campaigns">
                <Button size="sm">Explore campaigns</Button>
              </Link>
            }
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {profile.contributions.map((contribution) => (
              <ContributionRow key={contribution.id} contribution={contribution} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
function ChainPanel({ records }: { records: ProfileChainRecord[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Blocks written for you</CardTitle>
        <CardDescription>
          Each row is one transaction this account caused. Only opaque references are anchored —
          amounts and salted hashes, never your name, email or payment id.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {records.length === 0 ? (
          <EmptyState
            icon={<Blocks className="h-6 w-6" />}
            title="Nothing anchored yet"
            description="Contributions and votes are written to the chain once their payment is verified."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] text-sm">
              <thead>
                <tr className="border-b border-surface-border text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="pb-2 pr-4 font-medium">Type</th>
                  <th className="pb-2 pr-4 font-medium">Campaign</th>
                  <th className="pb-2 pr-4 font-medium">Block</th>
                  <th className="pb-2 pr-4 font-medium">Transaction</th>
                  <th className="pb-2 pr-4 font-medium">Gas</th>
                  <th className="pb-2 font-medium">Recorded</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {records.map((record) => (
                  <tr key={record.id}>
                    <td className="py-3 pr-4">
                      <Badge tone={record.record_type === "VOTE" ? "info" : "positive"}>
                        {record.record_type.toLowerCase().replace(/_/g, " ")}
                      </Badge>
                      {record.simulated && (
                        <Badge tone="neutral" className="ml-1.5">
                          simulated
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      {record.campaign_public_id ? (
                        <Link
                          href={`/campaign/${record.campaign_public_id}`}
                          className="text-ink hover:underline"
                        >
                          {record.campaign_public_id}
                        </Link>
                      ) : (
                        <span className="text-ink-faint">—</span>
                      )}
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-ink">
                      {record.block_number ?? <span className="text-ink-faint">pending</span>}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="inline-flex items-center gap-1.5 font-mono text-xs text-ink-muted">
                        {truncateHash(record.tx_hash)}
                        <CopyButton value={record.tx_hash} />
                        {record.explorer_url && (
                          <a
                            href={record.explorer_url}
                            target="_blank"
                            rel="noreferrer"
                            className="text-brand-600 hover:text-brand-700"
                            aria-label="View on block explorer"
                          >
                            <ExternalLink className="h-3.5 w-3.5" aria-hidden />
                          </a>
                        )}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-xs text-ink-muted">
                      {record.gas_used ? (
                        <span className="inline-flex items-center gap-1">
                          <Fuel className="h-3 w-3" aria-hidden />
                          {record.gas_used.toLocaleString()}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 text-xs text-ink-muted">
                      {formatDateTime(record.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
function VotesPanel({ profile }: { profile: Profile }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Governance votes</CardTitle>
        <CardDescription>
          Your vote is anchored under a salted, campaign-scoped reference, so it cannot be traced
          back to you or correlated across campaigns.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {profile.votes.length === 0 ? (
          <EmptyState
            icon={<VoteIcon className="h-6 w-6" />}
            title="No votes cast yet"
            description="When a campaign you backed misses its target, you decide what happens to the money."
          />
        ) : (
          <ul className="divide-y divide-surface-border">
            {profile.votes.map((vote) => (
              <li key={vote.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <Link
                    href={`/campaign/${vote.campaign_public_id}`}
                    className="text-sm font-medium text-ink hover:underline"
                  >
                    {vote.campaign_title ?? vote.campaign_public_id}
                  </Link>
                  <p className="mt-0.5 text-xs text-ink-faint">
                    {formatDateTime(vote.created_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={vote.choice === "CONTINUE" ? "positive" : "caution"}>
                    <BadgeCheck className="mr-1 h-3 w-3" aria-hidden />
                    {vote.choice.toLowerCase()}
                  </Badge>
                  <span className="text-xs text-ink-muted">
                    weight {formatCurrency(vote.weight)}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
