from __future__ import annotations

import ast
from pathlib import Path

from app.scan.models import Usage

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

JS_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
GO_SUFFIXES = (".go",)
RUBY_SUFFIXES = (".rb",)
JAVA_SUFFIXES = (".java",)
PHP_SUFFIXES = (".php",)
CS_SUFFIXES = (".cs",)

ALL_SUFFIXES: dict[str, tuple[str, ...]] = {
    "py": (".py",),
    "js": JS_SUFFIXES,
    "go": GO_SUFFIXES,
    "ruby": RUBY_SUFFIXES,
    "java": JAVA_SUFFIXES,
    "php": PHP_SUFFIXES,
    "cs": CS_SUFFIXES,
}

ALL_EXTENSIONS: dict[str, str] = {}
for _lang, _suffixes in ALL_SUFFIXES.items():
    for _ext in _suffixes:
        ALL_EXTENSIONS[_ext] = _lang

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
    # Strip query strings and fragments
    for sep in ("?", "#"):
        idx = path.find(sep)
        if idx != -1:
            path = path[:idx]
    return path if path.startswith("/") else None


def language_for_file(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return ALL_EXTENSIONS.get(suffix, "py")


class ApiScanner:
    def __init__(
        self,
        base_url: str,
        ignore_dirs: set[str] | None = None,
        languages: set[str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.ignore_dirs = ignore_dirs or {".git", ".venv", "__pycache__", "node_modules", ".tox"}
        # None means scan all languages
        self.languages: set[str] | None = languages

    def _should_scan(self, suffix: str) -> bool:
        lang = ALL_EXTENSIONS.get(suffix)
        if lang is None:
            return False
        if self.languages is None:
            return True
        return lang in self.languages

    def scan(self, root: str | Path) -> list[Usage]:
        usages: list[Usage] = []
        root_path = Path(root)
        for path in root_path.rglob("*"):
            if path.is_dir() or self._ignored(path):
                continue
            suffix = path.suffix.lower()
            if not self._should_scan(suffix):
                continue
            rel = path.relative_to(root_path).as_posix()
            usages.extend(self._scan_file(path, rel))
        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def scan_source(self, source: str, filename: str = "<string>", language: str | None = None) -> list[Usage]:
        language = language or language_for_file(filename)
        if language == "js":
            from app.scan.js_scanner import JsScanner

            return JsScanner(base_url=self.base_url).scan_source(source, filename)
        if language == "go":
            from app.scan.go_scanner import GoScanner

            return GoScanner(base_url=self.base_url).scan_source(source, filename)
        if language == "ruby":
            from app.scan.ruby_scanner import RubyScanner

            return RubyScanner(base_url=self.base_url).scan_source(source, filename)
        if language == "java":
            from app.scan.java_scanner import JavaScanner

            return JavaScanner(base_url=self.base_url).scan_source(source, filename)
        if language == "php":
            from app.scan.php_scanner import PhpScanner

            return PhpScanner(base_url=self.base_url).scan_source(source, filename)
        if language == "cs":
            from app.scan.cs_scanner import CSharpScanner

            return CSharpScanner(base_url=self.base_url).scan_source(source, filename)
        # Python (default)
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
        self._variables: dict[str, str] = {}

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        old_vars = dict(self._variables)
        self._collect_local_assigns(node)
        self.generic_visit(node)
        self._variables = old_vars

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        old_vars = dict(self._variables)
        self._collect_local_assigns(node)
        self.generic_visit(node)
        self._variables = old_vars

    def _collect_local_assigns(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        for node in ast.walk(func_node):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
            ):
                self._variables[node.targets[0].id] = node.value.value

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

    def _resolve_name(self, name: str) -> str | None:
        if name in self._variables:
            return self._variables[name]
        if name in self.constants:
            return self.constants[name]
        return None

    def _evaluate_url(self, arg) -> str | None:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
        if isinstance(arg, ast.Name):
            resolved = self._resolve_name(arg.id)
            if resolved is not None:
                return resolved
            return None
        if isinstance(arg, ast.JoinedStr):
            parts = []
            for value in arg.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
                elif isinstance(value, ast.FormattedValue) and isinstance(value.value, ast.Name):
                    name = value.value.id
                    resolved = self._resolve_name(name)
                    parts.append(resolved if resolved is not None else f"{{{name}}}")
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
