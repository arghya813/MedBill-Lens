import { Link } from "react-router-dom";
import {
  ArrowRight,
  Building2,
  ClipboardList,
  FileText,
  HelpCircle,
  LineChart,
  ListChecks,
  ScanLine,
  ShieldCheck,
} from "lucide-react";

import { useAppMeta } from "@/state/AppMeta";
import { FLAG_META, FLAG_ORDER, formatMoney, pluralize } from "@/lib/format";
import { Notice } from "@/components/Notice";
import { AnimatedNumber, ScrollReveal } from "@/components/motion";

const STEPS = [
  {
    icon: ScanLine,
    title: "Upload your bill",
    body: "Drop in a PDF or a photo of the itemised bill. We read the charges and group them by category.",
  },
  {
    icon: ListChecks,
    title: "Check what we read",
    body: "Every line is shown for you to correct. Nothing is compared until you confirm the numbers are right.",
  },
  {
    icon: LineChart,
    title: "Compare each charge",
    body: "Each charge is matched against benchmark records for your city and hospital type, with the range and source shown.",
  },
  {
    icon: HelpCircle,
    title: "Take questions to the hospital",
    body: "You get a prioritised list of things worth asking the billing department before you pay.",
  },
];

const FLAGS = FLAG_ORDER.filter((status) => status !== "not_comparable");

