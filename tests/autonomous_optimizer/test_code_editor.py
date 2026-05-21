import pytest
from pathlib import Path

from autonomous_optimizer.code_editor import (
    CodeEditor,
    FunctionNotFoundError,
    SyntaxValidationError,
)


@pytest.fixture
def editor():
    return CodeEditor()


def test_read_file_missing_raises(editor, tmp_path):
    with pytest.raises(FileNotFoundError):
        editor.read_file(str(tmp_path / "nonexistent.py"))


def test_write_valid_python(editor, tmp_path):
    p = tmp_path / "out.py"
    code = "x = 1\n"
    editor.write_file(str(p), code)
    assert p.exists()
    assert p.read_text() == code


def test_write_invalid_python_does_not_write(editor, tmp_path):
    p = tmp_path / "out.py"
    with pytest.raises(SyntaxError):
        editor.write_file(str(p), "def foo(:\n    pass\n")
    assert not p.exists()


def test_validate_syntax_valid(editor):
    editor.validate_syntax("x = 1\n", source_label="test.py")


def test_validate_syntax_invalid(editor):
    with pytest.raises(SyntaxError) as exc_info:
        editor.validate_syntax("def foo(:\n    pass\n", source_label="myfile.py")
    assert "myfile.py" in str(exc_info.value)


def test_list_top_level_functions(editor, tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def foo(): pass\ndef bar(): pass\nx = 1\n")
    funcs = editor.list_top_level_functions(str(p))
    assert set(funcs) == {"foo", "bar"}
    assert len(funcs) == 2


def test_surgical_replace_function_basic(editor, tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n")
    editor.surgical_replace_function(str(p), "foo", "def foo():\n    return 99\n")
    result = editor.read_file(str(p))
    assert "return 99" in result
    assert "bar" in result
    assert "return 2" in result


def test_surgical_replace_not_found_raises(editor, tmp_path):
    p = tmp_path / "mod.py"
    p.write_text("def foo():\n    return 1\n")
    with pytest.raises(FunctionNotFoundError):
        editor.surgical_replace_function(str(p), "nonexistent", "def nonexistent(): pass\n")
