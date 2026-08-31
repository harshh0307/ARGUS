"use client";

import { useCallback, useState } from "react";
import { api } from "@/lib/api";
import { POLL_INTERVALS } from "@/lib/constants";
import { usePolling } from "./use-polling";
import type { VendorOut } from "@/lib/types";

export function useVendors() {
  const fetcher = useCallback(() => api.vendors(), []);
  const { data, error, isLoading, refresh } = usePolling<VendorOut[]>(
    fetcher,
    POLL_INTERVALS.vendors
  );
  const [selectedVendor, setSelectedVendor] = useState<string | null>(null);

  return {
    vendors: data ?? [],
    selectedVendor,
    setSelectedVendor,
    error,
    isLoading,
    refresh,
  };
}
