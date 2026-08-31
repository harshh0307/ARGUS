"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { DetectionRunOut } from "@/lib/types";

export function useDetectionRuns(limit = 50) {
  const fetcher = useCallback(() => api.detectionRuns(limit), [limit]);
  const { data, error, isLoading, refresh } = usePolling<DetectionRunOut[]>(
    fetcher,
    POLL_INTERVALS.detectionRuns
  );
  const [selectedRun, setSelectedRun] = useState<DetectionRunOut | null>(null);

  const runs = data ?? [];

  return {
    runs,
    selectedRun: selectedRun ?? runs[0] ?? null,
    setSelectedRun,
    error,
    isLoading,
    refresh,
  };
}
