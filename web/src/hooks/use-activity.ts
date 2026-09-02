"use client";

import { useCallback } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { ActivityEventOut } from "@/lib/types";

export function useActivity() {
  const fetcher = useCallback(() => api.activity(30), []);
  const { data: events, isLoading } = usePolling<ActivityEventOut[]>(
    fetcher,
    POLL_INTERVALS.detectionRuns
  );

  const latestDetection = events?.find((e) => e.kind === "detection") ?? null;
  const latestPipeline = events?.find((e) => e.kind === "pipeline") ?? null;

  const pipelineStatus = latestPipeline?.status ?? "idle";
  const recentEvents = events ?? [];

  return {
    events: recentEvents,
    latestDetection,
    latestPipeline,
    pipelineStatus,
    isLoading,
  };
}
