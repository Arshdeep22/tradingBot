from __future__ import annotations

import logging

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.code_editor import CodeEditor

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Coder component of an autonomous trading bot optimizer.
You will receive a hypothesis and the current content of files to modify.

Rules:
1. Output ONLY valid Python code for each file — no explanations, no markdown.
2. Do NOT change function signatures that are called from other files.
3. Do NOT add new imports unless strictly required by the change.
4. Do NOT change anything outside the scope of the hypothesis.
5. The output must be a JSON object: {"filepath": "new_file_contents", ...}
6. Only include files that actually need to change.
"""

_MAX_FILE_LINES = 150


class CoderError(RuntimeError):
    pass


class Coder:
    def __init__(self, config: AgentConfig, llm: AgentLLMClient,
                 code_editor: CodeEditor):
        self._config = config
        self._llm = llm
        self._editor = code_editor

    def generate_changes(self, hypothesis: Hypothesis) -> dict[str, str]:
        file_contents: dict[str, str] = {}
        for filepath in hypothesis.target_files:
            try:
                file_contents[filepath] = self._editor.read_file(filepath)
            except FileNotFoundError:
                file_contents[filepath] = ""

        msg = self._build_user_message(hypothesis, file_contents)
        data = self._llm.call(_SYSTEM_PROMPT, msg)

        if not isinstance(data, dict):
            raise CoderError(f"Expected dict from LLM, got {type(data).__name__}")

        valid: dict[str, str] = {}
        for filepath, code in data.items():
            try:
                self._editor.validate_syntax(code, source_label=filepath)
                valid[filepath] = code
            except Exception as e:
                logger.warning("Syntax validation failed for %s: %s", filepath, e)

        if not valid:
            raise CoderError("All generated files failed syntax validation")

        return valid

    def _build_user_message(self, hypothesis: Hypothesis,
                             file_contents: dict[str, str]) -> str:
        parts = [
            f"Hypothesis slug: {hypothesis.slug}",
            f"Description: {hypothesis.description}",
            f"Expected delta: {hypothesis.expected_delta}",
            "",
            "Files to modify:",
        ]

        for filepath, content in file_contents.items():
            lines = content.splitlines()
            truncated = lines[:_MAX_FILE_LINES]
            suffix = (
                f"\n... (truncated, {len(lines) - _MAX_FILE_LINES} more lines)"
                if len(lines) > _MAX_FILE_LINES else ""
            )
            parts.append(
                f"\n### {filepath}\n```python\n"
                + "\n".join(truncated)
                + suffix
                + "\n```"
            )

        return "\n".join(parts)

    def apply_changes(self, changes: dict[str, str]) -> list[str]:
        written: list[str] = []
        for filepath, code in changes.items():
            self._editor.write_file(filepath, code)
            written.append(filepath)
        return written
