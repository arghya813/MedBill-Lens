/**
 * Review and confirm the bill.
 *
 * Two modes share this page:
 *  - no `:billId` in the URL: manual entry, creating the bill on submit.
 *  - with `:billId`: an uploaded bill, loaded and then confirmed.
 *
 * Confirmation is the gate for analysis. The UI states plainly that edits
 * change the comparison, because a stale benchmark match is the most common
 * way these tools mislead people.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowRight, History, Save } from "lucide-react";

import { ApiError, api } from "@/api/client";
import type {
  BillContextInput,
  BillMetadataInput,
  FlagStatus,
  PreviewResponse,
} from "@/api/types";
import {
  BillEditor,
  emptyItem,
  itemTotal,
  type EditableItem,
} from "@/components/BillEditor";
import { FlagPill } from "@/components/FlagPill";
import { PageSkeleton, Spinner } from "@/components/Feedback";
import { ErrorNotice, Notice } from "@/components/Notice";
import { useAppMeta } from "@/state/AppMeta";
import { useBillSession } from "@/state/BillSession";
import { usePreferences } from "@/state/Preferences";
import { formatDate, formatMoney, STATUS_LABELS, toOptions } from "@/lib/format";

const EMPTY_OPTIONS: never[] = [];

/**
 * How each count is phrased in the live summary above the table.
 *
 * Shorter than the full flag labels, because these are totals rather than a
 * verdict on one charge. `not_comparable` is folded into `insufficient_data`.
 */
const COUNT_LABELS: Partial<Record<FlagStatus, string>> = {
  attention: "above benchmark",
  review: "to review",
  within_range: "within benchmark",
  below_range: "below benchmark",
  insufficient_data: "not compared",
};

