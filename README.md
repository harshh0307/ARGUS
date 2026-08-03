# Argus

**The changelog that reads your codebase.**

Argus watches API vendors (Stripe, Twilio, GitHub...) by diffing their OpenAPI specs, scans your repositories for affected call sites, and automatically opens a pull request with the fix.

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
repo clone ─▶ AST usage scan ─▶ impact report ─┤
                                              ▼
                       LangGraph fix agent ─▶ patch ─▶ branch + PR ─▶ CI verify loop
```

| Component | Status | Tech |
|---|---|---|
| Spec ingestion + snapshot store | ✅ done | httpx, content-addressed JSON snapshots |
| Semantic diff engine (breaking-change rules) | ✅ done | normalized OpenAPI comparison |
| AST usage scanner + impact report | ✅ done | Python `ast`, constant folding, template path matching |
| LangGraph fix agent | ⏳ next | LangGraph |
| GitHub PR client + CI feedback loop | pending | PyGithub |
| CLI + docker-compose + full demo | pending | FastAPI, Docker |
| Multi-vendor registry, workers, Postgres | Phase 2 | Celery + Redis, PostgreSQL |
| AWS cloud deployment | Phase 3 | ECS Fargate, RDS, Terraform |

## Project layout

```
app/
├── core/          # settings (pydantic-settings, 12-factor config)
├── ingestion/     # fetch specs, snapshot versioning
├── detection/     # normalize + semantic diff + breaking-change rules
└── scan/          # AST scanner, impact assessment
tests/             # pytest suite (34 tests)
```

## Setup

Requires Python 3.14.

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

## Usage

Detect breaking changes between the pinned old spec (Jan 2026) and the current GitHub API spec, then find impacted call sites in a repo:

```powershell
.\.venv\Scripts\python -c "
from app.core.config import get_settings
from app.detection.detect import run_detection
result = run_detection(get_settings())
print(result['breaking_count'], 'breaking changes')
"
```

Scan a repo for GitHub API usages:

```powershell
.\.venv\Scripts\python -c "
from app.scan.scanner import ApiScanner
for u in ApiScanner('https://api.github.com').scan('path/to/repo'):
    print(u)
"
```

## Test & lint

```powershell
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
```

## How it works (in short)

1. **Ingestion** — fetch the vendor's OpenAPI spec with retries/backoff and ETag caching; store each version content-addressed (filename = SHA-256 digest), so history is immutable and deduplicated.
2. **Detection** — normalize both specs (strip descriptions, sort, keep only semantics), then apply rules: endpoint removed, parameter removed/required/type-changed, response code removed = `breaking`; new endpoints = `additive`.
3. **Impact** — parse each Python file with `ast`, resolve f-string URLs via constant folding (`BASE = "https://api.github.com"`), match call sites against spec path templates (`/repos/{owner}/{repo}`), and join with breaking changes.
4. **Fix agent (next)** — a LangGraph agent reads the impact report, edits the code, validates with a syntax check, and opens a PR. CI failures feed back into the agent for self-healing (max 3 retries).

## Roadmap

- **Phase 1 (MVP):** full loop on a real vendor — detection ✅, scanning ✅, fix agent, PR + CI loop, CLI + docker-compose demo
- **Phase 2:** multi-vendor registry, Postgres + Celery workers, GitHub App OAuth, tenant model
- **Phase 3:** AWS deployment — ECS Fargate, RDS, ElastiCache, S3, Terraform, GitHub Actions CI/CD
- **Phase 4:** JS/TS scanning, per-vendor agents, real-time webhooks, pgvector changelog search

## Known MVP limits

- Scans `requests`/`httpx` style HTTP calls; `requests.request("GET", ...)` style and async clients not yet supported
- Response-body usage analysis not yet supported
- Only the GitHub REST API vendor is wired (multi-vendor comes in Phase 2)
