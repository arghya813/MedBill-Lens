import { FLAG_META } from "@/lib/format";
import type { FlagStatus } from "@/api/types";

/**
 * Status pill for a comparison flag.
 *
 * The full meaning is exposed via `title` so hovering explains the label
 * without cluttering the table.
 */
export function FlagPill({
  status,
  label,
  className = "",
}: {
  status: FlagStatus;
  label?: string;
  className?: string;
}) {
  const meta = FLAG_META[status] ?? FLAG_META.not_comparable;
  return (
    <span
      className={`pill ${meta.className} ${className}`}
      title={meta.description}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dotClassName}`} aria-hidden="true" />
      {label ?? meta.label}
    </span>
  );
}
