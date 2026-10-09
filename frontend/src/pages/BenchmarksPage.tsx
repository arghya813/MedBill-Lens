/**
 * Benchmark dataset browser.
 *
 * The point of this page is transparency: what the comparisons are built from,
 * how many records exist, and where each one came from. Users should be able
 * to see that a range is thin before trusting it.
 */

import { useEffect, useMemo, useState } from "react";
import { ExternalLink, Search } from "lucide-react";

import { api } from "@/api/client";
import type { BenchmarkPriceOut, SelectOption } from "@/api/types";
import { SkeletonRows } from "@/components/Feedback";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useAppMeta } from "@/state/AppMeta";
import { usePreferences } from "@/state/Preferences";
import { useAsync } from "@/hooks/useAsync";
import { formatDate, formatMoney, humanize, toOptions } from "@/lib/format";

const PAGE_SIZE = 25;

const NO_FILTER: never[] = [];

const EMPTY_FILTERS = {
  city: "",
  hospital_category: "",
  service_category: "",
  treatment: "",
  room_category: "",
  verified_only: false,
};

export default function BenchmarksPage() {
  const { options } = useAppMeta();
  const { preferences, hydrated } = usePreferences();

  const [filters, setFilters] = useState({ ...EMPTY_FILTERS });
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");

  // Open on the comparison context saved in the profile.
  useEffect(() => {
    if (!hydrated) return;
    setFilters((previous) => ({
      ...previous,
      city: previous.city || preferences.default_city,
      hospital_category: previous.hospital_category || preferences.default_hospital_category,
      treatment: previous.treatment || preferences.default_treatment,
      room_category: previous.room_category || preferences.default_room_category,
    }));
  }, [
    hydrated,
    preferences.default_city,
    preferences.default_hospital_category,
    preferences.default_treatment,
    preferences.default_room_category,
  ]);

  const stats = useAsync((signal) => api.benchmarkStats(signal), []);

  const list = useAsync(
    (signal) =>
      api.benchmarks(
        {
          ...filters,
          verified_only: filters.verified_only ? true : undefined,
          limit: PAGE_SIZE,
          offset,
        },
        signal,
      ),
    [filters, offset],
  );

  const rows = useMemo<BenchmarkPriceOut[]>(() => {
    const items = list.data?.items ?? [];
    const term = query.trim().toLowerCase();
    if (!term) return items;
    // Client-side text filter: the API has no free-text search, and the current
    // page is small enough that filtering here avoids a round trip per keystroke.
    return items.filter((item) => item.service_name.toLowerCase().includes(term));
  }, [list.data, query]);

  const update = (patch: Partial<typeof filters>) => {
    setFilters((previous) => ({ ...previous, ...patch }));
    setOffset(0);
  };

  const reset = () => {
    setFilters({ ...EMPTY_FILTERS });
    setOffset(0);
  };

  const hasFilters =
    filters.city ||
    filters.hospital_category ||
    filters.service_category ||
    filters.treatment ||
    filters.room_category ||
    filters.verified_only;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <h1 className="text-3xl font-semibold tracking-tight text-ink-900">Benchmark data</h1>
      <p className="mt-2 max-w-3xl text-ink-600">
        Every comparison in MedBill Lens is drawn from this dataset. Ranges are computed per city,
        hospital type, treatment and room category from the records below, so you can see exactly
        what a "typical" price is based on.
      </p>

      {stats.data ? (
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="Records" value={stats.data.total_records.toLocaleString("en-IN")} />
          <StatTile label="Verified" value={stats.data.verified_records.toLocaleString("en-IN")} />
          <StatTile label="Cities" value={String(stats.data.cities.length)} />
          <StatTile
            label="Record dates"
            value={
              stats.data.min_source_date && stats.data.max_source_date
                ? `${formatDate(stats.data.min_source_date)} – ${formatDate(stats.data.max_source_date)}`
                : "Unknown"
            }
          />
        </div>
      ) : null}

      {stats.data ? (
        <Notice tone={stats.data.is_demo_data ? "warning" : "info"} className="mt-5">
          <span className="font-medium">{stats.data.dataset_label}. </span>
          {stats.data.notice}
          {stats.data.is_demo_data
            ? " Prices are illustrative and must not be used for real-world decisions."
            : ""}
        </Notice>
      ) : null}

      <div className="card card-pad mt-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-ink-900">Filter records</h2>
          {hasFilters ? (
            <button type="button" className="btn-ghost btn-sm" onClick={reset}>
              Clear filters
            </button>
          ) : null}
        </div>

        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Filter
            label="City"
            value={filters.city}
            options={toOptions(options?.cities)}
            onChange={(value) => update({ city: value })}
          />
          <Filter
            label="Hospital type"
            value={filters.hospital_category}
            options={options?.hospital_categories ?? NO_FILTER}
            onChange={(value) => update({ hospital_category: value })}
          />
          <Filter
            label="Service category"
            value={filters.service_category}
            options={options?.categories ?? NO_FILTER}
            onChange={(value) => update({ service_category: value })}
          />
          <Filter
            label="Treatment"
            value={filters.treatment}
            options={toOptions(options?.treatments)}
            onChange={(value) => update({ treatment: value })}
          />
          <Filter
            label="Room category"
            value={filters.room_category}
            options={options?.room_categories ?? NO_FILTER}
            onChange={(value) => update({ room_category: value })}
          />
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm text-ink-700">
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-ink-300 text-brand-600 focus:ring-brand-500"
            checked={filters.verified_only}
            onChange={(event) => update({ verified_only: event.target.checked })}
          />
          Only verified records
        </label>
      </div>

      <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-xs">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400"
            aria-hidden="true"
          />
          <input
            className="field-input pl-9"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter this page by service name"
            aria-label="Filter records on this page"
          />
        </div>
        {list.data ? (
          <p className="tnum text-sm text-ink-600">
            Showing {offset + 1}–{offset + rows.length} of{" "}
            {list.data.total.toLocaleString("en-IN")} records
          </p>
        ) : null}
      </div>

      {list.error ? <ErrorNotice error={list.error} className="mt-5" /> : null}

      <div className="mt-4 overflow-x-auto rounded-lg border border-ink-200 bg-white">
        {list.loading ? (
          <div className="p-4">
            <SkeletonRows rows={8} />
          </div>
        ) : rows.length === 0 ? (
          <p className="px-4 py-12 text-center text-sm text-ink-500">
            No records match these filters. Try widening the city or hospital type.
          </p>
        ) : (
          <table className="w-full min-w-[54rem] text-left text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th scope="col" className="px-3 py-2.5 font-semibold">Service</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Context</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Min</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Median</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Max</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Records</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {rows.map((item) => (
                <tr key={item.id} className="hover-row align-top">
                  <td className="px-3 py-2.5">
                    <p className="font-medium text-ink-900">{item.service_name}</p>
                    <p className="text-xs text-ink-500">{humanize(item.service_category)}</p>
                  </td>
                  <td className="px-3 py-2.5 text-xs text-ink-600">
                    {item.city}
                    {item.hospital_category ? ` · ${humanize(item.hospital_category)}` : ""}
                    {item.treatment ? ` · ${humanize(item.treatment)}` : ""}
                    {item.room_category ? ` · ${humanize(item.room_category)}` : ""}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-ink-700">
                    {formatMoney(item.min_price, item.currency_code, { decimals: false })}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right font-medium text-ink-900">
                    {formatMoney(item.median_price, item.currency_code, { decimals: false })}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-ink-700">
                    {formatMoney(item.max_price, item.currency_code, { decimals: false })}
                  </td>
                  <td className="tnum px-3 py-2.5 text-right text-ink-700">{item.record_count}</td>
                  <td className="px-3 py-2.5 text-xs text-ink-600">
                    {item.source_name ?? "\u2014"}
                    {item.source_url ? (
                      <a
                        className="ml-1 inline-flex align-middle"
                        href={item.source_url}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={`Source for ${item.service_name}`}
                      >
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : null}
                    {item.source_date ? (
                      <span className="block text-ink-400">{formatDate(item.source_date)}</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {list.data && list.data.total > PAGE_SIZE ? (
        <div className="mt-5 flex items-center justify-between gap-3">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => setOffset((value) => Math.max(0, value - PAGE_SIZE))}
            disabled={offset === 0 || list.refreshing}
          >
            Previous
          </button>
          <p className="tnum text-sm text-ink-600">
            Page {Math.floor(offset / PAGE_SIZE) + 1} of{" "}
            {Math.ceil(list.data.total / PAGE_SIZE)}
          </p>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => setOffset((value) => value + PAGE_SIZE)}
            disabled={offset + PAGE_SIZE >= list.data.total || list.refreshing}
          >
            Next
          </button>
        </div>
      ) : null}

      {stats.loading ? (
        <div className="mt-7" role="status" aria-busy="true">
          <span className="sr-only">Loading dataset details</span>
          <SkeletonRows rows={4} />
        </div>
      ) : null}
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="card card-lift px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className="tnum mt-1 text-lg font-semibold text-ink-900">{value}</p>
    </div>
  );
}

function Filter({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly SelectOption[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="field-label">{label}</label>
      <select
        className="field-input"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label={label}
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
