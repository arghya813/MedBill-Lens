/**
 * Methodology, data provenance and limitations.
 *
 * This page exists so the claims made elsewhere in the app can be checked. It
 * states what the engine actually does, what the AI does not do, and where the
 * product is deliberately cautious.
 */

import { Link } from "react-router-dom";
import { CheckCircle2, XCircle } from "lucide-react";

import { Notice } from "@/components/Notice";
import { useAppMeta } from "@/state/AppMeta";
import { formatDateTime } from "@/lib/format";

const DOES = [
  "Reads the line items, quantities and totals from a document, and lets you correct them before anything is compared.",
  "Selects benchmark records that match your city, hospital type, treatment and room category, and shows the range, record count and source for every charge.",
  "Computes the difference from the median, how far a charge sits above or below its range, and which charges are worth asking about.",
  "Explains how much of the bill was actually comparable, so a partial comparison is never presented as a complete one.",
  "Produces neutral, factual questions for the hospital billing department.",
];

const DOES_NOT = [
  "Judge whether a charge is correct. Only the hospital knows what was actually provided and billed.",
  "Detect fraud, overcharging, or malpractice. It has no evidence of intent and never claims any.",
  "Guarantee savings. Charges above a range are often legitimate and well explained.",
  "Replace advice from a doctor, a lawyer or an accountant.",
  "Learn from your bill. Your document is not used to improve the model.",
];

export default function AboutPage() {
  const { health, disclaimer } = useAppMeta();

  return (
    <div className="mx-auto max-w-4xl px-4 py-10 sm:px-6 sm:py-12">
      <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
        Methodology and limitations
      </h1>
      <p className="mt-2 text-ink-600">
        Everything below describes how the numbers are produced, so you can decide how much weight
        to put on them.
      </p>

      <section className="mt-8 grid gap-5 sm:grid-cols-2">
        <div className="card card-pad">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" aria-hidden="true" />
            What it does
          </h2>
          <ul className="mt-3 space-y-2.5 text-sm leading-relaxed text-ink-700">
            {DOES.map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                {item}
              </li>
            ))}
          </ul>
        </div>
        <div className="card card-pad">
          <h2 className="flex items-center gap-2 text-base font-semibold text-ink-900">
            <XCircle className="h-5 w-5 text-rose-600" aria-hidden="true" />
            What it does not do
          </h2>
          <ul className="mt-3 space-y-2.5 text-sm leading-relaxed text-ink-700">
            {DOES_NOT.map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-rose-400" />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">
          How a comparison is produced
        </h2>
        <ol className="stagger mt-4 space-y-4">
          {[
            {
              title: "1. Read the document",
              body: "Text PDFs are parsed directly. Scanned PDFs and images go through optical character recognition. You then review every extracted charge, because extraction is a starting point rather than the truth.",
            },
            {
              title: "2. Match each charge to benchmark records",
              body: "A charge is matched on its description and category, then narrowed by city, hospital type, treatment and room category. The analysis reports the matched service name and how close the match was, so you can judge it yourself.",
            },
            {
              title: "3. Compute a range and a difference",
              body: "For the matched records, the minimum, median and maximum are computed, along with the difference from the median and how far outside the range a charge sits. This arithmetic is deterministic: the same bill always produces the same result.",
            },
            {
              title: "4. Apply transparent thresholds",
              body: "Charges are labelled within range, below range, above range, worth checking, no benchmark, or not comparable, using fixed thresholds. The thresholds in use are recorded with every analysis and shown on the comparison page.",
            },
            {
              title: "5. Measure coverage",
              body: "If only part of the bill could be compared, the coverage percentage says so. A comparison covering 40% of a bill is presented as partial, not as a verdict on the whole bill.",
            },
          ].map((step) => (
            <li key={step.title} className="card p-5">
              <h3 className="font-semibold text-ink-900">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">
          Where the AI fits in
        </h2>
        <div className="mt-4 space-y-4 text-sm leading-relaxed text-ink-700">
          <p>
            The numbers never come from a language model. Reading a document may use one, and the
            written explanations, questions and summary may use one, but every range, difference,
            percentage and flag is computed by the analysis engine. That separation is the point:
            a model that is good at writing cannot be trusted to do arithmetic on your bill.
          </p>
          <p>
            {health?.ai_provider_is_real
              ? `This server is configured with ${health.ai_provider}. Written explanations are generated by that provider; comparisons remain deterministic.`
              : "No AI provider key is configured on this server, so reading falls back to the built-in demo engine and written explanations are templated. Every number works exactly the same either way."}
          </p>
          <p>
            Explanations are written to be neutral. They describe what the numbers are, not what
            anyone intended, and never suggest that a provider is at fault.
          </p>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold tracking-tight text-ink-900">
          Known limitations
        </h2>
        <ul className="mt-4 space-y-2.5 text-sm leading-relaxed text-ink-700">
          {[
            "Handwritten notes, stamps over text and very poor scans can produce extraction errors. Check the review screen every time.",
            "Benchmark packages are sometimes fixed-price plans rather than itemised prices, which makes a direct comparison misleading.",
            "A rare procedure may have few or no comparable records. We report that rather than extrapolating.",
            "Hospitals negotiate rates privately, so a published benchmark can sit well below what a given patient is actually charged.",
            "Benchmark records age. The record date is shown next to each comparison so you can judge how current it is.",
            "Currency and price inflation are not adjusted for. Comparisons assume the benchmark and the bill are in the same currency and period.",
          ].map((item) => (
            <li key={item} className="flex gap-2.5">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink-400" />
              {item}
            </li>
          ))}
        </ul>
      </section>

      {health ? (
        <section className="mt-10">
          <h2 className="text-xl font-semibold tracking-tight text-ink-900">
            This server
          </h2>
          <dl className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2">
            {[
              ["Version", `${health.app} ${health.version}`],
              ["Environment", health.environment],
              ["AI provider", health.ai_provider_is_real ? health.ai_provider : `${health.ai_provider} (no API key configured)`],
              ["Benchmark records", health.benchmark_records.toLocaleString("en-IN")],
              ["Benchmark label", health.benchmark_label],
              ["Database", health.database],
              ["Max upload", `${health.max_upload_size_mb} MB`],
              ["Raw file retention", `${health.raw_file_retention_minutes} minutes`],
              ["Server time", formatDateTime(health.server_time)],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 border-b border-ink-100 pb-2">
                <dt className="text-ink-500">{label}</dt>
                <dd className="tnum text-right font-medium text-ink-900">{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <section className="mt-10 space-y-3">
        {disclaimer ? (
          <Notice tone="warning" title={disclaimer.main}>
            <p className="mt-1">{disclaimer.tool_notice}</p>
            <p className="mt-1">{disclaimer.privacy_notice}</p>
          </Notice>
        ) : null}
        <p className="text-sm text-ink-600">
          Want to see it work?{" "}
          <Link to="/demo" className="link">
            Run a demo scenario
          </Link>{" "}
          or{" "}
          <Link to="/benchmarks" className="link">
            browse the benchmark data
          </Link>
          .
        </p>
      </section>
    </div>
  );
}
