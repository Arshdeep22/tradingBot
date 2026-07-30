import json
import logging
import os
import re
from typing import Any

from core.llm_advisor import AICoreLLM

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```")
_REQUIRED_ENV_VARS = (
    "AICORE_AUTH_URL",
    "AICORE_API_URL",
    "AICORE_CLIENT_ID",
    "AICORE_CLIENT_SECRET",
)


class LLMError(RuntimeError):
    pass


class AgentLLMClient:
    def __init__(self, config):
        self._config = config
        self._llm = self._build_llm()

    def call(self, system_prompt: str, user_message: str,
             expect_json: bool = True, max_retries: int = 3,
             stage: str = "", max_tokens: int = 4096) -> Any:
        if expect_json:
            system_prompt = system_prompt + "\nRespond ONLY with valid JSON."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Print the input the LLM will see (first ~800 chars of the user message)
        # so operators can actually understand what the agent is asking the model.
        preview_max = 800
        preview = user_message if len(user_message) <= preview_max else (
            user_message[:preview_max] + f"... [+{len(user_message) - preview_max} chars]"
        )
        tag = f"[{stage}] " if stage else ""
        logger.info("%sLLM PROMPT (%d chars, max_tokens=%d):\n%s",
                    tag, len(user_message), max_tokens, preview)

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                raw = self._llm.chat(messages, max_tokens=max_tokens, temperature=0.2)
            except Exception as e:
                last_error = e
                logger.warning("%sLLM call failed (attempt %d/%d): %s",
                               tag, attempt + 1, max_retries, e)
                continue

            logger.info("%sLLM REPLY (%d chars): %.400s",
                        tag, len(raw), raw.replace("\n", " "))

            if not expect_json:
                return raw

            text = self._strip_fences(raw)
            try:
                parsed = json.loads(text)
                return parsed
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning("JSON parse failed (attempt %d/%d): %s", attempt + 1, max_retries, e)

        raise LLMError(f"LLM call failed after {max_retries} attempts: {last_error}") from last_error

    def _strip_fences(self, text: str) -> str:
        """
        Remove markdown code fences from an LLM reply.
        Handles the case where the closing ``` is missing (e.g. reply was
        truncated by max_tokens) by stripping the leading fence alone.
        """
        text = text.strip()
        m = _FENCE_RE.search(text)
        if m:
            return m.group(1).strip()
        # Fallback: strip leading ```json / ``` and any trailing ``` if present
        if text.startswith("```json"):
            text = text[len("```json"):].lstrip("\r\n")
        elif text.startswith("```"):
            text = text[len("```"):].lstrip("\r\n")
        if text.endswith("```"):
            text = text[:-3].rstrip()
        return text

    def _build_llm(self) -> AICoreLLM:
        missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}"
            )
        return AICoreLLM(
            auth_url=os.environ["AICORE_AUTH_URL"],
            api_url=os.environ["AICORE_API_URL"],
            client_id=os.environ["AICORE_CLIENT_ID"],
            client_secret=os.environ["AICORE_CLIENT_SECRET"],
            resource_group=os.environ.get("AICORE_RESOURCE_GROUP", "default"),
            model=os.environ.get("AICORE_MODEL", self._config.llm_model),
        )
