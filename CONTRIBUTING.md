# Contributing to Argus

Thanks for your interest! This guide covers how to contribute code, report
issues, and get your changes merged.

## Quick links

- [README](README.md) — architecture, setup, usage
- [Code of conduct](#code-of-conduct) — be kind, always

## Development setup

Requires Python 3.14.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env   # then fill in at least GITHUB_TOKEN
```

## Before you start

1. **Open an issue** describing what you want to change (or pick an existing
   one) so maintainers can discuss the approach before you write code.
2. **Check the roadmap** in the README — some areas (e.g. AWS deployment) have
   specific planned work.

## Making changes

1. Fork the repo (external contributors) or create a branch.
2. Keep changes focused — one feature/bugfix per PR.
3. Follow existing code style: ruff with `line-length = 100`.
4. Add or update tests in `tests/` for any behavior change.

## Checks that must pass

Run these locally before pushing:

```powershell
.\.venv\Scripts\python -m ruff check app tests
.\.venv\Scripts\python -m pytest -q
```

For Terraform changes:

```powershell
terraform fmt -recursive infra/terraform
terraform validate -chdir=infra/terraform   # requires terraform init
```

CI runs all of the above on every push/PR — a red check blocks the merge.

## Commit conventions

- Write clear commit messages in the imperative mood: "Add foo", "Fix bar".
- Keep the working tree clean of generated files (`.terraform/`, `.venv/`,
  `data/`, `*.pem` are gitignored).
- **Never commit secrets.** `.env` is gitignored; if you need a new config
  option, add it to `.env.example` with an empty value.

## Code of conduct

- Be respectful and constructive in discussions and reviews.
- Assume good intent; focus feedback on the code, not the person.
- Harassment of any kind is not tolerated.

## Questions

Open a discussion or issue; the maintainers are happy to help.