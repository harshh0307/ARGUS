import type {
  HealthResponse,
  VendorOut,
  DetectionRunOut,
  RepositoryOut,
  ChangelogHitOut,
  PollOut,
  DetectOut,
  PipelineOut,
  MergeOut,
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

async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  return fetchJSON<T>(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
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
  searchChangelog: (q: string, vendor?: string, limit = 10) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    if (vendor) params.set("vendor", vendor);
    return fetchJSON<ChangelogHitOut[]>(`${BASE}/search/changelog?${params}`);
  },
  triggerPoll: () => postJSON<PollOut>(`${BASE}/poll`),
  triggerDetect: (vendor_slug: string) =>
    postJSON<DetectOut>(`${BASE}/detect`, { vendor_slug }),
  triggerPipeline: (repository_id: number, merge = true) =>
    postJSON<PipelineOut>(`${BASE}/pipeline`, { repository_id, merge }),
  triggerRerun: (repository_id: number) =>
    postJSON<PipelineOut>(`${BASE}/fix/rerun`, { repository_id }),
  triggerMerge: (owner: string, repo: string, pr_number: number) =>
    postJSON<MergeOut>(`${BASE}/pr/merge`, { owner, repo, pr_number }),
};
