/**
 * Profile and settings.
 *
 * Grouped so the common changes are reachable without scrolling: identity,
 * number formatting, comparison defaults, how the analysis table is filtered,
 * what gets redacted from a shared report, and stored data.
 *
 * Everything here lives in this browser only. There is no server-side account
 * and nothing on this page is transmitted to the API.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Check, Info, RotateCcw, Trash2 } from "lucide-react";

import { Notice } from "@/components/Notice";
import { ScrollReveal } from "@/components/motion";
import { useAppMeta } from "@/state/AppMeta";
import {
  CURRENCY_OPTIONS,
  usePreferences,
  type AnalysisFilter,
  type Density,
  type NumberStyle,
} from "@/state/Preferences";
import { humanize, pluralize, toOptions } from "@/lib/format";
import type { SelectOption } from "@/api/types";

export default function ProfilePage() {
  const {
    preferences,
    hydrated,
    update,
    updateRedaction,
    setDefaultContext,
    clearDefaultContext,
    resetAll,
    clearStoredData,
  } = usePreferences();
  const { options, health } = useAppMeta();
  const [confirmClear, setConfirmClear] = useState(false);

  const cities = useMemo(() => toOptions(options?.cities), [options]);
  const treatments = useMemo(() => toOptions(options?.treatments), [options]);
  const hospitalCategories = useMemo(() => toOptions(options?.hospital_categories), [options]);
  const roomCategories = useMemo(() => toOptions(options?.room_categories), [options]);

  const contextDefaults = [
    preferences.default_city,
    preferences.default_hospital_category,
    preferences.default_treatment,
    preferences.default_room_category,
  ].filter(Boolean).length;

  const enabledOptions = Object.values(preferences.redaction).filter(Boolean).length;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:px-6 sm:py-14">
      <header className="max-w-2xl">
        <h1 className="text-3xl font-semibold tracking-tight text-ink-900">
          Profile &amp; settings
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">
          Your display and privacy preferences. They are saved in this browser and applied
          everywhere in the app. MedBill Lens has no account system, so nothing here is sent to the
          server or shared with anyone.
        </p>
        {hydrated ? null : (
          <p className="mt-2 text-xs text-ink-500">Loading your saved settings.</p>
        )}
      </header>

      <Section
        title="Profile"
        description="A label for this browser. It appears next to the app name so you know which set of preferences you are looking at."
      >
        <label className="block">
          <span className="field-label">Display name</span>
          <input
            type="text"
            value={preferences.display_name}
            maxLength={60}
            placeholder="e.g. My checkup"
            onChange={(event) => update({ display_name: event.target.value })}
            className="field-input"
          />
          <span className="field-hint">
            Optional. Never appears on a report or an exported file.
          </span>
        </label>
      </Section>

      <Section
        title="Numbers"
        description="How amounts are written on screen. This changes formatting only, never the underlying figures or the arithmetic."
      >
        <Choice<NumberStyle>
          label="Digit grouping"
          hint="Lakh grouping follows the Indian convention."
          value={preferences.number_style}
          onChange={(number_style) => update({ number_style })}
          choices={[
            { value: "lakh", label: "Lakh", hint: "12,34,567" },
            { value: "million", label: "Million", hint: "1,234,567" },
          ]}
        />
        <Toggle
          label="Show paise"
          hint="Off rounds every amount to whole units. Underlying values are unchanged."
          checked={preferences.show_paise}
          onChange={(show_paise) => update({ show_paise })}
        />
        <SelectField
          label="Default currency"
          hint="Used for manual entries and any amount the bill does not specify."
          value={preferences.currency_code}
          onChange={(currency_code) => update({ currency_code })}
          options={CURRENCY_OPTIONS.map((code) => ({ value: code, label: code }))}
        />
        <Choice<Density>
          label="Layout density"
          hint="Compact trims vertical spacing in tables and cards."
          value={preferences.density}
          onChange={(density) => update({ density })}
          choices={[
            { value: "comfortable", label: "Comfortable" },
            { value: "compact", label: "Compact" },
          ]}
        />
      </Section>

      <Section
        title="Comparison defaults"
        description={`Pre-filled on the review page so you do not retype the same context each time. ${
          contextDefaults === 0 ? "None set." : `${pluralize(contextDefaults, "field")} set.`
        }`}
        action={
          contextDefaults > 0 ? (
            <button type="button" className="btn-secondary btn-sm" onClick={clearDefaultContext}>
              Clear all
            </button>
          ) : null
        }
      >
        <SelectField
          label="City"
          value={preferences.default_city}
          onChange={(value) => setDefaultContext({ city: value })}
          options={cities}
          placeholder="Any city"
        />
        <SelectField
          label="Hospital type"
          value={preferences.default_hospital_category}
          onChange={(value) => setDefaultContext({ hospital_category: value })}
          options={hospitalCategories}
          placeholder="Any hospital type"
        />
        <SelectField
          label="Treatment"
          value={preferences.default_treatment}
          onChange={(value) => setDefaultContext({ treatment: value })}
          options={treatments}
          placeholder="Any treatment"
        />
        <SelectField
          label="Room category"
          value={preferences.default_room_category}
          onChange={(value) => setDefaultContext({ room_category: value })}
          options={roomCategories}
          placeholder="Any room category"
        />
        <p className="text-xs leading-relaxed text-ink-500">
          A value already present on the bill always wins. These only apply where the bill is silent.
        </p>
      </Section>

      <Section
        title="Analysis view"
        description="Which charges the comparison table shows when it first opens."
      >
        <Choice<AnalysisFilter>
          label="Starting filter"
          value={preferences.default_analysis_filter}
          onChange={(default_analysis_filter) => update({ default_analysis_filter })}
          choices={[
            { value: "all", label: "All charges" },
            { value: "needs_looking_at", label: "Needs looking at" },
            { value: "matched", label: "Matched only" },
          ]}
        />
        <Toggle
          label="Hide charges with no benchmark"
          hint="Removes rows we have no comparable data for. Coverage percentages still account for them."
          checked={preferences.hide_unmatched_charges}
          onChange={(hide_unmatched_charges) => update({ hide_unmatched_charges })}
        />
      </Section>

      <Section
        title="Reports &amp; privacy"
        description="Applied to every report and text export."
        footer={
          enabledOptions === 6 ? "All 6 options are on." : `${enabledOptions} of 6 options are on.`
        }
      >
        <Toggle
          label="Hide patient name"
          checked={preferences.redaction.hide_patient_name}
          onChange={(value) => updateRedaction({ hide_patient_name: value })}
        />
        <Toggle
          label="Hide patient ID"
          checked={preferences.redaction.hide_patient_id}
          onChange={(value) => updateRedaction({ hide_patient_id: value })}
        />
        <Toggle
          label="Hide bill number"
          checked={preferences.redaction.hide_bill_number}
          onChange={(value) => updateRedaction({ hide_bill_number: value })}
        />
        <Toggle
          label="Hide hospital name"
          hint="Leave off if you are sending the report back to the same hospital."
          checked={preferences.redaction.hide_hospital_name}
          onChange={(value) => updateRedaction({ hide_hospital_name: value })}
        />
        <Toggle
          label="Include suggested questions"
          checked={preferences.redaction.include_questions}
          onChange={(value) => updateRedaction({ include_questions: value })}
        />
        <Toggle
          label="Include dataset and source notes"
          checked={preferences.redaction.include_sources}
          onChange={(value) => updateRedaction({ include_sources: value })}
        />
        <Notice tone="warning" title="Turning these off affects what you share">
          The report still records which fields were hidden. Turning a field off means the real
          value appears in the text, so check it before sending anything onward.
        </Notice>
      </Section>

      <Section title="Stored data" description="What this browser keeps between visits.">
        <Toggle
          label="Remember recent bills"
          hint="Stores up to 8 bill ids so you can jump back to them. No bill content is stored in the browser."
          checked={preferences.remember_bills}
          onChange={(remember_bills) => update({ remember_bills })}
        />
        <div className="rounded-lg border border-ink-200 bg-ink-50 px-4 py-3 text-sm text-ink-700">
          <p className="font-medium text-ink-900">Uploaded documents</p>
          <p className="mt-1 leading-relaxed">
            Bills and uploaded files live on the server, not in this browser. Raw uploaded files are
            deleted after {health?.raw_file_retention_minutes ?? 30} minutes.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => (confirmClear ? clearStoredData() : setConfirmClear(true))}
          >
            {confirmClear ? (
              <>
                <AlertTriangle className="h-4 w-4" aria-hidden="true" />
                Click again to confirm
              </>
            ) : (
              <>
                <Trash2 className="h-4 w-4" aria-hidden="true" />
                Clear recent bills
              </>
            )}
          </button>
          {confirmClear ? (
            <p className="mt-2 text-xs text-ink-500">
              This clears only the recent-bill list. Your preferences are kept.{" "}
              <button type="button" className="link" onClick={() => setConfirmClear(false)}>
                Cancel
              </button>
            </p>
          ) : null}
        </div>
      </Section>

      <Section
        title="About this install"
        description="Useful details when reporting a problem."
      >
        <dl className="grid gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
          <Fact label="AI provider" value={humanize(health?.ai_provider ?? "unknown")} />
          <Fact
            label="Real AI calls"
            value={health?.ai_provider_is_real ? "Enabled" : "Off, demo mode"}
          />
          <Fact label="Benchmark records" value={String(health?.benchmark_records ?? "\u2014")} />
          <Fact
            label="Raw file retention"
            value={`${health?.raw_file_retention_minutes ?? "\u2014"} min`}
          />
          <Fact label="Default currency" value={preferences.currency_code} />
          <Fact label="Today" value={new Date().toLocaleDateString()} />
        </dl>
      </Section>

      <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-ink-200 pt-6">
        <button type="button" className="btn-secondary btn-sm" onClick={resetAll}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Reset all settings
        </button>
        <p className="text-xs text-ink-500">
          Restores the defaults. Bills already on the server are not affected.
        </p>
      </div>

      <div className="card card-pad mt-6">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink-900">
          <Info className="h-4 w-4 text-brand-600" aria-hidden="true" />
          Want these to follow you across devices?
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-600">
          That needs real accounts, which this install does not have. Every field on this page maps
          directly onto a user profile record if that is added later.
        </p>
        <Link to="/about" className="btn-secondary btn-sm mt-4">
          Methodology and limitations
        </Link>
      </div>
    </div>
  );
}

function Section({
  title,
  description,
  action,
  footer,
  children,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  footer?: string;
  children: React.ReactNode;
}) {
  return (
    <ScrollReveal as="section" className="card card-lift card-pad mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 max-w-xl">
          <h2 className="text-base font-semibold tracking-tight text-ink-900">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm leading-relaxed text-ink-600">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="mt-5 space-y-5">{children}</div>
      {footer ? <p className="mt-5 text-xs text-ink-500">{footer}</p> : null}
    </ScrollReveal>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 border-b border-ink-100 py-1.5">
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-right font-medium text-ink-900">{value}</dd>
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <span className="relative mt-0.5 inline-flex shrink-0">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => onChange(event.target.checked)}
          className="peer sr-only"
        />
        <span
          aria-hidden="true"
          className="h-5 w-9 rounded-full bg-ink-300 transition-colors duration-200 peer-checked:bg-brand-600 peer-focus-visible:ring-2 peer-focus-visible:ring-brand-500 peer-focus-visible:ring-offset-2"
        />
        <span
          aria-hidden="true"
          className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-200 ease-out peer-checked:translate-x-4"
        />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-medium text-ink-900">{label}</span>
        {hint ? (
          <span className="mt-0.5 block text-xs leading-relaxed text-ink-500">{hint}</span>
        ) : null}
      </span>
    </label>
  );
}

function SelectField({
  label,
  hint,
  value,
  options,
  placeholder,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  options: SelectOption[];
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)} className="field-input">
        {placeholder !== undefined ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}

function Choice<T extends string>({
  label,
  hint,
  value,
  choices,
  onChange,
}: {
  label: string;
  hint?: string;
  value: T;
  choices: { value: T; label: string; hint?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div>
      <p className="field-label">{label}</p>
      <div className="mt-1.5 flex flex-wrap gap-2">
        {choices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            aria-pressed={value === choice.value}
            onClick={() => onChange(choice.value)}
            className={`btn btn-sm ${
              value === choice.value
                ? "bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-600"
                : "border border-ink-300 bg-white text-ink-700 hover:bg-ink-50"
            }`}
          >
            {value === choice.value ? (
              <Check className="h-3.5 w-3.5" aria-hidden="true" />
            ) : null}
            {choice.label}
            {choice.hint ? (
              <span className="font-normal opacity-70">{choice.hint}</span>
            ) : null}
          </button>
        ))}
      </div>
      {hint ? <p className="field-hint">{hint}</p> : null}
    </div>
  );
}