# Argus

**The changelog that reads your codebase.**

[![CI](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml)
[![Deploy](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Argus watches API vendors (Stripe, Twilio, GitHub...) by diffing their OpenAPI specs, scans your repositories for affected call sites, fixes them with an LLM agent, and opens a self-healing pull request.

> "API providers shouldn't just announce changes; they should apply them."
> When an API ships a breaking change, an agent should scan customer codebases, identify affected usages, and open a PR with the fix — like Dependabot, but for APIs.

## Why

- Breaking API changes ship with little warning
- Changelogs don't get read
- At AWS, over 30% of service downtime was caused by external API/package changes going unnoticed
- Agentic coding tools have proven developers trust tools with codebase access

## Architecture

```
spec poll ─▶ snapshot store ─▶ semantic diff ─▶ change events
                                              │
repo clone ─▶ AST usage scan ─▶ impact report ┤
                                              ▼
                       LangGraph fix agent ─▶ patch ─▶ branch + PR ─▶ CI verify loop
                          │  semantic guard ─┘                         ▲
                          └── syntax + AST re-scan rejects no-ops      │
                                              ▲                failure log ─┘
                                              └──────── (self-heal, max N attempts)
```

| Component | Status | Tech |
|---|---|---|
| Spec ingestion + snapshot store | ✅ | httpx, content-addressed JSON snapshots (SHA-256) |
| Vendor registry (multi-vendor) | ✅ | github + stripe + twilio built-ins, `argus vendors` |
| Postgres/SQLite persistence | ✅ | SQLAlchemy 2.0, psycopg; vendors, snapshots, detection runs |
| Celery workers + Redis | ✅ | Celery 5.6, Redis broker/backend, beat polling, `scan_and_fix` tasks |
| GitHub App auth (auto-refreshing install tokens) | ✅ | RS256 app JWT → installation access tokens, cached; PAT fallback |
| FastAPI read API + webhook receiver | ✅ | read-only dashboards, HMAC-verified GitHub webhooks |
| Real-time webhooks | ✅ | `push`, `installation`, `repository_dispatch` events → Celery dispatch (inline fallback) |
| Semantic diff engine (breaking-change rules) | ✅ | normalized OpenAPI comparison |
| AST usage scanner + impact report | ✅ | Python `ast` + JS/TS scanner (fetch/axios), constant folding, template path matching |
| LangGraph fix agent (validate + retry) | ✅ | LangGraph, OpenAI-compatible LLMs |
| Per-vendor fix agents | ✅ | vendor-specific guidance + model per vendor (`--vendor`) |
| Semantic guard (no-op patch rejection) | ✅ | re-scans patched AST, rejects if removed endpoint still called |
| Multi-provider LLM + quota fallback | ✅ | Gemini / OpenAI primary, Nemotron free fallback on 429 |
| Merge-on-green (`--merge` flag) | ✅ | squash-merge when CI passes, branch cleanup |
| GitHub PR client + CI feedback loop | ✅ | httpx (REST API), Actions job logs |
| Changelog + semantic search | ✅ | embeddings (OpenAI-compatible) + pgvector-capable Postgres, `/api/v1/search/changelog` |
| CLI + docker-compose | ✅ | argparse, Docker |
| Full end-to-end demo (PR self-heal) | ✅ | `scripts/demo_pr.py` (verified live) |
| Multi-vendor registry, workers, Postgres, API | ✅ | Celery + Redis, PostgreSQL, FastAPI |
| AWS cloud deployment | ✅ | ECS Fargate, RDS, ElastiCache, Terraform, GitHub Actions CI/CD |

## Project layout

```
app/
├── core/          # settings (pydantic-settings, 12-factor config)
├── ingestion/     # fetch specs, snapshot versioning
├── detection/     # normalize + semantic diff + breaking-change rules
├── scan/          # Python ast + JS/TS scanner, impact assessment
├── fix/           # LangGraph fix agent, patch engine, multi-provider LLM
├── github/        # GitHub client, App token auth, CI logs, PR self-heal loop
├── registry/      # vendor registry (github, stripe, twilio)
├── db/            # SQLAlchemy models + persistence layer
├── services/      # pipeline service layer (shared by CLI, workers, API)
├── search/        # changelog embeddings + cosine search
├── workers/       # Celery app + tasks
├── api/           # FastAPI read API + webhook receiver
└── cli.py         # argus detect/scan/fix/pr commands
infra/terraform/   # AWS IaC (VPC, RDS, ElastiCache, ECS Fargate, ALB)
.github/workflows/ # CI (tests+lint) + deploy (ECR → terraform → ECS)
scripts/
├── demo_pr.py     # full live pipeline demo (seed repo -> PR -> CI loop)
└── aws/           # upload-secrets.ps1 (SSM Parameter Store)
tests/             # pytest suite (319 tests)
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
| `DATABASE_URL` | `argus detect` persistence, API read endpoints | optional; `sqlite:///data/argus.db` or `postgresql+psycopg://...` (docker-compose has Postgres 16) |

## Usage

```powershell
argus vendors               # list registered spec vendors (github, stripe, twilio)
argus detect                # diff pinned old spec vs. current -> breaking/additive changes
argus detect --vendor stripe  # run detection for another vendor
argus scan [DIR]            # scan a repo (Python + JS/TS) for call sites hit by breaking changes
argus fix [DIR] --vendor github  # apply LLM fixes in place (--dry-run to preview diffs)
argus pr OWNER/REPO --vendor github  # full loop: detect, scan, fix, open PR, self-heal on CI failure
argus pr OWNER/REPO --merge  # same, but squash-merge when CI passes
```

### Celery workers (Phase 2)

```powershell
# worker (executes tasks from Redis)
celery -A app.workers.celery_app worker --loglevel=info

# beat (polls all vendors every 6h per the schedule)
celery -A app.workers.celery_app beat --loglevel=info
```

Tasks: `argus.poll_all_vendors` (beat-scheduled), `argus.run_detection`, `argus.scan_and_fix`, `argus.register_repository`. Requires `DATABASE_URL` and `REDIS_URL` (docker-compose provides Postgres + Redis).

### FastAPI (Phase 2)

```powershell
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

| Endpoint | Description |
|---|---|
| `GET /health` | liveness + database flag |
| `GET /api/v1/vendors` / `/api/v1/vendors/{slug}` | vendor registry |
| `GET /api/v1/detection-runs` / `.../{run_id}` | detection history from Postgres |
| `GET /api/v1/repositories` / `POST /api/v1/repositories` | register/list repos (`{owner, name, default_branch, vendor_slug}`) |
| `GET /api/v1/installations` | GitHub App installations (owner, active state) recorded from webhooks |
| `GET /api/v1/search/changelog?q=...&vendor=...&limit=...` | semantic search across detected changes (embeddings via `EMBEDDING_*`, keyword fallback; every `argus detect` batch-embeds new changes) |
| `POST /api/v1/webhook` | GitHub webhook receiver; HMAC-verified (needs `WEBHOOK_SECRET`). Events: `push` and `repository_dispatch` → `scan_and_fix` for registered repos; `installation` → upserts install rows (active on created/suspend, inactive on deleted/unsuspended). Dispatches via Celery with an inline-thread fallback when Redis is down |

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
```

## Test & lint

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
```

## How it works (in short)

1. **Ingestion** — fetch the vendor's OpenAPI spec with retries/backoff and ETag caching; store each version content-addressed (filename = SHA-256 digest), so history is immutable and deduplicated.
2. **Detection** — normalize both specs (strip descriptions, sort, keep only semantics), then apply rules: endpoint removed, parameter removed/required/type-changed, response code removed = `breaking`; new endpoints = `additive`.
3. **Impact** — scan each file: `ast` for Python; a dedicated tokenizer for JS/TS (`fetch()`, `axios.get/post`, `axios({method, url})`, template literals, module-level URL constants). Resolve f-string/template URLs via constant folding (`BASE = "https://api.github.com"`), match call sites against spec path templates (`/repos/{owner}/{repo}`), and join with breaking changes.
4. **Fix agent** — a LangGraph agent reads the impact report, proposes a patch, applies it, validates syntax (Python or JS depending on file), and retries up to `FIX_MAX_ATTEMPTS` times. Vendors may supply their own fix guidance and preferred model. The LLM is any OpenAI-compatible endpoint (Gemini, OpenAI, OpenRouter) with a free-tier fallback on 429 rate limits.
5. **Semantic guard** — after syntax validation, the agent re-scans the patched content with the AST scanner. If the removed endpoint is still called, the patch is rejected and the agent retries with the error as context. This prevents no-op patches (LLM echoing the original line) from being pushed.
6. **PR + CI self-heal** — Argus pushes the fixed files to a branch, opens a PR, and polls the check runs. On failure it extracts the error window from the Actions job log (`##[error]`/`Traceback`), posts it as a PR comment, and re-runs the agent with the error as context — until CI is green or attempts run out.
7. **Merge-on-green** — with `--merge`, Argus squash-merges the PR when CI passes and deletes the fix branch. If merge is rejected (e.g., branch protection), it warns and leaves the PR open.

## Demo

`scripts/demo_pr.py` runs the whole pipeline live: creates a seed repo calling removed GitHub endpoints, detects the breaking changes, scans, fixes, opens a PR, and self-heals from CI feedback (verified live: CI failures are fed back to the fix agent, semantic guard rejects no-op patches, and retries push real fixes).

`scripts/demo_search.py` seeds the changelog with 8 sample GitHub changes and lets you try the semantic search without a full live detection:

```powershell
python scripts/demo_search.py --db sqlite:///data/argus.db
uvicorn app.api.main:app
curl "http://127.0.0.1:8000/api/v1/search/changelog?q=transfer%20repository"
# 0.648 post /repos/{owner}/{repo}/transfer
```

## Roadmap

- **Phase 1 (MVP):** detection ✅, scanning ✅, fix agent ✅, semantic guard ✅, PR + CI self-heal ✅, merge-on-green ✅, CLI + docker-compose ✅, live demo ✅
- **Phase 2:** vendor registry ✅, Postgres persistence ✅, pipeline service layer ✅, Celery workers + Redis ✅, GitHub App OAuth + webhooks ✅, FastAPI read API ✅
- **Phase 3:** AWS deployment — ECS Fargate, RDS, ElastiCache, S3, Terraform, GitHub Actions CI/CD ✅ (IaC validated; apply requires an AWS account)
- **Phase 4:** JS/TS scanning ✅, per-vendor agents ✅, real-time webhooks ✅, pgvector changelog search ✅

## AWS deployment (Phase 3)

Two deployment options:

- **`infra/terraform/`** — production stack: VPC (2 AZs, NAT), RDS Postgres 16 (pgvector-compatible), ElastiCache Redis 7, S3 snapshot bucket, ECR repo, ECS Fargate cluster with `api` (behind an ALB), `worker`, and `beat` services, plus IAM roles and CloudWatch logging. Costs ~$130-150/month (not free-tier eligible).
- **`infra/terraform-free/`** — single **EC2 `t4g.micro`** running the whole app via docker-compose. ~$0/month during the free tier (750 hrs/mo t4g.micro + 30GB gp3 + public IPv4 are included). No ALB/NAT/RDS/ElastiCache. This is the recommended option for free-tier accounts — **it is the verified, live deployment used by this repo's author**.

### Free-tier deployment (`infra/terraform-free/`)

Creates: t4g.micro Ubuntu instance (20GB gp3), SSH key (saved to `keys/`), security group (SSH from your IP + API on 8000), Elastic IP, IAM role with SSM read **and SSM Session Manager access** (manage the instance without SSH), and cloud-init that installs Docker, clones the repo, pulls `.env` from SSM, and runs `docker compose up`.

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

Verified live with the following battle-tested fixes baked into `user_data.sh.tpl` / `docker-compose.yml`:

- Ubuntu 24.04 dropped the `awscli` apt package → the bootstrap installs it via `pip3 install awscli` instead
- Celery `beat` runs as a non-root user and could not write `/app/celerybeat-schedule` → `working_dir: /tmp` on the beat service
- The DB schema was created concurrently by `api`/`worker`/`beat` on startup, racing on Postgres → `init_db` now serializes DDL with a `pg_advisory_lock`
- All long-running services use `restart: unless-stopped` so the stack comes back up automatically after an instance reboot

Update the running app (from the instance): `git pull && docker compose up -d --build api worker beat` — automated in `scripts/aws/ec2-update.sh`.

**Pause / resume / teardown** (saves free-tier hours when you're not using it):

```powershell
aws ec2 stop-instances --instance-ids $(terraform -chdir=infra/terraform-free output -raw instance_id)   # pause (~$0/mo storage only)
aws ec2 start-instances --instance-ids $(terraform -chdir=infra/terraform-free output -raw instance_id)  # resume; containers auto-restart
terraform -chdir=infra/terraform-free destroy -var="ssh_cidr=<your-ip>/32" -auto-approve                 # delete everything
```

### One-time prerequisites

Run the bootstrap script — it creates the state bucket, DynamoDB lock table, GitHub OIDC provider + deploy role, attaches permissions, and uploads your `.env` secrets to SSM:

```powershell
.\scripts\aws\bootstrap.ps1 -Region us-east-1 -Environment dev -GitHubRepo your/ARGUS
```

It prints the two GitHub secrets to add (`AWS_DEPLOY_ROLE_ARN`, `TF_STATE_BUCKET`). If you'd rather do it manually:

1. **State bucket** — create an S3 bucket + DynamoDB lock table for Terraform state.
2. **AWS credentials** — configure locally via `aws configure` (or `AWS_PROFILE`).
3. **Secrets** — upload your `.env` secrets to SSM Parameter Store:

   ```powershell
   .\scripts\aws\upload-secrets.ps1 -Region us-east-1 -Prefix /argus -EnvFile .env
   ```

### Deploy

```powershell
terraform -chdir=infra/terraform init `
  -backend-config="bucket=<tf-state-bucket>" `
  -backend-config="key=argus/terraform.tfstate" `
  -backend-config="region=us-east-1"
terraform -chdir=infra/terraform apply

# build & push the image (or let GitHub Actions do it)
docker build -t <account>.dkr.ecr.us-east-1.amazonaws.com/argus-dev:<tag> .
docker push <account>.dkr.ecr.us-east-1.amazonaws.com/argus-dev:<tag>
```

The API is reachable at the ALB DNS name (from `terraform output alb_url`); health check: `GET /health`.

### CI/CD

- `.github/workflows/ci.yml` — ruff + pytest + `terraform validate` on every push/PR
- `.github/workflows/deploy.yml` — on push to `main`: test, build/push image to ECR, `terraform apply`, force new ECS deployments. The job is **skipped** (green) until `AWS_DEPLOY_ROLE_ARN` / `TF_STATE_BUCKET` secrets exist — run `scripts/aws/bootstrap.ps1` to create them and enable deployment.

Required GitHub secrets: `AWS_DEPLOY_ROLE_ARN` (OIDC role to assume), `TF_STATE_BUCKET`.

## Known MVP limits

- Python scanning covers `requests`/`httpx` style calls; `requests.request("GET", ...)` style and async clients not yet supported. JS/TS covers `fetch`/`axios` idioms only
- Response-body usage analysis not yet supported
- GitHub App private key must be kept secret; classic PATs work as a simpler fallback
- Free-tier LLMs may produce no-op patches; the semantic guard catches these but adds latency (paid models fix this entirely)
- Semantic search falls back to keyword matching when `EMBEDDING_API_KEY` is not configured
- Phase 3 AWS free-tier deployment (EC2 t4g.micro + docker-compose) verified live