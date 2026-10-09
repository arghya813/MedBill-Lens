/**
 * Bill editor: metadata, comparison context and the charge table.
 *
 * Shared by manual entry and the post-upload review step because the payload is
 * the same shape in both cases. Keeping one implementation means the two paths
 * cannot drift apart and produce different bills for the same data.
 */

import { useMemo } from "react";
import { Plus, Trash2 } from "lucide-react";

import type {
  BillContextInput,
  BillItemInput,
  BillMetadataInput,
  ChargeComparisonOut,
  SelectOption as CategoryOption,
} from "@/api/types";
import { FlagPill } from "@/components/FlagPill";
import { formatMoney } from "@/lib/format";

export interface EditableItem extends BillItemInput {
  /** Client-side key so React rows stay stable across edits and deletes. */
  rowKey: string;
}

let rowCounter = 0;
export function newRowKey(): string {
  rowCounter += 1;
  return `row-${rowCounter}`;
}

export function emptyItem(): EditableItem {
  return {
    rowKey: newRowKey(),
    description: "",
    category: "",
    quantity: 1,
    unit_price: 0,
    total_price: 0,
  };
}

export interface BillEditorProps {
  items: EditableItem[];
  onItemsChange: (items: EditableItem[]) => void;
  metadata: BillMetadataInput;
  onMetadataChange: (metadata: BillMetadataInput) => void;
  context: BillContextInput;
  onContextChange: (context: BillContextInput) => void;
  categories: CategoryOption[];
  hospitals: CategoryOption[];
  rooms: CategoryOption[];
  cities: CategoryOption[];
  countries: CategoryOption[];
  treatments: CategoryOption[];
  /** Per-row comparison status, matched to rows by the client's row key. */
  comparisons?: (ChargeComparisonOut | null)[];
  currency: string;
  readOnlyItems?: boolean;
}

/** Quantity x unit price, unless a total was typed in explicitly. */
export function itemTotal(item: BillItemInput): number {
  const quantity = Number(item.quantity) || 0;
  const unitPrice = Number(item.unit_price) || 0;
  const typed = item.total_price === null || item.total_price === undefined ? 0 : Number(item.total_price);
  return quantity * unitPrice || typed;
}

