from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class VendorOut(BaseModel):
    slug: str
    name: str
    spec_url: str
    old_spec_url: str | None = None
    poll_interval_seconds: int
    enabled: bool


class DetectionRunOut(BaseModel):
    id: int
    vendor_slug: str
    old_digest: str | None = None
    new_digest: str | None = None
    breaking_count: int
    additive_count: int
    changes: list
    created_at: datetime


class RepositoryOut(BaseModel):
    id: int
    owner: str
    name: str
    vendor_slug: str = "github"
    default_branch: str | None = None
    is_active: bool
    last_run_at: datetime | None = None
    created_at: datetime


class RepositoryIn(BaseModel):
    owner: str
    name: str
    default_branch: str | None = None
    vendor_slug: str = "github"


class RepositoryCreated(BaseModel):
    id: int
    task_id: str | None = None


class WebhookOut(BaseModel):
    ok: bool
    event: str | None = None
    dispatched: bool = False
    reason: str | None = None


class InstallationOut(BaseModel):
    id: int
    install_id: int
    owner: str
    is_active: bool
    created_at: datetime


class ChangelogHitOut(BaseModel):
    id: int
    vendor_slug: str
    kind: str
    path: str
    method: str
    detail: str | None = None
    score: float
    created_at: datetime


class PollIn(BaseModel):
    pass


class PollOut(BaseModel):
    dispatched: bool
    task_id: str | None = None


class DetectIn(BaseModel):
    vendor_slug: str


class DetectOut(BaseModel):
    dispatched: bool
    vendor_slug: str
    task_id: str | None = None


class PipelineIn(BaseModel):
    repository_id: int
    merge: bool = True


class PipelineOut(BaseModel):
    dispatched: bool
    repository_id: int
    task_id: str | None = None


class RerunIn(BaseModel):
    repository_id: int


class RerunOut(BaseModel):
    dispatched: bool
    repository_id: int
    task_id: str | None = None


class MergeIn(BaseModel):
    owner: str
    repo: str
    pr_number: int


class MergeOut(BaseModel):
    dispatched: bool
    owner: str
    repo: str
    pr_number: int
    task_id: str | None = None


class PipelineRunOut(BaseModel):
    id: int
    repository_id: int
    status: str
    current_step: str | None = None
    task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    error_message: str | None = None
    created_at: datetime


class ActivityEventOut(BaseModel):
    kind: str
    timestamp: datetime
    title: str
    detail: str | None = None
    status: str | None = None


class VendorIn(BaseModel):
    name: str
    slug: str | None = None
    spec_url: str | None = None
    enabled: bool = True


class VendorCreated(BaseModel):
    slug: str


# ── Auth schemas ────────────────────────────────────────────────────────


class RegisterIn(BaseModel):
    email: str
    password: str
    tenant_id: str | None = None


class RegisterOut(BaseModel):
    id: int
    email: str
    tenant_id: str


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class ApiKeyCreatedOut(BaseModel):
    id: int
    name: str
    key: str
    prefix: str
    created_at: datetime


class ApiKeyOut(BaseModel):
    id: int
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None
