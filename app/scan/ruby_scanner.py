from __future__ import annotations

import re

from app.scan.models import Usage
from app.scan.scanner import extract_path

RUBY_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# String patterns
_STRING_DOUBLE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
_STRING_SINGLE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")
_INTERPOLATION = re.compile(r"#\{(\w+)\}")
_IDENT = re.compile(r"[A-Za-z_]\w*")

# Constants: BASE_URL = "https://api.example.com"
# GEM_CONSTANT = "value"
_CONST = re.compile(
    r"""\b([A-Z_]\w*)\s*=\s*("(.*?)"|'(.*?)')""",
    re.DOTALL,
)

# Net::HTTP patterns
# Net::HTTP.get(URI("url"))
# Net::HTTP.post(URI("url"), data)
# Net::HTTP.start(host) { |http| http.get("/path") }
# Net::HTTP.post_form(URI("url"), data)
_NET_HTTP_GET = re.compile(r"""\bNet::HTTP\.(get|post|put|patch|delete|head|post_form|get_response)\s*\(""")
_NET_HTTP_NEW = re.compile(r"""\bNet::HTTP\.new\s*\(""")

# http = Net::HTTP.new(host); http.get("/path")
_HTTP_OBJ_CALL = re.compile(
    r"""\b(\w+)\.(get|post|put|patch|delete|head|request)\s*\(""",
)

# Faraday patterns
# conn = Faraday.new(url: "https://api.example.com")
# conn.get("/path")
# conn.post("/path", data)
_FARADAY_NEW = re.compile(r"""\bFaraday\.new\s*\(""")

# conn.get("/path") - can't distinguish from any object
# But Faraday objects typically use the variable name `conn` or `faraday`
# We'll match any .get/.post etc. on variables that look like Faraday
_FARADAY_CALL = re.compile(
    r"""\b(conn|faraday|client|connection)\.(get|post|put|patch|delete|head)\s*\(""",
    re.IGNORECASE,
)

# HTTParty
# HTTParty.get("url")
# response = HTTParty.post("url", data)
_HTTPARTY_CALL = re.compile(
    r"""\bHTTParty\.(get|post|put|patch|delete|head|options)\s*\(""",
)

# RestClient
# RestClient.get("url")
# RestClient.post("url", data)
# RestClient::Request.execute(method: :get, url: "url")
_RESTCLIENT_CALL = re.compile(
    r"""\bRestClient\.(get|post|put|patch|delete|head|options)\s*\(""",
)
_RESTCLIENT_REQUEST = re.compile(r"""\bRestClient::Request\.execute\s*\(""")

# Typhoeus
# Typhoeus.get("url")
# Typhoeus.post("url", body: data)
_TYPHOEUS_CALL = re.compile(
    r"""\bTyphoeus\.(get|post|put|patch|delete|head|options)\s*\(""",
)

# HTTP class: response = HTTP.get("url")
_HTTP_CALL = re.compile(
    r"""\bHTTP\.(get|post|put|patch|delete|head|options)\s*\(""",
)


class RubyScanner:
    """Lightweight Ruby scanner: finds Net::HTTP, Faraday, HTTParty,
    RestClient, Typhoeus, and HTTP gem call sites, resolves string
    constants and interpolation, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._extract_constants(source)
        usages: list[Usage] = []
        seen_lines: set[int] = set()

        # Net::HTTP.get/post/etc
        for match in _NET_HTTP_GET.finditer(source):
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

        # HTTParty.get/post
        for match in _HTTPARTY_CALL.finditer(source):
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

        # RestClient.get/post
        for match in _RESTCLIENT_CALL.finditer(source):
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

        # Typhoeus.get/post
        for match in _TYPHOEUS_CALL.finditer(source):
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

        # HTTP.get/post (http gem)
        for match in _HTTP_CALL.finditer(source):
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

        # Object calls: http.get("/path"), conn.post("/path")
        for match in _HTTP_OBJ_CALL.finditer(source):
            method = match.group(2).lower()
            if method not in RUBY_METHODS:
                continue
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
            if value:
                value = value.strip("\"'")
                constants[name] = value
        return constants

    def _extract_next_string(self, source: str, pos: int) -> str | None:
        """Extract the next string literal after pos."""
        while pos < len(source) and source[pos] in " \t\r\n(":
            pos += 1
        if pos >= len(source):
            return None
        ch = source[pos]
        if ch == '"':
            m = _STRING_DOUBLE.match(source, pos)
            if m:
                return m.group(1)
        elif ch == "'":
            m = _STRING_SINGLE.match(source, pos)
            if m:
                return m.group(1)
        # Handle URI("url") pattern
        if source[pos:pos+4] == "URI(":
            inner_pos = pos + 4
            while inner_pos < len(source) and source[inner_pos] in " \t\r\n":
                inner_pos += 1
            if inner_pos < len(source) and source[inner_pos] in ('"', "'"):
                ch2 = source[inner_pos]
                end = inner_pos + 1
                while end < len(source):
                    if source[end] == "\\":
                        end += 2
                        continue
                    if source[end] == ch2:
                        return source[inner_pos + 1 : end]
                    end += 1
        return None

    def _resolve_url(self, url: str, constants: dict[str, str]) -> str:
        """Resolve a URL that might contain #{constant} interpolation."""
        def _replace(m: re.Match) -> str:
            var = m.group(1)
            return constants.get(var, f"{{{var}}}")

        return _INTERPOLATION.sub(_replace, url)
