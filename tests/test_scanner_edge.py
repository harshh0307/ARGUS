
from app.scan.scanner import ApiScanner, extract_path, language_for_file

BASE = "https://api.github.com"


def _scan(scanner, root):
    usages, _headers, _bodies, _auths, _responses = scanner.scan(root)
    return usages


def _scan_source(scanner, source, filename, **kwargs):
    usages, _headers, _bodies, _auths, _responses = scanner.scan_source(source, filename, **kwargs)
    return usages


def test_extract_path_strips_base_prefix():
    assert extract_path("https://api.github.com/users", BASE) == "/users"
    assert extract_path("/users", BASE) == "/users"
    assert extract_path("https://api.github.com/users/{id}/repos", BASE) == "/users/{id}/repos"


def test_extract_path_url_equal_to_base_is_none():
    assert extract_path("https://api.github.com", BASE) is None
    assert extract_path("https://api.github.com/", BASE) == "/"


def test_extract_path_relative_url_is_none():
    assert extract_path("users", BASE) is None
    assert extract_path("api.github.com/users", BASE) is None


def test_extract_path_missing_prefix_with_slash_is_path():
    assert extract_path("/users", "https://api.github.com/v3") == "/users"


def test_scanner_strips_trailing_slash_from_base(tmp_path):
    scanner = ApiScanner(base_url="https://api.github.com/")
    assert scanner.base_url == "https://api.github.com"


def test_language_for_file():
    assert language_for_file("a.py") == "py"
    assert language_for_file("a.PY") == "py"
    assert language_for_file("a.ts") == "js"
    assert language_for_file("a.tsx") == "js"
    assert language_for_file("a.mjs") == "js"
    assert language_for_file("a.cjs") == "js"
    assert language_for_file("a.txt") == "py"


def test_scan_empty_directory(tmp_path):
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_missing_directory(tmp_path):
    assert _scan(ApiScanner(BASE), tmp_path / "nope") == []


def test_scan_custom_ignore_dirs(tmp_path):
    (tmp_path / "skipme").mkdir()
    (tmp_path / "skipme" / "a.py").write_text(
        f'import requests; requests.get("{BASE}/hidden")', encoding="utf-8"
    )
    (tmp_path / "keep").mkdir()
    (tmp_path / "keep" / "b.py").write_text(
        f'import requests; requests.get("{BASE}/shown")', encoding="utf-8"
    )
    usages = _scan(ApiScanner(BASE, ignore_dirs={"skipme"}), tmp_path)
    assert [u.path for u in usages] == ["/shown"]


def test_scan_fstring_with_two_constants(tmp_path):
    (tmp_path / "a.py").write_text(
        f'API = "{BASE}"\nPATH = "/users"\nget(f"{{API}}{{PATH}}")',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert [u.path for u in usages] == ["/users"]
    assert usages[0].method == "get"


def test_scan_fstring_attribute_formatted_value_skipped(tmp_path):
    (tmp_path / "a.py").write_text(
        f'class C:\n    base = "{BASE}"\n\nget(f"{{C.base}}/users")',
        encoding="utf-8",
    )
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_fstring_nested_expression_skipped(tmp_path):
    (tmp_path / "a.py").write_text(
        'get(f"{build_url()}/users")',
        encoding="utf-8",
    )
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_call_without_arguments_skipped(tmp_path):
    (tmp_path / "a.py").write_text("get()\npost()\n", encoding="utf-8")
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_head_and_options_methods(tmp_path):
    (tmp_path / "a.py").write_text(
        f'head("{BASE}/health")\noptions("{BASE}/meta")',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert [(u.method, u.path) for u in usages] == [
        ("head", "/health"),
        ("options", "/meta"),
    ]


def test_scan_attribute_client_calls(tmp_path):
    (tmp_path / "a.py").write_text(
        f'client = requests.Session()\nclient.delete("{BASE}/users/1")',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert [(u.method, u.path) for u in usages] == [("delete", "/users/1")]


def test_scan_chained_assignment_constants(tmp_path):
    (tmp_path / "a.py").write_text(
        f'A = B = "{BASE}"\nget(f"{{B}}/users")',
        encoding="utf-8",
    )
    assert [u.path for u in _scan(ApiScanner(BASE), tmp_path)] == ["/users"]


def test_scan_uppercase_extension_file(tmp_path):
    (tmp_path / "a.PY").write_text(
        f'get("{BASE}/upper")',
        encoding="utf-8",
    )
    assert [u.path for u in _scan(ApiScanner(BASE), tmp_path)] == ["/upper"]


def test_scan_binary_file_is_skipped(tmp_path):
    (tmp_path / "bin.py").write_bytes(b"\xff\xfe\x00\x01 garbage")
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_relative_file_paths(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        f'get("{BASE}/nested")',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].file == "pkg/mod.py"
    assert usages[0].line == 1


def test_scan_source_language_override_js(tmp_path):
    source = f'fetch("{BASE}/from-js")'
    usages = _scan_source(ApiScanner(BASE), source, "x.txt", language="js")
    assert [u.path for u in usages] == ["/from-js"]


def test_scan_source_language_override_py_for_js_file(tmp_path):
    source = f'const x = fetch("{BASE}/x");'
    assert _scan_source(ApiScanner(BASE), source, "x.js", language="py") == []


def test_scan_results_sorted_by_file_line_method_path(tmp_path):
    (tmp_path / "b.py").write_text(
        f'post("{BASE}/z")\nget("{BASE}/a")',
        encoding="utf-8",
    )
    (tmp_path / "a.py").write_text(
        f'get("{BASE}/m")',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    keys = [(u.file, u.line, u.method, u.path) for u in usages]
    assert keys == sorted(keys)
    assert keys == [
        ("a.py", 1, "get", "/m"),
        ("b.py", 1, "post", "/z"),
        ("b.py", 2, "get", "/a"),
    ]


def test_scan_non_http_url_ignored(tmp_path):
    (tmp_path / "a.py").write_text(
        'get("ftp://example.com/x")\nget("https://other.example.com/y")',
        encoding="utf-8",
    )
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_file_with_syntax_error_skipped(tmp_path):
    (tmp_path / "a.py").write_text("def broken(:\n", encoding="utf-8")
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_scan_fstring_constant_defined_after_use(tmp_path):
    (tmp_path / "a.py").write_text(
        'get(f"{API}/users")\nAPI = "https://api.github.com"',
        encoding="utf-8",
    )
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert [u.path for u in usages] == ["/users"]


def test_scan_ignores_venv_and_git(tmp_path):
    for sub in (".venv", ".git", "__pycache__", "node_modules"):
        (tmp_path / sub).mkdir(parents=True)
        (tmp_path / sub / "a.py").write_text(
            f'get("{BASE}/ignored")',
            encoding="utf-8",
        )
    (tmp_path / "real.py").write_text(f'get("{BASE}/kept")', encoding="utf-8")
    assert [u.path for u in _scan(ApiScanner(BASE), tmp_path)] == ["/kept"]


def test_scan_utf8_bom_handled(tmp_path):
    (tmp_path / "a.py").write_bytes(b"\xef\xbb\xbf" + f'get("{BASE}/bom")'.encode())
    assert [u.path for u in _scan(ApiScanner(BASE), tmp_path)] == ["/bom"]