from __future__ import annotations

import ast
from pathlib import Path

from app.scan.models import Usage

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


class ApiScanner:
    def __init__(self, base_url: str, ignore_dirs: set[str] | None = None):
        self.base_url = base_url.rstrip("/")
        self.ignore_dirs = ignore_dirs or {".git", ".venv", "__pycache__", "node_modules", ".tox"}

    def scan(self, root: str | Path) -> list[Usage]:
        usages: list[Usage] = []
        for path in Path(root).rglob("*.py"):
            if self._ignored(path):
                continue
            usages.extend(self.scan_file(path))
        return sorted(usages, key=lambda u: (u.file, u.line, u.method, u.path))

    def scan_source(self, source: str, filename: str = "<string>") -> list[Usage]:
        try:
            tree = ast.parse(source, filename=filename)
        except SyntaxError:
            return []
        constants = self._module_constants(tree)
        visitor = _CallVisitor(filename, self.base_url, constants)
        visitor.visit(tree)
        return visitor.usages

    def scan_file(self, path: Path) -> list[Usage]:
        try:
            source = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return []
        return self.scan_source(source, str(path))

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
        method = self._method_of(node.func)
        if method and node.args:
            url = self._evaluate_url(node.args[0])
            if url is not None:
                path = self._extract_path(url)
                if path is not None:
                    self.usages.append(Usage(self.file, node.lineno, method, path))
        self.generic_visit(node)

    def _method_of(self, func) -> str | None:
        if isinstance(func, ast.Name) and func.id in HTTP_METHODS:
            return func.id
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

    def _extract_path(self, url: str) -> str | None:
        if url.startswith(self.base_url):
            path = url[len(self.base_url):]
        elif url.startswith("/"):
            path = url
        else:
            return None
        return path if path.startswith("/") else None
