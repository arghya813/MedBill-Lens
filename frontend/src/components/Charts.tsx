import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { CategorySpend } from "@/api/types";
import { currencySymbol, formatMoney, formatPercent } from "@/lib/format";

const SLICE_COLORS = [
  "#337fff",
  "#14b8a6",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
  "#0ea5e9",
  "#84cc16",
  "#f43f5e",
  "#64748b",
];

export function CategorySpendChart({
  data,
  currency = "INR",
  height = 280,
}: {
  data: CategorySpend[];
  currency?: string;
  height?: number;
}) {
  if (data.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-ink-500">No category data available.</p>
    );
  }
  const symbol = currencySymbol(currency);

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 4, right: 16, left: 4, bottom: 4 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 11, fill: "#64748b" }}
            tickFormatter={(value: number) => `${symbol}${Math.round(value / 1000)}k`}
          />
          <YAxis
            type="category"
            dataKey="label"
            tick={{ fontSize: 11, fill: "#64748b" }}
            width={110}
          />
          <Tooltip
            formatter={(value) => [formatMoney(value as number, currency), "Billed"]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
          <Bar
            dataKey="actual"
            radius={[0, 3, 3, 0]}
            maxBarSize={22}
            cursor="pointer"
            isAnimationActive
            animationDuration={700}
            animationEasing="ease-out"
          >
            {data.map((entry, index) => (
              <Cell key={entry.category} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function CategoryShareChart({
  data,
  currency = "INR",
  height = 260,
}: {
  data: CategorySpend[];
  currency?: string;
  height?: number;
}) {
  const withSpend = data.filter((entry) => entry.actual !== 0);
  if (withSpend.length === 0) {
    return <p className="py-10 text-center text-sm text-ink-500">No spend to show.</p>;
  }

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={withSpend}
            dataKey="actual"
            nameKey="label"
            cx="50%"
            cy="50%"
            innerRadius="52%"
            outerRadius="80%"
            paddingAngle={1.5}
            stroke="none"
            cursor="pointer"
            isAnimationActive
            animationDuration={800}
            animationBegin={80}
            animationEasing="ease-out"
          >
            {withSpend.map((entry, index) => (
              <Cell key={entry.category} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value) => [formatMoney(value as number, currency), "Billed"]}
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Legend for the share chart, listing category and share of the bill. */
export function CategoryShareLegend({
  data,
  currency = "INR",
}: {
  data: CategorySpend[];
  currency?: string;
}) {
  const total = data.reduce((sum, entry) => sum + entry.actual, 0);
  return (
    <ul className="space-y-1.5 text-sm">
      {data.map((entry, index) => (
        <li key={entry.category} className="flex items-center gap-2">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: SLICE_COLORS[index % SLICE_COLORS.length] }}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1 truncate text-ink-700">{entry.label}</span>
          <span className="tnum text-ink-500">
            {formatMoney(entry.actual, currency, { decimals: false })}
          </span>
          <span className="tnum w-14 text-right font-medium text-ink-900">
            {formatPercent(total === 0 ? 0 : (entry.actual / total) * 100, 0)}
          </span>
        </li>
      ))}
    </ul>
  );
}
