"""The plugin gate: LLM-written strategy code is refused BEFORE the engine imports it.

augur_engine/plugin_gate.py (MANAGER 2026-10-17). A file in augur_strategies/qwen_lab/, named QL_*, or carrying an
`# AUGUR-SOURCE: qwen` marker must (1) be stamped in qwen_lab/REVIEWED.json with the LF sha256 of its bytes by the
Claude lane that reviewed it onto main and (2) pass the static whitelist - or load_strategy() raises PluginGateError
without executing a line of it. Hand-written strategies are untouched. The runner's own pin-check import and the
engine's AI code validator run the same gate. Everything here runs on temp files; no real strategy, data or
network is touched.
"""
import json
import os
import subprocess
import sys

import pytest

from augur_engine import load_strategy, gate_plugin, inspect_plugin, safety_check, PluginGateError
from augur_engine import plugin_gate as pg
from augur_engine.paths import ROOT

SAFE_PLUGIN = '''"""QL_SAFE - a minimal plugin that honours the contract."""
import numpy as np

STRATEGY_NAME = "QL SAFE 1.0"
DESCRIPTION = "buys the first bar of the series, flat at the last (test fixture)"
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}

DEFAULT_PARAMS = {
    "lookback": {"default": 5, "min": 2, "max": 20, "step": 1, "type": "int", "label": "Lookback"},
}


def run_backtest(O, H, L, C, lookback=5, return_trades=False, **kw):
    n = len(C)
    if n < lookback + 2:
        return None
    pnl = float(C[-1] - O[lookback])
    res = {"total_pnl": pnl, "num_trades": 1, "win_rate": 1.0 if pnl > 0 else 0.0,
           "profit_factor": 1.0, "max_drawdown": 0.0, "avg_pnl": pnl,
           "wins": 1 if pnl > 0 else 0, "losses": 0 if pnl > 0 else 1}
    if return_trades:
        res["trades"] = [(lookback, n - 1, pnl)]
    return res
'''

# A module body that would leave a trace if it ever ran. Each case is refused by the whitelist; the gate must
# refuse it BEFORE import, so the sentinel file must never appear.
UNSAFE_CASES = {
    "import os": "import os\nos.makedirs('x')\n",
    "open()": "f = open('sentinel.txt', 'w')\n",
    "subprocess": "import subprocess\nsubprocess.run(['echo'])\n",
    "dunder": "x = ().__class__.__bases__[0]\n",
    "np.load": "import numpy as np\nx = np.load('a.npy')\n",
    "pandas writer": "import pandas as pd\npd.DataFrame().to_csv('a.csv')\n",
    "getattr": "g = getattr(int, 'real')\n",
    "attribute store": "import numpy as np\nnp.random = None\n",
    "class": "class A:\n    pass\n",
    "from engine": "from augur_engine.engine import run_backtest\n",
    "module-level call": "import math\nmath.floor(1.5)\n",
    "bytes literal": "x = b'abc'\n",
    "dunder string": "x = '__class__'\n",
    "exec": "exec('1')\n",
    "star import": "from numpy import *\n",
}


def _write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def _stamp(path, by="TESTLANE"):
    return pg.stamp_reviewed(path, by, "test")


@pytest.fixture
def strat_dir(tmp_path):
    """A throwaway strategies directory with the qwen_lab/ sub-directory the lab writes into."""
    d = tmp_path / "augur_strategies"
    (d / "qwen_lab").mkdir(parents=True)
    return str(d)


# ----------------------------------------------------------------------------------------------- provenance
def test_hand_written_file_is_not_gated(strat_dir):
    p = _write(os.path.join(strat_dir, "ORB_TEST_9_9.py"), SAFE_PLUGIN.replace("QL SAFE", "ORB TEST"))
    rep = inspect_plugin(p)
    assert rep["llm"] is None and rep["ok"] and rep["reasons"] == []
    gate_plugin(p)                                      # no ledger, no marker: passes straight through
    mod = load_strategy(p)
    assert mod.STRATEGY_NAME == "ORB TEST 1.0"


def test_a_comment_mentioning_qwen_is_not_a_marker(strat_dir):
    p = _write(os.path.join(strat_dir, "NOISE_TEST_1.py"), "# ported from a qwen suggestion\n" + SAFE_PLUGIN)
    assert pg.provenance(p) is None


