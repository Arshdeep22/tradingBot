import pytest
from unittest.mock import MagicMock

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.models import Hypothesis
from autonomous_optimizer.llm.coder import Coder, CoderError
from autonomous_optimizer.code_editor import CodeEditor, SyntaxValidationError


@pytest.fixture
def config():
    return AgentConfig()


@pytest.fixture
def llm():
    return MagicMock()


@pytest.fixture
def code_editor():
    return MagicMock(spec=CodeEditor)


@pytest.fixture
def coder(config, llm, code_editor):
    return Coder(config, llm, code_editor)


@pytest.fixture
def hypothesis():
    return Hypothesis(
        slug="fix-exit-logic",
        description="Fix exit logic for better WR",
        target_files=["core/exit.py"],
        expected_delta="WR +5%",
    )


_VALID_CODE = "def foo():\n    return 42\n"


def test_generate_changes_returns_dict(coder, llm, code_editor, hypothesis):
    code_editor.read_file.return_value = _VALID_CODE
    llm.call.return_value = {"core/exit.py": _VALID_CODE}
    code_editor.validate_syntax.return_value = None

    result = coder.generate_changes(hypothesis)
    assert "core/exit.py" in result
    assert result["core/exit.py"] == _VALID_CODE


def test_invalid_syntax_file_excluded(coder, llm, code_editor):
    h = Hypothesis(
        slug="test", description="test",
        target_files=["file1.py", "file2.py"], expected_delta="",
    )
    code_editor.read_file.return_value = _VALID_CODE
    llm.call.return_value = {"file1.py": "bad(", "file2.py": _VALID_CODE}
    code_editor.validate_syntax.side_effect = [SyntaxValidationError("bad syntax"), None]

    result = coder.generate_changes(h)
    assert "file1.py" not in result
    assert "file2.py" in result


def test_all_syntax_fails_raises(coder, llm, code_editor, hypothesis):
    code_editor.read_file.return_value = _VALID_CODE
    llm.call.return_value = {"core/exit.py": "bad("}
    code_editor.validate_syntax.side_effect = SyntaxValidationError("bad syntax")

    with pytest.raises(CoderError):
        coder.generate_changes(hypothesis)


def test_build_user_message_truncates_long(coder, hypothesis):
    long_content = "\n".join(f"line {i}" for i in range(200))
    msg = coder._build_user_message(hypothesis, {"core/exit.py": long_content})
    assert "line 199" not in msg
    assert "line 149" in msg


def test_apply_changes_writes_files(coder, code_editor):
    changes = {"file1.py": _VALID_CODE, "file2.py": _VALID_CODE}
    written = coder.apply_changes(changes)
    assert code_editor.write_file.call_count == 2
    assert set(written) == {"file1.py", "file2.py"}
