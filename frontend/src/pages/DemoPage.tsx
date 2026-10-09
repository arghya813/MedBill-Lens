/**
 * One-click demo scenarios.
 *
 * Each scenario runs the entire pipeline server-side and lands on the real
 * analysis page, so what a visitor sees here is exactly what their own bill
 * will produce. Every number is synthetic and labelled as such.
 */

import { useNavigate } from "react-router-dom";
import { ArrowRight, FileText, FlaskConical, Play } from "lucide-react";

import { api } from "@/api/client";
import { Spinner } from "@/components/Feedback";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useAsync, useMutation } from "@/hooks/useAsync";
import { useAppMeta } from "@/state/AppMeta";
import { useBillSession } from "@/state/BillSession";
import { formatFileSize } from "@/lib/format";

export default function DemoPage() {
  const navigate = useNavigate();
  const { health, unreachable } = useAppMeta();
  const { remember } = useBillSession();

  const scenarios = useAsync((signal) => api.demoScenarios(signal), []);
  const samples = useAsync((signal) => api.sampleBills(signal), []);

  const run = useMutation(async (key: string) => {
    const response = await api.runDemoScenario(key);
    remember(response.analysis.bill_id);
    navigate(`/bills/${response.analysis.bill_id}/analysis`);
  });

  /**
   * Loads a scenario as a confirmed bill without analysing it, so the user can
   * walk through the review step themselves. The bill id comes from the server:
   * it is created fresh on every call.
   */
  const load = useMutation(async (key: string) => {
    const response = await api.loadDemoScenario(key);
    remember(response.bill.id);
    navigate(`/bills/${response.bill.id}`);
  });

  if (unreachable || health?.demo_mode === false) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <Notice tone="info" title="Demo mode is disabled on this server">
          The demo scenarios are synthetic data and can be turned off with{" "}
          <code className="font-mono">MEDBILL_DEMO_MODE=false</code>. Uploading your own bill
          works either way.
        </Notice>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
      <span className="inline-flex items-center gap-2 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800 ring-1 ring-inset ring-amber-600/20">
        <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
        Synthetic demo data
      </span>

      <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink-900">
        See how the comparison works
      </h1>
      <p className="mt-2 max-w-3xl text-ink-600">
        Three example bills covering different situations. Each one runs the complete pipeline:
        reading the document, confirming the charges, comparing against benchmarks and generating
        questions. Hospital names, amounts and benchmark values are all fictional.
      </p>

      {scenarios.error ? <ErrorNotice error={scenarios.error} className="mt-6" /> : null}
      {run.error ? <ErrorNotice error={run.error} className="mt-6" /> : null}
      {load.error ? <ErrorNotice error={load.error} className="mt-6" /> : null}

      <div className="mt-8 grid gap-5 lg:grid-cols-3">
        {(scenarios.data?.scenarios ?? []).map((scenario) => (
          <article key={scenario.key} className="card card-lift card-pad flex flex-col">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-ink-900">{scenario.title}</h2>
                <p className="mt-1 text-sm leading-relaxed text-ink-600">{scenario.description}</p>
              </div>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-sm font-bold text-brand-700">
                {scenario.key}
              </span>
            </div>

            <div className="mt-4 rounded-lg bg-ink-50 p-3">
              <p className="text-xs font-medium uppercase tracking-wide text-ink-500">
                What this shows
              </p>
              <p className="mt-1 text-sm leading-relaxed text-ink-700">{scenario.expectation}</p>
            </div>

            <div className="mt-5 flex-1" />

            <button
              type="button"
              className="btn-primary w-full"
              onClick={() => void run.run(scenario.key)}
              disabled={run.pending}
            >
              {run.pending ? <Spinner /> : <Play className="h-4 w-4" aria-hidden="true" />}
              {run.pending ? "Running" : "Run this scenario"}
              {!run.pending ? <ArrowRight className="h-4 w-4" aria-hidden="true" /> : null}
            </button>
          </article>
        ))}

        {scenarios.loading
          ? Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="card h-56 animate-pulse bg-ink-100/60" />
            ))
          : null}
      </div>

      <section className="mt-12">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">Sample documents</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-600">
          The same bills are available as files. Download one and run it through the normal upload
          flow to see the extraction path end to end.
        </p>

        {samples.error ? <ErrorNotice error={samples.error} className="mt-4" /> : null}

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {(samples.data?.files ?? []).map((file) => (
            <div key={file.filename} className="card flex items-center gap-3 p-4">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-ink-100 text-ink-600">
                <FileText className="h-4 w-4" aria-hidden="true" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink-900">{file.filename}</p>
                <p className="tnum text-xs text-ink-500">
                  {file.format.toUpperCase()} · {formatFileSize(file.size_bytes)}
                  {file.scenario ? ` · Scenario ${file.scenario}` : ""}
                </p>
              </div>
              {file.scenario ? (
                <button
                  type="button"
                  className="btn-ghost btn-sm shrink-0"
                  onClick={() => void load.run(file.scenario as string)}
                  disabled={load.pending}
                >
                  Open
                </button>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section className="mt-12 rounded-xl bg-ink-100/70 p-5">
        <h2 className="text-sm font-semibold text-ink-900">Why demo data matters</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">
          Benchmark comparisons are only trustworthy if you know where the numbers came from. In
          demo mode both the bills and the benchmark dataset are generated, which lets you explore
          the product without uploading a real document. When a real dataset is configured the same
          interface runs against verified public records and the dataset label changes
          accordingly.
        </p>
      </section>
    </div>
  );
}
