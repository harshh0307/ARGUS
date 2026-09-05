from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace

from app import cli
from app.scan.models import DriftSignal, Impact, Usage
from app.services import pipeline as svc


def usage(file="app.py", line=6, method="get", path="/repos/x/tags/protection"):
    return Usage(file, line, method, path)


def change(
    kind="endpoint_removed",
    path="/repos/{owner}/{repo}/tags/protection",
    method="delete",
    severity="breaking",
    detail="endpoint was removed",
):
    return DriftSignal(kind=kind, severity=severity, path=path, method=method, detail=detail)


def impact(file="app.py", line=6):
    return Impact(usage(file, line), change())


def settings(**overrides):
    defaults = {
        "github_token": "token",
        "api_base_url": "https://api.github.com",
        "fix_max_attempts": 3,
        "llm_model": "m",
        "llm_base_url": None,
        "gemini_api_key": None,
        "openai_api_key": "k",
        "openrouter_api_key": None,
        "openrouter_model": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_parser_has_all_commands():
    parser = cli.build_parser()
    for name in ("vendors", "scan", "fix"):
        assert name in parser._subparsers._group_actions[0].choices


def test_extract_tarball_strips_root_component(tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, is_dir in (
            ("repo-main-abc/", True),
            ("repo-main-abc/app.py", False),
            ("repo-main-abc/README.md", False),
        ):
            data = b"" if is_dir else (b"x" if name.endswith(".py") else b"readme")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.type = tarfile.DIRTYPE if is_dir else tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    svc._extract_tarball(buf.getvalue(), dest)
    assert (dest / "app.py").read_bytes() == b"x"
    assert (dest / "README.md").read_bytes() == b"readme"
