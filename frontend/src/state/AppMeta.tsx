/**
 * Global app metadata (health, disclaimer, enum options).
 *
 * Loaded once at the top of the tree so every page can show the same dataset
 * and privacy notices without refetching. Failures are non-fatal: the app stays
 * usable and simply omits the global banners.
 */

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "@/api/client";
import type {
  DisclaimerResponse,
  EnumOptionsResponse,
  HealthResponse,
} from "@/api/types";

interface AppMeta {
  health: HealthResponse | null;
  disclaimer: DisclaimerResponse | null;
  options: EnumOptionsResponse | null;
  /** Set when the metadata calls failed, e.g. the backend is not running. */
  unreachable: boolean;
  loading: boolean;
}

const MetaContext = createContext<AppMeta>({
  health: null,
  disclaimer: null,
  options: null,
  unreachable: false,
  loading: true,
});

export function AppMetaProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [disclaimer, setDisclaimer] = useState<DisclaimerResponse | null>(null);
  const [options, setOptions] = useState<EnumOptionsResponse | null>(null);
  const [unreachable, setUnreachable] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      api.health(controller.signal),
      api.disclaimer(controller.signal),
      api.options(controller.signal),
    ])
      .then(([nextHealth, nextDisclaimer, nextOptions]) => {
        setHealth(nextHealth);
        setDisclaimer(nextDisclaimer);
        setOptions(nextOptions);
        setUnreachable(false);
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setUnreachable(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  const value = useMemo(
    () => ({ health, disclaimer, options, unreachable, loading }),
    [health, disclaimer, options, unreachable, loading],
  );

  return <MetaContext.Provider value={value}>{children}</MetaContext.Provider>;
}

export function useAppMeta(): AppMeta {
  return useContext(MetaContext);
}
