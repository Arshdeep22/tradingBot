from __future__ import annotations

import ast

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis, CriticResult
from autonomous_optimizer.code_editor import CodeEditor


class Critic:
    def __init__(self, config: AgentConfig, code_editor: CodeEditor):
        self._config = config
        self._editor = code_editor

    def review(self, hypothesis: Hypothesis, proposed_code: dict[str, str]) -> CriticResult:
        scope_violations = self._check_scope(list(proposed_code.keys()), hypothesis.target_files)

        syntax_errors: dict[str, str] = {}
        for filepath, code in proposed_code.items():
            err = self._check_syntax(filepath, code)
            if err is not None:
                syntax_errors[filepath] = err

        hypothesis_drift = any(hypothesis.slug in code for code in proposed_code.values())

        approved = not scope_violations and not syntax_errors

        if not approved:
            parts = []
            if scope_violations:
                parts.append(f"Scope violations: {scope_violations}")
            if syntax_errors:
                parts.append(f"Syntax errors: {syntax_errors}")
            reason = "; ".join(parts)
        else:
            reason = ""

        return CriticResult(
            approved=approved,
            reason=reason,
            scope_violations=scope_violations,
            hypothesis_drift=hypothesis_drift,
        )

    def _check_syntax(self, filepath: str, code: str) -> str | None:
        try:
            ast.parse(code)
            return None
        except SyntaxError as e:
            return f"{e.msg} (line {e.lineno})"

    def _check_scope(self, proposed_files: list[str],
                     target_files: list[str]) -> list[str]:
        return [f for f in proposed_files if f not in target_files]
