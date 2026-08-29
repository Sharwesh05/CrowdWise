"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { EmptyState } from "@/components/ui";
import { formatCompactCurrency, formatDate } from "@/lib/format";

export function FundingChart({
  series,
  target,
}: {
  series: { date: string; amount: number; cumulative: number }[];
  target: number;
}) {
  if (!series.length) {
    return (
      <EmptyState
        title="No contributions yet"
        description="The funding curve appears once the first verified contribution arrives."
      />
    );
  }

  return (
    <>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="fundingFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#10B583" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#10B583" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 11, fill: "#94A3B8" }}
              tickFormatter={(value: string) => formatDate(value).slice(0, 6)}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#94A3B8" }}
              tickFormatter={(value: number) => formatCompactCurrency(value)}
              axisLine={false}
              tickLine={false}
              width={64}
            />
            <Tooltip
              formatter={(value: number, name: string) => [
                formatCompactCurrency(value),
                name === "cumulative" ? "Total raised" : "Contribution",
              ]}
              labelFormatter={(label: string) => formatDate(label)}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #E2E8F0" }}
            />
            {/* The target line makes the gap legible without a second chart. */}
            {target > 0 && (
              <ReferenceLine
                y={target}
                stroke="#94A3B8"
                strokeDasharray="4 4"
                label={{
                  value: "Target",
                  position: "insideTopRight",
                  fontSize: 11,
                  fill: "#94A3B8",
                }}
              />
            )}
            <Area
              type="monotone"
              dataKey="cumulative"
              stroke="#059669"
              strokeWidth={2}
              fill="url(#fundingFill)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* The same data as text, for anyone the chart does not serve. */}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-xs text-ink-muted hover:text-ink">
          View as a table
        </summary>
        <table className="mt-2 w-full text-xs">
          <thead>
            <tr className="border-b border-surface-border text-left text-ink-faint">
              <th scope="col" className="py-1.5">Date</th>
              <th scope="col" className="py-1.5">Contribution</th>
              <th scope="col" className="py-1.5">Total raised</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {series.map((point, index) => (
              <tr key={index}>
                <td className="py-1.5 text-ink-muted">{formatDate(point.date)}</td>
                <td className="py-1.5 tabular-nums text-ink-soft">
                  {formatCompactCurrency(point.amount)}
                </td>
                <td className="py-1.5 tabular-nums font-medium text-ink">
                  {formatCompactCurrency(point.cumulative)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </>
  );
}
