export interface VendorOut {
  slug: string;
  name: string;
  spec_url: string;
  old_spec_url: string | null;
  poll_interval_seconds: number;
  enabled: boolean;
}

export interface Change {
  kind: string;
  severity: string;
  path: string;
  method: string;
  detail: string;
  old_value?: unknown;
  new_value?: unknown;
  schema_path?: string;
  ref_source?: string;
}

export interface DetectionRunOut {
  id: number;
  vendor_slug: string;
  old_digest: string | null;
  new_digest: string | null;
  breaking_count: number;
  additive_count: number;
  changes: Change[];
  created_at: string;
}

export interface RepositoryOut {
  id: number;
  owner: string;
  name: string;
  vendor_slug: string;
  default_branch: string | null;
  is_active: boolean;
  last_run_at: string | null;
  created_at: string;
}

export interface InstallationOut {
  id: number;
  install_id: number;
  owner: string;
  is_active: boolean;
  created_at: string;
}

export interface ChangelogHitOut {
  id: number;
  vendor_slug: string;
  kind: string;
  path: string;
  method: string;
  detail: string | null;
  score: number;
  created_at: string;
}

export interface HealthResponse {
  status: string;
  database: boolean;
}

export interface PipelineRunOut {
  id: number;
  repository_id: number;
  status: string;
  current_step: string | null;
  task_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  pr_number: number | null;
  pr_url: string | null;
  error_message: string | null;
  created_at: string;
}

export interface ActivityEventOut {
  kind: string;
  timestamp: string;
  title: string;
  detail: string | null;
  status: string | null;
}

export interface RepositoryCreated {
  id: number;
  task_id: string | null;
}

export interface VendorCreated {
  slug: string;
}

export interface UserOut {
  id: number;
  email: string;
  tenant_id: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
}

export interface TokenOut {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ApiKeyOut {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreatedOut {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
}
