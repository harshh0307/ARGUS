from app.scan.js_scanner import JsScanner

BASE = "https://api.github.com"


def scan(source):
    return JsScanner(BASE).scan_source(source, "app.js")


def paths(source):
    return [u.path for u in scan(source)]


# ─── got ────────────────────────────────────────────────────────────────────


def test_got_get():
    usages = scan(f'got.get("{BASE}/users");')
    assert [(u.method, u.path) for u in usages] == [("get", "/users")]


def test_got_post():
    usages = scan(f'got.post("{BASE}/repos");')
    assert [(u.method, u.path) for u in usages] == [("post", "/repos")]


def test_got_put():
    usages = scan(f'got.put("{BASE}/users/1");')
    assert usages[0].method == "put"
    assert usages[0].path == "/users/1"


def test_got_patch():
    usages = scan(f'got.patch("{BASE}/orgs/acme");')
    assert usages[0].method == "patch"
    assert usages[0].path == "/orgs/acme"


def test_got_delete():
    usages = scan(f'got.delete("{BASE}/users/1");')
    assert usages[0].method == "delete"
    assert usages[0].path == "/users/1"


def test_got_head():
    usages = scan(f'got.head("{BASE}/health");')
    assert usages[0].method == "head"
    assert usages[0].path == "/health"


def test_got_options():
    usages = scan(f'got.options("{BASE}/users");')
    assert usages[0].method == "options"
    assert usages[0].path == "/users"


def test_got_get_template_literal():
    usages = scan('got.get(`https://api.github.com/users/${id}`);')
    assert usages[0].path == "/users/{id}"


def test_got_get_with_constant():
    usages = scan(f'const BASE = "{BASE}";\ngot.get(`${{BASE}}/repos`);')
    assert usages[0].path == "/repos"


# ─── superagent ─────────────────────────────────────────────────────────────


def test_superagent_get():
    usages = scan(f'superagent.get("{BASE}/users");')
    assert [(u.method, u.path) for u in usages] == [("get", "/users")]


def test_superagent_post():
    usages = scan(f'superagent.post("{BASE}/repos");')
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_superagent_put():
    usages = scan(f'superagent.put("{BASE}/users/1");')
    assert usages[0].method == "put"
    assert usages[0].path == "/users/1"


def test_superagent_delete():
    usages = scan(f'superagent.delete("{BASE}/users/1");')
    assert usages[0].method == "delete"


def test_superagent_request_style():
    usages = scan(f'superagent("GET", "{BASE}/users");')
    assert usages[0].method == "get"
    assert usages[0].path == "/users"


def test_superagent_request_post():
    usages = scan(f'superagent("POST", "{BASE}/repos");')
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_superagent_get_template_literal():
    usages = scan('superagent.get(`https://api.github.com/users/${id}`);')
    assert usages[0].path == "/users/{id}"


# ─── ky ─────────────────────────────────────────────────────────────────────


def test_ky_get():
    usages = scan(f'ky.get("{BASE}/users");')
    assert [(u.method, u.path) for u in usages] == [("get", "/users")]


def test_ky_post():
    usages = scan(f'ky.post("{BASE}/repos");')
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_ky_put():
    usages = scan(f'ky.put("{BASE}/users/1");')
    assert usages[0].method == "put"
    assert usages[0].path == "/users/1"


def test_ky_patch():
    usages = scan(f'ky.patch("{BASE}/orgs/acme");')
    assert usages[0].method == "patch"
    assert usages[0].path == "/orgs/acme"


def test_ky_delete():
    usages = scan(f'ky.delete("{BASE}/users/1");')
    assert usages[0].method == "delete"


def test_ky_get_with_constant():
    usages = scan(f'const BASE = "{BASE}";\nky.get(`${{BASE}}/items`);')
    assert usages[0].path == "/items"


def test_ky_get_template_literal():
    usages = scan('ky.get(`https://api.github.com/items/${id}`);')
    assert usages[0].path == "/items/{id}"


# ─── mixed patterns ────────────────────────────────────────────────────────


def test_multiple_libs_in_same_file():
    content = (
        f'import got from "got";\n'
        f'import ky from "ky";\n'
        f'got.get("{BASE}/a");\n'
        f'ky.get("{BASE}/b");\n'
    )
    usages = scan(content)
    paths = [u.path for u in usages]
    assert "/a" in paths and "/b" in paths


def test_got_get_relative_url():
    usages = scan('got.get("/users/1");')
    assert usages[0].path == "/users/1"


def test_ky_get_relative_url():
    usages = scan('ky.get("/repos");')
    assert usages[0].path == "/repos"


def test_superagent_get_relative_url():
    usages = scan('superagent.get("/orgs");')
    assert usages[0].path == "/orgs"


def test_got_get_url_equal_to_base_skipped():
    usages = scan(f'got.get("{BASE}");')
    assert usages == []


def test_ky_get_url_equal_to_base_skipped():
    usages = scan(f'ky.get("{BASE}");')
    assert usages == []


def test_unknown_lib_not_scanned():
    usages = scan('axiosx.get("/x");')
    assert usages == []


def test_unknown_lib_method_not_scanned():
    usages = scan('got.request("/x");')
    assert usages == []


def test_got_get_options_object_with_method():
    usages = scan(f'got("{BASE}/users", {{ method: "POST" }});')
    assert usages[0].method == "post"
    assert usages[0].path == "/users"
