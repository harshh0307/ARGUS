# Argus

**The changelog that reads your codebase.**

[![CI](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/ci.yml)
[![Deploy](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml/badge.svg)](https://github.com/harshh0307/ARGUS/actions/workflows/deploy.yml)
[![Python 3.14](https://img.shields.io/badge/python-3.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Argus watches API vendors (GitHub, Stripe, Twilio, Slack, AWS, Azure, Google Cloud) by diffing their OpenAPI specs, scans your repositories across 8 languages, fixes them with an LLM agent, and opens a self-healing pull request.

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
| Vendor registry (multi-vendor) | ✅ | github, stripe, twilio, slack, aws, azure, google_cloud built-ins, `argus vendors` |
| Postgres/SQLite persistence | ✅ | SQLAlchemy 2.0, psycopg; vendors, snapshots, detection runs |
| Celery workers + Redis | ✅ | Celery 5.6, Redis broker/backend, beat polling, `scan_and_fix` tasks |
| GitHub App auth (auto-refreshing install tokens) | ✅ | RS256 app JWT → installation access tokens, cached; PAT fallback |
| FastAPI read API + webhook receiver | ✅ | read-only dashboards, HMAC-verified GitHub webhooks |
| Real-time webhooks | ✅ | `push`, `installation`, `repository_dispatch` events → Celery dispatch (inline fallback) |
| Semantic diff engine (breaking-change rules) | ✅ | normalized OpenAPI comparison |
| AST usage scanner + impact report | ✅ | Python, JS/TS, Go, Ruby, Java, PHP, C# scanner; constant folding, template path matching |
| LangGraph fix agent (validate + retry) | ✅ | LangGraph, OpenAI-compatible LLMs |
| Per-vendor fix agents | ✅ | vendor-specific guidance + model per vendor (`--vendor`) |
| Semantic guard (no-op patch rejection) | ✅ | re-scans patched AST, rejects if removed endpoint still called |
| Multi-provider LLM + quota fallback | ✅ | Gemini / OpenAI primary, Nemotron free fallback on 429 |
| Merge-on-green (`--merge` flag) | ✅ | squash-merge when CI passes, branch cleanup |
| GitHub PR client + CI feedback loop | ✅ | httpx (REST API), Actions job logs |
| Changelog + semantic search | ✅ | embeddings (OpenAI-compatible) + pgvector-capable Postgres, `/api/v1/search/changelog` |
| CLI + docker-compose | ✅ | argparse, Docker, `--languages` + `--vendors` flags |
| Web dashboard | ✅ | TailwindCSS, Chart.js, vendor status, activity charts, repo list |
| Full end-to-end demo (PR self-heal) | ✅ | `scripts/demo_pr.py` (verified live) |
| Multi-vendor registry, workers, Postgres, API | ✅ | Celery + Redis, PostgreSQL, FastAPI |
| AWS cloud deployment | ✅ | ECS Fargate, RDS, ElastiCache, Terraform, GitHub Actions CI/CD |

## How It Works (end-to-end)

```
1. Webhook received (push event)
       ↓
2. Repo downloaded as tarball
       ↓
3. Old spec (pinned) vs new spec (latest) → semantic diff
       ↓
4. Diff finds breaking changes (removed endpoints, changed params, etc.)
       ↓
5. Scanner finds ALL API call sites in codebase
       ↓
6. Impact assessment: match call sites AGAINST breaking changes only
       ↓
7. LLM generates fixes for each impacted call site
       ↓
8. Validator checks: syntax (Python/JS), unreachable code, throw-in-expression
       ↓
9. Semantic guard: re-scans patched code, rejects if still calls removed endpoint
       ↓
10. Fixes committed to branch, PR opened
       ↓
11. CI check runs polled → on failure, error fed back to LLM → retry
       ↓
12. When CI passes → merge (optional)
```

**Key insight:** Argus only fixes endpoints that have a **breaking diff** in the spec AND are **actually called** in the codebase. Non-breaking changes and unused endpoints are ignored.

## Project layout

```
app/
├── core/          # settings (pydantic-settings, 12-factor config)
├── ingestion/     # fetch specs, snapshot versioning
├── detection/     # normalize + semantic diff + breaking-change rules
├── scan/          # multi-language scanners (Python, JS/TS, Go, Ruby, Java, PHP, C#)
│   ├── scanner.py      # main scanner with language dispatch
│   ├── python_scanner.py  # Python ast + requests/httpx/aiohttp
│   ├── js_scanner.py      # JS/TS fetch/axios/got/superagent/ky
│   ├── go_scanner.py      # Go net/http, go-resty, echo/gin/mux
│   ├── ruby_scanner.rb    # Ruby Net::HTTP, HTTParty, RestClient
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
│   └── errors.py      # error classification (rate limit, timeout, etc.)
├── github/        # GitHub client, App token auth, CI logs, PR self-heal loop
├── registry/      # vendor registry (github, stripe, twilio, slack, aws, azure, google_cloud)
├── db/            # SQLAlchemy models + persistence layer
├── services/      # pipeline service layer (shared by CLI, workers, API)
├── search/        # changelog embeddings + cosine search
├── workers/       # Celery app + tasks
├── api/           # FastAPI read API + webhook receiver + web dashboard
│   ├── main.py         # FastAPI app with routes
│   ├── dashboard.py    # dashboard endpoints (vendors, activity, repos)
│   └── templates/      # HTML templates (TailwindCSS + Chart.js)
└── cli.py         # argus detect/scan/fix/pr commands
infra/terraform/   # AWS IaC (VPC, RDS, ElastiCache, ECS Fargate, ALB)
.github/workflows/ # CI (tests+lint) + deploy (ECR → terraform → ECS)
scripts/
├── demo_pr.py     # full live pipeline demo (seed repo -> PR -> CI loop)
├── check_deprecated.py  # check deprecated API endpoints
├── test_hmac.py   # test HMAC webhook signature
└── aws/           # upload-secrets.ps1 (SSM Parameter Store)
tests/             # pytest suite (567 tests)
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

Tasks: `argus.poll_all_vendors` (beat-scheduled), `argus.run_detection`, `argus.scan_and_fix`, `argus.register_repository`. Requires `DATABASE_URL` and `REDIS_URL` (docker-compose provides Postgres + Redis).

### FastAPI

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
| `POST /api/v1/webhook` | GitHub webhook receiver; HMAC-verified (needs `WEBHOOK_SECRET`). Events: `push` and `repository_dispatch` → `scan_and_fix` for registered repos; `installation` → upserts install rows. Malformed payloads return 200 with error reason (no crash) |
| `GET /dashboard` | Web dashboard overview (vendor status, breaking/additive stats, recent runs) |
| `GET /dashboard/vendors` | Vendor detail pages with run history |
| `GET /dashboard/activity` | Activity chart (Chart.js stacked bar, changes over time) |
| `GET /dashboard/repositories` | Registered repositories list |

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

## How it works (detailed)

1. **Ingestion** — fetch the vendor's OpenAPI spec with retries/backoff and ETag caching; store each version content-addressed (filename = SHA-256 digest), so history is immutable and deduplicated.
2. **Detection** — normalize both specs (strip descriptions, sort, keep only semantics), then apply rules: endpoint removed, parameter removed/required/type-changed, response code removed = `breaking`; new endpoints = `additive`.
3. **Impact** — scan each file: `ast` for Python, dedicated tokenizer for JS/TS, Go, Ruby, Java, PHP, C#. Resolve variable-assigned URLs via constant folding, match call sites against spec path templates, and join with breaking changes. Query strings and fragments are stripped during path extraction. Use `--languages` to limit which languages are scanned.
4. **Fix agent** — a LangGraph agent reads the impact report, proposes a patch, applies it, validates syntax (Python, JS, TS, TSX, JSX), checks for unreachable code and throw-in-expression patterns, and retries up to `FIX_MAX_ATTEMPTS` times. The LLM is any OpenAI-compatible endpoint with free-tier fallback on 429.
5. **Semantic guard** — after syntax validation, the agent re-scans the patched content with the AST scanner. If the removed endpoint is still called, the patch is rejected and the agent retries with the error as context.
6. **PR + CI self-heal** — Argus pushes the fixed files to a branch, opens a PR, and polls the check runs. On failure it extracts the error from the Actions job log, posts it as a PR comment, and re-runs the agent with the error as context — until CI is green or attempts run out.
7. **Merge-on-green** — with `--merge`, Argus squash-merges the PR when CI passes and deletes the fix branch.

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
- **Phase 4:** JS/TS scanning ✅, per-vendor agents ✅, real-time webhooks ✅, pgvector changelog search ✅
- **Phase 5:** Guardrails ✅, error handling ✅, edge case fixes ✅, full end-to-end verification ✅
- **Phase 6:** Multi-language scanners (Go, Ruby, Java, PHP, C#) ✅, multi-vendor CLI flags ✅, 7 vendors ✅, web dashboard ✅, 567 tests ✅

## AWS deployment

Two deployment options:

- **`infra/terraform/`** — production stack: VPC (2 AZs, NAT), RDS Postgres 16 (pgvector-compatible), ElastiCache Redis 7, S3 snapshot bucket, ECR repo, ECS Fargate cluster with `api` (behind an ALB), `worker`, and `beat` services, plus IAM roles and CloudWatch logging. Costs ~$130-150/month.
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

- Python scanning covers `requests`/`httpx` style calls, `requests.request()` dynamic calls, and async clients. JS/TS covers `fetch`, `axios`, `got`, `superagent`, and `ky`. Go covers `net/http`, `go-resty`, and framework routes. Ruby covers `Net::HTTP`, `HTTParty`, `RestClient`, `Typhoeus`. Java covers `HttpClient`, `RestTemplate`, `Unirest`, Apache, Feign. PHP covers Guzzle, Symfony, cURL, WordPress, Laravel. C# covers `HttpClient`, `RestSharp`, `Refit`.
- Response-body usage analysis not yet supported
- GitHub App private key must be kept secret; classic PATs work as a simpler fallback
- Free-tier LLMs may produce no-op patches; the semantic guard catches these but adds latency
- Semantic search falls back to keyword matching when `EMBEDDING_API_KEY` is not configured