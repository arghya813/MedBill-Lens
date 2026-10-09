import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

export type NoticeTone = "info" | "success" | "warning" | "error";

const TONE_STYLES: Record<NoticeTone, { wrap: string; icon: string }> = {
  info: { wrap: "bg-brand-50 text-brand-900 ring-brand-600/20", icon: "text-brand-600" },
  success: {
    wrap: "bg-emerald-50 text-emerald-900 ring-emerald-600/20",
    icon: "text-emerald-600",
  },
  warning: {
    wrap: "bg-amber-50 text-amber-900 ring-amber-600/20",
    icon: "text-amber-600",
  },
  error: { wrap: "bg-rose-50 text-rose-900 ring-rose-600/20", icon: "text-rose-600" },
};

const ICONS: Record<NoticeTone, typeof Info> = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  error: AlertCircle,
};

export function Notice({
  tone = "info",
  title,
  children,
  className = "",
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  const Icon = ICONS[tone];
  const style = TONE_STYLES[tone];
  return (
    <div
      className={`anim-rise rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${style.wrap} ${className}`}
    >
      <div className="flex gap-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${style.icon}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          {title ? <p className="font-semibold">{title}</p> : null}
          {children ? <div className={title ? "mt-1 opacity-90" : "opacity-90"}>{children}</div> : null}
        </div>
      </div>
    </div>
  );
}

/**
 * Renders an `Error` from the API layer.
 *
 * Domain errors arrive as `ApiError` with a user-facing `message` plus optional
 * field-level `hint`, so validation problems are shown in full rather than
 * collapsed into a generic failure.
 */
export function ErrorNotice({ error, className = "" }: { error: Error; className?: string }) {
  const hints =
    "code" in error && Array.isArray((error as { fieldHints?: string[] }).fieldHints)
      ? ((error as unknown as { fieldHints: string[] }).fieldHints ?? [])
      : [];

  return (
    <Notice tone="error" title={error.message} className={className}>
      {hints.length > 0 ? (
        <ul className="mt-1 list-inside list-disc space-y-0.5">
          {hints.map((hint) => (
            <li key={hint}>{hint}</li>
          ))}
        </ul>
      ) : null}
    </Notice>
  );
}
