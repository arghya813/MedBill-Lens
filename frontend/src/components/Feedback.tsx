import type { ReactNode } from "react";

import { AnimatedNumber, ScrollReveal } from "@/components/motion";

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg
      className={`animate-spin ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path
        d="M22 12a10 10 0 0 0-10-10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Announced to screen readers while the visible placeholder stays decorative. */
function LoadingRegion({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/**
 * Page-shaped placeholder. Used as the Suspense fallback, so it should roughly
 * match the page it replaces to avoid a jarring reflow when content arrives.
 */
export function PageSkeleton({ label = "Loading" }: { label?: string }) {
  return (
    <LoadingRegion label={label}>
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
        <div className="skeleton skeleton-sheen h-8 w-2/3 max-w-md" />
        <div className="skeleton skeleton-sheen mt-3 h-4 w-1/2 max-w-sm" />
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="card card-pad">
              <div className="skeleton skeleton-sheen h-3 w-20" />
              <div className="skeleton skeleton-sheen mt-3 h-6 w-28" />
              <div className="skeleton skeleton-sheen mt-2 h-3 w-24" />
            </div>
          ))}
        </div>
        <div className="mt-6 space-y-3">
          {Array.from({ length: 3 }, (_, index) => (
            <div key={index} className="card h-24 p-4">
              <div className="skeleton skeleton-sheen h-4 w-1/3" />
              <div className="skeleton skeleton-sheen mt-3 h-3 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <LoadingRegion label={label}>
      <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 sm:py-12">
        <div className="flex items-center gap-3 text-sm text-ink-500">
          <Spinner className="h-4 w-4" />
          <span>{label}…</span>
        </div>
        <div className="mt-6 space-y-3">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="skeleton skeleton-sheen h-16 w-full" />
          ))}
        </div>
      </div>
    </LoadingRegion>
  );
}

/** Placeholder shaped like the analysis metric row. */
export function MetricSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index}>
          <div className="skeleton skeleton-sheen h-3 w-24" />
          <div className="skeleton skeleton-sheen mt-2 h-7 w-32" />
          <div className="skeleton skeleton-sheen mt-2 h-3 w-20" />
        </div>
      ))}
    </div>
  );
}

/** Placeholder shaped like a chart panel. */
export function ChartSkeleton({ height = 240 }: { height?: number }) {
  return (
    <div
      className="flex items-end gap-2"
      style={{ height }}
      aria-hidden="true"
    >
      {[45, 70, 55, 85, 60, 75, 50].map((heightPercent, index) => (
        <div
          key={index}
          className="skeleton skeleton-sheen flex-1 rounded-t"
          style={{ height: `${heightPercent}%` }}
        />
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="skeleton skeleton-sheen h-10 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <ScrollReveal animation="anim-pop">
      <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-ink-300 bg-ink-50/60 px-6 py-12 text-center">
        {icon ? <div className="text-ink-400">{icon ? <span className="anim-pop block">{icon}</span> : null}</div> : null}
        <p className="text-sm font-semibold text-ink-800">{title}</p>
        {children ? <div className="max-w-md text-sm text-ink-600">{children}</div> : null}
        {action}
      </div>
    </ScrollReveal>
  );
}

/** Simple key/value metric used across the summary and report views. */
export function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "positive" | "warning" | "danger" | "muted";
}) {
  const valueTone = {
    default: "text-ink-900",
    positive: "text-emerald-700",
    warning: "text-amber-700",
    danger: "text-orange-700",
    muted: "text-ink-500",
  }[tone];

  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={`tnum mt-1 text-lg font-semibold ${valueTone}`}>{value}</p>
      {hint ? <p className="mt-0.5 text-xs text-ink-500">{hint}</p> : null}
    </div>
  );
}

/**
 * Metric whose number counts up on first view. `format` keeps currency and
 * grouping decisions with the caller, so this stays presentation-only.
 */
export function AnimatedMetric({
  label,
  value,
  format,
  hint,
  tone = "default",
}: {
  label: string;
  value: number;
  format: (value: number) => string;
  hint?: ReactNode;
  tone?: "default" | "positive" | "warning" | "danger" | "muted";
}) {
  const valueTone = {
    default: "text-ink-900",
    positive: "text-emerald-700",
    warning: "text-amber-700",
    danger: "text-orange-700",
    muted: "text-ink-500",
  }[tone];

  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-ink-500">{label}</p>
      <p className={`tnum mt-1 text-lg font-semibold ${valueTone}`}>
        <AnimatedNumber value={value} format={format} />
      </p>
      {hint ? <p className="mt-0.5 text-xs text-ink-500">{hint}</p> : null}
    </div>
  );
}
