/**
 * Device-local profile and preferences.
 *
 * The backend has no accounts (auth is an off-by-default stub), so this store is
 * deliberately local: values live in `localStorage` on this browser only and are
 * never sent to the server. It is the settings surface that a real account would
 * later sit on top of, so every field here is something a server-side profile
 * could also hold.
 *
 * Every field is wired to real behaviour. There are no decorative toggles.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { setDisplayDefaults } from "@/lib/format";
import type { BillContextInput } from "@/api/types";
import { RECENT_BILLS_STORAGE_KEY } from "@/state/BillSession";

export const STORAGE_KEY = "medbill-lens.preferences.v1";

export type NumberStyle = "lakh" | "million";
export type Density = "comfortable" | "compact";
export type AnalysisFilter = "all" | "needs_looking_at" | "matched";

export interface ReportRedaction {
  hide_patient_name: boolean;
  hide_patient_id: boolean;
  hide_bill_number: boolean;
  hide_hospital_name: boolean;
  include_questions: boolean;
  include_sources: boolean;
}

export interface Preferences {
  display_name: string;
  currency_code: string;
  number_style: NumberStyle;
  show_paise: boolean;
  default_city: string;
  default_hospital_category: string;
  default_treatment: string;
  default_room_category: string;
  default_analysis_filter: AnalysisFilter;
  hide_unmatched_charges: boolean;
  remember_bills: boolean;
  density: Density;
  redaction: ReportRedaction;
}

export const DEFAULT_PREFERENCES: Preferences = {
  display_name: "",
  currency_code: "INR",
  number_style: "lakh",
  show_paise: true,
  default_city: "",
  default_hospital_category: "",
  default_treatment: "",
  default_room_category: "",
  default_analysis_filter: "all",
  hide_unmatched_charges: false,
  remember_bills: true,
  density: "comfortable",
  redaction: {
    hide_patient_name: true,
    hide_patient_id: true,
    hide_bill_number: true,
    hide_hospital_name: false,
    include_questions: true,
    include_sources: true,
  },
};

export const CURRENCY_OPTIONS = ["INR", "USD", "EUR", "GBP"] as const;

interface PreferencesValue {
  preferences: Preferences;
  /** True once the store has been read from storage, to avoid a settings flash. */
  hydrated: boolean;
  update: (patch: Partial<Preferences>) => void;
  updateRedaction: (patch: Partial<ReportRedaction>) => void;
  setDefaultContext: (patch: Partial<BillContextInput>) => void;
  clearDefaultContext: () => void;
  resetAll: () => void;
  clearStoredData: () => void;
}

const PreferencesContext = createContext<PreferencesValue | null>(null);

const isString = (value: unknown): value is string => typeof value === "string";
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";

/**
 * Merges stored values over the defaults, ignoring anything with the wrong type
 * or no longer recognised. A hand-edited or stale `localStorage` entry degrades to
 * defaults for that field instead of breaking the page.
 */
