import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { CampaignStatus, ContributionStatus, Sentiment } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Status presentation, kept in one place so a badge never disagrees with a chart. */
export const CAMPAIGN_STATUS_META: Record<
  CampaignStatus,
  { label: string; tone: "neutral" | "info" | "positive" | "caution" | "critical"; description: string }
> = {
  DRAFT: { label: "Draft", tone: "neutral", description: "Being prepared by the creator." },
  KYC_PENDING: { label: "KYC pending", tone: "caution", description: "Waiting on identity verification." },
  FEE_PENDING: { label: "Fee pending", tone: "caution", description: "Application fee not yet verified." },
  ANALYSIS_PENDING: { label: "AI analysis", tone: "info", description: "AI analysis in progress." },
  UNDER_REVIEW: { label: "Under review", tone: "info", description: "Awaiting admin review." },
  APPROVED: { label: "Approved", tone: "positive", description: "Approved and ready to publish." },
  LIVE: { label: "Live", tone: "positive", description: "Accepting contributions." },
  COMPLETED: { label: "Completed", tone: "neutral", description: "Deadline reached." },
  TARGET_MET: { label: "Target met", tone: "positive", description: "Funding target achieved." },
  TARGET_MISSED: { label: "Target missed", tone: "caution", description: "Funding target not reached." },
  GOVERNANCE: { label: "Governance", tone: "info", description: "Contributor vote in progress." },
  REFUND_PENDING: { label: "Refund pending", tone: "caution", description: "Refunds being processed." },
  CONTINUED: { label: "Continued", tone: "positive", description: "Continued by contributor vote." },
  CLOSED: { label: "Closed", tone: "neutral", description: "Campaign closed." },
  REJECTED: { label: "Rejected", tone: "critical", description: "Rejected in review." },
};

export const CONTRIBUTION_STATUS_META: Record<
  ContributionStatus,
  { label: string; tone: "neutral" | "info" | "positive" | "caution" | "critical" }
> = {
  PAYMENT_VERIFIED: { label: "Payment verified", tone: "positive" },
  BLOCKCHAIN_PENDING: { label: "Anchoring pending", tone: "info" },
  BLOCKCHAIN_RECORDED: { label: "Anchored on chain", tone: "positive" },
  BLOCKCHAIN_FAILED: { label: "Anchor failed", tone: "caution" },
  REFUND_PENDING: { label: "Refund pending", tone: "caution" },
  REFUNDED: { label: "Refunded", tone: "neutral" },
};

export const SENTIMENT_META: Record<Sentiment, { label: string; tone: string; dot: string }> = {
  POSITIVE: { label: "Positive", tone: "text-positive-strong bg-positive-soft", dot: "bg-positive" },
  NEUTRAL: { label: "Neutral", tone: "text-ink-muted bg-surface-muted", dot: "bg-neutralState" },
  NEGATIVE: { label: "Negative", tone: "text-critical-strong bg-critical-soft", dot: "bg-critical" },
  PENDING: { label: "Analysing", tone: "text-accent-700 bg-accent-50", dot: "bg-accent-500" },
  FAILED: { label: "Not analysed", tone: "text-ink-muted bg-surface-muted", dot: "bg-neutralState" },
};

export const CATEGORY_LABELS: Record<string, string> = {
  TECHNOLOGY: "Technology",
  ENVIRONMENT: "Environment",
  HEALTHCARE: "Healthcare",
  EDUCATION: "Education",
  AGRICULTURE: "Agriculture",
  SOCIAL_IMPACT: "Social Impact",
  ENERGY: "Energy",
  ARTS: "Arts",
  OTHER: "Other",
};

export function healthTone(score: number | null | undefined): string {
  const value = Number(score ?? 0);
  if (value >= 75) return "text-positive-strong";
  if (value >= 60) return "text-brand-700";
  if (value >= 45) return "text-caution-strong";
  return "text-critical-strong";
}

export function riskTone(level: string | null | undefined): string {
  switch (level) {
    case "Low":
      return "text-positive-strong bg-positive-soft";
    case "High":
      return "text-critical-strong bg-critical-soft";
    case "Medium":
      return "text-caution-strong bg-caution-soft";
    default:
      return "text-ink-muted bg-surface-muted";
  }
}

/** Extract the campaign public id from anything a QR scan might yield. */
export function parseCampaignReference(input: string): string | null {
  const value = input.trim();
  if (!value) return null;

  const urlMatch = value.match(/\/campaign\/([A-Za-z0-9-]+)/);
  if (urlMatch) return urlMatch[1];

  if (/^CMP-\d+$/i.test(value)) return value.toUpperCase();

  // A bare slug or id is still worth trying against the API.
  if (/^[A-Za-z0-9-]+$/.test(value)) return value;

  return null;
}

export function scoreToWidth(score: number | null | undefined): string {
  return `${Math.max(0, Math.min(100, Number(score ?? 0)))}%`;
}
