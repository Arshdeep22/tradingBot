# Session 02: Git Ops + Code Editor

**Prerequisite**: Session 01 complete (models.py and config.py exist).  
**Goal**: Two infrastructure modules — `git_ops.py` (branch/commit/revert) and `code_editor.py` (safe AST-validated read/write). Both must be fully testable without running a real backtest.  
**Rule**: No file exceeds 200 lines. Split any module that approaches the limit.

---

## Files to Create

### `autonomous_optimizer/git_ops.py`  (~160 lines)

Wraps git commands needed by the agent. All methods take `repo_root` from `AgentConfig`. Raises `GitError` on failure — never silently swallows errors.

**Methods required:**

```python
class GitOps:
    def __init__(self, config: AgentConfig): ...

    def ensure_branch(self) -> None:
        """Create agent/optimize branch if it doesn't exist; check it out."""
        # git checkout -b agent/optimize 2>/dev/null || git checkout agent/optimize

    def create_snapshot(self, label: str = "") -> str:
        """
        Stash current working tree state as a lightweight snapshot tag.
        Returns the snapshot tag name, e.g. "snap-iter-042".
        Uses: git stash push -m <label>  (stash index 0 is the snapshot)
        Stores snapshot ref in session state for revert.
        """

    def commit(self, message: str) -> str:
        """
        Stage all tracked files, commit with message.
        Returns the short SHA.
        Message format must be: [iter=N][phase=X][wr=Y][pnl=Z][trades=W][composite=S][hyp=slug]
        Validated before committing — raises ValueError if format wrong.
        """

    def push(self) -> None:
        """Push agent/optimize branch to origin. No-op if remote not configured."""

    def revert_to_snapshot(self) -> None:
        """Pop the most recent stash (snapshot). Discards working tree changes."""

    def tag(self, name: str) -> None:
        """Create a lightweight git tag at HEAD."""

    def query_commits(self, grep: str) -> list[dict]:
        """
        Query commits on agent/optimize branch matching grep string.
        Returns list of dicts parsed from semantic commit message fields.
        e.g. [{"iter": 14, "wr": 61.2, "pnl": 18400, "hyp": "trailing-stop"}]
        """

    def current_diff(self, base: str = "HEAD") -> str:
        """Return git diff of working tree vs base. Used by Observer."""

    def recent_blame(self, files: list[str], n_lines: int = 5) -> list[str]:
        """Return last-modified line info for the given files (for Observer)."""
```

**Commit message format validator** (private method):
```python
import re
_COMMIT_RE = re.compile(
    r"\[iter=\d+\]\[phase=[ABC]\]\[wr=[\d.]+\]\[pnl=[-\d.]+\]"
    r"\[trades=\d+\]\[composite=[\d.]+\]\[hyp=[\w-]+\]"
)
```

**Error class:**
```python
class GitError(RuntimeError): pass
```

---

### `autonomous_optimizer/code_editor.py`  (~140 lines)

Safe file read/write with AST validation before touching disk. Split into two concerns:

**`code_editor.py`** — public API:
```python
class CodeEditor:
    def read_file(self, path: str) -> str:
        """Read and return file contents. Raises FileNotFoundError if missing."""

    def write_file(self, path: str, new_code: str) -> None:
        """
        Validate Python syntax via ast.parse() before writing.
        Raises SyntaxError (with line info) if invalid — never writes to disk.
        Creates parent directories if needed.
        """

    def validate_syntax(self, code: str, source_label: str = "<generated>") -> None:
        """
        ast.parse() the code. Raises SyntaxError with source_label if invalid.
        Call this before any write_file to get a clean error message.
        """

    def surgical_replace_function(self, path: str, func_name: str, new_func_src: str) -> None:
        """
        Use libcst to replace exactly one function by name in the file.
        Validates: new_func_src must parse, func_name must exist in target file.
        All other code in the file is untouched.
        Raises: FunctionNotFoundError, SyntaxError, libcst.ParserSyntaxError
        """

    def list_top_level_functions(self, path: str) -> list[str]:
        """Return names of all top-level functions in a Python file. Used by Critic."""
```

**`code_editor.py`** — error classes:
```python
class FunctionNotFoundError(ValueError): pass
class SyntaxValidationError(SyntaxError): pass
```

**Implementation note on `surgical_replace_function`**: use `libcst`. If `libcst` is not installed, fall back to full-file replacement (write the entire new_func_src as a module-level function). Log a warning. This way the module works even if `libcst` is not yet installed in the test environment.

```python
try:
    import libcst as cst
    _LIBCST_AVAILABLE = True
except ImportError:
    _LIBCST_AVAILABLE = False
```

---

## Tests to Write

### `tests/autonomous_optimizer/test_git_ops.py`  (~100 lines)

Use `tmp_path` (pytest fixture) to create a real temporary git repo for each test. This avoids touching the real repo.

```python
@pytest.fixture
def tmp_repo(tmp_path):
    """Create a minimal git repo in a temp dir."""
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path
```

Tests:
```
test_ensure_branch_creates_branch       → after ensure_branch(), git branch shows agent/optimize
test_create_snapshot_and_revert         → write a file, snapshot, modify, revert → original content restored
test_commit_valid_message               → commit with valid semantic message → returns a short SHA string
test_commit_invalid_message_raises      → commit with "bad message" → ValueError
test_tag_creates_tag                    → after tag("phase-a-start"), git tag output contains it
test_query_commits_empty                → no matching commits → returns []
test_query_commits_parse                → commit with known message → parsed dict has correct fields
test_current_diff_empty_on_clean        → no changes → empty string
```

### `tests/autonomous_optimizer/test_code_editor.py`  (~80 lines)

```
test_read_file_missing_raises           → FileNotFoundError
test_write_valid_python                 → file created, content matches
test_write_invalid_python_does_not_write → SyntaxError raised, file not written
test_validate_syntax_valid              → no exception
test_validate_syntax_invalid            → SyntaxError with filename in message
test_list_top_level_functions           → counts correct number of functions in a test file
test_surgical_replace_function_basic    → replaces foo(), bar() stays intact
test_surgical_replace_not_found_raises  → FunctionNotFoundError for unknown func name
```

Run: `python -m pytest tests/autonomous_optimizer/test_git_ops.py tests/autonomous_optimizer/test_code_editor.py -v`

---

## Acceptance Criteria

1. Both test files pass — all green.
2. No file exceeds 200 lines.
3. `code_editor.write_file` with invalid Python never creates or modifies the target file.
4. `git_ops.revert_to_snapshot()` restores the working tree to the state at `create_snapshot()`.
5. `git_ops.commit()` raises `ValueError` for a non-semantic commit message.
6. `surgical_replace_function` works without `libcst` (falls back gracefully with a warning).