export default function ReviewPage() {
  const { billId } = useParams<{ billId: string }>();
  const navigate = useNavigate();
  const { options } = useAppMeta();
  const { setBill, setAnalysis, recent, remember } = useBillSession();
  const { preferences, hydrated } = usePreferences();

  const [items, setItems] = useState<EditableItem[]>(() => [emptyItem(), emptyItem(), emptyItem()]);
  const [metadata, setMetadata] = useState<BillMetadataInput>({});
  const [context, setContext] = useState<BillContextInput>({});
  const [loading, setLoading] = useState(Boolean(billId));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [dirty, setDirty] = useState(false);
  const [billCurrency, setBillCurrency] = useState("");
  // Live comparison of the table as typed. Independent of `dirty`, because the
  // point is to see the flags before anything is saved or confirmed.
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState<Error | null>(null);

  // Load the uploaded bill. The server copy is the source of truth; anything the
  // user types afterwards is treated as an edit on top of it.
  useEffect(() => {
    if (!billId) return;
    const controller = new AbortController();
    setLoading(true);
    setLoadError(null);
    api
      .getBill(billId, controller.signal)
      .then((bill) => {
        setBill(bill);
        setBillCurrency(bill.currency_code ?? "");
        setItems(
          bill.items.map((item) => ({
            rowKey: item.id,
            id: item.id,
            description: item.description,
            category: item.category,
            service_name: item.service_name,
            quantity: item.quantity,
            unit_price: item.unit_price,
            total_price: item.total_price,
          })),
        );
        setMetadata({
          hospital_name: bill.hospital_name,
          hospital_location: bill.hospital_location,
          patient_name: bill.patient_name,
          patient_id: bill.patient_id,
          bill_number: bill.bill_number,
          bill_date: bill.bill_date,
          admission_date: bill.admission_date,
          discharge_date: bill.discharge_date,
          room_category: bill.room_category,
          diagnosis: bill.diagnosis,
        });
        setContext({
          city: bill.city,
          country: bill.country,
          hospital_category: bill.hospital_category,
          treatment: bill.treatment,
          room_category: bill.room_category,
        });
        setDirty(false);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setLoadError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [billId]);

  const markDirty = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setDirty(true);
  };

  // Fill only the gaps the bill left. Anything the bill actually states wins, and
  // once the user has edited the form their choices are never overwritten.
  useEffect(() => {
    if (!hydrated || loading || dirty) return;
    setContext((previous) => ({
      city: previous.city || preferences.default_city || undefined,
      hospital_category:
        previous.hospital_category || preferences.default_hospital_category || undefined,
      treatment: previous.treatment || preferences.default_treatment || undefined,
      room_category: previous.room_category || preferences.default_room_category || undefined,
    }));
  }, [
    hydrated,
    loading,
    dirty,
    preferences.default_city,
    preferences.default_hospital_category,
    preferences.default_treatment,
    preferences.default_room_category,
  ]);

  // Re-compare the charges as the user corrects them.
  //
  // Debounced because every keystroke can change a row, and the endpoint is
  // rate limited on purpose: typing must not become a request per character.
  // The previous comparison stays on screen while the next one is in flight,
  // so rows never flash empty mid-edit.
  useEffect(() => {
    if (items.every((item) => item.description.trim() === "")) {
      setPreview(null);
      setPreviewError(null);
      setPreviewing(false);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setPreviewing(true);
      api
        .previewBill(
          {
            bill_id: billId ?? null,
            items: items.map((item) => ({
              key: item.rowKey,
              id: item.id ?? null,
              description: item.description.trim(),
              category: item.category || "other",
              service_name: item.service_name ?? null,
              quantity: Number(item.quantity) || 0,
              unit_price: Number(item.unit_price) || 0,
              total_price: itemTotal(item),
            })),
            context,
          },
          controller.signal,
        )
        .then((response) => {
          setPreview(response);
          setPreviewError(null);
        })
        .catch((cause: unknown) => {
          if (cause instanceof DOMException && cause.name === "AbortError") return;
          // A rate-limit hit while typing quickly is expected: keep the last
          // good comparison rather than replacing it with an error.
          if (cause instanceof ApiError && cause.status === 429) return;
          setPreviewError(cause instanceof Error ? cause : new Error(String(cause)));
        })
        .finally(() => {
          if (!controller.signal.aborted) setPreviewing(false);
        });
    }, 1500);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [billId, items, context]);

  const currency = billCurrency || preferences.currency_code;
  const editable = useMemo(() => items.filter((item) => item.description.trim() !== ""), [items]);

  // The editor matches by row key, never by position: a blank row skipped by
  // the server, or a row the user just inserted, must not shift every status
  // one place down the table.
  const comparisonCells = useMemo(() => {
    if (!preview) return null;
    const byKey = new Map(preview.comparisons.map((row) => [row.id, row]));
    return items.map((item) => byKey.get(item.rowKey) ?? null);
  }, [preview, items]);

  const previewCounts = useMemo(() => {
    if (!preview) return [];
    const counts = preview.counts;
    return (
      [
        ["attention", counts.attention],
        ["review", counts.review],
        ["within_range", counts.within_range],
        ["below_range", counts.below_range],
        ["insufficient_data", counts.insufficient_data + counts.not_comparable],
      ] as [FlagStatus, number][]
    ).filter(([status, count]) => count > 0 && COUNT_LABELS[status]);
  }, [preview]);

  const missingContext = useMemo(() => {
    const gaps: string[] = [];
    if (!context.city) gaps.push("city");
    if (!context.hospital_category) gaps.push("hospital type");
    if (!context.treatment) gaps.push("treatment");
    if (!context.room_category) gaps.push("room category");
    return gaps;
  }, [context]);

  const submit = useCallback(
    async (markConfirmed: boolean) => {
      setPending(true);
      setError(null);
      try {
        const payloadItems = editable.map((item) => ({
          id: item.id,
          description: item.description.trim(),
          category: item.category || "other",
          service_name: item.service_name ?? null,
          quantity: Number(item.quantity) || 0,
          unit_price: Number(item.unit_price) || 0,
          total_price: itemTotal(item),
        }));

        // Manual entry wraps the bill in an envelope; an update returns the
        // bare bill. Normalise to one shape so callers never have to branch.
        const response = billId
          ? await api.updateBillItems(billId, {
              items: payloadItems,
              metadata,
              context,
              mark_confirmed: markConfirmed,
            })
          : (await api.createManualBill({ items: payloadItems, metadata, context })).bill;

        setBill(response);
        remember(response.id);
        setDirty(false);
        if (markConfirmed) {
          // Confirming alone stores the bill but produces no comparison: the
          // analysis page renders its graphs from a stored analysis, so run it
          // here. Without this call the user would land on yet another "run
          // the comparison" button instead of the charts.
          try {
            const result = await api.analyzeBill(response.id);
            setAnalysis(result.analysis);
          } catch (cause) {
            setError(cause instanceof Error ? cause : new Error(String(cause)));
            return;
          }
        }
        navigate(`/bills/${response.id}/analysis`);
      } catch (cause) {
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      } finally {
        setPending(false);
      }
    },
    [billId, context, editable, metadata, navigate, remember, setAnalysis, setBill],
  );

  if (loading) return <PageSkeleton label="Loading your bill" />;

  if (loadError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
        <ErrorNotice error={loadError} />
        <div className="mt-4 flex gap-3">
          <Link to="/upload" className="btn-secondary btn-sm">
            Upload again
          </Link>
          <Link to="/review" className="btn-ghost btn-sm">
            Enter charges manually
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 sm:py-12">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
            {billId ? "Check what we read" : "Enter your charges"}
          </h1>
          <p className="mt-2 max-w-2xl text-ink-600">
            {billId
              ? "We read the charges below from your document. Correct anything that looks wrong, then confirm so we can compare them."
              : "Type the charges from your bill. You will get exactly the same comparison as the upload flow."}
          </p>
        </div>
        {billId ? (
          <span className="pill bg-amber-50 text-amber-800 ring-amber-600/20">
            Status: {STATUS_LABELS.awaiting_confirmation}
          </span>
        ) : null}
      </div>

      {recent.length > 0 && !billId ? (
        <div className="mt-6 flex flex-wrap items-center gap-2 text-sm text-ink-600">
          <History className="h-4 w-4 text-ink-400" aria-hidden="true" />
          <span>Recent bills:</span>
          {recent.slice(0, 4).map((id) => (
            <Link
              key={id}
              to={`/bills/${id}`}
              className="rounded-full bg-ink-100 px-2.5 py-1 font-mono text-xs text-ink-700 hover:bg-ink-200"
            >
              {id.slice(0, 8)}
            </Link>
          ))}
        </div>
      ) : null}

      {preview ? (
        <Notice
          tone={preview.counts.attention > 0 || preview.counts.review > 0 ? "warning" : "info"}
          className="mt-8"
          title="Benchmark check on the charges below"
        >
          <p>{preview.headline}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {previewCounts.map(([status, count]) => (
              <FlagPill
                key={status}
                status={status}
                label={`${count} ${COUNT_LABELS[status]}`}
              />
            ))}
            <span className="text-xs text-ink-500">{preview.dataset_label}</span>
          </div>
          {previewing ? (
            <p className="mt-2 text-xs text-ink-500">Updating the check…</p>
          ) : null}
        </Notice>
      ) : previewError ? (
        <ErrorNotice error={previewError} className="mt-8" />
      ) : null}

      <div className="mt-8">
        <BillEditor
          items={items}
          onItemsChange={markDirty(setItems)}
          metadata={metadata}
          onMetadataChange={markDirty(setMetadata)}
          context={context}
          onContextChange={markDirty(setContext)}
          categories={options?.categories ?? EMPTY_OPTIONS}
          hospitals={options?.hospital_categories ?? EMPTY_OPTIONS}
          rooms={options?.room_categories ?? EMPTY_OPTIONS}
          cities={toOptions(options?.cities)}
          countries={options?.countries ?? EMPTY_OPTIONS}
          treatments={toOptions(options?.treatments)}
          comparisons={comparisonCells ?? undefined}
          currency={currency}
        />
      </div>

      {missingContext.length > 0 ? (
        <Notice tone="warning" className="mt-6" title="Comparison will be broader than ideal">
          We are missing your {missingContext.join(", ")}. The comparison still works, but it will
          fall back to wider national ranges, so some charges may show no benchmark at all.
        </Notice>
      ) : null}

      {error ? <ErrorNotice error={error} className="mt-6" /> : null}

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-ink-200 pt-6">
        {billId ? (
          <>
            <button
              type="button"
              className="btn-primary"
              onClick={() => submit(true)}
              disabled={pending || editable.length === 0}
            >
              {pending ? <Spinner /> : <Save className="h-4 w-4" aria-hidden="true" />}
              Confirm and compare
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => submit(false)}
              disabled={pending || editable.length === 0}
            >
              Save without confirming
            </button>
          </>
        ) : (
          <button
            type="button"
            className="btn-primary"
            onClick={() => submit(true)}
            disabled={pending || editable.length === 0}
          >
            {pending ? <Spinner /> : null}
            Compare these charges
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        )}

        {dirty && billId ? (
          <span className="text-sm text-amber-700">
            You have unsaved edits. Confirming will re-run the comparison with them.
          </span>
        ) : null}
      </div>

      {editable.length === 0 ? (
        <p className="mt-3 text-sm text-ink-500">
          Add at least one charge with a description to continue.
        </p>
      ) : null}

      <div className="mt-10 rounded-xl bg-ink-100/70 p-5">
        <h2 className="text-sm font-semibold text-ink-900">Why confirm before comparing?</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">
          Automated reading is a starting point, not the truth. If a charge is missing or
          misread, every number that depends on it is wrong too. Confirming tells the analysis
          engine which version of the bill to use
          {billId && metadata.bill_date ? ` (bill dated ${formatDate(metadata.bill_date)})` : ""}.
          The bill total on your document is currently{" "}
          <span className="tnum font-medium">
            {formatMoney(
              editable.reduce((sum, item) => sum + itemTotal(item), 0),
              currency,
            )}
          </span>
          .
        </p>
      </div>
    </div>
  );
}
