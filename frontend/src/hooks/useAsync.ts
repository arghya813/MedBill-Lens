/**
 * Async data loading helpers.
 *
 * Kept deliberately small: a request key, a cancellable load and a reset on
 * unmount. Every page uses the same loading/error/empty contract so the UI
 * behaves predictably.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;
  /** True while refreshing data that is already on screen. */
  refreshing: boolean;
  reload: () => void;
  setData: (updater: T | ((previous: T | null) => T | null)) => void;
}

export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
  options: { enabled?: boolean } = {},
): AsyncState<T> {
  const { enabled = true } = options;
  const [data, setDataState] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [nonce, setNonce] = useState(0);
  const hasData = useRef(false);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    if (hasData.current) setRefreshing(true);
    else setLoading(true);
    setError(null);

    loader(controller.signal)
      .then((result) => {
        hasData.current = true;
        setDataState(result);
      })
      .catch((cause: unknown) => {
        if (cause instanceof DOMException && cause.name === "AbortError") return;
        setError(cause instanceof Error ? cause : new Error(String(cause)));
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        setLoading(false);
        setRefreshing(false);
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce, enabled]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);

  const setData = useCallback(
    (updater: T | ((previous: T | null) => T | null)) => {
      setDataState((previous) =>
        typeof updater === "function"
          ? (updater as (p: T | null) => T | null)(previous)
          : updater,
      );
    },
    [],
  );

  return { data, error, loading, refreshing, reload, setData };
}

/** Tracks a mutation's pending state and surfaces its error message. */
export function useMutation<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult>,
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | null> => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (cause) {
        if (mounted.current) {
          setError(cause instanceof Error ? cause : new Error(String(cause)));
        }
        return null;
      } finally {
        if (mounted.current) setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, setError };
}
