/**
 * Shareable report.
 *
 * The server owns redaction and report structure, so this page renders exactly
 * what the backend produced and never recomputes anything. A markdown export is
 * offered for copying into an email, which is why it is fetched on demand rather
 * than on every render.
 */

import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Copy, Download, Printer, Settings2 } from "lucide-react";

import { api } from "@/api/client";
import type { ReportResponse, ReportSection } from "@/api/types";
import { PageSkeleton, Spinner } from "@/components/Feedback";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useAsync, useMutation } from "@/hooks/useAsync";
import { formatDateTime } from "@/lib/format";
import { usePreferences } from "@/state/Preferences";
import { BenchmarkChartLegend, BenchmarkRangeChart } from "@/components/BenchmarkRangeChart";
import { CategoryShareChart, CategoryShareLegend, CategorySpendChart } from "@/components/Charts";

export default function ReportPage() {
  const { billId } = useParams<{ billId: string }>();
  const { preferences, hydrated } = usePreferences();
  const [copied, setCopied] = useState(false);

  const { redaction } = preferences;

  const state = useAsync(
    (signal) => api.report(billId ?? "", { ...redaction }, signal),
    [billId, hydrated, redaction],
    { enabled: Boolean(billId) },
  );

  const markdown = useMutation(async () => {
    const response = await api.report(billId ?? "", { format: "markdown", ...redaction });
    return response.markdown ?? "";
  });

  const downloadMarkdown = useCallback(() => {
    void (async () => {
      const content = markdown.error ? null : await markdown.run();
      if (!content) return;
      const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `medbill-lens-${billId?.slice(0, 8) ?? "report"}.md`;
      anchor.click();
      URL.revokeObjectURL(url);
    })();
  }, [billId, markdown]);

  const copyMarkdown = useCallback(() => {
    void (async () => {
      const content = markdown.error ? null : await markdown.run();
      if (!content) return;
      try {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 2000);
      } catch {
        // Clipboard blocked; the user can still use the download button.
      }
    })();
  }, [markdown]);

  const hiddenFields = useMemo(() => {
    const report = state.data;
    if (!report) return [];
    return Object.entries(report.redaction_applied)
      .filter(([, applied]) => applied)
      .map(([field]) => field.replace(/^hide_/, "").replace(/_/g, " "));
  }, [state.data]);

  if (state.loading) return <PageSkeleton label="Building your report" />;

  if (state.error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <ErrorNotice error={state.error} />
        <Link to="/review" className="btn-secondary btn-sm mt-4">
          Back to review
        </Link>
      </div>
    );
  }

  const report = state.data as ReportResponse;
  const currency = preferences.currency_code === "INR" ? "₹" : preferences.currency_code;

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 sm:py-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            to={`/bills/${billId}/analysis`}
            className="inline-flex items-center gap-1 text-sm text-ink-600 hover:text-ink-900"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Back to comparison
          </Link>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-900">
            {report.title}
          </h1>
          <p className="mt-1 text-sm text-ink-500">
            Generated {formatDateTime(report.generated_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-secondary btn-sm" onClick={() => window.print()}>
            <Printer className="h-3.5 w-3.5" aria-hidden="true" />
            Print
          </button>
          <Link to="/profile" className="btn-secondary btn-sm">
            <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />
            Redaction settings
          </Link>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={copyMarkdown}
            disabled={markdown.pending}
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy as text"}
          </button>
          <button
            type="button"
            className="btn-primary btn-sm"
            onClick={downloadMarkdown}
            disabled={markdown.pending}
          >
            {markdown.pending ? <Spinner /> : <Download className="h-3.5 w-3.5" />}
            Download
          </button>
        </div>
      </div>

      {markdown.error ? <ErrorNotice error={markdown.error} className="mt-5" /> : null}

{report.anonymized && hiddenFields.length > 0 ? (
        <Notice tone="info" title="Personal details removed for sharing">
          Hidden in this report: {hiddenFields.join(", ")}.
        </Notice>
      ) : null}

      <article className="stagger mt-7 space-y-8">
        {report.sections.map((section) => (
          <ReportSectionBlock key={section.key} section={section} />
        ))}
      </article>

      {report.chart_data ? (
        <section className="mt-8 space-y-6">
          <div className="card card-pad">
            <h2 className="text-lg font-semibold tracking-tight text-ink-900">Where the money went</h2>
            <p className="mt-1 text-sm text-ink-600">
              Share of the bill by category based on the charges that were analysed.
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-[1fr_1fr] sm:items-center">
              <CategoryShareChart data={report.chart_data.category_spend} currency={currency} />
              <CategoryShareLegend data={report.chart_data.category_spend} currency={currency} />
            </div>
            <div className="mt-6">
              <CategorySpendChart data={report.chart_data.category_spend} currency={currency} height={240} />
            </div>
          </div>

          {report.chart_data.category_spend.length > 0 ? (
            <div className="card card-pad">
              <h2 className="text-lg font-semibold tracking-tight text-ink-900">Category vs benchmark range</h2>
              <p className="mt-1 text-sm text-ink-600">
                Grey bands are the benchmark ranges. A blue bar sticking out past its band shows where the flags
                come from.
              </p>
              <div className="mt-4">
                <BenchmarkRangeChart data={report.chart_data.category_spend} currency={currency} />
              </div>
              <div className="mt-3 border-t border-ink-200 pt-3">
                <BenchmarkChartLegend />
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      <footer className="mt-10 space-y-3 border-t border-ink-200 pt-6 text-sm leading-relaxed text-ink-600">
        <p>{report.disclaimer}</p>
        <p>
          <span className="font-medium text-ink-800">Benchmarks: </span>
          {report.dataset_notice}
        </p>
        <p>
          <span className="font-medium text-ink-800">Explanations: </span>
          {report.ai_notice}
        </p>
        {report.provider_is_real ? (
          <p className="text-xs text-ink-500">
            Provider: {report.provider_name}. All numerical comparisons come from the deterministic
            analysis engine, not the AI.
          </p>
        ) : null}
      </footer>
    </div>
  );
}

function ReportSectionBlock({ section }: { section: ReportSection }) {
  return (
    <section>
      <h2 className="text-lg font-semibold tracking-tight text-ink-900">{section.title}</h2>

      {section.headline ? (
        <p className="mt-1 text-sm font-medium text-ink-600">{section.headline}</p>
      ) : null}

      {section.text ? (
        <p className="mt-3 whitespace-pre-line text-sm leading-relaxed text-ink-700">
          {section.text}
        </p>
      ) : null}

      {section.fields && section.fields.length > 0 ? (
        <dl className="mt-4 grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
          {section.fields
            .filter((field) => field.value !== null && field.value !== "")
            .map((field) => (
              <div key={field.label} className="flex justify-between gap-4 border-b border-ink-100 pb-1.5">
                <dt className="text-sm text-ink-500">{field.label}</dt>
                <dd className="tnum text-right text-sm font-medium text-ink-900">{field.value}</dd>
              </div>
            ))}
        </dl>
      ) : null}

      {section.columns && section.rows && section.rows.length > 0 ? (
        <div className="mt-4 overflow-x-auto rounded-lg border border-ink-200">
          <table className="w-full min-w-[32rem] text-left text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                {section.columns.map((column) => (
                  <th key={column} scope="col" className="px-3 py-2 font-semibold">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {section.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className={`px-3 py-2 ${
                        cellIndex === 0 ? "font-medium text-ink-900" : "tnum text-ink-700"
                      }`}
                    >
                      {cell === null || cell === undefined || cell === "" ? "\u2014" : cell}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {section.items && section.items.length > 0 ? (
        <ul className="mt-3 space-y-1.5 text-sm leading-relaxed text-ink-700">
          {section.items.map((item, index) => (
            <li key={index} className="flex gap-2.5">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" aria-hidden="true" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
