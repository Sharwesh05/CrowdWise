"use client";

import { AlertTriangle, Brain, CheckCircle2, HelpCircle, Info, Lightbulb, RefreshCw } from "lucide-react";

import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, useToast } from "@/components/ui";
import { useRefreshAnalysis } from "@/hooks";
import { cn, riskTone, scoreToWidth } from "@/lib/utils";
import type { AIAnalysis } from "@/types";

function ScoreBar({
  label,
  score,
  invert = false,
}: {
  label: string;
  score: number | null;
  invert?: boolean;
}) {
  const value = score ?? 0;
  // Risk is the one score where higher is worse, so its bar colour inverts.
  const good = invert ? value < 40 : value >= 70;
  const middling = invert ? value < 70 : value >= 45;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-ink-soft">{label}</span>
        <span className="text-sm font-semibold tabular-nums text-ink">{value}</span>
      </div>
      <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted">
        <div
          className={cn(
            "h-full rounded-full transition-[width] duration-700",
            good ? "bg-positive" : middling ? "bg-caution" : "bg-critical",
          )}
          style={{ width: scoreToWidth(value) }}
        />
      </div>
    </div>
  );
}

function List({
  title,
  items,
  icon,
  tone,
}: {
  title: string;
  items: string[];
  icon: React.ReactNode;
  tone: string;
}) {
  if (!items?.length) return null;
  return (
    <div>
      <h4 className="flex items-center gap-1.5 text-sm font-medium text-ink">
        <span className={tone}>{icon}</span>
        {title}
      </h4>
      <ul className="mt-2 space-y-1.5">
        {items.map((item, index) => (
          <li key={index} className="flex gap-2 text-sm leading-relaxed text-ink-muted">
            <span className={cn("mt-1.5 h-1 w-1 shrink-0 rounded-full", tone.replace("text-", "bg-"))} />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function AIAnalysisPanel({
  analysis,
  showQuestions = false,
  publicId,
  canRefresh = false,
}: {
  analysis: AIAnalysis | null;
  showQuestions?: boolean;
  /** Required for the refresh control; without it the button is not rendered. */
  publicId?: string;
  canRefresh?: boolean;
}) {
  const refresh = useRefreshAnalysis(publicId ?? "");
  const { notify } = useToast();
  const showRefresh = canRefresh && Boolean(publicId);

  const handleRefresh = async () => {
    try {
      const result = await refresh.mutateAsync();
      notify({
        title: result.status === "DEGRADED" ? "Analysis degraded" : "Analysis refreshed",
        description:
          result.status === "DEGRADED"
            ? "The model was unreachable, so the heuristic analyst ran instead."
            : `Re-analysed by ${result.model}.`,
        tone: result.status === "DEGRADED" ? "info" : "positive",
      });
    } catch {
      notify({
        title: "Could not refresh the analysis",
        description: "The previous analysis is unchanged. Try again in a moment.",
        tone: "critical",
      });
    }
  };

  const refreshButton = showRefresh ? (
    <Button
      size="sm"
      variant="outline"
      loading={refresh.isPending}
      onClick={handleRefresh}
      leadingIcon={<RefreshCw className="h-3.5 w-3.5" />}
    >
      {refresh.isPending ? "Analysing…" : "Re-run"}
    </Button>
  ) : null;

  if (!analysis) {
    return (
      <Card>
        <CardHeader className="flex-row items-start justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-accent-600" aria-hidden />
            AI campaign analysis
          </CardTitle>
          {refreshButton}
        </CardHeader>
        <CardContent>
          <EmptyState
            title="No analysis yet"
            description="Analysis runs once the application fee is verified."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-accent-600" aria-hidden />
          AI campaign analysis
        </CardTitle>
        <div className="flex flex-wrap items-center gap-2">
          {analysis.status === "DEGRADED" && (
            <Badge tone="caution">Fallback analysis</Badge>
          )}
          <Badge className={riskTone(analysis.risk_level)}>{analysis.risk_level} risk</Badge>
          {refreshButton}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {analysis.summary && (
          <p className="text-sm leading-relaxed text-ink-soft">{analysis.summary}</p>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <ScoreBar label="Feasibility" score={analysis.feasibility_score} />
          <ScoreBar label="Problem clarity" score={analysis.problem_clarity_score} />
          <ScoreBar label="Potential impact" score={analysis.impact_score} />
          <ScoreBar label="Execution risk" score={analysis.risk_score} invert />
        </div>

        <div className="grid gap-5 border-t border-surface-border pt-5 sm:grid-cols-2">
          <List
            title="Strengths"
            items={analysis.strengths}
            icon={<CheckCircle2 className="h-4 w-4" aria-hidden />}
            tone="text-positive"
          />
          <List
            title="Concerns"
            items={analysis.concerns}
            icon={<AlertTriangle className="h-4 w-4" aria-hidden />}
            tone="text-caution"
          />
          <List
            title="Recommendations"
            items={analysis.recommendations}
            icon={<Lightbulb className="h-4 w-4" aria-hidden />}
            tone="text-accent-500"
          />
          {showQuestions && (
            <List
              title="Questions for the creator"
              items={analysis.questions_for_creator}
              icon={<HelpCircle className="h-4 w-4" aria-hidden />}
              tone="text-ink-muted"
            />
          )}
        </div>

        {/* The disclaimer travels with every AI surface, by design. */}
        <p className="flex items-start gap-2 rounded-lg bg-surface-muted p-3 text-xs leading-relaxed text-ink-muted">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          {analysis.disclaimer} Generated by{" "}
          <span className="font-medium">{analysis.model}</span>.
        </p>
      </CardContent>
    </Card>
  );
}
