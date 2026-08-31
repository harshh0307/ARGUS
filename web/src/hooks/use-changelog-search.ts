"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { ChangelogHitOut } from "@/lib/types";

export function useChangelogSearch(query: string, vendor?: string) {
  const [results, setResults] = useState<ChangelogHitOut[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const doSearch = useCallback(async () => {
    if (!query.trim()) {
      setResults([]);
      return;
    }
    setIsLoading(true);
    try {
      const data = await api.searchChangelog(query, vendor);
      setResults(data);
      setError(null);
    } catch (err) {
      setError(err as Error);
    } finally {
      setIsLoading(false);
    }
  }, [query, vendor]);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(doSearch, 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [doSearch]);

  return { results, isLoading, error };
}
