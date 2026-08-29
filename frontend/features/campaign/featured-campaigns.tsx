"use client";

import Link from "next/link";
import { Compass } from "lucide-react";

import { Button, EmptyState, ErrorState } from "@/components/ui";
import { CampaignCard, CampaignCardSkeleton } from "@/features/campaign/campaign-card";
import { usePublicCampaigns } from "@/hooks";

export function FeaturedCampaigns() {
  const { data, isLoading, isError, error, refetch } = usePublicCampaigns({
    sort: "trending",
    limit: 3,
  });

  if (isLoading) {
    return (
      <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((index) => (
          <CampaignCardSkeleton key={index} />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="Could not load campaigns"
        message={error instanceof Error ? error.message : undefined}
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || data.items.length === 0) {
    return (
      <EmptyState
        icon={<Compass className="h-6 w-6" />}
        title="No campaigns are live yet"
        description="Approved campaigns appear here as soon as they are published."
        action={
          <Link href="/register?role=CREATOR">
            <Button size="sm">Start the first one</Button>
          </Link>
        }
      />
    );
  }

  return (
    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-3">
      {data.items.map((campaign) => (
        <CampaignCard key={campaign.id} campaign={campaign} />
      ))}
    </div>
  );
}
