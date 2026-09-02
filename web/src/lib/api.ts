import type {
  HealthResponse,
  VendorOut,
  DetectionRunOut,
  RepositoryOut,
  ChangelogHitOut,
  PipelineRunOut,
  ActivityEventOut,
} from "./types";

const BASE = "/api/v1";

async function fetchJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  health: () => fetchJSON<HealthResponse>("/health"),
  vendors: () => fetchJSON<VendorOut[]>(`${BASE}/vendors`),
  vendor: (slug: string) => fetchJSON<VendorOut>(`${BASE}/vendors/${slug}`),
  detectionRuns: (limit = 50) =>
    fetchJSON<DetectionRunOut[]>(`${BASE}/detection-runs?limit=${limit}`),
  detectionRun: (id: number) =>
    fetchJSON<DetectionRunOut>(`${BASE}/detection-runs/${id}`),
  repositories: () => fetchJSON<RepositoryOut[]>(`${BASE}/repositories`),
  pipelineRuns: (limit = 20) =>
    fetchJSON<PipelineRunOut[]>(`${BASE}/pipeline-runs?limit=${limit}`),
  activity: (limit = 30) =>
    fetchJSON<ActivityEventOut[]>(`${BASE}/activity?limit=${limit}`),
  searchChangelog: (q: string, vendor?: string, limit = 10) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    if (vendor) params.set("vendor", vendor);
    return fetchJSON<ChangelogHitOut[]>(`${BASE}/search/changelog?${params}`);
  },
};