export default function HomePage() {
  const { health, unreachable } = useAppMeta();

  return (
    <>
      <section className="border-b border-ink-200 bg-gradient-to-b from-white to-ink-50">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
          <div className="grid items-center gap-10 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="stagger">
              <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-800 ring-1 ring-inset ring-brand-600/20">
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                You stay in control of your data
              </span>

              <h1 className="mt-5 text-4xl font-semibold tracking-tight text-ink-900 sm:text-5xl">
                Understand your hospital bill before you pay it.
              </h1>

              <p className="mt-5 max-w-xl text-lg leading-relaxed text-ink-700">
                MedBill Lens reads an itemised hospital bill, shows you exactly what each charge
                is, and compares it against benchmark price ranges. You get clear, factual
                questions to ask the hospital. It never claims a charge is wrong — it shows you
                where the numbers differ so you can ask about them yourself.
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                <Link to="/upload" className="btn-primary">
                  <FileText className="h-4 w-4" aria-hidden="true" />
                  Check a bill
                  <ArrowRight className="h-4 w-4" aria-hidden="true" />
                </Link>
                <Link to="/review" className="btn-secondary">
                  <ClipboardList className="h-4 w-4" aria-hidden="true" />
                  Enter charges manually
                </Link>
                {!unreachable ? (
                  <Link to="/demo" className="btn-ghost">
                    See a worked example
                  </Link>
                ) : null}
              </div>

              <p className="mt-5 text-sm text-ink-500">
                Free to use. No account required.
                {health?.raw_file_retention_minutes
                  ? ` Uploaded files are purged automatically after ${pluralize(
                      health.raw_file_retention_minutes,
                      "minute",
                    )}.`
                  : ""}
              </p>
            </div>

            <ScrollReveal animation="anim-pop" delay={200} className="card card-pad">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-500">
                What the comparison shows
              </p>
              <div className="stagger mt-4 space-y-3">
                {FLAGS.map((status) => {
                  const meta = FLAG_META[status];
                  return (
                    <div key={status} className="flex gap-3">
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${meta.dotClassName}`}
                        aria-hidden="true"
                      />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-ink-900">{meta.label}</p>
                        <p className="text-sm leading-relaxed text-ink-600">{meta.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </ScrollReveal>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
        <h2 className="text-2xl font-semibold tracking-tight text-ink-900">How it works</h2>
        <ol className="stagger mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => (
            <li key={step.title} className="relative">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                  <step.icon className="h-4 w-4" aria-hidden="true" />
                </span>
                <span className="tnum text-xs font-semibold text-ink-400">
                  Step {index + 1}
                </span>
              </div>
              <h3 className="mt-3 text-base font-semibold text-ink-900">{step.title}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-600">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-y border-ink-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-ink-900">
                Built to stay honest about what it knows
              </h2>
              <p className="mt-3 leading-relaxed text-ink-700">
                A benchmark comparison is only useful if you can see where it came from and how far
                it reaches. Every comparison in MedBill Lens shows the range, the number of records
                behind it, and the source. When there is not enough comparable data, we say so
                instead of guessing.
              </p>
              <ul className="stagger mt-6 space-y-4">
                {[
                  {
                    icon: LineChart,
                    title: "Deterministic numbers",
                    body: "Ranges, differences, percentages and flags are computed by the analysis engine, not by a language model. The same bill always produces the same comparison.",
                  },
                  {
                    icon: Building2,
                    title: "Context-aware matching",
                    body: "City, hospital type, treatment and room category narrow the benchmark set, and the report says how closely each charge matched.",
                  },
                  {
                    icon: ShieldCheck,
                    title: "Your confirmation first",
                    body: "Nothing is compared until you have reviewed and confirmed the extracted charges. The analysis is only as good as what you verified.",
                  },
                ].map((item) => (
                  <li key={item.title} className="flex gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ink-100 text-ink-600">
                      <item.icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-ink-900">{item.title}</p>
                      <p className="mt-0.5 text-sm leading-relaxed text-ink-600">{item.body}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="space-y-4">
              <div className="card card-lift card-pad">
                <h3 className="text-sm font-semibold text-ink-900">
                  "Above range" does not mean "wrong"
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-600">
                  Being above a benchmark range is normal and often has an explanation: a higher
                  grade of room, a different implant, an emergency, or a hospital that simply
                  charges more. MedBill Lens flags the difference so you know what to ask about. It
                  does not label anything as an error, and neither should you.
                </p>
              </div>

              <div className="card card-lift card-pad">
                <h3 className="text-sm font-semibold text-ink-900">
                  Benchmarks are a reference, not a price list
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-ink-600">
                  {health
                    ? `${health.benchmark_records.toLocaleString("en-IN")} benchmark records are loaded (${health.benchmark_label}). `
                    : ""}
                  Benchmarks can be outdated, aggregated from different hospitals, or based on
                  package rates. Always check the source shown next to a comparison.
                </p>
                <Link to="/benchmarks" className="link mt-3 inline-flex items-center gap-1 text-sm">
                  Browse the benchmark data
                  <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </div>

              {health && !health.ai_provider_is_real ? (
                <Notice tone="info" title="Running without an AI provider key">
                  Charge reading and every number still work: the built-in demo engine reads text
                  PDFs and produces the same comparisons. Written explanations are templated rather
                  than generated until{" "}
                  <code className="font-mono">MEDBILL_AI_API_KEY</code> is configured.
                </Notice>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-16">
        <ScrollReveal animation="anim-pop" className="card card-pad text-center">
          <h2 className="text-2xl font-semibold tracking-tight text-ink-900">
            Ready to look at your bill?
          </h2>
          <p className="mx-auto mt-3 max-w-lg text-ink-600">
            Upload a document or type the charges in. Either way, you will see every line before
            anything is compared.
          </p>
          <div className="mt-6 flex flex-wrap justify-center gap-3">
            <Link to="/upload" className="btn-primary">
              Upload a bill
            </Link>
            <Link to="/review" className="btn-secondary">
              Enter charges manually
            </Link>
          </div>
          <p className="tnum mt-5 text-xs text-ink-400">
            Figures shown in this app are illustrative. A typical comparison covers a{" "}
            <AnimatedNumber
              value={43950}
              format={(value) => formatMoney(value, "INR", { decimals: false })}
            />{" "}
            hospital bill.
          </p>
        </ScrollReveal>
      </section>
    </>
  );
}
