import re
import subprocess
import sys

from autonomous_optimizer.config import AgentConfig

_COMMIT_RE = re.compile(
    r"\[iter=\d+\]\[phase=[ABC]\]\[wr=[\d.]+\]\[pnl=[-\d.]+\]"
    r"\[trades=\d+\]\[composite=[\d.]+\]\[hyp=[\w-]+\]"
)

_SNAP_PREFIX = "SNAP:"
_CREATIONFLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


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
                capture_output=True, text=True, encoding="utf-8",
                errors="replace",
                creationflags=_CREATIONFLAGS,
            )
        except subprocess.CalledProcessError as e:
            raise GitError(f"git command failed: {e.stderr.strip()}") from e

    def ensure_branch(self) -> None:
        branch = self._config.agent_branch
        result = self._run(["git", "checkout", "-b", branch], check=False)
        if result.returncode != 0:
            self._run(["git", "checkout", branch])

    def create_snapshot(self, label: str = "") -> str:
        """
        Create a snapshot commit so we can reset to it later.
        Using git stash is unreliable: it silently no-ops when there are no
        staged changes, so a later 'stash pop' would restore the wrong state.
        A snapshot commit is deterministic on all platforms.
        """
        tag_name = f"snap-{label}" if label else "snap-auto"
        self._run(["git", "add", "-A"])
        result = self._run(["git", "diff", "--cached", "--quiet"], check=False)
        if result.returncode == 0:
            # Nothing staged — nothing changed, record current HEAD as snapshot
            head = self._run(["git", "rev-parse", "HEAD"]).stdout.strip()
            return head
        self._run(["git", "commit", "-m", f"{_SNAP_PREFIX} {tag_name}"])
        head = self._run(["git", "rev-parse", "HEAD"]).stdout.strip()
        return head

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
        """Hard-reset to the most recent snapshot commit, then remove it."""
        result = self._run(
            ["git", "log", "--oneline", "--format=%H %s"],
            check=False,
        )
        snap_sha = None
        for line in result.stdout.splitlines():
            sha, _, subject = line.partition(" ")
            if subject.startswith(_SNAP_PREFIX):
                snap_sha = sha
                break

        if snap_sha is None:
            # No snapshot commit found — nothing to revert
            return

        # Get the parent of the snapshot commit (the clean state before changes)
        parent = self._run(["git", "rev-parse", f"{snap_sha}^"]).stdout.strip()
        self._run(["git", "reset", "--hard", parent])

    def tag(self, name: str) -> None:
        # Tags can conflict on re-runs — use -f to overwrite silently
        self._run(["git", "tag", "-f", name])

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
            if result.returncode == 0 and result.stdout:
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
