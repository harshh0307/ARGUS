from pathlib import Path

from app.scan.scanner import ApiScanner

BASE = "https://api.github.com"


def write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _scan(scanner, root):
    usages, _headers, _bodies, _auths, _responses = scanner.scan(root)
    return usages


def test_finds_plain_url_call(tmp_path):
    write(tmp_path, "app.py", 'import requests\nresp = requests.get("https://api.github.com/repos/me/proj")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    u = usages[0]
    assert (u.method, u.path, u.line) == ("get", "/repos/me/proj", 2)
    assert u.file.endswith("app.py")


def test_finds_fstring_with_base_constant(tmp_path):
    write(
        tmp_path,
        "app.py",
        'BASE = "https://api.github.com"\n'
        'resp = requests.get(f"{BASE}/repos/{owner}/{repo}")\n',
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert usages[0].path == "/repos/{owner}/{repo}"


def test_finds_fstring_without_base(tmp_path):
    write(tmp_path, "app.py", 'resp = httpx.get(f"/repos/{owner}/issues")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert usages[0].path == "/repos/{owner}/issues"


def test_attribute_client_call(tmp_path):
    write(tmp_path, "app.py", 'client.post("https://api.github.com/repos/me")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("post", "/repos/me")


def test_ignores_other_domains(tmp_path):
    write(tmp_path, "app.py", 'requests.get("https://api.stripe.com/v1/charges")\n')
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_ignores_non_http_calls(tmp_path):
    write(tmp_path, "app.py", 'print("hello")\n')
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_syntax_error_file_is_skipped(tmp_path):
    write(tmp_path, "broken.py", "def (:\n")
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_ignores_venv_and_git(tmp_path):
    write(tmp_path, ".venv/x.py", 'requests.get("https://api.github.com/repos/a")\n')
    write(tmp_path, "app.py", 'requests.get("https://api.github.com/repos/b")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert [u.path for u in usages] == ["/repos/b"]


def test_line_numbers(tmp_path):
    write(tmp_path, "app.py", 'import requests\n\nresp = requests.get("https://api.github.com/repos/me")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].line == 3


def test_utf8_bom_is_handled(tmp_path):
    write(tmp_path, "app.py", '\ufeffimport requests\nrequests.get("https://api.github.com/repos/me")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert usages[0].path == "/repos/me"


def test_scan_returns_relative_file_paths(tmp_path):
    write(tmp_path, "pkg/app.py", 'requests.get("https://api.github.com/repos/me")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert usages[0].file == "pkg/app.py"
    assert not Path(usages[0].file).is_absolute()
