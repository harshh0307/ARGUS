"use client";

import { useState, useEffect, useCallback, useRef } from "react";

interface UsePollingOptions {
  enabled?: boolean;
  immediate?: boolean;
}

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  options: UsePollingOptions = {}
) {
  const { enabled = true, immediate = true } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const activeRef = useRef(true);

  const doFetch = useCallback(async () => {
    try {
      const result = await fetcher();
      if (activeRef.current) {
        setData(result);
        setError(null);
        setIsLoading(false);
      }
    } catch (err) {
      if (activeRef.current) {
        setError(err as Error);
        setIsLoading(false);
      }
    }
  }, [fetcher]);

  const refresh = useCallback(() => {
    doFetch();
  }, [doFetch]);

  useEffect(() => {
    activeRef.current = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    if (enabled) {
      if (immediate) {
        timer = setTimeout(doFetch, 0);
      }
      intervalRef.current = setInterval(doFetch, intervalMs);
    }
    return () => {
      activeRef.current = false;
      if (timer) clearTimeout(timer);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [doFetch, intervalMs, enabled, immediate]);

  return { data, error, isLoading, refresh };
}
