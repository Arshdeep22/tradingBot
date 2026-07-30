"""Base class for every trading-agent tool.

Wraps each public method with an auto-tracing helper so:
  * `tool_invocations` in the DB gets one row per call,
  * the row is tagged `agent='trading_bot'` and stamped with the current
    `run_id` via `contextvars`,
  * errors are captured (ok=0, error=<msg>) without swallowing the exception.

Subclasses just call `self._trace_call(...)` (context-managed) around the
work they do, or use the `@traced_action` decorator on individual methods.
"""
from __future__ import annotations

import contextlib
import functools
import logging
from typing import Any, Callable, Iterator, Optional

from autonomous_optimizer.storage.agent_db import AgentDB, get_agent_db

logger = logging.getLogger(__name__)


class ToolError(RuntimeError):
    """Raised for domain-level failures (missing symbol, timeout, etc.)."""


class ToolBase:
    """Common trace-to-DB plumbing shared by every trading-agent tool."""

    #: subclasses override — used as the `tool_name` column value.
    tool_name: str = "tool"

    def __init__(self, db: Optional[AgentDB] = None):
        self._db = db or get_agent_db()

    # ── low-level tracing primitives ───────────────────────────────────────
    @contextlib.contextmanager
    def _trace_call(self, action: str, args: dict | None = None) -> Iterator[dict]:
        """Context manager that guarantees exactly one `tool_invocations` row.

        Usage:
            with self._trace_call("get_data", {"symbol": s}) as result_slot:
                data = ...
                result_slot["rows"] = len(data)
                return data
        """
        result: dict[str, Any] = {}
        error: Optional[str] = None
        ok = True
        try:
            yield result
        except Exception as exc:  # log + reraise
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            try:
                self._db.record_tool(
                    tool_name=self.tool_name,
                    action=action,
                    args=args or {},
                    result=result,
                    ok=ok,
                    error=error,
                )
            except Exception as trace_exc:  # never let tracing crash the tool
                logger.debug("tool trace failed for %s.%s: %s",
                             self.tool_name, action, trace_exc)


def traced_action(action: Optional[str] = None) -> Callable:
    """Decorator: wrap a ToolBase method so it's automatically traced.

    The decorated function's return value is stored in the trace row under
    `result_json.value`, or — if the return value is a dict — merged in
    directly. Positional/keyword args (excluding `self`) are stored in
    `args_json`.
    """
    def deco(fn: Callable) -> Callable:
        act_name = action or fn.__name__

        @functools.wraps(fn)
        def wrapper(self: ToolBase, *args, **kwargs):
            call_args: dict[str, Any] = {}
            # Best-effort — some args may not be JSON-serialisable, that's OK.
            if args:
                call_args["args"] = [repr(a)[:200] for a in args]
            if kwargs:
                call_args["kwargs"] = {k: repr(v)[:200] for k, v in kwargs.items()}
            with self._trace_call(act_name, call_args) as slot:
                out = fn(self, *args, **kwargs)
                if isinstance(out, dict):
                    slot.update({k: _summarise(v) for k, v in out.items()})
                else:
                    slot["value"] = _summarise(out)
                return out
        return wrapper
    return deco


def _summarise(v: Any) -> Any:
    """Reduce large payloads (DataFrames, arrays) to a short descriptor."""
    try:
        import pandas as pd  # type: ignore
        if isinstance(v, pd.DataFrame):
            return {"kind": "DataFrame", "rows": len(v), "cols": list(v.columns)}
        if isinstance(v, pd.Series):
            return {"kind": "Series", "rows": len(v), "name": v.name}
    except Exception:
        pass
    if isinstance(v, (list, tuple)):
        return v if len(v) <= 20 else {"kind": "list", "len": len(v)}
    if isinstance(v, dict):
        return v if len(v) <= 20 else {"kind": "dict", "len": len(v)}
    return v