@pytest.mark.parametrize("where", ["dir", "name", "marker", "unknown-marker"])
def test_llm_provenance_is_detected(strat_dir, where):
    if where == "dir":
        p = _write(os.path.join(strat_dir, "qwen_lab", "ZZ_PLAIN.py"), SAFE_PLUGIN)
        assert pg.provenance(p) == "dir qwen_lab/"
    elif where == "name":
        p = _write(os.path.join(strat_dir, "QL_ROOT.py"), SAFE_PLUGIN)
        assert pg.provenance(p) == "name QL_"
    elif where == "marker":
        p = _write(os.path.join(strat_dir, "PLAIN_NAME.py"), "# AUGUR-SOURCE: qwen\n" + SAFE_PLUGIN)
        assert pg.provenance(p) == "marker qwen"
    else:
        p = _write(os.path.join(strat_dir, "PLAIN_NAME.py"), "# AUGUR-SOURCE: some-new-model\n" + SAFE_PLUGIN)
        assert pg.provenance(p) == "marker some-new-model"      # unknown values fail closed


def test_human_marker_values_are_not_gated(strat_dir):
    for who in ("hand", "claude", "claude-review", "human"):
        p = _write(os.path.join(strat_dir, "PLAIN_%s.py" % who.replace("-", "_")),
                   "# AUGUR-SOURCE: %s\n" % who + SAFE_PLUGIN)
        assert pg.provenance(p) is None, who


