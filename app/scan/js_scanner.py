from __future__ import annotations

import re

from app.scan.models import Usage
from app.scan.scanner import extract_path

JS_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Libs that follow got.<method>() / superagent.<method>() / ky.<method>() pattern
HTTP_CLIENT_LIBS = ("got", "superagent", "ky")
_STRING = re.compile(r"""(['"])(.*?)\1""", re.DOTALL)
_TEMPLATE = re.compile(r"""`([^`]*)`""", re.DOTALL)
_TEMPLATE_VAR = re.compile(r"\$\{([A-Za-z_$][\w$]*)\}")
_CONST = re.compile(
    r"""\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(['"`])(.*?)\2\s*;?\s*$""", re.MULTILINE
)
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


class JsScanner:
    """Lightweight JavaScript/TypeScript scanner: finds fetch() and
    axios.<method>() call sites, resolves string/template literals and
    module-level constants, and extracts the API path."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        constants = self._module_constants(source)
        usages: list[Usage] = []
        for start, end, call in _iter_calls(source):
            method, url = self._parse_call(call, constants)
            if method is None or url is None:
                continue
            path = extract_path(url, self.base_url)
            if path is not None:
                line = source.count("\n", 0, start) + 1
                usages.append(Usage(filename, line, method, path))
        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    @staticmethod
    def _module_constants(source: str) -> dict[str, str]:
        constants: dict[str, str] = {}
        for match in _CONST.finditer(source):
            value = match.group(3)
            if match.group(2) == "`":
                value = _TEMPLATE_VAR.sub(
                    lambda m: constants.get(m.group(1), f"{{{m.group(1)}}}"),
                    value,
                )
            constants[match.group(1)] = value
        return constants

    def _parse_call(self, call: str, constants: dict[str, str]) -> tuple[str | None, str | None]:
        name, _, args = call.partition("(")
        name = name.strip()
        args = args[: args.rfind(")")] if args.endswith(")") else args
        parts = _split_top_level(args)

        if name == "fetch":
            if not parts:
                return None, None
            method = self._options_method(parts[1]) if len(parts) > 1 else "get"
            return method or "get", self._eval_url(parts[0], constants)

        if name == "axios":
            method = "get"
            url_arg = parts[0] if parts else None
            options = parts[1] if len(parts) > 1 else None
            if url_arg and url_arg.strip().startswith("{"):
                options = url_arg
                url_arg = None
            if options is not None:
                method = self._options_method(options) or "get"
                options_url = self._options_url(options)
                if options_url is not None:
                    return method, options_url
            return method, self._eval_url(url_arg or "", constants)

        if name.startswith("axios."):
            method = name.split(".", 1)[1].lower()
            if method not in JS_METHODS or not parts:
                return None, None
            return method, self._eval_url(parts[0], constants)

        # got.get(), ky.get(), superagent.get() - same pattern
        if name.startswith(("got.", "ky.", "superagent.")):
            lib_method = name.split(".", 1)[1].lower()
            if lib_method not in JS_METHODS or not parts:
                return None, None
            return lib_method, self._eval_url(parts[0], constants)

        # superagent("GET", url) - request-style call
        if name == "superagent" and len(parts) >= 2:
            method = self._eval_url(parts[0], constants)
            if method:
                method = method.lower()
            if method and method in JS_METHODS:
                return method, self._eval_url(parts[1], constants)

        # got(url) or got(url, options) - defaults to GET
        if name in ("got", "ky"):
            if not parts:
                return None, None
            method = self._options_method(parts[1]) if len(parts) > 1 else "get"
            return method or "get", self._eval_url(parts[0], constants)

        return None, None

    def _eval_url(self, raw: str, constants: dict[str, str]) -> str | None:
        value = raw.strip()
        string_match = _STRING.match(value)
        if string_match:
            return string_match.group(2)
        template_match = _TEMPLATE.match(value)
        if template_match:
            return _TEMPLATE_VAR.sub(
                lambda m: constants.get(m.group(1), f"{{{m.group(1)}}}"),
                template_match.group(1),
            )
        ident_match = _IDENT.fullmatch(value)
        if ident_match:
            return constants.get(ident_match.group(0))
        return None

    def _options_method(self, options: str | None) -> str | None:
        if not options:
            return None
        match = re.search(
            r"""['"]?method['"]?\s*:\s*['"]([a-zA-Z]+)['"]""", options
        )
        return match.group(1).lower() if match else None

    def _options_url(self, options: str | None) -> str | None:
        if not options:
            return None
        match = re.search(
            r"""['"]?url['"]?\s*:\s*(['"`])(.*?)\1""", options, re.DOTALL
        )
        return match.group(2) if match else None


def _iter_calls(source: str):
    """Yield (start, end, raw_call) for fetch(...) and axios[...] call sites.

    Walks the source with a brace/paren/string-aware cursor so nested and
    multi-line calls are captured correctly."""
    i = 0
    length = len(source)
    while i < length:
        ch = source[i]
        if ch in ("'", '"', "`"):
            i = _skip_string(source, i)
            continue
        if ch == "/" and i + 1 < length and source[i + 1] == "/":
            newline = source.find("\n", i)
            i = length if newline == -1 else newline + 1
            continue
        if ch == "/" and i + 1 < length and source[i + 1] == "*":
            end = source.find("*/", i + 2)
            i = length if end == -1 else end + 2
            continue
        match = _IDENT.match(source, i)
        ident = match.group(0) if match else ""
        if ident in ("fetch", "axios", *HTTP_CLIENT_LIBS):
            j = _skip_ws(source, match.end())
            if j < length and source[j] == "(":
                end = _match_balanced(source, j, "(", ")")
                if end != -1:
                    yield i, end + 1, source[i : end + 1]
                    i = end + 1
                    continue
            # axios.get() / got.get() / superagent.get() / ky.get()
            if (
                ident in ("axios", *HTTP_CLIENT_LIBS)
                and j < length
                and source[j] == "."
            ):
                prop = _IDENT.match(source, j + 1)
                if prop and prop.group(0) in JS_METHODS:
                    k = _skip_ws(source, prop.end())
                    if k < length and source[k] == "(":
                        end = _match_balanced(source, k, "(", ")")
                        if end != -1:
                            yield i, end + 1, source[i : end + 1]
                            i = end + 1
                            continue
            # superagent("GET", url) - request-style call
            if (
                ident == "superagent"
                and j < length
                and source[j] == "("
            ):
                end = _match_balanced(source, j, "(", ")")
                if end != -1:
                    yield i, end + 1, source[i : end + 1]
                    i = end + 1
                    continue
        i += 1


def _skip_string(source: str, i: int) -> int:
    quote = source[i]
    i += 1
    length = len(source)
    while i < length:
        if source[i] == "\\":
            i += 2
            continue
        if source[i] == quote:
            return i + 1
        if quote == "`" and source[i] == "$" and i + 1 < length and source[i + 1] == "{":
            i = _match_balanced(source, i + 1, "{", "}") + 1
            continue
        i += 1
    return length


def _match_balanced(source: str, open_idx: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    i = open_idx
    length = len(source)
    while i < length:
        ch = source[i]
        if ch in ("'", '"', "`"):
            i = _skip_string(source, i)
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _skip_ws(source: str, i: int) -> int:
    while i < len(source) and source[i] in " \t\r\n":
        i += 1
    return i


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch in ("'", '"', "`"):
            j = _skip_string(text, i)
            current.append(text[i:j])
            i = j
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    if current:
        parts.append("".join(current).strip())
    return parts