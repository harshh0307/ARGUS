from __future__ import annotations

import re

from app.scan.models import AuthUsage, BodyUsage, HeaderUsage, ResponseUsage, Usage
from app.scan.scanner import extract_path

CS_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# String patterns
_STRING_DOUBLE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_IDENT = re.compile(r"[A-Za-z_]\w*")

# String interpolation: $"{BaseUrl}/path" or $"{CONSTANT}/path"
# Also handles: {BaseUrl} inside $"..." strings
_STRING_INTERPOLATION = re.compile(r"\$\{(\w+)\}")

# Constants: private const string BaseUrl = "https://api.example.com";
# string baseUrl = "https://api.example.com";
_CONST = re.compile(
    r"""\b(?:private\s+)?(?:const|static\s+readonly)\s+string\s+(\w+)\s*=\s*"(.*?)"\s*;""",
    re.DOTALL,
)

# Variable: string baseUrl = "https://api.example.com";
_VAR_DECL = re.compile(
    r"""\bstring\s+(\w+)\s*=\s*"(.*?)"\s*;""",
)

# HttpClient
# var client = new HttpClient();
# var response = await client.GetAsync("url");
# var response = await client.PostAsync("url", content);
# var response = await client.SendAsync(request);
_HTTP_CLIENT = re.compile(
    r"""\b(\w+)\.(Get|Post|Put|Patch|Delete|Head|Options|GetAsync|PostAsync|PutAsync|PatchAsync|DeleteAsync|HeadAsync|OptionsAsync|SendAsync|Send)\s*\(""",
)

# HttpClient static methods: HttpClient.GetStringAsync("url")
_HTTP_STATIC = re.compile(
    r"""\bHttpClient\.(Get|Post|Put|Patch|Delete|GetAsync|PostAsync|PutAsync|PatchAsync|DeleteAsync|GetStringAsync|GetFromJsonAsync)\s*\(""",
)

# RestSharp
# var client = new RestClient("base_url");
# var request = new RestRequest("/path");
# var response = await client.GetAsync(request);
# client.PostJsonAsync("/path", data);
_RESTSHARP = re.compile(
    r"""\b(\w+)\.(Get|Post|Put|Patch|Delete|Head|Options|GetAsync|PostAsync|PutAsync|PatchAsync|DeleteAsync|GetJsonAsync|PostJsonAsync|PutJsonAsync|PutJsonAsync|ExecuteAsync|ExecutePostAsync)\s*\(""",
)

# RestSharp: new RestRequest("/path") with Method = Method.Get
_RESTSHARP_REQUEST = re.compile(
    r"""\bnew\s+RestRequest\s*\(\s*"(.*?)"\s*[,)]""",
)

# Flurl
# var url = "https://api.example.com".AppendPathSegment("/path");
# await url.GetAsync();
# await "https://api.example.com/path".GetAsync();
# await client.PostJsonAsync(data);
_FLURL_URL = re.compile(
    r"""\b(".*?")\.(AppendPathSegment|WithHeaders|WithBasicAuth)\s*\(""",
)

# Refit
# [Get("/path")]
# Task<Response> GetAsync();
# [Post("/path")]
# Task<Response> PostAsync([Body] data);
_REFIT = re.compile(
    r"""\[(Get|Post|Put|Patch|Delete|Head|Options)\s*\(\s*"(.*?)"\s*\)\]""",
)

# Minimal API: app.MapGet("/path", handler);
# app.MapPost("/path", handler);
_MINIMAL_API = re.compile(
    r"""\bapp\.Map(Get|Post|Put|Patch|Delete|Head|Options|)\s*\(\s*"(.*?)"\s*""",
)


