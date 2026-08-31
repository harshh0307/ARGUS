"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { RepositoryOut } from "@/lib/types";

export function useRepositories() {
  const fetcher = useCallback(() => api.repositories(), []);
  const { data, error, isLoading, refresh } = usePolling<RepositoryOut[]>(
    fetcher,
    POLL_INTERVALS.repositories
  );
  const [isRegistering, setIsRegistering] = useState(false);

  const repositories = data ?? [];

  return {
    repositories,
    error,
    isLoading,
    refresh,
    isRegistering,
  };
}
