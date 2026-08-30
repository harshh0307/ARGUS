from __future__ import annotations

import re

from app.scan.models import HeaderUsage, Usage
from app.scan.scanner import extract_path

JAVA_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# String patterns
_STRING_DOUBLE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_IDENT = re.compile(r"[A-Za-z_]\w*")

# String constants: private static final String BASE_URL = "https://api.example.com";
# String baseUrl = "https://api.example.com";
_CONST = re.compile(
    r"""\b(?:private\s+)?(?:static\s+)?(?:final\s+)?String\s+(\w+)\s*=\s*"(.*?)"\s*;""",
    re.DOTALL,
)

# HttpClient (Java 11+)
# HttpClient client = HttpClient.newHttpClient();
# client.send(request, bodyHandler);
# HttpResponse<String> response = client.send(request, BodyHandlers.ofString());
_HTTP_CLIENT_SEND = re.compile(r"""\b(\w+)\.send\s*\(""")

# HttpRequest.newBuilder().uri(URI.create("url")).GET().build()
_HTTP_REQUEST = re.compile(r"""\bHttpRequest\.newBuilder\s*\(""")

# RestTemplate
# restTemplate.getForObject("url", String.class);
# restTemplate.postForEntity("url", data, String.class);
# restTemplate.exchange("url", HttpMethod.GET, entity, String.class);
_REST_TEMPLATE = re.compile(
    r"""\b(\w+)\.(getForObject|getForEntity|postForObject|postForEntity|exchange|execute|delete|put)\s*\(""",
)

# WebClient (Spring WebFlux)
# webClient.get().uri("url").retrieve().bodyToMono(...).block();
# webClient.post().uri("url").bodyValue(data).retrieve().bodyToMono(...).block();
_WEB_CLIENT = re.compile(
    r"""\b(\w+)\.(get|post|put|patch|delete|head)\s*\(\s*\)\s*\.uri\s*\(""",
)

# OkHttp
# Request request = new Request.Builder().url("url").get().build();
# client.newCall(request).execute();
# response = client.newCall(new Request.Builder().url("url").build()).execute();
_OK_HTTP_URL = re.compile(r"""\.url\s*\(\s*"(.*?)"\s*\)""")

# HttpGet/HttpPost (Apache HttpClient)
#HttpGet httpGet = new HttpGet("url");
#HttpPost httpPost = new HttpPost("url");
_APACHE_HTTP = re.compile(
    r"""\bnew\s+(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete|HttpHead|HttpOptions)\s*\(\s*"(.*?)"\s*\)""",
)

# Feign
# @FeignClient(name = "service", url = "${base.url}")
# interface ServiceClient { @GetMapping("/path") Response get(); }
# client.get("/path", params);
_FEIGN_CALL = re.compile(
    r"""\b(\w+)\.(get|post|put|patch|delete)\s*\(\s*"(.*?)"\s*[,)]""",
)

# Unirest
# Unirest.get("url");
# Unirest.post("url");
_UNIREST_CALL = re.compile(
    r"""\bUnirest\.(get|post|put|patch|delete|head|options)\s*\(""",
)


class JavaScanner:
    """Lightweight Java scanner: finds HttpClient, RestTemplate, WebClient,
    OkHttp, Apache HttpClient, Feign, and Unirest call sites, resolves
    string constants, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._extract_constants(source)
        usages: list[Usage] = []
        seen_lines: set[int] = set()

        # RestTemplate.getForObject/postForEntity/etc
        for match in _REST_TEMPLATE.finditer(source):
            method = self._rest_template_method(match.group(2))
            if method is None:
                continue
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))
                seen_lines.add(line)

        # Unirest.get/post
        for match in _UNIREST_CALL.finditer(source):
            method = match.group(1).lower()
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

        # Feign client calls
        for match in _FEIGN_CALL.finditer(source):
            method = match.group(2).lower()
            url = match.group(3)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # Apache HttpClient: new HttpGet("url")
        for match in _APACHE_HTTP.finditer(source):
            method = self._apache_method(match.group(1))
            url = match.group(2)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # WebClient: webClient.get().uri("url")
        for match in _WEB_CLIENT.finditer(source):
            method = match.group(2).lower()
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

        # HttpClient.send(request, bodyHandler)
        for match in _HTTP_CLIENT_SEND.finditer(source):
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, "get", path))
                    seen_lines.add(line)

        # HttpRequest.newBuilder().uri(URI.create("url"))
        for match in _HTTP_REQUEST.finditer(source):
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, "get", path))
                    seen_lines.add(line)

        # OkHttp .url("path")
        for match in _OK_HTTP_URL.finditer(source):
            url = match.group(1)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, "get", path))
                    seen_lines.add(line)

        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def _extract_constants(self, source: str) -> dict[str, str]:
        constants: dict[str, str] = {}
        for match in _CONST.finditer(source):
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
        """Resolve a URL that might contain ${var} placeholders."""
        if "+" in url:
            resolved = self._eval_concat(url, constants)
            if resolved is not None:
                return resolved
        def _replace(m: re.Match) -> str:
            var = m.group(1)
            return constants.get(var, f"{{{var}}}")

        return re.sub(r"\$\{(\w+)\}", _replace, url)

    def _eval_concat(self, expr: str, constants: dict[str, str]) -> str | None:
        """Resolve string concatenation like '"/api" + basePath + "/users"'."""
        parts = [p.strip() for p in expr.split("+")]
        result = []
        for part in parts:
            if not part:
                continue
            m = _STRING_DOUBLE.match(part)
            if m:
                result.append(m.group(1))
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
    def _rest_template_method(name: str) -> str | None:
        mapping = {
            "getForObject": "get",
            "getForEntity": "get",
            "postForObject": "post",
            "postForEntity": "post",
            "exchange": None,  # depends on HttpMethod arg, skip
            "execute": None,
            "delete": "delete",
            "put": "put",
        }
        return mapping.get(name)

    @staticmethod
    def _apache_method(class_name: str) -> str:
        mapping = {
            "HttpGet": "get",
            "HttpPost": "post",
            "HttpPut": "put",
            "HttpPatch": "patch",
            "HttpDelete": "delete",
            "HttpHead": "head",
            "HttpOptions": "options",
        }
        return mapping.get(class_name, "get")

    def scan_headers(self, source: str, filename: str = "<string>") -> list[HeaderUsage]:
        headers: list[HeaderUsage] = []
        lines = source.splitlines()
        auth_re = re.compile(
            r"""['"]?(Authorization|X-Api-Key|X-Auth-Token|Api-Key|X-Access-Token|"""
            r"""X-GitHub-Api-Version|Stripe-Version)['"]?\s*[:=]""",
            re.IGNORECASE,
        )
        header_set_re = re.compile(
            r"""\.header\s*\(\s*["'](\w[\w-]*)["']""",
        )
        add_header_re = re.compile(
            r"""\.addHeader\s*\(\s*["'](\w[\w-]*)["']""",
        )
        for i, line in enumerate(lines, 1):
            for m in auth_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
            for m in header_set_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
            for m in add_header_re.finditer(line):
                headers.append(HeaderUsage(filename, i, m.group(1), None, "header"))
        return headers