function parseStored(raw: string | null): Preferences {
  if (!raw) return { ...DEFAULT_PREFERENCES };
  let stored: unknown;
  try {
    stored = JSON.parse(raw);
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
  if (!stored || typeof stored !== "object") return { ...DEFAULT_PREFERENCES };
  const source = stored as Record<string, unknown>;

  const oneOf = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
    isString(value) && (allowed as readonly string[]).includes(value) ? (value as T) : fallback;

  const next: Preferences = {
    display_name: isString(source.display_name) ? source.display_name : "",
    currency_code: oneOf(source.currency_code, CURRENCY_OPTIONS, DEFAULT_PREFERENCES.currency_code),
    number_style: oneOf(source.number_style, ["lakh", "million"] as const, "lakh"),
    show_paise: isBoolean(source.show_paise) ? source.show_paise : true,
    default_city: isString(source.default_city) ? source.default_city : "",
    default_hospital_category: isString(source.default_hospital_category)
      ? source.default_hospital_category
      : "",
    default_treatment: isString(source.default_treatment) ? source.default_treatment : "",
    default_room_category: isString(source.default_room_category)
      ? source.default_room_category
      : "",
    default_analysis_filter: oneOf(
      source.default_analysis_filter,
      ["all", "needs_looking_at", "matched"] as const,
      "all",
    ),
    hide_unmatched_charges: isBoolean(source.hide_unmatched_charges)
      ? source.hide_unmatched_charges
      : false,
    remember_bills: isBoolean(source.remember_bills) ? source.remember_bills : true,
    density: oneOf(source.density, ["comfortable", "compact"] as const, "comfortable"),
    redaction: { ...DEFAULT_PREFERENCES.redaction },
  };

  const storedRedaction = source.redaction;
  if (storedRedaction && typeof storedRedaction === "object") {
    const redaction = storedRedaction as Record<string, unknown>;
    for (const key of Object.keys(DEFAULT_PREFERENCES.redaction) as (keyof ReportRedaction)[]) {
      const value = redaction[key];
      if (isBoolean(value)) next.redaction[key] = value;
    }
  }
  return next;
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<Preferences>(() => ({
    ...DEFAULT_PREFERENCES,
  }));
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setPreferences(parseStored(window.localStorage.getItem(STORAGE_KEY)));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    } catch {
      // Storage can be full or blocked (private mode). Preferences then simply
      // live for the session, which is acceptable.
    }
  }, [preferences, hydrated]);

  // Money and date formatting are plain functions used throughout the app, so the
  // resolved display defaults are published on the format module rather than
  // threaded through props.
  useEffect(() => {
    setDisplayDefaults({
      currency: preferences.currency_code,
      numberStyle: preferences.number_style,
      showPaise: preferences.show_paise,
    });
  }, [preferences.currency_code, preferences.number_style, preferences.show_paise]);

  const update = useCallback((patch: Partial<Preferences>) => {
    setPreferences((previous) => ({ ...previous, ...patch }));
  }, []);

  const updateRedaction = useCallback((patch: Partial<ReportRedaction>) => {
    setPreferences((previous) => ({ ...previous, redaction: { ...previous.redaction, ...patch } }));
  }, []);

  const setDefaultContext = useCallback((patch: Partial<BillContextInput>) => {
    setPreferences((previous) => {
      const next: Preferences = { ...previous };
      if (patch.city !== undefined) next.default_city = patch.city ?? "";
      if (patch.hospital_category !== undefined) {
        next.default_hospital_category = patch.hospital_category ?? "";
      }
      if (patch.treatment !== undefined) next.default_treatment = patch.treatment ?? "";
      if (patch.room_category !== undefined) {
        next.default_room_category = patch.room_category ?? "";
      }
      return next;
    });
  }, []);

  const clearDefaultContext = useCallback(() => {
    setPreferences((previous) => ({
      ...previous,
      default_city: "",
      default_hospital_category: "",
      default_treatment: "",
      default_room_category: "",
    }));
  }, []);

  const resetAll = useCallback(() => {
    setPreferences({ ...DEFAULT_PREFERENCES });
  }, []);

  const clearStoredData = useCallback(() => {
    try {
      window.localStorage.removeItem(RECENT_BILLS_STORAGE_KEY);
    } catch {
      // Nothing to clear if storage is unavailable.
    }
    window.location.reload();
  }, []);

  const value = useMemo<PreferencesValue>(
    () => ({
      preferences,
      hydrated,
      update,
      updateRedaction,
      setDefaultContext,
      clearDefaultContext,
      resetAll,
      clearStoredData,
    }),
    [
      preferences,
      hydrated,
      update,
      updateRedaction,
      setDefaultContext,
      clearDefaultContext,
      resetAll,
      clearStoredData,
    ],
  );

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function usePreferences(): PreferencesValue {
  const value = useContext(PreferencesContext);
  if (!value) throw new Error("usePreferences must be used inside PreferencesProvider");
  return value;
}