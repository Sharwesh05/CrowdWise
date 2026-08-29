import Link from "next/link";
import { BadgeCheck, Clock, HeartHandshake, Star } from "lucide-react";

import { Badge, Progress } from "@/components/ui";
import { formatCompactCurrency, formatNumber } from "@/lib/format";
import { CAMPAIGN_STATUS_META, CATEGORY_LABELS, cn, healthTone } from "@/lib/utils";
import type { CampaignSummary } from "@/types";

const COVER_TONES = [
  "from-brand-100 to-brand-50",
  "from-accent-100 to-accent-50",
  "from-caution-soft to-surface-muted",
  "from-surface-muted to-surface-subtle",
];

export function CampaignCard({ campaign }: { campaign: CampaignSummary }) {
  const status = CAMPAIGN_STATUS_META[campaign.status];
  // Deterministic cover tint when no image is set, so cards stay distinguishable
  // without inventing imagery.
  const tone = COVER_TONES[campaign.id % COVER_TONES.length];

  return (
    <article className="card card-hover flex h-full flex-col overflow-hidden">
      <div className={cn("relative h-36 bg-gradient-to-br", tone)}>
        {campaign.cover_image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={campaign.cover_image_url}
            alt=""
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <div className="flex h-full items-center justify-center">
            <span className="text-3xl font-bold tracking-tight text-ink/15">
              {campaign.public_id}
            </span>
          </div>
        )}
        <div className="absolute left-3 top-3 flex gap-2">
          <Badge tone="neutral" className="bg-surface/90 backdrop-blur">
            {CATEGORY_LABELS[campaign.category] ?? campaign.category}
          </Badge>
          {campaign.is_demo && (
            <Badge tone="caution" className="bg-surface/90 backdrop-blur">
              DEMO
            </Badge>
          )}
        </div>
        <div className="absolute right-3 top-3">
          <Badge tone={status.tone} className="bg-surface/90 backdrop-blur">
            {status.label}
          </Badge>
        </div>
      </div>

      <div className="flex flex-1 flex-col p-4">
        <div className="flex items-center gap-1.5 text-xs text-ink-muted">
          <span>{campaign.creator.name}</span>
          {campaign.creator.is_verified && (
            <span className="inline-flex items-center gap-0.5 text-brand-700" title="Identity verified creator">
              <BadgeCheck className="h-3.5 w-3.5" aria-hidden />
              <span className="sr-only">Verified creator</span>
            </span>
          )}
        </div>

        <h3 className="mt-1.5 line-clamp-2 text-base font-semibold leading-snug text-ink">
          <Link href={`/campaign/${campaign.public_id}`} className="hover:underline">
            {campaign.title}
          </Link>
        </h3>

        <p className="mt-1.5 line-clamp-2 text-sm text-ink-muted">{campaign.short_description}</p>

        <div className="mt-4 space-y-2">
          <Progress
            value={campaign.funding_percentage}
            label={`${campaign.funding_percentage}% funded`}
          />
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-semibold text-ink">
              {formatCompactCurrency(campaign.raised_amount)}
            </span>
            <span className="text-xs text-ink-muted">
              of {formatCompactCurrency(campaign.target_amount)} · {campaign.funding_percentage}%
            </span>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-surface-border pt-3 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1">
            <HeartHandshake className="h-3.5 w-3.5" aria-hidden />
            {formatNumber(campaign.contributor_count)} backers
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" aria-hidden />
            {campaign.days_remaining}d left
          </span>
          {campaign.average_rating !== null && (
            <span className="inline-flex items-center gap-1">
              <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" aria-hidden />
              {campaign.average_rating.toFixed(1)}
            </span>
          )}
          {campaign.health_score !== null && (
            <span className={cn("ml-auto font-medium", healthTone(campaign.health_score))}>
              Health {campaign.health_score}
            </span>
          )}
        </div>
      </div>

      <div className="border-t border-surface-border p-3">
        <Link
          href={`/campaign/${campaign.public_id}`}
          className="block rounded-lg bg-surface-muted py-2 text-center text-sm font-medium text-ink transition-colors hover:bg-ink hover:text-white"
        >
          View campaign
        </Link>
      </div>
    </article>
  );
}

export function CampaignCardSkeleton() {
  return (
    <div className="card overflow-hidden">
      <div className="h-36 skeleton rounded-none" />
      <div className="space-y-3 p-4">
        <div className="skeleton h-3 w-24" />
        <div className="skeleton h-4 w-full" />
        <div className="skeleton h-4 w-3/4" />
        <div className="skeleton h-2 w-full" />
        <div className="flex gap-3">
          <div className="skeleton h-3 w-16" />
          <div className="skeleton h-3 w-16" />
        </div>
      </div>
    </div>
  );
}
