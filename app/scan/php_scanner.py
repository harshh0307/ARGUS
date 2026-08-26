from __future__ import annotations

import re

from app.scan.models import Usage
from app.scan.scanner import extract_path

PHP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# String patterns
_STRING_DOUBLE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_STRING_SINGLE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")
_VARIABLE = re.compile(r"\$(\w+)")
_IDENT = re.compile(r"[A-Za-z_]\w*")

# Constants: define('BASE_URL', 'https://api.example.com');
# const BASE_URL = 'https://api.example.com';
_CONST = re.compile(
    r"""\b(?:define\s*\(\s*['"](\w+)['"]\s*,\s*['"](.+?)['"]\s*\)|const\s+(\w+)\s*=\s*['"](.+?)['"])""",
    re.DOTALL,
)

# Variable: $baseUrl = 'https://api.example.com';
_VAR_DECL = re.compile(
    r"""\$(\w+)\s*=\s*['"](.+?)['"]\s*;""",
)

# GuzzleHttp\Client
# $client = new \GuzzleHttp\Client(['base_uri' => 'https://api.example.com']);
# $response = $client->get('/path');
# $response = $client->post('/path', ['json' => $data]);
_GUZZLE_CALL = re.compile(
    r"""\$(\w+)->(get|post|put|patch|delete|head|options|request)\s*\(""",
)

# GuzzleHttp::request('GET', '/path')
# GuzzleHttp::get('/path')
_GUZZLE_STATIC = re.compile(
    r"""\bGuzzleHttp::(get|post|put|patch|delete|head|options|request)\s*\(""",
)

# GuzzleHttp\Psr7\request('GET', '/path')
_GUZZLE_PSR7 = re.compile(
    r"""\brequest\s*\(\s*['"](\w+)['"]\s*,\s*['"](.+?)['"]\s*\)""",
)

# Symfony HttpClient
# $client = new \Symfony\Component\HttpClient\HttpClient();
# $response = $client->request('GET', '/path');
# $response = $client->get('/path');
# $response = $client->post('/path', ['json' => $data]);
_SYMFONY_CLIENT = re.compile(
    r"""\$(\w+)->(request|get|post|put|patch|delete|head)\s*\(""",
)

# file_get_contents('https://api.example.com/path')
_FILE_GET = re.compile(r"""\bfile_get_contents\s*\(\s*['"](.+?)['"]\s*[,)]""")

# curl_exec($ch); - can't resolve URL from this pattern
# But we can detect: curl_setopt($ch, CURLOPT_URL, 'https://api.example.com/path');
_CURL_SETOPT = re.compile(
    r"""\bcurl_setopt\s*\(\s*\$\w+\s*,\s*CURLOPT_URL\s*,\s*['"](.+?)['"]\s*\)""",
)

# WordPress: wp_remote_get('url'), wp_remote_post('url')
_WP_REMOTE = re.compile(
    r"""\bwp_remote_(get|post|put|patch|delete|head)\s*\(\s*['"](.+?)['"]""",
)

# Laravel Http facade: Http::get('/path'), Http::post('/path')
_LARAVEL_HTTP = re.compile(
    r"""\bHttp::(get|post|put|patch|delete|head|options)\s*\(""",
)

# Artisan API: Route::get('/path', controller)
_ROUTE_DEF = re.compile(
    r"""\bRoute::(get|post|put|patch|delete|head|options|any|match)\s*\(\s*['"](.+?)['"]""",
)


class PhpScanner:
    """Lightweight PHP scanner: finds Guzzle, Symfony HttpClient, cURL,
    file_get_contents, WordPress HTTP, Laravel Http facade, and route
    definitions, resolves string constants, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._extract_constants(source)
        usages: list[Usage] = []
        seen_lines: set[int] = set()

        # Laravel Http facade
        for match in _LARAVEL_HTTP.finditer(source):
            method = match.group(1).lower()
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))
                seen_lines.add(line)

        # Laravel Route definitions
        for match in _ROUTE_DEF.finditer(source):
            method = match.group(1).lower()
            url = match.group(2)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # Guzzle static calls
        for match in _GUZZLE_STATIC.finditer(source):
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

        # Guzzle object calls
        for match in _GUZZLE_CALL.finditer(source):
            method = match.group(2).lower()
            if method == "request":
                # request('GET', '/path') - extract method from first arg
                method = self._extract_next_string(source, match.end())
                if method is None:
                    continue
                method = method.lower()
                # Now extract URL from second arg
                after_method = source.find(",", match.end())
                if after_method != -1:
                    url = self._extract_next_string(source, after_method + 1)
                else:
                    url = None
            else:
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

        # Symfony HttpClient
        for match in _SYMFONY_CLIENT.finditer(source):
            method = match.group(2).lower()
            if method == "request":
                # request('GET', '/path')
                method = self._extract_next_string(source, match.end())
                if method is None:
                    continue
                method = method.lower()
                after_method = source.find(",", match.end())
                if after_method != -1:
                    url = self._extract_next_string(source, after_method + 1)
                else:
                    url = None
            else:
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

        # WordPress wp_remote_get/post
        for match in _WP_REMOTE.finditer(source):
            method = match.group(1).lower()
            url = match.group(2)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, method, path))
                    seen_lines.add(line)

        # file_get_contents
        for match in _FILE_GET.finditer(source):
            url = match.group(1)
            url = self._resolve_url(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                if line not in seen_lines:
                    usages.append(Usage(filename, line, "get", path))
                    seen_lines.add(line)

        # cURL CURLOPT_URL
        for match in _CURL_SETOPT.finditer(source):
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
            name = match.group(1) or match.group(3)
            value = match.group(2) or match.group(4)
            if name and value:
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
        elif source[pos] == "'":
            m = _STRING_SINGLE.match(source, pos)
            if m:
                return m.group(1)
        return None

    def _resolve_url(self, url: str, constants: dict[str, str]) -> str:
        """Resolve a URL that might contain {$var} or constant references."""
        def _replace_var(m: re.Match) -> str:
            var = m.group(1)
            return constants.get(var, f"{{{var}}}")

        url = re.sub(r"\{?\$(\w+)\}?", _replace_var, url)
        return url
