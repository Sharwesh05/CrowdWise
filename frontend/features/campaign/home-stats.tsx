"use client";

import { formatCompactCurrency, formatNumber } from "@/lib/format";
import { usePlatformStats } from "@/hooks";

/** Headline numbers. Every value is observed from the database — nothing invented. */
export function HomeStats() {
  const { data, isLoading, isError } = usePlatformStats();

  if (isError) return null;

  const items = [
    { label: "Live campaigns", value: data ? formatNumber(data.live_campaigns) : null },
    { label: "Total raised", value: data ? formatCompactCurrency(data.total_raised) : null },
    { label: "Contributors", value: data ? formatNumber(data.contributors) : null },
    { label: "On-chain records", value: data ? formatNumber(data.blockchain_records) : null },
  ];

  return (
    <dl className="mt-14 grid max-w-3xl grid-cols-2 gap-x-8 gap-y-6 border-t border-surface-border pt-8 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label}>
          <dd className="text-2xl font-semibold tracking-tight text-ink tabular-nums">
            {isLoading || item.value === null ? (
              <span className="skeleton inline-block h-7 w-20 align-middle" />
            ) : (
              item.value
            )}
          </dd>
          <dt className="mt-1 text-xs font-medium uppercase tracking-wide text-ink-faint">
            {item.label}
          </dt>
        </div>
      ))}
    </dl>
  );
}