export function BillEditor({
  items,
  onItemsChange,
  metadata,
  onMetadataChange,
  context,
  onContextChange,
  categories,
  hospitals,
  rooms,
  cities,
  countries,
  treatments,
  comparisons,
  currency,
  readOnlyItems = false,
}: BillEditorProps) {
  const totals = useMemo(() => {
    const subtotal = items.reduce((sum, item) => {
      const value = itemTotal(item);
      // Discounts are negative lines; they reduce the bill rather than adding.
      return item.category === "discount" ? sum - Math.abs(value) : sum + value;
    }, 0);
    return { subtotal, count: items.length };
  }, [items]);

  const updateItem = (rowKey: string, patch: Partial<EditableItem>) => {
    onItemsChange(items.map((item) => (item.rowKey === rowKey ? { ...item, ...patch } : item)));
  };

  return (
    <div className="stagger space-y-8">
      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
          Bill details
        </h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className="field-label" htmlFor="hospital-name">
              Hospital
            </label>
            <input
              id="hospital-name"
              className="field-input"
              value={metadata.hospital_name ?? ""}
              onChange={(event) =>
                onMetadataChange({ ...metadata, hospital_name: event.target.value || null })
              }
              placeholder="Sunrise Multispecialty Hospital"
            />
          </div>
          <div>
            <label className="field-label" htmlFor="bill-number">
              Bill number
            </label>
            <input
              id="bill-number"
              className="field-input"
              value={metadata.bill_number ?? ""}
              onChange={(event) =>
                onMetadataChange({ ...metadata, bill_number: event.target.value || null })
              }
              placeholder="Optional"
            />
          </div>
          <div>
            <label className="field-label" htmlFor="bill-date">
              Bill date
            </label>
            <input
              id="bill-date"
              type="date"
              className="field-input"
              value={metadata.bill_date ?? ""}
              onChange={(event) =>
                onMetadataChange({ ...metadata, bill_date: event.target.value || null })
              }
            />
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
          Comparison context
        </h2>
        <p className="mt-1 text-sm text-ink-500">
          These pick which benchmark records apply. Getting them right matters more than
          anything else here.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="field-label" htmlFor="context-country">
              Country
            </label>
            <select
              id="context-country"
              className="field-input"
              value={context.country ?? ""}
              onChange={(event) =>
                onContextChange({ ...context, country: event.target.value || null })
              }
            >
              <option value="">Not specified</option>
              {countries.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="context-city">
              City
            </label>
            <select
              id="context-city"
              className="field-input"
              value={context.city ?? ""}
              onChange={(event) =>
                onContextChange({ ...context, city: event.target.value || null })
              }
            >
              <option value="">Not specified</option>
              {cities.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="context-hospital-category">
              Hospital type
            </label>
            <select
              id="context-hospital-category"
              className="field-input"
              value={context.hospital_category ?? ""}
              onChange={(event) =>
                onContextChange({ ...context, hospital_category: event.target.value || null })
              }
            >
              <option value="">Not specified</option>
              {hospitals.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="context-treatment">
              Treatment / speciality
            </label>
            <select
              id="context-treatment"
              className="field-input"
              value={context.treatment ?? ""}
              onChange={(event) =>
                onContextChange({ ...context, treatment: event.target.value || null })
              }
            >
              <option value="">Not specified</option>
              {treatments.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="context-room">
              Room category
            </label>
            <select
              id="context-room"
              className="field-input"
              value={context.room_category ?? ""}
              onChange={(event) =>
                onContextChange({ ...context, room_category: event.target.value || null })
              }
            >
              <option value="">Not specified</option>
              {rooms.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-500">
            Charges ({totals.count})
          </h2>
          {!readOnlyItems ? (
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => onItemsChange([...items, emptyItem()])}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              Add charge
            </button>
          ) : null}
        </div>

        <div className="mt-4 overflow-x-auto rounded-lg border border-ink-200">
          <table className="w-full min-w-[46rem] text-left text-sm">
            <thead className="bg-ink-50 text-xs uppercase tracking-wide text-ink-500">
              <tr>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Description
                </th>
                <th scope="col" className="px-3 py-2.5 font-semibold">
                  Category
                </th>
                <th scope="col" className="w-24 px-3 py-2.5 text-right font-semibold">
                  Qty
                </th>
                <th scope="col" className="w-36 px-3 py-2.5 text-right font-semibold">
                  Unit price
                </th>
                <th scope="col" className="w-36 px-3 py-2.5 text-right font-semibold">
                  Total
                </th>
                {comparisons ? (
                  <th scope="col" className="w-56 px-3 py-2.5 font-semibold">
                    Benchmark check
                  </th>
                ) : null}
                {!readOnlyItems ? (
                  <th scope="col" className="w-12 px-3 py-2.5">
                    <span className="sr-only">Remove</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-200">
              {items.map((item, index) => {
                const comparison = comparisons?.[index];
                return (
                  <tr key={item.rowKey} className="hover-row align-middle">
                    <td className="px-3 py-2">
                      <input
                        className="field-input"
                        value={item.description}
                        disabled={readOnlyItems}
                        onChange={(event) =>
                          updateItem(item.rowKey, { description: event.target.value })
                        }
                        placeholder="Consultant doctor fee"
                        aria-label={`Charge ${index + 1} description`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <select
                        className="field-input"
                        value={item.category}
                        disabled={readOnlyItems}
                        onChange={(event) =>
                          updateItem(item.rowKey, { category: event.target.value })
                        }
                        aria-label={`Charge ${index + 1} category`}
                      >
                        <option value="">Select</option>
                        {categories.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        min={0}
                        step="any"
                        className="field-input tnum text-right"
                        value={item.quantity}
                        disabled={readOnlyItems}
                        onChange={(event) =>
                          updateItem(item.rowKey, {
                            quantity: Number(event.target.value) || 0,
                            total_price: undefined,
                          })
                        }
                        aria-label={`Charge ${index + 1} quantity`}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        type="number"
                        step="any"
                        className="field-input tnum text-right"
                        value={item.unit_price}
                        disabled={readOnlyItems}
                        onChange={(event) =>
                          updateItem(item.rowKey, {
                            unit_price: Number(event.target.value) || 0,
                            total_price: undefined,
                          })
                        }
                        aria-label={`Charge ${index + 1} unit price`}
                      />
                    </td>
                    <td className="tnum px-3 py-2 text-right font-medium text-ink-900">
                      {formatMoney(itemTotal(item), currency)}
                    </td>
                    {comparisons ? (
                      <td className="px-3 py-2">
                        {comparison ? (
                          <div className="flex flex-col items-start gap-1">
                            <FlagPill
                              status={comparison.flag_status}
                              label={comparison.flag_label}
                            />
                            <span className="text-xs leading-snug text-ink-500">
                              {comparison.benchmark_display}
                            </span>
                          </div>
                        ) : (
                          <span className="text-xs text-ink-400">{"\u2014"}</span>
                        )}
                      </td>
                    ) : null}
                    {!readOnlyItems ? (
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          className="btn-ghost btn-sm px-2 text-ink-400 hover:text-rose-600"
                          onClick={() =>
                            onItemsChange(items.filter((row) => row.rowKey !== item.rowKey))
                          }
                          aria-label={`Remove charge ${index + 1}`}
                        >
                          <Trash2 className="h-4 w-4" aria-hidden="true" />
                        </button>
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="border-t border-ink-200 bg-ink-50">
              <tr>
                <td colSpan={4} className="px-3 py-2.5 text-right text-sm font-semibold text-ink-700">
                  Subtotal
                </td>
                <td className="tnum px-3 py-2.5 text-right text-sm font-semibold text-ink-900">
                  {formatMoney(totals.subtotal, currency)}
                </td>
                {comparisons ? <td /> : null}
                {!readOnlyItems ? <td /> : null}
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="field-hint">
          Enter discounts as a negative amount in the Discount category. Taxes, if your bill shows
          them separately, can be added as their own line.
        </p>
      </section>
    </div>
  );
}
