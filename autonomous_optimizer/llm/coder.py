from __future__ import annotations

import logging

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis
from autonomous_optimizer.llm.client import AgentLLMClient
from autonomous_optimizer.code_editor import CodeEditor

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Coder component of an autonomous trading bot optimizer.
You will receive a hypothesis and the COMPLETE contents of files to modify.

Rules:
1. Output ONLY valid Python code for each file — no explanations, no markdown.
2. Do NOT change function signatures that are called from other files.
3. Do NOT add new imports unless strictly required by the change.
4. Do NOT change anything outside the scope of the hypothesis.
5. The output must be a JSON object: {"filepath": "new_file_contents", ...}
6. Only include files that actually need to change.
7. CRITICAL: Each file's value must be the COMPLETE file contents, not a partial snippet.
   Never truncate, abbreviate with "..." or "# rest of file unchanged". Return every line.
"""

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
            original = file_contents.get(filepath, "")
            try:
                self._editor.validate_syntax(code, source_label=filepath)
                self._check_no_truncation(filepath, original, code)
                valid[filepath] = code
            except Exception as e:
                logger.warning("Validation failed for %s: %s", filepath, e)

        if not valid:
            raise CoderError("All generated files failed validation")

        return valid

    def _check_no_truncation(self, filepath: str, original: str, generated: str) -> None:
        """Reject generated code that is suspiciously shorter than the original."""
        orig_lines = len(original.splitlines())
        gen_lines = len(generated.splitlines())
        if orig_lines > 50 and gen_lines < orig_lines * 0.6:
            raise CoderError(
                f"{filepath}: generated code has {gen_lines} lines vs original {orig_lines} "
                f"— likely truncated. Refusing to overwrite."
            )

    def _build_user_message(self, hypothesis: Hypothesis,
                             file_contents: dict[str, str]) -> str:
        parts = [
            f"Hypothesis slug: {hypothesis.slug}",
            f"Description: {hypothesis.description}",
            f"Expected delta: {hypothesis.expected_delta}",
            "",
            "Files to modify (COMPLETE file contents — you must return the ENTIRE file):",
        ]

        for filepath, content in file_contents.items():
            parts.append(
                f"\n### {filepath}\n```python\n{content}\n```"
            )

        return "\n".join(parts)

    def apply_changes(self, changes: dict[str, str]) -> list[str]:
        written: list[str] = []
        for filepath, code in changes.items():
            self._editor.write_file(filepath, code)
            written.append(filepath)
        return written
