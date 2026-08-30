
from app.scan.scanner import ApiScanner

BASE = "https://api.github.com"


def _scan(scanner, root):
    usages, _headers = scanner.scan(root)
    return usages


def write(tmp_path, name, content):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ─── requests.request(method, url) ──────────────────────────────────────────


def test_requests_request_literal_method(tmp_path):
    write(tmp_path, "a.py", 'requests.request("GET", f"{BASE}/users")\n'.replace("{BASE}", BASE))
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert (usages[0].method, usages[0].path) == ("get", "/users")


def test_requests_request_post(tmp_path):
    write(tmp_path, "a.py", f'requests.request("POST", "{BASE}/repos")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_requests_request_delete(tmp_path):
    write(tmp_path, "a.py", f'requests.request("DELETE", "{BASE}/users/1")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "delete"
    assert usages[0].path == "/users/1"


def test_requests_request_fstring_url(tmp_path):
    write(tmp_path, "a.py", f'BASE = "{BASE}"\nrequests.request("GET", f"{{BASE}}/items")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/items"


def test_requests_request_constant_method(tmp_path):
    write(tmp_path, "a.py", f'METHOD = "GET"\nrequests.request(METHOD, "{BASE}/users")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 0  # method from variable not resolved (only string literals)


def test_requests_request_invalid_method_ignored(tmp_path):
    write(tmp_path, "a.py", f'requests.request("INVALID", "{BASE}/users")\n')
    assert _scan(ApiScanner(BASE), tmp_path) == []


def test_httpx_request_literal_method(tmp_path):
    write(tmp_path, "a.py", f'httpx.request("PUT", "{BASE}/users/1")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "put"
    assert usages[0].path == "/users/1"


# ─── httpx.AsyncClient / Client patterns ────────────────────────────────────


def test_httpx_client_get(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client()\nclient.get("{BASE}/users")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert len(usages) == 1
    assert usages[0].method == "get"
    assert usages[0].path == "/users"


def test_httpx_async_client_post(tmp_path):
    write(tmp_path, "a.py", f'async with httpx.AsyncClient() as client:\n    await client.post("{BASE}/repos", json={{}})\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_httpx_client_fstring(tmp_path):
    write(tmp_path, "a.py", f'BASE = "{BASE}"\nclient = httpx.Client()\nclient.get(f"{{BASE}}/repos/{{owner}}")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/repos/{owner}"


def test_httpx_client_put(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client()\nclient.put("{BASE}/users/1")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "put"


def test_httpx_client_patch(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.AsyncClient()\nclient.patch("{BASE}/orgs/acme")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "patch"
    assert usages[0].path == "/orgs/acme"


def test_httpx_client_delete(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client()\nclient.delete("{BASE}/users/1")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "delete"


def test_httpx_client_head(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client()\nclient.head("{BASE}/health")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "head"


def test_httpx_client_options(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client()\nclient.options("{BASE}/users")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "options"


# ─── requests.Session / aiohttp.ClientSession ──────────────────────────────


def test_requests_session_get(tmp_path):
    write(tmp_path, "a.py", f'session = requests.Session()\nsession.get("{BASE}/users")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "get"
    assert usages[0].path == "/users"


def test_requests_session_post(tmp_path):
    write(tmp_path, "a.py", f'session = requests.Session()\nsession.post("{BASE}/repos")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "post"


def test_aiohttp_client_session_get(tmp_path):
    write(tmp_path, "a.py", f'async with aiohttp.ClientSession() as session:\n    async with session.get("{BASE}/users") as resp:\n        pass\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "get"
    assert usages[0].path == "/users"


def test_aiohttp_client_session_post(tmp_path):
    write(tmp_path, "a.py", f'async with aiohttp.ClientSession() as session:\n    async with session.post("{BASE}/repos", json={{"name": "test"}}) as resp:\n        pass\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "post"
    assert usages[0].path == "/repos"


def test_aiohttp_fstring_url(tmp_path):
    write(tmp_path, "a.py", f'BASE = "{BASE}"\nasync with aiohttp.ClientSession() as s:\n    async with s.get(f"{{BASE}}/items/{{id}}") as resp:\n        pass\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/items/{id}"


# ─── mixed patterns ────────────────────────────────────────────────────────


def test_multiple_clients_in_same_file(tmp_path):
    content = (
        f'import requests, httpx\n'
        f'requests.get("{BASE}/a")\n'
        f'client = httpx.Client()\n'
        f'client.post("{BASE}/b")\n'
        f'session = requests.Session()\n'
        f'session.put("{BASE}/c")\n'
    )
    write(tmp_path, "a.py", content)
    usages = _scan(ApiScanner(BASE), tmp_path)
    paths = [u.path for u in usages]
    assert paths == ["/a", "/b", "/c"]
    methods = [u.method for u in usages]
    assert methods == ["get", "post", "put"]


def test_requests_request_with_keyword_args(tmp_path):
    write(tmp_path, "a.py", f'requests.request("GET", "{BASE}/users", timeout=30)\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].method == "get"
    assert usages[0].path == "/users"


def test_httpx_client_with_timeout(tmp_path):
    write(tmp_path, "a.py", f'client = httpx.Client(timeout=30)\nclient.get("{BASE}/users")\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/users"


def test_aiohttp_with_verify_false(tmp_path):
    write(tmp_path, "a.py", f'async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as s:\n    async with s.get("{BASE}/secure") as resp:\n        pass\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/secure"


def test_chained_method_call(tmp_path):
    write(tmp_path, "a.py", f'client.get("{BASE}/users", headers={{"Authorization": "Bearer xxx"}})\n')
    usages = _scan(ApiScanner(BASE), tmp_path)
    assert usages[0].path == "/users"
