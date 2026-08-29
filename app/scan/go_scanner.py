from __future__ import annotations

import re

from app.scan.models import Usage
from app.scan.scanner import extract_path

GO_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Patterns for Go HTTP client calls
# net/http: http.Get(url), http.Post(url, ...), http.NewRequest("GET", url, ...)
# go-resty: client.R().Get(url), client.R().Post(url, ...)
# echo/gin: c.Get("GET", path, handler)

_STRING_SINGLE = re.compile(r"'(.*?)'")
_STRING_DOUBLE = re.compile(r'"(.*?)"')
_BACKTICK = re.compile(r"`(.*?)`")
_TEMPLATE_VAR = re.compile(r"\$\{(\w+)\}")
_IDENT = re.compile(r"[A-Za-z_]\w*")

# Constant declarations: const BaseURL = "https://api.example.com"
_CONST_DECL = re.compile(
    r"""\bconst\s+(\w+)\s*=\s*("(.*?)"|'(.*?)'|`(.*?)`)""",
    re.DOTALL,
)

# Variable declarations: var BaseURL = "https://api.example.com"
_VAR_DECL = re.compile(
    r"""\bvar\s+(\w+)\s*=\s*("(.*?)"|'(.*?)'|`(.*?)`)""",
    re.DOTALL,
)

# Short variable: baseURL := "https://api.example.com"
_SHORT_VAR = re.compile(
    r"""\b(\w+)\s*:=\s*("(.*?)"|'(.*?)'|`(.*?)`)""",
    re.DOTALL,
)

# http.Get("url")
_HTTP_METHOD_CALL = re.compile(
    r"""\bhttp\.(Get|Post|Put|Patch|Delete|Head|Options)\s*\(""",
)

# http.NewRequest("METHOD", "url", body)
_HTTP_NEW_REQUEST = re.compile(r"""\bhttp\.NewRequest\s*\(""")

# client.Do(req) - can't resolve URL from this pattern easily
# client.R().Get("url") - go-resty
_RESTY_CALL = re.compile(
    r"""\.R\(\)\.(Get|Post|Put|Patch|Delete|Head|Options)\s*\(""",
)

# echo.GET("path", handler) / gin.GET("path", handler)
# Also matches e.GET, r.GET, router.GET, etc.
_FRAMEWORK_ROUTE = re.compile(
    r"""\b(\w+)\.(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|Any|Handle|Add)\s*\(""",
)

# c.Request().URL.Path - won't resolve, skip


class GoScanner:
    """Lightweight Go scanner: finds net/http, go-resty, and framework
    call sites, resolves string constants, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._extract_constants(source)
        usages: list[Usage] = []
        for match in _HTTP_METHOD_CALL.finditer(source):
            method = match.group(1).lower()
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_value(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))

        for match in _HTTP_NEW_REQUEST.finditer(source):
            args_start = match.start()
            parts = self._extract_func_args(source, args_start)
            if len(parts) < 2:
                continue
            method = self._eval_string(parts[0], constants)
            url = self._eval_string(parts[1], constants)
            if method is None or url is None:
                continue
            method = method.lower()
            if method not in GO_METHODS:
                continue
            url = self._resolve_value(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))

        for match in _RESTY_CALL.finditer(source):
            method = match.group(1).lower()
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_value(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))

        for match in _FRAMEWORK_ROUTE.finditer(source):
            method = match.group(2).lower()
            if method == "any":
                method = "get"
            url = self._extract_next_string(source, match.end())
            if url is None:
                continue
            url = self._resolve_value(url, constants)
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, match.start()) + 1
                usages.append(Usage(filename, line, method, path))

        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def _extract_constants(self, source: str) -> dict[str, str]:
        constants: dict[str, str] = {}
        for pattern in (_CONST_DECL, _VAR_DECL, _SHORT_VAR):
            for match in pattern.finditer(source):
                name = match.group(1)
                value = match.group(2)
                if value:
                    # Unquote
                    value = value.strip("\"'`")
                    constants[name] = value
        return constants

    def _extract_next_string(self, source: str, pos: int) -> str | None:
        """Extract the next string literal after pos."""
        # Skip whitespace and opening paren
        while pos < len(source) and source[pos] in " \t\r\n(":
            pos += 1
        if pos >= len(source):
            return None
        ch = source[pos]
        if ch in ('"', "'", "`"):
            return self._extract_string(source, pos)
        # Could be a variable name
        m = _IDENT.match(source, pos)
        if m:
            return f"${{{m.group(0)}}}"  # sentinel for variable
        return None

    def _extract_string(self, source: str, pos: int) -> str | None:
        """Extract a quoted string at pos."""
        if pos >= len(source):
            return None
        quote = source[pos]
        if quote not in ('"', "'", "`"):
            return None
        end = pos + 1
        while end < len(source):
            if source[end] == "\\":
                end += 2
                continue
            if source[end] == quote:
                return source[pos + 1 : end]
            end += 1
        return None

    def _extract_func_args(self, source: str, pos: int) -> list[str]:
        """Extract comma-separated arguments from a function call at pos."""
        # Find opening paren
        while pos < len(source) and source[pos] != "(":
            if source[pos] in ('"', "'", "/"):
                break
            pos += 1
        if pos >= len(source) or source[pos] != "(":
            return []
        depth = 1
        start = pos + 1
        args: list[str] = []
        current: list[str] = []
        i = start
        while i < len(source) and depth > 0:
            ch = source[i]
            if ch in ('"', "'", "`"):
                j = i + 1
                while j < len(source):
                    if source[j] == "\\":
                        j += 2
                        continue
                    if source[j] == ch:
                        current.append(source[i : j + 1])
                        i = j + 1
                        break
                    j += 1
                else:
                    current.append(source[i:])
                    i = len(source)
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    args.append("".join(current).strip())
                    return args
            elif ch == "," and depth == 1:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
            i += 1
        if current:
            args.append("".join(current).strip())
        return args

    def _eval_string(self, raw: str, constants: dict[str, str]) -> str | None:
        """Evaluate a raw string literal, resolving constants."""
        raw = raw.strip()
        # Check for string literal
        if raw and raw[0] in ('"', "'", "`"):
            return raw[1:-1] if len(raw) > 1 else None
        # Check for variable reference
        if raw in constants:
            return constants[raw]
        # Check for template variable
        m = _TEMPLATE_VAR.match(raw)
        if m and m.group(1) in constants:
            return constants[m.group(1)]
        return None

    def _resolve_value(self, url: str, constants: dict[str, str]) -> str:
        """Resolve a URL that might contain ${var} placeholders."""
        def _replace(m: re.Match) -> str:
            var = m.group(1)
            return constants.get(var, f"{{{var}}}")

        return _TEMPLATE_VAR.sub(_replace, url)
