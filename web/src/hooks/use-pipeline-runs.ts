"use client";

import { useCallback, useMemo } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { PipelineRunOut } from "@/lib/types";

export function usePipelineRuns(limit = 20) {
  const fetcher = useCallback(() => api.pipelineRuns(limit), [limit]);
  const { data, error, isLoading, refresh } = usePolling<PipelineRunOut[]>(
    fetcher,
    POLL_INTERVALS.pipelineActive
  );

  const runs = data ?? [];
  const activeRun = useMemo(
    () => runs.find((r) => r.status === "running") ?? null,
    [runs]
  );

  return { runs, activeRun, error, isLoading, refresh };
}
