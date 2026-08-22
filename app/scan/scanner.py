from __future__ import annotations

import ast
from pathlib import Path

from app.scan.models import Usage

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")

CLIENT_CLASS_METHODS = {
    "client": frozenset(HTTP_METHODS),
    "AsyncClient": frozenset(HTTP_METHODS),
    "Session": frozenset(HTTP_METHODS),
}

CLIENT_OBJECT_PATTERNS = {
    "requests.Session",
    "httpx.Client",
    "httpx.AsyncClient",
    "aiohttp.ClientSession",
}

REQUEST_METHOD_CALLS = {
    "request",
}


def extract_path(url: str, base_url: str) -> str | None:
    """Turn a request URL into a spec path ('' base URL prefix removed)."""
    if url.startswith(base_url):
        path = url[len(base_url):]
    elif url.startswith("/"):
        path = url
    else:
        return None
    return path if path.startswith("/") else None


def language_for_file(path: str) -> str:
    return "js" if Path(path).suffix.lower() in JS_SUFFIXES else "py"


class ApiScanner:
    def __init__(self, base_url: str, ignore_dirs: set[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.ignore_dirs = ignore_dirs or {".git", ".venv", "__pycache__", "node_modules", ".tox"}

    def scan(self, root: str | Path) -> list[Usage]:
        usages: list[Usage] = []
        root_path = Path(root)
        for path in root_path.rglob("*"):
            if path.is_dir() or self._ignored(path):
                continue
            suffix = path.suffix.lower()
            if suffix != ".py" and suffix not in JS_SUFFIXES:
                continue
            rel = path.relative_to(root_path).as_posix()
            usages.extend(self._scan_file(path, rel))
        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def scan_source(self, source: str, filename: str = "<string>", language: str | None = None) -> list[Usage]:
        language = language or language_for_file(filename)
        if language == "js":
            from app.scan.js_scanner import JsScanner

            return JsScanner(base_url=self.base_url).scan_source(source, filename)
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            return []
        constants = self._module_constants(tree)
        visitor = _CallVisitor(filename, self.base_url, constants)
        visitor.visit(tree)
        return visitor.usages

    def scan_file(self, path: Path) -> list[Usage]:
        return self._scan_file(path, path)

    def _scan_file(self, path: Path, filename: Path) -> list[Usage]:
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return []
        return self.scan_source(source, str(filename))

    def _ignored(self, path: Path) -> bool:
        return any(part in self.ignore_dirs for part in path.parts)

    @staticmethod
    def _module_constants(tree: ast.Module) -> dict[str, str]:
        constants = {}
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
        return constants


class _CallVisitor(ast.NodeVisitor):
    def __init__(self, file: str, base_url: str, constants: dict[str, str]):
        self.file = file
        self.base_url = base_url
        self.constants = constants
        self.usages: list[Usage] = []

    def visit_Call(self, node: ast.Call) -> None:
        # requests.request("GET", url) - method in first arg, URL in second
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in REQUEST_METHOD_CALLS
            and len(node.args) >= 2
        ):
            method = self._evaluate_method(node.args[0])
            if method:
                url = self._evaluate_url(node.args[1])
                if url is not None:
                    path = extract_path(url, self.base_url)
                    if path is not None:
                        self.usages.append(Usage(self.file, node.lineno, method, path))

        # Direct method calls: get(), post(), requests.get(), client.get(), etc.
        method = self._method_of(node.func)
        if method and node.args:
            url = self._evaluate_url(node.args[0])
            if url is not None:
                path = extract_path(url, self.base_url)
                if path is not None:
                    self.usages.append(Usage(self.file, node.lineno, method, path))

        self.generic_visit(node)

    def _method_of(self, func) -> str | None:
        # requests.get(), httpx.get(), etc.
        if isinstance(func, ast.Name) and func.id in HTTP_METHODS:
            return func.id

        # requests.request("GET", url) - first arg is method
        if (
            isinstance(func, ast.Attribute)
            and func.attr in REQUEST_METHOD_CALLS
            and func.value
            and isinstance(func.value, ast.Name)
            and func.value.id in ("requests", "httpx")
        ):
            return "_request_"
        if isinstance(func, ast.Name) and func.id in REQUEST_METHOD_CALLS:
            return "_request_"

        # client.get(), client.post(), etc. - attribute access
        if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
            return func.attr

        return None

    def _evaluate_url(self, arg) -> str | None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.JoinedStr):
            parts = []
            for value in arg.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                    name = value.value.id
                    parts.append(self.constants.get(name, f"{{{name}}}"))
                else:
                    return None
            return "".join(parts)
        return None

    def _evaluate_method(self, node: ast.expr) -> str | None:
        """Evaluate a method argument to extract HTTP method string."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            method = node.value.lower()
            if method in HTTP_METHODS:
                return method
        return None
