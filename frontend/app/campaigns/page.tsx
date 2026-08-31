"use client";

import { useState } from "react";
import { Search, SlidersHorizontal } from "lucide-react";

import { Button, EmptyState, ErrorState, Input, Select } from "@/components/ui";
import { CampaignCard, CampaignCardSkeleton } from "@/features/campaign/campaign-card";
import { CATEGORY_LABELS } from "@/lib/utils";
import { usePublicCampaigns } from "@/hooks";

const SORTS = [
  { value: "trending", label: "Trending" },
  { value: "newest", label: "Newest" },
  { value: "progress", label: "Funding progress" },
  { value: "most_supported", label: "Most supported" },
  { value: "ending_soon", label: "Ending soon" },
];

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "LIVE", label: "Live" },
  { value: "GOVERNANCE", label: "In governance" },
  { value: "TARGET_MET", label: "Target met" },
  { value: "TARGET_MISSED", label: "Target missed" },
];

const PAGE_SIZE = 9;

export default function CampaignsPage() {
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("trending");
  const [page, setPage] = useState(0);

  const { data, isLoading, isFetching, isError, error, refetch } = usePublicCampaigns({
    search: submittedSearch || undefined,
    category: category || undefined,
    status: status || undefined,
    sort,
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0;

  const applySearch = (event: React.FormEvent) => {
    event.preventDefault();
    setPage(0);
    setSubmittedSearch(search.trim());
  };

  const resetFilters = () => {
    setSearch("");
    setSubmittedSearch("");
    setCategory("");
    setStatus("");
    setSort("trending");
    setPage(0);
  };

  const hasFilters = Boolean(submittedSearch || category || status || sort !== "trending");

  return (
    <div className="container-page py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight">Explore campaigns</h1>
        <p className="mt-2 max-w-2xl text-ink-muted">
          Every campaign here has passed identity verification, AI analysis and human review
          before being published.
        </p>
      </header>

      <div className="mb-6 space-y-3">
        <form onSubmit={applySearch} className="flex gap-2" role="search">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint"
              aria-hidden
            />
            <Input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search campaigns by title or description"
              aria-label="Search campaigns"
              className="pl-9"
            />
          </div>
          <Button type="submit" variant="outline">
            Search
          </Button>
        </form>

        <div className="flex flex-wrap items-center gap-3">
          <span className="flex items-center gap-1.5 text-sm text-ink-muted">
            <SlidersHorizontal className="h-4 w-4" aria-hidden />
            Filter
          </span>
          <div className="w-full sm:w-44">
            <Select
              value={category}
              onChange={(event) => {
                setCategory(event.target.value);
                setPage(0);
              }}
              aria-label="Filter by category"
            >
              <option value="">All categories</option>
              {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-full sm:w-44">
            <Select
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(0);
              }}
              aria-label="Filter by status"
            >
              {STATUSES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="w-full sm:w-48">
            <Select
              value={sort}
              onChange={(event) => {
                setSort(event.target.value);
                setPage(0);
              }}
              aria-label="Sort campaigns"
            >
              {SORTS.map((option) => (
                <option key={option.value} value={option.value}>
                  Sort: {option.label}
                </option>
              ))}
            </Select>
          </div>
          {hasFilters && (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Clear
            </Button>
          )}
          {data && (
            <span className="text-sm text-ink-muted sm:ml-auto" aria-live="polite">
              {data.total} campaign{data.total === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </div>

      {isError ? (
        <ErrorState
          title="Could not load campaigns"
          message={error instanceof Error ? error.message : undefined}
          onRetry={() => refetch()}
        />
      ) : isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <CampaignCardSkeleton key={index} />
          ))}
        </div>
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={<Search className="h-6 w-6" />}
          title="No campaigns match those filters"
          description="Try a different search term, or clear the filters to see everything."
          action={
            hasFilters ? (
              <Button size="sm" variant="outline" onClick={resetFilters}>
                Clear filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {data.items.map((campaign) => (
              <CampaignCard key={campaign.id} campaign={campaign} />
            ))}
          </div>

          {totalPages > 1 && (
            <nav className="mt-8 flex items-center justify-center gap-3" aria-label="Pagination">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0 || isFetching}
                onClick={() => setPage((current) => current - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-ink-muted">
                Page {page + 1} of {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page + 1 >= totalPages || isFetching}
                onClick={() => setPage((current) => current + 1)}
              >
                Next
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
