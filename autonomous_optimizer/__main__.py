"""Entry point: python -m autonomous_optimizer [--dry-run] [--iterations N] [--phase A|B|C]"""
import argparse
import logging
import sys

from autonomous_optimizer.storage import install_db_logging

# Install DB-backed logging FIRST so every subsequent log line lands in
# database/agent.db (runtime_logs). A console handler is also attached so
# operators still see live output — but no *.log files are written to disk.
#
# We do NOT pin the handler's agent label — the handler reads
# `current_agent` from contextvars on every emit, so log lines emitted
# from inside `agent_scope("trading_bot", run_id=...)` will correctly
# land tagged as trading_bot even though the process was started as the
# optimizer. Default agent (outside any scope) is "optimizer".
install_db_logging(
    level=logging.INFO,
    also_console=True,
    console_prefix="[OPT]",
)

logger = logging.getLogger(__name__)


def _parse_args():
    p = argparse.ArgumentParser(description="Autonomous Trading Bot Optimizer")
    p.add_argument("--dry-run", action="store_true", help="Validate setup and exit")
    p.add_argument("--iterations", type=int, default=None, help="Override max_iterations")
    p.add_argument("--phase", choices=["A", "B", "C"], default=None, help="Force start phase")
    return p.parse_args()


def main():
    args = _parse_args()

    if args.dry_run:
        from autonomous_optimizer.agent import Agent
        from autonomous_optimizer.config import DEFAULT_CONFIG
        Agent(DEFAULT_CONFIG)
        logger.info("dry-run OK — Agent constructed successfully")
        sys.exit(0)

    from autonomous_optimizer.agent import Agent
    from autonomous_optimizer.config import DEFAULT_CONFIG
    agent = Agent(DEFAULT_CONFIG)
    agent.run(
        override_iterations=args.iterations,
        override_phase=args.phase,
    )


if __name__ == "__main__":
    main()