import ast
import logging
from pathlib import Path

try:
    import libcst as cst
    _LIBCST_AVAILABLE = True
except ImportError:
    _LIBCST_AVAILABLE = False

logger = logging.getLogger(__name__)


class FunctionNotFoundError(ValueError):
    pass


class SyntaxValidationError(SyntaxError):
    pass


class CodeEditor:
    def read_file(self, path: str) -> str:
        return Path(path).read_text()

    def write_file(self, path: str, new_code: str) -> None:
        self.validate_syntax(new_code, source_label=path)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_code)

    def validate_syntax(self, code: str, source_label: str = "<generated>") -> None:
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise SyntaxValidationError(
                f"Syntax error in {source_label}: {e.msg} (line {e.lineno})"
            ) from e

    def surgical_replace_function(self, path: str, func_name: str, new_func_src: str) -> None:
        self.validate_syntax(new_func_src, source_label=f"<new {func_name}>")
        existing = self.read_file(path)
        if func_name not in self.list_top_level_functions(path):
            raise FunctionNotFoundError(f"Function {func_name!r} not found in {path}")

        if _LIBCST_AVAILABLE:
            self._libcst_replace(path, existing, func_name, new_func_src)
        else:
            logger.warning("libcst not available; falling back to AST-based function replacement")
            self._ast_replace_fallback(path, existing, func_name, new_func_src)

    def list_top_level_functions(self, path: str) -> list[str]:
        tree = ast.parse(Path(path).read_text())
        return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]

    def _libcst_replace(self, path: str, existing: str, func_name: str, new_func_src: str) -> None:
        import libcst as cst  # noqa: F811 — only reached when _LIBCST_AVAILABLE

        class _FuncReplacer(cst.CSTTransformer):
            def __init__(self, target: str, replacement: cst.FunctionDef):
                self._target = target
                self._replacement = replacement

            def leave_FunctionDef(self, original_node, updated_node):
                if updated_node.name.value == self._target:
                    return self._replacement
                return updated_node

        new_tree = cst.parse_module(new_func_src)
        new_func_node = next(
            (n for n in new_tree.body if isinstance(n, cst.FunctionDef)), None
        )
        if new_func_node is None:
            raise ValueError(f"No function definition found in new_func_src for {func_name!r}")

        old_tree = cst.parse_module(existing)
        new_module = old_tree.visit(_FuncReplacer(func_name, new_func_node))
        Path(path).write_text(new_module.code)

    def _ast_replace_fallback(self, path: str, existing: str, func_name: str, new_func_src: str) -> None:
        tree = ast.parse(existing)
        lines = existing.splitlines(keepends=True)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                start = node.lineno - 1       # 0-indexed inclusive start
                end = node.end_lineno         # 0-indexed exclusive end (end_lineno is 1-indexed inclusive)
                replacement = new_func_src.rstrip("\n") + "\n"
                new_lines = lines[:start] + [replacement] + lines[end:]
                Path(path).write_text("".join(new_lines))
                return
