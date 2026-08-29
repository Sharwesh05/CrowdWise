"use client";

import Link from "next/link";
import {
  AlertTriangle,
  Blocks,
  ClipboardCheck,
  Layers,
  ShieldCheck,
  Users,
} from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ErrorState,
  Skeleton,
  Stat,
} from "@/components/ui";
import { RequireRole } from "@/components/layout/require-role";
import { DemoControls } from "@/features/admin/demo-controls";
import { formatCompactCurrency, formatNumber, titleCase, formatDateTime } from "@/lib/format";
import { useAdminDashboard, useAuditLogs, useChainStatus } from "@/hooks";

export default function AdminDashboardPage() {
  return (
    <RequireRole roles={["ADMIN"]}>
      <AdminDashboardContent />
    </RequireRole>
  );
}

function AdminDashboardContent() {
  const { data, isLoading, isError, refetch } = useAdminDashboard();
  const { data: chain } = useChainStatus();
  const { data: logs } = useAuditLogs();

  if (isError) {
    return (
      <div className="container-page py-10">
        <ErrorState title="Could not load the admin dashboard" onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="container-page py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Platform overview</h1>
          <p className="mt-1.5 text-ink-muted">
            Review queue, platform health and the audit trail.
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/admin/campaigns">
            <Button variant="outline">All campaigns</Button>
          </Link>
          {data && data.pending_reviews > 0 && (
            <Link href="/admin/campaigns?status=UNDER_REVIEW">
              <Button leadingIcon={<ClipboardCheck className="h-4 w-4" />}>
                Review {data.pending_reviews} pending
              </Button>
            </Link>
          )}
        </div>
      </header>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, index) => (
            <Skeleton key={index} className="h-28 w-full" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Total campaigns"
              value={formatNumber(data!.total_campaigns)}
              sublabel={`${data!.active_campaigns} active · ${data!.completed_campaigns} completed`}
              icon={<Layers className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Pending review"
              value={formatNumber(data!.pending_reviews)}
              sublabel={data!.pending_reviews ? "Awaiting your decision" : "Queue is clear"}
              tone={data!.pending_reviews ? "text-caution-strong" : undefined}
              icon={<ClipboardCheck className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Total contributions"
              value={formatCompactCurrency(data!.total_contributions_amount)}
              sublabel={`${formatNumber(data!.total_contributions_count)} verified payments`}
            />
            <Stat
              label="People"
              value={formatNumber(data!.total_contributors + data!.total_creators)}
              sublabel={`${data!.total_creators} creators · ${data!.total_contributors} contributors`}
              icon={<Users className="h-4 w-4" aria-hidden />}
            />
          </div>

          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Governance rounds"
              value={formatNumber(data!.governance_campaigns)}
              sublabel="Contributor votes open"
            />
            <Stat
              label="Failed payments"
              value={formatNumber(data!.failed_payments)}
              tone={data!.failed_payments ? "text-critical-strong" : undefined}
              sublabel={`${data!.unverified_payments} captured without a webhook`}
              icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="Chain pending"
              value={formatNumber(data!.blockchain_pending)}
              sublabel={`${data!.blockchain_failed} failed and retryable`}
              tone={data!.blockchain_failed ? "text-caution-strong" : undefined}
              icon={<Blocks className="h-4 w-4" aria-hidden />}
            />
            <Stat
              label="KYC verified"
              value={formatNumber(data!.kyc_summary.VERIFIED ?? 0)}
              sublabel={`${data!.kyc_summary.PROCESSING ?? 0} processing · ${data!.kyc_summary.SUBMITTED ?? 0} submitted`}
              icon={<ShieldCheck className="h-4 w-4" aria-hidden />}
            />
          </div>

          {data!.unverified_payments > 0 && (
            <Alert tone="caution" className="mt-6" title="Payments captured without a webhook">
              {data!.unverified_payments} payment
              {data!.unverified_payments === 1 ? " was" : "s were"} verified from the client
              callback signature but have not been confirmed by a Razorpay webhook. This is
              expected in demo mode; in production it is worth investigating.
            </Alert>
          )}

          <div className="mt-6 grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <Card>
                <CardHeader>
                  <CardTitle>Recent audit log</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  {!logs || logs.items.length === 0 ? (
                    <p className="p-5 text-sm text-ink-muted">No audit entries yet.</p>
                  ) : (
                    <ul className="max-h-[28rem] divide-y divide-surface-border overflow-y-auto">
                      {logs.items.slice(0, 40).map((log) => (
                        <li key={log.id} className="flex items-start justify-between gap-3 px-5 py-2.5">
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-ink">{titleCase(log.action)}</p>
                            <p className="text-xs text-ink-faint">
                              {log.entity_type ? `${log.entity_type} ${log.entity_id ?? ""}` : "—"}
                              {log.actor_id ? ` · actor #${log.actor_id}` : ""}
                            </p>
                          </div>
                          <span className="shrink-0 text-xs text-ink-faint">
                            {formatDateTime(log.created_at)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Blocks className="h-4 w-4" aria-hidden />
                    Blockchain
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {chain ? (
                    <>
                      <Row label="Provider" value={chain.provider} />
                      <Row label="Network" value={chain.network} />
                      <Row label="Records" value={formatNumber(chain.records_total)} />
                      <Row label="Pending" value={formatNumber(chain.pending_records)} />
                      {chain.contract_address && (
                        <div>
                          <p className="text-ink-muted">Contract</p>
                          <p className="break-all font-mono text-xs text-ink-soft">
                            {chain.contract_address}
                          </p>
                        </div>
                      )}
                      {chain.simulated && <Badge tone="caution">Simulated ledger</Badge>}
                      <p className="pt-1 text-xs text-ink-faint">{chain.note}</p>
                    </>
                  ) : (
                    <Skeleton className="h-24 w-full" />
                  )}
                </CardContent>
              </Card>

              {data!.demo_mode && <DemoControls />}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-muted">{label}</span>
      <span className="font-medium text-ink">{value}</span>
    </div>
  );
}
