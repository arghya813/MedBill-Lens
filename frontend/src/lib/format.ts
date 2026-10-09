import type { FlagStatus, SelectOption } from "@/api/types";

/**
 * Display helpers.
 *
 * Money formatting mirrors the backend's compact style so the same number is
 * rendered identically in the UI and in generated reports. No arithmetic
 * happens here: the API already returns ready-to-use display strings for
 * benchmark ranges and differences.
 */

const NBSP = "\u00a0";

const SYMBOLS: Record<string, string> = {
  INR: "\u20b9",
  USD: "$",
  AUD: "A$",
  EUR: "\u20ac",
  GBP: "\u00a3",
};

/**
 * Display preferences resolved from the user's profile.
 *
 * Money and date formatting are plain helpers called from deep inside tables and
 * charts, so the active settings are published here by `PreferencesProvider`
 * instead of being threaded through every component as props. An explicit
 * argument always wins over these defaults.
 */
export interface DisplayDefaults {
  currency: string;
  /** `lakh` groups as 1,23,456; `million` groups as 123,456. */
  numberStyle: "lakh" | "million";
  showPaise: boolean;
}

let displayDefaults: DisplayDefaults = {
  currency: "INR",
  numberStyle: "lakh",
  showPaise: true,
};

export function setDisplayDefaults(next: DisplayDefaults): void {
  displayDefaults = next;
}

export function getDisplayDefaults(): DisplayDefaults {
  return displayDefaults;
}

function groupingLocale(): string {
  return displayDefaults.numberStyle === "million" ? "en-US" : "en-IN";
}

export function currencySymbol(code: string | null | undefined): string {
  return SYMBOLS[(code ?? "INR").toUpperCase()] ?? code ?? "";
}

/** Full precision with locale-appropriate digit grouping, e.g. `₹ 1,23,450.50`. */
export function formatMoney(
  amount: number | null | undefined,
  currency?: string,
  options: { decimals?: boolean } = {},
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "\u2014";
  const decimals = options.decimals ?? displayDefaults.showPaise;
  const code = currency ?? displayDefaults.currency;
  const formatted = new Intl.NumberFormat(groupingLocale(), {
    minimumFractionDigits: decimals ? 2 : 0,
    maximumFractionDigits: decimals ? 2 : 0,
  }).format(Math.abs(amount));
  const sign = amount < 0 ? "-" : "";
  return `${sign}${currencySymbol(code)}${NBSP}${formatted}`;
}

/**
 * Compact money for tight spaces: `₹1.23L`, `₹43,950`, `₹1.2Cr`.
 * Small amounts keep exact paise-free integers so nothing looks lost.
 */
export function formatMoneyCompact(
  amount: number | null | undefined,
  currency?: string,
): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return "\u2014";
  const code = currency ?? displayDefaults.currency;
  const symbol = currencySymbol(code);
  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  if (abs >= 1_00_00_000) return `${sign}${symbol}${(abs / 1_00_00_000).toFixed(2)}Cr`;
  if (abs >= 1_00_000) return `${sign}${symbol}${(abs / 1_00_000).toFixed(2)}L`;
  if (abs >= 1_000) {
    return `${sign}${symbol}${new Intl.NumberFormat(groupingLocale()).format(abs)}`;
  }
  return `${sign}${symbol}${abs.toFixed(0)}`;
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "\u2014";
  const rounded = Number(value.toFixed(decimals));
  // Avoid rendering "-0.0%" for tiny negative differences.
  const safe = Object.is(rounded, -0) ? 0 : rounded;
  return `${safe.toFixed(decimals)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "\u2014";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Replaces `_`/`-` separated machine values with readable text. */
export function humanize(value: string | null | undefined): string {
  if (!value) return "\u2014";
  const text = value.replace(/[_-]+/g, " ").trim();
  if (!text) return "\u2014";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export interface FlagMeta {
  label: string;
  /** Tailwind classes for the pill. */
  className: string;
  dotClassName: string;
  description: string;
}

/**
 * Flag styling and plain-language meaning.
 *
 * The wording stays strictly factual. Nothing here implies wrongdoing: a
 * charge above a benchmark range is a reason to ask a question, not evidence
 * of an error.
 */
export const FLAG_META: Record<FlagStatus, FlagMeta> = {
  within_range: {
    label: "Within range",
    className: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
    dotClassName: "bg-emerald-500",
    description: "The amount sits inside the benchmark range for comparable records.",
  },
  below_range: {
    label: "Below range",
    className: "bg-sky-50 text-sky-700 ring-sky-600/20",
    dotClassName: "bg-sky-500",
    description: "The amount is lower than the benchmark range. Worth confirming the details.",
  },
  review: {
    label: "Review details",
    className: "bg-amber-50 text-amber-800 ring-amber-600/20",
    dotClassName: "bg-amber-500",
    description: "A hospital-specific detail affects the match. Confirm it before relying on the number.",
  },
  above_range: {
    label: "Above range",
    className: "bg-orange-50 text-orange-700 ring-orange-600/20",
    dotClassName: "bg-orange-500",
    description: "The amount is higher than the benchmark range. A good candidate for a question.",
  },
  attention: {
    label: "Check this",
    className: "bg-rose-50 text-rose-700 ring-rose-600/20",
    dotClassName: "bg-rose-500",
    description: "The amount differs from the benchmark by a large margin relative to the charge.",
  },
  insufficient_data: {
    label: "No benchmark",
    className: "bg-ink-100 text-ink-600 ring-ink-500/20",
    dotClassName: "bg-ink-400",
    description: "We do not have enough comparable records for this charge.",
  },
  not_comparable: {
    label: "Not comparable",
    className: "bg-ink-100 text-ink-600 ring-ink-500/20",
    dotClassName: "bg-ink-400",
    description: "This charge was excluded from the comparison, for example discounts or taxes.",
  },
};

export const FLAG_ORDER: FlagStatus[] = [
  "attention",
  "above_range",
  "review",
  "below_range",
  "within_range",
  "insufficient_data",
  "not_comparable",
];

export const STATUS_LABELS: Record<string, string> = {
  uploaded: "Uploaded",
  extracting: "Reading bill",
  awaiting_confirmation: "Needs your review",
  confirmed: "Confirmed",
  analyzing: "Analysing",
  completed: "Analysis ready",
  failed: "Failed",
};

export function titleCase(value: string): string {
  return humanize(value);
}

/**
 * Normalises a dropdown source into `{value, label}` pairs.
 *
 * The API returns enum lists in two shapes: `{value, label}` objects for
 * categories, and bare strings for cities and treatments. Components should not
 * care which, so they take `SelectOption[]` and this converts on the way in.
 */
export function toOptions(
  source: readonly ({ value: string; label: string } | string)[] | null | undefined,
): SelectOption[] {
  if (!source) return [];
  return source.map((entry) =>
    typeof entry === "string" ? { value: entry, label: humanize(entry) } : entry,
  );
}


export function pluralize(count: number, singular: string, plural?: string): string {
  return `${count} ${count === 1 ? singular : (plural ?? `${singular}s`)}`;
}
