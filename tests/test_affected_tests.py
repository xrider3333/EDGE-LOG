r"""Narrow re-validation: which tests could these changed files break? (2026-10-04)

WHY IT EXISTS. The pre-push engine tier is ~23 minutes. The machine-wide push lock stops local
lanes overtaking each other, but the owner's CLOUD sessions push straight to main from another
machine, where no local lock reaches them; TRADING-LOG lost a full 25-minute gate to exactly that.
After such a rejection ship rebases under the same lock hold and gates again, and re-running all
23 minutes to absorb an unrelated commit is the waste being removed.

THE ASKED-FOR RULE WAS UNSAFE, which is the thing these tests exist to keep true. The ask was to
skip the engine tier when the incoming commits "touch nothing in the engine tier" - nothing under
augur_engine/, api/ or tests/. But the suite READS index.html (5 files), docs and *.md (10+),
tools/data/ (8) and setups/ (2), so a commit touching "only" index.html can still change what the
suite sees. And the commit that prompted the ask touched index.html AND a test file, so the
literal rule would not have narrowed it at all. These tests pin the rule that replaced it: narrow
by what the tests actually read - imports, transitively, plus names for everything else - and
return None, meaning run everything, on every doubt.

MEASURED, not argued: over the last 400 commits, 92 changed both code and a test. The selection
covered every touched test in 70, said "run everything" in 20, and appeared to miss 2 - both of
them commits whose only non-test change was a markdown file that happened to add a test in the
same breath, and both of which production would select anyway because a changed test file is
always included. No real misses.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import affected_tests as at  # noqa: E402


# ═══════════════════════════════════════════════════ the pieces, on synthetic input
def test_module_of():
    assert at.module_of("augur_engine/data.py") == "augur_engine.data"
    assert at.module_of("augur_engine/__init__.py") == "augur_engine"
    assert at.module_of("tools/wt.py") == "tools.wt"


def test_imported_names_reads_both_import_forms():
    names = at._imported_names(
        "import os\n"
        "import augur_engine.data\n"
        "from augur_engine import rolls\n"
        "from augur_engine.master_write import write_master_csv\n")
    assert "augur_engine.data" in names
    assert "augur_engine.rolls" in names, "`from X import Y` names the module X.Y too"
    assert "augur_engine.master_write" in names


def test_imported_names_ignores_relative_imports():
    """A relative import stays inside its own package; resolving it needs context this does not
    have, and guessing would put a wrong edge in the graph."""
    assert at._imported_names("from . import sibling\nfrom .. import parent\n") == set()


def test_imported_names_survives_a_syntax_error():
    """A file mid-edit, or Python this interpreter cannot parse, must not break the selection."""
    assert at._imported_names("def oops(:\n") == set()


def test_importers_closure_is_transitive():
    """THE STEP THAT MAKES THIS TRUSTWORTHY. A test importing `data` is affected by a change to
    `rolls` because data imports rolls. Direct importers only would miss it."""
    imports = {
        "augur_engine.rolls": set(),
        "augur_engine.data": {"augur_engine.rolls"},
        "tests.test_resample": {"augur_engine.data"},
        "tests.test_unrelated": {"augur_engine.other"},
        "augur_engine.other": set(),
    }
    hit = at.importers_closure({"augur_engine.rolls"}, imports)
    assert "augur_engine.data" in hit
    assert "tests.test_resample" in hit, "two hops, not one"
    assert "tests.test_unrelated" not in hit


def test_importers_closure_survives_a_cycle():
    imports = {"a": {"b"}, "b": {"a"}, "c": {"a"}}
    hit = at.importers_closure({"a"}, imports)
    assert hit == {"a", "b", "c"}


# ═══════════════════════════════════════════════════ every doubt means "run everything"
@pytest.mark.parametrize("path", ["tests/conftest.py", "pytest.ini", "requirements.txt",
                                  "pyproject.toml"])
def test_a_change_to_how_the_suite_RUNS_cannot_be_narrowed(path):
    assert at.tests_for([path], ROOT) is None


def test_a_python_file_the_tree_does_not_have_cannot_be_narrowed():
    """A file the incoming commit DELETED, or one outside git's listing: the graph cannot speak
    for it, so it does not get to."""
    assert at.tests_for(["augur_engine/no_such_module_here.py"], ROOT) is None


def test_no_changed_paths_selects_nothing():
    assert at.tests_for([], ROOT) == set()


def test_a_selection_covering_most_of_the_suite_is_not_worth_narrowing(monkeypatch):
    monkeypatch.setattr(at, "MAX_SHARE", 0.0001)
    assert at.tests_for(["augur_engine/data.py"], ROOT) is None


def test_any_exception_resolves_to_run_everything(monkeypatch):
    monkeypatch.setattr(at, "test_files",
                        lambda root: (_ for _ in ()).throw(RuntimeError("boom")))
    assert at.tests_for(["augur_engine/data.py"], ROOT) is None


# ═══════════════════════════════════════════════════ against the real repo
def test_a_changed_test_file_is_always_selected():
    picked = at.tests_for(["tests/test_push_lock.py"], ROOT)
    assert picked is not None and "tests/test_push_lock.py" in picked


def test_index_html_selects_the_tests_that_read_it():
    """THE CASE THE ASKED-FOR RULE GOT WRONG. index.html is not under augur_engine/, api/ or
    tests/, so a path rule waves it through - but five test files read it."""
    picked = at.tests_for(["index.html"], ROOT)
    assert picked is not None and len(picked) >= 3
    for t in picked:
        src = open(os.path.join(ROOT, t), encoding="utf-8", errors="replace").read()
        assert "index.html" in src


def test_a_tool_selects_its_own_tests():
    """Tests do not import tools as a package - they put tools/ on sys.path and say
    `import push_lock`, or load the file by path. Without the bare-stem registration a changed
    tools/*.py selected NOTHING, which is the same hole the hook's tools tier exists for."""
    picked = at.tests_for(["tools/push_lock.py"], ROOT)
    assert picked is not None and "tests/test_push_lock.py" in picked


def test_a_transitive_dependency_is_selected_even_when_the_test_never_names_it():
    """Changing rolls.py selects tests that never mention "rolls", because they import modules
    that do. This is the measurable difference between this and a grep."""
    picked = at.tests_for(["augur_engine/rolls.py"], ROOT)
    assert picked is not None
    blind = [t for t in picked
             if "rolls" not in open(os.path.join(ROOT, t), encoding="utf-8",
                                    errors="replace").read()]
    assert blind, "the transitive step must catch tests that never name the changed module"


def test_a_doc_nothing_reads_affects_nothing():
    """A name no test can mention affects no test.

    The first version of this named a REAL doc - and failed, because this very file mentions that
    path two lines up, so the selection was right to pick it. Funny, and the right answer: the
    rule is "a test that names the file is affected", and a test file naming it counts.
    """
    # BUILT, never written literally: a path spelled out here would appear in this very file's
    # source, so the selection would find it and be right to. The first two versions of this test
    # fell into that one after the other.
    unmentioned = "docs/" + "zq" * 9 + ".md"
    assert at.tests_for([unmentioned], ROOT) == set()


def test_a_doc_selects_exactly_the_tests_that_name_it():
    picked = at.tests_for(["docs/ALPACA_STOCK_BARS.md"], ROOT)
    assert picked is not None
    for t in picked:
        src = open(os.path.join(ROOT, t), encoding="utf-8", errors="replace").read()
        assert "ALPACA_STOCK_BARS" in src


# ═══════════════════════════════════════════════════ the CLI contract the hook relies on
def _cli(stdin_text):
    p = subprocess.run([sys.executable, os.path.join(TOOLS, "affected_tests.py"),
                        "--root", ROOT], input=stdin_text, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def test_the_cli_never_asks_for_more_than_the_engine_tier_would_run():
    """A narrowed re-validation stands in for the ENGINE tier, so it must be a SUBSET of it. The
    tier ignores the strategy contract and the surrogate battery, each of which has its own tier.
    Before this, an index.html change narrowed to a set including the 4-minute surrogate battery -
    more work than the thing being approximated."""
    rc, out = _cli("index.html\n")
    assert rc == 0
    for f in out.split():
        base = "tests/" + os.path.basename(f)
        assert base not in at.NOT_IN_ENGINE_TIER, base
    # and it really is affected-by-index.html, just not run here
    assert "tests/test_surrogate.py" in (at.tests_for(["index.html"], ROOT) or set())


def test_the_cli_prints_the_files_to_run():
    rc, out = _cli("index.html\n")
    assert rc == 0 and out, "it must name the files"
    assert all(f.endswith(".py") for f in out.split())


def test_the_cli_prints_NOTHING_when_it_cannot_narrow():
    """The hook reads empty output as "run the full tier", so every failure mode has to come out
    as silence - the hook must not need to know which one happened."""
    for stdin_text in ("", "tests/conftest.py\n", "augur_engine/no_such_module.py\n"):
        rc, out = _cli(stdin_text)
        assert rc == 0 and out == "", repr(stdin_text)


# ═══════════════════════════════════════════════════ how the hook and ship use it
def _read(rel):
    return open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8").read()


def test_the_hook_narrows_only_on_a_verified_claim():
    """ship's env var says "the full tier already passed at THIS tree". The hook must check that
    tree exists and diff it ITSELF - the variable must never be able to ask for work to be
    skipped, only to say where it was already done."""
    src = _read("tools/githooks/pre-push")
    assert "EDGELOG_GATE_PASSED_TREE" in src
    assert "cat-file -e" in src, "it must confirm the tree really exists"
    assert "diff --name-only" in src, "and compute the difference itself"
    assert "affected_tests.py" in src
    i_var = src.index("EDGELOG_GATE_PASSED_TREE")
    i_narrow = src.index('run_tier "Engine (narrowed)"')
    assert i_var < i_narrow


def test_the_hook_falls_back_to_the_full_tier():
    src = _read("tools/githooks/pre-push")
    i_narrow = src.index('run_tier "Engine (narrowed)"')
    after = src[i_narrow:i_narrow + 400]
    assert "else" in after and 'run_tier "Engine"' in after, (
        "empty narrowing must run the whole tier")


def test_ship_retries_without_letting_go_of_the_lock():
    """Releasing the lock to retry would hand it to another lane and reintroduce the race this
    whole thing exists to remove."""
    src = _read("tools/wt.py")
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    assert "EDGELOG_GATE_PASSED_TREE" in body
    assert "_unlock_fd" not in body and "push_lock.release" not in body
    i_push = body.index("'push', '-q', 'origin', 'HEAD:main'")
    i_retry = body.index("EDGELOG_GATE_PASSED_TREE")
    assert i_push < i_retry, "the retry comes after the first push, under the same hold"


def test_ship_reads_the_passed_tree_BEFORE_the_rebase_changes_it():
    """The tree whose gate passed is the PRE-rebase one. Anchored on the RETRY rebase, not
    ship's first one near the top - an earlier version of this test matched that instead and
    failed on correct code."""
    src = _read("tools/wt.py")
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    i_tree = body.index("passed_tree = run(")
    i_retry_rebase = body.index("'rebase', 'origin/main'", body.index("push rejected - main moved"))
    assert i_tree < i_retry_rebase


def test_ship_fetches_before_the_retry_rebase():
    """main moved while the gate ran; rebasing onto a stale origin/main would just be rejected
    again."""
    src = _read("tools/wt.py")
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    i_rejected = body.index("push rejected - main moved")
    after = body[i_rejected:i_rejected + 900]
    assert "'fetch'" in after and after.index("'fetch'") < after.index("'rebase'")


def test_ship_still_proves_the_sha_is_on_main_after_a_retry():
    src = _read("tools/wt.py")
    body = src[src.index("def cmd_ship"):src.index("def warn_pages_budget")]
    assert body.index("EDGELOG_GATE_PASSED_TREE") < body.index("--is-ancestor"), (
        "the on-main proof must come after the retry, not be skipped by it")
