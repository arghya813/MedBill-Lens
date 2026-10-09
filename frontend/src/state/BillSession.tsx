/**
 * The bill currently being worked on.
 *
 * The lifecycle is upload -> extract -> review/confirm -> analyse -> report, and
 * the user can move between those steps freely. Holding the bill id (and the
 * latest server copy) in one place keeps every page consistent after an edit
 * without refetching on each navigation.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { AnalysisOut, BillOut } from "@/api/types";
import { usePreferences } from "@/state/Preferences";

interface BillSession {
  bill: BillOut | null;
  analysis: AnalysisOut | null;
  setBill: (bill: BillOut | null) => void;
  setAnalysis: (analysis: AnalysisOut | null) => void;
  /** Ids of the last few bills, newest first, for the "recent bills" list. */
  recent: string[];
  remember: (billId: string) => void;
  forget: (billId: string) => void;
}

const BillSessionContext = createContext<BillSession | null>(null);

export const RECENT_BILLS_STORAGE_KEY = "medbill-lens.recent-bills";
const STORAGE_KEY = RECENT_BILLS_STORAGE_KEY;
const MAX_RECENT = 8;

function readRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    // Private browsing or a corrupt value should never break the app.
    return [];
  }
}

function writeRecent(ids: string[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  } catch {
    // Storage being unavailable is not an error worth surfacing.
  }
}

export function BillSessionProvider({ children }: { children: ReactNode }) {
  const { preferences } = usePreferences();
  const [bill, setBill] = useState<BillOut | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisOut | null>(null);
  const [recent, setRecent] = useState<string[]>(() => readRecent());

  // With "remember recent bills" off the list still works for this visit, but
  // nothing is written to the browser.
  const remember = useCallback(
    (billId: string) => {
      setRecent((previous) => {
        const next = [billId, ...previous.filter((id) => id !== billId)].slice(0, MAX_RECENT);
        if (preferences.remember_bills) writeRecent(next);
        return next;
      });
    },
    [preferences.remember_bills],
  );

  const forget = useCallback((billId: string) => {
    setRecent((previous) => {
      const next = previous.filter((id) => id !== billId);
      if (preferences.remember_bills) writeRecent(next);
      return next;
    });
  }, [preferences.remember_bills]);

  const value = useMemo(
    () => ({ bill, analysis, setBill, setAnalysis, recent, remember, forget }),
    [bill, analysis, recent, remember, forget],
  );

  return <BillSessionContext.Provider value={value}>{children}</BillSessionContext.Provider>;
}

export function useBillSession(): BillSession {
  const context = useContext(BillSessionContext);
  if (!context) throw new Error("useBillSession must be used inside a BillSessionProvider");
  return context;
}
