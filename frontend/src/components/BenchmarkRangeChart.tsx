/**
 * Benchmark range chart.
 *
 * Bars show what was billed against the comparable range. A range band that
 * contains the actual bar means the charge sits inside the benchmark; anything
 * outside it is what the flags pick up. Categories without a benchmark are
 * drawn as actual-only so the bill total always reconciles visually.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CategorySpend } from "@/api/types";
import { currencySymbol, formatMoney } from "@/lib/format";

const COLORS = {
  within: "#10b981",
  below: "#0ea5e9",
  above: "#f97316",
  attention: "#f43f5e",
  none: "#94a3b8",
};

interface Row extends CategorySpend {
  band: [number, number] | null;
  tone: keyof typeof COLORS;
}

export function BenchmarkRangeChart({
  data,
  currency = "INR",
  height = 320,
}: {
  data: CategorySpend[];
  currency?: string;
  height?: number;
}) {
  if (data.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-ink-500">
        No category data available for this bill.
      </p>
    );
  }

  const rows: Row[] = data.map((entry) => {
    const hasRange = entry.benchmark_min !== null && entry.benchmark_max !== null;
    const actual = entry.actual;
    let tone: keyof typeof COLORS = "none";
    if (!hasRange) tone = "none";
    else if (actual < (entry.benchmark_min as number)) tone = "below";
    else if (actual > (entry.benchmark_max as number)) tone = "above";
    else tone = "within";
    return {
      ...entry,
      band: hasRange ? [entry.benchmark_min as number, entry.benchmark_max as number] : null,
      tone,
    };
  });

  // Recharts renders the range as a stacked pair: an invisible base up to the
  // minimum, then the band itself.
  const chartData = rows.map((row) => ({
    label: row.label,
    actual: row.actual,
    bandBase: row.band ? row.band[0] : 0,
    bandSize: row.band ? row.band[1] - row.band[0] : 0,
    hasRange: Boolean(row.band),
    color: COLORS[row.tone],
    percentOfBill: row.percent_of_bill,
    benchmarkMin: row.benchmark_min,
    benchmarkMax: row.benchmark_max,
    difference: row.difference,
  }));

  const symbol = currencySymbol(currency);

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 8, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "#64748b" }}
            interval={0}
            angle={-18}
            textAnchor="end"
            height={56}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickFormatter={(value: number) => `${symbol}${Math.round(value / 1000)}k`}
            width={64}
          />
          <Tooltip
            formatter={(value, name) => {
              if (name === "What you were billed") return [formatMoney(value as number, currency), name];
              return [formatMoney(value as number, currency), "Benchmark range"];
            }}
            labelFormatter={(label) => String(label)}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12 }}
            formatter={(value) =>
              value === "What you were billed" ? "Billed amount" : "Benchmark range"
            }
          />
          <Bar dataKey="bandBase" stackId="range" fill="transparent" isAnimationActive={false} />
          <Bar
            dataKey="bandSize"
            stackId="range"
            fill="#cbd5e1"
            isAnimationActive={false}
            radius={[3, 3, 0, 0]}
          />
          <Bar
            dataKey="actual"
            radius={[3, 3, 0, 0]}
            maxBarSize={44}
            cursor="pointer"
            isAnimationActive
            animationDuration={800}
            animationBegin={120}
            animationEasing="ease-out"
          >
            {chartData.map((entry) => (
              <Cell key={entry.label} fill={entry.color} />
            ))}
          </Bar>
          <ReferenceLine y={0} stroke="#cbd5e1" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Legend explaining the bar colours used by the range chart. */
export function BenchmarkChartLegend() {
  const items: { label: string; color: string }[] = [
    { label: "Inside the benchmark range", color: COLORS.within },
    { label: "Below the range", color: COLORS.below },
    { label: "Above the range", color: COLORS.above },
    { label: "No comparable benchmark", color: COLORS.none },
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-ink-600">
      {items.map((item) => (
        <li key={item.label} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
