
from app.scan.js_scanner import JsScanner
from app.scan.scanner import ApiScanner, language_for_file

BASE = "https://api.github.com"


def write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def scan_js(source, filename="app.js"):
    return JsScanner(BASE).scan_source(source, filename)


def test_fetch_defaults_to_get(tmp_path):
    write(tmp_path, "app.js", 'const resp = await fetch("https://api.github.com/repos/me/proj");\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path, usages[0].line) == ("get", "/repos/me/proj", 1)


def test_fetch_method_from_options(tmp_path):
    write(
        tmp_path,
        "app.js",
        'fetch("/repos/me/proj", { method: "DELETE", headers: {} })\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("delete", "/repos/me/proj")


def test_fetch_options_spans_lines(tmp_path):
    write(
        tmp_path,
        "app.js",
        'fetch(\n  "/repos/me",\n  {\n    method: "post",\n  },\n)\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path, usages[0].line) == ("post", "/repos/me", 1)


def test_axios_method_call(tmp_path):
    write(tmp_path, "app.ts", 'axios.get("https://api.github.com/repos/me/issues")\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("get", "/repos/me/issues")


def test_axios_options_object(tmp_path):
    write(
        tmp_path,
        "api.js",
        'axios({ method: "PATCH", url: "/repos/me", data: {} })\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("patch", "/repos/me")


def test_axios_base_constant(tmp_path):
    write(
        tmp_path,
        "api.ts",
        'const BASE = "https://api.github.com";\n'
        'axios.get(`${BASE}/repos/${owner}/collaborators`)\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert usages[0].path == "/repos/{owner}/collaborators"


def test_template_literal_without_base(tmp_path):
    write(
        tmp_path,
        "api.ts",
        'const id = 7;\nfetch(`/repos/${id}`)\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert usages[0].path == "/repos/{id}"


def test_ignores_other_domains(tmp_path):
    write(tmp_path, "app.js", 'fetch("https://api.stripe.com/v1/charges")\n')
    assert ApiScanner(BASE).scan(tmp_path) == []


def test_ignores_non_http_calls(tmp_path):
    write(tmp_path, "app.js", 'console.log("hi")\n')
    assert ApiScanner(BASE).scan(tmp_path) == []


def test_jsx_and_mjs_scanned(tmp_path):
    write(tmp_path, "client.jsx", 'fetch("/repos/a")\n')
    write(tmp_path, "worker.mjs", 'fetch("/repos/b")\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert sorted(u.path for u in usages) == ["/repos/a", "/repos/b"]


def test_python_and_js_in_same_repo(tmp_path):
    write(tmp_path, "app.py", 'requests.get("https://api.github.com/repos/py")\n')
    write(tmp_path, "app.js", 'fetch("/repos/js")\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert sorted(u.path for u in usages) == ["/repos/js", "/repos/py"]


def test_node_modules_ignored(tmp_path):
    write(tmp_path, "node_modules/x/app.js", 'fetch("/repos/a")\n')
    write(tmp_path, "app.js", 'fetch("/repos/b")\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert [u.path for u in usages] == ["/repos/b"]


def test_quoted_object_keys(tmp_path):
    write(tmp_path, "app.js", 'axios({ "method": "PUT", url: "/repos/me" })\n')
    usages = ApiScanner(BASE).scan(tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("put", "/repos/me")


def test_comment_and_string_are_skipped(tmp_path):
    write(
        tmp_path,
        "app.js",
        '// fetch("/repos/comment")\n'
        'const note = "fetch(\\"/repos/string\\")";\n'
        'fetch("/repos/real")\n',
    )
    usages = ApiScanner(BASE).scan(tmp_path)
    assert [u.path for u in usages] == ["/repos/real"]


def test_scan_source_language_override():
    js = 'fetch("/repos/me")'
    usages = ApiScanner(BASE).scan_source(js, filename="plain.txt", language="js")
    assert len(usages) == 1
    assert usages[0].path == "/repos/me"
    assert language_for_file("app.ts") == "js"
    assert language_for_file("app.py") == "py"