class CSharpScanner:
    """Lightweight C# scanner: finds HttpClient, RestSharp, Flurl,
    Refit, and Minimal API call sites, resolves string constants
    and interpolation, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._extract_constants(source)
        usages: list[Usage] = []
        seen_lines: set[int] = set()

        # Minimal API route definitions
        for match in _MINIMAL_API.finditer(source):
            method = match.group(1).lower()
            if not method:
                method = "get"
            url = match.group(2)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))
                seen_lines.add(line)

        # Refit interface definitions
        for match in _REFIT.finditer(source):
            method = match.group(1).lower()
            url = match.group(2)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # RestSharp RestRequest
        for match in _RESTSHARP_REQUEST.finditer(source):
            url = match.group(1)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, "get", path))
                    seen_lines.add(line)

        # RestSharp client calls
        for match in _RESTSHARP.finditer(source):
            method = match.group(2).lower()
            method = self._normalize_method(method)
            url = self._extract_next_string(source, match.end())
            if url is not None:
                url = self._resolve_url(url, constants)
                path = extract_path(url, self.base_url)
                if path is not None:
                    line = source.count("\n", 0, match.start()) + 1
                    if line not in seen_lines:
                        usages.append(Usage(filename, line, method, path))
                        seen_lines.add(line)

        # HttpClient static methods
        for match in _HTTP_STATIC.finditer(source):
            method = match.group(1).lower()
            method = self._normalize_method(method)
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # HttpClient instance calls
        for match in _HTTP_CLIENT.finditer(source):
            method = match.group(2).lower()
            method = self._normalize_method(method)
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def _extract_constants(self, source: str) -> dict[str, str]:
        constants: dict[str, str] = {}
        for match in _CONST.finditer(source):
            name = match.group(1)
            value = match.group(2)
            constants[name] = value
        for match in _VAR_DECL.finditer(source):
            name = match.group(1)
            value = match.group(2)
            constants[name] = value
        return constants

    def _extract_next_string(self, source: str, pos: int) -> str | None:
        """Extract the next string literal after pos."""
        while pos < len(source) and source[pos] in " \t\r\n(":
            pos += 1
        if pos >= len(source):
            return None
        if source[pos] == '"':
            m = _STRING_DOUBLE.match(source, pos)
            if m:
                return m.group(1)
        return None

    def _resolve_url(self, url: str, constants: dict[str, str]) -> str:
        """Resolve a URL that might contain ${constant} interpolation."""
        if "+" in url:
            resolved = self._eval_concat(url, constants)
            if resolved is not None:
                return resolved
        def _replace(m: re.Match) -> str:
            var = m.group(1)
            return constants.get(var, f"{{{var}}}")

        return _STRING_INTERPOLATION.sub(_replace, url)

    def _eval_concat(self, expr: str, constants: dict[str, str]) -> str | None:
        """Resolve string concatenation like '$"{BaseUrl}/api" + "/users"' or '"/api" + path + "/users"'."""
        parts = [p.strip() for p in expr.split("+")]
        result = []
        for part in parts:
            if not part:
                continue
            m = _STRING_DOUBLE.match(part)
            if m:
                inner = m.group(1)
                inner = _STRING_INTERPOLATION.sub(
                    lambda im: constants.get(im.group(1), f"{{{im.group(1)}}}"),
                    inner,
                )
                result.append(inner)
                continue
            m = _IDENT.fullmatch(part)
            if m:
                val = constants.get(part)
                if val is None:
                    return None
                result.append(val)
                continue
            return None
        return "".join(result)

    @staticmethod
    def _normalize_method(name: str) -> str:
        """Normalize C# method names to standard HTTP methods."""
        mapping = {
            "get": "get",
            "getasync": "get",
            "post": "post",
            "postasync": "post",
            "put": "put",
            "putasync": "put",
            "patch": "patch",
            "patchasync": "patch",
            "delete": "delete",
            "deleteasync": "delete",
            "head": "head",
            "headasync": "head",
            "options": "options",
            "optionsasync": "options",
            "send": "get",  # SendAsync needs request object, default to get
            "sendasync": "get",
            "executeasync": "get",
            "executepostasync": "post",
            "getjsonasync": "get",
            "postjsonasync": "post",
            "putjsonasync": "put",
            "getstringasync": "get",
            "getfromjsonasync": "get",
            "getobjectasync": "get",
        }
        return mapping.get(name, "get")

    def scan_headers(self, source: str, filename: str = "<string>") -> list[HeaderUsage]:
        headers: list[HeaderUsage] = []
        lines = source.splitlines()
        auth_re = re.compile(
            r"""['"]?(Authorization|X-Api-Key|X-Auth-Token|Api-Key|X-Access-Token|"""
            r"""X-GitHub-Api-Version|Stripe-Version)['"]?\s*[:=]""",
            re.IGNORECASE,
        )
        header_add_re = re.compile(
            r"""\.Headers\.Add\s*\(\s*["'](\w[\w-]*)["']""",
        )
        default_header_re = re.compile(
            r"""DefaultRequestHeaders\.\w+\s*\(\s*["'](\w[\w-]*)["']""",
        )
        for i, line in enumerate(lines, 1):
            for m in auth_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
            for m in header_add_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
            for m in default_header_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
        return headers

    def scan_body(self, source: str, filename: str = "<string>") -> list[BodyUsage]:
        bodies: list[BodyUsage] = []
        lines = source.splitlines()
        json_re = re.compile(r"""\.PostAsJsonAsync\s*\(|\.PutAsJsonAsync\s*\(|\.BodyValue\s*\(\s*new\s+\w*\s*\{([^}]+)\}""", re.DOTALL)
        field_re = re.compile(r"""(\w+)\s*=\s*""")
        form_re = re.compile(r"""FormUrlEncodedContent\s*\(\s*(?:new\s+(?:Dictionary|List)\s*[<{]?\([^)>]*\)\s*\{?\s*)?([^\}]+)\}?""")
        for i, line in enumerate(lines, 1):
            for m in json_re.finditer(line):
                fields = tuple(sorted(set(field_re.findall(m.group(1)))))
                if fields:
                    bodies.append(BodyUsage(filename, i, "post", "/", fields, "application/json"))
            for m in form_re.finditer(line):
                fields = tuple(sorted(set(field_re.findall(m.group(1)))))
                if fields:
                    bodies.append(BodyUsage(filename, i, "post", "/", fields, "application/x-www-form-urlencoded"))
        return bodies

    def scan_auth(self, source: str, filename: str = "<string>") -> list[AuthUsage]:
        auths: list[AuthUsage] = []
        lines = source.splitlines()
        bearer_re = re.compile(r"""['"]Bearer\s+[\w.=-]+['"]""")
        auth_header_re = re.compile(r"""\.Headers\.Add\s*\(\s*["']Authorization["']""")
        api_key_re = re.compile(r"""['"](?:X-Api-Key|X-Auth-Token|Api-Key)['"]?\s*[=:]\s*['"]?(\w+)['"]?""")
        basic_re = re.compile(r"""Convert\.ToBase64String|FromBase64String""")
        oauth_re = re.compile(r"""['"]access_token['"]\s*[=:]\s*['"]?(\w+)['"]?""")
        for i, line in enumerate(lines, 1):
            if bearer_re.search(line) or auth_header_re.search(line):
                auths.append(AuthUsage(filename, i, "bearer", "Authorization", None, None))
            for m in api_key_re.finditer(line):
                auths.append(AuthUsage(filename, i, "api_key", m.group(0).split(":")[0].strip().strip("'\""), None, None))
            if basic_re.search(line):
                auths.append(AuthUsage(filename, i, "basic", "Authorization", None, None))
            if oauth_re.search(line):
                auths.append(AuthUsage(filename, i, "oauth2", None, None, None))
        return auths

    def scan_response(self, source: str, filename: str = "<string>") -> list[ResponseUsage]:
        responses: list[ResponseUsage] = []
        lines = source.splitlines()
        status_re = re.compile(r"""(?:\.StatusCode|\.IsSuccessStatusCode)\s*(?:==|!=)\s*(\d{3})""")
        field_re = re.compile(r"""(?:response|resp|res)\.(\w+)""")
        for i, line in enumerate(lines, 1):
            status_codes = tuple(m.group(1) for m in status_re.finditer(line))
            fields = tuple(m.group(1) for m in field_re.finditer(line))
            if status_codes or fields:
                responses.append(ResponseUsage(filename, i, "get", "/", status_codes, fields))
        return responses
