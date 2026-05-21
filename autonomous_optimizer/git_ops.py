import re
import subprocess

from .config import AgentConfig

_COMMIT_RE = re.compile(
    r"\[iter=\d+\]\[phase=[ABC]\]\[wr=[\d.]+\]\[pnl=[-\d.]+\]"
    r"\[trades=\d+\]\[composite=[\d.]+\]\[hyp=[\w-]+\]"
)


class GitError(RuntimeError):
    pass


class GitOps:
    def __init__(self, config: AgentConfig):
        self._config = config
        self._repo = config.repo_root

    def _run(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                args, cwd=self._repo, check=check,
                capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            raise GitError(f"git command failed: {e.stderr.strip()}") from e

    def ensure_branch(self) -> None:
        branch = self._config.agent_branch
        result = self._run(["git", "checkout", "-b", branch], check=False)
        if result.returncode != 0:
            self._run(["git", "checkout", branch])

    def create_snapshot(self, label: str = "") -> str:
        tag_name = f"snap-{label}" if label else "snap-auto"
        self._run(["git", "stash", "push", "-m", tag_name])
        return tag_name

    def commit(self, message: str) -> str:
        self._validate_commit_message(message)
        self._run(["git", "add", "-u"])
        self._run(["git", "commit", "-m", message])
        result = self._run(["git", "rev-parse", "--short", "HEAD"])
        return result.stdout.strip()

    def push(self) -> None:
        result = self._run(["git", "remote"], check=False)
        if not result.stdout.strip():
            return
        self._run(["git", "push", "origin", self._config.agent_branch])

    def revert_to_snapshot(self) -> None:
        self._run(["git", "stash", "pop"])

    def tag(self, name: str) -> None:
        self._run(["git", "tag", name])

    def query_commits(self, grep: str) -> list[dict]:
        result = self._run(
            ["git", "log", self._config.agent_branch,
             f"--grep={grep}", "--format=%s"],
            check=False,
        )
        commits = []
        for line in result.stdout.splitlines():
            parsed = self._parse_commit_message(line)
            if parsed:
                commits.append(parsed)
        return commits

    def current_diff(self, base: str = "HEAD") -> str:
        result = self._run(["git", "diff", base], check=False)
        return result.stdout

    def recent_blame(self, files: list[str], n_lines: int = 5) -> list[str]:
        lines = []
        for f in files:
            result = self._run(["git", "blame", "--porcelain", f], check=False)
            if result.returncode == 0:
                lines.extend(result.stdout.splitlines()[:n_lines])
        return lines

    def _validate_commit_message(self, message: str) -> None:
        if not _COMMIT_RE.search(message):
            raise ValueError(
                f"Commit message does not match required format: {message!r}"
            )

    def _parse_commit_message(self, message: str) -> dict | None:
        fields: dict = {}
        for key, pattern in [
            ("iter",      r"\[iter=(\d+)\]"),
            ("phase",     r"\[phase=([ABC])\]"),
            ("wr",        r"\[wr=([\d.]+)\]"),
            ("pnl",       r"\[pnl=([-\d.]+)\]"),
            ("trades",    r"\[trades=(\d+)\]"),
            ("composite", r"\[composite=([\d.]+)\]"),
            ("hyp",       r"\[hyp=([\w-]+)\]"),
        ]:
            m = re.search(pattern, message)
            if not m:
                return None
            val = m.group(1)
            if key in ("iter", "trades"):
                fields[key] = int(val)
            elif key in ("wr", "pnl", "composite"):
                fields[key] = float(val)
            else:
                fields[key] = val
        return fields
