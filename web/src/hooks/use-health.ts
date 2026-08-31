"use client";

import { useCallback } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { HealthResponse } from "@/lib/types";

export function useHealth() {
  const fetcher = useCallback(() => api.health(), []);
  return usePolling<HealthResponse>(fetcher, POLL_INTERVALS.health);
}