# ----------------------------------------------------------------------------------------------- the ledger
def test_unreviewed_llm_file_is_refused_before_import(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_UNREVIEWED.py"), SAFE_PLUGIN)
    with pytest.raises(PluginGateError) as ei:
        load_strategy(p)
    assert "not reviewed" in str(ei.value)
    assert ei.value.report["llm"] == "dir qwen_lab/"
    assert ei.value.report["sha"] == pg.lf_sha256_file(p)


def test_reviewed_llm_file_loads_and_runs(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_REVIEWED.py"), SAFE_PLUGIN)
    e = _stamp(p)
    assert e["sha256_lf"] == pg.lf_sha256_file(p) and e["reviewed_by"] == "TESTLANE"
    ledger = json.load(open(os.path.join(strat_dir, "qwen_lab", "REVIEWED.json"), encoding="utf-8"))
    assert ledger["QL_REVIEWED.py"]["sha256_lf"] == e["sha256_lf"]
    rep = gate_plugin(p)
    assert rep["ok"] and rep["reviewed"] == e["sha256_lf"] and rep["reviewed_by"] == "TESTLANE"
    mod = load_strategy(p)
    assert callable(mod.run_backtest)


def test_file_changed_after_review_is_refused(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_EDITED.py"), SAFE_PLUGIN)
    _stamp(p)
    _write(p, SAFE_PLUGIN.replace('"default": 5', '"default": 6'))
    with pytest.raises(PluginGateError) as ei:
        gate_plugin(p)
    assert "does not match the file on disk" in str(ei.value)


def test_crlf_and_lf_copies_share_one_sha(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_CRLF.py"), SAFE_PLUGIN)
    _stamp(p)
    with open(p, "wb") as f:
        f.write(SAFE_PLUGIN.replace("\n", "\r\n").encode("utf-8"))   # a Windows checkout of the same file
    assert gate_plugin(p)["ok"]


def test_llm_file_in_the_root_dir_uses_the_one_ledger(strat_dir):
    p = _write(os.path.join(strat_dir, "QL_IN_ROOT.py"), SAFE_PLUGIN)
    assert pg.ledger_path(p) == os.path.join(strat_dir, "qwen_lab", "REVIEWED.json")
    with pytest.raises(PluginGateError):
        gate_plugin(p)
    _stamp(p)
    assert gate_plugin(p)["ok"]


def test_a_broken_ledger_refuses_every_llm_file(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_LEDGER.py"), SAFE_PLUGIN)
    _write(os.path.join(strat_dir, "qwen_lab", "REVIEWED.json"), "{not json")
    with pytest.raises(PluginGateError) as ei:
        gate_plugin(p)
    assert "ledger unreadable" in str(ei.value)


def test_stamp_refuses_a_hand_file_and_an_unsafe_file(strat_dir):
    hand = _write(os.path.join(strat_dir, "ORB_HAND.py"), SAFE_PLUGIN)
    with pytest.raises(ValueError):
        _stamp(hand)
    bad = _write(os.path.join(strat_dir, "qwen_lab", "QL_BAD.py"), SAFE_PLUGIN + "\nimport os\n")
    with pytest.raises(PluginGateError):
        _stamp(bad)                                      # review is not a waiver
    assert not os.path.exists(os.path.join(strat_dir, "qwen_lab", "REVIEWED.json"))


# ----------------------------------------------------------------------------------------------- the whitelist
def test_safe_plugin_passes_the_whitelist():
    assert safety_check(SAFE_PLUGIN) == []
    allowed = ("import math\nimport pandas as pd\nfrom augur_engine.rolls import seam_days\n"
               "from augur_engine.session_calendar import session_dates\n")
    assert safety_check(allowed + SAFE_PLUGIN) == []


@pytest.mark.parametrize("label", sorted(UNSAFE_CASES))
def test_unsafe_code_is_refused_by_the_whitelist(label):
    reasons = safety_check(UNSAFE_CASES[label] + SAFE_PLUGIN)
    assert reasons, label


@pytest.mark.parametrize("label", ["import os", "open()", "subprocess"])
def test_unsafe_reviewed_file_is_refused_before_import(strat_dir, label, monkeypatch):
    """Even a stamped file is refused when its source fails the whitelist - and its body never runs."""
    monkeypatch.chdir(strat_dir)
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_UNSAFE.py"), UNSAFE_CASES[label] + SAFE_PLUGIN)
    ledger = {"QL_UNSAFE.py": {"sha256_lf": pg.lf_sha256_file(p), "reviewed_by": "X", "date": "2026-10-17"}}
    _write(os.path.join(strat_dir, "qwen_lab", "REVIEWED.json"), json.dumps(ledger))
    with pytest.raises(PluginGateError) as ei:
        load_strategy(p)
    assert any(r.startswith("safety:") for r in ei.value.report["reasons"])
    assert not os.path.exists(os.path.join(strat_dir, "sentinel.txt"))
    assert not os.path.exists(os.path.join(strat_dir, "x"))


def test_size_caps():
    assert safety_check("") == ["no code"]
    assert safety_check("x = 1\n" * (pg.CODE_MAX_LINES + 1))[0].startswith("more than")
    assert safety_check("def f(:\n")[0].startswith("syntax error")


# ----------------------------------------------------------------------------------------------- the other doors
def test_ai_validator_refuses_unsafe_code_without_importing_it(tmp_path, monkeypatch):
    from augur_engine.ai import validate_strategy_code
    monkeypatch.chdir(tmp_path)
    mod, err = validate_strategy_code("import os\nos.makedirs('ai_sentinel')\n" + SAFE_PLUGIN)
    assert mod is None and err and "Safety gate refused" in err
    assert not os.path.exists(tmp_path / "ai_sentinel")
    mod, err = validate_strategy_code(SAFE_PLUGIN)
    assert err is None and mod.STRATEGY_NAME == "QL SAFE 1.0"


def test_runner_gates_its_own_pin_check_import():
    """api/runner.py imports the job's strategy file itself for the pin / search-space check; the gate must run
    before that exec_module. A source assertion keeps the runner (Firestore, live paths) un-imported here."""
    src = open(os.path.join(ROOT, "api", "runner.py"), encoding="utf-8").read()
    i_gate = src.find("ae.gate_plugin(_sp)")
    i_exec = src.find('spec_from_file_location("_pin_chk", _sp)')
    assert 0 < i_gate < i_exec


def test_load_strategy_gates_before_exec_module():
    src = open(os.path.join(ROOT, "augur_engine", "strategies.py"), encoding="utf-8").read()
    body = src[src.find("def load_strategy("):src.find("def strategy_file_sha(")]
    assert 0 < body.find("gate_plugin(path)") < body.find("spec.loader.exec_module(mod)")


# ----------------------------------------------------------------------------------------------- the CLI
def test_cli_check_and_stamp(strat_dir):
    p = _write(os.path.join(strat_dir, "qwen_lab", "QL_CLI.py"), SAFE_PLUGIN)
    hand = _write(os.path.join(strat_dir, "HAND_CLI.py"), SAFE_PLUGIN)
    env = dict(os.environ, PYTHONIOENCODING="utf-8")

    def run(*args):
        return subprocess.run([sys.executable, "-m", "augur_engine.plugin_gate", *args], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=120)

    r = run(p, hand)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "REFUSED" in r.stdout and "not reviewed" in r.stdout and "NOT GATED" in r.stdout
    r = run("--stamp", "TESTLANE", p, "fixture")
    assert r.returncode == 0 and r.stdout.startswith("STAMPED"), r.stdout + r.stderr
    r = run(p)
    assert r.returncode == 0 and r.stdout.startswith("PASS"), r.stdout + r.stderr
    r = run("--stamp", "TESTLANE", hand)
    assert r.returncode == 1 and "not LLM-written" in r.stdout


def test_repo_ledger_exists_and_is_empty_or_valid():
    lp = os.path.join(ROOT, "augur_strategies", "qwen_lab", "REVIEWED.json")
    assert os.path.exists(lp)
    led = pg.read_ledger(lp)
    for name, e in led.items():
        assert name.endswith(".py") and len(e.get("sha256_lf", "")) == 64 and e.get("reviewed_by"), name
