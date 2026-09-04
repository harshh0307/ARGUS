# Argus

**The changelog that reads your codebase.**

[![CI](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml)
[![Deploy](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Argus watches API vendors (GitHub, Stripe, Twilio, Slack, AWS, Azure, Google Cloud) by diffing their OpenAPI specs, scans your repositories across 7 languages, fixes them with an LLM agent, and opens a pull request for review.

It ships as a multi-tenant service: JWT + API-key auth, per-tenant data scoping, rate limiting, a Next.js dashboard, and a Celery-driven autonomous monitoring loop.

> "API providers shouldn't just announce changes; they should apply them."
> When an API ships a breaking change, an agent should scan customer codebases, identify affected usages, and open a PR with the fix — like Dependabot, but for APIs.

## Why

- Breaking API changes ship with little warning
- Changelogs don't get read
- At AWS, over 30% of service downtime was caused by external API/package changes going unnoticed
- Agentic coding tools have proven developers trust tools with codebase access

## Architecture

**Detection loop** — Celery beat, every 6h:

```
poll_all_vendors ─▶ fetch spec ─▶ snapshot store ─▶ 161-kind diff ─▶ change events
                                                                          │
                                                     breaking / deprecation
                                                                          ▼
                                                        dispatch_scan_for_vendor
                                                                          │
                                                      (one scan_and_fix per repo)
```

**Fix pipeline** — per repository:

```
repo tarball ─▶ scan (7 languages, 5 usage kinds) ─▶ impact report
                                                          │
                                                          ▼
                     LangGraph fix agent ─▶ patch ─▶ branch + PR ─▶ CI verify loop
                        │   guards ────────┘                            ▲
                        └── syntax + semantic re-scan reject no-ops     │
                                            ▲                failure log ┘
                                            └───────── (self-heal, max N attempts)
```

**Service topology:**

```
  browser ────────▶ web/ (Next.js :3000) ──┐
                                           │
  GitHub webhooks ─────────────────────────┤
                                           ▼
                                  ┌──────────────────┐        ┌─────────┐
                                  │ FastAPI :8000    │───────▶│  Redis  │
                                  │ auth · tenants   │        └────┬────┘
                                  │ rate limits      │      broker │
                                  └────────┬─────────┘             ▼
                                           │            ┌──────────────────┐
                                           │            │ celery worker    │
                                           │            │ celery beat      │
                                           ▼            └────────┬─────────┘
                                  ┌──────────────────┐           │
                                  │ Postgres         │◀──────────┘
                                  └──────────────────┘
```

| Component | Status | Tech |
|---|---|---|
| Spec ingestion + snapshot store | ✅ | httpx, content-addressed JSON snapshots (SHA-256) |
| Vendor registry (multi-vendor) | ✅ | github, stripe, twilio, slack, aws, azure, google_cloud built-ins, `argus vendors` |
| Postgres/SQLite persistence | ✅ | SQLAlchemy 2.0, psycopg; vendors, snapshots, detection runs |
| Celery workers + Redis | ✅ | Celery 5.6, Redis broker/backend, beat polling, `scan_and_fix` tasks |
| GitHub App auth (auto-refreshing install tokens) | ✅ | RS256 app JWT → installation access tokens, cached; PAT fallback |
| FastAPI API + webhook receiver | ✅ | authenticated read/write endpoints, HMAC-verified GitHub webhooks |
| Real-time webhooks | ✅ | `push`, `pull_request`, `repository_dispatch`, `installation`, `check_run` → Celery dispatch (inline fallback) |
| AST usage scanner + impact report | ✅ | Python, JS/TS, Go, Ruby, Java, PHP, C# scanner; constant folding, template path matching |
| LangGraph fix agent (validate + retry) | ✅ | LangGraph, OpenAI-compatible LLMs |
| Per-vendor fix agents | ✅ | vendor-specific guidance + model per vendor (`--vendor`) |
| Semantic guard (no-op patch rejection) | ✅ | re-scans patched AST, rejects if removed endpoint still called |
| Multi-provider LLM + quota fallback | ✅ | Gemini / OpenAI primary, Nemotron free fallback on 429 |
| Merge-on-green (opt-in) | ✅ | squash-merge when CI passes, branch cleanup; off by default except in the autonomous chain (see [Known limits](#known-limits)) |
| GitHub PR client + CI feedback loop | ✅ | httpx (REST API), Actions job logs |
| Changelog + semantic search | ✅ | embeddings (OpenAI-compatible) stored as JSON, cosine ranked in Python, `/api/v1/search/changelog` |
| CLI + docker-compose | ✅ | argparse, Docker, `--languages` + `--vendors` flags |
| Full end-to-end demo (PR self-heal) | ✅ | `scripts/demo_pr.py` (verified live) |
| Multi-vendor registry, workers, Postgres, API | ✅ | Celery + Redis, PostgreSQL, FastAPI |
| AWS cloud deployment | ✅ | ECS Fargate, RDS, ElastiCache, Terraform, GitHub Actions CI/CD |
| Full change taxonomy (161 kinds, 15 categories) | ✅ | `ChangeKind` enum; endpoint, param, request/response body, schema, constraints, composition, security, servers, webhooks, refs |
| Recursive schema diff | ✅ | `detection/schema_diff.py`; properties, required fields, enums, formats, constraints, `allOf`/`oneOf`/`anyOf`, depth-capped at 32 |
| Response / body / auth / header usage scanning | ✅ | `ResponseUsage`, `BodyUsage`, `AuthUsage`, `HeaderUsage` alongside call-site `Usage` |
| Deterministic fix strategy registry | ✅ | `fix/strategies.py`; 41 registered strategies with validators + guards per change kind |
| Auth (JWT + API keys) | ✅ | bcrypt passwords, HS256 access/refresh tokens via python-jose, SHA-256-hashed `argus_*` API keys |
| Multi-tenant scoping | ✅ | `tenant_id` on vendors, repositories, detection runs, changelog, installations |
| Rate limiting | ✅ | slowapi; separate default / auth / webhook limits |
| Custom vendors + spec upload | ✅ | `POST/PUT/DELETE /api/v1/vendors`, `POST /api/v1/vendors/{slug}/spec` (JSON or YAML) |
| Pipeline run tracking | ✅ | `pipeline_runs` table: status, current step, PR number/URL, error, timings |
| Control endpoints | ✅ | trigger poll / detect / pipeline / rerun / merge over HTTP |
| Autonomous monitoring loop | ✅ | beat → `poll_all_vendors` → `dispatch_scan_for_vendor` → `scan_and_fix` per repo |
| Next.js dashboard | ✅ | React 19 + Tailwind + Framer Motion, login/register, three-pane workspace, polling hooks |
| Server-rendered dashboard | ✅ | Jinja2 + TailwindCSS + Chart.js pages under `/dashboard`: vendor status, activity charts, repo list |
| Metrics + cost tracking | ✅ | `GET /metrics`, per-model token/cost accounting, circuit breaker, token budget |

**Key insight:** Argus only patches endpoints that have a **breaking or deprecation diff** in the spec AND are **actually used** in the codebase. Additive changes and untouched endpoints are recorded but never patched. Step-by-step detail is in [How it works (detailed)](#how-it-works-detailed).

## Project layout

```
app/
├── core/          # settings (pydantic-settings, 12-factor config)
├── ingestion/     # fetch specs, snapshot versioning
├── detection/     # normalize + semantic diff + breaking-change rules
│   ├── models.py       # 161 ChangeKind values across 15 ChangeCategory groups
│   ├── normalize.py    # extracts 16 attributes per operation
│   ├── diff.py         # operation/param/body/response/security/server/webhook diff
│   └── schema_diff.py  # recursive schema diff (properties, enums, constraints, composition)
├── scan/          # multi-language scanners (Python, JS/TS, Go, Ruby, Java, PHP, C#)
│   ├── scanner.py      # language dispatch + Python ast (requests/httpx/aiohttp)
│   ├── models.py       # Usage, HeaderUsage, BodyUsage, AuthUsage, ResponseUsage
│   ├── impact.py       # joins every usage type against breaking changes
│   ├── js_scanner.py      # JS/TS fetch/axios/got/superagent/ky
│   ├── go_scanner.py      # Go net/http, go-resty, echo/gin/mux
│   ├── ruby_scanner.py    # Ruby Net::HTTP, HTTParty, RestClient
│   ├── java_scanner.py    # Java HttpClient, RestTemplate, Feign
│   ├── php_scanner.py     # PHP Guzzle, Symfony, cURL, Laravel
│   └── cs_scanner.py      # C# HttpClient, RestSharp, Refit
├── fix/           # LangGraph fix agent, patch engine, multi-provider LLM
│   ├── agent.py       # LangGraph graph with guardrails
│   ├── patch.py       # patch application + validation (unreachable code, throw-in-expression)
│   ├── prompt.py      # LLM prompt with injection sanitization
│   ├── validator.py   # patch validation
│   ├── token_budget.py # token budget management
│   ├── cost_tracker.py # per-model cost tracking
│   ├── circuit_breaker.py # trips after repeated provider failures
│   ├── token_manager.py   # scoped installation tokens
│   ├── semantic_guards.py # per-change-kind deterministic guards
│   ├── ast_validators.py  # unreachable code / throw-in-expression checks
│   ├── strategies.py  # deterministic strategy registry (41 strategies)
│   ├── state.py       # LangGraph state, history trimming, checkpointer
│   └── errors.py      # error classification (rate limit, timeout, etc.)
├── github/        # GitHub client, App token auth, CI logs, PR self-heal loop
├── registry/      # vendor registry (github, stripe, twilio, slack, aws, azure, google_cloud)
├── db/            # SQLAlchemy models + persistence layer
├── services/      # pipeline service layer (shared by CLI, workers, API)
├── search/        # changelog embeddings + cosine search
├── workers/       # Celery app + tasks
├── auth/          # JWT tokens, bcrypt passwords, API key hashing, FastAPI deps
├── metrics.py     # in-process counters exposed at GET /metrics
├── api/           # FastAPI API + auth + webhooks + control + dashboard
│   ├── main.py         # FastAPI app: auth, vendors, repos, runs, control, webhook
│   ├── schemas.py      # request/response models
│   ├── dashboard.py    # server-rendered dashboard endpoints
│   └── templates/      # Jinja2 templates (TailwindCSS + Chart.js)
└── cli.py         # argus detect/scan/fix/pr commands
web/               # Next.js 15 dashboard (React 19, Tailwind, Framer Motion)
├── src/app/           # login, register, workspace pages
├── src/components/    # dashboard panes, vendor pages, UI primitives
├── src/hooks/         # polling hooks (repos, runs, vendors, activity, health)
└── src/lib/           # API client + types
infra/terraform/   # AWS IaC (VPC, RDS, ElastiCache, ECS Fargate, ALB)
.github/workflows/ # CI (tests+lint) + deploy (ECR → terraform → ECS)
scripts/
├── demo_pr.py     # full live pipeline demo (seed repo -> PR -> CI loop)
├── check_deprecated.py  # check deprecated API endpoints
├── test_hmac.py   # test HMAC webhook signature
└── aws/           # upload-secrets.ps1 (SSM Parameter Store)
tests/             # pytest suite (710 tests)
```

## Setup

Requires Python 3.14.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill in at least:

```powershell
Copy-Item .env.example .env
```

| Variable | Required for | Notes |
|---|---|---|
| `GITHUB_TOKEN` | `argus pr`, demo | classic PAT; scopes: `repo`, `workflow` |
| `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY` / `GITHUB_INSTALL_ID` | alternative to `GITHUB_TOKEN` | GitHub App with repo-access install; tokens auto-renew per request |
| `WEBHOOK_SECRET` | `api` webhook receiver | verifies `X-Hub-Signature-256`; push events trigger `scan_and_fix` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | `argus fix`, `argus pr` | any OpenAI-compatible provider works via `LLM_BASE_URL` |
| `OPENROUTER_API_KEY` | fallback when primary LLM is rate-limited | free model: `nvidia/nemotron-3-ultra-550b-a55b:free` (verified) |
| `OPENROUTER_MODEL` | — | default `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `LLM_MODEL` | — | default `gpt-4o-mini` |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | semantic changelog search | OpenAI-compatible embeddings endpoint (default `text-embedding-3-small`); keyword fallback without it. **Tip:** your OpenRouter key works — set `EMBEDDING_BASE_URL=https://openrouter.ai/api/v1` + `EMBEDDING_MODEL=openai/text-embedding-3-small` (free, verified) |
| `DATABASE_URL` | `argus detect` persistence, API read endpoints, **all auth** | optional for the CLI, required for the API; `sqlite:///data/argus.db` or `postgresql+psycopg://...` (docker-compose has Postgres 16) |
| `AUTH_SECRET_KEY` | every authenticated endpoint | **must be changed before deploying** — the default `change-me-in-production` makes every JWT forgeable |
| `AUTH_ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES` | — | default `HS256`, `30` |
| `RATE_LIMIT_DEFAULT` / `RATE_LIMIT_AUTH` / `RATE_LIMIT_WEBHOOK` | — | slowapi strings; default `60/minute`, `10/minute`, `30/minute` |
| `NEXT_PUBLIC_API_URL` | `web/` dashboard | where the browser reaches the API; compose sets `http://api:8000` |
| `HTTP_TIMEOUT_SECONDS` / `HTTP_MAX_RETRIES` | — | spec fetching; default `30.0`, `3` |
| `LLM_TIMEOUT_SECONDS` | — | per-request LLM timeout; default `60` |
| `SEARCH_LIMIT` | — | default changelog search result count; default `10` |

## Usage

```powershell
argus vendors               # list registered spec vendors (7 total)
argus detect                # diff pinned old spec vs. current -> breaking/additive changes
argus detect --vendor stripe  # run detection for another vendor
argus detect --vendors github stripe  # detect for multiple vendors
argus scan [DIR]            # scan a repo for call sites hit by breaking changes
argus scan [DIR] --languages py go ruby java php cs  # scan only specific languages
argus fix [DIR] --vendor github  # apply LLM fixes in place (--dry-run to preview diffs)
argus pr OWNER/REPO --vendor github  # full loop: detect, scan, fix, open PR, self-heal on CI failure
argus pr OWNER/REPO --merge  # same, but squash-merge when CI passes
argus pr OWNER/REPO --languages py js --vendors github stripe  # multi-language, multi-vendor
```

### Celery workers

```powershell
# worker (executes tasks from Redis)
celery -A app.workers.celery_app worker --loglevel=info

# beat (polls all vendors every 6h per the schedule)
celery -A app.workers.celery_app beat --loglevel=info
```

Tasks: `argus.poll_all_vendors` and `argus.sync_all_installation_repos` (beat-scheduled), plus `argus.run_detection`, `argus.dispatch_scan_for_vendor`, `argus.scan_and_fix`, `argus.register_repository`, `argus.sync_installation_repos`, `argus.merge_pr`. Requires `DATABASE_URL` and `REDIS_URL` (docker-compose provides Postgres + Redis).

Beat schedule:

| Task | Interval | Chain |
|---|---|---|
| `argus.poll_all_vendors` | 6h | detect every enabled vendor → on breaking changes, `dispatch_scan_for_vendor` → `scan_and_fix` per active repo |
| `argus.sync_all_installation_repos` | 1h | walk active GitHub App installations and upsert their repos |

### FastAPI

```powershell
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

All `/api/v1/*` endpoints except `/auth/register`, `/auth/login`, `/auth/refresh` and `/webhook` require authentication — either an `Authorization: Bearer <jwt>` header or an `X-API-Key: argus_...` header. Reads are scoped to the caller's `tenant_id`; admin users see everything.

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | — | liveness + database flag |
| `GET /metrics` | — | in-process counters (detections, fixes, PRs, LLM cost) |
| `POST /api/v1/auth/register` | — | create a user; returns `{id, email, tenant_id}` |
| `POST /api/v1/auth/login` | — | returns access + refresh tokens |
| `POST /api/v1/auth/refresh` | refresh token | exchange a refresh token for a new access token |
| `GET /api/v1/auth/me` | user | current user, tenant, admin flag |
| `POST /api/v1/auth/api-keys` | user | mint an API key (raw value shown once) |
| `GET /api/v1/auth/api-keys` | user | list your keys (prefix + last used) |
| `DELETE /api/v1/auth/api-keys/{key_id}` | user | revoke a key |
| `POST /api/v1/vendors` / `PUT /api/v1/vendors/{slug}` / `DELETE /api/v1/vendors/{slug}` | user | create, update, delete a custom vendor in your tenant |
| `POST /api/v1/vendors/{slug}/spec` | user | upload a spec body directly (JSON or YAML) instead of polling a URL |
| `GET /api/v1/pipeline-runs` / `.../{run_id}` | user | pipeline run status, current step, PR link, error |
| `GET /api/v1/activity` | user | merged detection + repository activity feed |
| `POST /api/v1/poll` | admin | trigger a poll of all vendors now |
| `POST /api/v1/detect` | admin | trigger detection for one vendor |
| `POST /api/v1/pipeline` | user | run scan → fix → PR for one repository |
| `POST /api/v1/fix/rerun` | user | rerun the pipeline for one repository (never merges) |
| `POST /api/v1/pr/merge` | user | merge a specific PR |
| `GET /api/v1/vendors` / `/api/v1/vendors/{slug}` | user | vendor registry (built-ins plus your tenant's custom vendors) |
| `GET /api/v1/detection-runs` / `.../{run_id}` | user | detection history from Postgres |
| `GET /api/v1/repositories` / `POST /api/v1/repositories` | user | register/list repos (`{owner, name, default_branch, vendor_slug}`) |
| `GET /api/v1/installations` | user | GitHub App installations (owner, active state) recorded from webhooks |
| `GET /api/v1/search/changelog?q=...&vendor=...&limit=...` | user | semantic search across detected changes (embeddings via `EMBEDDING_*`, keyword fallback; every `argus detect` batch-embeds new changes) |
| `POST /api/v1/webhook` | HMAC | GitHub webhook receiver; HMAC-verified (needs `WEBHOOK_SECRET`). Events: `push`, `repository_dispatch`, `pull_request` (opened/synchronize/reopened) → `scan_and_fix` for registered repos; `installation` → upserts install rows; `check_run` → logged. Malformed payloads return 200 with error reason (no crash) |
| `GET /dashboard` | none | Server-rendered overview (vendor status, breaking/additive stats, recent runs) |
| `GET /dashboard/vendors` | none | Vendor detail pages with run history |
| `GET /dashboard/activity` | none | Activity chart (Chart.js stacked bar, changes over time) |
| `GET /dashboard/repositories` | none | Registered repositories list |

> The `/dashboard/*` pages and `GET /metrics` are **not** behind auth and are **not** tenant-scoped. Do not expose them publicly — put them behind a reverse proxy or network policy until they are gated.

Point `https://your.host/webhook` at the repo's GitHub webhook with content type `application/json` and a secret matching `WEBHOOK_SECRET`.

Example:

```powershell
argus detect
# 11 breaking, 150 additive changes

argus scan .\my-service
# Scanned .\my-service: 42 call sites, 3 impacted by breaking changes
#   app.py:6 affected by [breaking] endpoint_removed

argus fix --dry-run .\my-service   # preview diffs, don't write
argus fix .\my-service             # write fixes to disk

argus pr acme/website --branch argus/fix --max-attempts 3
# PR #12: https://github.com/acme/website/pull/12
# passed=True attempts=3

argus pr acme/website --merge      # squash-merge when CI passes
# merged; fix branch deleted

curl "http://127.0.0.1:8000/api/v1/search/changelog?q=manage%20dependabot%20access"
# semantic hits ranked by cosine similarity (needs EMBEDDING_* set)
```

`argus pr` fetches the repo as a tarball through the GitHub API (no local git checkout needed; use `--dir` to scan a local checkout instead).

## Docker

```powershell
docker build -t argus:local .
docker run --rm argus:local detect
docker compose up             # scans ./repos with argus scan /repos
docker compose up api         # FastAPI on :8000 (with postgres + redis)
docker compose up dashboard   # Next.js dashboard on :3000, talking to api:8000
docker compose up api-dev     # same as api, with --reload and ./app bind-mounted
docker compose run --rm test  # run the pytest suite inside the image
```

Compose services: `argus` (one-shot scan), `postgres` (pgvector/pg16), `redis`, `migrate`, `worker`, `beat`, `api`, `api-dev`, `test` (dev stage), `dashboard`. Postgres and Redis have healthchecks; dependents wait on `service_healthy`, and on `migrate` completing successfully so exactly one process applies migrations.

`env_file` is marked `required: false`, so a fresh clone can run `docker compose run --rm test` before anyone has copied `.env.example` to `.env`.

## Web dashboard (Next.js)

```powershell
cd web
npm install
npm run dev        # http://localhost:3000, expects the API on NEXT_PUBLIC_API_URL
```

Register at `/register`, sign in at `/login`, then the workspace gives you a three-pane view: repositories and vendors on the left, pipeline runs and activity in the middle, analytics and changelog search on the right. Repos and custom vendors can be added from the UI, and adding a repo auto-triggers a pipeline run. State refreshes through polling hooks (`use-repositories`, `use-pipeline-runs`, `use-detection-runs`, `use-activity`, `use-vendors`, `use-health`).

## Database migrations

Alembic owns the schema. `migrations/env.py` reads `DATABASE_URL` from `Settings`, so there is no URL in `alembic.ini` to keep in sync.

```powershell
docker compose up migrate                     # apply everything (compose does this automatically)

# or directly, against any database:
alembic upgrade head
alembic current
alembic downgrade -1
alembic revision --autogenerate -m "what changed"
```

Revisions:

| Revision | What it does |
|---|---|
| `cd7a0398601e` | baseline — the schema as it stood before Alembic (9 tables) |
| `a9bec9bb0b7d` | `spec_snapshots.content` + `spec_format`, unique `(vendor_slug, digest)`, new `spec_pointers` table |

**Upgrading a database that predates Alembic.** It has no `alembic_version` table, so stamp the baseline first — otherwise Alembic tries to create tables that already exist:

```powershell
alembic stamp cd7a0398601e
alembic upgrade head
```

The second revision is written to be safe against existing data: it adds `spec_format` nullable, backfills `'json'`, then enforces `NOT NULL`, and collapses any duplicate `(vendor_slug, digest)` rows to their earliest row before adding the unique constraint. Both paths are covered in the verification steps below.

When adding a model column, generate the revision and **read it before committing** — autogenerate emits `nullable=False` with no server default, which fails on any table that already has rows.

## Test & lint

710 tests, all offline (no network, no live LLM).

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check app tests
```

The package declares `requires-python = ">=3.14"`, so `pip install -e ".[dev]"` **fails outright on 3.13 or older** — the error names the interpreter, not the constraint, which is easy to misread. If you don't have 3.14 locally, run the suite in the image instead:

```powershell
docker compose run --rm test                  # pytest
docker compose run --rm test ruff check --no-cache app tests migrations
```

The `test` service builds the `dev` stage of the Dockerfile, which is the only image with `pytest` and `ruff` — the runtime image deliberately installs no dev dependencies. It supplies a placeholder `GITHUB_TOKEN` so the suite needs no real credentials; a few tests exercise credential *resolution* and fail if nothing is configured at all.

On Docker Desktop for Windows, `ruff` reports `EXE002` for every file because the build context presents them as mode 0755. Git tracks them all as `100644`, so CI on Linux does not see this.

## Auth and tenancy

- **Users** register with an email, a bcrypt-hashed password, and a `tenant_id`.
- **Access tokens** are HS256 JWTs (30 min default); **refresh tokens** last 7 days and are marked `type: refresh` so they cannot be used as access tokens.
- **API keys** look like `argus_<token>`; only the SHA-256 hash and an 8-char prefix are stored, and `last_used_at` is stamped on each use. Send them as `X-API-Key`.
- **Tenant scoping**: `vendors`, `repositories`, `detection_runs`, `changelog_entries` and `app_installations` all carry a `tenant_id`. Non-admin reads are filtered to the caller's tenant; rows with a `NULL` tenant are treated as global and visible to everyone.
- **Admin users** (`is_admin`) bypass tenant filters and are required for `POST /api/v1/poll` and `POST /api/v1/detect`.

Before exposing this to anyone else, read [Known limits](#known-limits) — the current auth model has gaps that matter.

## Guardrails

The fix agent includes comprehensive guardrails to prevent bad patches:

| Guardrail | What it does |
|---|---|
| **Syntax validation** | Python: `ast.parse()`. JS/TS: bracket balancing + throw-in-expression detection |
| **Unreachable code detection** | Catches dead code after `raise`/`return`/`break`/`continue` |
| **Throw-in-expression detection** | Catches 7 patterns: IIFE, async IIFE, dummy assignment, logical expression, comma expression, function argument, string expression |
| **Semantic guard** | Re-scans patched AST; rejects if removed endpoint still called |
| **Duplicate patch detection** | Signature-based; same patch proposed twice → give up |
| **Progress stall detection** | Same error 2x in a row → give up |
| **Rate limit handling** | Provider-specific backoff (30s, 60s, 120s) |
| **Token budget** | Truncates large files to fit LLM context window |
| **Cost tracking** | Per-model pricing, budget limits |
| **Prompt sanitization** | 13 injection patterns stripped from code context |
| **Per-kind semantic guards** | `semantic_guards.py` rejects patches that leave the old method, param, enum value, status code or removed property in place |
| **Patch validator** | checks the patch's file, line range and resulting diff before it is accepted |
| **Circuit breaker** | trips after repeated provider failures instead of hammering the API |
| **History trimming** | patch and error history capped (10 / 5 entries) to bound the context window |

## Scanner capabilities

### Python
- `requests.get()`, `requests.post()`, etc.
- `httpx.get()`, `httpx.AsyncClient`
- `aiohttp.ClientSession`
- `requests.request("GET", url)` dynamic calls
- F-string URL resolution (`f"{BASE_URL}/repos/{OWNER}/{REPO}"`)
- Module-level constant resolution
- Local variable resolution

### JavaScript/TypeScript
- `fetch()`, `axios.get()`, `axios.post()`
- `got.get()`, `superagent.get()`, `ky.get()`
- Template literal URLs (`` `${BASE_URL}/repos/${OWNER}/${REPO}` ``)
- `const`/`let`/`var` constant resolution
- `.ts`, `.tsx`, `.jsx`, `.mjs`, `.cjs` support

### Go
- `net/http` (`http.Get`, `http.Post`, `client.Do`)
- `go-resty` (`resty.R().Get`)
- Echo/Gin/Mux framework routes (`c.Param`, `c.Query`, `mux.Vars`)

### Ruby
- `Net::HTTP`, `HTTParty`, `RestClient`
- `Typhoeus`, `HTTP` gem

### Java
- `HttpClient`, `RestTemplate`, `Unirest`
- Apache `HttpClient`, Feign, `WebClient`

### PHP
- Guzzle, Symfony HttpClient
- cURL (`curl_init`), `file_get_contents`
- WordPress (`wp_remote_get`), Laravel (`Http::get`)

### C#
- `HttpClient`, `RestSharp`, `Refit`
- ASP.NET Minimal API

### Beyond call sites (all languages)

Every scanner emits five usage kinds, not just call sites:

| Kind | What it captures |
|---|---|
| `Usage` | the HTTP call site — method + resolved spec path |
| `HeaderUsage` | headers being set (`Authorization`, `Content-Type`, `X-GitHub-Api-Version`, `Stripe-Version`, …) |
| `BodyUsage` | request body field names and content type |
| `AuthUsage` | auth style in use — bearer, API key, basic, OAuth2 |
| `ResponseUsage` | response handling — status codes compared, response fields read |

[impact.py](app/scan/impact.py) joins each kind against the change kinds that can affect it, so a security-scheme change matches auth usages, a request-body schema change matches body usages, and so on. Only `Usage` carries a real endpoint path today — see [Known limits](#known-limits).

## How it works (detailed)

1. **Ingestion** — fetch the vendor's OpenAPI spec with retries/backoff and ETag caching; store each version content-addressed (filename = SHA-256 digest), so history is immutable and deduplicated.
2. **Detection** — normalize both specs into 16 attributes per operation, then diff across **161 change kinds** in 15 categories (endpoint, operation, parameter, request body, response, schema, schema constraints, schema composition, servers, security, info, components, webhooks, tags, `$ref`). `schema_diff.py` walks schemas recursively — properties, required fields, enums, formats, `minimum`/`maxLength`/`pattern` constraints, `allOf`/`oneOf`/`anyOf` — up to a depth of 32. Each change carries a severity of `breaking`, `additive`, `deprecation` or `warning`; only `breaking` and `deprecation` produce impacts.
3. **Impact** — scan each file: `ast` for Python, dedicated tokenizers for JS/TS, Go, Ruby, Java, PHP, C#. Each scanner emits five usage kinds — call sites (`Usage`), headers, request bodies, auth patterns, and response handling — and `impact.py` joins each kind against the change kinds that can affect it. Call sites match on method plus path template; header/body/auth/response usages match on change category. Query strings and fragments are stripped during path extraction. Use `--languages` to limit which languages are scanned.
4. **Fix agent** — a LangGraph agent reads the impact report, proposes a patch, applies it, validates syntax (Python, JS, TS, TSX, JSX), checks for unreachable code and throw-in-expression patterns, and retries up to `FIX_MAX_ATTEMPTS` times. The LLM is any OpenAI-compatible endpoint with free-tier fallback on 429.
5. **Semantic guard** — after syntax validation, the agent re-scans the patched content with the AST scanner. If the removed endpoint is still called, the patch is rejected and the agent retries with the error as context.
6. **PR + CI self-heal** — Argus pushes the fixed files to a branch, opens a PR, and polls the check runs. On failure it extracts the error from the Actions job log, posts it as a PR comment, and re-runs the agent with the error as context — until CI is green or attempts run out.
7. **Merge-on-green** — with `--merge`, Argus squash-merges the PR when CI passes and deletes the fix branch. Merging is **opt-in** for the CLI, the webhook path and `POST /api/v1/pipeline`. It is still hard-coded on in the autonomous beat chain (`dispatch_scan_for_vendor`) — see [Known limits](#known-limits).

## Error handling

The pipeline gracefully handles:

- **GitHub API failures**: Automatic retry with exponential backoff on 429 (rate limit), 502, 503, 504
- **Malformed webhook payloads**: Returns 200 with error reason (no crash)
- **Pipeline exceptions**: Caught and returned as error dicts (no worker crash)
- **Per-vendor errors**: Caught individually in batch polling (other vendors continue)
- **File not found**: Graceful handling when scanned files are missing
- **Network errors**: Retry logic on all external API calls

## Demo

`scripts/demo_pr.py` runs the whole pipeline live: creates a seed repo calling removed GitHub endpoints, detects the breaking changes, scans, fixes, opens a PR, and self-heals from CI feedback.

`scripts/check_deprecated.py` checks which GitHub API endpoints are deprecated:

```powershell
python scripts/check_deprecated.py
```

`scripts/demo_search.py` seeds the changelog with 8 sample GitHub changes and lets you try the semantic search:

```powershell
python scripts/demo_search.py --db sqlite:///data/argus.db
uvicorn app.api.main:app
curl "http://127.0.0.1:8000/api/v1/search/changelog?q=transfer%20repository"
```

## Roadmap

- **Phase 1 (MVP):** detection ✅, scanning ✅, fix agent ✅, semantic guard ✅, PR + CI self-heal ✅, merge-on-green ✅, CLI + docker-compose ✅, live demo ✅
- **Phase 2:** vendor registry ✅, Postgres persistence ✅, pipeline service layer ✅, Celery workers + Redis ✅, GitHub App OAuth + webhooks ✅, FastAPI read API ✅
- **Phase 3:** AWS deployment — ECS Fargate, RDS, ElastiCache, S3, Terraform, GitHub Actions CI/CD ✅
- **Phase 4:** JS/TS scanning ✅, per-vendor agents ✅, real-time webhooks ✅, embedding-based changelog search ✅
- **Phase 5:** Guardrails ✅, error handling ✅, edge case fixes ✅, full end-to-end verification ✅
- **Phase 6:** Multi-language scanners (Go, Ruby, Java, PHP, C#) ✅, multi-vendor CLI flags ✅, 7 vendors ✅, server-rendered dashboard ✅
- **Phase 7:** Full change taxonomy (161 kinds) ✅, recursive schema diff ✅, response/body/auth/header usage scanning ✅, deterministic strategy registry ✅
- **Phase 8:** Autonomous pipeline (beat → detect → scan → fix → PR) ✅, control endpoints ✅, human-in-the-loop review (auto-merge off by default) ✅
- **Phase 9:** Auth (JWT + API keys) ✅, tenant scoping ✅, rate limiting ✅, Next.js dashboard ✅, PipelineRun tracking ✅, custom vendors + spec upload ✅, 710 tests ✅
- **Next:** close the auth gaps below, gate PR creation on a confidence threshold, wire the strategy registry into patch generation, and use per-installation tokens instead of one global credential

## AWS deployment

Two deployment options:

- **`infra/terraform/`** — production stack: VPC (2 AZs, NAT), RDS Postgres 16, ElastiCache Redis 7, S3 snapshot bucket, ECR repo, ECS Fargate cluster with `api` (behind an ALB), `worker`, and `beat` services, plus IAM roles and CloudWatch logging. Costs ~$130-150/month.
- **`infra/terraform-free/`** — single **EC2 `t4g.micro`** running the whole app via docker-compose. ~$0/month during the free tier. Recommended for free-tier accounts.

### Free-tier deployment

```powershell
# 1. AWS credentials (one time)
aws configure          # region: us-east-1, output: json

# 2. Upload secrets to SSM (one time)
.\scripts\aws\upload-secrets.ps1 -Region us-east-1 -Prefix /argus -EnvFile .env

# 3. Deploy
terraform -chdir=infra/terraform-free init
terraform -chdir=infra/terraform-free apply -var="ssh_cidr=<your-ip>/32"

# 4. Wait ~10 min for the container build, then check health
terraform -chdir=infra/terraform-free output health_url
```

**Pause / resume / teardown:**

```powershell
aws ec2 stop-instances --instance-ids $(terraform -chdir=infra/terraform-free output -raw instance_id)   # pause
aws ec2 start-instances --instance-ids $(terraform -chdir=infra/terraform-free output -raw instance_id)  # resume
terraform -chdir=infra/terraform-free destroy -var="ssh_cidr=<your-ip>/32" -auto-approve                 # delete
```

### CI/CD

- `.github/workflows/ci.yml` — ruff + pytest + `terraform validate` on every push/PR
- `.github/workflows/deploy.yml` — on push to `main`: test, build/push image to ECR, `terraform apply`, force new ECS deployments

## Known limits

Current as of the `s_upgrading101` tree. Each item names the file it lives in.

### Do not expose this deployment publicly yet

These are open holes in the auth model, not hardening suggestions.

- **Anyone can join any tenant.** `POST /api/v1/auth/register` needs no authentication and accepts a caller-supplied `tenant_id` ([api/main.py:278](app/api/main.py#L278)). Registering with someone else's `tenant_id` grants read access to their repositories, detection runs, pipeline runs, changelog, and installations. Tenant filtering is correct everywhere else — this one door bypasses all of it.
- **`AUTH_SECRET_KEY` defaults to `change-me-in-production`** ([core/config.py:58](app/core/config.py#L58)) with no startup guard. Deployed unset, every JWT is forgeable by anyone who has read this repository.
- **`/dashboard/*` and `GET /metrics` have no authentication and no tenant filter.** Every tenant's repositories, runs, and activity are served to any visitor who finds the URL.
- **Registering a repo can take it from another tenant.** `upsert_repository` matches on `owner`/`name` only ([db/repository.py:131](app/db/repository.py#L131)) and then overwrites `tenant_id`.

### The autonomous loop merges without review

`dispatch_scan_for_vendor` passes `{"merge": True}` on both the Celery and inline paths ([workers/tasks.py:122](app/workers/tasks.py#L122), [:130](app/workers/tasks.py#L130)), and `scan_and_fix` still defaults to `merge=True` ([workers/tasks.py:46](app/workers/tasks.py#L46)). The human-in-the-loop change covered the CLI, webhook, and `POST /api/v1/pipeline` paths only. So with beat running, every 6h an LLM-authored patch can reach a squash-merge on your default branch unattended. Disable beat, or pass `merge=False`, until this is reconciled.

There is also no confidence gate: `Change.confidence` exists ([detection/models.py:412](app/detection/models.py#L412)) but is never set or read, so a detector false positive goes straight to a PR.

### Detection and impact accuracy

- **Removed properties never produce an impact.** `_body_matches_change` and `_response_matches_change` test `change.new_value` for `SCHEMA_PROPERTY_REMOVED`, but [detection/schema_diff.py](app/detection/schema_diff.py) sets only `old_value` on a removal. A removed response field — the most common real-world breakage — is detected and then dropped at the join.
- **Body and response matching over-fires in the other direction.** `BodyUsage` and `ResponseUsage` are emitted with `path="/"` and a hard-coded method ([scan/scanner.py](app/scan/scanner.py)), so they carry no endpoint identity. Several matchers compensate by returning `True` unconditionally ([scan/impact.py](app/scan/impact.py)) — one breaking schema change then fans out to every body- or response-touching line in the repository.
- **`ChangeKind.REQUEST_BODY_PROPERTY_ADDED` is referenced but not defined** ([detection/schema_diff.py:107](app/detection/schema_diff.py#L107)). Raises `AttributeError` when a spec marks a field required that wasn't previously a declared property.
- **`endpoint_removed` means "absent from this spec file"**, not "removed from the API". A vendor reorganizing their spec repository reads as mass breakage.
- **Installation state is inverted** ([api/main.py:151](app/api/main.py#L151)): `unsuspended` records inactive, `suspend` records active.

### Fix stage

- **The strategy registry does not generate patches.** `run_fix` calls `get_strategy` only to *skip* work ([fix/agent.py:479](app/fix/agent.py#L479)); everything else goes to the LLM. The validators, guards, and replacement templates in [fix/strategies.py](app/fix/strategies.py) are not on the patch path, and `needs_llm()` is never called.
- **Some breaking changes are reported fixed without being touched.** Strategies with `llm_required=False` and no `pattern` hit the skip branch and return `success=True` with no code change — including `PARAM_REMOVED`, `PARAM_TYPE_CHANGED`, `RESPONSE_CODE_REMOVED`, `REQUEST_BODY_REMOVED`, and `REQUIRED_FIELD_REMOVED`.
- **Patches are single-line.** `apply_patch` replaces or deletes exactly one line ([fix/patch.py](app/fix/patch.py)), so migrations needing a new import, a reshaped body, or an added argument cannot be expressed. It also rejoins with `
`, converting CRLF files wholesale.
- **SDK calls are invisible.** The scanners find raw HTTP only. `stripe.Customer.create(...)` or `client.messages.create(...)` are not detected, which is most real usage for most of the registered vendors. Vendor `fix_guidance` tells the LLM to prefer SDK idioms, but nothing finds the call sites to begin with.
- Free-tier LLMs may produce no-op patches; the semantic guard catches these but adds latency.

### Operational

- **Changelog search is not pgvector.** Embeddings are stored in a JSON column and `search_changelog` loads every matching row to score cosine in Python ([db/repository.py](app/db/repository.py)) — no vector index, no `LIMIT` pushdown.
- **Two schema paths.** Alembic owns the deployed Postgres schema (`docker compose` runs `alembic upgrade head` once via the `migrate` service). The CLI, the test suite and SQLite still use `create_all` directly, which is equivalent — the Alembic baseline is generated from the same models and verified to produce an empty autogenerate diff. **The ECS deploy workflow does not yet run migrations**; `deploy.yml` force-deploys the services without an `alembic upgrade head` step, so a schema change needs one run by hand until that is wired up.
- **The broker-down fallback is unbounded.** When Redis is unreachable the full pipeline runs in a daemon thread inside the API process — no concurrency cap, no `X-GitHub-Delivery` idempotency, and the thread dies on restart.
- **`web/` has no CI coverage.** `ci.yml` runs `ruff check app tests`, pytest, and `terraform validate`; there is no Node or `npm run build` step.
- Semantic search falls back to keyword matching when `EMBEDDING_API_KEY` is not configured.
- GitHub App private key must be kept secret; classic PATs work as a simpler fallback. Credentials still resolve from one global `GITHUB_INSTALL_ID` — the `app_installations` rows are recorded but never used to mint per-tenant tokens.

### Scanner coverage

Python covers `requests`/`httpx` style calls, `requests.request()` dynamic calls, and async clients. JS/TS covers `fetch`, `axios`, `got`, `superagent`, `ky`. Go covers `net/http`, `go-resty`, framework routes. Ruby covers `Net::HTTP`, `HTTParty`, `RestClient`, `Typhoeus`. Java covers `HttpClient`, `RestTemplate`, `Unirest`, Apache, Feign. PHP covers Guzzle, Symfony, cURL, WordPress, Laravel. C# covers `HttpClient`, `RestSharp`, `Refit`. URL resolution handles module constants, local string assignments, f-strings, template literals, and `+` concatenation — anything computed at runtime is missed.