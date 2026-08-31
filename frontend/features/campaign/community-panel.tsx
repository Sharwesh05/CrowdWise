"use client";

import { useState } from "react";
import { MessagesSquare, RefreshCw, Sparkles } from "lucide-react";
import {
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  Skeleton,
  StarRating,
  useToast,
} from "@/components/ui";
import { formatDateTime, formatRelative } from "@/lib/format";
import { SENTIMENT_META, cn } from "@/lib/utils";
import {
  useCampaignFeedback,
  useCommunityInsights,
  useRefreshInsights,
  useRefreshSentiment,
} from "@/hooks";
import type { CommunityInsight, SentimentSummary } from "@/types";

const SENTIMENT_COLORS = {
  positive: "#16A34A",
  neutral: "#94A3B8",
  negative: "#DC2626",
};

export function SentimentPanel({
  sentiment,
  publicId,
  canRefresh = false,
}: {
  sentiment: SentimentSummary | null;
  /** Required for the refresh control; without it the button is not rendered. */
  publicId?: string;
  canRefresh?: boolean;
}) {
  const refresh = useRefreshSentiment(publicId ?? "");
  const { notify } = useToast();

  const handleRefresh = async () => {
    try {
      const result = await refresh.mutateAsync();
      const outstanding = result.feedback_count - result.analyzed_count;
      notify({
        title: "Sentiment refreshed",
        description:
          outstanding > 0
            ? `${result.analyzed_count} of ${result.feedback_count} classified; ${outstanding} still failing.`
            : `All ${result.feedback_count} comments classified.`,
        tone: outstanding > 0 ? "info" : "positive",
      });
    } catch {
      notify({
        title: "Could not refresh sentiment",
        description: "The existing classification is unchanged.",
        tone: "critical",
      });
    }
  };

  const refreshButton =
    canRefresh && publicId ? (
      <Button
        size="sm"
        variant="outline"
        loading={refresh.isPending}
        onClick={handleRefresh}
        leadingIcon={<RefreshCw className="h-3.5 w-3.5" />}
      >
        {refresh.isPending ? "Classifying…" : "Re-classify"}
      </Button>
    ) : null;

  if (!sentiment || sentiment.feedback_count === 0) {
    return (
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
          <CardTitle>Community sentiment</CardTitle>
          {refreshButton}
        </CardHeader>
        <CardContent>
          <EmptyState
            icon={<MessagesSquare className="h-6 w-6" />}
            title="No feedback yet"
            description="Sentiment appears once contributors start rating and commenting."
          />
        </CardContent>
      </Card>
    );
  }

  const pieData = [
    { name: "Positive", value: sentiment.positive_percentage, color: SENTIMENT_COLORS.positive },
    { name: "Neutral", value: sentiment.neutral_percentage, color: SENTIMENT_COLORS.neutral },
    { name: "Negative", value: sentiment.negative_percentage, color: SENTIMENT_COLORS.negative },
  ].filter((entry) => entry.value > 0);

  const aspectData = sentiment.aspect_distribution.slice(0, 6).map((entry) => ({
    aspect: entry.aspect,
    percentage: entry.percentage,
  }));

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle>Community sentiment</CardTitle>
          <p className="mt-1 text-sm text-ink-muted">
            {sentiment.feedback_count} review{sentiment.feedback_count === 1 ? "" : "s"} ·
            average {sentiment.average_rating.toFixed(1)} / 5
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StarRating value={sentiment.average_rating} readOnly size={16} />
          {refreshButton}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <p className="mb-2 text-sm font-medium text-ink">Sentiment split</p>
            <div className="h-40">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    innerRadius={38}
                    outerRadius={62}
                    paddingAngle={2}
                    strokeWidth={0}
                  >
                    {pieData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value: number, name: string) => [`${value}%`, name]}
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }}
                  />
                  <Legend
                    verticalAlign="bottom"
                    height={24}
                    formatter={(value) => <span className="text-xs text-ink-muted">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
            {/* The chart is decorative for screen readers; the numbers are the content. */}
            <ul className="mt-2 space-y-1">
              {pieData.map((entry) => (
                <li key={entry.name} className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1.5 text-ink-muted">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ backgroundColor: entry.color }}
                      aria-hidden
                    />
                    {entry.name}
                  </span>
                  <span className="font-medium tabular-nums text-ink">{entry.value}%</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="mb-2 text-sm font-medium text-ink">What the community is discussing</p>
            {aspectData.length ? (
              <div className="h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={aspectData} layout="vertical" margin={{ left: 0, right: 12 }}>
                    <XAxis type="number" hide domain={[0, 100]} />
                    <YAxis
                      type="category"
                      dataKey="aspect"
                      width={110}
                      tick={{ fontSize: 11, fill: "#475569" }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      formatter={(value: number) => [`${value}%`, "Share of mentions"]}
                      contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }}
                      cursor={{ fill: "#F1F5F9" }}
                    />
                    <Bar dataKey="percentage" fill="#4F46E5" radius={[0, 4, 4, 0]} barSize={14} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p className="text-sm text-ink-muted">No themes identified yet.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function CommunityInsightsPanel({
  publicId,
  canRefresh,
}: {
  publicId: string;
  canRefresh: boolean;
}) {
  const { data: insight, isLoading } = useCommunityInsights(publicId);
  const refresh = useRefreshInsights(publicId);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>AI community intelligence</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    );
  }

  if (!insight) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent-600" aria-hidden />
            AI community intelligence
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EmptyState
            title="Not enough feedback yet"
            description="Once contributors leave feedback, their sentiment is aggregated and summarised here."
            action={
              canRefresh ? (
                <Button
                  size="sm"
                  variant="outline"
                  loading={refresh.isPending}
                  onClick={() => refresh.mutate()}
                >
                  Generate now
                </Button>
              ) : undefined
            }
          />
        </CardContent>
      </Card>
    );
  }

  return <InsightBody insight={insight} publicId={publicId} canRefresh={canRefresh} />;
}

function InsightBody({
  insight,
  canRefresh,
}: {
  insight: CommunityInsight;
  publicId: string;
  canRefresh: boolean;
}) {
  const refresh = useRefreshInsights(insight.campaign_id.toString());

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-accent-600" aria-hidden />
            AI community intelligence
          </CardTitle>
          <p className="mt-1 text-xs text-ink-muted">
            From {insight.feedback_count} feedback item
            {insight.feedback_count === 1 ? "" : "s"} · updated {formatRelative(insight.created_at)}
          </p>
        </div>
        {canRefresh && (
          <Button
            size="sm"
            variant="ghost"
            loading={refresh.isPending}
            onClick={() => refresh.mutate()}
            leadingIcon={<RefreshCw className="h-3.5 w-3.5" />}
          >
            Refresh
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-5">
        {insight.community_summary && (
          <blockquote className="border-l-2 border-accent-300 pl-4 text-sm leading-relaxed text-ink-soft">
            {insight.community_summary}
          </blockquote>
        )}

        <div className="grid gap-5 sm:grid-cols-2">
          {insight.positive_themes?.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-ink">What the community likes</h4>
              <ul className="mt-2 space-y-1.5">
                {insight.positive_themes.map((theme, index) => (
                  <li key={index} className="flex gap-2 text-sm text-ink-muted">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-positive" />
                    {theme}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {insight.top_concerns?.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-ink">Top concerns</h4>
              <ul className="mt-2 space-y-1.5">
                {insight.top_concerns.map((concern, index) => (
                  <li key={index} className="flex gap-2 text-sm text-ink-muted">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-caution" />
                    {concern}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {insight.recommendations?.length > 0 && (
          <div className="rounded-lg bg-surface-muted p-4">
            <h4 className="text-sm font-medium text-ink">Recommended for the creator</h4>
            <ul className="mt-2 space-y-1.5">
              {insight.recommendations.map((item, index) => (
                <li key={index} className="flex gap-2 text-sm text-ink-muted">
                  <span className="text-ink-faint">{index + 1}.</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {insight.risk_change && (
          <p className="text-sm text-ink-muted">
            <span className="font-medium text-ink">Risk signal: </span>
            {insight.risk_change}
          </p>
        )}

        <p className="text-xs text-ink-faint">{insight.disclaimer}</p>
      </CardContent>
    </Card>
  );
}

export function FeedbackList({ publicId }: { publicId: string }) {
  const [page, setPage] = useState(0);
  const { data, isLoading, isFetching } = useCampaignFeedback(publicId, page);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((index) => (
          <div key={index} className="card space-y-2 p-4">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ))}
      </div>
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        icon={<MessagesSquare className="h-6 w-6" />}
        title="No feedback yet"
        description="Be the first to share what you think about this campaign."
      />
    );
  }

  const totalPages = Math.ceil(data.total / data.limit);

  return (
    <div className="space-y-3">
      {data.items.map((item) => {
        const meta = SENTIMENT_META[item.sentiment];
        return (
          <article key={item.id} className="card p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-ink">
                  {item.author_name ?? "Contributor"}
                </span>
                <StarRating value={item.rating} readOnly size={14} />
              </div>
              <div className="flex items-center gap-2">
                {item.aspect_label && <Badge tone="neutral">{item.aspect_label}</Badge>}
                <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium", meta.tone)}>
                  <span className={cn("h-1.5 w-1.5 rounded-full", meta.dot)} aria-hidden />
                  {meta.label}
                </span>
              </div>
            </div>
            <p className="mt-2.5 text-sm leading-relaxed text-ink-soft">{item.text}</p>
            <p className="mt-2 text-xs text-ink-faint" title={formatDateTime(item.created_at)}>
              {formatRelative(item.created_at)}
            </p>
          </article>
        );
      })}

      {totalPages > 1 && (
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
          <p className="text-xs text-ink-muted">
            Page {page + 1} of {totalPages} · {data.total} total
          </p>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={page === 0 || isFetching}
              onClick={() => setPage((current) => current - 1)}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page + 1 >= totalPages || isFetching}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
