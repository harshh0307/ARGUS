import type {
  HealthResponse,
  VendorOut,
  DetectionRunOut,
  RepositoryOut,
  ChangelogHitOut,
  PipelineRunOut,
  ActivityEventOut,
  RepositoryCreated,
  VendorCreated,
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

async function putJSON<T>(path: string, body: unknown): Promise<T> {
  return fetchJSON<T>(path, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

async function deleteJSON(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
}

export const api = {
  health: () => fetchJSON<HealthResponse>("/health"),
  vendors: () => fetchJSON<VendorOut[]>(`${BASE}/vendors`),
  vendor: (slug: string) => fetchJSON<VendorOut>(`${BASE}/vendors/${slug}`),
  createVendor: (data: { name: string; slug?: string; spec_url?: string; enabled?: boolean }) =>
    postJSON<VendorCreated>(`${BASE}/vendors`, data),
  updateVendor: (slug: string, data: { name: string; spec_url?: string; enabled?: boolean }) =>
    putJSON<VendorOut>(`${BASE}/vendors/${slug}`, data),
  deleteVendor: (slug: string) => deleteJSON(`${BASE}/vendors/${slug}`),
  uploadSpec: async (slug: string, file: File) => {
    const res = await fetch(`${BASE}/vendors/${slug}/spec`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/octet-stream" },
    });
    if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
    return res.json() as Promise<{ slug: string; spec_file: string; size: number }>;
  },
  detectionRuns: (limit = 50) =>
    fetchJSON<DetectionRunOut[]>(`${BASE}/detection-runs?limit=${limit}`),
  detectionRun: (id: number) =>
    fetchJSON<DetectionRunOut>(`${BASE}/detection-runs/${id}`),
  repositories: () => fetchJSON<RepositoryOut[]>(`${BASE}/repositories`),
  registerRepository: (data: { owner: string; name: string; vendor_slug?: string; default_branch?: string }) =>
    postJSON<RepositoryCreated>(`${BASE}/repositories`, data),
  triggerPipeline: (repository_id: number, merge = true) =>
    postJSON<{ dispatched: boolean; repository_id: number; task_id: string | null }>(
      `${BASE}/pipeline`,
      { repository_id, merge }
    ),
  pipelineRuns: (limit = 20) =>
    fetchJSON<PipelineRunOut[]>(`${BASE}/pipeline-runs?limit=${limit}`),
  pipelineRun: (id: number) =>
    fetchJSON<PipelineRunOut>(`${BASE}/pipeline-runs/${id}`),
  activity: (limit = 30) =>
    fetchJSON<ActivityEventOut[]>(`${BASE}/activity?limit=${limit}`),
  searchChangelog: (q: string, vendor?: string, limit = 10) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    if (vendor) params.set("vendor", vendor);
    return fetchJSON<ChangelogHitOut[]>(`${BASE}/search/changelog?${params}`);
  },
};
