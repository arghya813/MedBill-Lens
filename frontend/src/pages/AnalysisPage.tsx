/**
 * Bill analysis: the comparison result.
 *
 * Everything numeric here comes straight from the deterministic engine. The
 * layout is ordered by what the user came to do: see the headline, see the
 * charges worth asking about, then dig into the full comparison.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowRight,
  ClipboardCopy,
  FileDown,
  Info,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { ApiError, api } from "@/api/client";
import type { AnalysisOut, ChargeComparisonOut } from "@/api/types";
import { BenchmarkChartLegend, BenchmarkRangeChart } from "@/components/BenchmarkRangeChart";
import {
  CategoryShareChart,
  CategoryShareLegend,
  CategorySpendChart,
} from "@/components/Charts";
import { Metric, Spinner } from "@/components/Feedback";
import { AnimatedMetric, PageSkeleton } from "@/components/Feedback";
import { ScrollReveal } from "@/components/motion";
import { FlagPill } from "@/components/FlagPill";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useBillSession } from "@/state/BillSession";
import { usePreferences } from "@/state/Preferences";
import {
  FLAG_META,
  formatDateTime,
  formatMoney,
  formatPercent,
  humanize,
  pluralize,
} from "@/lib/format";

type Filter = "all" | "needs_looking_at" | "matched";

export default function AnalysisPage() {
  const { billId } = useParams<{ billId: string }>();
  const navigate = useNavigate();
  const { bill, setBill, setAnalysis } = useBillSession();
  const { preferences, hydrated } = usePreferences();

  const [analysis, setLocal] = useState<AnalysisOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [notConfirmed, setNotConfirmed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [copied, setCopied] = useState(false);

  // Adopt the saved starting filter once preferences have loaded from storage.
  useEffect(() => {
    if (hydrated) setFilter(preferences.default_analysis_filter);
  }, [hydrated, preferences.default_analysis_filter]);

  const currency = bill?.currency_code ?? "INR";

  // Load the bill and its analysis in parallel. A bill without an analysis is
  // a valid state, not an error: the user may still need to confirm it.
  useEffect(() => {
    if (!billId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setNotConfirmed(false);

    Promise.all([
      api.getBill(billId, controller.signal),
      api.getAnalysis(billId, controller.signal).catch((cause: unknown) => {
        // 409 means "confirm the bill first", which the page renders as a
        // prompt rather than an error. Anything else is a real failure.
        if (cause instanceof ApiError && cause.status === 409) {
          setNotConfirmed(true);
          return null;
        }
        throw cause;
      }),
    ])
      .then(([nextBill, nextAnalysis]) => {
        setBill(nextBill);
        setAnalysis(nextAnalysis);
        setLocal(nextAnalysis);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billId]);

  const run = useCallback(async () => {
    if (!billId) return;
    setRunning(true);
    setError(null);
    try {
      const response = await api.analyzeBill(billId);
      setLocal(response.analysis);
      setAnalysis(response.analysis);
      setNotConfirmed(false);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) setNotConfirmed(true);
      setError(cause instanceof Error ? cause : new Error(String(cause)));
    } finally {
      setRunning(false);
    }
  }, [billId, setAnalysis]);

  // Stable identity: `?? []` would allocate a new array on every render and
  // invalidate the filtered memo below on each one.
  const comparisons = useMemo(() => analysis?.comparisons ?? [], [analysis]);

  const filtered = useMemo(() => {
    const base =
      preferences.hide_unmatched_charges
        ? comparisons.filter((row) => row.benchmark_available)
        : comparisons;
    if (filter === "needs_looking_at") {
      return base.filter(
        (row) => row.flag_status !== "within_range" && row.flag_status !== "not_comparable",
      );
    }
    if (filter === "matched") return base.filter((row) => row.benchmark_available);
    return base;
  }, [comparisons, filter, preferences.hide_unmatched_charges]);

  const copyQuestions = useCallback(async () => {
    if (!analysis) return;
    try {
      await navigator.clipboard.writeText(analysis.questions.join("\n"));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be denied; the questions stay visible on screen.
    }
  }, [analysis]);

  if (loading) return <PageSkeleton label="Loading analysis" />;

  if (error && !analysis) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <ErrorNotice error={error} />
        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/review" className="btn-secondary btn-sm">
            Back to review
          </Link>
          <Link to="/" className="btn-ghost btn-sm">
            Start over
          </Link>
        </div>
      </div>
    );
  }

  if (!billId) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <Notice tone="warning" title="No bill selected">
          <Link to="/upload" className="link">
            Upload a bill
          </Link>{" "}
          or{" "}
          <Link to="/review" className="link">
            enter charges manually
          </Link>{" "}
          to get an analysis.
        </Notice>
      </div>
    );
  }

  // The bill has not been confirmed yet: explain the gate and offer the fix.
  if (!analysis) {
    const blocked = notConfirmed || bill?.status !== "confirmed";
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink-900">
          {blocked ? "Confirm your bill to see the comparison" : "Run the comparison"}
        </h1>
        <p className="mt-2 text-ink-600">
          {blocked
            ? "We compare charges only after you have confirmed the bill data, so the numbers always match what you agreed is correct."
            : "Your bill is confirmed. Run the benchmark comparison to see each charge against comparable records."}
        </p>
        {error ? <ErrorNotice error={error} className="mt-5" /> : null}
        <div className="mt-6 flex flex-wrap gap-3">
          {blocked ? (
            <Link to={`/bills/${billId}`} className="btn-primary">
              Review and confirm
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          ) : (
            <button type="button" className="btn-primary" onClick={run} disabled={running}>
              {running ? <Spinner /> : null}
              Run the comparison
            </button>
          )}
          <Link to="/review" className="btn-ghost">
            Start a different bill
          </Link>
        </div>
      </div>
    );
  }

  const { totals, counts } = analysis;
  const coverageTone =
    totals.coverage_percent >= 80
      ? "positive"
      : totals.coverage_percent >= 50
        ? "warning"
        : "danger";

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
            {analysis.headline ?? "Bill comparison"}
          </h1>
          <p className="mt-2 max-w-3xl text-ink-600">
            {bill?.hospital_name ? `${bill.hospital_name} · ` : ""}
            {bill?.bill_date ? `Bill dated ${formatDateTime(bill.bill_date)} · ` : ""}
            {analysis.dataset_label}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={run}
            disabled={running}
          >
            {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Re-run
          </button>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => navigate(`/bills/${billId}/report`)}
          >
            <FileDown className="h-3.5 w-3.5" aria-hidden="true" />
            Full report
          </button>
        </div>
      </div>

      {analysis.notices.map((notice) => (
        <Notice key={notice} tone="info" className="mt-5">
          {notice}
        </Notice>
      ))}

      {analysis.summary ? (
        <p className="mt-5 max-w-4xl text-base leading-relaxed text-ink-700">
          {analysis.summary}
        </p>
      ) : null}

      <section className="card card-pad mt-7">
        <div className="stagger grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <AnimatedMetric
            label="Bill total"
            value={totals.bill_total}
            format={(value) => formatMoney(value, currency)}
            hint={`${counts.analyzed} charges analysed`}
          />
          <AnimatedMetric
            label="Comparable charges"
            value={totals.comparable_subtotal}
            format={(value) => formatMoney(value, currency)}
            hint={`${formatPercent(totals.coverage_percent, 0)} of the bill`}
          />
          <Metric
            label="Benchmark range"
            value={totals.benchmark_display}
            hint={totals.benchmark_median_total !== null
              ? `Median ${formatMoney(totals.benchmark_median_total, currency)}`
              : "No comparable records"}
            tone={totals.benchmark_min_total === null ? "muted" : "default"}
          />
          <AnimatedMetric
            label="Coverage"
            value={totals.coverage_percent}
            format={(value) => formatPercent(value)}
            hint={
              totals.coverage_percent < 100
                ? `${counts.insufficient_data + counts.not_comparable} charges not compared`
                : "All charges compared"
            }
            tone={coverageTone}
          />
        </div>

        <div className="mt-6 flex flex-wrap gap-2 border-t border-ink-200 pt-5">
          {counts.attention > 0 ? (
            <FlagPill status="attention" label={`${counts.attention} to check`} />
          ) : null}
          {counts.above_range > 0 ? (
            <FlagPill status="above_range" label={`${counts.above_range} above range`} />
          ) : null}
          {counts.review > 0 ? (
            <FlagPill status="review" label={`${counts.review} need review`} />
          ) : null}
          {counts.within_range > 0 ? (
            <FlagPill status="within_range" label={`${counts.within_range} within range`} />
          ) : null}
          {counts.insufficient_data > 0 ? (
            <FlagPill status="insufficient_data" label={`${counts.insufficient_data} no benchmark`} />
          ) : null}
        </div>
      </section>

      {analysis.flagged.length > 0 ? (
        <section className="mt-8">
          <h2 className="text-xl font-semibold tracking-tight text-ink-900">
            Worth a question
          </h2>
          <p className="mt-1 text-sm text-ink-600">
            These charges sit outside their benchmark range or match weakly. Ask the hospital why
            before treating the difference as a problem.
          </p>
          <div className="stagger mt-4 space-y-3">
            {analysis.flagged.map((row) => (
              <FlaggedCard key={row.id} row={row} currency={currency} />
            ))}
          </div>
        </section>
      ) : (
        <Notice tone="success" className="mt-8" title="Nothing stands out">
          Every charge that had a comparable benchmark sat inside its range. You can still ask
          about anything you did not understand on the bill.
        </Notice>
      )}

      <ScrollReveal as="section" className="stagger mt-8 grid gap-6 lg:grid-cols-2">
        <div className="card card-pad">
          <h2 className="text-base font-semibold text-ink-900">Category vs benchmark range</h2>
          <p className="mt-1 text-sm text-ink-600">
            Grey bands are the benchmark ranges. A blue bar sticking out past its band is what the
            flags are based on.
          </p>
          <div className="mt-4">
            <BenchmarkRangeChart data={analysis.chart_data.category_spend} currency={currency} />
          </div>
          <div className="mt-3 border-t border-ink-200 pt-3">
            <BenchmarkChartLegend />
          </div>
        </div>

        <div className="card card-pad">
          <h2 className="text-base font-semibold text-ink-900">Where the money went</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr] sm:items-center">
            <CategoryShareChart data={analysis.chart_data.category_spend} currency={currency} />
            <CategoryShareLegend data={analysis.chart_data.category_spend} currency={currency} />
          </div>
          <div className="mt-2 border-t border-ink-200 pt-3">
            <h3 className="text-sm font-semibold text-ink-800">By category</h3>
            <CategorySpendChart data={analysis.chart_data.category_spend} currency={currency} height={240} />
          </div>
        </div>
      </ScrollReveal>

      <section className="mt-8">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">
          Questions to ask the billing department
        </h2>
        <div className="mt-4 flex items-start justify-between gap-3">
          <p className="text-sm text-ink-600">
            Neutral questions about the flagged charges and the totals.
          </p>
          <button
            type="button"
            className="btn-ghost btn-sm shrink-0"
            onClick={copyQuestions}
            disabled={analysis.questions.length === 0}
          >
            <ClipboardCopy className="h-3.5 w-3.5" aria-hidden="true" />
            {copied ? "Copied" : "Copy all"}
          </button>
        </div>
        {analysis.questions.length === 0 ? (
          <p className="mt-3 text-sm text-ink-500">
            No questions were generated for this bill. Use the comparison table below to write your
            own.
          </p>
        ) : (
          <ol className="stagger mt-4 space-y-2.5">
            {analysis.questions.map((question, index) => (
              <li key={question} className="card card-lift flex gap-3 p-4">
                <span className="tnum flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
                  {index + 1}
                </span>
                <p className="text-sm leading-relaxed text-ink-800">{question}</p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold tracking-tight text-ink-900">
              Charge-by-charge comparison
            </h2>
            <p className="mt-1 text-sm text-ink-600">
              {pluralize(comparisons.length, "charge")} ·{" "}
              {pluralize(
                comparisons.filter((row) => row.benchmark_available).length,
                "with a benchmark",
                "with a benchmark",
              )}
            </p>
          </div>
          <div className="flex gap-1.5" role="group" aria-label="Filter charges">
            {(
              [
                ["all", "All"],
                ["needs_looking_at", "Worth a question"],
                ["matched", "Has benchmark"],
              ] as [Filter, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                aria-pressed={filter === value}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  filter === value
                    ? "bg-ink-900 text-white"
                    : "bg-ink-100 text-ink-700 hover:bg-ink-200"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-4 overflow-x-auto rounded-lg border border-ink-200 bg-white">
          <table className="w-full min-w-[58rem] text-left text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th scope="col" className="px-3 py-2.5 font-semibold">Charge</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Matched service</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Billed</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Benchmark</th>
                <th scope="col" className="px-3 py-2.5 text-right font-semibold">Difference</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {filtered.map((row) => (
                <ComparisonRow key={row.id} row={row} currency={currency} />
              ))}
            </tbody>
          </table>
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-ink-500">
              No charges match this filter.
            </p>
          ) : null}
        </div>
      </section>

      <section className="mt-10 rounded-xl border border-ink-200 bg-ink-50 p-5">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink-900">
          <Info className="h-4 w-4 text-ink-500" aria-hidden="true" />
          How to read this
        </h2>
        <ul className="mt-3 grid gap-3 text-sm leading-relaxed text-ink-600 sm:grid-cols-2">
          <li>
            <span className="font-medium text-ink-800">Benchmarks are ranges, not fixed prices.</span>{" "}
            A charge inside the range is unremarkable. One outside it is worth a question, not a
            conclusion.
          </li>
          <li>
            <span className="font-medium text-ink-800">Coverage is partial.</span>{" "}
            {formatPercent(totals.coverage_percent)} of this bill was compared, so the totals are
            an indication rather than a verdict.
          </li>
          <li>
            <span className="font-medium text-ink-800">Match quality matters.</span>{" "}
            Each row states which record it matched and how closely, so you can judge the
            comparison yourself.
          </li>
          <li>
            <span className="font-medium text-ink-800">The numbers are deterministic.</span>{" "}
            Ranges, differences and flags come from the analysis engine. Any written explanation is
            {analysis.provider_is_real ? ` generated by ${analysis.provider_name}.` : " templated, because no AI provider key is configured."}
          </li>
        </ul>
        <p className="mt-4 text-xs text-ink-500">{analysis.disclaimer}</p>
      </section>
    </div>
  );
}

function FlaggedCard({ row, currency }: { row: ChargeComparisonOut; currency: string }) {
  const meta = FLAG_META[row.flag_status];
  return (
    <article className="card card-lift p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-semibold text-ink-900">{row.description}</h3>
          <p className="mt-0.5 text-sm text-ink-500">
            {humanize(row.category)}
            {row.matched_service_name ? ` · matched to ${row.matched_service_name}` : ""}
            {row.quantity !== 1 ? ` · ×${row.quantity}` : ""}
          </p>
        </div>
        <FlagPill status={row.flag_status} label={row.flag_label} />
      </div>

      <div className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-ink-500">Billed</p>
          <p className="tnum font-semibold text-ink-900">
            {formatMoney(row.actual_amount, currency)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-ink-500">Benchmark range</p>
          <p className="tnum font-medium text-ink-800">{row.benchmark_display}</p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-ink-500">Difference</p>
          <p className="tnum font-medium text-ink-800">{row.difference_display}</p>
        </div>
      </div>

      {row.flag_reason ? (
        <p className="mt-3 rounded-md bg-ink-50 px-3 py-2 text-sm text-ink-700">
          {row.flag_reason}
        </p>
      ) : null}

      {row.ai_explanation ? (
        <p className="mt-2 text-sm leading-relaxed text-ink-600">{row.ai_explanation}</p>
      ) : null}

      {row.ai_questions.length > 0 ? (
        <ul className="mt-3 space-y-1.5 border-l-2 border-brand-200 pl-3">
          {row.ai_questions.map((question) => (
            <li key={question} className="text-sm leading-relaxed text-ink-700">
              {question}
            </li>
          ))}
        </ul>
      ) : null}

      <p className="mt-3 text-xs text-ink-500">
        {meta.description}
        {row.source_name ? ` Source: ${row.source_name}.` : ""}
        {row.source_date ? ` Record date ${formatDateTime(row.source_date)}.` : ""}
      </p>
    </article>
  );
}

function ComparisonRow({ row, currency }: { row: ChargeComparisonOut; currency: string }) {
  const [open, setOpen] = useState(false);
  const hasDetail =
    Boolean(row.match_reason) ||
    Boolean(row.source_name) ||
    Boolean(row.ai_explanation) ||
    row.ai_questions.length > 0;

  return (
    <>
      <tr className="hover-row align-top">
        <td className="px-3 py-2.5">
          <p className="font-medium text-ink-900">{row.description}</p>
          <p className="text-xs text-ink-500">{humanize(row.category)}</p>
        </td>
        <td className="px-3 py-2.5 text-ink-700">
          {row.matched_service_name ?? "\u2014"}
          {row.match_score > 0 && row.benchmark_available ? (
            <span className="tnum ml-1.5 text-xs text-ink-400">
              ({Math.round(row.match_score * 100)}% match)
            </span>
          ) : null}
        </td>
        <td className="tnum px-3 py-2.5 text-right font-medium text-ink-900">
          {formatMoney(row.actual_amount, currency)}
        </td>
        <td className="tnum px-3 py-2.5 text-right text-ink-700">
          {row.benchmark_display}
        </td>
        <td className="tnum px-3 py-2.5 text-right text-ink-700">
          {row.benchmark_available ? row.difference_display : "\u2014"}
        </td>
        <td className="px-3 py-2.5">
          <div className="flex flex-col items-start gap-1.5">
            <FlagPill status={row.flag_status} label={row.flag_label} />
            {hasDetail ? (
              <button
                type="button"
                className="text-xs text-brand-700 hover:underline"
                onClick={() => setOpen((value) => !value)}
                aria-expanded={open}
              >
                {open ? "Hide detail" : "Why"}
              </button>
            ) : null}
          </div>
        </td>
      </tr>
      {open ? (
        <tr className="anim-expand bg-ink-50">
          <td colSpan={6} className="px-3 py-3 text-sm leading-relaxed text-ink-700">
            {row.match_reason ? <p>{row.match_reason}</p> : null}
            {row.ai_explanation ? (
              <p className={row.match_reason ? "mt-2" : ""}>{row.ai_explanation}</p>
            ) : null}
            {row.ai_questions.length > 0 ? (
              <ul className="mt-2 list-inside list-disc">
                {row.ai_questions.map((question) => (
                  <li key={question}>{question}</li>
                ))}
              </ul>
            ) : null}
            {row.source_name ? (
              <p className="mt-2 text-xs text-ink-500">
                {row.source_name}
                {row.source_url ? (
                  <>
                    {" · "}
                    <a className="link" href={row.source_url} target="_blank" rel="noreferrer">
                      source
                    </a>
                  </>
                ) : null}
                {row.source_date ? ` · ${formatDateTime(row.source_date)}` : null}
                {row.verification_status ? ` · ${humanize(row.verification_status)}` : null}
              </p>
            ) : null}
            <p className="mt-2 text-xs text-ink-500">{row.dataset_label}</p>
          </td>
        </tr>
      ) : null}
    </>
  );
}
