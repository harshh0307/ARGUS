# Argus

**The changelog that reads your codebase.**

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
| Semantic diff engine (breaking-change rules) | ✅ | normalized OpenAPI comparison |
| AST usage scanner + impact report | ✅ | Python `ast`, constant folding, template path matching |
| LangGraph fix agent (validate + retry) | ✅ | LangGraph, OpenAI-compatible LLMs |
| Semantic guard (no-op patch rejection) | ✅ | re-scans patched AST, rejects if removed endpoint still called |
| Multi-provider LLM + quota fallback | ✅ | Gemini / OpenAI primary, Nemotron free fallback on 429 |
| Merge-on-green (`--merge` flag) | ✅ | squash-merge when CI passes, branch cleanup |
| GitHub PR client + CI feedback loop | ✅ | httpx (REST API), Actions job logs |
| CLI + docker-compose | ✅ | argparse, Docker |
| Full end-to-end demo (PR self-heal) | ✅ | `scripts/demo_pr.py` (verified live) |
| Multi-vendor registry, workers, Postgres | Phase 2 | Celery + Redis, PostgreSQL |
| AWS cloud deployment | Phase 3 | ECS Fargate, RDS, Terraform |

## Project layout

```
app/
├── core/          # settings (pydantic-settings, 12-factor config)
├── ingestion/     # fetch specs, snapshot versioning
├── detection/     # normalize + semantic diff + breaking-change rules
├── scan/          # AST scanner, impact assessment
├── fix/           # LangGraph fix agent, patch engine, multi-provider LLM
├── github/        # GitHub client, CI log extraction, PR self-heal loop
└── cli.py         # argus detect/scan/fix/pr commands
scripts/
└── demo_pr.py     # full live pipeline demo (seed repo -> PR -> CI loop)
tests/             # pytest suite (90 tests)
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
| `GITHUB_TOKEN` | `argus pr`, demo | scopes: `repo`, `workflow` |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` | `argus fix`, `argus pr` | any OpenAI-compatible provider works via `LLM_BASE_URL` |
| `OPENROUTER_API_KEY` | fallback when primary LLM is rate-limited | free model: `nvidia/nemotron-3-ultra-550b-a55b:free` (verified) |
| `OPENROUTER_MODEL` | — | default `nvidia/nemotron-3-ultra-550b-a55b:free` |
| `LLM_MODEL` | — | default `gpt-4o-mini` |

## Usage

```powershell
argus detect                 # diff pinned old spec vs. current -> breaking/additive changes
argus scan [DIR]             # scan a repo for call sites hit by breaking changes
argus fix [DIR]              # apply LLM fixes in place (add --dry-run to preview diffs)
argus pr OWNER/REPO          # full loop: detect, scan, fix, open PR, self-heal on CI failure
argus pr OWNER/REPO --merge  # same, but squash-merge when CI passes
```

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
```

`argus pr` fetches the repo as a tarball through the GitHub API (no local git checkout needed; use `--dir` to scan a local checkout instead).

## Docker

```powershell
docker build -t argus:local .
docker run --rm argus:local detect
docker compose up             # scans ./repos with argus scan /repos
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
4. **Fix agent** — a LangGraph agent reads the impact report, proposes a patch, applies it, validates Python syntax, and retries up to `FIX_MAX_ATTEMPTS` times. The LLM is any OpenAI-compatible endpoint (Gemini, OpenAI, OpenRouter) with a free-tier fallback on 429 rate limits.
5. **Semantic guard** — after syntax validation, the agent re-scans the patched content with the AST scanner. If the removed endpoint is still called, the patch is rejected and the agent retries with the error as context. This prevents no-op patches (LLM echoing the original line) from being pushed.
6. **PR + CI self-heal** — Argus pushes the fixed files to a branch, opens a PR, and polls the check runs. On failure it extracts the error window from the Actions job log (`##[error]`/`Traceback`), posts it as a PR comment, and re-runs the agent with the error as context — until CI is green or attempts run out.
7. **Merge-on-green** — with `--merge`, Argus squash-merges the PR when CI passes and deletes the fix branch. If merge is rejected (e.g., branch protection), it warns and leaves the PR open.

## Demo

`scripts/demo_pr.py` runs the whole pipeline live: creates a seed repo calling removed GitHub endpoints, detects the breaking changes, scans, fixes, opens a PR, and self-heals from CI feedback (verified: PR went CI-fail -> fail -> green fully autonomously).

## Roadmap

- **Phase 1 (MVP):** detection ✅, scanning ✅, fix agent ✅, semantic guard ✅, PR + CI self-heal ✅, merge-on-green ✅, CLI + docker-compose ✅, live demo ✅
- **Phase 2:** multi-vendor registry, Postgres + Celery workers, GitHub App OAuth, tenant model
- **Phase 3:** AWS deployment — ECS Fargate, RDS, ElastiCache, S3, Terraform, GitHub Actions CI/CD
- **Phase 4:** JS/TS scanning, per-vendor agents, real-time webhooks, pgvector changelog search

## Known MVP limits

- Scans `requests`/`httpx` style HTTP calls; `requests.request("GET", ...)` style and async clients not yet supported
- Response-body usage analysis not yet supported
- Only the GitHub REST API vendor is wired (multi-vendor comes in Phase 2)
- Free-tier LLMs may produce no-op patches; the semantic guard catches these but adds latency (paid models fix this entirely)
