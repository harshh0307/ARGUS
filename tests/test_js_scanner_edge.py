from app.scan.js_scanner import JsScanner

BASE = "https://api.github.com"


def _scan_source(scanner, source, filename, **kwargs):
    return scanner.scan_source(source, filename, **kwargs)


def scan(source):
    return _scan_source(JsScanner(BASE), source, "app.js")


def paths(source):
    return [u.path for u in scan(source)]


def test_axios_get_with_module_constant():
    source = f'const BASE = "{BASE}";\naxios.get(`${{BASE}}/users`);'
    assert paths(source) == ["/users"]


def test_fetch_template_variable_missing_constant_keeps_placeholder():
    source = 'fetch(`https://api.github.com/users/${unknown}`);'
    assert paths(source) == ["/users/{unknown}"]


def test_template_with_non_identifier_expression_kept():
    source = 'fetch(`https://api.github.com/users/${getId()}`);'
    assert paths(source) == ["/users/${getId()}"]


def test_block_comment_skipped():
    source = f'/* fetch("{BASE}/nope") */\nconst x = 1;'
    assert paths(source) == []


def test_line_comment_skipped():
    source = f'// fetch("{BASE}/nope")\nconst x = 1;'
    assert paths(source) == []


def test_string_with_escaped_quote():
    source = 'const s = "don\\\'t";'
    assert paths(source) == []


def test_axios_object_uppercase_method_lowered():
    source = f'axios({{ url: "{BASE}/orgs", method: "POST" }});'
    usages = scan(source)
    assert [(u.method, u.path) for u in usages] == [("post", "/orgs")]


def test_axios_object_without_method_defaults_get():
    source = f'axios({{ url: "{BASE}/orgs" }});'
    assert [(u.method, u.path) for u in scan(source)] == [("get", "/orgs")]


def test_fetch_relative_url():
    source = 'fetch("/users/1");'
    assert paths(source) == ["/users/1"]


def test_fetch_url_equal_to_base_skipped():
    source = f'fetch("{BASE}");'
    assert paths(source) == []


def test_unbalanced_paren_no_call_detected():
    source = f'fetch("{BASE}/x";'
    assert paths(source) == []


def test_fetch_from_identifier_constant():
    source = f'const U = "{BASE}/z";\nconst r = await fetch(U);'
    assert paths(source) == ["/z"]


def test_template_constant_with_variable_substitution():
    source = f'const H = "{BASE}";\nconst url = `${{H}}/repos/{{owner}}`;\nconst r = await fetch(url);'
    assert paths(source) == ["/repos/{owner}"]


def test_axios_method_with_unknown_method_skipped():
    source = 'axios.request("/x");'
    assert paths(source) == []


def test_axios_call_with_no_arguments_skipped():
    source = "axios.get();"
    assert paths(source) == []


def test_fetch_call_with_no_arguments_skipped():
    source = "fetch();"
    assert paths(source) == []


def test_nested_call_in_args_parsed_correctly():
    source = f'fetch("{BASE}/a", {{ signal: controller.signal }});'
    assert [(u.method, u.path) for u in scan(source)] == [("get", "/a")]


def test_fetch_with_options_without_method_defaults_get():
    source = f'fetch("{BASE}/a", {{ headers: {{ "X-K": "v" }} }});'
    assert [(u.method, u.path) for u in scan(source)] == [("get", "/a")]


def test_fetch_template_literal_with_escaped_backtick_content():
    source = "fetch(`https://api.github.com/raw/` + path);"
    assert paths(source) == []


def test_axios_url_from_options_object():
    source = f'axios.post("/local", data, {{ url: "{BASE}/remote" }});'
    usages = scan(source)
    assert [(u.method, u.path) for u in usages] == [("post", "/local")]


def test_sorted_by_line_then_method():
    source = f'fetch("{BASE}/z");\nfetch("{BASE}/a");'
    keys = [(u.line, u.method, u.path) for u in scan(source)]
    assert keys == [(1, "get", "/z"), (2, "get", "/a")]


def test_ts_and_jsx_suffixes_use_js_scanner(tmp_path):
    from app.scan.scanner import ApiScanner

    def _scan(scanner, root):
        return scanner.scan(root)

    (tmp_path / "a.tsx").write_text(f'fetch("{BASE}/tsx")', encoding="utf-8")
    (tmp_path / "b.mjs").write_text(f'fetch("{BASE}/mjs")', encoding="utf-8")
    usages, _headers = _scan(ApiScanner(BASE), tmp_path)
    assert sorted(u.path for u in usages) == ["/mjs", "/tsx"]


def test_template_variable_with_underscore_and_dollar():
    source = "fetch(`https://api.github.com/users/${_id}`);"
    assert paths(source) == ["/users/{_id}"]