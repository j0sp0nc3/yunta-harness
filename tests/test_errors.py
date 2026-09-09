import pytest
from yunta.errors import classify_tool_error


def test_classify_file_not_found():
    res = classify_tool_error("read_file", "FileNotFoundError: [Errno 2] No such file or directory: 'foo.py'")
    assert "[RECUPERACIÓN DE ERROR (FILE_NOT_FOUND):" in res
    assert "list_dir" in res or "tree" in res


def test_classify_permission_denied():
    res = classify_tool_error("write_file", "PermissionError: [Errno 13] Access is denied: 'secret.txt'")
    assert "[RECUPERACIÓN DE ERROR (PERMISSION_DENIED):" in res


def test_classify_timeout():
    res = classify_tool_error("bash", "TimeoutError: command timed out after 30 seconds")
    assert "[RECUPERACIÓN DE ERROR (TIMEOUT):" in res


def test_classify_parse_syntax():
    res = classify_tool_error("bash", "json.decoder.JSONDecodeError: Expecting value")
    assert "[RECUPERACIÓN DE ERROR (PARSE_OR_SYNTAX):" in res


def test_classify_git_conflict():
    res = classify_tool_error("bash", "git error: merge conflict in file.py")
    assert "[RECUPERACIÓN DE ERROR (GIT_CONFLICT):" in res


def test_classify_unknown():
    res = classify_tool_error("custom_tool", "Unexpected internal state code 99")
    assert "[RECUPERACIÓN DE ERROR (UNKNOWN):" in res
