import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import repo_map  # noqa: E402


def test_describe_py_docstring_and_functions():
    src = '"""Does the thing. More text."""\n\ndef alpha():\n    pass\n\ndef _hidden():\n    pass\n\nclass Beta:\n    pass\n'
    purpose, funcs = repo_map.describe_py(src)
    assert purpose == "Does the thing."
    assert funcs == ["alpha", "Beta"]


def test_describe_py_comment_fallback():
    purpose, funcs = repo_map.describe_py("# -*- coding: utf-8 -*-\n# Builds the widget\nx = 1\n")
    assert purpose == "Builds the widget" and funcs == []


def test_build_handles_bad_python(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "ok.py").write_text('"""Fine module."""\ndef f():\n    pass\n', encoding="utf-8")
    (tmp_path / "tools" / "bad.py").write_text("def (:\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Hello repo\n", encoding="utf-8")
    text = repo_map.build(["README.md", "tools/bad.py", "tools/ok.py"], root=str(tmp_path))
    assert "`tools/ok.py` - Fine module. | f" in text
    assert "does not parse" in text
    assert "`README.md` - Hello repo" in text
    assert "(3 files)" in text
