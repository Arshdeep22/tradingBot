"""Entry point: python -m autonomous_optimizer [--dry-run] [--iterations N] [--phase A|B|C]"""
import argparse
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
