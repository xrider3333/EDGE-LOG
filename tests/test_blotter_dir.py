"""Per-run trade blotters are written OUTSIDE the repo (2026-11-18).

The repo root sits under OneDrive/Desktop. On 2026-11-15 the trial cache rewriting
itself inside that tree flooded Explorer's change notices until the taskbar froze; the
fix moved the cache to C:/EdgeLog. The runner's blotter CSVs are the same write pattern
(one file per Auto-Validate / grid run, into a folder Explorer watches), so they move the
same way - and the reader still has to find every CSV written before the move.
"""
import os

from augur_engine import paths


def test_the_default_is_edgelog_home_not_the_repo(monkeypatch, tmp_path):
    home = tmp_path / "EdgeLog"
    home.mkdir()
    monkeypatch.delenv("AUGUR_BLOTTER_DIR", raising=False)
    monkeypatch.setenv("EDGELOG_HOME", str(home))
    d = paths.blotter_dir()
    assert os.path.realpath(d) == os.path.realpath(str(home / "blotters"))
    assert os.path.isdir(d), "the directory is created on demand"
    assert not os.path.realpath(d).startswith(os.path.realpath(paths.ROOT) + os.sep), \
        "a blotter must never land inside the OneDrive repo tree"


def test_it_falls_back_to_the_repo_when_there_is_no_edgelog_home(monkeypatch, tmp_path):
    # CI, or a clone on another machine: no C:/EdgeLog, so the repo root is all there is.
    monkeypatch.delenv("AUGUR_BLOTTER_DIR", raising=False)
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "nope"))
    assert os.path.realpath(paths.blotter_dir()) == \
        os.path.realpath(os.path.join(paths.ROOT, "blotters"))


def test_the_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("EDGELOG_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AUGUR_BLOTTER_DIR", str(tmp_path / "mine"))
    assert os.path.realpath(paths.blotter_dir()) == os.path.realpath(str(tmp_path / "mine"))


def test_it_is_read_live_so_a_test_can_redirect_it(monkeypatch, tmp_path):
    monkeypatch.setenv("AUGUR_BLOTTER_DIR", str(tmp_path / "a"))
    first = paths.blotter_dir()
    monkeypatch.setenv("AUGUR_BLOTTER_DIR", str(tmp_path / "b"))
    assert paths.blotter_dir() != first, "no import-time caching"


def test_the_runner_writes_through_the_helper_and_not_under_root():
    import io
    import api.runner as R
    src = io.open(R.__file__, encoding="utf-8").read()
    assert 'os.path.join(blotter_dir(),' in src
    assert 'os.path.join(ROOT, "blotters"' not in src, \
        "the runner must not write a blotter into the repo tree any more"


def test_the_reader_still_finds_the_blotters_saved_before_the_move():
    """Every run saved before 2026-11-18 wrote into the repo's own blotters/ and those
    CSVs stay where they are - the search order has to include that folder."""
    import io
    import api.blotter as B
    src = io.open(B.__file__, encoding="utf-8").read()
    # the search list in load_blotter_rows - not the unrelated `cands = []` further up
    cands = src.split("cands = [os.path.join(", 1)[1].split("]", 1)[0]
    assert "blotter_dir()" in cands, "the new directory is searched"
    assert '"blotters", name' in cands, "the repo's old copies are still searched"
    assert cands.index("blotter_dir()") < cands.index('root, "blotters"'), \
        "the new directory comes first"
