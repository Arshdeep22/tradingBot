import subprocess
import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.git_ops import GitOps, GitError


@pytest.fixture
def tmp_repo(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("init")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def git_ops(tmp_repo):
    config = AgentConfig(repo_root=str(tmp_repo))
    return GitOps(config)


def test_ensure_branch_creates_branch(tmp_repo, git_ops):
    git_ops.ensure_branch()
    result = subprocess.run(["git", "branch"], cwd=tmp_repo, capture_output=True, text=True)
    assert "agent/optimize" in result.stdout


def test_create_snapshot_and_revert(tmp_repo, git_ops):
    git_ops.ensure_branch()
    (tmp_repo / "README.md").write_text("original")
    subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True)
    subprocess.run(["git", "commit", "-m", "set original"], cwd=tmp_repo, check=True)

    (tmp_repo / "README.md").write_text("modified")
    git_ops.create_snapshot(label="test")

    assert (tmp_repo / "README.md").read_text() == "original"

    git_ops.revert_to_snapshot()
    assert (tmp_repo / "README.md").read_text() == "modified"


def test_commit_valid_message(tmp_repo, git_ops):
    git_ops.ensure_branch()
    (tmp_repo / "test.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True)
    msg = "[iter=1][phase=A][wr=60.0][pnl=1000.0][trades=10][composite=0.5][hyp=trailing-stop]"
    sha = git_ops.commit(msg)
    assert len(sha) > 0
    assert all(c in "0123456789abcdef" for c in sha)


def test_commit_invalid_message_raises(tmp_repo, git_ops):
    git_ops.ensure_branch()
    with pytest.raises(ValueError):
        git_ops.commit("bad message")


def test_tag_creates_tag(tmp_repo, git_ops):
    git_ops.ensure_branch()
    git_ops.tag("phase-a-start")
    result = subprocess.run(["git", "tag"], cwd=tmp_repo, capture_output=True, text=True)
    assert "phase-a-start" in result.stdout


def test_query_commits_empty(tmp_repo, git_ops):
    git_ops.ensure_branch()
    result = git_ops.query_commits("nonexistent-grep-xyz")
    assert result == []


def test_query_commits_parse(tmp_repo, git_ops):
    git_ops.ensure_branch()
    (tmp_repo / "test.txt").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=tmp_repo, check=True)
    msg = "[iter=14][phase=B][wr=61.2][pnl=18400.0][trades=20][composite=0.7][hyp=trailing-stop]"
    git_ops.commit(msg)

    commits = git_ops.query_commits("iter=14")
    assert len(commits) == 1
    assert commits[0]["iter"] == 14
    assert commits[0]["wr"] == 61.2
    assert commits[0]["hyp"] == "trailing-stop"


def test_current_diff_empty_on_clean(tmp_repo, git_ops):
    git_ops.ensure_branch()
    diff = git_ops.current_diff()
    assert diff == ""
