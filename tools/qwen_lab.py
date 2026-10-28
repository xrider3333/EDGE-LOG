# -*- coding: utf-8 -*-
r"""QWEN LAB - the local Qwen model as a strategy TESTER (owner order 2026-10-15, MANAGER #130; built by CUSTOM-ML).

Owner: "using qwen to read but not push buttons on EL or develop the backtest (which is in python not qwen) doesn't make
sense." So the local model (Ollama, qwen3.8:27b - tools/local_llm.py is the house client) now PROPOSES an idea from the
reading shelf, WRITES a strategy plugin, and this harness GATES it, RUNS it and REPORTS it.

THE RULE THIS FILE IS BUILT AROUND: PYTHON COMPUTES EVERY NUMBER. Qwen's text never supplies a number that is reported.
Every figure in a post, a prereg or a numbers file is computed here (or by the house helpers this file imports) from the
engine's trade list and the pinned master; Qwen sees those numbers as tool results, never the other way round.

ORDER OF GATES (each refuses with a reason that goes back to Qwen as data):
  1. SAFETY GATE (safety_gate): an AST whitelist on Qwen's code BEFORE it is written, imported or executed - imports only
     numpy / pandas / math / `from augur_engine.rolls import seam_days`; no open/exec/eval/compile/__import__/globals/
     getattr/setattr/print, no dunder or private attribute, no attribute assignment, no class, no file or network I/O
     names (np.load, pd.read_*, .to_csv ...), no '__' in any string. Then the plugin only ever runs in a SANDBOX
     SUBPROCESS (`_sandbox`) with a timeout, a memory watchdog, restricted builtins (guarded __import__), and an audit
     hook that blocks file writes, reads outside the Python / engine folders, subprocess, socket, ctypes, registry, etc.
  2. CONTRACT (sandbox mode 'contract'): constants, DEFAULT_PARAMS with at least one RANGED numeric knob, the engine's
     synthetic battery (well-formed / deterministic / truncation no-look-ahead - the same checks as
     tests/test_strategy_contract.py), a real-data smoke on the pinned master's PRE-walk-forward bars and every knob
     at its min and max, and the FIRST-SIGNAL-BAR contract (TTM #144): no smoke entry fills before the proposal's
     first_signal_bar (0-based in-session index + its open clock; checked again on every PRE-WF trade); the ENTRY-FILL
     and TIME-STOP contract (MANAGER #160b/#162): every smoke entry fills at the stated bar's stated price point (open /
     close) and a time stop of N bars exits at the close of entry bar + N; the smoke trade rate within 3x of the stated
     prior (TTM #155). Plugins get REAL dates (MANAGER #156): the bar timestamps (`index`) and the session-calendar
     helpers of augur_engine/session_calendar.py.
  3. LOOK-AHEAD (sandbox mode 'lookahead'): tools/exec_feasibility_audit.py's file checks on the single file, plus a
     PERTURBATION audit on real pre-walk-forward bars - for sampled trades, every bar after the fill (and the
     unknowable part of the fill bar) is replaced and the trade must not change; the ENTRY-BAR INPUTS phase (TTM #145)
     re-draws the first bar at risk (high / low pushed, close / volume moved; open, close and intrabar fills; at the
     defaults and at every ranged knob's min / max) and requires the same exit price and size; the OPEN-EXIT phase
     (TTM, MOMDRIVE) moves the high / low / close of a bar inside a trade whose exit filled at that bar's open and
     requires the same exit - plus fill realism (every fill inside its bar's range). Every phase also runs at EVERY
     searched knob value - each ranged knob's min and max and each option of a multi-option str / bool knob (a 1-trade
     default hides leaks). Every sandboxed run gets a FRESH module namespace and copies of its arrays (no cache can
     replay one run's answer to another). No walk-forward bar is read before the prereg.
     tools/gate_lookahead_audit.py audits the ML gate's feature matrix; a Qwen plugin has no ML gate, so it does not apply.
  4. DEAD LIST: the proposal's name / mechanism against RESEARCH_LEDGER.md's closed rows; clear matches are refused.
     IDEA DEDUPE (MANAGER #148, at propose): an idea the lab already ran - same normalised name, same rule text, same
     mechanism family (IDEA_FAMILIES) or a near copy of its rule - is refused, without using a proposal slot; a plugin
     byte-identical (LF sha256) to one a run idea already ran is refused at write_plugin and at run_stage_a, and an
     open idea RESUMED with such a plugin (or rule) is closed 'CLOSED AS DUPLICATE of <id>' without a run (MANAGER
     #158/#162).
  5. POWER FIRST (inside run_stage_a, after 1-4): tools/mapcheck_f.py's generator and rules on Qwen's stated prior
     (yearly Sharpe as stated; a stated trade rate off by > 2x from the plugin's own pre-walk-forward COUNT is replaced
     by the count); only "CLEARS" goes on. A map close ends the idea at draft (the prior is not re-stated upward).
  6. AUTO PREREG: C:\EdgeLog\qwen_lab\preregs\<name>_<date>.md (hypothesis, mechanism, prior, map, plugin + harness LF
     sha256, session-calendar LF sha256, window, master filename) posted to MANAGER BEFORE the run; the run re-checks
     the plugin, harness and calendar hashes before each stage (the sandbox loads exactly the pinned calendar file).
  7. STAGE A (sandbox mode 'stage_a'): the plugin on its PINNED master (by filename), walk-forward window only
     2016-07-01..2025-06-29 (data loaded from 2015-01-02 to warm indicators; trades entering before the stretch are
     dropped; nothing after 2025-06-29 is ever loaded - asserted), house cost for the instrument, single-threaded,
     AUGUR_TRIAL_CACHE=1. The FOUR NUMBERS are computed HERE from the trade list: ROC %/yr at a $30k drawdown, Sortino
     and DD % from peak (augur_engine.book_sizing.stretch_reading on the valued-daily series built by
     augur_engine.book._mtm_increments), DD5 and the one-episode flag (augur_engine.drawdowns.dd5; NOT TESTABLE when
     DD5 is one episode or the curve never makes a new high - MANAGER #160a), plus trades / yr and the gross edge per
     trade against the round-trip cost. PROMOTION from the PRE-WF to the WF block (MANAGER 10-16 15:45, amends #134):
     pre-WF gross / trade >= cost AND net ROC@30k > 0 AND one-episode False.
  8. AUTO-VALIDATE: only when Stage A WF ROC@30k >= 15, not one episode, >= 100 WF trades and peak RAM < 4 GB; at most ONE
     Qwen-lab validate queued or running (Firestore checked, fail closed); the file must be on main (Claude lane review)
     with the same hash, else the request waits as 'pending review'; tools/queue_guard.py's guard() runs in the sandbox;
     the job is the lanes' shape (tools/noise_queue_422_tp_validate.BASE), 900 trials, window + master pinned.
     --dry-run-validate builds and logs the job and writes nothing to Firestore.

RUN / STOP / RESUME (state + logs under C:\EdgeLog\qwen_lab\, override with QWEN_LAB_HOME):
    python tools/qwen_lab.py run [--once] [--idea N] [--dry-run-validate] [--max-steps 18] [--no-beacon]
    python tools/qwen_lab.py launch [same flags]     detached (no console), for a long unattended run
    python tools/qwen_lab.py stop                     writes STOP; the loop saves and exits at the next step
    python tools/qwen_lab.py status                   current idea, done ideas, validates, pending reviews
    python tools/qwen_lab.py queue-pending [--dry-run-validate]   queue a pending validate once its file is on main
    python tools/qwen_lab.py shelf-open N [N ...] / shelf-close N [N ...] [--why "..."]   MANAGER opens / closes shelf
                                                      papers (appends to shelf_open.txt; the latest line per paper wins)
A killed or stopped run resumes the open idea from its saved transcript on the next `run`.
Run it from a git WORKTREE (plugins are written to <worktree>\augur_strategies\qwen_lab\); it refuses to write plugins
into the shared checkout. Nothing in augur_strategies/qwen_lab/ ships to main without a Claude lane review.
docs/QWEN_LAB.md has the long form.
"""
from __future__ import annotations

import argparse
import ast
import builtins
import datetime as _dt
import functools
import hashlib
import inspect
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import traceback
import types
import zlib

# ------------------------------------------------------------------------------------------------ paths and pins
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"            # the shared checkout: master registry, engine, ledger
HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS_PATH = os.path.abspath(__file__)
LAB_REPO = os.path.dirname(HERE)                                 # the checkout this file lives in (a worktree when run)
LAB_HOME = os.environ.get("QWEN_LAB_HOME") or r"C:\EdgeLog\qwen_lab"
SHELF_HTML = os.environ.get("QWEN_LAB_SHELF") or r"C:\EdgeLog\manager\papers\reading_shelf.html"
LEDGER_REL = "RESEARCH_LEDGER.md"
REPLY_TO = "CUSTOM-ML-MODEL-OPTIMIZATION"                        # the lane that owns the lab (QWEN-LAB has no inbox)
TAG = "QWEN LAB"

# house stretches (tools/rocfrontier/r11_risk.py WF0 / PRE_END / LB0 / LB1)
WF0, WF1 = "2016-07-01", "2025-06-29"
LB0, LB1 = "2025-06-30", "2026-06-30"
DATA_FROM = "2015-01-02"                                         # warm-up: >= 300 sessions before WF0
SMOKE_TO = "2016-06-30"                                          # contract smoke: pre-WF bars only (no WF bar is read
                                                                 # before the prereg); its trade COUNT feeds the map
VALIDATE_FROM, VALIDATE_TO, VALIDATE_LB_MONTHS = "2010-06-07", LB1, 12
# MANAGER #134 (owner: the lab must actually TEST): every idea that passes the hard gates gets a PRE-WF Stage A on the
# pre-walk-forward rows only, file defaults, no tuning; the WF Stage A runs only past the pre-WF bar
PREWF0, PREWF1 = "2010-06-07", "2016-06-30"
PROMOTE_ROC = 15.0                                               # the #134 bar (kept for the record; see below)
# MANAGER 10-16 15:45 (amends #134 - NOISE #422 itself reads 10.99 pre-WF, so ROC >= 15 was a bar no house leg clears):
# promote from the PRE-WF block to the WF block when the pre-WF GROSS edge per trade (before cost, points) >= the
# instrument's round-trip cost in points AND the net pre-WF ROC@30k > 0 AND one-episode is False (NOT TESTABLE fails)
PROMOTE_GROSS_COST_RATIO, PROMOTE_NET_ROC_MIN = 1.0, 0.0
PROMOTION_RULE = ("pre-WF gross / trade >= the round-trip cost (points) AND net pre-WF ROC@30k > 0 AND one-episode "
                  "False - NOT TESTABLE does not pass (MANAGER 10-16 15:45, amends #134)")
assert WF1 < LB0, "the walk-forward stretch must end before the lockbox starts"
assert PREWF1 < WF0, "the pre-walk-forward stretch must end before the walk-forward stretch starts"

# masters pinned BY FILENAME (never an unpinned lookup); (instrument, timeframe) -> registry row identity
MASTERS = {
    ("NQ", "1m"): dict(filename="NOADJ_NQ_1m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("NQ", "2m"): dict(filename="NOADJ_NQ_2m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("NQ", "5m"): dict(filename="NOADJ_NQ_5m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("NQ", "15m"): dict(filename="NOADJ_NQ_15m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("ES", "1m"): dict(filename="NOADJ_ES_1m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("ES", "5m"): dict(filename="NOADJ_ES_5m_RTH.csv", source="db_noadj_rth", session="rth"),
    ("ES", "15m"): dict(filename="NOADJ_ES_15m_RTH.csv", source="db_noadj_rth", session="rth"),
}
# house cost per round trip in POINTS and $ per point (NQ 0.533 RTH - every NQ RTH crown; ES 0.363 - TTM ES legs)
COSTS = {"NQ": (0.533, 20.0), "ES": (0.363, 50.0)}
# short holds (the owner's scalper ask) are charged the 10-12 scalp hunt's basis: NQ 0.783 pt ($15.66), ES 0.613 pt
COSTS_SHORT_HOLD = {"NQ": (0.783, 20.0), "ES": (0.613, 50.0)}

# bars and limits
VALIDATE_BAR_ROC = 15.0
MIN_WF_TRADES = 100
PEAK_RAM_GB_MAX = 4.0                                            # a validate runs 3 fold processes (port trap 1)
PRIOR_SHARPE_MAX = 1.5                                           # house priors run 0.15-0.64; >1.5 is not a prior
PRIOR_TRADES_RANGE = (5, 3000)
MAX_STEPS = 18                                                   # model turns per idea
MAX_PLUGIN_ATTEMPTS = 6
MAX_PROPOSALS = 3
# the version of the hard gates a plugin passed (gates record + plugin record). 2 = the first-signal-bar contract (TTM
# #144, clock index, every searched knob's min / max) and the entry-bar inputs audit (TTM #145, high / low / close /
# volume, intrabar entries incl. strict stop / limit tests, a level dragged past the bar's open, knob corners). 3 = fix
# round 3: the entry-fill + time-stop contract (MANAGER #160b/#162), the smoke trade rate within 3x of the stated prior
# (TTM #155), the open-exit phase and the whole perturbation audit at every ranged knob's min / max (TTM, MOMDRIVE).
# 4 = review round 4 of fix round 3: every plugin run in the sandbox gets a FRESH module namespace and copies of its
# input arrays (a module-level cache replayed the real bars' trades to every audit variant), the safety gate refuses
# caches (module-level stores / mutating calls, mutable defaults), the look-ahead audit covers EVERY searched knob (all
# ranged numeric knobs - at most SEARCHED_KNOBS_MAX - and every option of a multi-option str / bool knob), the entry
# fill is checked at every searched knob value, and the time-stop check catches a time stop shorter than the stated N
# and an undeclared one.
# run_stage_a refuses a plugin gated by an older version: write_plugin again.
GATES_VERSION = 4
# the proposal's timing contract (TTM #144, MANAGER #160b/#162): every NEW proposal states these; a frozen older
# proposal records only the missing ones (propose again with its name)
CONTRACT_FIELDS = ("first_signal_bar", "entry_fill", "time_stop_bars")
NO_FSB_REFUSAL = ("the proposal %s predates the timing contract (TTM #144, MANAGER #160b/#162): it lacks %s, so the "
                  "contract cannot hold the plugin to it. Call propose(...) again WITH first_signal_bar = {\"index\": "
                  "k, \"clock\": \"HH:MM\"}, entry_fill = {\"at\": \"open\"|\"close\"|\"level\", \"bar\": k or -1} and "
                  "time_stop_bars = N (0 = none) (a proposal the map or a prereg has frozen keeps everything else and "
                  "only records the missing fields), then write_plugin(name, code), then run_stage_a")
MAX_LOOK_TURNS = 3                                               # turns of pure reading allowed before a proposal
LOOK_TOOLS = {"read_repo_file", "list_strategies", "dead_list", "shelf_ideas", "ideas"}
MODEL_TIMEOUT = 1800                                             # s per model reply (cold load is minutes)
IDEA_WALL_S = 4 * 3600
SANDBOX_TIMEOUT = {"contract": 900, "lookahead": 3600, "stage_a": 2400, "guard": 2400, "synthetic": 300}   # look-ahead:
# every phase also runs at every searched knob value (QL_NOISE2M_TREND on 2m bars: 508 s on a busy box with 4 knobs;
# review round 4: all ranged knobs, up to SEARCHED_KNOBS_MAX, plus str / bool options)
SANDBOX_MEM_GB = 6.0
NUM_PREDICT = 6000
MAX_CTX_CHARS = 75000                                            # ~21k tokens of the 32k context
TOOL_RESULT_CHARS = 6000
READ_MAX_CHARS = 12000
CODE_MAX_CHARS = 80000
# every paper a lane has CLAIMED or CLOSED (MANAGER #133, 2026-10-15: the lab's #8 runs repeated two lanes' work);
# live / dead papers are skipped from the shelf's own marks, and ledger citations are detected on top of this
DEFAULT_SKIP_SHELF = [2, 3, 6, 8, 10, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 26, 27, 29]
# MANAGER #142 (#137/#138): shelf #30 was picked three times. A paper the lab ran a Stage A on is CLOSED in state.json
# (closed_shelf) and the picker never takes it again; the shelf slot runs ONLY on papers MANAGER opens with
# `python tools/qwen_lab.py shelf-open N ...` (lines appended to <home>\shelf_open.txt). Seeded with every paper the
# lab has already run.
CLOSED_SHELF_SEED = (8, 30)
SHELF_OPEN_FILE = "shelf_open.txt"
# MANAGER #142: lab-level closed families on top of the ledger's dead rows - no source may re-propose them
LAB_DEAD = [
    {"family": "GAMMA", "rx": r"\bgamma|\bgex\b|dealer (?:gamma|hedg)",
     "why": "GAMMA r1 is dead (ledger rows 2.135-2.137; the lab's QL_GAMMA_MOM pre-WF ROC@30k -4.51 and QL_GAMMA_ORB "
            "-3.73), and gamma exposure / GEX / dealer gamma is an owner ask-first idea (MANAGER #142)"},
]
# MANAGER #139: a plugin that barely trades is a BUG, not a dead idea. Before any verdict: pre-WF trades a year more
# than 3x below the stated rate, under 20 a year, or under 100 a year for a scalp idea -> Qwen gets the count and real
# sessions of bars to check its entry condition against, and fixes the plugin (every hard gate again; a prereg
# addendum posted before the re-run). At most 2 retries; still failing -> 'BROKEN PLUGIN (n trades)'.
SANITY_MAX_RETRIES = 2
SANITY_RATIO, SANITY_MIN_TPY, SANITY_MIN_TPY_SCALP = 3.0, 20.0, 100.0
SANITY_BONUS_STEPS, SANITY_BONUS_ATTEMPTS = 4, 3
SANITY_SESSIONS, SANITY_ROWS, SANITY_RESULT_CHARS = 3, 40, 12000
# MANAGER #143: load courtesy - while a ship holds the machine-wide push lock (tools/push_lock.py: an OS lock on byte 0
# of C:\EdgeLog\state\push.lock, the holder's name from byte 1), no NEW Qwen generation or NEW Stage A starts. The lab
# only READS the file; it never takes, creates or deletes the lock.
PUSH_LOCK_DEFAULT = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "state", "push.lock")
COURTESY_RECHECK_S, COURTESY_LOG_EVERY_S = 60, 600

# IDEA SOURCES (MANAGER #133): rotate so the lab never loops on one - the owner's scalper ask, then Qwen's own idea,
# then the next unclaimed shelf paper (skipped while the shelf has none). The pick is recorded in state.json and
# posted to MANAGER as 'QWEN LAB next pick: ...' (harness-written).
SOURCE_ORDER = ("scalper", "own", "shelf")
SOURCE_LABEL = {"scalper": "the owner's scalper ask", "own": "Qwen's own idea", "shelf": "reading shelf"}
SCALPER_FACTS = (
    "The owner wants a profitable SHORT-HOLD NQ or ES strategy (holds of minutes up to about an hour, flat by the "
    "close). HARD FACTS - do not repeat dead work: 59 NQ 1m short-hold cells are dead (micro opening range, open drive, "
    "PDH/PDL, range burst, VWAP cross, sweep-reclaim, chop-fade, volume ignition, box break), plus the BALANCE VWAP fade, "
    "the REVERT 10-second fades and the MISC range fades. At ZERO cost the best gross win rate was 52.1%; the median "
    "gross was $6.60 a trade against a $15.66 NQ round trip (0.783 pt); ES costs 0.613 pt. The only short-hold earner is "
    "NOISE's band on 2m bars (hold 4-12 minutes, win rate 17-25%, payoff about 4x). So a scalp idea must target a LARGE "
    "PAYOFF PER TRADE or long-tail winners, not a high win rate; fixed-target scalps are dead. (Source: the house's "
    "10-12 scalp hunt.)")
OWN_FACTS = (
    "Propose a NEW NQ or ES intraday mechanism of your own - not taken from a shelf paper - with a clear reason it should "
    "earn after costs. It must not be on dead_list(): check it there once before you propose (the harness checks the "
    "proposal too). Prefer a large payoff per trade over a high win rate: fixed-target scalps are dead and the best gross "
    "win rate the house ever found on NQ short holds was 52.1%.")

_MAP_LIFT_MIN = 0.30                                             # mapcheck_f.LIFT_MIN (re-read from the module at run)


class ToolRefused(Exception):
    """A tool call the harness will not carry out; the message goes back to Qwen."""


class LabStopped(Exception):
    """A STOP file appeared while the harness waited (load courtesy) before a new Stage A - nothing was run."""


# ------------------------------------------------------------------------------------------------ small utilities
def lf_bytes(b):
    return b.replace(b"\r\n", b"\n")


def lf_sha256_bytes(b):
    return hashlib.sha256(lf_bytes(b)).hexdigest()


def lf_sha256_file(path):
    with open(path, "rb") as f:
        return lf_sha256_bytes(f.read())


def now_s():
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return _dt.date.today().isoformat()


def jdump(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, default=str, ensure_ascii=False)
    os.replace(tmp, path)


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def cap(s, n=TOOL_RESULT_CHARS):
    s = str(s)
    return s if len(s) <= n else s[:n] + " ...[cut at %d chars]" % n


def _norm(p):
    return os.path.normcase(os.path.realpath(os.path.abspath(p)))


def under(path, root):
    """True when `path` resolves inside `root` (symlinks and .. resolved)."""
    p, r = _norm(path), _norm(root)
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:                                           # different drives
        return False


# ------------------------------------------------------------------------------------------------ the session calendar
# MANAGER #156: plugins get REAL dates - the bar timestamps (`index`, handed to a run_backtest that declares it) and the
# helpers of augur_engine/session_calendar.py (is_last_n_sessions_of_month, session_index_in_month, week_of_month,
# days_to_month_end, ...). The sandbox imports the SHARED checkout's engine (what the runner imports); until the module
# ships there, this checkout's copy is loaded under the same name (both pinned by LF sha256 in the prereg).
CALENDAR_MODULE = "augur_engine.session_calendar"


def calendar_module_path():
    """The session_calendar.py a plugin will import: the shared checkout's when it has one, else this checkout's."""
    for root in (SHARED, LAB_REPO):
        p = os.path.join(root, "augur_engine", "session_calendar.py")
        if os.path.isfile(p):
            return p
    return None


def calendar_pin():
    """(path, LF sha256) of the session_calendar.py a plugin will import now - (None, None) when there is none."""
    p = calendar_module_path()
    return (p, lf_sha256_file(p)) if p else (None, None)


def calendar_module(path=None, expect_sha=None):
    """augur_engine.session_calendar - imported normally, or (the imported augur_engine has none: the shared checkout
    before the module ships) loaded from this checkout's augur_engine/ under the same module name. With `path` (the
    sandbox, review round 4): loaded from EXACTLY that file after its LF sha256 is checked against `expect_sha` (the
    prereg's pin) - a mismatch raises HASH MISMATCH - and registered under the module name, so the plugin's
    `from augur_engine.session_calendar import ...` gets that file and no other."""
    if "augur_engine" not in sys.modules and SHARED not in sys.path and os.path.isdir(SHARED):
        sys.path.insert(0, SHARED)
    if path is None:
        try:
            import augur_engine.session_calendar as sc
            return sc
        except ImportError:
            pass
    import importlib.util
    import augur_engine as ae
    p = path or os.path.join(LAB_REPO, "augur_engine", "session_calendar.py")
    with open(p, "rb") as f:                                     # read ONCE: the bytes checked are the bytes executed
        raw = f.read()
    if expect_sha is not None and lf_sha256_bytes(raw) != expect_sha:
        raise RuntimeError("HASH MISMATCH: the session calendar %s is %s, the prereg pinned %s - refused"
                           % (p, lf_sha256_bytes(raw), expect_sha))
    spec = importlib.util.spec_from_file_location(CALENDAR_MODULE, p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[CALENDAR_MODULE] = mod
    try:
        exec(compile(raw, p, "exec"), mod.__dict__)              # noqa: S102 - the house module, trusted code
    except Exception:
        sys.modules.pop(CALENDAR_MODULE, None)
        raise
    ae.session_calendar = mod                                    # harness code: `import augur_engine.session_calendar`
    return mod


# ------------------------------------------------------------------------------------------------ the lab's home
# one shelf_open.txt line: [YYYY-MM-DD [HH:MM[:SS]]] [open...|close...[:]] n [n, ...]
_SHELF_LINE_RX = re.compile(r"^(?:(\d{4}-\d\d-\d\d)(?:[ T](\d\d:\d\d)(:\d\d)?)?\s+)?(?:(open\w*|clos\w*)\b[\s:]*)?"
                            r"(?=[\d\s,]*\d)([\d\s,]+)$", re.I)


class Lab:
    """State, run log and per-idea folders under LAB_HOME. All writes of the lab go here (or to the plugin folder)."""

    def __init__(self, home=None, plugin_repo=None):
        self.home = home or os.environ.get("QWEN_LAB_HOME") or LAB_HOME
        self.plugin_repo = plugin_repo or LAB_REPO
        self.state_path = os.path.join(self.home, "state.json")
        self.log_path = os.path.join(self.home, "run.log")
        self.stop_path = os.path.join(self.home, "STOP")
        self.lock_path = os.path.join(self.home, "run.lock")
        self.shelf_warnings = []
        os.makedirs(self.home, exist_ok=True)
        self.state = jload(self.state_path, None) or {
            "created": now_s(), "skip_shelf": list(DEFAULT_SKIP_SHELF), "current_idea": None,
            "done_ideas": [], "validates": [], "pending_validates": []}
        self.state["skip_shelf"] = sorted(set(int(x) for x in self.state.get("skip_shelf", [])) |
                                          set(DEFAULT_SKIP_SHELF))
        self.state.setdefault("rotation_index", 0)
        self.state.setdefault("picks", [])
        self.state.setdefault("next_pick", None)
        closed = self.state.setdefault("closed_shelf", {})
        # MANAGER #153b: a shelf paper is closed only by a SANE Stage A - not by a BROKEN PLUGIN, an abort or a
        # duplicate. A closure an earlier harness made on such a run (QL_TOM_CALENDAR_NQ, shelf #34, BROKEN PLUGIN
        # 10-16) is undone here (kept in shelf_closures_undone), so a paper MANAGER opened is open again
        rows = {str((d or {}).get("id")): d for d in list(self.state.get("done_ideas") or [])
                + list(self.state.get("aborted_ideas") or [])}

        def outcome_of(iid):
            o = (rows.get(str(iid)) or {}).get("outcome")
            if o is None:
                o = (jload(os.path.join(self.home, "ideas", str(iid), "idea.json"), None) or {}).get("outcome")
            return str(o or "")
        for k, c in list(closed.items()):
            if (c or {}).get("idea") and _NOT_A_VERDICT_RX.match(outcome_of(c["idea"])):
                self.state.setdefault("shelf_closures_undone", []).append(
                    dict(c, n=int(k), undone_at=now_s(), undone_why="MANAGER #153b: closed by a run that was not a "
                                                                    "sane Stage A (%s)" % outcome_of(c["idea"])[:80]))
                del closed[k]
        # the seed (MANAGER #142: every shelf paper the lab already ran) takes only rows that reached a SANE PRE-WF
        # Stage A - not a BROKEN PLUGIN, an abort, a duplicate, a dead-list refusal, a crash or a model that finished
        # before Stage A (the seed would re-close such a paper on every load)
        seed = set(CLOSED_SHELF_SEED) | {int(d["shelf_n"]) for d in self.state.get("done_ideas", [])
                                         if d.get("shelf_n") is not None
                                         and _SANE_STAGE_RX.match(str(d.get("outcome") or ""))}
        for n in sorted(seed):
            closed.setdefault(str(n), {"at": self.state.get("created") or now_s(), "idea": None,
                                       "why": "seeded: already run by the lab (MANAGER #142)"})

    @property
    def plugin_dir(self):
        return os.path.join(self.plugin_repo, "augur_strategies", "qwen_lab")

    def save(self):
        jdump(self.state_path, self.state)

    def log(self, msg, idea=None):
        line = "%s %s%s" % (now_s(), ("[%s] " % idea) if idea else "", msg)
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass
        try:
            print(line, flush=True)
        except Exception:
            pass

    def idea_dir(self, idea_id):
        d = os.path.join(self.home, "ideas", idea_id)
        os.makedirs(d, exist_ok=True)
        return d

    def stop_requested(self):
        return os.path.exists(self.stop_path)

    # -- the reading shelf: closed after a Stage A, opened only by MANAGER (MANAGER #142)
    @property
    def shelf_open_path(self):
        return os.path.join(self.home, SHELF_OPEN_FILE)

    def close_shelf(self, n, idea_id, why):
        self.state.setdefault("closed_shelf", {})[str(int(n))] = {"at": now_s(), "idea": idea_id, "why": why}
        self.save()
        self.log("shelf #%s CLOSED for the picker: %s" % (n, why), idea_id)

    def shelf_marks(self):
        """{paper number: (action, when)} from shelf_open.txt - the LATEST line naming a paper wins (lines are appended
        in time order, so file order is the authority; MANAGER #147). A line is 'YYYY-MM-DD HH:MM:SS n n ...' (what
        `shelf-open` appends) = OPEN, or 'YYYY-MM-DD HH:MM:SS CLOSE n n ...' (what `shelf-close` appends) = CLOSED
        ('open...' / 'close...' words, ':' and HH:MM or a date alone are accepted); a line of bare numbers still means
        OPEN. An UNDATED line is dated '' - older than any closure the lab recorded (never the file's write time, which
        moves with every append). Any other line is IGNORED and listed in self.shelf_warnings (a malformed line never
        opens a paper); '# ...' is a comment. So a close after an open = closed, an open after a close = open."""
        out = {}
        self.shelf_warnings = []
        try:
            with open(self.shelf_open_path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return out
        for i, raw in enumerate(lines, 1):
            ln = raw.split("#")[0].strip()
            if not ln:
                continue
            m = _SHELF_LINE_RX.match(ln)
            if not m:
                self.shelf_warnings.append("shelf_open.txt line %d ignored (not '[date [time]] [open|close] numbers'): "
                                           "%r" % (i, raw.strip()[:80]))
                continue
            date, hhmm, ss, word, nums = m.groups()
            at = ("%s %s%s" % (date, hhmm or "00:00", ss or ":00")) if date else ""
            act = "close" if (word or "").lower().startswith("clos") else "open"
            for tok in re.findall(r"\d+", nums):
                out[int(tok)] = (act, at)
        return out

    def shelf_opened(self):
        """{paper number: when MANAGER opened it} for the papers whose latest shelf_open.txt line is an OPEN."""
        return {n: at for n, (act, at) in self.shelf_marks().items() if act == "open"}

    def shelf_closed_by_manager(self):
        """{paper number: when MANAGER closed it} for the papers whose latest shelf_open.txt line is a CLOSE."""
        return {n: at for n, (act, at) in self.shelf_marks().items() if act == "close"}

    def open_shelf_numbers(self):
        """Papers MANAGER opened and the lab has not run a Stage A on since (an undated open line is older than any lab
        closure)."""
        closed = self.state.get("closed_shelf", {})
        return sorted(n for n, at in self.shelf_opened().items()
                      if str(n) not in closed or at > str(closed[str(n)].get("at") or ""))


def check_plugin_repo(repo):
    """Plugins go into a WORKTREE, never the shared checkout (house rule: never commit on shared main)."""
    if under(repo, SHARED) and _norm(repo) == _norm(SHARED):
        raise SystemExit("REFUSED: the plugin repo is the shared checkout %s - run the lab from a worktree "
                         "(tools/wt.py new <name>) or pass --plugin-repo <worktree>" % SHARED)
    if not os.path.isdir(os.path.join(repo, "augur_strategies")):
        raise SystemExit("REFUSED: %s has no augur_strategies/ folder" % repo)


# ------------------------------------------------------------------------------------------------ read-only repo tools
_SECRET_PATH_RX = re.compile(
    r"(^|[\\/])\.env|secret|credential|passw|token|service_?account|api_?key|_keys?(\.|$|_)|\.key$|\.pem$|\.pfx$|"
    r"\.p12$|id_rsa|firebase uid|ntfy|webull_keys|alpaca_keys|(^|[\\/])\.git([\\/]|$)|optimizer_history\.db", re.I)
_READ_EXT = (".py", ".md", ".txt", ".json", ".csv", ".html", ".ini", ".toml", ".cfg", ".pine")


def _read_roots(lab=None):
    """Where Qwen may read: the shared checkout, and the lab's own plugin folder."""
    roots = [SHARED]
    if lab is not None:
        roots.append(lab.plugin_dir)
    return roots


def safe_repo_path(path, lab=None):
    """Resolve a Qwen-supplied path to a readable file under the shared checkout (or the lab's plugin folder).
    Raises ToolRefused on anything outside, any secret-looking path, folders and non-text types."""
    p = str(path or "").strip().strip('"').strip("'")
    if not p:
        raise ToolRefused("path is empty")
    if "\x00" in p:
        raise ToolRefused("path contains a NUL byte")
    roots = _read_roots(lab)
    if os.path.isabs(p):
        cands = [p]
    else:
        cands = [os.path.join(SHARED, p)]
        if lab is not None and p.replace("\\", "/").startswith("augur_strategies/qwen_lab/"):
            cands.insert(0, os.path.join(lab.plugin_repo, p))
    inside = False
    for c in cands:
        root = next((r for r in roots if under(c, r)), None)
        if root is None:
            continue
        inside = True
        rel = os.path.relpath(os.path.realpath(c), os.path.realpath(root))
        if _SECRET_PATH_RX.search(rel) or _SECRET_PATH_RX.search(os.path.basename(c)):
            raise ToolRefused("refused: %r looks like a secret / credential / git-internal path" % p)
        if os.path.isdir(c):
            raise ToolRefused("%r is a folder - list_strategies() lists plugins; name a file" % p)
        if os.path.isfile(c):
            if not c.lower().endswith(_READ_EXT):
                raise ToolRefused("refused: only text files (%s) can be read" % ", ".join(_READ_EXT))
            return os.path.realpath(c)
    if not inside:
        raise ToolRefused("refused: %r is outside the repo" % p)
    raise ToolRefused("not found under the repo: %r" % p)


def read_repo_file(path, start_line=1, lab=None, max_chars=READ_MAX_CHARS):
    real = safe_repo_path(path, lab)
    with open(real, "rb") as f:
        raw = f.read(2_000_000)
    if b"\x00" in raw[:8192]:
        raise ToolRefused("binary file")
    text = raw.decode("utf-8", "replace")
    lines = text.splitlines()
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import local_llm as _LL                                  # the house redaction (keys / tokens / passwords)
        lines, n_red = _LL.redact_lines(lines)
    except Exception:
        n_red = 0
    start = max(1, int(start_line or 1))
    out, size = [], 0
    for i in range(start - 1, len(lines)):
        ln = "%d: %s" % (i + 1, lines[i])
        if size + len(ln) + 1 > max_chars:
            out.append("...[cut: call again with start_line=%d]" % (i + 1))
            break
        out.append(ln)
        size += len(ln) + 1
    return {"path": os.path.relpath(real, SHARED) if under(real, SHARED) else real, "lines_total": len(lines),
            "redacted_lines": n_red, "text": "\n".join(out)}


_NAME_RX = re.compile(r"^\s*STRATEGY_NAME\s*=\s*['\"](.+?)['\"]", re.M)


def list_strategies(lab=None):
    """House plugins (shared checkout, top level) and the lab's own, by file name with STRATEGY_NAME (regex, no import)."""
    out = {"house": [], "qwen_lab": []}
    sd = os.path.join(SHARED, "augur_strategies")
    for fn in sorted(os.listdir(sd)):
        if fn.endswith(".py") and not fn.startswith("_"):
            out["house"].append(fn)
    if lab is not None and os.path.isdir(lab.plugin_dir):
        for fn in sorted(os.listdir(lab.plugin_dir)):
            if fn.endswith(".py") and not fn.startswith("_"):
                try:
                    m = _NAME_RX.search(open(os.path.join(lab.plugin_dir, fn), encoding="utf-8").read())
                except OSError:
                    m = None
                out["qwen_lab"].append(fn + (" - " + m.group(1) if m else ""))
    fams = {}
    for fn in out["house"]:
        fams.setdefault(re.split(r"[_.]", fn)[0], []).append(fn)
    return {"house_families": {k: len(v) for k, v in sorted(fams.items())},
            "house_files": " ".join(f[:-3] for f in out["house"]), "qwen_lab": out["qwen_lab"],
            "note": "read_repo_file('augur_strategies/<FILE>.py') to read one (small clean ones: ORB_FADE_1_0, "
                    "ONDRIFT_1_0, ORB_1_0)."}


# ---- the dead list (RESEARCH_LEDGER.md section 2 rows whose outcome is closed)
_DEAD_RX = re.compile(r"\bdead\b|\bclosed\b|close at draft|nothing clears|\b0 of \d+|\bfail(?:s|ed)?\b|not adopted|"
                      r"\bretracted\b|\bnulls?\b|no edge|\bkill(?:ed)?\b|\bdies\b|\bdied\b", re.I)


def parse_ledger_rows(text):
    rows = []
    for ln in text.splitlines():
        m = re.match(r"^\|\s*(2\.\d+[a-z]?)\s*\|(.*)\|\s*$", ln)
        if not m:
            continue
        parts = [x.strip() for x in m.group(2).split("|")]
        if len(parts) < 3:
            continue
        rows.append({"num": m.group(1), "tried": parts[0], "source": " | ".join(parts[1:-1]), "outcome": parts[-1]})
    return rows


def _ledger_text():
    with open(os.path.join(SHARED, LEDGER_REL), encoding="utf-8") as f:
        return f.read()


def dead_rows(text=None):
    rows = parse_ledger_rows(text if text is not None else _ledger_text())
    return [r for r in rows if _DEAD_RX.search(r["outcome"][:600])]


def _strip_md(s):
    return re.sub(r"[*`]|\[\[|\]\]", "", s)


def dead_list(query=None, text=None, limit_chars=9000):
    rows = dead_rows(text)
    if query:
        q = keywords(query)
        rows = [r for r in rows if keywords(r["tried"]) & q] or rows[:0]
    out = ["LAB %s -> CLOSED: %s" % (d["family"], d["why"]) for d in LAB_DEAD]
    size = sum(len(x) + 1 for x in out)
    for r in rows:
        verdict = re.search(r"\*\*([^*]{3,60})\*\*", r["outcome"])
        ln = "%s %s -> %s" % (r["num"], _strip_md(r["tried"])[:150], _strip_md(verdict.group(1) if verdict else
                                                                                  r["outcome"][:60]))
        if size + len(ln) > limit_chars:
            out.append("...[%d more rows; call dead_list(query=...) to filter]" % (len(rows) - len(out)))
            break
        out.append(ln)
        size += len(ln) + 1
    return {"rows": len(rows), "list": out}


# ---- the reading shelf (C:\EdgeLog\manager\papers\reading_shelf.html, the `const P=[...]` entries)
def _js_objects_to_json(js):
    """Quote the bare keys of a JS object-literal array so json can read it (strings / escapes respected)."""
    out, i, n, in_str, esc = [], 0, len(js), False, False
    while i < n:
        ch = js[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*(?=\s*:)", js[i:])
        if m and (not out or re.match(r"[\s{,]", out[-1] or " ")):
            out.append('"%s"' % m.group(0))
            i += len(m.group(0))
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def parse_shelf(html_text):
    m = re.search(r"const P\s*=\s*(\[.*?\n\]);", html_text, re.S)
    if not m:
        m = re.search(r"const P\s*=\s*(\[.*?\]);\s*const FIRST", html_text, re.S)
    if not m:
        raise ValueError("reading shelf: no `const P=[...]` array found")
    return json.loads(_js_objects_to_json(m.group(1)))


def _surnames(authors):
    out = []
    for a in str(authors or "").split(","):
        toks = [t for t in re.split(r"\s+", a.strip()) if t and not t.endswith(".") and t[:1].isalpha()]
        if toks:
            out.append(toks[-1])
    return out


def ledger_shelf_refs(text=None, papers=None):
    """Shelf papers a ledger row already works on -> {n: row number}: rows citing "reading shelf No. N", and rows
    citing the paper's first two authors together ("Kim-Tse-Wald 2016" took No. 7 into the KEEL decomposition)."""
    out = {}
    rows = parse_ledger_rows(text if text is not None else _ledger_text())
    for r in rows:
        for m in re.finditer(r"shelf\s+No\.?\s*(\d+)", r["tried"] + " " + r["outcome"], re.I):
            out.setdefault(int(m.group(1)), r["num"])
    for p in papers or []:
        sn = _surnames(p.get("a"))
        if not sn or int(p["n"]) in out:
            continue
        rx = re.compile(r"\b%s\b" % re.escape(sn[0]) + (r"[\s,&\-]+(?:and\s+)?%s\b" % re.escape(sn[1])
                                                      if len(sn) > 1 else r"\b[^|]{0,40}\b%s\b" % p.get("y")))
        for r in rows:
            if rx.search(r["tried"] + " " + r["outcome"]):
                out[int(p["n"])] = r["num"]
                break
    return out


def shelf_ideas(skip=(), shelf_path=None, ledger_text=None, include_taken=False):
    with open(shelf_path or SHELF_HTML, encoding="utf-8") as f:
        papers = parse_shelf(f.read())
    taken = ledger_shelf_refs(ledger_text, papers)
    out = []
    for p in papers:
        why = None
        if p.get("st") in ("live", "dead"):
            why = "marked %s on the shelf" % p.get("st")
        elif int(p["n"]) in set(int(x) for x in skip):
            why = "taken / done (skip list)"
        elif int(p["n"]) in taken:
            why = "already in the ledger (row %s)" % taken[int(p["n"])]
        if why and not include_taken:
            continue
        out.append({"n": p["n"], "title": p.get("t"), "authors": p.get("a"), "year": p.get("y"), "venue": p.get("v"),
                    "tag": p.get("tag"), "priority": p.get("p"), "summary": p.get("s"), "why_for_us": p.get("w"),
                    "repo_note": p.get("r"), **({"excluded": why} if why else {})})
    out.sort(key=lambda d: (d.get("priority") or 9, d["n"]))
    return out


def open_shelf_papers(lab, shelf_path=None):
    """The shelf papers the picker may take: opened by MANAGER (shelf-open) and not closed since (MANAGER #142). An
    explicit open overrides the skip list and the live / dead / ledger marks; a number not on the shelf is skipped."""
    nums = lab.open_shelf_numbers()
    if not nums:
        return []
    try:
        papers = shelf_ideas((), shelf_path=shelf_path, include_taken=True)
    except OSError:
        return []
    by_n = {int(p["n"]): p for p in papers}
    return [{k: v for k, v in by_n[n].items() if k != "excluded"} for n in nums if n in by_n]


# ---- dead-list check on a proposal
_STOP = set("""
a an the and or of to in on at by for with from as is are was were be been it its this that these those than then into
over under after before during per vs via not no nor but if when while which who what where how all any each every both
more most less least very also only just about above below between up down out off can could would should will may
might must do does did done has have had having trade trades trading traded leg legs nq es futures future emini e-mini
mini long short session sessions rth bar bars minute minutes min day days daily intraday price prices return returns
signal signals entry entries exit exits stop stops target targets rule rules hold holds holding position positions open
close closes opening closing high low highs lows strategy strategies test tested tests idea using use used based
first last next prior same one two three time times hour hours year years week weeks month months cost costs edge
market markets move moves moving index point points tick ticks level levels when then plugin house qwen lab proposal
""".split())


def keywords(text):
    t = str(text or "").lower()
    t = re.sub(r"(\d{1,2}):(\d{2})", r"t\1\2", t)                # 01:30 -> t0130
    words = re.findall(r"[a-z][a-z0-9\-]{2,}|t\d{3,4}", t)
    return {w.strip("-") for w in words if w.strip("-") not in _STOP and len(w.strip("-")) >= 3}


# families that are LIVE (in the book, or a lane's own name) - a closed ROUND of theirs does not close the name
LIVE_FAMILIES = {"NOISE", "ORB", "ENGU", "ENGUQ", "ENGUDQ", "TTM", "TTMSQZ", "SQUEEZE", "DIP", "NQDIP", "KEEL", "BOOK",
                 "ROUND", "FRONTIER", "MISC", "SCOPE", "QWEN", "TRADINGVIEW", "MANAGER", "STAGE", "MAP", "CHECK", "DRAFT",
                 "RESMOM", "GAMMA", "EVENT", "SLEEVE", "WEBULL", "PAPER", "LIVE", "TBIS", "TTIBS", "REPORT", "ONLY",
                 "OWNER", "ASK", "NEW", "FAMILY", "LANE", "QQQ", "ETF", "NQBRD", "TV", "ELWA", "CUSTOM", "ML"}


def dead_families(rows):
    """Names of CLOSED families: the leading upper-case token of a dead row ('XGAP r1', 'BVC QA r1', 'CALMTAPE ...')
    and any upper-case name the ledger calls dead ('= the dead ONDRIFT'), minus the live families."""
    out = {}
    for r in rows:
        t = _strip_md(r["tried"]).strip()
        m = re.match(r"([A-Z][A-Z0-9]{2,}(?:-[A-Z0-9]{2,})*)\b", t)
        if m:
            out.setdefault(m.group(1), r["num"])
        for m in re.finditer(r"\b(?:the )?dead ([A-Z][A-Z0-9]{3,})\b|\b([A-Z][A-Z0-9]{3,}) \(dead\)",
                             _strip_md(r["tried"] + " " + r["outcome"])):
            out.setdefault(m.group(1) or m.group(2), r["num"])
    return {k: v for k, v in out.items() if k not in LIVE_FAMILIES and k not in _NOT_FAMILIES and len(k) >= 4
            and not k.isdigit()}


_NOT_FAMILIES = {"LEDGER", "MAPCHECK", "OVERRIDE", "WIDE", "SCAN", "TEST", "STUDY"}


def _name_has_family(base, fam):
    return re.search(r"(^|_)%s(_|$)" % re.escape(fam.replace("-", "_")), base) is not None


def lab_dead_hit(name, hypothesis="", mechanism=""):
    """The LAB_DEAD family a proposal names (name, hypothesis or mechanism), else None."""
    txt = " %s " % re.sub(r"[\W_]+", " ", "%s %s %s" % (name, hypothesis, mechanism)).lower()
    for d in LAB_DEAD:
        if re.search(d["rx"], txt):
            return d
    return None


def dead_check(name, hypothesis, mechanism, rows=None):
    """Refuse a proposal that clearly matches a closed ledger row. Returns {refused, reason, nearest[]}.

    Two refusals: (1) the proposal's NAME reuses a closed family's name; (2) at least half of the proposal's content
    words (name + hypothesis + mechanism, stop words out, clock times kept) appear in one closed row's description,
    with at least five shared. Lexical, so it catches clear re-runs, not paraphrases - Qwen also gets dead_list()."""
    lab_hit = lab_dead_hit(name, hypothesis, mechanism)
    if lab_hit:
        return {"refused": True, "reason": "%s is closed for the lab: %s" % (lab_hit["family"], lab_hit["why"]),
                "nearest": []}
    rows = rows if rows is not None else dead_rows()
    idea_kw = keywords("%s %s %s" % (name, hypothesis, mechanism))
    base = re.sub(r"\W", "_", re.sub(r"^QL_", "", str(name or "").upper()))
    fams = dead_families(rows)
    scored = []
    for r in rows:
        rk = keywords(r["tried"][:700])
        shared = idea_kw & rk
        frac = len(shared) / max(1, len(idea_kw))
        scored.append((frac, len(shared), r, sorted(shared)))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    nearest = [{"row": s[2]["num"], "match": round(s[0], 2), "shared_words": s[3][:12],
                "tried": _strip_md(s[2]["tried"])[:180]} for s in scored[:3]]
    hit = sorted(f for f in fams if _name_has_family(base, f))
    if hit:
        return {"refused": True, "reason": "the name reuses a closed family's name %s (ledger row %s)"
                % (hit, fams[hit[0]]), "nearest": nearest}
    for frac, nshared, r, shared in scored:
        if frac >= 0.5 and nshared >= 5:
            return {"refused": True, "reason": "%.0f%% of the proposal's keywords match closed ledger row %s (%s)"
                    % (100 * frac, r["num"], ", ".join(shared[:10])), "nearest": nearest}
    return {"refused": False, "reason": "no clear match among %d closed rows" % len(rows), "nearest": nearest}


# ---- idea-level dedupe (MANAGER #148: QL_VWAPREVERT_NQ ran twice under one name with two plugins)
# A proposal is refused when (1) its normalised name is an idea the lab already ran (every source: plugin files are
# keyed by name), (2) its mechanism falls in the same mechanism FAMILY as an idea the lab already ran, or (3) its
# mechanism's content words overlap one run idea's (a near copy that names no family). A shelf paper the lab ran is
# closed by the shelf list; a NEW shelf paper whose mechanism repeats a run idea is refused here like any source.
# Families are read from the NAME (name_rx: patterns that are only safe in a file name, e.g. 'TOM', 'ORB'; rx too) and
# the MECHANISM (rx), each on its own (no pattern runs across the two) - never the hypothesis, where Qwen may name an
# idea it is contrasting with. Every pattern is a family-SPECIFIC phrase: 'momentum', 'breakout', 'VWAP', 'range',
# 'month' or 'first hour' alone match nothing, so the map cannot block every momentum, every breakout or every VWAP
# idea. A phrase in a FILTER / NEGATED clause ('No entries in the first hour', 'skip days where the first-hour range
# ...', 'do not trade on the last 2 days of the month', 'avoid fading') is a passing mention, not the rule
# (_family_hit); the VWAP revert-to patterns also ignore an EXIT clause ('exit when price reverts to VWAP' is how a
# VWAP-trend rule exits). tests/test_qwen_lab.py holds the positives (the lab's own real repeats) and the negatives.
_WORDNUM = r"(?:\d+|n|k|few|several|five|ten|fifteen|twenty|thirty|sixty|[a-z_]*bars?)"
_FIRST_WINDOW = (r"(?<!skip the )(?<!after the )(?<!ignore the )(?<!skipping the )(?<!excluding the )"
                 r"first[\s\-]+(?:half[\s\-]+(?:an[\s\-]+)?hour|hour|%s[\s\-]*(?:min(?:ute)?s?|bars?|candles?))"
                 % _WORDNUM)
_OPEN_CLOCK = r"0?9:30\s*(?:-|\u2013|to|until|through)\s*(?:0?9:[3-5]\d|1[0-2]:\d\d)"   # '09:30-10:30'
_EARLY = r"(?:(?:opening|morning|initial|early)\s+)?"
# a break OF a range: 'breaks above the range', 'close > range high', 'above the OR high' (a bare 'or' is English)
_RANGE_BREAK = (r"(?:\bbreak\w*\s+(?:out\s+)?(?:above|below|through|of|out\s+of)?\s*(?:the\s+|its\s+|that\s+|this\s+)?"
                + _EARLY + r"(?:range|ib|box|or[\s_\-]*(?:high|low|hi|lo))\b"
                r"|(?:>|<|\babove|\bbelow|\bthrough|\bpast|\bbeyond|\bover|\bunder)\s*(?:the\s+|its\s+|that\s+)?"
                + _EARLY + r"(?:range|or|ib|box)(?:['\u2019]s)?[\s_\-]*(?:high|low|hi|lo|top|bottom)s?\b)")
# a range DEFINED over the session's opening window: 'opening range', 'initial balance', 'first-hour range', 'first 12
# bars (24 min) form a range', 'the high and low of the first 30 minutes' ('the first 6 bars are warm-up' is not one)
_OR_DEF = (r"(?:opening[\s\-]*range|initial[\s\-]*balance|morning[\s\-]*range"
           r"|opening\s+%(wn)s[\s\-]*(?:min(?:ute)?s?|bars?)[\s\-]+range"
           r"|%(fw)s(?:['\u2019]s?)?[\s\-]+(?:range|box|high[\s\-]*(?:/|and|-)[\s\-]*low|extremes?)\b"
           r"|%(fw)s\s*(?:\([^)]{0,40}\)\s*)?(?:forms?|defines?|sets?|makes?|builds?|is|are)\s+(?:a|the|its|our)\s+"
           r"(?:\w+\s+)?(?:range|box)\b"
           r"|(?:range|box|high(?:\s+and\s+|\s*/\s*)low)\s+(?:=|is|of|over|from|across|for|during)\s+(?:the\s+)?%(fw)s)"
           % {"wn": _WORDNUM, "fw": _FIRST_WINDOW})
_MORNING_WIN = r"(?:%s|morning|opening|%s)" % (_FIRST_WINDOW, _OPEN_CLOCK)
_NUM = r"\+?\d[\d.,]*%?"
# an entry IN THE SIGN of the morning quantity: '> 0, go long', 'larger than 0.5% buy', '< 0 ... short' (a fade - the
# morning move up, then a SHORT - is a different idea and does not match)
_SAME_SIGN_ENTRY = (r"(?:(?:>\s*\+?0(?![\d.])|\bpositive\b|\b(?:larger|greater|bigger|more|higher)\s+than\s+%(n)s|"
                    r"\bexceeds?\s+%(n)s|\babove\s+%(n)s)[^;]{0,40}?\b(?:go(?:es)?\s+long|buy|long)\b"
                    r"|(?:<\s*-?\s*0(?![\d.])|\bnegative\b|\b(?:smaller|less|lower)\s+than\s+-\s*%(n)s|"
                    r"\bbelow\s+-\s*%(n)s)[^;]{0,40}?\b(?:go(?:es)?\s+short|sell|short)\b)" % {"n": _NUM})
# VWAP deviation as a number: '(close - VWAP)/ATR', 'z-score of close vs VWAP', 'distance from VWAP'
_VWAP_DEV = (r"(?:(?:close|price)(?:\[\w*\])?\s*-\s*(?:the\s+)?(?:session\s+)?vwap|vwap[\s\-]*(?:deviation|distance|"
             r"z[\s\-]*score|spread)|(?:deviation|distance|z[\s\-]*score|spread|stretch)\s+(?:of\s+(?:the\s+)?"
             r"(?:close|price)\s+)?(?:from|to|vs\.?|versus|over|above|below)\s+(?:the\s+)?(?:session\s+)?vwap)")
# ... then a CONTRARIAN entry on it: '> 2.5 short', '< -2 buy'
_CONTRA_ENTRY = (r"(?:(?:>|\babove|\bexceeds?|\bover)\s*%(n)s[^;]{0,25}?\b(?:short|sell)\b"
                 r"|(?:<|\bbelow|\bunder)\s*-\s*%(n)s[^;]{0,25}?\b(?:long|buy)\b)" % {"n": _NUM})
_IN_CLAUSE = r"(?:[^.;]|\.(?=\d)){0,80}?"                         # up to 80 chars, not past a sentence end
IDEA_FAMILIES = [
    {"family": "VWAP_REVERSION", "label": "fade a stretch away from VWAP / mean-revert to VWAP",
     "name_rx": [r"vwap\s*(?:rev\w*|fade\w*|snap\w*|mr\b|mean\w*)|(?:rev\w*|fade\w*|snap\w*)\s*vwap"],
     "rx": [r"vwap[\s\-]*(?:revert\w*|reversion|fade\w*|snap[\s\-]*back|mean[\s\-]*rever\w*)",
            (r"(?:revert\w*|reversion|fad(?:e|es|ing)|snap(?:s|ping)?[\s\-]*back|mean[\s\-]*rever\w*)\s+(?:\w+\s+){0,3}?"
             r"(?:to|toward|towards|into)\s+(?:the\s+)?(?:session(?:['\u2019]s)?\s+|intraday\s+|daily\s+|anchored\s+)?"
             r"vwap\b", {"exit_ctx": True}),
            r"(?:target|take[\s\-]*profit|objective)\w*\s*(?:\w+\s+){0,2}?(?:at|to|=|:|is)\s*(?:the\s+)?"
            r"(?:session(?:['\u2019]s)?\s+|intraday\s+)?vwap\b",
            (r"vwap\b" + _IN_CLAUSE + r"(?:mean[\s\-]*rever\w*|reversion|\bfad(?:e|es|ed|ing)\b)", {"exit_ctx": True}),
            (r"(?:mean[\s\-]*rever\w*|reversion|\bfad(?:e|es|ed|ing)\b)" + _IN_CLAUSE + r"\bvwap", {"exit_ctx": True}),
            # the band fade without the word: 'close > VWAP + 2.5*ATR, enter SHORT' (QL_VWAPREVERT_NQ's own rule)
            r"(?:>|\babove|\bover|\bexceeds?)\s*(?:the\s+)?(?:session(?:['\u2019]s)?\s+)?vwap\s*\+[^,;]{0,30}?,?\s*"
            r"(?:then\s+)?(?:(?:enter|go)\s+short|sell\b)",
            r"(?:<|\bbelow|\bunder)\s*(?:the\s+)?(?:session(?:['\u2019]s)?\s+)?vwap\s*-[^,;]{0,30}?,?\s*"
            r"(?:then\s+)?(?:(?:enter|go)\s+long|buy\b)",
            # the same fade on a VWAP-deviation number: 'd = (close - VWAP)/ATR20; d > 2.5 short, d < -2.5 long'
            _VWAP_DEV + r".{0,200}?" + _CONTRA_ENTRY]},
    {"family": "OPENING_RANGE", "label": "opening-range / morning-range breakout, morning momentum continuation",
     "name_rx": [r"\borb\b|\bor\s*break\w*|\bib\s*break\w*|opening\s*range|morning\s*(?:mom\w*|break\w*|range)"],
     "rx": [r"opening[\s\-]*range[\s\-]*break\w*|initial[\s\-]*balance[\s\-]*(?:break\w*|extension)",
            # a range DEFINED over the session's opening window, then a break of THAT range
            _OR_DEF + r".{0,300}?" + _RANGE_BREAK,
            # a break whose object is the opening range itself: 'breaks above the opening range high'
            r"(?:\bbreak\w*\s+(?:out\s+)?(?:above|below|through|of|out\s+of)?\s*|(?:>|<|\babove|\bbelow|\bthrough|"
            r"\bpast|\bbeyond)\s*)(?:the\s+|its\s+|today['\u2019]s\s+)?(?:opening[\s\-]*range|initial[\s\-]*balance|"
            r"morning[\s\-]*range)",
            # a break of the opening window's own extreme: 'a close above the first 30-minute high'
            r"(?:>|<|\babove|\bbelow|\bthrough|\bpast|\bbeyond|\bbreak\w*(?:\s+(?:out\s+)?(?:above|below|through|of))?)"
            r"\s*(?:the\s+)?(?:%s|opening[\s\-]+%s[\s\-]*(?:min(?:ute)?s?|bars?))(?:['\u2019]s?)?[\s\-]+"
            r"(?:range[\s\-]+)?(?:high|low|hi|lo|extreme)s?\b" % (_FIRST_WINDOW, _WORDNUM),
            # morning momentum CONTINUATION: trade in the direction / sign of the morning / opening / first-window move
            # ('with the opening GAP direction' is a gap idea, not this one)
            r"(?:in\s+the\s+(?:same\s+)?(?:direction|sign)\s+of|\bwith|\bfollow(?:s|ing)?|\bcontinu\w*(?:\s+of)?)\s+"
            r"(?:the\s+)?(?:morning|opening|%s(?:['\u2019]s?)?|%s)(?:[\s\-]+(?!gap\b)\w+){0,2}?[\s\-]+(?:move|direction|"
            r"trend|momentum|drive|return|displacement)\b" % (_FIRST_WINDOW, _OPEN_CLOCK),
            r"morning[\s\-]+momentum",
            r"%s(?:['\u2019]s?)?\s+(?:(?!gap\b)\w+\s+){0,2}?(?:return|move|momentum|displacement|change)\b.{0,160}?"
            r"(?:predict\w*|continu\w*|persist\w*|same\s+direction|(?:direction|sign)\s+of)" % _MORNING_WIN,
            # the morning quantity, then an entry in ITS sign (QL_TRENDN: 'the first-hour close displacement (close[11]
            # - open[0]) ... displacement > 0, go long'; '09:30-10:30 return is larger than 0.5% buy')
            r"%s(?:['\u2019]s?)?[\s\-]+(?:close[\s\-]+)?(?:displacement|return|move|change|drift)\b.{0,200}?%s"
            % (_MORNING_WIN, _SAME_SIGN_ENTRY)]},
    {"family": "OPEN_DRIVE", "label": "open drive / momentum drive from the open",
     "name_rx": [r"open\s*drive|\bmom\w*\s*drive"],
     "rx": [r"open(?:ing)?[\s\-]*drive|\bmom(?:entum)?[\s\-]*drive|drive[\s\-]+(?:from|off)[\s\-]+the[\s\-]+open"]},
    {"family": "GAMMA", "label": "gamma exposure / GEX / dealer gamma (closed for the lab, MANAGER #142)",
     "name_rx": [], "rx": [LAB_DEAD[0]["rx"]]},
    {"family": "TURN_OF_MONTH", "label": "turn-of-the-month / month-end calendar",
     "name_rx": [r"\btom\b(?![\s_]*demark)|turn\s*of\s*(?:the\s*)?month|month\s*(?:end|start|turn)"],
     "rx": [r"turn[\s\-]*of[\s\-]*(?:the[\s\-]*)?month|\bmonth[\s\-]*(?:end|start)\b",
            r"\b(?:end|start)[\s\-]+of[\s\-]+(?:the[\s\-]+|each[\s\-]+|every[\s\-]+|a[\s\-]+)?(?:calendar[\s\-]+)?"
            r"month\b",
            r"\b(?:last|first)[\s\-]+(?:(?:\d+|one|two|three|four|five)[\s\-]+)?(?:trading[\s\-]+)?(?:days?|sessions?)"
            r"[\s\-]+(?:of|in)[\s\-]+(?:the|each|every|a)[\s\-]+(?:new[\s\-]+)?(?:calendar[\s\-]+)?month\b"]},
]
# generic fallback: Jaccard of the SIGNAL / ENTRY clauses' content words (signal_text - the stop / exit / target /
# trailing clauses out - keywords() minus rule boilerplate), >= 0.45 with >= 6 shared words. Re-calibrated 10-16 on
# the lab's 11 real proposals: distinct pairs top out at 0.17 (QL_GAMMA_MOM vs QL_MOMDRIVE); a copy with a reworded
# parameter is 1.0 (QL_TPT_NQ, 9 shared words); the lab's real REWORDED repeat (QL_TRENDN of QL_ES_MOMBREAK) shares
# only 3 signal words (0.27) - the OPENING_RANGE family catches it, a word count cannot; a new signal that re-uses a run
# idea's stop sentence (an inside-bar breakout with QL_MOMDRIVE's chandelier stop: 0.69 on the whole text) is 0.25 with
# 2 shared words once the risk clauses are out
DEDUPE_JACCARD, DEDUPE_MIN_SHARED = 0.45, 6
_DEDUPE_BOILERPLATE = set("""
compute computed enter entered flat books book gap-through intrabar whose max min away favor favour hit proxy since
t0930-t1600 t0930 t1600 regular-hours regular contract contracts one per checked check fill fills filled bar's
session's default otherwise else either above below greater less equal than wins win loss losses side sides
chandelier chandelier-style highest lowest longs shorts plus minus trailing trail breakeven ratchet ratchets
""".split())
RAN_LIST_MAX = 25                                                # run ideas LISTED to Qwen (~300 chars each)


def norm_idea_name(name):
    """'QL_VWAPREVERT_NQ' -> 'VWAPREVERT': QL_ prefix, instrument / timeframe / version tokens and underscores out -
    also as a token's SUFFIX ('NOISE2M' -> 'NOISE', 'TRENDV2' -> 'TREND', 'VWAPNQ' -> 'VWAP'), so 'QL_NOISE2M_TREND'
    and 'QL_NOISE_2M_TREND' are one name."""
    toks = [t for t in re.split(r"[\W_]+", str(name or "").upper()) if t]
    if toks and toks[0] == "QL":
        toks = toks[1:]
    keep = [re.sub(r"(?<=[A-Z])(?:\d+M|V\d+|M?NQ)$", "", t) for t in toks if t not in ("NQ", "ES", "MNQ", "MES", "RTH")
            and not re.fullmatch(r"V\d+|R\d+|\d+|\d+M", t)]
    return "".join(keep) or "".join(toks)


def _name_text(name):
    """'QL_VWAPREVERT_NQ' -> 'vwaprevert nq' (the QL_ prefix out, underscores to spaces)."""
    return re.sub(r"[_\W]+", " ", re.sub(r"(?i)^ql_", "", str(name or ""))).lower().strip()


# a FILTER / NEGATED clause around a family phrase: 'No entries in the first hour', 'skip days where ...', 'do not
# trade on the last 2 days of the month', 'avoid fading', 'the first 6 bars are warm-up'
_NEG_CTX_RX = re.compile(r"\b(?:not|never|avoid\w*|skip\w*|ignor\w*|exclud\w*|except|unless|without|don\W?t|"
                         r"warm[\s\-]*up|no\s+(?:new\s+)?(?:entr\w*|trad\w*|signals?|positions?|longs?|shorts?))\b")
# an EXIT clause: 'exit when price reverts to VWAP' is how a VWAP-trend rule exits, not a VWAP fade
_EXIT_CTX_RX = re.compile(r"\b(?:exit\w*|stop\w*|cover\w*|flat|liquidat\w*)\b")
_CLAUSE_END_RX = re.compile(r"[;:!?\n,()]|\.(?!\d)")


def _context_before(text, pos, words=6):
    """The last `words` words of the clause before `pos` (a match's own clause: 'No entries in the first hour.' does
    not reach into the next sentence; a decimal point is not a clause end)."""
    head = text[:pos]
    cut = 0
    for m in _CLAUSE_END_RX.finditer(head):
        cut = m.end()
    return " ".join(head[cut:].split()[-words:])


def _family_hit(rx, text, exit_ctx=False):
    """The first match of `rx` in `text` that is not a passing mention - no negation / filter word in the clause before
    it (and with exit_ctx, no exit / stop word either). Every start position is tried, so a rejected match never hides
    a later real one."""
    p = re.compile(rx, re.S)
    pos = 0
    while pos <= len(text):
        m = p.search(text, pos)
        if not m:
            return None
        ctx = _context_before(text, m.start())
        if not _NEG_CTX_RX.search(ctx) and not (exit_ctx and _EXIT_CTX_RX.search(ctx)):
            return m
        pos = m.start() + 1
    return None


def idea_families(name, mechanism):
    """{family: the phrase that put the idea in it} - the name (name_rx, rx) and the mechanism (rx), each on its own,
    never the hypothesis (see IDEA_FAMILIES)."""
    nm = _name_text(name)
    mech = re.sub(r"\s+", " ", str(mechanism or "")).lower()
    out = {}
    for fam in IDEA_FAMILIES:
        hit = next((m for m in (re.search(rx, nm) for rx in fam.get("name_rx") or []) if m), None)
        for item in ([] if hit else fam["rx"]):
            rx, opts = item if isinstance(item, tuple) else (item, {})
            hit = _family_hit(rx, nm, **opts) or _family_hit(rx, mech, **opts)
            if hit:
                break
        if hit:
            out[fam["family"]] = hit.group(0)[:80]
    return out


# the near-copy overlap reads the SIGNAL and ENTRY only: a stop / exit / target / trailing / one-trade clause is the
# risk boilerplate Qwen re-uses from earlier lab proposals (an inside-bar breakout that copies QL_MOMDRIVE's chandelier
# stop sentence is a new signal)
_RISK_CLAUSE_RX = re.compile(r"^\W*(?:stop\w*|exits?\b|exiting|target\w*|take[\s\-]*profits?|trail\w*|risk\w*|flat\b|"
                             r"cover\w*|one\s+trade|max(?:imum)?\s+one|time[\s\-]*stops?|after\s+(?:the\s+)?(?:entry|"
                             r"fill)|then\s+(?:exit|flat))", re.I)


def _clauses(text):
    """The sentences / ';' parts of a rule, split OUTSIDE parentheses (a decimal point is not a sentence end)."""
    s = str(text or "")
    out, cur, depth = [], [], 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        cur.append(ch)
        if depth == 0 and (ch in ";\n" or (ch == "." and (i + 1 >= len(s) or s[i + 1].isspace()))):
            out.append("".join(cur).strip())
            cur = []
    out.append("".join(cur).strip())
    return [c for c in out if c]


def signal_text(mechanism):
    """The mechanism without its risk clauses (stop, exit, target, trailing, flat, one trade a session)."""
    keep = [c for c in _clauses(mechanism) if not _RISK_CLAUSE_RX.match(c)]
    return " ".join(keep) if keep else str(mechanism or "")


def _mech_words(mechanism):
    return {w for w in keywords(signal_text(mechanism)) if w not in _DEDUPE_BOILERPLATE}


def _one_line(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " ..."


# outcomes that are NOT a verdict on the idea (MANAGER #139: a broken plugin is a bug; an operator abort tested nothing;
# MANAGER #158/#162: a duplicate closed on resume never ran): such a run still blocks its NAME (plugin files are keyed by
# name) but not its mechanism family / rule
_NOT_A_VERDICT_RX = re.compile(r"^\s*(?:BROKEN PLUGIN|ABORTED|CLOSED AS DUPLICATE)\b", re.I)
_DUPLICATE_RX = re.compile(r"^\s*CLOSED AS DUPLICATE\b", re.I)
_SANE_STAGE_RX = re.compile(r"^\s*(?:PRE-WF DONE|STAGE A DONE)\b")     # outcomes reached through a sane PRE-WF run


def norm_rule(text):
    """A rule's text with case, punctuation and spacing normalised - the 'same rule' test (MANAGER #158/#162)."""
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def idea_ran_shas(idea):
    """LF sha256 of every plugin an idea RAN through a Stage A: the prereg's plugin (and the plugins its addenda
    replaced) once the prereg was posted or a stage ran, and every broken-plugin attempt's plugin."""
    idea = idea or {}
    pre = idea.get("prereg") or {}
    out = []
    if pre.get("posted_id") or idea.get("stage_pre_wf") or idea.get("stage_a") or idea.get("sanity"):
        out += [h.get("plugin_sha") for h in pre.get("history") or []] + [pre.get("plugin_sha")]
    out += [a.get("plugin_sha") for a in idea.get("sanity") or []]
    return [s for i, s in enumerate(out) if s and s not in out[:i]]


def ran_ideas(lab, exclude=None):
    """Every idea the lab has already RUN (state.json done_ideas + aborted_ideas, read from their idea folders, plus any
    CLOSED idea folder that state.json never recorded - a run killed between the close and its bookkeeping), one entry
    per normalised name, oldest first: name, source, runs, one-line mechanism, verdict, families, the shelf papers it
    came from, and retry_ok (every run was a BROKEN PLUGIN or an abort - not a verdict). An idea with no accepted
    proposal (aborted before it proposed) is not an idea yet and is left out. ALL of them are checked by propose();
    only the latest RAN_LIST_MAX are listed to Qwen. Read only - no folder is created."""
    out, by = [], {}
    st = lab.state or {}
    recs = [dict(r or {}) for r in list(st.get("done_ideas") or []) + list(st.get("aborted_ideas") or [])]
    seen = {str(r.get("id")) for r in recs}
    try:
        folders = sorted(d for d in os.listdir(os.path.join(lab.home, "ideas")) if d not in seen)
    except OSError:
        folders = []
    recs += [{"id": d, "_folder": True} for d in folders]
    for rec in recs:
        iid = rec.get("id")
        if not iid or iid == exclude:
            continue
        idea = jload(os.path.join(lab.home, "ideas", str(iid), "idea.json"), None) or {}
        if rec.get("_folder") and idea.get("status") != "closed":
            continue                                             # the idea in flight (or an empty folder)
        pr = idea.get("proposal") or {}
        name = pr.get("name")
        if not name:
            continue
        outcome = str(rec.get("outcome") or idea.get("outcome") or "-")
        if _DUPLICATE_RX.match(outcome):
            continue                       # MANAGER #158/#162: closed as a duplicate on resume - it never ran
        key = norm_idea_name(name)
        verdict = _one_line(outcome, 110)
        is_verdict = not _NOT_A_VERDICT_RX.match(outcome)
        shelf_n = idea.get("shelf_n") if idea.get("shelf_n") is not None else rec.get("shelf_n")
        shas = idea_ran_shas(idea)
        rule = norm_rule(pr.get("mechanism"))
        if key in by:
            e = by[key]
            e["runs"] += 1
            e["ids"].append(iid)
            if is_verdict or not e["verdict_runs"]:
                e["verdict"] = verdict                           # the latest verdict (a later non-verdict run keeps it)
            e["verdict_runs"] += int(is_verdict)
            e["retry_ok"] = e["verdict_runs"] == 0
            e["families"] = sorted(set(e["families"]) | set(idea_families(name, pr.get("mechanism"))))
            if shelf_n is not None and int(shelf_n) not in e["shelf_ns"]:
                e["shelf_ns"].append(int(shelf_n))
            if str(pr.get("mechanism") or "") not in e["_mechs"]:
                e["_mechs"].append(str(pr.get("mechanism") or ""))
        else:
            e = {"name": name, "norm": key, "source": idea.get("source") or rec.get("source") or "shelf", "runs": 1,
                 "ids": [iid], "mechanism": _one_line(pr.get("mechanism"), 170), "verdict": verdict,
                 "families": sorted(idea_families(name, pr.get("mechanism"))),
                 "_mechs": [str(pr.get("mechanism") or "")], "verdict_runs": int(is_verdict), "retry_ok": not is_verdict,
                 "shelf_ns": [int(shelf_n)] if shelf_n is not None else [], "plugin_shas": {}, "_rules": {}}
            by[key] = e
            out.append(e)
        for s in shas:                                            # MANAGER #158/#162: every plugin a run idea ran
            e["plugin_shas"].setdefault(s, iid)
        if rule and is_verdict:
            e["_rules"].setdefault(rule, iid)
    return out


def plugin_sha_ran_elsewhere(lab, sha, exclude=None, ran=None):
    """{idea, name, verdict} of a run idea (not `exclude`) that already ran a plugin with this LF sha256, else None
    (MANAGER #158/#162: the same plugin never runs twice)."""
    if not sha:
        return None
    for r in (ran if ran is not None else ran_ideas(lab, exclude=exclude)):
        if sha in (r.get("plugin_shas") or {}):
            return {"idea": r["plugin_shas"][sha], "name": r["name"], "verdict": r["verdict"]}
    return None


def resume_duplicate(lab, idea):
    """MANAGER #158/#162 (QL_TRENDN 13:42 / 14:02 ran one plugin twice): an OPEN idea that is resumed is a duplicate
    when its plugin (any sha it wrote, gated or ran) is one a run idea already ran, when its rule text is a run idea's
    (normalised; a run that was a verdict), or when its proposal's normalised name is taken (MANAGER #148 - the name
    keys the plugin file). Returns {of, name, why, sha?} or None."""
    ran = ran_ideas(lab, exclude=idea.get("id"))
    pl = idea.get("plugin") or {}
    shas = [s for s in [pl.get("sha"), pl.get("gates_sha")] + idea_ran_shas(idea) if s]
    for s in shas:
        hit = plugin_sha_ran_elsewhere(lab, s, ran=ran)
        if hit:
            return {"of": hit["idea"], "name": hit["name"], "verdict": hit["verdict"], "why": "same plugin sha",
                    "sha": s}
    pr = idea.get("proposal") or {}
    if not pr.get("name"):
        return None
    rule = norm_rule(pr.get("mechanism"))
    for r in ran:
        if rule and rule in (r.get("_rules") or {}):
            return {"of": r["_rules"][rule], "name": r["name"], "verdict": r["verdict"], "why": "same rule"}
    key = norm_idea_name(pr["name"])
    for r in ran:
        if r["norm"] == key:
            return {"of": r["ids"][-1], "name": r["name"], "verdict": r["verdict"], "why": "same name"}
    return None


def families_taken(ran):
    """The mechanism families of the run ideas that got a verdict (a BROKEN PLUGIN / aborted run leaves its family
    open to a retry under a new name)."""
    return sorted({f for r in ran or [] if not r.get("retry_ok") for f in r["families"]})


def ran_ideas_brief(ran, limit=RAN_LIST_MAX):
    """One line per run idea, for Qwen (name, families, source, runs, mechanism, verdict) - the latest `limit`, with a
    count of the older ones (propose() checks every one)."""
    shown = list(ran or [])[-limit:] if limit else list(ran or [])
    out = ["%s%s (%s%s): %s -> %s%s" % (r["name"], (" [%s]" % ", ".join(r["families"])) if r["families"] else "",
                                        r["source"], (", ran %dx" % r["runs"]) if r["runs"] > 1 else "",
                                        r["mechanism"], r["verdict"],
                                        " (NOT a verdict on the idea: its mechanism may be retried under a NEW name)"
                                        if r.get("retry_ok") else "") for r in shown]
    if len(ran or []) > len(shown):
        out.append("... and %d older ideas (not listed; propose() checks them too)" % (len(ran) - len(shown)))
    return out


def family_map_brief():
    return {f["family"]: f["label"] for f in IDEA_FAMILIES}


def dedupe_check(name, mechanism, ran, reopened_shelf=None):
    """MANAGER #148: refuse a proposal that repeats an idea the lab already ran - same normalised name, same mechanism
    family, or a near copy of a run idea's signal / entry rule (word overlap). The NAME check covers every run idea;
    the family and overlap checks skip a run that was no verdict (BROKEN PLUGIN / aborted - MANAGER #139) and, for a
    session on a shelf paper MANAGER RE-OPENED after the lab ran it (`reopened_shelf`), that paper's own earlier runs.
    Returns {refused, reason, matches[], families, retry_allowed[]}."""
    key = norm_idea_name(name)
    fams = idea_families(name, mechanism)
    words = _mech_words(mechanism)
    rule = norm_rule(mechanism)
    matches, retry = [], []
    for r in ran or []:
        if r["norm"] == key:
            matches.append({"why": "name", "idea": r["name"], "verdict": r["verdict"],
                            "detail": "normalised name %s" % key})
            continue
        if r.get("retry_ok") or (reopened_shelf is not None and int(reopened_shelf) in (r.get("shelf_ns") or [])):
            retry.append(r["name"])
            continue
        if rule and rule in (r.get("_rules") or {}):             # MANAGER #158/#162: the same rule text
            matches.append({"why": "rule", "idea": r["name"], "verdict": r["verdict"],
                            "detail": "the same rule text (case / punctuation / spacing aside) as idea %s"
                                      % r["_rules"][rule]})
            continue
        common = sorted(set(fams) & set(r["families"]))
        if common:
            f = common[0]
            matches.append({"why": "family", "idea": r["name"], "verdict": r["verdict"], "family": f,
                            "detail": "mechanism family %s (%s) - your text matched %r"
                                      % (f, family_map_brief()[f], fams[f])})
            continue
        best = (0.0, set())
        for mech_r in r.get("_mechs") or [r.get("mechanism")]:            # every plugin the name ran with
            rw = _mech_words(mech_r)
            shared = words & rw
            jac = len(shared) / max(1, len(words | rw))
            if (jac, len(shared)) > (best[0], len(best[1])):
                best = (jac, shared)
        jac, shared = best
        if jac >= DEDUPE_JACCARD and len(shared) >= DEDUPE_MIN_SHARED:
            matches.append({"why": "overlap", "idea": r["name"], "verdict": r["verdict"],
                            "detail": "%.0f%% word overlap with its mechanism (%s)"
                                      % (100 * jac, ", ".join(sorted(shared)[:10]))})
    if not matches:
        return {"refused": False, "families": sorted(fams), "matches": [], "retry_allowed": retry,
                "reason": "not a repeat of the %d idea%s the lab already ran%s"
                          % (len(ran or []), "" if len(ran or []) == 1 else "s",
                             (" (mechanism retry allowed after %s: no verdict, or a shelf paper MANAGER re-opened)"
                              % ", ".join(retry)) if retry else "")}
    m = matches[0]
    reason = ("the lab already ran %s (%s) - %s" % (m["idea"], m["verdict"], m["detail"]) if m["why"] != "name" else
              "the lab already ran an idea named %s (%s) - a repeat under the same name is refused" % (m["idea"],
                                                                                                    m["verdict"]))
    return {"refused": True, "reason": reason, "matches": matches[:5], "families": sorted(fams),
            "retry_allowed": retry}


# ---- the bar-index convention (TTM #145) and the first-signal-bar contract (TTM #144)
# ONE way to name a bar everywhere (prompt, proposal, prereg, contract check): the 0-based IN-SESSION index k (bar 0 =
# the first regular-hours bar, 09:30 open) WITH the clock time of that bar's OPEN - 'bar 12 (10:30 open)' on 5m bars.
# Bar k's close is bar k+1's open time. An entry is said to fill at a bar's OPEN or at its CLOSE.
RTH_OPEN_MIN, RTH_MINUTES = 9 * 60 + 30, 390


def tf_minutes(tf):
    m = re.fullmatch(r"(\d+)m", str(tf or "").strip())
    if not m:
        raise ValueError("timeframe %r is not '<n>m'" % (tf,))
    return int(m.group(1))


def bars_per_session(tf):
    return RTH_MINUTES // tf_minutes(tf)


def bar_clock(index, tf):
    """'HH:MM' - the clock time of in-session bar `index`'s OPEN (09:30 + index x bar minutes)."""
    return "%02d:%02d" % divmod(RTH_OPEN_MIN + int(index) * tf_minutes(tf), 60)


def bar_label(index, tf):
    """'bar 12 (10:30 open)' - the house way to name a bar (TTM #145)."""
    return "bar %d (%s open)" % (int(index), bar_clock(index, tf))


def parse_first_signal_bar(value, tf):
    """The proposal's first_signal_bar -> {index, clock, label}: the 0-based in-session index of the EARLIEST bar on
    which an entry may FILL, with the clock time of that bar's open. Accepts {"index": 12, "clock": "10:30"}, its JSON
    text, or '12 (10:30)'. The clock must be the index's own open time - one convention (TTM #145). Raises
    ToolRefused."""
    ex = "e.g. {\"index\": 12, \"clock\": \"%s\"} = %s on %s bars" % (bar_clock(12, tf), bar_label(12, tf), tf)
    v = value
    if isinstance(v, str):
        s = v.strip()
        try:
            v = json.loads(s)
        except ValueError:
            m = re.match(r"^\s*(?:bar\s*)?(\d+)\D+?(\d{1,2}:\d{2})", s, re.I)
            v = {"index": int(m.group(1)), "clock": m.group(2)} if m else None
    if isinstance(v, (list, tuple)) and len(v) == 2:
        v = {"index": v[0], "clock": v[1]}
    if not isinstance(v, dict):
        raise ToolRefused("first_signal_bar is required: the 0-based in-session index of the EARLIEST bar on which an "
                          "entry may fill, with the clock time of that bar's open (%s). The harness checks that no "
                          "entry fills before it (TTM #144)" % ex)
    try:
        idx = int(v.get("index"))
        if float(v.get("index")) != idx:
            raise ValueError
    except (TypeError, ValueError):
        raise ToolRefused("first_signal_bar.index must be a whole number (0-based in-session bar index; %s)" % ex)
    nb = bars_per_session(tf)
    if not (0 <= idx < nb):
        raise ToolRefused("first_signal_bar.index %s is outside the session: %s bars run 0..%d (09:30..%s open)"
                          % (idx, tf, nb - 1, bar_clock(nb - 1, tf)))
    m = re.search(r"(\d{1,2}):(\d{2})", str(v.get("clock") or ""))
    want = bar_clock(idx, tf)
    if not m:
        raise ToolRefused("first_signal_bar.clock is required: the clock time of bar %d's OPEN (%s on %s bars) - bars "
                          "are named one way, 'bar k (HH:MM open)' (TTM #145)" % (idx, want, tf))
    got = "%02d:%02d" % (int(m.group(1)), int(m.group(2)))
    if got != want:
        raise ToolRefused("first_signal_bar {index %d, clock %s} disagree: on %s bars, bar %d OPENS at %s (bar 0 = the "
                          "09:30 open; bar k's close is bar k+1's open). Give the index and the open time of the SAME "
                          "bar - the earliest bar on which an entry may fill (TTM #144/#145)"
                          % (idx, got, tf, idx, want))
    return {"index": idx, "clock": want, "label": bar_label(idx, tf), "timeframe": tf}


# MANAGER #160b / #162: the proposal states WHERE its entry fills - a bar's OPEN, its CLOSE, or a stop / limit LEVEL
# inside it - and, for a fixed-time entry, WHICH in-session bar; and its time stop in the one bar-count convention:
# 'a time stop of N bars' = exit at the CLOSE of entry bar + N (exit_bar - entry_bar = N). The contract smoke checks
# every entry and every time-stop exit against them.
ENTRY_FILL_AT = {"open": "open", "close": "close", "level": "level", "stop": "level", "limit": "level",
                 "intrabar": "level"}


def entry_fill_label(ef):
    """'the OPEN of bar 13 (10:35 open) - every entry' / 'the OPEN of the fill bar (the bar varies with the signal)'."""
    if not ef or not ef.get("at"):
        return "not stated"
    where = {"open": "the OPEN of", "close": "the CLOSE of", "level": "a stop / limit LEVEL inside"}[ef["at"]]
    if ef.get("bar") is None:
        return "%s the fill bar (the bar varies with the signal)" % where
    return "%s %s - every entry" % (where, ef.get("label") or "bar %s" % ef["bar"])


def parse_entry_fill(value, tf, first_bar=None):
    """The proposal's entry_fill -> {at, bar, clock, label}: at = 'open' | 'close' | 'level' (a stop / limit inside the
    bar); bar = the 0-based in-session bar every entry fills on (a fixed-time entry, counted by the clock) or None (-1 /
    omitted: the bar varies with the signal). Accepts {"at": "open", "bar": 13, "clock": "10:35"}, its JSON text, or
    text like 'open' / 'bar 13 (10:35 open), open'. A fixed bar before first_signal_bar is refused. Raises ToolRefused."""
    ex = ("e.g. {\"at\": \"open\", \"bar\": -1} (the OPEN of the bar after the signal; the bar varies) or {\"at\": "
          "\"open\", \"bar\": 13, \"clock\": \"%s\"} (every entry at %s's open)" % (bar_clock(13, tf), bar_label(13, tf)))
    v = value
    if isinstance(v, str):
        s = v.strip()
        try:
            v = json.loads(s)
        except ValueError:
            words = re.findall(r"\b(open|close|level|stop|limit|intrabar)\b", re.sub(r"\([^)]*\)", " ", s.lower()))
            mb = re.search(r"\bbar\s*(-?\d+)", s, re.I)
            mc = re.search(r"(\d{1,2}:\d{2})", s)
            v = {"at": words[-1] if words else None, "bar": int(mb.group(1)) if mb else None,
                 "clock": mc.group(1) if mc else None}
    if not isinstance(v, dict):
        raise ToolRefused("entry_fill is required (MANAGER #160b/#162): where every entry FILLS - at the bar's OPEN, "
                          "its CLOSE, or a stop / limit LEVEL inside it - and, for a fixed-time entry, which bar (%s)"
                          % ex)
    at = ENTRY_FILL_AT.get(str(v.get("at") or v.get("price") or v.get("fill") or "").strip().lower())
    if at is None:
        raise ToolRefused("entry_fill.at must be 'open', 'close' or 'level' (a stop / limit inside the bar) - %s" % ex)
    bar = v.get("bar")
    if bar in (None, "", "any", "varies") or (isinstance(bar, (int, float)) and int(bar) < 0):
        return {"at": at, "bar": None, "clock": None, "label": None}
    try:
        k = int(bar)
        if float(bar) != k:
            raise ValueError
    except (TypeError, ValueError):
        raise ToolRefused("entry_fill.bar must be a whole in-session bar index, or -1 when the bar varies (%s)" % ex)
    nb = bars_per_session(tf)
    if not (0 <= k < nb):
        raise ToolRefused("entry_fill.bar %s is outside the session: %s bars run 0..%d" % (k, tf, nb - 1))
    m = re.search(r"(\d{1,2}):(\d{2})", str(v.get("clock") or ""))
    if m and "%02d:%02d" % (int(m.group(1)), int(m.group(2))) != bar_clock(k, tf):
        raise ToolRefused("entry_fill {bar %d, clock %s:%s} disagree: on %s bars, bar %d OPENS at %s (bar 0 = the 09:30 "
                          "open)" % (k, m.group(1), m.group(2), tf, k, bar_clock(k, tf)))
    if first_bar is not None and k < int(first_bar):
        raise ToolRefused("entry_fill.bar %d is before first_signal_bar %d - the earliest bar an entry may fill on: "
                          "state the same bar in both" % (k, int(first_bar)))
    return {"at": at, "bar": k, "clock": bar_clock(k, tf), "label": bar_label(k, tf)}


def parse_time_stop(value, tf):
    """The proposal's time_stop_bars -> int N >= 0 (0 = no time stop). Convention (MANAGER #160b/#162): a time stop
    of N bars exits at the CLOSE of entry bar + N (exit_bar - entry_bar = N = 'N bars held'). Raises ToolRefused."""
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ToolRefused("time_stop_bars is required (MANAGER #160b/#162): N = exit at the CLOSE of entry bar + N "
                          "(exit_bar - entry_bar = N, 'N bars held'), or 0 when the rule has no time stop")
    if isinstance(value, str) and value.strip().lower() in ("none", "no", "0", "false", "n/a"):
        return 0
    if isinstance(value, bool):
        return 0
    try:
        n = int(float(value))
        if float(value) != n:
            raise ValueError
    except (TypeError, ValueError):
        raise ToolRefused("time_stop_bars must be a whole number of bars (0 = no time stop)")
    if not (0 <= n < bars_per_session(tf)):
        raise ToolRefused("time_stop_bars %s is outside 0..%d (%s bars in a session)" % (n, bars_per_session(tf) - 1, tf))
    return n


def time_stop_label(n, tf=None):
    if n is None:
        return "not stated"
    if not int(n):
        return "none (time_stop_bars 0)"
    return "%d bars: exit at the CLOSE of entry bar + %d (exit_bar - entry_bar = %d)" % (int(n), int(n), int(n))


def missing_contract_fields(pr):
    """The timing-contract fields a proposal lacks (an older proposal): first_signal_bar, entry_fill, time_stop_bars."""
    pr = pr or {}
    out = []
    if (pr.get("first_signal_bar") or {}).get("index") is None:
        out.append("first_signal_bar")
    if not (pr.get("entry_fill") or {}).get("at"):
        out.append("entry_fill")
    if pr.get("time_stop_bars") is None:
        out.append("time_stop_bars")
    return out


def _fill_tol(p):
    return 1e-6 * max(1.0, abs(float(p)))


def _session_bounds(day_id):
    """(starts, ends) index arrays of the day_id runs."""
    import numpy as np
    did = np.asarray(day_id)
    n = len(did)
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]]) if n else np.zeros(0, int)
    return starts, np.r_[starts[1:], n] if n else np.zeros(0, int)


def entry_fill_violations(trades, arrays, entry_fill, tf=None, limit=8):
    """MANAGER #160b/#162: realised entries against the proposal's entry_fill - at 'open' every entry price is its bar's
    OPEN, at 'close' its CLOSE (a price equal to both passes either; 'level' = any price inside the bar, which fill
    realism checks), and with a fixed bar every entry fills on that in-session bar (by the clock, session_bar_index).
    Returns {n, checked, at, bar, examples[]}."""
    import numpy as np
    ef = entry_fill or {}
    at, bar = ef.get("at"), ef.get("bar")
    O = np.asarray(arrays["open"], float)
    C = np.asarray(arrays["close"], float)
    idx = arrays.get("index")
    starts, _ = _session_bounds(arrays["day_id"])
    n = len(C)
    bad, checked = [], 0
    for t in trades or []:
        e = int(t[0])
        px = t[4] if len(t) > 4 else None
        if not (0 <= e < n) or px is None:
            continue
        checked += 1
        px = float(px)
        tol = _fill_tol(px)
        why = []
        if at == "open" and abs(px - O[e]) > tol:
            why.append("filled at %.4f, not the bar's OPEN %.4f%s" % (px, O[e], " - it is the bar's CLOSE"
                                                                     if abs(px - C[e]) <= tol else ""))
        if at == "close" and abs(px - C[e]) > tol:
            why.append("filled at %.4f, not the bar's CLOSE %.4f%s" % (px, C[e], " - it is the bar's OPEN"
                                                                      if abs(px - O[e]) <= tol else ""))
        start = int(starts[np.searchsorted(starts, e, side="right") - 1])
        k = session_bar_index(e, start, idx, tf)
        if bar is not None and k != int(bar):
            why.append("filled on session bar %d, not the stated bar %d" % (k, int(bar)))
        if why:
            bad.append({"entry_bar": e, "session_bar": int(k), "time": str(idx[e])[:16] if idx is not None else None,
                        "side": int(t[3]) if len(t) > 3 and t[3] is not None else None, "price": round(px, 4),
                        "bar_open": round(float(O[e]), 4), "bar_close": round(float(C[e]), 4), "why": "; ".join(why)})
    return {"n": len(bad), "checked": checked, "at": at, "bar": bar, "examples": bad[:limit]}


def time_stop_violations(trades, arrays, n_bars, limit=8, cost_pts=0.0):
    """MANAGER #160b/#162: a time stop of N bars exits at the CLOSE of entry bar + N. Violations: a trade held MORE
    than N bars (exit_bar - entry_bar > N); and the shapes read from the realised exits (an exit reason is not
    reported). With N > 0: no exit at entry bar + N's close while >= 3 (and >= 20% of the trades) exit at entry bar
    + N-1's CLOSE inside the session (the entry bar counted as bar 1), or while >= 3 exit at entry bar + N's OPEN (the
    time stop filled at the open), or (review round 4) the plugin's own time stop is SHORTER: no trade is held past h
    < N-1 bars and >= 3 (>= 20% of the trades) exit at entry bar + h's CLOSE inside the session (a stated 6-bar stop the
    code runs as 4 bars). With N == 0 ('no time stop'): the same shape at any h >= 1 is an UNDECLARED h-bar time stop.
    The exit price is rebuilt from the entry price and the GROSS points: an engine run's trade P&L is net of cost_pts,
    so pass the cost it charged. Returns {n, checked, time_stop_bars, held_past, at_time_stop, effective_time_stop,
    pattern[], examples[] (trades held past N), pattern_examples[] (the trades behind each pattern)}."""
    import numpy as np
    N = int(n_bars or 0)
    out = {"n": 0, "checked": 0, "time_stop_bars": N, "held_past": 0, "at_time_stop": 0, "effective_time_stop": None,
           "pattern": [], "examples": [], "pattern_examples": []}
    O = np.asarray(arrays["open"], float)
    C = np.asarray(arrays["close"], float)
    idx = arrays.get("index")
    starts, ends = _session_bounds(arrays["day_id"])
    n = len(C)

    def row(e, x, hold, xp, why):
        return {"entry_bar": e, "exit_bar": x, "bars_held": hold,
                "entry_time": str(idx[e])[:16] if idx is not None else None,
                "exit_time": str(idx[x])[:16] if idx is not None else None,
                "exit_price": round(float(xp), 4) if xp is not None else None, "bar_open": round(float(O[x]), 4),
                "bar_close": round(float(C[x]), 4), "why": why}
    held, at_close, at_open, early = [], 0, [], []
    close_holds = {}                                             # hold -> [rows] of in-session exits at a bar's CLOSE
    max_hold = None
    for t in trades or []:
        e, x = int(t[0]), int(t[1])
        if not (0 <= e <= x < n):
            continue
        out["checked"] += 1
        side = int(t[3]) if len(t) > 3 and t[3] is not None else None
        px = float(t[4]) if len(t) > 4 and t[4] is not None else None
        xp = px + side * (float(t[2]) + float(cost_pts or 0.0)) if (px is not None and side in (1, -1)) else None
        last = x == int(ends[np.searchsorted(starts, x, side="right") - 1]) - 1
        hold = x - e
        max_hold = hold if max_hold is None else max(max_hold, hold)
        is_close = xp is not None and abs(xp - C[x]) <= _fill_tol(xp)
        is_open = (xp is not None and abs(xp - O[x]) <= _fill_tol(xp) and abs(O[x] - C[x]) > _fill_tol(xp))
        if is_close and not last:
            close_holds.setdefault(hold, []).append((e, x, hold, xp))
        if N <= 0:
            continue
        if hold > N:
            held.append(row(e, x, hold, xp, "held %d bars, past the stated time stop of %d (exit at the close of entry "
                                            "bar + %d = bar %d)" % (hold, N, N, e + N)))
        elif hold == N and (is_close or last):
            at_close += 1
        elif hold == N and is_open:
            at_open.append(row(e, x, hold, xp, "exits at the OPEN of entry bar + %d (%.4f), not its CLOSE (%.4f)"
                                               % (N, O[x], C[x])))
        elif hold == N - 1 and is_close and not last:
            early.append(row(e, x, hold, xp, "exits at the CLOSE of entry bar + %d, one bar before the stated time "
                                             "stop of %d" % (hold, N)))
    out.update(held_past=len(held), at_time_stop=at_close, examples=held[:limit])
    need = max(3, 0.2 * out["checked"])
    if N > 0 and not at_close and len(early) >= need:
        out["pattern"].append("%d of %d trades exit at the CLOSE of entry bar + %d and none at entry bar + %d - the "
                              "time stop counts the entry bar as bar 1; the convention is the CLOSE of entry bar + N "
                              "(exit_bar - entry_bar = N)" % (len(early), out["checked"], N - 1, N))
        out["pattern_examples"] += early[:limit]
    if N > 0 and not at_close and len(at_open) >= 3:
        out["pattern"].append("%d trades exit at the OPEN of entry bar + %d and none at its close - the convention is "
                              "the CLOSE of entry bar + N" % (len(at_open), N))
        out["pattern_examples"] += at_open[:limit]
    # review round 4: the plugin's OWN time stop h - no trade held past h bars and >= 3 (>= 20%) in-session exits at
    # entry bar + h's close. Shorter than a stated N (h < N-1; N-1 is the off-by-one shape above), or undeclared (N 0)
    h = max_hold
    if h is not None and h >= 1 and len(close_holds.get(h, ())) >= need and (N <= 0 or (h < N - 1 and not at_close)):
        out["effective_time_stop"] = h
        rows = [row(e, x, hh, xp, "exits at the CLOSE of entry bar + %d - no trade is held longer" % hh)
                for e, x, hh, xp in close_holds[h][:limit]]
        if N > 0:
            out["pattern"].append("%d of %d trades exit at the CLOSE of entry bar + %d and no trade is held longer - "
                                  "the plugin's time stop is %d bars, the proposal states %d (exit at the CLOSE of "
                                  "entry bar + N, exit_bar - entry_bar = N)" % (len(close_holds[h]), out["checked"], h,
                                                                                h, N))
        else:
            out["pattern"].append("%d of %d trades exit at the CLOSE of entry bar + %d and no trade is held longer - "
                                  "the plugin has an undeclared %d-bar time stop, the proposal states time_stop_bars 0 "
                                  "(no time stop); state time_stop_bars = %d (a clock exit a fixed number of bars after "
                                  "a fixed entry bar is the same thing) or remove it"
                                  % (len(close_holds[h]), out["checked"], h, h, h))
        out["pattern_examples"] += rows
    out["pattern_examples"] = out["pattern_examples"][:limit]
    out["n"] = len(held) + len(out["pattern"])
    return out


_BAR_MENTION_RX = re.compile(r"\bbar\s+(\d{1,3})\b(?!\s*\(\s*\d{1,2}:\d{2})", re.I)
_BAR_CLOCK_RX = re.compile(r"\bbar\s+(\d{1,3})\s*\(\s*(\d{1,2}):(\d{2})", re.I)


def bar_convention_notes(text, tf):
    """Soft lint of the proposal text against the bar convention: 'bar 12' with no clock, or a clock that is not that
    bar's open. Returned to Qwen with an accepted proposal (never a refusal)."""
    out = []
    s = str(text or "")
    bare = sorted({int(m.group(1)) for m in _BAR_MENTION_RX.finditer(s)} & set(range(bars_per_session(tf))))
    if bare:
        out.append("name bars as 'bar k (HH:MM open)': %s" % ", ".join(
            "'bar %d' -> '%s'" % (k, bar_label(k, tf)) for k in bare[:4]))
    for m in _BAR_CLOCK_RX.finditer(s):
        k, got = int(m.group(1)), "%02d:%02d" % (int(m.group(2)), int(m.group(3)))
        if k < bars_per_session(tf) and got != bar_clock(k, tf):
            out.append("'bar %d (%s ...)': on %s bars bar %d OPENS at %s (its close is %s)"
                       % (k, got, tf, k, bar_clock(k, tf), bar_clock(k + 1, tf)))
    return out[:4]


def session_bar_index(e, start, index=None, tf=None):
    """The in-session index of bar e BY THE CLOCK (the convention: bar k opens at 09:30 + k x bar minutes), so a session
    with missing bars (1m / 2m holidays: 2015-02-16 10:30 is the 59th bar, yet bar 60 by the clock) keeps the prompt's
    numbering. Falls back to the position in the session (e - start) without timestamps / timeframe, or for a stamp
    outside the regular session."""
    pos = int(e) - int(start)
    if index is None or not tf:
        return pos
    try:
        ts = index[int(e)]
        k = (int(ts.hour) * 60 + int(ts.minute) - RTH_OPEN_MIN) // tf_minutes(tf)
    except (AttributeError, TypeError, ValueError, IndexError):
        return pos
    return int(k) if 0 <= k < bars_per_session(tf) else pos


def first_bar_violations(trades, day_id, index=None, first_bar=0, limit=8, tf=None):
    """Entries that FILL before the pre-registered first_signal_bar (TTM #144). The in-session index is read from the
    entry bar's OPEN clock (session_bar_index - the prompt's convention); without timestamps / timeframe it is the
    entry bar minus the first bar of its session (day_id). Returns {n, checked, earliest_session_bar,
    first_signal_bar, index_by, examples[]}."""
    import numpy as np
    did = np.asarray(day_id)
    n = len(did)
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]]) if n else np.zeros(0, int)
    bad, checked, earliest = [], 0, None
    for t in trades or []:
        e = int(t[0])
        if not (0 <= e < n):
            continue
        checked += 1
        start = int(starts[np.searchsorted(starts, e, side="right") - 1])
        k = session_bar_index(e, start, index, tf)
        earliest = k if earliest is None else min(earliest, k)
        if k < int(first_bar):
            bad.append({"entry_bar": e, "session_bar": int(k),
                        "time": str(index[e])[:16] if index is not None else None,
                        "side": int(t[3]) if len(t) > 3 and t[3] is not None else None,
                        **({"position_in_session": e - start} if e - start != k else {})})
    return {"n": len(bad), "checked": checked, "earliest_session_bar": earliest, "first_signal_bar": int(first_bar),
            "index_by": "clock" if (index is not None and tf) else "position", "examples": bad[:limit]}


# ------------------------------------------------------------------------------------------------ the SAFETY GATE
ALLOWED_IMPORTS = {"numpy", "pandas", "math"}
# None = any non-forbidden name; the session-calendar helpers (MANAGER #156) by name
ALLOWED_FROM = {"augur_engine.rolls": {"seam_days"}, "math": None, "numpy": None,
                "augur_engine.session_calendar": {"session_calendar", "session_dates", "session_index_in_month",
                                                  "days_to_month_end", "is_last_n_sessions_of_month",
                                                  "is_first_n_sessions_of_month", "week_of_month",
                                                  "exchange_sessions", "is_exchange_session"}}
FORBIDDEN_NAMES = {
    "open", "exec", "eval", "compile", "__import__", "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "hasattr", "input", "breakpoint", "help", "exit", "quit", "print", "memoryview", "type", "super",
    "object", "classmethod", "staticmethod", "property", "__builtins__", "os", "sys", "subprocess", "socket",
    "shutil", "pathlib", "requests", "urllib", "http", "ctypes", "importlib", "pickle", "threading",
    "multiprocessing", "io", "builtins", "inspect", "gc", "marshal", "signal", "asyncio", "tempfile", "glob", "json",
    "codecs", "runpy", "types", "zipimport", "winreg", "msvcrt", "mmap", "sqlite3", "shelve", "dbm", "webbrowser",
    "ftplib", "smtplib", "telnetlib", "ssl", "select", "selectors", "concurrent", "_thread", "platform", "resource"}
FORBIDDEN_ATTRS = {
    "load", "loads", "save", "savez", "savez_compressed", "savetxt", "loadtxt", "genfromtxt", "fromfile", "tofile",
    "memmap", "fromregex", "dump", "dumps", "open", "system", "popen", "eval", "query", "ctypeslib", "ctypes", "lib",
    "f2py", "distutils", "testing", "os", "sys", "ma", "rec", "DataSource", "HDFStore", "ExcelWriter", "ExcelFile",
    "io", "api", "options", "set_option", "get_option", "reset_option", "describe_option", "option_context",
    "show_versions", "plotting", "style", "core", "compat", "util", "mro", "gi_frame", "gi_code", "gi_yieldfrom",
    "cr_frame", "cr_code", "ag_frame", "ag_code", "f_globals", "f_locals", "f_builtins", "f_back", "f_code",
    "tb_frame", "tb_next", "co_code", "co_consts", "func_globals", "exec", "compile", "import_module", "spawn",
    "Popen", "environ", "getenv", "putenv", "unlink", "rmdir", "makedirs", "mkdir", "chdir", "listdir", "scandir",
    "write", "writelines", "urlopen", "request", "connect", "socket", "plot", "figure", "savefig", "clipboard",
    "seterrcall", "setbufsize", "set_printoptions", "open_memmap", "fromstring_file"}
TO_OK = {"to_numpy", "to_list", "to_dict", "to_frame", "to_period", "to_timestamp", "to_pydatetime", "to_datetime",
         "to_numeric", "to_timedelta", "to_series", "to_datetime64", "to_flat_index", "to_offset", "to_string"}
_BAD_ATTR_PREFIX = ("_", "read_", "save", "load", "dump")
_MODULE_STMTS = (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.FunctionDef)
_BANNED_NODES = {ast.ClassDef: "class definitions", ast.Global: "global statements", ast.Nonlocal: "nonlocal",
                 ast.AsyncFunctionDef: "async functions", ast.Await: "await", ast.AsyncFor: "async for",
                 ast.AsyncWith: "async with"}
if hasattr(ast, "TypeAlias"):
    _BANNED_NODES[ast.TypeAlias] = "type aliases"


# review round 4 (MEMO2): no state may survive from one run_backtest call to the next - the look-ahead audit compares
# runs on perturbed bars, and a cache replays the real bars' answer. The sandbox gives every run a fresh namespace
# (_sb_load_plugin); the gate refuses the plain shapes too, so Qwen hears why: a module-level mutable container (only
# the contract constants may be dicts), a write into a module-level name from a function (subscript store / del /
# a mutating method call), and a mutable default argument
CONTRACT_DICTS = {"DEFAULT_PARAMS", "_AUGUR_MARKET"}
_MUTATING_METHODS = {"append", "extend", "insert", "pop", "popitem", "update", "setdefault", "clear", "remove", "add",
                     "discard", "sort", "reverse", "fill", "put", "itemset", "resize", "setflags", "partition",
                     "intersection_update", "difference_update", "symmetric_difference_update", "byteswap"}
_CONTAINER_CALLS = {"dict", "list", "set", "bytearray"}


def _mutable_in(node, arr_names):
    """A description of the first mutable container built in expression `node` (a list / dict / set display or
    comprehension, dict() / list() / set() / bytearray(), or a numpy / pandas call), else None."""
    for n in ast.walk(node):
        if isinstance(n, (ast.List, ast.ListComp)):
            return "a list"
        if isinstance(n, (ast.Dict, ast.DictComp)):
            return "a dict"
        if isinstance(n, (ast.Set, ast.SetComp)):
            return "a set"
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name) and f.id in _CONTAINER_CALLS:
                return "%s()" % f.id
            if _attr_root(f, through_calls=False) in arr_names:
                return "a numpy / pandas object (%s)" % ast.unparse(f)[:40]
    return None


def _attr_root(node, through_calls=True):
    """The Name at the root of a subscript / attribute (/ method-call) chain: `_SEEN[k]` -> '_SEEN', `_C.get(k).append`
    -> '_C' (through_calls: through a METHOD call only - `helper(x).append` has no root, its result is a new object),
    `np.typecodes['x']` -> 'np'; None when the chain starts at anything else."""
    while True:
        if isinstance(node, (ast.Subscript, ast.Attribute, ast.Starred)):
            node = node.value
        elif through_calls and isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            node = node.func
        else:
            return node.id if isinstance(node, ast.Name) else None


def _scope_locals(fn):
    """The names a function / lambda binds in its OWN scope (arguments, assignment / loop / with / except targets,
    walrus targets, imports, nested function names); nested function bodies are not entered."""
    a = fn.args
    out = {x.arg for x in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs) + [v for v in (a.vararg, a.kwarg) if v]}
    stack = list(fn.body) if isinstance(fn.body, list) else [fn.body]
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            if not isinstance(n, ast.Lambda):
                out.add(n.name)
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out |= {(al.asname or al.name).split(".")[0] for al in n.names}
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        stack.extend(ast.iter_child_nodes(n))
    return out


def _state_problems(tree):
    """Review round 4: the shapes that carry state between runs - [(node, message)]."""
    probs = []
    mod_names, imported, arr_names = set(), set(), set()
    for st in tree.body:
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            for al in st.names:
                nm = (al.asname or al.name).split(".")[0]
                imported.add(nm)
                mod_names.add(nm)
                if (isinstance(st, ast.Import) and al.name.split(".")[0] in ("numpy", "pandas")) or \
                        (isinstance(st, ast.ImportFrom) and st.module == "numpy"):
                    arr_names.add(nm)                            # calls through these build arrays / frames
        elif isinstance(st, ast.FunctionDef):
            mod_names.add(st.name)
        elif isinstance(st, (ast.Assign, ast.AnnAssign)):
            targets = st.targets if isinstance(st, ast.Assign) else [st.target]
            names = [n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)]
            mod_names |= set(names)
            what = _mutable_in(st.value, arr_names) if st.value is not None else None
            if what and not (len(names) == 1 and names[0] in CONTRACT_DICTS and isinstance(targets[0], ast.Name)):
                probs.append((st, "module-level %s holds %s - only the contract dicts (%s) may be mutable at module "
                                  "level: a module-level container can carry state from one run to the next (a cache "
                                  "replays one run's trades to another). Use a tuple / number / string constant, or "
                                  "build it inside run_backtest" % (", ".join(names) or "value", what,
                                                                    " / ".join(sorted(CONTRACT_DICTS)))))

    def mutated(target, locs, in_fn):
        """The module-level name a store / mutating call on `target` writes into, else None: anything reached from an
        IMPORTED name (np.typecodes['x'] - numpy's own state outlives every run), and - inside a function - any
        non-local module-level name (through method calls: _CACHE.get(k).append)."""
        r0 = _attr_root(target, through_calls=False)
        if r0 in imported and r0 not in locs:
            return r0
        if in_fn:
            r = _attr_root(target)
            if r in mod_names and r not in imported and r not in locs:
                return r
        return None

    def scan(node, locs, in_fn):
        for n in ast.iter_child_nodes(node):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for d in list(n.args.defaults) + [x for x in n.args.kw_defaults if x is not None]:
                    what = _mutable_in(d, arr_names)
                    if what or isinstance(d, ast.Call):
                        probs.append((n, "a default argument of %s is %s - a default is built ONCE and shared by "
                                         "every call, so it can carry state between runs; use None and build it "
                                         "inside the function" % (getattr(n, "name", "a lambda"),
                                                                  what or "a call (%s)" % ast.unparse(d)[:40])))
                scan(n, locs | _scope_locals(n), True)
                continue
            root = None
            if isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)):
                root = mutated(n, locs, in_fn)
                if root:
                    probs.append((n, "writes into the module-level %s (`%s`) - state that outlives the run (a cache) "
                                     "is not allowed; keep every container local to run_backtest"
                                     % (root, ast.unparse(n)[:50])))
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in _MUTATING_METHODS:
                root = mutated(n.func.value, locs, in_fn)
                if root:
                    probs.append((n, "calls .%s() on the module-level %s (`%s`) - mutating a module-level object "
                                     "carries state between runs (a cache); keep every container local to run_backtest"
                                     % (n.func.attr, root, ast.unparse(n.func)[:50])))
            scan(n, locs, in_fn)

    scan(tree, set(), False)
    return probs


def _attr_problem(attr):
    if attr.startswith("__") or attr.endswith("__"):
        return "dunder attribute .%s" % attr
    if attr in FORBIDDEN_ATTRS:
        return "forbidden attribute .%s (file / network / interpreter access)" % attr
    if attr.startswith("to_") and attr not in TO_OK:
        return "forbidden attribute .%s (pandas / numpy writers are I/O)" % attr
    for p in _BAD_ATTR_PREFIX:
        if attr.startswith(p):
            return "forbidden attribute .%s (private, or a reader / writer)" % attr
    return None


def safety_gate(code):
    """(ok, reasons). Static whitelist check of LLM-written plugin code - nothing is imported or executed here."""
    reasons = []
    if not isinstance(code, str) or not code.strip():
        return False, ["no code"]
    if len(code) > CODE_MAX_CHARS:
        return False, ["code is %d chars (cap %d)" % (len(code), CODE_MAX_CHARS)]
    if code.count("\n") > 1500:
        return False, ["more than 1500 lines"]
    try:
        tree = ast.parse(code, filename="<qwen_plugin>")
    except SyntaxError as e:
        return False, ["syntax error line %s: %s" % (e.lineno, e.msg)]
    nodes = list(ast.walk(tree))
    if len(nodes) > 30000:
        return False, ["more than 30000 syntax nodes"]

    def bad(node, msg):
        reasons.append("line %s: %s" % (getattr(node, "lineno", "?"), msg))

    for i, st in enumerate(tree.body):
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str):
            continue                                             # a docstring / comment string
        if not isinstance(st, _MODULE_STMTS):
            bad(st, "only imports, assignments, function definitions and docstrings are allowed at module level "
                    "(found %s)" % type(st).__name__)
    for node in nodes:
        for cls, what in _BANNED_NODES.items():
            if isinstance(node, cls):
                bad(node, "%s are not allowed" % what)
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name not in ALLOWED_IMPORTS:
                    bad(node, "import %s is not allowed (numpy, pandas, math only)" % a.name)
                if a.asname and (a.asname.startswith("__") or a.asname in FORBIDDEN_NAMES):
                    bad(node, "import alias %s is not allowed" % a.asname)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level:
                bad(node, "relative imports are not allowed")
            elif mod not in ALLOWED_FROM:
                bad(node, "from %s import ... is not allowed (only `from augur_engine.rolls import seam_days`, "
                          "`from augur_engine.session_calendar import <helper>`, math, numpy)" % mod)
            else:
                allow = ALLOWED_FROM[mod]
                for a in node.names:
                    if a.name == "*":
                        bad(node, "star imports are not allowed")
                    elif allow is not None and a.name not in allow:
                        bad(node, "from %s import %s is not allowed" % (mod, a.name))
                    elif _attr_problem(a.name) or a.name in FORBIDDEN_NAMES:
                        bad(node, "importing %s is not allowed" % a.name)
                    if a.asname and (a.asname.startswith("__") or a.asname in FORBIDDEN_NAMES):
                        bad(node, "import alias %s is not allowed" % a.asname)
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_NAMES:
                bad(node, "name %s is not allowed" % node.id)
            elif node.id.startswith("__"):
                bad(node, "dunder name %s is not allowed" % node.id)
        elif isinstance(node, ast.Attribute):
            p = _attr_problem(node.attr)
            if p:
                bad(node, p)
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bad(node, "assigning or deleting an attribute (.%s) is not allowed" % node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("__"):
                bad(node, "dunder function name %s" % node.name)
            args = node.args
            for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs) + \
                    [x for x in (args.vararg, args.kwarg) if x is not None]:
                if a.arg.startswith("__") or a.arg in FORBIDDEN_NAMES:
                    bad(node, "argument name %s is not allowed" % a.arg)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, str) and "__" in node.value:
                bad(node, "strings may not contain '__'")
            elif isinstance(node.value, bytes):
                bad(node, "bytes literals are not allowed")
        elif isinstance(node, ast.ExceptHandler):
            if node.name and (node.name.startswith("__") or node.name in FORBIDDEN_NAMES):
                bad(node, "exception name %s is not allowed" % node.name)
    for node, msg in _state_problems(tree):                      # review round 4: no state between runs (MEMO2)
        bad(node, msg)
    # de-duplicate, keep order
    seen, out = set(), []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return (not out), out[:25]


def clean_code(code):
    """Strip a markdown fence Qwen may wrap the code in."""
    s = str(code or "").replace("\r\n", "\n")
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", s, re.S)
    if blocks:
        try:
            ast.parse(s)
        except SyntaxError:
            s = max(blocks, key=len)                             # prose around a fenced file: keep the file
    return s.rstrip() + "\n"


# ------------------------------------------------------------------------------------------------ the SANDBOX (child)
_SB = {"armed": 0, "blocked": [], "read_roots": [], "real_import": None}
_SB_BLOCK_PREFIXES = (
    "subprocess.", "os.system", "os.exec", "os.spawn", "os.posix_spawn", "os.startfile", "os.kill", "os.remove",
    "os.rename", "os.rmdir", "os.mkdir", "os.chmod", "os.link", "os.symlink", "os.truncate", "os.putenv",
    "os.unsetenv", "os.chdir", "os.add_dll_directory", "shutil.", "socket.", "ctypes.", "winreg.", "_winapi.",
    "msvcrt.", "urllib.", "http.", "ftplib.", "smtplib.", "poplib.", "imaplib.", "nntplib.", "telnetlib.",
    "webbrowser.", "builtins.input", "builtins.breakpoint", "sys.addaudithook", "code.__new__",
    "_thread.start_new_thread", "pickle.find_class", "mmap.", "sqlite3.", "cpython.run_", "os.listdrives",
    "os.listmounts", "os.listvolumes")
_SB_IMPORTS = ("numpy", "pandas", "math", "augur_engine.rolls", "augur_engine.session_calendar")
_SB_DROP_BUILTINS = ("open", "exec", "eval", "compile", "globals", "locals", "vars", "dir", "getattr", "setattr",
                     "delattr", "hasattr", "input", "breakpoint", "help", "exit", "quit", "memoryview", "type",
                     "super", "classmethod", "staticmethod", "property", "__loader__", "__spec__", "__build_class__")


def _sb_write_flags(mode, flags):
    if isinstance(mode, str):
        return any(c in mode for c in "wax+")
    try:
        f = int(flags or 0)
    except (TypeError, ValueError):
        return True
    return bool(f & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC))


def _sb_hook(event, args):
    if not _SB["armed"] or _SB.get("in_hook"):
        return
    _SB["in_hook"] = True
    try:
        _sb_check(event, args)
    finally:
        _SB["in_hook"] = False


def _sb_check(event, args):
    if event == "open":
        path, mode, flags = (list(args) + [None, None, None])[:3]
        if isinstance(path, int):
            if _sb_write_flags(mode, flags):
                _SB["blocked"].append("open fd for write")
                raise PermissionError("QWEN LAB sandbox: writing is blocked")
            return
        p = os.fsdecode(path) if isinstance(path, (bytes, bytearray)) else str(path)
        if _sb_write_flags(mode, flags):
            _SB["blocked"].append("open for write: %s" % p[:200])
            raise PermissionError("QWEN LAB sandbox: writing %s is blocked" % p)
        if not any(under(p, r) for r in _SB["read_roots"]):
            _SB["blocked"].append("open outside the allowed folders: %s" % p[:200])
            raise PermissionError("QWEN LAB sandbox: reading %s is blocked" % p)
        return
    for pre in _SB_BLOCK_PREFIXES:
        if event.startswith(pre):
            _SB["blocked"].append(event)
            raise PermissionError("QWEN LAB sandbox: %s is blocked" % event)


class _Armed:
    def __enter__(self):
        _SB["armed"] += 1

    def __exit__(self, *a):
        _SB["armed"] -= 1
        return False


# C code (numpy's ndarray.min -> numpy._core._methods) imports through the CURRENT frame's builtins, i.e. the
# plugin's. Those internal imports are allowed: numpy / pandas submodules, and a few harmless stdlib modules that are
# already loaded. The plugin itself can only write the whitelisted imports (the AST gate); this is the second layer.
_SB_INTERNAL_OK = ("numpy.", "pandas.", "augur_engine.rolls", "augur_engine.session_calendar")
_SB_STDLIB_OK = {"datetime", "operator", "copyreg", "warnings", "functools", "itertools", "collections", "numbers",
                 "decimal", "fractions", "time", "_strptime", "locale", "re", "string", "enum", "abc", "typing",
                 "dataclasses", "zoneinfo", "calendar", "math", "cmath", "_datetime", "_decimal", "unicodedata"}


def _sb_guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    ok = level == 0 and (name in _SB_IMPORTS or name.startswith(_SB_INTERNAL_OK)
                         or (name in _SB_STDLIB_OK and name in sys.modules))
    if not ok:
        raise ImportError("QWEN LAB sandbox: import of %r is not allowed" % (name,))
    return _SB["real_import"](name, globals, locals, fromlist, level)


def _sb_builtins():
    b = dict(builtins.__dict__)
    for k in _SB_DROP_BUILTINS:
        b.pop(k, None)
    b["__import__"] = _sb_guarded_import
    b["print"] = lambda *a, **k: None
    return b


def _sb_watchdog(limit_bytes):
    import threading

    def run():
        try:
            import psutil
            proc = psutil.Process()
        except Exception:
            return
        while True:
            try:
                if proc.memory_info().rss > limit_bytes:
                    os._exit(86)
            except Exception:
                pass
            time.sleep(0.2)
    t = threading.Thread(target=run, daemon=True)
    t.start()


def _sb_exec_plugin(code, path, name):
    """A FRESH module namespace for the compiled plugin (new globals, new builtins dict, new function objects and
    defaults), its module code executed armed."""
    mod = types.ModuleType("qwen_lab_plugin_" + name)
    mod.__file__ = path
    mod.__dict__["__builtins__"] = _sb_builtins()
    with _Armed():
        exec(code, mod.__dict__)                                 # noqa: S102 - the sandbox's exec, armed
    return mod


def _sb_fresh_arg(x):
    """A private copy of a numpy array argument (bars, volumes, day_id) - nothing a run writes into its inputs reaches
    the harness's arrays or the next run."""
    import numpy as np
    return np.array(x, copy=True) if isinstance(x, np.ndarray) else x


def _sb_load_plugin(path, expect_sha):
    """Load the plugin armed. Review round 4 (MEMO2: a same-bar-foresight rule whose trades were cached in a module-level
    `_SEEN = {}` keyed on the bar count passed every look-ahead gate - the audit re-ran the SAME module object, so the
    real bars' answer was replayed to every perturbed variant): EVERY run_backtest call executes the compiled module
    into a fresh namespace and calls THAT run_backtest on copies of its array arguments, so no run can see another's
    state (module-level containers, mutable defaults, the input arrays). The module returned is the first execution:
    the engine reads its constants (DEFAULT_PARAMS, ROLL_SIGNAL ...) and the signature of run_backtest from it."""
    with open(path, "rb") as f:
        raw = f.read()
    sha = lf_sha256_bytes(raw)
    if sha != expect_sha:
        raise RuntimeError("HASH MISMATCH: %s is %s, the harness expected %s - refused" % (path, sha, expect_sha))
    src = raw.decode("utf-8")
    code = compile(src, path, "exec")                            # compiled by trusted code; executed armed below
    name = re.sub(r"\W", "_", os.path.splitext(os.path.basename(path))[0])
    mod = _sb_exec_plugin(code, path, name)
    fn = mod.__dict__.get("run_backtest")
    if not callable(fn):
        raise RuntimeError("the plugin defines no run_backtest()")

    @functools.wraps(fn)
    def armed_run_backtest(*a, **k):
        fresh = _sb_exec_plugin(code, path, name).__dict__.get("run_backtest")
        if not callable(fresh):
            raise RuntimeError("the plugin's run_backtest() is gone on a fresh load")
        a = tuple(_sb_fresh_arg(x) for x in a)
        k = {kk: _sb_fresh_arg(v) for kk, v in k.items()}
        with _Armed():
            return fresh(*a, **k)
    mod.run_backtest = armed_run_backtest
    return mod, src


def _sb_defaults(mod):
    dp = getattr(mod, "DEFAULT_PARAMS", None) or {}
    return {k: v.get("default") for k, v in dp.items() if isinstance(v, dict) and "default" in v}


def _sb_norm_trades(res):
    out = []
    for t in (res or {}).get("trades") or []:
        t = list(t)
        out.append([int(t[0]), int(t[1]), float(t[2]), (int(t[3]) if len(t) > 3 and t[3] is not None else None),
                    (float(t[4]) if len(t) > 4 and t[4] is not None else None)])
    return out


def _sb_master(req):
    from augur_engine import data as D
    rows = [m for m in D.list_masters() if m.get("filename") == req["master_filename"]]
    if len(rows) != 1:
        raise RuntimeError("pinned master %s: %d registry rows" % (req["master_filename"], len(rows)))
    m = rows[0]
    for k in ("instrument", "timeframe", "source"):
        if str(m.get(k)) != str(req[k]):
            raise RuntimeError("pinned master %s has %s=%r, expected %r" % (m.get("filename"), k, m.get(k), req[k]))
    return m


def _sb_load(req, date_from, date_to):
    from augur_engine import data as D
    m = _sb_master(req)
    A = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
    last = str(A["index"][-1].date())
    if last >= LB0:
        raise RuntimeError("LOCKBOX GUARD: arrays reach %s, on or after the lockbox start %s" % (last, LB0))
    return m, A


def _sb_synthetic(n_days=60, per_day=78, seed=7):
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    n = n_days * per_day
    close = 15000 + rng.normal(0, 4, n).cumsum()
    high = close + np.abs(rng.normal(0, 3, n))
    low = close - np.abs(rng.normal(0, 3, n))
    openp = np.clip(close + rng.normal(0, 2, n), low, high)
    vol = np.abs(rng.normal(1000, 200, n))
    day_id = np.repeat(np.arange(n_days), per_day).astype("int64")
    # MANAGER #156: REAL session dates (the exchange calendar from 2026-03-02), per_day 5m bars from each 09:30 - so a
    # calendar plugin sees month ends, and cutting the bars (the truncation check) never moves an earlier session's
    # calendar answer
    days = calendar_module().exchange_sessions("2026-03-02", "2030-12-31")[:n_days]
    idx = (pd.DatetimeIndex(days).repeat(per_day)
           + pd.to_timedelta(np.tile(570 + 5 * np.arange(per_day), n_days), unit="min")).tz_localize("US/Eastern")
    return {"open": openp, "high": high, "low": low, "close": close, "volume": vol, "day_id": day_id, "index": idx,
            "meta": {"name": "SYN", "roll_mode": "none"}}


_REQUIRED_KEYS = {"total_pnl", "num_trades", "win_rate", "profit_factor", "max_drawdown", "avg_pnl", "wins", "losses"}
# review round 4: the contract and the look-ahead audit cover EVERY knob the Auto-Validate searches - each ranged numeric
# knob at its min and max, each other option of a multi-option str / bool knob (bool_trail: a same-bar trail leak only
# with trail_on=True passed, every corner ran trail_on=False). A plugin with more searched knobs than this fails hard
# (the 5th ranged knob of a plugin used to go unaudited: ENTRY_BAR_CORNER_KNOBS was 4)
SEARCHED_KNOBS_MAX = 8


def searched_values(dp, params=None):
    """[(knob, value)] the Auto-Validate searches: every RANGED numeric knob (max > min) at its min and its max, and
    every option of a str / bool knob with more than one option (bool: [True, False] when unstated) - with `params`,
    the values equal to the default are left out."""
    out = []
    for k, v in (dp or {}).items():
        if not isinstance(v, dict):
            continue
        typ = v.get("type", "float")
        if typ in ("int", "float"):
            try:
                lo, hi = float(v["min"]), float(v["max"])
            except (KeyError, TypeError, ValueError):
                continue
            if hi > lo:
                out += [(k, int(v[end]) if typ == "int" else float(v[end])) for end in ("min", "max")]
        elif typ in ("str", "bool"):
            opts = v.get("options", [True, False] if typ == "bool" else None) or []
            if len(opts) > 1:
                out += [(k, o) for o in opts if o != v.get("default")]
    if params is not None:
        out = [(k, val) for k, val in out if params.get(k) != val]
    return out


def searched_knobs(dp):
    """The knobs the Auto-Validate searches (searched_values' knobs, in DEFAULT_PARAMS order)."""
    return list(dict.fromkeys(k for k, _ in searched_values(dp)))


def _sb_state_check(mod, S, params):
    """Review round 4 (MEMO2): the sandbox runs every call in a fresh namespace, but the Auto-Validate's runner runs
    every trial in ONE process - state a plugin keeps between calls (a cache the gate missed through an alias) would
    hand one trial's answer to the next. So the plugin's FIRST namespace (never used by any run) is run on the synthetic
    bars, on a mirrored copy (same length and first open - a cache key on those hits) and on the bars again, and each
    result must equal a fresh run's on the same bars. Returns the failure text, or None."""
    import numpy as np
    raw = getattr(mod.run_backtest, "__wrapped__", None)
    if raw is None:
        return None
    n = len(S["close"])
    k0 = max(1, n // 3)
    m = float(S["close"][k0 - 1])
    S2 = dict(S)
    for key, src in (("open", "open"), ("close", "close"), ("high", "low"), ("low", "high")):
        a = np.array(S[key], dtype=float, copy=True)
        a[k0:] = 2.0 * m - np.asarray(S[src], dtype=float)[k0:]  # the path mirrored from bar k0 (high <-> low)
        S2[key] = a

    @functools.wraps(raw)
    def shared(*a, **k):
        a = tuple(_sb_fresh_arg(x) for x in a)
        k = {kk: _sb_fresh_arg(v) for kk, v in k.items()}
        with _Armed():
            return raw(*a, **k)

    def sig(fn, A):
        sp = inspect.signature(raw).parameters
        has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
        ex = {}
        if A.get("volume") is not None and (has_kw or "volumes" in sp):
            ex["volumes"] = A["volume"]
        if A.get("day_id") is not None and (has_kw or "day_id" in sp):
            ex["day_id"] = A["day_id"]
        if A.get("index") is not None and "index" in sp:
            ex["index"] = A["index"]
        from augur_engine import rolls as R
        with R.roll_context(None, A["index"], 300):                # the synthetic bars: no roll (as _sb_direct)
            res = fn(A["open"], A["high"], A["low"], A["close"], **ex, **params, return_trades=True)
        if not isinstance(res, dict):
            return repr(res)
        return (_sb_norm_trades(res), sorted((k, repr(v)) for k, v in res.items()
                                             if k != "trades" and isinstance(v, (int, float, str, bool, type(None)))))
    for i, (A, what) in enumerate(((S, "the synthetic bars"), (S2, "a mirrored copy of them"),
                                   (S, "the synthetic bars again"))):
        if sig(shared, A) != sig(mod.run_backtest, A):
            return ("STATE BETWEEN RUNS (review round 4): run %d of one module (on %s) differs from a fresh run on the "
                    "same bars - the plugin keeps state from one run_backtest call to the next (a module-level cache, "
                    "a mutable default, a container reached through an alias). The Auto-Validate runs every trial in "
                    "one process, so one trial's answer would leak into the next: keep every container local to "
                    "run_backtest" % (i + 1, what))
    return None


def _sb_contract(mod, src, req, out):
    import numpy as np
    from augur_engine.engine import run_backtest
    problems, warns = [], []
    if not isinstance(getattr(mod, "STRATEGY_NAME", None), str):
        problems.append("STRATEGY_NAME must be a str")
    dp = getattr(mod, "DEFAULT_PARAMS", None)
    ranged = []
    if not isinstance(dp, dict) or not dp:
        problems.append("DEFAULT_PARAMS must be a non-empty dict")
        dp = {}
    for k, v in dp.items():
        if not isinstance(v, dict) or "default" not in v:
            problems.append("DEFAULT_PARAMS[%r] needs a dict with 'default'" % k)
            continue
        typ = v.get("type", "float")
        if typ in ("int", "float"):
            try:
                lo, hi, st, de = float(v["min"]), float(v["max"]), float(v.get("step", 0)), float(v["default"])
            except (KeyError, TypeError, ValueError):
                problems.append("knob %r: int/float knobs need numeric min, max, step, default" % k)
                continue
            if not (lo <= de <= hi):
                problems.append("knob %r: default %s outside [%s, %s]" % (k, de, lo, hi))
            if st <= 0:
                problems.append("knob %r: step must be > 0" % k)
            if hi > lo:
                ranged.append(k)
        elif typ in ("str", "bool"):
            opts = v.get("options", [True, False] if typ == "bool" else None)
            if not opts or v["default"] not in opts:
                problems.append("knob %r: str knobs need 'options' that contain the default" % k)
            elif len(opts) > 1:
                warns.append("knob %r offers %d options - the Auto-Validate searches EVERY option of a str/bool knob "
                             "(port trap 2); keep fidelity knobs to one option" % (k, len(opts)))
        else:
            problems.append("knob %r: type must be int, float, str or bool" % k)
    if dp and not ranged:
        problems.append("no numeric knob has max > min - a PINNED file cannot be Auto-Validated (house rule)")
    searched = searched_knobs(dp)
    if len(searched) > SEARCHED_KNOBS_MAX:
        problems.append("%d searched knobs (%s): the contract and the look-ahead audit check EVERY knob the "
                        "Auto-Validate searches at its min / max and options - at most %d. Pin the rest (min == max, "
                        "or one option)" % (len(searched), ", ".join(searched), SEARCHED_KNOBS_MAX))
    rs = getattr(mod, "ROLL_SIGNAL", None)
    if rs is not None and str(rs).lower() not in ("difference", "ratio", "raw"):
        problems.append("ROLL_SIGNAL must be 'difference', 'ratio' or 'raw'")
    fn = getattr(mod, "run_backtest", None)
    sig = inspect.signature(fn)
    names = list(sig.parameters)
    if names[:4] != ["opens", "highs", "lows", "closes"] and len([p for p in sig.parameters.values()
                                                                    if p.default is inspect._empty]) < 4:
        problems.append("run_backtest must take (opens, highs, lows, closes, ...) first")
    if "return_trades" not in sig.parameters and not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        problems.append("run_backtest needs a return_trades keyword")
    for k in dp:
        if k not in sig.parameters and not any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
            problems.append("knob %r is not a run_backtest keyword" % k)
    out["knobs_ranged"] = ranged
    if problems:
        out.update(ok=False, problems=problems, warnings=warns)
        return
    params = _sb_defaults(mod)

    def well_formed(r, label, n_bars):
        if r is None:
            return
        if not isinstance(r, dict):
            problems.append("%s: run_backtest returned %s, not a dict or None" % (label, type(r).__name__))
            return
        miss = _REQUIRED_KEYS - set(r)
        if miss:
            problems.append("%s: result is missing %s" % (label, sorted(miss)))
        for t in r.get("trades") or []:
            if not isinstance(t, (list, tuple)) or len(t) < 5:
                problems.append("%s: every trade must be (entry_bar, exit_bar, pnl_points, side, entry_price)" % label)
                break
            e, x, p, s, px = t[:5]
            if not (0 <= int(e) <= int(x) < n_bars):
                problems.append("%s: trade bars out of order / range %r" % (label, tuple(t[:2])))
                break
            if int(s) not in (1, -1) or not np.isfinite(float(p)) or not np.isfinite(float(px)):
                problems.append("%s: trade %r has a bad side / pnl / price" % (label, tuple(t[:5])))
                break
    # synthetic battery (tests/test_strategy_contract.py's checks)
    S = _sb_synthetic()
    a = run_backtest(mod, arrays=S, params=params, return_trades=True)
    well_formed(a, "synthetic", len(S["close"]))
    b = run_backtest(mod, arrays=S, params=params, return_trades=True)
    if (a is None) != (b is None) or (a and _sb_norm_trades(a) != _sb_norm_trades(b)):
        problems.append("synthetic: two identical runs gave different trades (non-deterministic)")
    else:
        st = _sb_state_check(mod, S, params)                     # review round 4: no state between runs (MEMO2)
        if st:
            problems.append(st)
    if a and a.get("trades"):
        cut = int((S["day_id"] < 45).sum())
        T = {k: (v[:cut] if k in ("open", "high", "low", "close", "volume", "day_id", "index") else v)
             for k, v in S.items()}
        tr = run_backtest(mod, arrays=T, params=params, return_trades=True)
        early = {(t[0], t[1], round(t[2], 6)) for t in _sb_norm_trades(tr) if t[1] < cut}
        for t in _sb_norm_trades(a):
            if t[1] < cut and (t[0], t[1], round(t[2], 6)) not in early:
                problems.append("synthetic: a trade closing at bar %d changed when later bars were removed "
                                "(look-ahead)" % t[1])
                break
    out["synthetic_trades"] = len((a or {}).get("trades") or [])
    # real-data smoke on the pinned master: the PRE-walk-forward bars only (counts reported, never P&L)
    smoke_to = req.get("smoke_to", SMOKE_TO)
    if smoke_to >= WF0:
        raise RuntimeError("the contract smoke must end before the walk-forward stretch starts (%s)" % WF0)
    m, A = _sb_load(req, DATA_FROM, smoke_to)
    cost = float(req["cost_pts"])
    r = run_backtest(mod, arrays=A, params=params, cost_pts=cost, return_trades=True)
    well_formed(r, "real smoke", len(A["close"]))
    yrs = max((A["index"][-1] - A["index"][0]).days / 365.25, 1e-9)
    n_sm = len((r or {}).get("trades") or [])
    out["smoke"] = {"master": m.get("filename"), "bars": int(len(A["close"])), "from": str(A["index"][0]),
                    "to": str(A["index"][-1]), "trades": n_sm, "years": round(yrs, 3),
                    "trades_per_year": round(n_sm / yrs, 1),
                    "roll": ((r or {}).get("_meta") or {}).get("roll_stamp", {}).get("signal_method")}
    if not n_sm:
        warns.append("real smoke: no trades %s..%s with the default knobs" % (DATA_FROM, smoke_to))
    # TTM #144: the FIRST-SIGNAL-BAR contract - no entry may fill before the pre-registered in-session bar (defaults:
    # a hard failure with the offending entries; a knob corner that moves it is a warning)
    fsb = req.get("first_signal_bar")
    tf_req = req.get("timeframe")
    if fsb is not None:
        v = first_bar_violations(_sb_norm_trades(r if isinstance(r, dict) else None), A["day_id"], A["index"], int(fsb),
                                 tf=tf_req)
        out["first_signal_bar"] = {k: v[k] for k in ("first_signal_bar", "checked", "n", "earliest_session_bar",
                                                     "index_by")}
        if v["n"]:
            out["first_signal_bar_violations"] = v["examples"]
            problems.append("FIRST-SIGNAL-BAR CONTRACT (TTM #144): %d of %d smoke entries (%s..%s, default knobs) fill "
                            "at an in-session bar before the proposal's first_signal_bar %d (the earliest at bar %s) - "
                            "e.g. %s" % (v["n"], v["checked"], DATA_FROM, smoke_to, int(fsb), v["earliest_session_bar"],
                                         "; ".join("%s session bar %d" % (x["time"], x["session_bar"])
                                                   for x in v["examples"][:3])))
    # MANAGER #160b/#162: every smoke entry fills at the stated bar's stated price point, and a time stop of N bars exits
    # at the close of entry bar + N (default knobs - a time-stop knob moves N at its corners)
    smoke_trades = _sb_norm_trades(r if isinstance(r, dict) else None)
    ef = req.get("entry_fill")
    if ef:
        v = entry_fill_violations(smoke_trades, A, ef, tf_req)
        out["entry_fill"] = {k: v[k] for k in ("at", "bar", "checked", "n")}
        if v["n"]:
            out["entry_fill_violations"] = v["examples"]
            problems.append("ENTRY-FILL CONTRACT (MANAGER #160b/#162): %d of %d smoke entries (%s..%s, default knobs) do "
                            "not fill at %s - e.g. %s" % (v["n"], v["checked"], DATA_FROM, smoke_to,
                                                         entry_fill_label(ef), "; ".join(
                                                             "%s: %s" % (x["time"], x["why"]) for x in v["examples"][:3])))
    ts = req.get("time_stop_bars")
    if ts is not None:
        v = time_stop_violations(smoke_trades, A, ts, cost_pts=cost)
        out["time_stop"] = {k: v[k] for k in ("time_stop_bars", "checked", "n", "held_past", "at_time_stop",
                                              "effective_time_stop")}
        if v["n"]:
            # the offending trades for EVERY shape (review round 4: a pattern failure returned none to Qwen)
            out["time_stop_violations"] = (v["examples"] + v["pattern_examples"])[:8]
            out["time_stop_patterns"] = v["pattern"]
            problems.append("TIME-STOP CONTRACT (MANAGER #160b/#162): the stated time stop is %s; on the smoke (%s..%s, "
                            "default knobs) %s" % (time_stop_label(ts), DATA_FROM, smoke_to, "; ".join(
                                (["%d of %d trades are held past it (e.g. %s)" % (
                                    v["held_past"], v["checked"], "; ".join("%s -> %s, %d bars" % (
                                        x["entry_time"], x["exit_time"], x["bars_held"]) for x in v["examples"][:2]))]
                                 if v["held_past"] else []) + v["pattern"])))
    # every searched knob value - each ranged knob at its min and its max, each other option of a multi-option str / bool
    # knob (the validate will search there). TTM #144: the first-signal-bar contract holds for the SEARCHED rule too - a
    # knob value that fills before first_signal_bar is a hard failure (the validate would pick it), not a warning.
    # Review round 4: so does the entry fill's price point (fill_knob: entries at the bar's CLOSE at fill_q=1.0 passed)
    corners, fsb_corners, fsb_corner_bad, ef_corners, ef_corner_bad = [], [], [], [], []
    ef_at = (ef or {}).get("at") if (ef or {}).get("at") in ("open", "close") else None
    for k, val in searched_values(dp):
        p2 = dict(params)
        p2[k] = val
        try:
            rr = run_backtest(mod, arrays=A, params=p2, cost_pts=cost, return_trades=True)
            well_formed(rr, "%s=%s" % (k, p2[k]), len(A["close"]))
            corners.append("%s=%s: %d trades" % (k, p2[k], len((rr or {}).get("trades") or [])))
            rt = _sb_norm_trades(rr if isinstance(rr, dict) else None)
            if fsb is not None:
                vc = first_bar_violations(rt, A["day_id"], A["index"], int(fsb), limit=2, tf=tf_req)
                fsb_corners.append({"knob": k, "value": p2[k], "checked": vc["checked"], "n": vc["n"],
                                    "earliest_session_bar": vc["earliest_session_bar"]})
                if vc["n"]:
                    fsb_corner_bad.append({"knob": k, "value": p2[k], "n": vc["n"], "checked": vc["checked"],
                                           "earliest_session_bar": vc["earliest_session_bar"],
                                           "examples": vc["examples"]})
            if ef_at:                                    # the price point only (a knob may move a fixed entry bar)
                ve = entry_fill_violations(rt, A, {"at": ef_at, "bar": None}, tf_req, limit=3)
                ef_corners.append({"knob": k, "value": p2[k], "checked": ve["checked"], "n": ve["n"]})
                if ve["n"]:
                    ef_corner_bad.append({"knob": k, "value": p2[k], "n": ve["n"], "checked": ve["checked"],
                                          "examples": ve["examples"]})
        except Exception as e:                                   # noqa: BLE001
            problems.append("crashes with %s=%s (the validate searches there): %s: %s"
                            % (k, p2[k], type(e).__name__, str(e)[:160]))
    out["corners"] = corners
    if ef_at:
        out["entry_fill_corners"] = ef_corners
    if ef_corner_bad:
        out["entry_fill_corner_violations"] = ef_corner_bad
        problems.append("ENTRY-FILL CONTRACT (MANAGER #160b/#162) at the knob values the Auto-Validate searches: %s - "
                        "every entry must fill at %s for EVERY searched value, not only the defaults (a knob may not "
                        "switch the fill to the other price point)" % ("; ".join(
                            "%s=%s: %d of %d smoke entries (e.g. %s: %s)" % (
                                b["knob"], b["value"], b["n"], b["checked"], b["examples"][0]["time"],
                                b["examples"][0]["why"]) for b in ef_corner_bad[:4]), entry_fill_label(ef)))
    if fsb is not None:
        out["first_signal_bar_corners"] = fsb_corners
    if fsb_corner_bad:
        out["first_signal_bar_corner_violations"] = fsb_corner_bad
        problems.append("FIRST-SIGNAL-BAR CONTRACT (TTM #144) at the knob values the Auto-Validate searches: %s - the "
                        "pre-registered first_signal_bar %d must hold for EVERY searched value (narrow the knob's "
                        "range, or pre-register the earliest bar a searched value can fill on)"
                        % ("; ".join("%s=%s: %d of %d smoke entries before it (earliest at bar %s)"
                                     % (b["knob"], b["value"], b["n"], b["checked"], b["earliest_session_bar"])
                                     for b in fsb_corner_bad[:4]), int(fsb)))
    out.update(ok=not problems, problems=problems[:20], warnings=warns)


def _sb_direct(mod, A, params, root, tf):
    from augur_engine import rolls as R
    fn = mod.run_backtest
    sp = inspect.signature(fn).parameters
    has_kw = any(p.kind == p.VAR_KEYWORD for p in sp.values())
    ex = {}
    if A.get("volume") is not None and (has_kw or "volumes" in sp):
        ex["volumes"] = A["volume"]
    if A.get("day_id") is not None and (has_kw or "day_id" in sp):
        ex["day_id"] = A["day_id"]
    if A.get("index") is not None and "index" in sp:
        ex["index"] = A["index"]
    with R.roll_context(root, A["index"], tf):
        res = fn(A["open"], A["high"], A["low"], A["close"], **ex, **params, return_trades=True)
    return _sb_norm_trades(res if isinstance(res, dict) else None)


def _sb_perturb(A, k, kind, px, amp, vmed, phase):
    import numpy as np
    O, H, L, C = (np.array(A[x], dtype=float, copy=True) for x in ("open", "high", "low", "close"))
    V = np.array(A["volume"], dtype=float, copy=True) if A.get("volume") is not None else None
    n = len(C)
    if kind == "open":
        base = O[k]
        H[k] = L[k] = C[k] = O[k]
    elif kind == "intrabar":
        base = px
        C[k] = px
    else:
        base = C[k]
    if V is not None and kind in ("open", "intrabar"):
        V[k] = vmed * 0.37 + 1.0
    if k + 1 < n:
        m = n - (k + 1)
        sign = np.where(np.arange(m) % 2 == 0, 1.0, -1.0) * phase
        cl = base + sign * amp * 0.5
        op = base - sign * amp * 0.5
        O[k + 1:], C[k + 1:] = op, cl
        H[k + 1:] = np.maximum(op, cl) + amp * 0.25
        L[k + 1:] = np.minimum(op, cl) - amp * 0.25
        if V is not None:
            V[k + 1:] = vmed * 1.9 + 3.0
    B = dict(A, open=O, high=H, low=L, close=C)
    if V is not None:
        B["volume"] = V
    return B


def _sb_widen(A, k, px, amp, vmed, phase, lo_w, hi_w):
    """The intrabar perturbation, plus the fill bar's low pushed lower by lo_w and / or its high pushed higher by
    hi_w (x half the median range). A stop / limit LEVEL from bars <= k-1 still fills at the same price when the side
    it crossed is pushed further; a level built from bar k's own high / low (an ATR or range that includes the fill
    bar, a trailing extreme updated with bar k before the check) moves."""
    B = _sb_perturb(A, k, "intrabar", px, amp, vmed, phase)
    H, L = B["high"], B["low"]
    H[k] = H[k] + hi_w * amp * 0.5
    L[k] = L[k] - lo_w * amp * 0.5
    return B


def _sb_push(A, f, side, which, d, later=None, close_q=None, vol=None, keep=None, pen=0.0):
    """Bar f re-drawn as a ONE-WAY bar from its (unchanged) open. which='adverse': it trades only AGAINST the position -
    the adverse extreme (a long's low, a short's high) pushed d points beyond its own, the other extreme pulled in to
    the open; 'favourable': only WITH it, mirrored. So only the levels on the pushed side can be crossed on bar f (a
    stop-first / target-first order never flips the exit between two pushes). `keep` (an intrabar entry's fill price on
    bar f) stays inside the bar, and when the pulled-in extreme is the one the entry CROSSED (a buy stop above the open,
    a buy limit below it, mirrored for a sell) it stays past the fill by min(its own overshoot, pen): a stop / limit
    entry written with a strict test ('high > level') still fills - the crossing is what that entry legitimately read.
    close_q puts bar f's close that fraction of the way from the open to the pushed extreme, vol sets bar f's volume
    (bar f's close and volume did not exist at the fill either). With later=(amp, vmed) every bar AFTER f is replaced
    too (the _sb_perturb pattern around bar f's new close). Returns (arrays, 'low' | 'high')."""
    import numpy as np
    H = np.array(A["high"], dtype=float, copy=True)
    L = np.array(A["low"], dtype=float, copy=True)
    C = np.array(A["close"], dtype=float, copy=True)
    o = float(A["open"][f])
    pen = max(0.0, float(pen or 0.0))
    lower = (which == "adverse") == (side > 0)
    if lower:
        L[f] = float(A["low"][f]) - d
        H[f] = o if keep is None or keep <= o else max(keep, min(float(A["high"][f]), keep + pen))
        ext = L[f]
    else:
        H[f] = float(A["high"][f]) + d
        L[f] = o if keep is None or keep >= o else min(keep, max(float(A["low"][f]), keep - pen))
        ext = H[f]
    if close_q is not None:
        C[f] = o + float(close_q) * (ext - o)
    B = dict(A, high=H, low=L, close=C)
    if vol is not None and A.get("volume") is not None:
        V = np.array(A["volume"], dtype=float, copy=True)
        V[f] = float(vol)
        B["volume"] = V
    if later:
        B = _sb_perturb(B, f, "close", None, later[0], later[1], 1.0)
    return B, ("low" if lower else "high")


# TTM #145 entry-bar inputs: the first bar at risk is pushed by these many median bar ranges (a third depth runs only
# when the first two settle nothing - a wide stop / target, e.g. one from a daily range); the deeper pushes also replace
# every bar after it. Each push puts bar f's close at a different place (a fraction of the way from its open to the
# pushed extreme) and sets a different volume (x the median), so a level / size that reads them moves too.
ENTRY_BAR_PUSH = (10.0, 30.0, 90.0)
ENTRY_BAR_CLOSE_Q = (0.15, 0.85, 0.5)
ENTRY_BAR_VOL_X = (0.37, 1.9, 1.0)
ENTRY_BAR_KEEP_PEN = 0.25          # an intrabar entry's crossed extreme stays up to 0.25 median ranges past its fill
ENTRY_BAR_K = 6
ENTRY_BAR_CORNER_K = 2          # the same phase at every searched knob value (2 trades each; every knob - review round 4)


def _sb_entry_bar_cands(A, full, pick):
    """[(trade index, first bar at risk f, fill kind)] for the entry-bar phase: f = e for an entry filled at bar e's
    OPEN or INSIDE bar e (a stop / limit level: only the open and the level existed at the fill), f = e + 1 for a fill
    at bar e's CLOSE (an entry price equal to both the open and the close counts as a close fill - the lenient
    reading); f must be in the same session and not after the exit."""
    import numpy as np
    did = np.asarray(A["day_id"]) if A.get("day_id") is not None else None
    n = len(A["close"])
    out = []
    for j in pick:
        e, x, pnl, side, px = full[j]
        if side not in (1, -1) or px is None:
            continue
        ke = _sb_kind(px, e, A)
        if ke == "open" and abs(px - float(A["close"][e])) <= 1e-6 * max(1.0, abs(px)):
            ke = "close"                                         # open == close: ambiguous, read it as a close fill
        f = e + 1 if ke == "close" else e
        if f >= n or f > x or (did is not None and did[f] != did[e]):
            continue
        out.append((j, f, ke))
    return out


def _sb_entry_bar_inputs(mod, A, params, root, tf, full, pick, amp, vmed=1000.0, k_max=ENTRY_BAR_K, tag=""):
    """TTM #145: a stop, target or size set at ENTRY may only use what existed at the fill. A plugin reports only
    (entry, exit, pnl, side, price), so the levels and the size are read through the exit, on the FIRST BAR AT RISK f
    (_sb_entry_bar_cands: the fill bar for an open or intrabar fill, the next bar for a close fill). Bar f is re-drawn
    one-way from its unchanged open (_sb_push): its adverse extreme (then its favourable one) pushed ENTRY_BAR_PUSH
    median ranges, its close moved (ENTRY_BAR_CLOSE_Q) and its volume set (ENTRY_BAR_VOL_X) differently in each push;
    the deeper pushes also replace every bar after f. A level known at the fill is crossed by every push deep enough to
    reach it and fills at the SAME price with the SAME size (P&L) each time; a level or size that reads bar f's own
    high / low / close / volume (an ATR / range / volatility including the entry bar, a trailing extreme updated before
    the check, a stop anchored at the entry bar's close) or a bar after f (a centred / forward window) moves. Only EXITS
    ON BAR f AT A LEVEL are compared (an exit at bar f's close may read that close). Conclusive when two pushes exit
    there; a trade that exits there at a level on a push and not at all on bar f on the next, deeper push fails too, and
    so does a push that books bar f's (unchanged) OPEN when the real bars do not (a level known at the fill that is past
    that open books it on the real bars too; a stop hung off bar f's own favourable extreme or close - a chandelier
    raised with bar f before its check - is dragged past the open and books it on every push at the same P&L).
    No level exit on bar f = inconclusive (no failure): a rule with no stop / target on that bar - or a level that
    scales with bar f's own range by >= 1x, which can never be crossed on bar f, so its trades equal those of a rule that
    sets the level at bar f's close and checks it from the next bar (realisable). Returns (fails, checked, conclusive)."""
    cands = _sb_entry_bar_cands(A, full, pick)
    fails, conclusive = [], 0
    for j, f, ke in cands[:k_max]:
        e, x, pnl, side, px = full[j]
        tol = 1e-6 * max(1.0, abs(px))
        keep = px if ke == "intrabar" else None
        head = "%sENTRY-BAR INPUT at bar %d (%s fill %.4f), first bar at risk %d" % (tag, e, ke, px, f)
        o_f = float(A["open"][f])
        tol_o = 1e-6 * max(1.0, abs(o_f))
        # on the real bars, did the trade exit at bar f's OPEN (a level known at the fill that is already past it)?
        orig_at_open = x == f and abs(px + side * float(pnl) - o_f) <= tol_o
        failed, conc = False, False
        for which in ("adverse", "favourable"):
            prev = None                                  # the last push whose trade exited on bar f at a level
            for i, mult in enumerate(ENTRY_BAR_PUSH):
                B, ext = _sb_push(A, f, side, which, mult * amp, later=(amp, vmed) if i else None,
                                  close_q=ENTRY_BAR_CLOSE_Q[i], vol=vmed * ENTRY_BAR_VOL_X[i] + 1.0, keep=keep,
                                  pen=ENTRY_BAR_KEEP_PEN * amp)
                tr = _sb_direct(mod, B, params, root, tf)
                u = next((u for u in tr if u[0] == e and u[3] == side and abs((u[4] or 0) - px) <= tol), None)
                what = "bar %d's %s was pushed %.0f median ranges further (its close / volume moved)%s" % (
                    f, ext, mult, " and the bars after it were replaced" if i else "")
                if u is None:
                    fails.append("%s: the ENTRY itself changed when %s - the entry may not read the first bar at risk%s"
                                 % (head, what, " or any later bar" if i else ""))
                    failed = True
                    break
                xp = px + side * float(u[2])
                at_level = u[1] == f and abs(xp - float(B["close"][f])) > 1e-6 * max(1.0, abs(xp))
                if (ke != "intrabar" and u[1] == f and abs(xp - o_f) <= tol_o and not orig_at_open):
                    # bar f's open is unchanged by every push: a stop / target known at the fill that is past it books
                    # that open on the real bars too. Booking it only on a push = the level jumped past the open with
                    # bar f's own extreme / close / volume (a stop hung off the entry bar's high, then gap-through)
                    conc = True
                    fails.append("%s: the trade exits at bar %d's OPEN (%.4f) when %s, but not on the real bars - a "
                                 "stop / target known at the fill that is past that open exits there on the real bars "
                                 "too; this level moved past it with bar %d's own high / low / close / volume (or a "
                                 "bar after it)" % (head, f, o_f, what, f))
                    failed = True
                    break
                if prev is not None:
                    m1, u1 = prev
                    if at_level:
                        conc = True
                        p1, p2 = float(u1[2]), float(u[2])
                        if abs(p1 - p2) > 1e-6 * max(1.0, abs(p1), abs(p2)):
                            fails.append("%s: pushes of bar %d's %s by %.0f and %.0f median ranges both exit on bar %d "
                                         "at a level, but at %+.4f pt (exit %.4f) and %+.4f pt (exit %.4f) - the stop / "
                                         "target level or the size moved with that bar's own high / low / close / "
                                         "volume (or a bar after it)"
                                         % (head, f, ext, m1, mult, f, p1, px + side * p1, p2, px + side * p2))
                            failed = True
                        break
                    if u[1] != f:
                        conc = True
                        fails.append("%s: the trade exits on bar %d at a level when its %s is pushed %.0f median ranges "
                                     "but NOT on bar %d when it is pushed %.0f - a level known at the fill is crossed at "
                                     "least as early by the bigger push" % (head, f, ext, m1, f, mult))
                        failed = True
                        break
                elif at_level:
                    prev = (mult, u)
            if failed:
                break
        conclusive += int(conc)                                  # trades with at least one conclusive side
    return fails, len(cands[:k_max]), conclusive


# TTM's MOMDRIVE note (fix round 3): QL_MOMDRIVE's default made ONE trade in six years, so the audit sampled one trade
# and its leak (a chandelier raised with bar j's close before bar j is checked) hid. So every phase - the entry / exit
# perturbations, fill realism, the open-exit phase and the entry-bar phase - also runs at each ranged knob's min and max
# (the Auto-Validate searches there), and the OPEN-EXIT phase reads every trade whose exit filled at a later bar's open.
OPEN_EXIT_K, OPEN_EXIT_CORNER_K = 6, 2          # open-exit trades checked at the defaults / at each knob corner
LA_CORNER_K = 2                                # entry / exit perturbation trades at each knob corner (incl. 1 short hold)


def _sb_fill_realism(A, full):
    """Fills outside their bar's traded range (a gap-through stop must book the open; pnl = side x (exit - entry))."""
    import numpy as np
    H, L = np.asarray(A["high"], float), np.asarray(A["low"], float)
    n = len(H)
    bad = []
    for t in full:
        e, x, pnl, side, px = t
        if side not in (1, -1) or px is None:
            bad.append("trade %r has no side / entry price" % (t,))
            continue
        xp = px + side * pnl
        for bar, price, what in ((e, px, "entry"), (x, xp, "exit")):
            tol = 1e-6 * max(1.0, abs(price))
            if not (0 <= bar < n) or price < L[bar] - tol or price > H[bar] + tol:
                bad.append("%s %.4f at bar %d outside its range [%.4f, %.4f]" % (what, price, bar,
                                                                                   L[min(max(bar, 0), n - 1)],
                                                                                   H[min(max(bar, 0), n - 1)]))
    return bad


_LA_WHAT = {"open": "the bar's high/low/close/volume and every later bar",
            "intrabar": "the bar's close/volume and every later bar", "close": "every later bar"}


def _sb_perturb_trades(mod, A, params, root, tf, full, pick, amp, vmed, tag=""):
    """The entry / exit phases for the trades `pick` of `full`: for each fill, everything that did not exist at it is
    replaced in two opposite phases (an intrabar fill's crossed extreme is also pushed further, a stop-type exit's other
    extreme widened) and the trade must not change. Returns the failure lines (prefixed with `tag`)."""
    fails = []
    for j in pick:
        e, x, pnl, side, px = full[j]
        kind_e = _sb_kind(px, e, A)
        xp = px + side * pnl
        kind_x = _sb_kind(xp, x, A)
        tries = [(_sb_perturb(A, e, kind_e, px, amp, vmed, ph), _LA_WHAT[kind_e]) for ph in (1.0, -1.0)]
        if kind_e == "intrabar":
            cs, _ = _sb_cross_side(px, e, A, side, "entry")
            tries.append((_sb_widen(A, e, px, amp, vmed, 1.0, 2.0 * (cs == "low"), 2.0 * (cs == "high")),
                          "the bar's %s was pushed further past the fill (the level still crossed)" % cs))
        for B, what in tries:
            pe = _sb_direct(mod, B, params, root, tf)
            if not any(u[0] == e and u[3] == side and abs((u[4] or 0) - px) <= 1e-6 * max(1, abs(px)) for u in pe):
                fails.append("%sENTRY at bar %d (%s fill %.4f) changed when %s" % (
                    tag, e, kind_e, px, what + (" were replaced" if what in _LA_WHAT.values() else "")))
                break
        tries = [(_sb_perturb(A, x, kind_x, xp, amp, vmed, ph), _LA_WHAT[kind_x]) for ph in (1.0, -1.0)]
        if kind_x == "intrabar":
            cs, stop_like = _sb_cross_side(xp, x, A, side, "exit")
            tries.append((_sb_widen(A, x, xp, amp, vmed, 1.0, 2.0 * (cs == "low"), 2.0 * (cs == "high")),
                          "the bar's %s was pushed further past the fill (the level still crossed)" % cs))
            if stop_like:
                other = "high" if cs == "low" else "low"
                tries.append((_sb_widen(A, x, xp, amp, vmed, 1.0, 10.0 * (other == "low"), 10.0 * (other == "high")),
                              "the bar's %s was widened (the stop still crossed: a stop level may not use the fill "
                              "bar's own %s, and a same-bar target may not be checked before the stop)"
                              % (other, other)))
        for B, what in tries:
            px_ = _sb_direct(mod, B, params, root, tf)
            if not any(u[0] == e and u[1] == x and u[3] == side and abs(u[2] - pnl) <= 1e-6 * max(1, abs(pnl))
                       for u in px_):
                fails.append("%sEXIT at bar %d (%s fill %.4f) changed when %s" % (
                    tag, x, kind_x, xp, what + (" were replaced" if what in _LA_WHAT.values() else "")))
                break
    return fails


def _sb_pick(full, k_n, n_short):
    """k_n trades spread through `full`, plus up to n_short of the shortest holds (exits on the entry bar first)."""
    import numpy as np
    if not full:
        return [], []
    pick = set(np.linspace(0, len(full) - 1, min(k_n, len(full))).round().astype(int).tolist()) if k_n else set()
    holds = sorted(range(len(full)), key=lambda i: (int(full[i][1]) - int(full[i][0]), i))
    short = [i for i in holds if int(full[i][1]) - int(full[i][0]) <= 1][:200]
    if not n_short:
        extra = []
    elif short:
        extra = [short[int(round(q))] for q in np.linspace(0, len(short) - 1, min(n_short, len(short)))]
    else:
        extra = holds[:min(2, n_short)]
    return sorted(pick | set(extra)), extra


def _sb_open_exit_cands(A, full):
    """Indexes of the trades whose EXIT filled at the OPEN of a bar after the entry bar (that bar not a doji)."""
    out = []
    for i, (e, x, pnl, side, px) in enumerate(full):
        if side not in (1, -1) or px is None or x <= e:
            continue
        xp = px + side * pnl
        o, c = float(A["open"][x]), float(A["close"][x])
        if abs(xp - o) <= 1e-6 * max(1.0, abs(xp)) and abs(o - c) > 1e-6 * max(1.0, abs(o)):
            out.append(i)
    return out


def _sb_open_exit_phase(mod, A, params, root, tf, full, amp=None, k_max=OPEN_EXIT_K, tag=""):
    """TTM's MOMDRIVE note: an EXIT filled at bar j's OPEN (j after the entry bar) may not depend on what bar j did
    after its open - a stop / target known before bar j is either already past that open (it books the open whatever bar
    j does next) or not. Bar j is PULLED IN, never widened, so no new level can be crossed: its close moved to its
    adverse extreme (a long's low, a short's high), then its favourable extreme pulled in to max / min(open, close) -
    open, adverse extreme, volume and the later bars unchanged - and the trade must still exit at bar j's open with the
    same P&L. A trailing stop / chandelier raised with bar j's close (or favourable extreme) BEFORE bar j is checked, then
    booked at the open as a 'gap-through', moves. A legit stop-first rule whose bar opened through its target does not:
    the adverse side of the bar is never extended (fix round 3: a one-way re-draw that widened it failed the clean
    stop-first template). Returns (fails, checked)."""
    import numpy as np
    cands = _sb_open_exit_cands(A, full)
    if not cands or not k_max:
        return [], 0
    pick = sorted({cands[int(q)] for q in np.linspace(0, len(cands) - 1, min(k_max, len(cands))).round()})
    fails = []
    for j in pick:
        e, x, pnl, side, px = full[j]
        o, hi, lo, cl = (float(A[k][x]) for k in ("open", "high", "low", "close"))
        adverse_close = lo if side > 0 else hi
        variants = [("its close was moved to its %s" % ("low" if side > 0 else "high"), {"close": adverse_close})]
        if side > 0 and hi > max(o, cl):
            variants.append(("its high was pulled in to max(open, close)", {"high": max(o, cl)}))
        if side < 0 and lo < min(o, cl):
            variants.append(("its low was pulled in to min(open, close)", {"low": min(o, cl)}))
        for how, chg in variants:
            if all(abs(v - float(A[k][x])) <= 1e-12 for k, v in chg.items()):
                continue
            B = dict(A)
            for k, v in chg.items():
                arr = np.array(A[k], dtype=float, copy=True)
                arr[x] = v
                B[k] = arr
            tr = _sb_direct(mod, B, params, root, tf)
            u = next((u for u in tr if u[0] == e and u[3] == side and abs((u[4] or 0) - px) <= 1e-6 * max(1, abs(px))),
                     None)
            what = "bar %d's %s (its open and %s unchanged)" % (x, how.replace("its ", "", 1),
                                                               "low" if side > 0 else "high")
            if u is None:
                fails.append("%sENTRY at bar %d changed when %s - bar %d is after the entry: the entry read a later bar"
                             % (tag, e, what, x))
                break
            if u[1] != x or abs(float(u[2]) - float(pnl)) > 1e-6 * max(1.0, abs(float(pnl))):
                fails.append("%sEXIT at bar %d (filled at its OPEN %.4f) changed when %s: now exits at bar %d, %+.4f pt "
                             "(was %+.4f) - an exit booked at a bar's open may not depend on that bar's close / %s "
                             "(a trailing stop / chandelier raised with bar %d's close or extreme BEFORE its check, then "
                             "booked at the open)" % (tag, x, o, what, u[1], float(u[2]), float(pnl),
                                                      "high" if side > 0 else "low", x))
                break
    return fails, len(pick)


def _sb_corner_audit(mod, A, params, root, tf, amp, vmed, eb_k=ENTRY_BAR_CORNER_K, la_k=LA_CORNER_K,
                     oe_k=OPEN_EXIT_CORNER_K):
    """Every look-ahead phase at EVERY searched knob value (searched_values: each ranged numeric knob's min and max,
    each other option of a multi-option str / bool knob - the Auto-Validate searches there; TTM: a 1-trade default
    hides leaks): fill realism, the entry / exit perturbations (la_k trades incl. a short hold), the open-exit phase
    (oe_k) and the entry-bar phase (eb_k). The entry-bar phase is why it started (TTM #145): a level that scales with
    the entry bar's own range by a knob (stop = stop_frac x 1.5 x that range) is >= 1x at the default - never crossed
    on that bar, realisable - but < 1x at a searched corner, where it leaks. Review round 4: it covered only the first
    4 ranged knobs (a leak at the 5th knob's max passed) and never a bool / str option (a same-bar trail switched on by
    trail_on=True passed). Returns (entry-bar fails, other fails, [{knob, value, trades, checked, conclusive,
    perturbed, open_exits}])."""
    import numpy as np
    dp = getattr(mod, "DEFAULT_PARAMS", None) or {}
    eb_fails, la_fails, rows = [], [], []
    for k, val in searched_values(dp, params):
        p2 = dict(params, **{k: val})
        tag = "at %s=%s: " % (k, val)
        full2 = _sb_direct(mod, A, p2, root, tf)
        row = {"knob": k, "value": val, "trades": len(full2), "checked": 0, "conclusive": 0, "perturbed": 0,
               "open_exits": 0}
        rows.append(row)
        if not full2:
            continue
        bad = _sb_fill_realism(A, full2)
        if bad:
            la_fails.append("%sfill realism: %d of %d fills outside their bar's range (e.g. %s)"
                            % (tag, len(bad), 2 * len(full2), bad[0]))
        if la_k:
            pick, _ = _sb_pick(full2, max(1, la_k - 1), 1)
            row["perturbed"] = len(pick)
            la_fails += _sb_perturb_trades(mod, A, p2, root, tf, full2, pick, amp, vmed, tag=tag)
        if oe_k:
            f3, row["open_exits"] = _sb_open_exit_phase(mod, A, p2, root, tf, full2, amp, oe_k, tag=tag)
            la_fails += f3
        cands = _sb_entry_bar_cands(A, full2, range(len(full2))) if eb_k else []
        if cands:
            pick = sorted({cands[int(q)][0] for q in np.linspace(0, len(cands) - 1, min(eb_k, len(cands))).round()})
            f2, row["checked"], row["conclusive"] = _sb_entry_bar_inputs(mod, A, p2, root, tf, full2, pick, amp,
                                                                         vmed, eb_k, tag=tag)
            eb_fails += f2
    return eb_fails, la_fails, rows


def _sb_cross_side(px, k, A, side, what):
    """Which extreme of bar k an intrabar fill crossed: 'low' or 'high'; and whether an exit is stop-like."""
    o = float(A["open"][k])
    below = px < o
    if what == "exit":            # long: below the open = a stop (crossed the low); above = a target (crossed the high)
        stop_like = below if side > 0 else not below
        return ("low" if below else "high"), stop_like
    return ("low" if below else "high"), False      # entry: buy stop above (high) / buy limit below (low), mirrored


def _sb_kind(px, k, A):
    tol = 1e-6 * max(1.0, abs(px))
    if abs(px - float(A["open"][k])) <= tol:
        return "open"
    if abs(px - float(A["close"][k])) <= tol:
        return "close"
    return "intrabar"


def _sb_lookahead(mod, src, req, out):
    import numpy as np
    from augur_engine import rolls as R
    problems, warns, notes = [], [], []
    # (a) the house static file checks, on this one file (efa._load is pointed at the sandboxed module)
    sys.path.insert(0, os.path.join(SHARED, "tools"))
    import exec_feasibility_audit as EFA
    EFA._load = lambda _p: mod
    for fn in EFA.CHECKS:
        try:
            for level, msg in fn(mod.__file__, src):
                (problems if level == "fail" else warns).append("exec_feasibility_audit %s: %s" % (fn.__name__, msg))
        except Exception as e:                                   # noqa: BLE001
            warns.append("exec_feasibility_audit %s crashed: %s" % (fn.__name__, e))
    # (b) perturbation audit on real bars (synthetic_days: seeded synthetic bars, for the offline tests)
    params = _sb_defaults(mod)
    if req.get("synthetic_days"):
        A, root, tf = _sb_synthetic(int(req["synthetic_days"])), None, 300
    else:
        m, A = _sb_load(req, req["la_from"], req["la_to"])
        root = R.roll_root(req["instrument"])
        tf = R.tf_seconds_of(m, R.epoch_seconds(A["index"]))
    full = _sb_direct(mod, A, params, root, tf)
    H, L = np.asarray(A["high"], float), np.asarray(A["low"], float)
    n = len(H)
    out["la_window"] = {"from": str(A["index"][0]), "to": str(A["index"][-1]), "bars": n, "trades": len(full)}
    if not full:
        problems.append("no trades in the audit window %s..%s with the default knobs - nothing to audit"
                        % (req.get("la_from"), req.get("la_to")))
        out.update(ok=False, problems=problems, warnings=warns)
        return
    # (c) fill realism: every fill inside its bar's traded range (a gap-through stop books the open, not the level)
    bad = _sb_fill_realism(A, full)
    out["fills_checked"] = 2 * len(full)
    if bad:
        problems.append("fill realism: %d of %d fills sit outside their bar's range (e.g. %s) - a stop on a bar that "
                        "OPENED past it must book the open; pnl must be side x (exit - entry) in points"
                        % (len(bad), 2 * len(full), "; ".join(bad[:3])))
    amp = float(np.median(H - L)) or 1.0
    vmed = float(np.median(A["volume"])) if A.get("volume") is not None else 1000.0
    # (d) entry / exit perturbations on k sampled trades, stratified: up to 4 of the shortest holds too (exits on the
    # entry bar first) - a level built from the entry bar's own range only shows on a trade that exits on that bar (the
    # 10-15 QL_ES_MOMBREAK v4 ATR)
    pick, extra = _sb_pick(full, int(req.get("la_k", 8)), 4)
    fails = _sb_perturb_trades(mod, A, params, root, tf, full, pick, amp, vmed)
    out["perturbed_trades"] = len(pick)
    out["short_holds_sampled"] = len(set(extra))
    if fails:
        problems.append("LOOK-AHEAD: %d of %d sampled trades changed when information that did not exist at the "
                        "fill was replaced: %s. A decision at bar k may use bars <= k only; fill at bar k's close or "
                        "bar k+1's open; an intrabar stop/limit may use the bar's high/low, never its close or volume."
                        % (len(fails), len(pick), "; ".join(fails[:3])))
    # (d2) OPEN EXITS (TTM's MOMDRIVE note): every trade whose exit filled at a later bar's OPEN is a candidate - that
    # bar's high / low / close may not move the exit (a trailing stop raised with the bar's close before its check)
    oe_fails, out["open_exits_checked"] = _sb_open_exit_phase(mod, A, params, root, tf, full, amp,
                                                              int(req.get("oe_k", OPEN_EXIT_K)))
    out["open_exit_candidates"] = len(_sb_open_exit_cands(A, full))
    if oe_fails:
        problems.append("LOOK-AHEAD (open exits, TTM / QL_MOMDRIVE): %d of %d trades: %s. An exit filled at bar j's open "
                        "may use only bars <= j-1 (and the open itself): update a trailing stop / chandelier with bar "
                        "j's high / low / close AFTER bar j's stop check." % (len(oe_fails), out["open_exits_checked"],
                                                                             "; ".join(oe_fails[:2])))
    # (e) ENTRY-BAR INPUTS (TTM #145): the phases above check the entry tuple and each exit bar; a stop / target / size
    # set at entry from the entry bar's own high / low / close / volume (open or intrabar fill) or from a bar after a
    # close fill only showed when a sampled trade happened to exit on that bar. This phase forces the first bar at risk
    # to hit the levels - at the defaults, then at each ranged knob's min and max (the Auto-Validate searches there).
    eb_fails, eb_n, eb_conc = _sb_entry_bar_inputs(mod, A, params, root, tf, full, pick, amp, vmed,
                                                   int(req.get("eb_k", ENTRY_BAR_K)))
    out["entry_bar_checked"], out["entry_bar_conclusive"] = eb_n, eb_conc
    if eb_n and not eb_conc:
        warns.append("entry-bar inputs (TTM #145): none of the %d sampled trades exited on its first bar at risk at a "
                     "price level under any push, so the stop / target levels on that bar were not exercised - fine "
                     "for a rule with no stop or target on that bar" % eb_n)
    # (f) KNOB CORNERS (fix round 3, TTM's MOMDRIVE note: a 1-trade default hides leaks): every phase above again at
    # EVERY searched knob value (review round 4: all ranged knobs, not the first 4, and every option of a multi-option
    # str / bool knob). A plugin with more searched knobs than the audit covers fails hard. corner_knobs=0 (or the
    # older eb_corner_knobs=0) switches the pass off - offline tests only; write_plugin never sends it
    cla = []
    dp = getattr(mod, "DEFAULT_PARAMS", None) or {}
    if int(req.get("corner_knobs", req.get("eb_corner_knobs", 1))):
        searched = searched_knobs(dp)
        if len(searched) > SEARCHED_KNOBS_MAX:
            problems.append("%d searched knobs (%s): the look-ahead audit runs every phase at EVERY searched knob value "
                            "and covers at most %d knobs - pin the rest (min == max, or one option)"
                            % (len(searched), ", ".join(searched), SEARCHED_KNOBS_MAX))
        else:
            cf, cla, rows = _sb_corner_audit(
                mod, A, params, root, tf, amp, vmed,
                eb_k=ENTRY_BAR_CORNER_K if int(req.get("eb_k", ENTRY_BAR_K)) else 0,
                la_k=int(req.get("la_corner_k", LA_CORNER_K)), oe_k=int(req.get("oe_corner_k", OPEN_EXIT_CORNER_K)))
            out["entry_bar_corners"] = rows
            out["searched_knobs"] = searched
            eb_fails += cf
    if eb_fails:
        problems.append("LOOK-AHEAD (entry-bar inputs, TTM #145): %d trades: %s. A stop, target or size set at "
                        "entry may use only what existed at the fill: bars <= k-1 and bar k's open for a fill at bar "
                        "k's open (never bar k's high / low / close / volume); bars <= k-1, bar k's open and the fill "
                        "level for a stop / limit fill inside bar k; bars <= k for a fill at bar k's close."
                        % (len(eb_fails), "; ".join(eb_fails[:2])))
    if cla:
        problems.append("LOOK-AHEAD at the knob values the Auto-Validate searches (each ranged knob's min / max; the "
                        "defaults alone can hide a leak): %d findings: %s" % (len(cla), "; ".join(cla[:3])))
    out.update(ok=not problems, problems=problems[:12], warnings=warns[:12], notes=notes)


def _sb_stage_a(mod, src, req, out):
    from augur_engine.engine import run_backtest
    lo, hi, stretch = req.get("load_from", DATA_FROM), req.get("load_to", WF1), req.get("stretch", "wf")
    if hi > WF1 or hi >= LB0:
        raise RuntimeError("LOCKBOX GUARD: a Stage A may not load past %s (asked %s)" % (WF1, hi))
    if stretch == "pre_wf" and hi >= WF0:
        raise RuntimeError("PRE-WF GUARD: the pre-WF Stage A may not load a walk-forward row (asked to %s, WF starts "
                           "%s)" % (hi, WF0))
    m, A = _sb_load(req, lo, hi)
    if stretch == "pre_wf" and str(A["index"][-1].date()) >= WF0:
        raise RuntimeError("PRE-WF GUARD: the loaded data reach %s" % A["index"][-1])
    t0 = time.time()
    params = _sb_defaults(mod)
    r = run_backtest(mod, arrays=A, params=params, cost_pts=float(req["cost_pts"]), return_trades=True)
    trades = _sb_norm_trades(r if isinstance(r, dict) else None)
    meta = (r or {}).get("_meta") or {}
    rs = meta.get("roll_stamp") or {}
    n = len(A["close"])
    out.update(ok=True, trades=trades, params=params, secs=round(time.time() - t0, 1), stretch=stretch,
               entry_times=[str(A["index"][t[0]])[:19] if 0 <= t[0] < n else None for t in trades],
               bars=int(n), first=str(A["index"][0]), last=str(A["index"][-1]),
               fingerprint=A.get("fingerprint"), master=m.get("filename"),
               roll={k: rs.get(k) for k in ("calendar", "kind", "signal_method", "method_source", "warning",
                                            "crossings", "registry") if k in rs})


def _sb_guard(mod, src, req, out):
    sys.path.insert(0, os.path.join(SHARED, "tools"))
    import queue_guard as QG
    from augur_engine import data as D
    m = _sb_master(req)
    fm = D.find_master(req["instrument"], req["timeframe"], req["session"], req["source"])
    if not fm or fm.get("filename") != m.get("filename"):
        raise RuntimeError("queue_guard's lookup (%s) is not the pinned master %s" % ((fm or {}).get("filename"),
                                                                                     m.get("filename")))
    orig = QG.load_strategy
    QG.load_strategy = lambda x: mod if x is mod else orig(x)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        g = QG.guard(mod, {}, instrument=req["instrument"], timeframe=req["timeframe"], session=req["session"],
                     source=req["source"], cost_pts=float(req["cost_pts"]), mult=float(req["mult"]),
                     date_from=req["date_from"], date_to=req["date_to"], split=req["split"], label=req["name"])
    finally:
        sys.stdout = old
    out.update(ok=True, verdict=g.get("verdict"), exit_code=g.get("exit_code"), reasons=g.get("reasons"),
               printout=buf.getvalue()[-20000:])


def _sb_synthetic_mode(mod, src, req, out):
    from augur_engine.engine import run_backtest
    S = _sb_synthetic(int(req.get("days", 20)))
    r = run_backtest(mod, arrays=S, params=_sb_defaults(mod), return_trades=True)
    out.update(ok=True, trades=_sb_norm_trades(r if isinstance(r, dict) else None))


_SB_MODES = {"contract": _sb_contract, "lookahead": _sb_lookahead, "stage_a": _sb_stage_a, "guard": _sb_guard,
             "synthetic": _sb_synthetic_mode}


def sandbox_main(req_path, out_path):
    """CHILD side: load the plugin armed, run one mode, write the JSON result. Never trusts the plugin's own output."""
    out = {"ok": False, "error": None, "blocked": [], "peak_gb": None}
    try:
        with open(req_path, encoding="utf-8") as f:
            req = json.load(f)
        out["mode"] = req.get("mode")
        sys.path.insert(0, SHARED)
        import numpy                                             # noqa: F401 - preloaded before arming
        import pandas                                            # noqa: F401
        import augur_engine                                      # noqa: F401
        import augur_engine.engine                               # noqa: F401
        from augur_engine import rolls                           # noqa: F401
        # MANAGER #156, loaded before arming. Review round 4: EXACTLY the file the parent pinned (the prereg's path and
        # LF sha256 for a Stage A), checked here - a calendar changed after the prereg refuses the run
        cal = calendar_module(req.get("calendar_path"), req.get("calendar_sha")) if req.get("calendar_path") \
            else calendar_module()
        out["calendar_module"] = getattr(cal, "__file__", None)
        out["calendar_sha"] = lf_sha256_file(out["calendar_module"]) if out["calendar_module"] else None
        import site
        roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(os.__file__),
                 os.path.join(SHARED, "augur_engine"), os.path.join(SHARED, "tools", "data"),
                 os.path.dirname(os.path.dirname(numpy.__file__)), os.path.dirname(os.path.dirname(pandas.__file__))}
        try:
            roots.update(site.getsitepackages())
            roots.add(site.getusersitepackages())
        except Exception:
            pass
        _SB["read_roots"] = [r for r in roots if r]
        _SB["real_import"] = builtins.__import__
        sys.addaudithook(_sb_hook)
        _sb_watchdog(int(float(req.get("mem_gb", SANDBOX_MEM_GB)) * 1024 ** 3))
        mod, src = _sb_load_plugin(req["plugin_path"], req["plugin_sha"])
        _SB_MODES[req["mode"]](mod, src, req, out)
    except Exception as e:                                       # noqa: BLE001
        out["ok"] = False
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:1500])
        out["traceback"] = traceback.format_exc()[-4000:]
    out["blocked"] = list(_SB["blocked"])
    if out["blocked"]:
        out["ok"] = False
        out["error"] = (out.get("error") or "") + " | SANDBOX BLOCKED: " + "; ".join(out["blocked"][:5])
    try:
        import psutil
        mi = psutil.Process().memory_info()
        out["peak_gb"] = round(float(getattr(mi, "peak_wset", 0) or mi.rss) / 1024 ** 3, 3)
    except Exception:
        pass
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, default=str)
    return 0


# ------------------------------------------------------------------------------------------------ the SANDBOX (parent)
_SECRET_ENV_RX = re.compile(r"KEY|SECRET|TOKEN|PASS|CRED|NTFY|ALPACA|APCA|WEBULL|GOOGLE_APPLICATION", re.I)


def sandbox_env():
    env = {k: v for k, v in os.environ.items() if not _SECRET_ENV_RX.search(k)}
    env.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", NUMEXPR_NUM_THREADS="1",
               AUGUR_TRIAL_CACHE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               NUMBA_NUM_THREADS="1", EDGELOG_VALIDATE_WORKERS="1")
    return env


def run_sandbox(mode, plugin_path, plugin_sha, req_extra, workdir, timeout=None, label=None):
    """Run one sandbox mode in a child process; returns its JSON (or an error dict). Never imports the plugin here."""
    os.makedirs(workdir, exist_ok=True)
    tag = label or mode
    req = dict(req_extra, mode=mode, plugin_path=plugin_path, plugin_sha=plugin_sha)
    if not req.get("calendar_path"):                             # the calendar the child loads, pinned by LF sha256
        req["calendar_path"], req["calendar_sha"] = calendar_pin()
    rp = os.path.join(workdir, "sandbox_%s_req.json" % tag)
    op = os.path.join(workdir, "sandbox_%s_out.json" % tag)
    if os.path.exists(op):
        os.remove(op)
    jdump(rp, req)
    flags = 0x08000000 if os.name == "nt" else 0                 # CREATE_NO_WINDOW
    t0 = time.time()
    with open(os.path.join(workdir, "sandbox_%s.log" % tag), "w", encoding="utf-8") as logf:
        try:
            p = subprocess.run([sys.executable, "-B", HARNESS_PATH, "_sandbox", rp, op], cwd=workdir,
                               env=sandbox_env(), stdout=logf, stderr=subprocess.STDOUT,
                               timeout=timeout or SANDBOX_TIMEOUT.get(mode, 900), creationflags=flags)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "TIMEOUT: the plugin ran longer than %ss in mode %s" % (
                timeout or SANDBOX_TIMEOUT.get(mode, 900), mode), "secs": round(time.time() - t0, 1)}
    res = jload(op, None)
    if res is None:
        why = "MEMORY LIMIT: the sandbox passed %.0f GB and was killed" % req.get("mem_gb", SANDBOX_MEM_GB) \
            if rc == 86 else "the sandbox exited %s without a result" % rc
        try:
            tail = open(os.path.join(workdir, "sandbox_%s.log" % tag), encoding="utf-8").read()[-1500:]
        except OSError:
            tail = ""
        return {"ok": False, "error": why, "log_tail": tail, "secs": round(time.time() - t0, 1)}
    res["secs_wall"] = round(time.time() - t0, 1)
    return res


# ------------------------------------------------------------------------------------------------ engine helpers (parent)
def _eng():
    """The house engine modules (shared checkout first, so the master registry is the real one). When augur_engine
    is already imported (a test session), that copy is used and sys.path is left alone."""
    if "augur_engine" not in sys.modules and SHARED not in sys.path and os.path.isdir(SHARED):
        sys.path.insert(0, SHARED)
    from augur_engine import book as B, book_sizing as BS, drawdowns as DD, data as D
    return B, BS, DD, D


def pinned_master(instrument, timeframe):
    key = (str(instrument).upper(), str(timeframe))
    if key not in MASTERS:
        raise ToolRefused("no pinned master for %s %s - choose one of %s" % (
            key[0], key[1], ", ".join("%s %s" % k for k in MASTERS)))
    pin = MASTERS[key]
    _, _, _, D = _eng()
    rows = [m for m in D.list_masters() if m.get("filename") == pin["filename"]]
    if len(rows) != 1:
        raise RuntimeError("pinned master %s: %d registry rows (run from a machine with the shared registry)"
                           % (pin["filename"], len(rows)))
    m = rows[0]
    if (str(m.get("instrument")), str(m.get("timeframe")), str(m.get("source"))) != (key[0], key[1], pin["source"]):
        raise RuntimeError("pinned master %s does not match its pin %r" % (pin["filename"], pin))
    return m


def assert_pre_wf(index):
    """The pre-WF guard: nothing on or after the walk-forward start may be in memory for the pre-WF Stage A."""
    last = str(index[-1].date()) if hasattr(index[-1], "date") else str(index[-1])[:10]
    if not (PREWF1 < WF0):
        raise AssertionError("configuration error: pre-WF end %s is not before the WF start %s" % (PREWF1, WF0))
    if last >= WF0:
        raise AssertionError("PRE-WF GUARD: data reach %s, on or after the walk-forward start %s" % (last, WF0))
    return last


def assert_wf_only(index):
    """The lockbox guard: nothing on or after the lockbox start may be in memory for a Stage A."""
    last = str(index[-1].date()) if hasattr(index[-1], "date") else str(index[-1])[:10]
    if not (WF1 < LB0):
        raise AssertionError("configuration error: WF end %s is not before the lockbox start %s" % (WF1, LB0))
    if last > WF1 or last >= LB0:
        raise AssertionError("LOCKBOX GUARD: data reach %s, past the walk-forward end %s (lockbox starts %s)"
                             % (last, WF1, LB0))
    return last


ONE_EPISODE_NOT_TESTABLE = "NOT TESTABLE"


def four_numbers(trades, arrays, mult, wf0=WF0, wf1=WF1, label="WF", cost_pts=None):
    """THE FOUR NUMBERS, computed here from the engine's trade list and the master's own bars - never from model text.

    trades: [(entry_bar, exit_bar, pnl_points_net, side, entry_price)] in the coordinates of `arrays`.
    The valued-daily series is augur_engine.book._mtm_increments (open trades valued at each session's last close),
    on every session of the stretch (zeros included); ROC @ $30k, Sortino and DD % from peak are
    augur_engine.book_sizing.stretch_reading; DD5 + the one-episode flag are augur_engine.drawdowns.dd5.
    MANAGER #160a: one_episode is 'NOT TESTABLE' (not False) when DD5 is built from a single episode (dd5_n <= 1) or
    the net curve never makes a new high - one drawdown cannot be compared with others. With cost_pts (the round-trip
    cost the engine charged each trade, points) the gross edge per trade is reported against it (MANAGER 10-16 15:45):
    gross / trade = net / trade + cost, and the gross / cost ratio."""
    import numpy as np
    import pandas as pd
    B, BS, DDM, _ = _eng()
    idx = pd.DatetimeIndex(arrays["index"])
    assert_wf_only(idx)
    if label == "PRE-WF" or str(wf1) < WF0:
        if not str(wf1) < WF0:
            raise AssertionError("PRE-WF GUARD: a pre-WF stretch must end before %s (asked %s)" % (WF0, wf1))
        assert_pre_wf(idx)                       # no walk-forward row may even be in memory for the pre-WF numbers
    sess = np.asarray(idx.tz_localize(None).normalize().values if idx.tz is not None else idx.normalize().values,
                      dtype="datetime64[D]")
    lo, hi = np.datetime64(wf0), np.datetime64(wf1)
    keep = [t for t in trades if lo <= sess[int(t[0])] <= hi]
    inc, marked, unmarked = B._mtm_increments(sess, arrays["close"], [(tuple(t), 1.0) for t in keep], float(mult),
                                              1.0)
    days = np.unique(sess[(sess >= lo) & (sess <= hi)])
    daily = pd.Series(0.0, index=pd.DatetimeIndex(days))
    for d, usd in inc:
        ts = pd.Timestamp(d)
        if ts in daily.index:
            daily.loc[ts] += float(usd)
    r = BS.stretch_reading(daily, wf0, wf1)
    d5 = DDM.dd5(daily)
    pts = np.array([float(t[2]) for t in keep], float)
    yrs = (daily.index[-1] - daily.index[0]).days / 365.25 if len(daily) > 1 else float("nan")
    gw, gl = float(pts[pts > 0].sum()) if len(pts) else 0.0, float(-pts[pts < 0].sum()) if len(pts) else 0.0
    # MANAGER #160a: a single drawdown episode (or a curve that never makes a new high: one drawdown from the start)
    # cannot show that ONE episode drives the drawdown - not testable, which is not the same as 'False'
    never_high = not bool((np.cumsum(daily.to_numpy(float)) > 1e-9).any()) if len(daily) else True
    one_ep, one_why = bool(d5["one_episode"]), None
    if int(d5["n"]) <= 1 or never_high:
        one_ep = ONE_EPISODE_NOT_TESTABLE
        one_why = ("the net curve never makes a new high (one drawdown from the start)" if never_high else
                   "DD5 is built from %d episode%s" % (int(d5["n"]), "" if int(d5["n"]) == 1 else "s"))
    out = {"stretch": "%s %s..%s" % (label, wf0, wf1), "sessions": int(len(daily)), "years": round(yrs, 3),
           "trades": int(len(keep)), "trades_per_year": round(len(keep) / yrs, 1) if yrs and yrs > 0 else None,
           "net_usd": round(float(daily.sum()), 2),
           "roc_30k": (r or {}).get("roc_30k"), "sortino": (r or {}).get("sortino"),
           "dd_pct_peak": (r or {}).get("dd_pct_peak"), "max_dd_usd": (r or {}).get("max_drawdown"),
           "dd5_usd": d5["dd5_usd"], "dd5_n": d5["n"], "one_episode": one_ep,
           "net_pts_per_trade": round(float(pts.mean()), 4) if len(pts) else None,
           "net_usd_per_trade": round(float(daily.sum()) / len(pts), 2) if len(pts) else None,
           "win_rate": round(100.0 * float((pts > 0).sum()) / len(pts), 2) if len(pts) else None,
           "profit_factor": round(gw / gl, 4) if gl > 0 else None, "mtm_marked": marked, "mtm_unmarked": unmarked,
           "dropped_before_wf": int(len(trades) - len(keep)), "mult": float(mult)}
    if one_why:
        out["one_episode_why"] = one_why
    if cost_pts is not None:                                     # MANAGER 10-16 15:45: gross edge vs the cost
        c = float(cost_pts)
        g = round(float(pts.mean()) + c, 4) if len(pts) else None
        out.update(cost_pts=c, gross_pts_per_trade=g,
                   gross_cost_ratio=round(g / c, 3) if (g is not None and c > 0) else None)
    if r is not None and abs(float(r["max_drawdown"]) - float(d5["max_dd"])) > 0.02:
        out["warning"] = "stretch_reading DD %s != dd5 worst episode %s" % (r["max_drawdown"], d5["max_dd"])
    return out


def fmt_four(nm):
    """The four numbers as text - built only from a numbers dict computed by four_numbers()."""
    if not nm:
        return "ROC@30k - | DD5 - | DD% - | Sortino - (no curve)"

    def f(v, spec):
        return "-" if v is None else format(v, spec)
    oe = nm.get("one_episode")
    ep = " 1 EPISODE" if oe is True else (" one-episode NOT TESTABLE" if oe == ONE_EPISODE_NOT_TESTABLE else "")
    usd = nm.get("net_usd_per_trade")
    per = ("" if nm.get("net_pts_per_trade") is None else
           " | net/trade %+.3f pt (%s$%s)" % (nm["net_pts_per_trade"], "-" if (usd or 0) < 0 else "+",
                                              format(abs(usd or 0.0), ",.2f")))
    gross = ("" if nm.get("gross_pts_per_trade") is None or nm.get("cost_pts") is None else
             " | gross/trade %+.3f pt vs cost %.3f pt (gross/cost %s)" % (
                 nm["gross_pts_per_trade"], nm["cost_pts"], f(nm.get("gross_cost_ratio"), ".2f")))
    return ("ROC@30k %s | DD5 $%s (n=%s%s) | DD%% %s%% | Sortino %s | trades %s (%s/yr)%s%s"
            % (f(nm.get("roc_30k"), ".2f"), f(nm.get("dd5_usd"), ",.0f"), nm.get("dd5_n", "-"), ep,
               f(nm.get("dd_pct_peak"), ".2f"), f(nm.get("sortino"), ".3f"), f(nm.get("trades"), ","),
               f(nm.get("trades_per_year"), ".1f"), per, gross))


def is_scalp_idea(idea):
    pr = idea.get("proposal") or {}
    return idea.get("source") == "scalper" or bool(re.search(r"scalp", "%s %s %s" % (
        pr.get("name"), pr.get("hypothesis"), pr.get("mechanism")), re.I))


def sanity_check(nm, idea, where="in the PRE-WF window"):
    """None when the pre-WF trade count is plausible, else why it looks like a BROKEN plugin (MANAGER #139)."""
    pr = idea.get("proposal") or {}
    tpy = float((nm or {}).get("trades_per_year") or 0.0)
    n = int((nm or {}).get("trades") or 0)
    stated = float(pr.get("trades_per_year") or 0.0)
    why = []
    if stated > 0 and tpy < stated / SANITY_RATIO:
        why.append("more than %.0fx below the stated %s/yr" % (SANITY_RATIO, pr.get("trades_per_year")))
    if tpy < SANITY_MIN_TPY:
        why.append("under %.0f a year" % SANITY_MIN_TPY)
    if is_scalp_idea(idea) and tpy < SANITY_MIN_TPY_SCALP:
        why.append("under %.0f a year for a scalp idea" % SANITY_MIN_TPY_SCALP)
    if not why:
        return None
    return "%d trade%s %s (%.1f/yr): %s" % (n, "" if n == 1 else "s", where, tpy, "; ".join(why))


def smoke_rate_check(smoke, idea):
    """TTM #155's cheap check at contract-smoke time: the plugin's own trade COUNT on the smoke bars against the stated
    prior, before any prereg. The broken-plugin rule (MANAGER #139) run early - more than 3x BELOW the stated rate,
    under 20 a year, or under 100 a year for a scalp idea - is a HARD gate failure (the PRE-WF check would only send it
    back after the prereg, burning a fix retry); more than 3x ABOVE the stated rate is flagged (the map reads the
    counted rate). Returns {stated_per_year, smoke_per_year, ratio, hard, flag}."""
    pr = (idea or {}).get("proposal") or {}
    tpy = (smoke or {}).get("trades_per_year")
    stated = float(pr.get("trades_per_year") or 0.0)
    out = {"stated_per_year": stated, "smoke_per_year": tpy, "hard": None, "flag": None,
           "ratio": round(float(tpy) / stated, 2) if (tpy is not None and stated > 0) else None}
    if tpy is None:
        return out
    hard = sanity_check({"trades": (smoke or {}).get("trades") or 0, "trades_per_year": tpy}, idea,
                        where="on the contract smoke %s..%s" % (DATA_FROM, SMOKE_TO))
    if hard:
        out["hard"] = hard
    elif stated > 0 and float(tpy) > SANITY_RATIO * stated:
        out["flag"] = ("the rule trades %.1f a year on the contract smoke, more than %.0fx the stated %s/yr - check that "
                       "the entry fires only when the rule says (the map reads the counted rate)"
                       % (float(tpy), SANITY_RATIO, pr.get("trades_per_year")))
    return out


def sanity_sessions(arrays, trades, k=SANITY_SESSIONS, rows=SANITY_ROWS):
    """Real sessions of bars for Qwen to check its entry condition against: the biggest up day, the biggest down day
    and a median-range day among the sessions where the plugin did NOT trade (all sessions if it traded every day)."""
    import numpy as np
    import pandas as pd
    did = np.asarray(arrays["day_id"])
    idx = pd.DatetimeIndex(arrays["index"])
    O, H, L, C = (np.asarray(arrays[x], float) for x in ("open", "high", "low", "close"))
    V = np.asarray(arrays["volume"], float) if arrays.get("volume") is not None else None
    n = len(did)
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
    ends = np.r_[starts[1:], n]
    traded = {}
    for t in trades:
        e = int(t[0])
        if 0 <= e < n:
            traded.setdefault(int(did[e]), []).append(t)
    stats = [(int(did[a]), int(a), int(b), float(C[b - 1] - O[a]), float(H[a:b].max() - L[a:b].min()))
             for a, b in zip(starts, ends) if b - a >= 2]
    pool = [x for x in stats if x[0] not in traded] or stats
    if not pool:
        return []
    picks = [(max(pool, key=lambda x: x[3]), "the biggest UP day (close - open) with no trade from your plugin"),
             (min(pool, key=lambda x: x[3]), "the biggest DOWN day with no trade from your plugin"),
             (sorted(pool, key=lambda x: x[4])[len(pool) // 2], "a median-range day with no trade from your plugin")]
    out, seen = [], set()
    for (d, a, b, move, rng), why in picks[:k]:
        if d in seen:
            continue
        seen.add(d)
        head = list(range(a, min(b, a + rows - 8)))
        tail = list(range(max(a + rows - 8, b - 8), b)) if b - a > rows else []
        sel = head + [i for i in tail if i not in head]
        out.append({"date": str(idx[a].date()), "why": why, "bars_in_session": b - a,
                    "move_pts": round(move, 2), "range_pts": round(rng, 2),
                    "your_trades_this_session": [[int(t[0]) - a, int(t[1]) - a, round(float(t[2]), 2), int(t[3])]
                                                 for t in traded.get(d, [])],
                    "columns": ["i (bar of the session)", "time", "open", "high", "low", "close", "volume"],
                    "bars": [[i - a, idx[i].strftime("%H:%M"), round(O[i], 2), round(H[i], 2), round(L[i], 2),
                              round(C[i], 2), int(V[i]) if V is not None else None] for i in sel],
                    "omitted_bars": (b - a) - len(sel)})
    return out


def trades_by_year(trades, arrays):
    import pandas as pd
    idx = pd.DatetimeIndex(arrays["index"])
    out = {}
    for y in sorted(set(idx.year)):
        out[str(y)] = 0
    for t in trades:
        if 0 <= int(t[0]) < len(idx):
            out[str(idx[int(t[0])].year)] = out.get(str(idx[int(t[0])].year), 0) + 1
    return out


def _one_episode_why(nm, stretch):
    """The reason a numbers dict fails 'not one episode', or None (only False passes - NOT TESTABLE does not)."""
    oe = (nm or {}).get("one_episode")
    if oe is True:
        return "one episode drives the %sdrawdown (worst > 1.3 x DD5)" % stretch
    if oe is not False:
        return "one-episode NOT TESTABLE (%s) - it must be False" % ((nm or {}).get("one_episode_why") or "not computed")
    return None


def promotion_bar(nm):
    """(promote, why) - MANAGER 10-16 15:45 (amends #134): the WF Stage A runs only if the PRE-WF GROSS edge per trade
    (before cost, points) >= the round-trip cost (points) AND the net pre-WF ROC@30k > 0 AND one-episode is False (NOT
    TESTABLE does not pass)."""
    if nm is None or nm.get("roc_30k") is None:
        return False, "NOT PROMOTED: no pre-WF numbers (no trades or no drawdown)"
    why = []
    g, c = nm.get("gross_pts_per_trade"), nm.get("cost_pts")
    if g is None or c is None:
        why.append("no gross / trade against the cost (the cost was not recorded)")
    elif float(g) < PROMOTE_GROSS_COST_RATIO * float(c):
        why.append("pre-WF gross/trade %+.3f pt < cost %.3f pt (gross/cost %.2f)" % (g, c, float(g) / float(c)))
    if float(nm["roc_30k"]) <= PROMOTE_NET_ROC_MIN:
        why.append("pre-WF net ROC@30k %.2f <= 0" % nm["roc_30k"])
    oe = _one_episode_why(nm, "pre-WF ")
    if oe:
        why.append(oe)
    if why:
        return False, "NOT PROMOTED: " + "; ".join(why)
    return True, ("PROMOTED: pre-WF gross/trade %+.3f pt >= cost %.3f pt (gross/cost %.2f), net ROC@30k %.2f > 0, "
                  "not one episode" % (g, c, float(g) / float(c), nm["roc_30k"]))


def validate_bar(nm, peak_gb=None):
    """(met, why) - the house bar for a Qwen-lab Auto-Validate, read only from computed numbers."""
    why = []
    if nm is None or nm.get("roc_30k") is None:
        return False, "no Stage A numbers"
    if float(nm["roc_30k"]) < VALIDATE_BAR_ROC:
        why.append("WF ROC@30k %.2f < %.0f" % (nm["roc_30k"], VALIDATE_BAR_ROC))
    oe = _one_episode_why(nm, "")
    if oe:
        why.append(oe)
    if int(nm.get("trades") or 0) < MIN_WF_TRADES:
        why.append("%s WF trades < %d (house minimum)" % (nm.get("trades"), MIN_WF_TRADES))
    if peak_gb is not None and float(peak_gb) > PEAK_RAM_GB_MAX:
        why.append("peak RAM %.1f GB > %.1f GB per process (a validate runs 3 folds)" % (peak_gb, PEAK_RAM_GB_MAX))
    return (not why), ("MET: ROC@30k >= %.0f, not one episode, >= %d WF trades" % (VALIDATE_BAR_ROC, MIN_WF_TRADES)
                       if not why else "NOT MET: " + "; ".join(why))


# ------------------------------------------------------------------------------------------------ POWER FIRST (mapcheck_f)
_MF_CACHE = {}


def mapcheck_prior(name, prior_sharpe, trades_per_year):
    """tools/mapcheck_f.py's generator and rules on one stated prior. Returns the computed read + verdict."""
    if "MF" not in _MF_CACHE:
        sys.path.insert(0, os.path.join(SHARED, "tools"))
        if SHARED not in sys.path:
            sys.path.insert(0, SHARED)
        import mapcheck_f as MF
        x, dates = MF.book463()
        SW, _, V = MF.M12.build_stretches(x, dates)
        _MF_CACHE.update(MF=MF, SW=SW, V=V)
    MF, SW, V = _MF_CACHE["MF"], _MF_CACHE["SW"], _MF_CACHE["V"]
    s_mid = float(prior_sharpe)
    p = dict(name=name, n=int(round(trades_per_year)), s_mid=s_mid, s_sd=max(0.30, 0.5 * s_mid), rho_dd=0.0,
             rho_out="zero", tails="t3", vol="clustered")
    k = 1000 + zlib.crc32(str(name).encode()) % 100000
    seed = [MF.SEED0, k, 0]
    a = MF.read(SW, V, p, MF.M, seed, MF.M12.BAR_WF_ROC, MF.M12.BAR_WF_SORT)
    lift_min = float(getattr(MF, "LIFT_MIN", _MAP_LIFT_MIN))
    closes = a["own_med"] < 8 and a["own_p15"] < 0.10 and a["rho_med"] > -0.15
    if p["n"] < 50:
        verdict = "GREYED - cannot be a seat on its own (< 50 trades a year)"
    elif closes:
        verdict = "CLOSE at draft (own-ROC rule)"
    elif a["lift"] < lift_min:
        verdict = "CLOSE at draft (P(book lift) %.0f%% < %.0f%%)" % (100 * a["lift"], 100 * lift_min)
    else:
        verdict = "CLEARS - worth a prereg"
    return {"verdict": verdict, "clears": verdict.startswith("CLEARS"), "prior": {k2: p[k2] for k2 in
                                                                                    ("n", "s_mid", "s_sd", "rho_dd",
                                                                                     "rho_out", "tails", "vol")},
            "seed": seed, "draws": MF.M, "own_wf_roc_median": round(a["own_med"], 2),
            "p_own_roc_ge_15": round(a["own_p15"], 3), "p_lift_463": round(a["lift"], 3),
            "book_roc_median": round(a["book_roc_med"], 2), "rho_dd_realised": round(a["rho_med"], 3),
            "rules": "mapcheck_f: < 50 trades/yr GREYED; median own ROC < 8 AND P(>=15) < 10%% closes; P(lift #463, WF) "
                     "< %.0f%% closes" % (100 * lift_min)}


# ------------------------------------------------------------------------------------------------ posting
def post_manager(text, frm="QWEN-LAB"):
    """Post to MANAGER through the house inbox tool (MANAGER exists, so no --new; a sender without an inbox only warns)."""
    p = subprocess.run([sys.executable, os.path.join(HERE, "chat_inbox.py"), "post", "MANAGER", "--from", frm, text],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                       creationflags=0x08000000 if os.name == "nt" else 0)
    m = re.search(r"posted #(\d+)", p.stdout or "")
    if p.returncode != 0 or not m:
        raise RuntimeError("chat_inbox post failed (rc %s): %s %s" % (p.returncode, (p.stdout or "")[-300:],
                                                                       (p.stderr or "")[-300:]))
    return int(m.group(1))


def idea_costs(idea, instrument):
    """(cost points per round trip, $ per point): the scalp hunt's basis for the scalper ask, the house RTH cost else."""
    table = COSTS_SHORT_HOLD if (idea or {}).get("source") == "scalper" else COSTS
    return table[str(instrument).upper()]


def source_ref(idea):
    """'shelf #8 Goulding 2023' / "the owner's scalper ask" / "Qwen's own idea" - harness text for posts."""
    src = (idea or {}).get("source") or "shelf"
    if src == "shelf":
        sh = idea.get("shelf") or {}
        return "shelf #%s %s %s" % (sh.get("n", "-"), (sh.get("authors") or "").split(",")[0], sh.get("year", ""))
    return SOURCE_LABEL.get(src, src)


def _safe_name(s):
    return re.sub(r"[^A-Z0-9_]", "", str(s or "").upper())[:48]


def schedule_check(stated, counted):
    """The rule's own trade COUNT on the pre-walk-forward bars against the proposal (schedule facts, never P&L).
    The map GREYS a leg under 50 trades a year and reads the counted rate when the stated one is off by more than 2x."""
    out = {"stated_per_year": stated, "counted_per_year_pre_wf": counted, "ok": True, "notes": []}
    if counted is None:
        out["notes"].append("no count (no smoke trades)")
        return out
    if counted >= 1 and stated and not (0.5 <= float(stated) / float(counted) <= 2.0):
        out["ok"] = False
        out["notes"].append("the rule trades %.1f a year on %s..%s, not the %s you stated - the map will read %.1f"
                            % (counted, DATA_FROM, SMOKE_TO, stated, counted))
    if (counted if counted >= 1 else float(stated or 0)) < 50:
        out["ok"] = False
        out["notes"].append("under 50 trades a year the map GREYS the leg (it cannot be a seat on its own); the verdict "
                            "is recorded, and the Stage A still runs")
    return out


def plugin_traceback(res, path):
    """The traceback lines that point into the plugin file (file / line / code), for Qwen to fix its own bug."""
    tb = str((res or {}).get("traceback") or "")
    base = os.path.basename(path or "")
    lines = tb.splitlines()
    out = []
    for i, ln in enumerate(lines):
        if base and base in ln and "line" in ln:
            m = re.search(r"line (\d+), in (\S+)", ln)
            code = lines[i + 1].strip() if i + 1 < len(lines) else ""
            out.append("%s line %s in %s: %s" % (base, m.group(1) if m else "?", m.group(2) if m else "?", code))
    return out[-4:]


_LA_HINT = {
    ("EXIT", "open"): "the EXIT is filled at bar %d's OPEN, yet the decision changed when that bar's high/low/close "
                      "changed - so the exit decision read bar %d itself. Usual cause: a trailing stop / ATR / band "
                      "updated with the bar's high, low or close BEFORE the exit check on that bar, or an exit signal "
                      "computed on the bar's close but filled at its open. Fix: compute every level from bars <= k-1; "
                      "at bar k either fill at the open on a decision taken at bar k-1's close, or fill a stop "
                      "intrabar at its level when bar k's low/high crosses it (at the open if the bar opens through "
                      "it); update the trailing level with bar k's high/low only AFTER the bar-k exit check.",
    ("ENTRY", "open"): "the ENTRY is filled at bar %d's OPEN, yet it changed when that bar's high/low/close changed - "
                       "the entry signal read bar %d itself. Decide on bars <= k-1 and fill at bar k's open, or "
                       "decide on bar k's close and fill at bar k's close (or bar k+1's open).",
    ("EXIT", "intrabar"): "the EXIT is filled inside bar %d at a price level, yet it changed when that bar's close / "
                          "volume changed - an intrabar stop or limit at bar %d may use only its level (from bars "
                          "<= k-1) and the bar's open/high/low.",
    ("ENTRY", "intrabar"): "the ENTRY is filled inside bar %d at a price level, yet it changed when that bar's close / "
                           "volume changed - an intrabar stop or limit entry at bar %d may use only its level (from "
                           "bars <= k-1) and the bar's open/high/low.",
    ("EXIT", "close"): "the EXIT is filled at bar %d's close, yet it changed when LATER bars were replaced - the rule "
                       "reads bars after %d (shift(-1), a centred window, a whole-series statistic, a future index).",
    ("ENTRY", "close"): "the ENTRY is filled at bar %d's close, yet it changed when LATER bars were replaced - the rule "
                        "reads bars after %d (shift(-1), a centred window, a whole-series statistic, a future index).",
}


_LA_WIDE_HINT = ("the fill at bar %d is an intrabar stop / limit whose LEVEL moved when bar %d's own high or low "
                 "moved - the level read the fill bar itself. Usual causes: an ATR / range that includes the fill bar "
                 "(for a stop checked on the ENTRY bar: an ATR over bars up to and including the entry bar), a "
                 "trailing extreme updated with the bar's high / low before the check, or a same-bar target checked "
                 "before the stop. Fix: build every level from bars <= k-1 (for the entry bar: bars before it), "
                 "update trailing extremes after the check, and check the stop before any same-bar target.")


_LA_ENTRYBAR_HINT = {
    "open": "the trade entered at bar %d's OPEN has a stop / target / size that moved with bar %d's own high / low / "
            "close / volume (or with a later bar) - which did not exist when it filled at that open. Usual cause: an "
            "ATR / range / volatility window that INCLUDES the entry bar (a rolling window ending at k, tr[k] or "
            "|c[k] - c[k-1]| in the mean, max(high[a:k+1])) used for a level checked on the entry bar, or for the "
            "size; a stop anchored at c[k] instead of the entry price; or a centred / forward window. Fix: build every "
            "level and the size from bars <= k-1 and bar k's open (atr[k-1], the range of the bars BEFORE k); update "
            "trailing levels with bar k's high / low / close only AFTER bar k's stop / target check.",
    "intrabar": "the trade entered INSIDE bar %d at a stop / limit level has a stop / target / size that moved with bar "
                "%d's own high / low / close / volume - only the bar's open and the crossed level existed at that "
                "fill. Usual cause: an ATR / range including the entry bar (h[k] - l[k] in the mean) for a stop "
                "checked on the entry bar. Fix: levels and size from bars <= k-1, bar k's open and the entry level "
                "(atr[k-1]).",
    "close": "the trade entered at bar %d's CLOSE has a stop / target / size that moved with bar %d's high / low / "
             "close / volume (or a later bar) - bars AFTER the fill. Usual cause: a centred or forward window "
             "(rolling(..., center=True), shift(-1), c[k+1] in a volatility), or a level computed from the next bar. "
             "Fix: levels and size from bars <= k at a close fill; the first bar after the fill may only be checked "
             "against them.",
}


_LA_OPEN_EXIT_HINT = ("the EXIT booked at bar %d's OPEN changed when that bar's high / low / close moved (its open did "
                      "not) - the exit decision read bar %d itself. Usual cause: a trailing stop / chandelier updated "
                      "with bar j's close (or high / low) BEFORE bar j's stop check, so a strong bar drags the stop "
                      "past its own open and the 'gap-through' books the open. Fix: check bar j against the stop built "
                      "from bars <= j-1 first (book the open only when the bar OPENS past that stop), and update the "
                      "trailing level with bar j's close / extreme AFTER the check.")


def lookahead_hints(problems):
    """Concrete fix hints for the perturbation audit's findings (text only - no numbers)."""
    out = []
    for p in problems or []:
        for m in re.finditer(r"EXIT at bar (\d+) \(filled at its OPEN", str(p)):
            h = _LA_OPEN_EXIT_HINT % (int(m.group(1)), int(m.group(1)))
            if h not in out:
                out.append(h)
        for m in re.finditer(r"ENTRY-BAR INPUT at bar (\d+) \((open|intrabar|close) fill [-0-9.]+\), first bar at "
                             r"risk (\d+)", str(p)):
            h = _LA_ENTRYBAR_HINT[m.group(2)] % (int(m.group(1)), int(m.group(3)))
            if h not in out:
                out.append(h)
        for m in re.finditer(r"(?:ENTRY|EXIT) at bar (\d+) \(intrabar fill [-0-9.]+\) changed when the bar's "
                             r"(?:low|high) was (?:pushed|widened)", str(p)):
            h = _LA_WIDE_HINT % (int(m.group(1)), int(m.group(1)))
            if h not in out:
                out.append(h)
        for m in re.finditer(r"(ENTRY|EXIT) at bar (\d+) \((open|intrabar|close) fill", str(p)):
            h = _LA_HINT.get((m.group(1), m.group(3)))
            if h:
                h = h % (int(m.group(2)), int(m.group(2)))
                if h not in out:
                    out.append(h)
    return out[:3]


def _gate_failed(g):
    """(gate, first problem) of a gates_v<k>.json record that failed, else None."""
    if not g:
        return None
    if not (g.get("safety") or {}).get("ok"):
        return "safety", "; ".join(str(x) for x in ((g.get("safety") or {}).get("reasons") or [])[:2])
    for key, label in (("contract", "contract"), ("rate", "contract (trade rate - TTM #155)"),
                       ("lookahead", "look-ahead audit")):
        c = g.get(key)
        if key == "rate" and c is None:                          # a gates record from before TTM #155
            continue
        if c is None or not c.get("ok"):
            return label, str((c or {}).get("error") or "; ".join(str(x) for x in ((c or {}).get("problems") or [])[:1]))
    return None


def push_lock_state(path=None):
    """(held, holder text) of the machine-wide push lock - READ ONLY (MANAGER #143). tools/push_lock.py holds an OS
    lock on byte 0 and writes the holder's name from byte 1; the name stays in the file after a release, so the name
    alone cannot tell held from stale. On Windows the byte-0 lock is mandatory: reading byte 0 while a ship holds it
    raises PermissionError - that is 'held'. Elsewhere (advisory locks) a named holder whose pid is alive counts as
    held. A missing file is free. Never opens the file for writing, never takes or deletes the lock."""
    path = path or os.environ.get("QWEN_LAB_PUSH_LOCK") or PUSH_LOCK_DEFAULT
    if not os.path.exists(path):
        return False, ""
    text = ""
    try:
        with open(path, "rb") as fh:
            fh.seek(1)
            text = fh.read(200).decode("utf-8", "replace").strip(chr(0) + " ").strip()
    except OSError:
        pass
    try:
        with open(path, "rb") as fh:
            fh.read(1)
        locked = False
    except PermissionError:
        return True, text
    except OSError:
        locked = False
    if os.name != "nt" and not locked:
        m = re.search(r"pid (\d+)", text)
        if m:
            try:
                import psutil
                return bool(psutil.pid_exists(int(m.group(1)))), text
            except ImportError:
                pass
    return False, text


def courtesy_wait(lab, what, idea_id=None, *, interruptible=True, check=None, sleep=time.sleep, clock=time.time):
    """Wait while a ship holds the push lock before starting a NEW `what` (a Qwen generation or a Stage A). Re-checks
    every 60 s and logs the wait; a STOP file ends an interruptible wait (returns False). Returns True to go ahead."""
    check = check or push_lock_state
    held, who = check()
    if not held:
        return True
    t0 = clock()
    lab.log("LOAD COURTESY: push.lock held (%s) - waiting before a new %s; re-check every %d s (MANAGER #143)"
            % (who or "holder not named", what, COURTESY_RECHECK_S), idea_id)
    last_log = t0
    while held:
        if interruptible and lab.stop_requested():
            lab.log("LOAD COURTESY: STOP during the wait for the push lock (%d s) - nothing started"
                    % (clock() - t0), idea_id)
            return False
        sleep(COURTESY_RECHECK_S)
        held, who2 = check()
        who = who2 or who
        if held and clock() - last_log >= COURTESY_LOG_EVERY_S:
            lab.log("LOAD COURTESY: still waiting (%d min) - push.lock held (%s)" % ((clock() - t0) // 60, who),
                    idea_id)
            last_log = clock()
    waited = clock() - t0
    lab.log("LOAD COURTESY: push.lock free after %d s - the %s goes ahead" % (waited, what), idea_id)
    waits = lab.state.setdefault("courtesy_waits", [])
    waits.append({"at": now_s(), "what": what, "idea": idea_id, "secs": round(waited, 1), "holder": who})
    del waits[:-50]
    return True


def retries_text(idea):
    """'retries k/2' - the broken-plugin fix retries that RE-RAN a Stage A (MANAGER #139 / #153a): an identical-sha
    resubmission is never one."""
    sanity = (idea or {}).get("sanity") or []
    st = (idea or {}).get("stage_pre_wf") or {}
    k = int(sanity[-1].get("retry", len(sanity) - 1)) if (st.get("broken") and sanity) else len(sanity)
    return "retries %d/%d" % (k, SANITY_MAX_RETRIES)


def compose_prereg_post(idea, prereg):
    pr, mp = idea["proposal"], idea["map"]
    return ("%s: PREREG %s (%s) - %s %s RTH, master %s (%s) pinned; TWO STAGES (MANAGER #134): PRE-WF %s..%s "
            "(pre-walk-forward rows only, file defaults, no tuning), then the WF Stage A %s..%s ONLY if %s; lockbox "
            "%s..%s never read (asserted); cost %s pt x $%s. Stated "
            "pre-data prior (Qwen's input, not a result): Sharpe %s, %s trades/yr (map used %s/yr); first entry %s; "
            "entry fill %s; time stop %s. "
            "Map (python, "
            "mapcheck_f, recorded - no longer a stop): own WF ROC median %s, P(>=15) %s, P(lift #463) %s -> %s. "
            "Plugin %s LF sha256 %s; harness tools/qwen_lab.py LF sha256 %s; session calendar LF sha256 %s; prereg %s "
            "sha256 %s. Each stage re-checks the plugin, harness and calendar hashes. Replies -> %s."
            % (TAG, _safe_name(pr["name"]), source_ref(idea), pr["instrument"], pr["timeframe"], prereg["master"],
               prereg["source"], PREWF0, PREWF1, WF0, WF1, PROMOTION_RULE, LB0, LB1, prereg["cost_pts"],
               int(prereg["mult"]), pr["prior_sharpe_yearly"], pr["trades_per_year"], (mp.get("prior") or {}).get("n"),
               ("%s (pre-registered%s; checked on every PRE-WF entry - TTM #144)"
                % (pr["first_signal_bar"]["label"], ", amended" if pr.get("first_signal_bar_amended_at") else "")
                if (pr.get("first_signal_bar") or {}).get("label") else "not stated - not checked"),
               ("%s (checked on every contract-smoke entry - MANAGER #160b/#162)" % entry_fill_label(pr["entry_fill"])
                if (pr.get("entry_fill") or {}).get("at") else "not stated - not checked"),
               ("%s (checked on the contract smoke)" % time_stop_label(pr["time_stop_bars"])
                if pr.get("time_stop_bars") is not None else "not stated - not checked"),
               mp["own_wf_roc_median"],
               mp["p_own_roc_ge_15"], mp["p_lift_463"], mp["verdict"].split(" -")[0].split(" (")[0],
               os.path.basename(prereg["plugin_path"]), prereg["plugin_sha"], prereg["harness_sha"],
               prereg.get("calendar_sha") or "-", prereg["path"], prereg["sha"], REPLY_TO))


def compose_prewf_post(idea):
    """'QWEN LAB: <idea> PRE-WF ...' - every number from the harness's numbers dict."""
    pr, st = idea["proposal"], idea["stage_pre_wf"]
    mp = idea.get("map") or {}
    return ("%s: %s PRE-WF (%s) - %s..%s (pre-walk-forward rows only), %s %s RTH (%s), cost %s pt x $%s, file "
            "defaults (broken-plugin fix %s, MANAGER #139/#153a): %s. Promotion to the WF Stage A (%s): %s. Map "
            "(mapcheck_f, recorded - not a stop since MANAGER #134): %s. Prereg %s (sha %s); numbers %s. Every number "
            "computed by the harness (Python); Qwen supplied none. Replies -> %s."
            % (TAG, _safe_name(pr["name"]), source_ref(idea), PREWF0, PREWF1, pr["instrument"], pr["timeframe"],
               st.get("master"), st.get("cost_pts"), int(st.get("mult") or 0), retries_text(idea),
               fmt_four(st.get("numbers")), PROMOTION_RULE, st.get("promotion"), mp.get("verdict", "-"),
               (idea.get("prereg") or {}).get("path"), ((idea.get("prereg") or {}).get("sha") or "")[:16],
               st.get("numbers_json"), REPLY_TO))


def compose_result_post(idea):
    """The result post - every number in it comes from the harness's computed dicts (numbers / map), never model text."""
    pr = idea.get("proposal") or {}
    name = _safe_name(pr.get("name") or idea.get("plugin", {}).get("name") or idea["id"])
    head = "%s: %s (%s)" % (TAG, name, source_ref(idea))
    oc = idea.get("outcome") or "incomplete"
    nm = (idea.get("stage_a") or {}).get("numbers")
    if nm:
        sa = idea["stage_a"]
        v = idea.get("validate") or {}
        pre = (idea.get("stage_pre_wf") or {}).get("numbers")
        return ("%s - PRE-WF %s..%s: %s (broken-plugin fix %s) -> promoted. Stage A %s, %s %s RTH (%s), cost %s pt x "
                "$%s: %s. Bar for an Auto-Validate: %s. Validate: %s. Prereg %s (sha %s); plugin sha %s. Lockbox "
                "unread. Every number computed by the harness (Python); Qwen supplied none. Replies -> %s."
                % (head, PREWF0, PREWF1, fmt_four(pre), retries_text(idea), nm["stretch"], pr.get("instrument"),
                   pr.get("timeframe"),
                   sa.get("master"), sa.get("cost_pts"),
                   int(sa.get("mult") or 0), fmt_four(nm), sa.get("bar"), v.get("status", "not requested"),
                   (idea.get("prereg") or {}).get("path"), ((idea.get("prereg") or {}).get("sha") or "")[:16],
                   ((idea.get("prereg") or {}).get("plugin_sha") or "")[:16], REPLY_TO))
    st = idea.get("stage_pre_wf") or {}
    if st.get("numbers"):                       # PRE-WF numbers only (not promoted, or the WF stage did not finish)
        return ("%s - %s. PRE-WF %s..%s, %s %s RTH (%s), cost %s pt x $%s, file defaults (broken-plugin fix %s): %s. "
                "%s. Map (mapcheck_f, recorded - not a stop): %s. Prereg %s; numbers %s. Every number computed by the "
                "harness (Python); Qwen supplied none. Replies -> %s."
                % (head, oc, PREWF0, PREWF1, pr.get("instrument"), pr.get("timeframe"), st.get("master"),
                   st.get("cost_pts"), int(st.get("mult") or 0), retries_text(idea), fmt_four(st["numbers"]),
                   st.get("promotion"),
                   (idea.get("map") or {}).get("verdict", "-"), (idea.get("prereg") or {}).get("path"),
                   st.get("numbers_json"), REPLY_TO))
    mp = idea.get("map")
    extra = ""
    if mp and not mp.get("clears"):
        extra = (" Map (python, mapcheck_f): own WF ROC median %s, P(>=15) %s, P(lift #463) %s -> %s."
                 % (mp["own_wf_roc_median"], mp["p_own_roc_ge_15"], mp["p_lift_463"], mp["verdict"]))
    return "%s - %s.%s Four numbers: ROC@30k - | DD5 - | DD%% - | Sortino - (no curve). Replies -> %s." % (
        head, oc, extra, REPLY_TO)


# ------------------------------------------------------------------------------------------------ validate path
VALIDATE_TAG = TAG + " AUTO-VALIDATE"


def _qwen_tagged(job):
    """A Qwen-lab VALIDATE job (the lab's own research-beacon record also says QWEN LAB - it is not a validate)."""
    if str(job.get("type") or "") == "research":
        return False
    return VALIDATE_TAG in str(job.get("preset") or "") or VALIDATE_TAG in str(job.get("note") or "")


def firestore_live_jobs():
    """[(doc id, job dict)] of every queued / running / paused job (the lanes' query; ~a few reads)."""
    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(SHARED, "serviceAccount.json")))
    u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    return [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
            for d in u.collection("backtests").where(filter=_FF("status", "==", st)).stream()]


def firestore_queue(job):
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(SHARED, "serviceAccount.json")))
    u = firestore.client().collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")
    job = dict(job, createdAt=_dt.datetime.now(_dt.timezone.utc))
    ref = u.collection("backtests").document()
    ref.set(job)
    return ref.id


def lanes_job_base():
    """The lanes' Auto-Validate job shape, imported from tools/noise_queue_422_tp_validate.py (it chdirs on import)."""
    cwd, path = os.getcwd(), list(sys.path)
    try:
        sys.path.insert(0, HERE)
        import noise_queue_422_tp_validate as NQ
        return dict(NQ.BASE)
    finally:
        os.chdir(cwd)
        sys.path[:] = path


def build_validate_job(name, strategy_ref, instrument, timeframe, plugin_sha, prereg_path, cost=None, mult=None,
                       first_signal_bar=None):
    pin = MASTERS[(instrument, timeframe)]
    if cost is None or mult is None:
        cost, mult = COSTS[instrument]
    job = lanes_job_base()
    job.update(type="validate", strategy=strategy_ref, instrument=instrument, timeframe=timeframe,
               session=pin["session"], source=pin["source"], cost_pts=cost, mult=mult, date_from=VALIDATE_FROM,
               date_to=VALIDATE_TO, lockbox_months=VALIDATE_LB_MONTHS, wf_folds=8, warm_days=300, n_trials=900,
               status="queued", progress=0)
    job["preset"] = "%s AUTO-VALIDATE 900: %s" % (TAG, name)
    job["note"] = ("%s AUTO-VALIDATE 900: %s (Qwen-written plugin, LF sha256 %s, reviewed onto main). Prereg %s. %s %s "
                   "RTH, source %s (master %s) pinned, window %s..%s, %d-month lockbox, 8 folds, warm_days 300, cost %s "
                   "pt x $%s, 900 trials (OWNER RULE). Queued by tools/qwen_lab.py; Stage A cleared the house bar "
                   "(WF ROC@30k >= %.0f, not one episode, >= %d WF trades).%s"
                   % (TAG, name, plugin_sha, prereg_path, instrument, timeframe, pin["source"], pin["filename"],
                      VALIDATE_FROM, VALIDATE_TO, VALIDATE_LB_MONTHS, cost, mult, VALIDATE_BAR_ROC, MIN_WF_TRADES,
                      (" Pre-registered first entry %s: checked at the defaults and at every searched knob's min / max "
                       "(TTM #144) - a chosen param set that fills earlier is not the pre-registered rule."
                       % first_signal_bar) if first_signal_bar else ""))
    assert job["n_trials"] == 900
    return job


def split_date():
    import pandas as pd
    return (pd.Timestamp(VALIDATE_TO) - pd.Timedelta(days=int(VALIDATE_LB_MONTHS * 30.44))).date().isoformat()


def reviewed_on_main(name, plugin_sha):
    """Where the reviewed file sits on main (the runner reads the shared checkout) with the SAME LF hash, else None."""
    for rel, ref in (("augur_strategies/%s.py" % name, "%s.py" % name),
                     ("augur_strategies/qwen_lab/%s.py" % name, None)):
        p = os.path.join(SHARED, *rel.split("/"))
        if os.path.isfile(p) and lf_sha256_file(p) == plugin_sha:
            return p, (ref or p)
    return None, None


# ------------------------------------------------------------------------------------------------ prompts and tool specs
TEMPLATE_PLUGIN = '''"""QL_TEMPLATE - opening-range breakout, close-confirmed (template; shows the contract)."""
import numpy as np

STRATEGY_NAME = "QL TEMPLATE 1.0 - opening-range breakout"
DESCRIPTION = ("After the first range_bars bars, a close above the range high buys (below the low sells) at the "
               "NEXT bar's open; stop stop_frac x range away (a bar that opens past it books its open); flat at "
               "the session's last bar. One trade a session.")
_AUGUR_MARKET = {"instrument": "NQ", "timeframe": "5m"}
ROLL_SIGNAL = "difference"

DEFAULT_PARAMS = {
    "range_bars": {"default": 6, "min": 3, "max": 24, "step": 3, "type": "int", "label": "Opening range (bars)"},
    "stop_frac": {"default": 1.0, "min": 0.25, "max": 2.0, "step": 0.25, "type": "float", "label": "Stop (x range)"},
}


def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None,
                 range_bars=6, stop_frac=1.0,
                 return_trades=False, _stop_event=None, _pause_event=None, **_ignore):
    # index = the bar timestamps (US/Eastern, each bar's OPEN time): REAL dates. A calendar rule reads them through
    # `from augur_engine.session_calendar import is_last_n_sessions_of_month, session_index_in_month, week_of_month,
    # days_to_month_end, session_dates` (one value per bar; e.g. is_last_n_sessions_of_month(index, 3, day_id)).
    # This rule needs no calendar. Entry fill: the OPEN of the bar after the signal (entry_fill {"at": "open", "bar":
    # -1}); no time stop (time_stop_bars 0).
    o = np.asarray(opens, float)
    h = np.asarray(highs, float)
    l = np.asarray(lows, float)
    c = np.asarray(closes, float)
    n = len(c)
    if day_id is None or n < 50:
        return None
    did = np.asarray(day_id)
    starts = np.flatnonzero(np.r_[True, did[1:] != did[:-1]])
    ends = np.r_[starts[1:], n]
    rb = int(range_bars)
    trades = []
    for a, b in zip(starts, ends):
        if b - a <= rb + 2:
            continue
        hi = h[a:a + rb].max()
        lo = l[a:a + rb].min()
        rng = hi - lo
        if rng <= 0:
            continue
        # in-session bar index = k - a (bar 0 = the 09:30 open). The first decision is on bar range_bars's close and
        # the first fill at bar range_bars+1's open: bar 7 (10:05 open) with the default 6 on 5m bars. range_bars is
        # searched down to 3 (first fill bar 4 (09:50 open)), so first_signal_bar = {"index": 4, "clock": "09:50"}
        for k in range(a + rb, b - 2):          # decide on bar k's CLOSE
            side = 1 if c[k] > hi else (-1 if c[k] < lo else 0)
            if side == 0:
                continue
            e = k + 1                            # fill at the NEXT bar's open
            entry = o[e]
            stop = entry - side * float(stop_frac) * rng
            x, px = b - 1, c[b - 1]              # default exit: the session's last close
            for j in range(e, b):
                if side > 0 and l[j] <= stop:
                    x, px = j, (o[j] if o[j] < stop else stop)    # gap-through: book the open
                    break
                if side < 0 and h[j] >= stop:
                    x, px = j, (o[j] if o[j] > stop else stop)
                    break
            trades.append((int(e), int(x), float(side * (px - entry)), int(side), float(entry)))
            break                                # one trade a session
    if not trades:
        return None
    p = np.array([t[2] for t in trades], float)
    wins = p[p > 0]
    losses = p[p < 0]
    gw = float(wins.sum())
    gl = float(-losses.sum())
    cum = np.cumsum(p)
    out = {"total_pnl": float(p.sum()), "num_trades": int(len(p)),
           "win_rate": 100.0 * len(wins) / len(p),
           "profit_factor": (gw / gl) if gl > 1e-9 else (float("inf") if gw > 0 else 0.0),
           "max_drawdown": float((cum - np.maximum.accumulate(cum)).min()),
           "avg_pnl": float(p.mean()), "wins": int(len(wins)), "losses": int(len(losses))}
    if return_trades:
        out["trades"] = trades
    return out
'''

SYSTEM_PROMPT = """You are QWEN LAB, a strategy TESTER for the EDGE-LOG futures research repo. In one session you turn ONE \
reading-shelf paper into ONE concrete, testable NQ or ES intraday futures rule, write it as a strategy plugin, and hand \
it to the Python harness, which gates it, runs it and computes every number.

HARD RULES
1. Python computes every number. Never state a result (ROC, drawdown, Sortino, P&L, trade count) in your own words; the \
harness reports results from its own computation.
2. The harness enforces this order: propose -> write_plugin (safety gate, contract test, look-ahead audit - hard \
gates) -> run_stage_a (dead list; the power-first map is recorded; a pre-registration naming both stages is posted to \
MANAGER; then a PRE-WF Stage A on %(p0)s..%(p1)s with the file's defaults, and the walk-forward Stage A only if \
%(promo)s) -> queue_validate (only when the harness says the bar is met) -> finish. A refused step returns the reason: \
fix it and call again. Steps are limited. A plugin byte-identical to one the lab already ran, or to the one this idea \
already ran, is refused (it would give the same trades) - a fix must change the code.
3. The proposal is pre-data. State an HONEST prior: the yearly Sharpe ratio of the leg after costs and after decay \
(halve a published edge; house priors are usually 0.2-0.7; the harness refuses above %(smax)s) and the trades a year \
it will take. The map's verdict on it is recorded and posted next to the results.
4. Data: NQ or ES regular-hours bars (1m, 5m or 15m; NQ also 2m), 09:30-16:00 ET, non-adjusted front contract (the engine handles \
contract rolls). Walk-forward stretch only (%(wf0)s..%(wf1)s); the lockbox year is sealed - you never see it. The \
engine charges the house cost (NQ 0.533 pt, ES 0.363 pt a round trip; short-hold scalper ideas NQ 0.783, ES 0.613); \
the plugin returns GROSS points.
5. Do not re-propose a dead idea: dead_list() lists the closed rows of the research ledger.
6. Do not re-run an idea the LAB already ran: your first message lists them (name, mechanism family, rule, verdict) \
and ideas() repeats the list with the family map. propose() refuses the same name, the same mechanism family, or a \
near copy of a run idea's rule (such a refusal uses no proposal slot) - propose something the lab has not run.
7. If you cannot emit a native tool call, reply with ONLY one JSON object: {"tool": "<name>", "arguments": {...}}.

BAR INDEX CONVENTION - name bars ONE way everywhere (hypothesis, mechanism, first_signal_bar, code comments)
- bar k = the 0-based IN-SESSION index: bar 0 is the first regular-hours bar (the 09:30 open). Always write it WITH \
the clock time of that bar's OPEN: on 5m bars 'bar 12 (10:30 open)' is the bar from 10:30 to 10:35; on 1m bars \
'bar 12 (09:42 open)'. Bar k's close is bar k+1's open time: on 5m bars bar 11 closes at 10:30. The harness numbers \
bars BY THE CLOCK (bar k opens at 09:30 + k x bar minutes), so on a session with missing bars the 10:30 bar is still \
bar 60 on 1m bars.
- For every entry and exit say whether it fills at a bar's OPEN or at its CLOSE, e.g. 'decide on bar 11's close \
(10:30), enter at bar 12's open (10:30 open)'. The trade list records the FILL bar.
- propose() needs first_signal_bar = {"index": k, "clock": "HH:MM"}: the earliest bar on which an entry may FILL, with \
that bar's open time (the harness refuses a clock that is not bar k's open), for the default knobs AND every knob \
value the Auto-Validate searches (a knob that sets a warm-up or a range length moves the first fill: use its MIN). \
The contract smoke (defaults and every knob's min and max) and every PRE-WF trade are checked: an entry that fills \
before it is a hard gate failure.
- propose() also needs entry_fill = {"at": "open" | "close" | "level", "bar": k or -1}: WHERE every entry fills - at \
the bar's OPEN, at its CLOSE, or at a stop / limit LEVEL inside it - and, for a fixed-time entry, the in-session bar \
(with "clock"); bar -1 when the bar varies with the signal. And time_stop_bars = N: ONE bar-count convention - a time \
stop of N bars exits at the CLOSE of entry bar + N (exit_bar - entry_bar = N, 'N bars held'); 0 = no time stop. The \
contract smoke checks every entry's fill bar and price point (at the defaults and at every knob value the validate \
searches) and every time-stop exit - a time stop the code has must be the one you state: a shorter one, or one with \
time_stop_bars 0, fails too (a violation is a hard gate failure with the offending trades), and its trade rate must \
be within 3x of the trades_per_year you state.

DATES AND THE SESSION CALENDAR (MANAGER #156)
- Declare index=None in run_backtest to receive the bar timestamps (US/Eastern, each bar's OPEN time): REAL dates. \
day_id is only a session NUMBER - never count sessions from the start of the data to find a month end.
- `from augur_engine.session_calendar import ...` gives one value per BAR (equal on every bar of a session): \
session_dates(index, day_id) -> int YYYYMMDD; is_last_n_sessions_of_month(index, n, day_id) / \
is_first_n_sessions_of_month(index, n, day_id) -> True on the last / first n trading sessions of the calendar month; \
session_index_in_month(index, day_id) -> 0 = the month's first session; days_to_month_end(index, day_id) -> sessions \
left in the month after this one (0 = the last); week_of_month(index, day_id) -> 1 + (day - 1) // 7 (a third Friday \
is in week 3); session_calendar(index, day_id) -> a dict of all of them plus "weekday" (0 = Monday).
- The month-end helpers read the published exchange calendar (knowable in advance), not prices - allowed. They \
never read the data's own dates: a day missing from the data is still a session (with no bars to trade), so an \
answer never depends on where the data start or end. Example, \
long the last 3 sessions of each month from the open to the close: `last3 = is_last_n_sessions_of_month(index, 3, \
day_id)`, then for each session [a, b): `if last3[a]: trades.append((a, b - 1, float(c[b - 1] - o[a]), 1, float(o[a])))`.

PLUGIN CONTRACT (the harness checks every point)
- File = one Python module. Imports: numpy, pandas, math, `from augur_engine.rolls import seam_days` and `from \
augur_engine.session_calendar import <helper>` - nothing else.
- Module level: only imports, constant assignments, function definitions and the docstring. Constants: STRATEGY_NAME \
(str), DESCRIPTION (str), _AUGUR_MARKET = {"instrument": ..., "timeframe": ...}, ROLL_SIGNAL = "difference" (rules on \
point distances) or "ratio" (rules on percentages), DEFAULT_PARAMS.
- NO STATE BETWEEN RUNS: every run_backtest call is a fresh run. Only DEFAULT_PARAMS / _AUGUR_MARKET may be dicts at \
module level (other constants: tuples, numbers, strings); never write into a module-level name from a function \
(no cache), never a mutable default argument (use None). The gate refuses these and every run gets a fresh module.
- DEFAULT_PARAMS = {knob: {"default", "min", "max", "step", "type": "int"|"float", "label"}}; at least one numeric knob \
with max > min (the Auto-Validate searches these ranges with 900 trials). A str knob {"default", "type": "str", \
"options": [...]} has EVERY option searched - keep fidelity choices to one option. Every knob is a run_backtest keyword. \
At most %(knobs_max)d searched knobs (ranged numeric + multi-option str / bool): the audits run every one at its min \
/ max and every option.
- def run_backtest(opens, highs, lows, closes, volumes=None, day_id=None, index=None, <knobs=defaults>, \
return_trades=False, _stop_event=None, _pause_event=None, **_ignore): numpy float arrays of bars; day_id[i] is the \
session number (equal for every bar of one session); index = the bar timestamps (real dates). Return None when there are no trades, else a dict with total_pnl, num_trades, win_rate, \
profit_factor, max_drawdown, avg_pnl, wins, losses (points, 1 contract, gross) plus "trades": a list of \
(entry_bar, exit_bar, pnl_points, side +1/-1, entry_price) when return_trades is true. pnl = side x (exit_price - \
entry_price).
- TIMING (audited by perturbing the data): a decision at bar k uses bars <= k only. Fill at bar k's close, or at bar \
k+1's open. An intrabar stop/limit may use the bar's high/low, never its close or volume; if the bar OPENS past the \
level, book the open (gap-through). Never use any bar after the fill bar to decide an entry, nor after the exit bar to \
decide an exit; no whole-array statistics (full-series mean / percentile / max) - only trailing windows.
- STOP / TARGET / SIZE at entry use only what was known at the fill: for a fill at bar k's open, bars <= k-1 and bar \
k's open (atr[k-1] - never an ATR / range / volatility window that includes bar k, nor bar k's close or volume); for \
an intrabar stop / limit fill inside bar k, bars <= k-1, bar k's open and the fill level; for a fill at bar k's close, \
bars <= k. The audit re-draws the first bar at risk (its high / low pushed further, its close and volume moved) and \
requires the same exit price and size. Update a trailing level with a bar's high / low / close only AFTER that bar's \
stop / target check.
- Be flat by each session's last bar. Deterministic (no randomness).
- Forbidden: print, open, file / network / OS access, eval / exec / compile, getattr / setattr / hasattr, globals, \
classes, global statements, assigning attributes (x.y = ...), names or attributes with leading underscores or dunders, \
'__' inside strings, pandas/numpy readers or writers (read_*, to_csv, np.load, np.save ...), df.query / df.eval.

TEMPLATE (passes every gate - copy its structure, change the rule):
%(template)s"""

TOOLS = [
    {"name": "read_repo_file", "description": "Read a text file of the repo (read-only, capped; secrets refused).",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "repo-relative path, e.g. augur_strategies/ORB_FADE_1_0.py"},
         "start_line": {"type": "integer", "description": "first line to return (default 1)"}},
         "required": ["path"]}},
    {"name": "list_strategies", "description": "List the house strategy plugins and the lab's own.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "dead_list", "description": "Closed / dead rows of the research ledger (compact). Optional keyword filter.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": []}},
    {"name": "shelf_ideas", "description": "Reading-shelf papers still open to the lab (live / dead / taken excluded).",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "ideas", "description": "This session's idea source (the owner's scalper ask / your own idea / a shelf "
                                     "paper), its brief, the rotation, the open shelf papers, and every idea the lab "
                                     "already ran (name, mechanism family, rule, verdict) with the family map - "
                                     "propose() refuses a repeat.",
     "parameters": {"type": "object", "properties": {}, "required": []}},
    {"name": "propose", "description": "Record the PRE-DATA proposal. Refuses an idea the lab already ran (same name, "
                                       "mechanism family or rule - no proposal slot used) and runs the dead-list "
                                       "check; the power-first map reads the prior later. Must come before "
                                       "write_plugin.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string", "description": "UPPER_CASE file name, e.g. QL_TURNPT_NQ (QL_ is added if missing)"},
         "hypothesis": {"type": "string", "description": "what should happen and why, 2-6 sentences"},
         "mechanism": {"type": "string", "description": "the exact rule: signal, entry fill (name bars 'bar k (HH:MM "
                                                         "open)' and say open or close fill), exit, stop, session"},
         "prior_sharpe_yearly": {"type": "number", "description": "honest yearly Sharpe after costs and decay"},
         "trades_per_year": {"type": "number", "description": "expected trades a year"},
         "instrument": {"type": "string", "enum": ["NQ", "ES"]},
         "timeframe": {"type": "string", "enum": ["1m", "2m", "5m", "15m"],
                       "description": "bar size (default 5m; 2m is NQ only)"},
         "first_signal_bar": {"type": "object",
                              "description": "the EARLIEST in-session bar on which an entry may FILL - with the "
                                             "default knobs and every searched knob value: 0-based index (bar 0 = the "
                                             "09:30 open, counted by the clock) and the clock time of that bar's OPEN, "
                                             "e.g. {\"index\": 12, \"clock\": \"10:30\"} on 5m bars. No entry may fill "
                                             "before it (checked).",
                              "properties": {"index": {"type": "integer"}, "clock": {"type": "string"}},
                              "required": ["index", "clock"]},
         "entry_fill": {"type": "object",
                        "description": "WHERE every entry fills: at the bar's OPEN, its CLOSE, or a stop / limit LEVEL "
                                       "inside it; bar = the in-session bar of a fixed-time entry (with its open "
                                       "clock), -1 when the bar varies with the signal. E.g. {\"at\": \"open\", \"bar\": "
                                       "-1}. Checked on every contract-smoke entry.",
                        "properties": {"at": {"type": "string", "enum": ["open", "close", "level"]},
                                       "bar": {"type": "integer"}, "clock": {"type": "string"}},
                        "required": ["at"]},
         "time_stop_bars": {"type": "integer",
                            "description": "N = exit at the CLOSE of entry bar + N (exit_bar - entry_bar = N, 'N bars "
                                           "held'); 0 = no time stop. Checked on the contract smoke."}},
         "required": ["name", "hypothesis", "mechanism", "prior_sharpe_yearly", "trades_per_year", "instrument",
                      "first_signal_bar", "entry_fill", "time_stop_bars"]}},
    {"name": "write_plugin", "description": "Write the plugin (full file source). Runs the safety gate, the contract test "
                                            "and the look-ahead audit; returns pass/fail with reasons.",
     "parameters": {"type": "object", "properties": {
         "name": {"type": "string"}, "code": {"type": "string", "description": "the complete Python file"}},
         "required": ["name", "code"]}},
    {"name": "run_stage_a", "description": "Run the dead-list gate, record the power-first map, auto pre-register "
                                           "(posted to MANAGER), then the PRE-WF Stage A and - if promoted - the WF "
                                           "Stage A. Returns the harness's computed numbers.",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "queue_validate", "description": "Queue the 900-trial Auto-Validate (only when Stage A met the bar).",
     "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
    {"name": "finish", "description": "End this session.",
     "parameters": {"type": "object", "properties": {"note": {"type": "string"}}, "required": []}},
]


def system_prompt():
    return SYSTEM_PROMPT % {"smax": PRIOR_SHARPE_MAX, "wf0": WF0, "wf1": WF1, "template": TEMPLATE_PLUGIN,
                            "p0": PREWF0, "p1": PREWF1, "promo": PROMOTION_RULE, "knobs_max": SEARCHED_KNOBS_MAX}


def idea_brief(idea):
    src = (idea or {}).get("source") or "shelf"
    if src == "scalper":
        return SCALPER_FACTS
    if src == "own":
        return OWN_FACTS
    sh = idea.get("shelf") or {}
    return ("reading shelf #%s: \"%s\" (%s, %s; %s).\nSummary: %s\nWhy it matters to us: %s\nRepo note: %s"
            % (sh.get("n"), sh.get("title"), sh.get("authors"), sh.get("year"), sh.get("venue"), sh.get("summary"),
               sh.get("why_for_us"), sh.get("repo_note")))


def ran_ideas_block(ran):
    """The 'already run' block of the idea prompt (MANAGER #148) - harness text built from state.json + idea folders."""
    if not ran:
        return ""
    fams = families_taken(ran)
    fm = family_map_brief()
    return ("\n\nIDEAS THE LAB HAS ALREADY RUN - do not propose any of them again. propose() refuses the same name, the "
            "same mechanism family, or a near copy of the rule (no proposal slot used); a run that was NOT a verdict "
            "(a broken plugin, an abort) blocks only its name:\n- %s\nMechanism families already taken: %s."
            % ("\n- ".join(ran_ideas_brief(ran)), "; ".join("%s (%s)" % (f, fm.get(f, f)) for f in fams) or "none"))


def idea_prompt(idea, max_steps, max_attempts, ran=None):
    if "source" not in idea and "shelf" not in idea:                    # a bare shelf entry (older callers)
        idea = {"source": "shelf", "shelf": idea}
    src = idea.get("source") or "shelf"
    head = {"scalper": "TODAY'S SOURCE - THE OWNER'S SCALPER ASK. %s\nThis session's Stage A charges the scalp hunt's "
                       "costs: NQ 0.783 pt, ES 0.613 pt a round trip. Bars: NQ 1m / 2m / 5m, ES 1m / 5m (RTH)."
                       % SCALPER_FACTS,
            "own": "TODAY'S SOURCE - YOUR OWN IDEA. %s" % OWN_FACTS,
            "shelf": "TODAY'S PAPER - %s" % idea_brief(idea)}[src]
    return (head + "\n\nTurn it into ONE concrete NQ or ES intraday rule on the held regular-hours bars (1m / 2m NQ / "
            "5m / 15m). One "
            "look at dead_list() is enough (at most %d turns of reading before you propose - the harness checks your "
            "proposal against the dead list itself; do not search it word by word). Then: propose -> write_plugin "
            "(fix and resubmit on failure; at most %d attempts) -> run_stage_a -> queue_validate only if the harness "
            "says the bar is met -> finish (run_stage_a runs a PRE-WF Stage A, then the WF Stage A only if promoted). "
            "You have %d steps; every tool result says how many are left. Name bars 'bar k (HH:MM open)' and give "
            "first_signal_bar, entry_fill and time_stop_bars with the proposal. A calendar rule reads REAL dates "
            "(index + augur_engine.session_calendar), never a count of day_id from the start of the data."
            % (MAX_LOOK_TURNS, max_attempts, max_steps)) + ran_ideas_block(ran)


# ------------------------------------------------------------------------------------------------ the model client
class OllamaChat:
    """Ollama /api/chat with native tool calling (verified with qwen3.8:27b on Ollama 0.40.4, 2026-10-15)."""

    def __init__(self, model=None, host=None, think=False, timeout=MODEL_TIMEOUT, num_ctx=None):
        sys.path.insert(0, HERE)
        import local_llm as LL
        self.LL = LL
        self.model = model or LL.MODEL
        self.host = (host or LL.HOST).rstrip("/")
        self.think = bool(think)
        self.timeout = timeout
        self.num_ctx = int(num_ctx or LL.NUM_CTX)

    def ping(self):
        return self.LL.ping()

    def chat(self, messages, tools):
        payload = {"model": self.model, "messages": messages, "stream": False, "think": self.think,
                   "keep_alive": self.LL.KEEP_ALIVE, "tools": [{"type": "function", "function": t} for t in tools],
                   "options": {"temperature": 0.2, "seed": 20261015, "num_ctx": self.num_ctx,
                               "num_predict": NUM_PREDICT}}
        t0 = time.time()
        d = self.LL._http_json("/api/chat", payload, timeout=self.timeout)
        if d.get("error"):
            raise self.LL.OllamaError("Ollama error: %s" % str(d["error"])[:300])
        msg = d.get("message") or {}
        return msg, {"secs": round(time.time() - t0, 1), "eval_tokens": d.get("eval_count"),
                     "prompt_tokens": d.get("prompt_eval_count"), "done_reason": d.get("done_reason")}


def parse_json_action(content):
    """The fallback protocol: {"tool": name, "arguments": {...}} anywhere in a plain-text reply."""
    s = str(content or "")
    for m in re.finditer(r"\{", s):
        depth, i = 0, m.start()
        for j in range(i, len(s)):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(s[i:j + 1])
                    except ValueError:
                        break
                    if isinstance(obj, dict) and isinstance(obj.get("tool"), str):
                        args = obj.get("arguments", obj.get("args", {}))
                        return obj["tool"], args if isinstance(args, dict) else {}
                    break
    return None


def compact_messages(messages, limit=MAX_CTX_CHARS, keep_last=6):
    """A copy small enough for the context: old tool results and old plugin code are cut to stubs."""
    msgs = [dict(m) for m in messages]

    def size():
        return sum(len(json.dumps(m, default=str)) for m in msgs)
    if size() <= limit:
        return msgs
    for i, m in enumerate(msgs[:-keep_last]):
        if m.get("role") == "tool" and len(str(m.get("content", ""))) > 400:
            m["content"] = str(m["content"])[:400] + " ...[trimmed; the full result is in the transcript]"
        if m.get("tool_calls"):
            tcs = []
            for tc in m["tool_calls"]:
                tc = json.loads(json.dumps(tc, default=str))
                args = (tc.get("function") or {}).get("arguments") or {}
                if isinstance(args, dict) and isinstance(args.get("code"), str) and len(args["code"]) > 300:
                    args["code"] = "<plugin code omitted: %d chars>" % len(args["code"])
                tcs.append(tc)
            m["tool_calls"] = tcs
        if size() <= limit:
            break
    return msgs


# ------------------------------------------------------------------------------------------------ one idea = one session
class IdeaSession:
    """The per-idea state machine. Qwen calls tools; the harness enforces the order and computes every number."""

    def __init__(self, lab, idea, *, dry_run_validate=False, poster=None, sandbox=None, mapcheck=None, live_jobs=None,
                 queue_job=None, dead_rows_fn=None, master_loader=None, numbers_fn=None, courtesy=None):
        self.lab = lab
        self.idea = idea
        self.dir = lab.idea_dir(idea["id"])
        self.dry = bool(dry_run_validate)
        self.poster = poster or post_manager
        self.sandbox = sandbox or run_sandbox
        self.mapcheck = mapcheck or mapcheck_prior
        self.live_jobs = live_jobs or firestore_live_jobs
        self.queue_job = queue_job or firestore_queue
        self.dead_rows_fn = dead_rows_fn or dead_rows
        self.master_loader = master_loader or self._load_master
        self.numbers_fn = numbers_fn or four_numbers
        self.courtesy = courtesy or courtesy_wait
        idea.setdefault("events", [])
        idea.setdefault("proposals", [])
        idea.setdefault("plugin", {})
        idea.setdefault("gates", {})
        idea.setdefault("status", "open")

    # -- bookkeeping
    def event(self, what, **kw):
        self.idea["events"].append(dict(at=now_s(), event=what, **kw))
        self.save()
        self.lab.log(what + ((" " + json.dumps(kw, default=str)[:300]) if kw else ""), self.idea["id"])

    def save(self):
        jdump(os.path.join(self.dir, "idea.json"), self.idea)

    def close(self, outcome):
        if self.idea.get("status") != "closed":
            self.idea["status"] = "closed"
            self.idea["outcome"] = outcome
            self.event("closed", outcome=outcome)

    @property
    def closed(self):
        return self.idea.get("status") == "closed"

    def _name(self, name):
        n = _safe_name(name)
        if not n.startswith("QL_"):
            n = "QL_" + n
        if not re.match(r"^QL_[A-Z0-9][A-Z0-9_]{2,40}$", n):
            raise ToolRefused("name must be UPPER_CASE letters / digits / underscores, 3-40 chars after QL_")
        return n

    def plugin_path(self, name):
        p = os.path.join(self.lab.plugin_dir, name + ".py")
        if not under(p, self.lab.plugin_dir):
            raise ToolRefused("refused: the plugin path escapes augur_strategies/qwen_lab/")
        return p

    # -- tools
    def t_read_repo_file(self, path, start_line=1):
        return read_repo_file(path, start_line, lab=self.lab)

    def t_list_strategies(self):
        return list_strategies(self.lab)

    def t_dead_list(self, query=None):
        return dead_list(query)

    def t_shelf_ideas(self):
        return {"papers": [{k: p.get(k) for k in ("n", "title", "authors", "year", "tag", "summary")}
                           for p in open_shelf_papers(self.lab)],
                "note": "only papers MANAGER opened for the lab; a paper the lab has run is closed (MANAGER #142)"}

    def t_ideas(self):
        ran = ran_ideas(self.lab, exclude=self.idea.get("id"))
        return {"session_source": SOURCE_LABEL.get(self.idea.get("source") or "shelf"),
                "brief": idea_brief(self.idea), "rotation": [SOURCE_LABEL[x] for x in SOURCE_ORDER],
                "open_shelf_papers": ["#%s %s" % (p["n"], p["title"]) for p in open_shelf_papers(self.lab)],
                "closed_for_the_lab": [d["family"] for d in LAB_DEAD],
                "already_run": ran_ideas_brief(ran),                           # MANAGER #148
                "families_taken": families_taken(ran),
                "family_map": family_map_brief(), "_cap": 10000}

    def _reopened_shelf(self):
        """The shelf paper of this session when the lab ran it before (closed_shelf) - MANAGER re-opened it, so its
        own earlier runs do not block its mechanism (the name check still does)."""
        n = self.idea.get("shelf_n")
        if (self.idea.get("source") or "shelf") != "shelf" or n is None:
            return None
        return int(n) if str(int(n)) in (self.lab.state.get("closed_shelf") or {}) else None

    def _amend_contract_fields(self, name, first_signal_bar, entry_fill, time_stop_bars):
        """A FROZEN proposal from before the timing contract (TTM #144: first_signal_bar; MANAGER #160b/#162:
        entry_fill, time_stop_bars) records the MISSING fields and nothing else: the contract (write_plugin again) and
        every PRE-WF entry are checked against them, and the prereg addendum names them."""
        pr = self.idea["proposal"]
        if self._name(name) != pr["name"]:
            raise ToolRefused("the proposal is frozen (%s): call propose with ITS name to record %s - the rest of the "
                              "frozen proposal is kept" % (pr["name"], ", ".join(missing_contract_fields(pr))))
        missing = missing_contract_fields(pr)
        got = {}
        if "first_signal_bar" in missing:
            got["first_signal_bar"] = parse_first_signal_bar(first_signal_bar, pr["timeframe"])
        if "entry_fill" in missing:
            fb = (got.get("first_signal_bar") or pr.get("first_signal_bar") or {}).get("index")
            got["entry_fill"] = parse_entry_fill(entry_fill, pr["timeframe"], fb)
        if "time_stop_bars" in missing:
            got["time_stop_bars"] = parse_time_stop(time_stop_bars, pr["timeframe"])
        pr.update(got)
        at = now_s()
        if "first_signal_bar" in got:
            pr["first_signal_bar_amended_at"] = at
        pr["contract_amended_at"] = at
        pr["contract_amended_fields"] = sorted(got)
        self.idea["plugin"]["gates_ok"] = False                      # the contract must check them: re-gate
        self.event("contract_fields_amended", fields=sorted(got),
                   first_signal_bar=(pr.get("first_signal_bar") or {}).get("label"))
        fsb = pr["first_signal_bar"]
        return {"accepted": True, "amended": sorted(got), "name": pr["name"],
                "first_signal_bar": "%s on %s bars: no entry may FILL before it - checked by the contract and on every "
                                    "PRE-WF trade" % (fsb["label"], pr["timeframe"]),
                "entry_fill": entry_fill_label(pr["entry_fill"]), "time_stop": time_stop_label(pr["time_stop_bars"]),
                "note": "the frozen proposal is otherwise unchanged; the amendment is written into the prereg (or its "
                        "addendum) before the next Stage A",
                "next": "write_plugin(name, code) - the current gates check them - then run_stage_a(name)"}

    def t_propose(self, name, hypothesis, mechanism, prior_sharpe_yearly, trades_per_year, instrument,
                  timeframe="5m", first_signal_bar=None, entry_fill=None, time_stop_bars=None):
        prereg_posted = bool((self.idea.get("prereg") or {}).get("posted_id"))
        cur = self.idea.get("proposal")
        if (cur and missing_contract_fields(cur) and not self.idea.get("stage_pre_wf")
                and (self.idea.get("map") or prereg_posted) and (not prereg_posted or self.idea.get("sanity_open"))):
            # TTM #144 / MANAGER #160b on a frozen older proposal: record only the missing timing fields
            return self._amend_contract_fields(name, first_signal_bar, entry_fill, time_stop_bars)
        if self.idea.get("stage_pre_wf") or prereg_posted:
            raise ToolRefused("the prereg is posted / Stage A ran - the pre-data proposal is frozen")
        if self.idea.get("map"):
            raise ToolRefused("the power-first map already read this session's proposal - it is frozen")
        if len(self.idea["proposals"]) >= MAX_PROPOSALS:
            raise ToolRefused("proposal limit (%d) reached for this session" % MAX_PROPOSALS)
        name = self._name(name)
        inst, tf = str(instrument).upper().strip(), str(timeframe or "5m").strip()
        if (inst, tf) not in MASTERS:
            raise ToolRefused("instrument/timeframe must be one of %s" % ", ".join("%s %s" % k for k in MASTERS))
        try:
            s, n = float(prior_sharpe_yearly), float(trades_per_year)
        except (TypeError, ValueError):
            raise ToolRefused("prior_sharpe_yearly and trades_per_year must be numbers")
        if not (0 < s <= PRIOR_SHARPE_MAX) or not math.isfinite(s):
            raise ToolRefused("prior_sharpe_yearly must be in (0, %s] - a yearly Sharpe after costs and decay; house "
                              "priors run 0.2-0.7" % PRIOR_SHARPE_MAX)
        if not (PRIOR_TRADES_RANGE[0] <= n <= PRIOR_TRADES_RANGE[1]):
            raise ToolRefused("trades_per_year must be in %s..%s" % PRIOR_TRADES_RANGE)
        hyp, mech = str(hypothesis or "").strip(), str(mechanism or "").strip()
        if len(hyp) < 20 or len(mech) < 20:
            raise ToolRefused("hypothesis and mechanism must each say something (>= 20 characters)")
        fsb = parse_first_signal_bar(first_signal_bar, tf)                  # TTM #144 / #145 (refusals use no slot)
        ef = parse_entry_fill(entry_fill, tf, fsb["index"])                 # MANAGER #160b / #162 (no slot either)
        tsb = parse_time_stop(time_stop_bars, tf)
        # MANAGER #148: an idea the lab already ran (same name, same mechanism family, or a near copy) is refused here,
        # BEFORE it takes a proposal slot - the reason goes back to Qwen with the list of run ideas
        ran = ran_ideas(self.lab, exclude=self.idea.get("id"))
        dd = dedupe_check(name, mech, ran, reopened_shelf=self._reopened_shelf())
        if dd["refused"]:
            self.idea.setdefault("dedupe_refusals", []).append({"at": now_s(), "name": name, "reason": dd["reason"],
                                                                "matches": dd["matches"]})
            self.event("dedupe_refused", name=name, reason=dd["reason"])
            return {"accepted": False, "gate": "already run (MANAGER #148)", "reason": dd["reason"],
                    "matches": dd["matches"], "proposal_slots_left": MAX_PROPOSALS - len(self.idea["proposals"]),
                    "already_run": ran_ideas_brief(ran),
                    "families_taken": families_taken(ran),
                    "family_map": family_map_brief(),
                    "next": "propose a mechanism the lab has NOT run - outside every family taken above and not a "
                            "copy of a run idea's rule (this refusal used no proposal slot)", "_cap": 10000}
        prop = {"name": name, "hypothesis": hyp[:2000], "mechanism": mech[:2000], "prior_sharpe_yearly": s,
                "trades_per_year": n, "instrument": inst, "timeframe": tf, "first_signal_bar": fsb,
                "entry_fill": ef, "time_stop_bars": tsb,
                "families": dd["families"], "at": now_s(),
                "dedupe": {"reason": dd["reason"], "families": dd["families"], "retry_allowed": dd["retry_allowed"],
                           "ideas_checked": len(ran), "at": now_s()}}
        self.idea["proposals"].append(prop)
        dc = dead_check(name, hyp, mech, self.dead_rows_fn())
        prop["dead_check"] = dc
        if dc["refused"]:
            self.event("dead_list_refused", name=name, reason=dc["reason"])
            return {"accepted": False, "gate": "dead list", "reason": dc["reason"], "nearest_closed_rows": dc["nearest"],
                    "next": "propose a materially different mechanism (or finish)"}
        prev = self.idea.get("proposal")
        self.idea["proposal"] = prop
        if prev:                                     # a revised proposal: the plugin must be (re)written and re-gated
            self.idea["plugin"] = {"attempts": int(self.idea["plugin"].get("attempts", 0))}
            self.idea["gates"] = {}
        self.event("proposal_accepted", name=name, first_signal_bar=fsb["label"], entry_fill=entry_fill_label(ef),
                   time_stop_bars=tsb)
        notes = bar_convention_notes("%s\n%s" % (hyp, mech), tf)
        return {"accepted": True, "name": name, "dead_list": dc["reason"], "already_run": dd["reason"],
                "first_signal_bar": "%s on %s bars: no entry may FILL before it - checked on the contract smoke and on "
                                    "every PRE-WF trade (a violation is a hard gate failure)" % (fsb["label"], tf),
                "entry_fill": "%s - checked on every contract-smoke entry" % entry_fill_label(ef),
                "time_stop": "%s%s" % (time_stop_label(tsb), " - checked on the contract smoke" if tsb else ""),
                **({"bar_convention": notes} if notes else {}),
                "plugin_file": "augur_strategies/qwen_lab/%s.py" % name,
                "note": "the power-first map reads this prior inside run_stage_a, after the plugin gates; its "
                        "verdict is recorded and posted (MANAGER #134: it no longer stops the idea)",
                "next": "write_plugin(name, code)"}

    def t_write_plugin(self, name, code):
        pr = self.idea.get("proposal")
        if not pr:
            raise ToolRefused("propose first (the proposal must pass the dead-list check)")
        if (self.idea.get("stage_pre_wf") or (self.idea.get("prereg") or {}).get("posted_id")) \
                and not self.idea.get("sanity_open"):
            raise ToolRefused("the prereg is posted / Stage A ran - the plugin is frozen (its hash is pre-registered)")
        if missing_contract_fields(pr):
            raise ToolRefused(NO_FSB_REFUSAL % (pr["name"], ", ".join(missing_contract_fields(pr))))
        name = self._name(name)
        if name != pr["name"]:
            raise ToolRefused("the plugin name must be the proposal's: %s" % pr["name"])
        pl = self.idea["plugin"]
        limit = self._attempt_limit()
        if int(pl.get("attempts", 0)) >= limit:
            raise ToolRefused("plugin attempt limit (%d) reached" % limit)
        src = clean_code(code)
        rep_ = self._failed_before(src, int(pl.get("attempts", 0)))
        if rep_:                       # the 10-15 live run: the model re-sent one failed file three times, verbatim
            self.event("identical_resubmission", same_as=rep_[0], gate=rep_[1])
            raise ToolRefused("this code is IDENTICAL to attempt %d, which failed the %s gate (%s). The same file "
                              "cannot pass - change the code that the gate names (no attempt used)%s"
                              % (rep_[0], rep_[1], rep_[2][:400],
                                 (". Hint: " + " ".join(lookahead_hints([rep_[2]]))) if lookahead_hints([rep_[2]])
                                 else ""))
        new_sha = lf_sha256_bytes(src.encode("utf-8"))                 # the LF sha the file will have on disk
        # MANAGER #153a / TTM #155: QL_TOM_CALENDAR_NQ re-sent the plugin that ran its PRE-WF Stage A eight times
        # (same sha), each counted as an attempt. An identical file is no fix: refused, no attempt, never a retry
        ran_here = idea_ran_shas(self.idea)
        if new_sha in ran_here:
            self.event("identical_sha_refused", sha=new_sha, ran_as=ran_here.index(new_sha))
            raise ToolRefused("this plugin is byte-identical (LF sha256 %s) to the plugin that already ran this idea's "
                              "PRE-WF Stage A%s - the same file gives the same trades, so it is NO fix: it never counts "
                              "as a retry and never re-runs (no attempt used). Change the code the broken-plugin check "
                              "named (the entry condition), then write_plugin again."
                              % (new_sha[:16], (" (fix retry %d)" % ran_here.index(new_sha))
                                 if ran_here.index(new_sha) else ""))
        dup = plugin_sha_ran_elsewhere(self.lab, new_sha, exclude=self.idea.get("id"))
        if dup:                                                         # MANAGER #158/#162: never the same plugin twice
            self.event("duplicate_plugin_refused", sha=new_sha, of=dup["idea"])
            raise ToolRefused("this plugin is byte-identical (LF sha256 %s) to the plugin idea %s (%s) already ran (%s) "
                              "- the lab never runs the same plugin twice (MANAGER #158/#162; no attempt used). Write "
                              "the rule THIS proposal states." % (new_sha[:16], dup["idea"], dup["name"], dup["verdict"]))
        if pl.get("gates_ok") and pl.get("gates_sha") == new_sha and pl.get("gates_version") == GATES_VERSION:
            raise ToolRefused("this plugin is identical (LF sha256 %s) to the one that already passed every gate - "
                              "nothing to re-gate (no attempt used): call run_stage_a(%s)" % (new_sha[:16], name))
        pl["attempts"] = int(pl.get("attempts", 0)) + 1
        k = pl["attempts"]
        ok, reasons = safety_gate(src)
        with open(os.path.join(self.dir, "plugin_v%d.py.txt" % k), "w", encoding="utf-8", newline="\n") as f:
            f.write(src)                                        # an inert copy for the record (.txt, never imported)
        gates = {"attempt": k, "safety": {"ok": ok, "reasons": reasons}, "proposal_key": self._proposal_key()}
        if not ok:
            self.event("safety_gate_failed", attempt=k, reasons=reasons[:5])
            jdump(os.path.join(self.dir, "gates_v%d.json" % k), gates)
            return {"passed": False, "gate": "safety", "reasons": reasons, "written": False,
                    "attempts_left": self._attempt_limit() - k}
        path = self.plugin_path(name)
        os.makedirs(self.lab.plugin_dir, exist_ok=True)
        init = os.path.join(self.lab.plugin_dir, "__init__.py")
        if not os.path.exists(init):
            with open(init, "w", encoding="utf-8", newline="\n") as f:
                f.write('"""QWEN LAB plugins (tools/qwen_lab.py). Written by the local model, gated by the harness. '
                        'Nothing here ships to main without a Claude lane review."""\n')
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(src)
        sha = lf_sha256_file(path)
        pl.update(name=name, path=path, sha=sha, gates_ok=False)
        self.event("plugin_written", attempt=k, sha=sha)
        pin = MASTERS[(pr["instrument"], pr["timeframe"])]
        cost, mult = idea_costs(self.idea, pr["instrument"])
        fsb = pr.get("first_signal_bar") or {}
        ef = pr.get("entry_fill") or {}
        req = dict(instrument=pr["instrument"], timeframe=pr["timeframe"], source=pin["source"],
                   session=pin["session"], master_filename=pin["filename"], cost_pts=cost, mult=mult,
                   smoke_to=SMOKE_TO, mem_gb=SANDBOX_MEM_GB, first_signal_bar=fsb.get("index"),
                   entry_fill={"at": ef.get("at"), "bar": ef.get("bar")} if ef.get("at") else None,
                   time_stop_bars=pr.get("time_stop_bars"))
        c = self.sandbox("contract", path, sha, req, self.dir, label="contract_v%d" % k)
        gates["contract"] = c
        if not c.get("ok"):
            self.event("contract_failed", attempt=k, error=c.get("error"), problems=(c.get("problems") or [])[:4])
            jdump(os.path.join(self.dir, "gates_v%d.json" % k), gates)
            out = {"passed": False, "gate": "contract", "error": c.get("error"),
                   "where_in_your_file": plugin_traceback(c, path), "problems": c.get("problems"),
                   "warnings": c.get("warnings"), "attempts_left": self._attempt_limit() - k}
            if c.get("entry_fill_violations"):                           # MANAGER #160b/#162: the offending entries
                out["offending_entry_fills"] = c["entry_fill_violations"]
                out.setdefault("how_to_fix", []).append(
                    "your proposal states the entry fills at %s; the entries above do not (price = the fill price, "
                    "bar_open / bar_close = that bar's open and close, session_bar = its in-session index by the "
                    "clock). Fill exactly there - a decision on bar k's close fills at bar k+1's OPEN (o[k+1]) or at "
                    "bar k's CLOSE (c[k]) - or (proposal slots allowing) propose again with the entry_fill the rule "
                    "really has." % entry_fill_label(ef))
            if c.get("entry_fill_corner_violations"):                    # review round 4: at a searched knob value
                out["offending_entry_fill_knob_values"] = c["entry_fill_corner_violations"]
                out.setdefault("how_to_fix", []).append(
                    "the Auto-Validate searches every knob between its min and max (and every option), and at the knob "
                    "values above the entries do not fill at %s. The fill's price point is part of the rule: no knob "
                    "may switch it - fix the code (or, proposal slots allowing, propose the entry_fill the rule really "
                    "has)." % entry_fill_label(ef))
            if c.get("time_stop_violations") or c.get("time_stop_patterns"):
                out["offending_time_stops"] = c.get("time_stop_violations")
                out["time_stop_patterns"] = c.get("time_stop_patterns")
                out.setdefault("how_to_fix", []).append(
                    "your proposal states a time stop of %s. The convention: entry on bar e (its fill bar) -> exit at "
                    "the CLOSE of bar e + N, i.e. exit_bar - entry_bar == N (stops / targets / the session end may exit "
                    "earlier, nothing later). E.g. `if j - e >= N: x, px = j, c[j]` inside the bar loop. A time stop "
                    "the code has must be the stated one (the trades above show the one it really has - "
                    "bars_held, exit_price vs bar_open / bar_close)%s."
                    % (time_stop_label(pr.get("time_stop_bars")),
                       ("; the plugin's own time stop is %s bars" % (c.get("time_stop") or {})["effective_time_stop"])
                       if (c.get("time_stop") or {}).get("effective_time_stop") else ""))
            if c.get("first_signal_bar_violations"):                     # TTM #144: the offending entries
                out["offending_entries"] = c["first_signal_bar_violations"]
                out["how_to_fix"] = ["your proposal pre-registered %s as the earliest bar an entry may FILL on; these "
                                     "entries fill earlier (session_bar = the in-session index of the entry bar by its "
                                     "OPEN clock: 09:30 + index x bar minutes). Start the entry loop so the FILL bar "
                                     "is >= %d - e.g. a decision on bar k's close filled at bar k+1's open needs k + 1 "
                                     ">= %d - or the proposal and the plugin disagree about the bar index (bar 0 = the "
                                     "09:30 open)." % (fsb.get("label"), fsb.get("index"), fsb.get("index"))]
            if c.get("first_signal_bar_corner_violations"):              # a searched knob value fires earlier
                out["offending_knob_values"] = c["first_signal_bar_corner_violations"]
                out.setdefault("how_to_fix", []).append(
                    "the Auto-Validate searches every knob between its min and max, and at the knob values above the "
                    "plugin fills before %s - so the pre-registered bar does not hold for the searched rule. Narrow "
                    "that knob's range (e.g. raise its min) so no searched value fills before bar %d, or (proposal "
                    "slots allowing) propose again with first_signal_bar = the earliest bar any searched value can "
                    "fill on." % (fsb.get("label"), fsb.get("index")))
            return out
        # TTM #155: the smoke's trade rate against the stated prior - the broken-plugin rule (MANAGER #139) run before any
        # prereg, so a rule that barely fires never burns a PRE-WF fix retry
        rate = smoke_rate_check(c.get("smoke"), self.idea)
        gates["rate"] = dict(rate, ok=not rate["hard"], problems=[rate["hard"]] if rate["hard"] else [])
        if rate["hard"]:
            self.event("rate_check_failed", attempt=k, why=rate["hard"])
            jdump(os.path.join(self.dir, "gates_v%d.json" % k), gates)
            return {"passed": False, "gate": "contract (trade rate - TTM #155)", "problems": [rate["hard"]],
                    "smoke": c.get("smoke"), "stated_trades_per_year": pr["trades_per_year"],
                    "how_to_fix": ["the PRE-WF broken-plugin check (MANAGER #139) would stop this rule too: check the "
                                   "entry condition against real sessions (an impossible threshold, a wrong index, a "
                                   "session window off by one, a calendar counted from the start of the data instead "
                                   "of the real dates) and fix the plugin - or, if the rule really trades that rarely "
                                   "and the proposal is not frozen yet, propose again with an honest trades_per_year "
                                   "(under %.0f a year - %.0f for a scalp - is a broken plugin by house rule)"
                                   % (SANITY_MIN_TPY, SANITY_MIN_TPY_SCALP)],
                    "attempts_left": self._attempt_limit() - k}
        la_from, la_to = ("2015-07-01", SMOKE_TO) if pr["timeframe"] == "1m" else (DATA_FROM, SMOKE_TO)
        la = self.sandbox("lookahead", path, sha, dict(req, la_from=la_from, la_to=la_to, la_k=8), self.dir,
                          label="lookahead_v%d" % k)
        gates["lookahead"] = la
        jdump(os.path.join(self.dir, "gates_v%d.json" % k), gates)
        if not la.get("ok"):
            self.event("lookahead_failed", attempt=k, error=la.get("error"), problems=(la.get("problems") or [])[:4])
            return {"passed": False, "gate": "look-ahead audit", "error": la.get("error"),
                    "where_in_your_file": plugin_traceback(la, path), "problems": la.get("problems"),
                    "how_to_fix": lookahead_hints(la.get("problems")),
                    "attempts_left": self._attempt_limit() - k}
        pl.update(gates_ok=True, gates_sha=sha, gates_file="gates_v%d.json" % k, gates_version=GATES_VERSION)
        self.idea["gates"] = {"sha": sha, "version": GATES_VERSION, "safety": True, "contract": True,
                              "lookahead": True,
                              "contract_warnings": c.get("warnings"), "lookahead_warnings": la.get("warnings"),
                              "smoke": c.get("smoke"), "la_window": la.get("la_window"),
                              "perturbed_trades": la.get("perturbed_trades"), "fills_checked": la.get("fills_checked"),
                              "first_signal_bar": c.get("first_signal_bar"),
                              "first_signal_bar_corners": c.get("first_signal_bar_corners"),
                              "entry_fill": c.get("entry_fill"), "time_stop": c.get("time_stop"),
                              "entry_fill_corners": c.get("entry_fill_corners"),
                              "searched_knobs": la.get("searched_knobs"),
                              "rate_check": {k2: rate[k2] for k2 in ("stated_per_year", "smoke_per_year", "ratio",
                                                                     "flag")},
                              "entry_bar_checked": la.get("entry_bar_checked"),
                              "entry_bar_conclusive": la.get("entry_bar_conclusive"),
                              "entry_bar_corners": la.get("entry_bar_corners"),
                              "open_exits_checked": la.get("open_exits_checked"),
                              "calendar_module": c.get("calendar_module")}
        self.event("gates_passed", attempt=k, sha=sha)
        sched = schedule_check(pr["trades_per_year"], (c.get("smoke") or {}).get("trades_per_year"))
        if rate["flag"]:
            sched["notes"].append(rate["flag"])
        return {"passed": True, "sha256": sha, "contract": {"smoke": c.get("smoke"), "warnings": c.get("warnings"),
                                                             "corners": (c.get("corners") or [])[:8],
                                                             "first_signal_bar": c.get("first_signal_bar"),
                                                             "entry_fill": c.get("entry_fill"),
                                                             "time_stop": c.get("time_stop")},
                "lookahead": {"window": la.get("la_window"), "perturbed_trades": la.get("perturbed_trades"),
                              "fills_checked": la.get("fills_checked"), "warnings": la.get("warnings")},
                "schedule_check": sched,
                "next": "run_stage_a(name)" if sched["ok"] else
                        "your rule's schedule does not match your proposal: revise it (propose + write_plugin) or "
                        "call run_stage_a (the map reads the counted rate)"}

    def _proposal_key(self):
        """What the contract judged a plugin against (first_signal_bar, entry_fill, time stop, stated rate): the same
        file is a different submission once the proposal changed these."""
        pr = self.idea.get("proposal") or {}
        return [(pr.get("first_signal_bar") or {}).get("index"), (pr.get("entry_fill") or {}).get("at"),
                (pr.get("entry_fill") or {}).get("bar"), pr.get("time_stop_bars"), pr.get("trades_per_year")]

    def _failed_before(self, src, attempts):
        """(attempt, gate, problem) when `src` is the text of an earlier attempt that failed a gate (read from the
        idea folder's plugin_v<k>.py.txt + gates_v<k>.json, so it also covers attempts made before a resume) - against
        the same proposal (a revised first_signal_bar / entry_fill / time stop / rate may make the same file pass)."""
        norm = src.replace("\r\n", "\n").strip()
        key = self._proposal_key()
        for k in range(1, attempts + 1):
            pth = os.path.join(self.dir, "plugin_v%d.py.txt" % k)
            if not os.path.isfile(pth):
                continue
            with open(pth, encoding="utf-8") as f:
                if f.read().replace("\r\n", "\n").strip() != norm:
                    continue
            g = jload(os.path.join(self.dir, "gates_v%d.json" % k), None)
            if g and "proposal_key" in g and g["proposal_key"] != key:
                continue
            bad = _gate_failed(g)
            if bad:
                return (k,) + bad
        return None

    def _load_master(self, instrument, timeframe, date_from=DATA_FROM, date_to=WF1):
        _, _, _, D = _eng()
        m = pinned_master(instrument, timeframe)
        A = D.load_master_arrays(m, date_from=date_from, date_to=date_to)
        assert_wf_only(A["index"])
        return m, A

    def write_prereg(self, master, arrays):
        """The prereg names BOTH stages (MANAGER #134). `arrays` is the PRE-WF slice (loaded for its fingerprint)."""
        pr, mp, pl = self.idea["proposal"], self.idea["map"], self.idea["plugin"]
        cost, mult = idea_costs(self.idea, pr["instrument"])
        harness_sha = lf_sha256_file(HARNESS_PATH)
        d = os.path.join(self.lab.home, "preregs")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%s_%s.md" % (pr["name"], today()))
        sh = self.idea.get("shelf") or {}
        g = self.idea.get("gates") or {}
        fsb = pr.get("first_signal_bar") or {}
        fsc = g.get("first_signal_bar") or {}
        # every 'checked' line below says what the gates RECORDED - a check that did not run is written 'not checked'
        if fsb.get("index") is None:
            fsb_check = "- (no first-signal-bar check: not stated - the proposal predates TTM #144)"
        elif not fsc:
            fsb_check = ("- NOT checked by the contract (the plugin's gates record has no first-signal-bar result); "
                         "checked on EVERY PRE-WF trade before any verdict")
        else:
            fsb_check = ("- checked by Python: the contract smoke (%s..%s, default knobs: %s entries checked, %s before "
                         "bar %s; earliest entry at session bar %s), every searched knob at its min and its max (%s), "
                         "and EVERY PRE-WF trade before any verdict - the in-session index is read from each bar's "
                         "OPEN clock. A violation is a hard gate failure: no verdict, the plugin goes back to Qwen with "
                         "the offending entries (a fix retry with an ADDENDUM, like a broken plugin)"
                         % (DATA_FROM, SMOKE_TO, fsc.get("checked"), fsc.get("n"), fsb.get("index"),
                            fsc.get("earliest_session_bar"),
                            "%d knob values, none earlier" % len(g["first_signal_bar_corners"])
                            if g.get("first_signal_bar_corners") is not None else "not recorded"))
        # MANAGER #160b/#162: the entry fill and the time stop, as stated and as the contract smoke checked them
        ef, efc, tsc = pr.get("entry_fill") or {}, g.get("entry_fill") or {}, g.get("time_stop") or {}
        tsb = pr.get("time_stop_bars")
        ef_lines = [
            ("- entry fill (Qwen's stated pre-data input%s): %s" % (
                ", amended %s" % pr["contract_amended_at"] if "entry_fill" in (pr.get("contract_amended_fields") or [])
                else "", entry_fill_label(ef)) if ef.get("at") else
             "- entry fill: not stated (the proposal predates MANAGER #160b) - not checked"),
            ("- time stop (Qwen's stated pre-data input): %s" % time_stop_label(tsb) if tsb is not None else
             "- time stop: not stated (the proposal predates MANAGER #160b) - not checked"),
            ("- checked by Python on the contract smoke (%s..%s, default knobs): %s entries, %s not filling at the "
             "stated bar / price point%s - a violation is a hard gate failure with the offending trades returned"
             % (DATA_FROM, SMOKE_TO, efc.get("checked"), efc.get("n"),
                ("; the time stop on %s trades: %s held past it, %s exits at it" % (
                    tsc.get("checked"), tsc.get("held_past"), tsc.get("at_time_stop")) if tsc.get("time_stop_bars")
                 else "") if tsc or not tsb else "; the time stop NOT checked by the contract")
             if efc else ("- entry fill / time stop NOT checked by the contract (the plugin's gates record has no "
                          "entry-fill result)" if ef.get("at") else "- (no entry-fill / time-stop check)"))]
        if ef.get("at") in ("open", "close"):                    # review round 4: the price point at every searched value
            ef_lines.append("- the entry fill's price point at every knob value the Auto-Validate searches: %s"
                            % ("%d values checked, none off" % len(g["entry_fill_corners"])
                               if g.get("entry_fill_corners") is not None else "NOT checked (older gates)"))
        if tsb is not None:
            ef_lines.append("- the plugin's own time stop (read from the realised holds: a shorter one than stated, or "
                            "one with time_stop_bars 0, fails): %s" % ("checked, none" if "effective_time_stop" in tsc
                                                                       else "NOT checked (older gates)"))
        rc = g.get("rate_check") or {}
        rate_line = ("- trade rate (TTM #155): %s a year on the contract smoke vs the stated %s (ratio %s) - within 3x "
                     "below, else the gate fails%s" % (rc.get("smoke_per_year"), rc.get("stated_per_year"),
                                                       rc.get("ratio"), "; FLAG: " + rc["flag"] if rc.get("flag") else "")
                     if rc else "- trade rate vs the stated prior (TTM #155): NOT checked at the contract (older gates)")
        cal_path, cal_sha = calendar_pin()                       # pinned: re-checked before each stage, loaded by path
        ddp = pr.get("dedupe")
        try:
            dd_now = dedupe_check(pr["name"], pr["mechanism"], ran_ideas(self.lab, exclude=self.idea.get("id")),
                                  reopened_shelf=self._reopened_shelf())
            now_txt = "re-checked now: %s" % dd_now["reason"]
        except Exception as e:                                   # noqa: BLE001
            now_txt = "re-check failed (%s)" % e
        if ddp:
            dedupe_line = ("- ideas the lab already ran (MANAGER #148: same name / mechanism family / near copy refused "
                           "at propose): checked at propose (%s): %s; %s; this proposal's families: %s"
                           % (ddp.get("at"), ddp.get("reason"), now_txt, ", ".join(ddp.get("families") or []) or "none"))
        elif "families" in pr:
            dedupe_line = ("- ideas the lab already ran (MANAGER #148): checked at propose - no match; %s; this "
                           "proposal's families: %s" % (now_txt, ", ".join(pr.get("families") or []) or "none"))
        else:
            dedupe_line = ("- ideas the lab already ran (MANAGER #148): NOT checked at propose (the proposal predates "
                           "MANAGER #148); %s" % now_txt)
        gates_done = ["safety gate (AST whitelist)",
                      "contract test (synthetic battery + real smoke + every searched knob value: ranged knobs at "
                      "min/max, str / bool options%s%s%s)"
                      % (" + the first-signal-bar check" if fsc else "; first-signal-bar check NOT recorded",
                         " + the entry-fill / time-stop check" if efc else "; entry-fill check NOT recorded",
                         " + the trade rate within 3x of the stated prior" if rc else "; rate check NOT recorded"),
                      "look-ahead audit (exec_feasibility_audit file checks; perturbation of %s sampled trades; %s; %s; "
                      "%s fills inside their bars%s)"
                      % (g.get("perturbed_trades"),
                         ("entry-bar inputs - the first bar at risk's high / low / close / volume moved - on %s trades, "
                          "%s conclusive%s" % (g.get("entry_bar_checked"), g.get("entry_bar_conclusive"),
                                               ", plus %s knob corners" % len(g["entry_bar_corners"])
                                               if g.get("entry_bar_corners") else ""))
                         if g.get("entry_bar_checked") is not None else "entry-bar inputs NOT checked (older gates)",
                         ("open exits (the exit bar's high / low / close moved) on %s trades"
                          % g["open_exits_checked"]) if g.get("open_exits_checked") is not None
                         else "open-exit phase NOT run (older gates)",
                         g.get("fills_checked"),
                         ("; every phase again at %d searched knob values (%s)"
                          % (len(g["entry_bar_corners"]), "knobs: " + ", ".join(g["searched_knobs"])
                             if g.get("searched_knobs") else "every searched knob NOT recorded - older gates"))
                         if g.get("entry_bar_corners") and g.get("open_exits_checked") is not None else ""),
                      "idea dedupe" if (ddp or "families" in pr) else "idea dedupe NOT run at propose",
                      "dead list"]
        lines = [
            "# QWEN LAB PREREG - %s (%s)" % (pr["name"], today()), "",
            "Written by tools/qwen_lab.py BEFORE either Stage A and posted to MANAGER before any run. Every number in "
            "this file is either Qwen's stated PRE-DATA input (marked) or computed by Python (marked). Qwen supplies no "
            "result.", "",
            "## Source", ("Reading shelf #%s: %s - %s (%s), %s." % (sh.get("n"), sh.get("title"), sh.get("authors"),
                                                                  sh.get("year"), sh.get("venue"))
                          if self.idea.get("source", "shelf") == "shelf" else
                          "%s (idea source rotation, MANAGER #133). Brief given to the model: %s"
                          % (SOURCE_LABEL.get(self.idea.get("source")), idea_brief(self.idea))), "",
            "## Hypothesis (Qwen's words, verbatim)", pr["hypothesis"], "",
            "## Mechanism (Qwen's words, verbatim)", pr["mechanism"], "",
            "## Bar index convention (TTM #145)",
            "- every bar index in this file is the 0-based IN-SESSION index WITH the clock time of that bar's OPEN: "
            "bar 0 (09:30 open) is the first regular-hours bar; on %s bars %s; bar k's close is bar k+1's open time "
            "(bar 11 closes at %s)" % (pr["timeframe"], bar_label(12, pr["timeframe"]), bar_clock(12, pr["timeframe"])),
            "- an entry 'at bar k's open' fills at bar k's OPEN price (its decision used bars <= k-1); 'at bar k's "
            "close' fills at bar k's CLOSE (its decision used bars <= k). The trade list records the FILL bar.",
            "- a time stop of N bars exits at the CLOSE of entry bar + N (exit_bar - entry_bar = N, 'N bars held') - "
            "the one bar-count convention (MANAGER #160b/#162)", "",
            "## Timing contract - the first entry bar (TTM #144), the entry fill and the time stop (MANAGER #160b/#162)",
            ("- first_signal_bar (Qwen's stated pre-data input%s): %s - no entry may FILL at an in-session bar index "
             "< %d, with the default knobs or any knob value the Auto-Validate searches"
             % (", amended %s" % pr["first_signal_bar_amended_at"] if pr.get("first_signal_bar_amended_at") else "",
                fsb.get("label"), fsb.get("index")) if fsb.get("index") is not None else
             "- first_signal_bar: not stated (the proposal predates TTM #144) - not checked"),
            fsb_check] + ef_lines + ["",
            "## Dates (MANAGER #156)",
            "- the plugin may read REAL dates: the bar timestamps (`index`) and augur_engine/session_calendar.py "
            "(session_dates, is_last_n_sessions_of_month, session_index_in_month, week_of_month, days_to_month_end); "
            "the month-end helpers read the published CME equity-index calendar alone (never the data's own dates: a "
            "data hole is a session with no bars, so an answer never depends on where the load starts or ends) and "
            "date each session by its trading day - knowable in advance, not prices",
            "- session_calendar.py the sandbox imports: %s (LF sha256 %s) - the sandbox loads exactly this file and "
            "checks this hash, re-checked before each stage" % (cal_path or "-", cal_sha or "-"), "",
            "## Prior (Qwen's stated pre-data input)",
            "- yearly Sharpe after costs and decay: %s" % pr["prior_sharpe_yearly"],
            "- trades a year: %s" % pr["trades_per_year"], "",
            "## Power first (computed by Python: tools/mapcheck_f.py generator and rules) - RECORDED, NOT A STOP",
            "- MANAGER #134 (owner: the lab must actually test): the map's verdict is recorded and posted; a greyed or "
            "closed map no longer stops the idea",
            "- prior as mapped: %s" % json.dumps(mp.get("prior")),
            "- seed %s, %s draws" % (mp.get("seed"), mp.get("draws")),
            "- own WF ROC@30k median %s; P(own >= 15) %s; P(lift #463, WF) %s; median book ROC %s"
            % (mp.get("own_wf_roc_median"), mp.get("p_own_roc_ge_15"), mp.get("p_lift_463"),
               mp.get("book_roc_median")),
            "- trade rate: %s" % (mp.get("trade_rate") or {}).get("note", "stated rate used"),
            "- verdict: %s" % mp["verdict"], "",
            "## Dead list (computed by Python)", "- %s" % pr.get("dead_check", {}).get("reason"),
            "- nearest closed rows: %s" % ", ".join("%s (%.2f)" % (x["row"], x["match"])
                                                    for x in pr.get("dead_check", {}).get("nearest", [])),
            dedupe_line, "",
            "## Hard gates passed before this prereg (gates v%s)" % (g.get("version") or pl.get("gates_version") or 1),
            "- " + ", ".join(gates_done), rate_line,
            "- the contract smoke and the look-ahead audit read pre-walk-forward bars only (%s..%s); no walk-forward "
            "bar was read before this prereg" % (DATA_FROM, SMOKE_TO), "",
            "## Data (both stages)",
            "- instrument %s, %s RTH bars; master pinned BY FILENAME: %s (source %s, registry id %s)"
            % (pr["instrument"], pr["timeframe"], master.get("filename"), master.get("source"), master.get("id")),
            "- cost %s points a round trip x $%s a point (%s); 1 contract; params = the file's DEFAULT_PARAMS defaults, "
            "no tuning" % (cost, mult, "the 10-12 scalp hunt's short-hold basis" if self.idea.get("source") == "scalper"
                          else "house RTH cost for %s" % pr["instrument"]),
            "- single-threaded sandbox subprocess, AUGUR_TRIAL_CACHE=1", "",
            "## Stage 1 - PRE-WF Stage A (every idea that passed the hard gates)",
            "- window %s..%s: the pre-walk-forward rows only (the house WF starts %s); data loaded %s..%s (%d bars, "
            "fingerprint %s); the window end before the WF start is asserted in the sandbox and the harness"
            % (PREWF0, PREWF1, WF0, str(arrays["index"][0])[:10], str(arrays["index"][-1])[:10], len(arrays["close"]),
               arrays.get("fingerprint")),
            "- reported (computed by Python): ROC %%/yr at a $30k drawdown, DD5 (one-episode flag: True / False / NOT "
            "TESTABLE when DD5 is one episode or the curve never makes a new high - MANAGER #160a), DD %% from peak "
            "($100k start), Sortino, trades and trades a year, net per trade in points and $, gross per trade in "
            "points against the %s pt round-trip cost and the gross / cost ratio; posted as 'QWEN LAB: <idea> PRE-WF "
            "...'" % cost,
            "- BROKEN-PLUGIN CHECK before any verdict (MANAGER #139): pre-WF trades a year more than %.0fx below the "
            "stated %s/yr, under %.0f/yr, or under %.0f/yr for a scalp idea -> the plugin goes back to Qwen with "
            "the count and real sessions of bars (no verdict); at most %d retries, each a CHANGED plugin (an identical "
            "file is refused and never counts - MANAGER #153a) through every hard gate with an ADDENDUM line here "
            "posted to MANAGER before the re-run; the result line says 'retries k/%d'; still failing -> BROKEN PLUGIN "
            "(n trades; retries %d/%d still broken), not a dead idea" % (
                SANITY_RATIO, pr["trades_per_year"], SANITY_MIN_TPY, SANITY_MIN_TPY_SCALP, SANITY_MAX_RETRIES,
                SANITY_MAX_RETRIES, SANITY_MAX_RETRIES, SANITY_MAX_RETRIES),
            "- PROMOTION RULE: the WF Stage A runs only if %s" % PROMOTION_RULE,
            "- a shelf paper is closed for the lab only after a SANE PRE-WF Stage A (not a broken plugin - MANAGER "
            "#153b)", "",
            "## Stage 2 - WF Stage A (only if promoted)",
            "- walk-forward %s..%s ONLY (data loaded from %s to warm indicators; trades entering before %s dropped). "
            "Lockbox %s..%s is never loaded (asserted)." % (WF0, WF1, DATA_FROM, WF0, LB0, LB1),
            "- the same four numbers on the WF stretch",
            "- Auto-Validate only if WF ROC@30k >= %.0f AND not one episode AND >= %d WF trades AND peak RAM <= %.0f GB; "
            "then 900 trials on this ranged file, window %s..%s, %d-month lockbox, the same master; only one Qwen-lab "
            "validate at a time; the file must be reviewed onto main first" % (
                VALIDATE_BAR_ROC, MIN_WF_TRADES, PEAK_RAM_GB_MAX, VALIDATE_FROM, VALIDATE_TO, VALIDATE_LB_MONTHS), "",
            "## Hashes (LF sha256) - re-checked before EACH stage",
            "- plugin %s: %s" % (os.path.relpath(pl["path"], self.lab.plugin_repo).replace("\\", "/"), pl["sha"]),
            "- harness tools/qwen_lab.py (also the sandbox): %s" % harness_sha,
            "- session calendar helpers %s: %s" % (cal_path or "-", cal_sha or "-"), ""]
        text = "\n".join(lines)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        sha = lf_sha256_file(path)
        with open(os.path.join(self.dir, os.path.basename(path)), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return {"path": path, "sha": sha, "plugin_sha": pl["sha"], "plugin_path": pl["path"],
                "harness_sha": harness_sha, "calendar_path": cal_path, "calendar_sha": cal_sha,
                "master": master.get("filename"), "source": master.get("source"), "cost_pts": cost, "mult": mult}

    def _attempt_limit(self):
        return MAX_PLUGIN_ATTEMPTS + int(self.idea.get("bonus_attempts", 0))

    def _prereg_addendum(self, prereg, retry, path, new_sha):
        """A sanity retry keeps the prereg and appends an ADDENDUM line for the new plugin hash - posted to MANAGER
        BEFORE the re-run (MANAGER #139). A failed post refuses the run."""
        last = self.idea["sanity"][-1]
        harness_sha = lf_sha256_file(HARNESS_PATH)
        rel = os.path.relpath(path, self.lab.plugin_repo).replace("\\", "/")
        pr = self.idea["proposal"]
        amend = ""
        if (pr.get("first_signal_bar_amended_at") or pr.get("contract_amended_at")) \
                and not self.idea.get("fsb_amendment_posted"):
            fields = pr.get("contract_amended_fields") or ["first_signal_bar"]
            amend = (" Timing contract AMENDED at %s: %s (TTM #144 / MANAGER #160b: the frozen proposal predated the "
                     "fields; checked on the contract smoke%s)." % (
                         pr.get("contract_amended_at") or pr.get("first_signal_bar_amended_at"), "; ".join(
                             {"first_signal_bar": "first_signal_bar %s" % (pr.get("first_signal_bar") or {}).get("label"),
                              "entry_fill": "entry fill %s" % entry_fill_label(pr.get("entry_fill")),
                              "time_stop_bars": "time stop %s" % time_stop_label(pr.get("time_stop_bars"))}[f]
                             for f in fields), ", at every searched knob's min / max and on every PRE-WF entry"
                         if "first_signal_bar" in fields else ""))
        cal_path, cal_sha = calendar_pin()
        line = ("ADDENDUM %d (%s; MANAGER #139 / TTM #144 fix retry %d of %d): the previous plugin (sha %s): %s - "
                "a check before any verdict (broken plugin / first-signal-bar contract), NOT a verdict on the idea.%s "
                "New plugin %s LF sha256 %s passed the safety gate, "
                "the contract test and the look-ahead audit again (gates v%s, %s). Harness LF sha256 %s; session "
                "calendar %s LF sha256 %s. Same windows, master, cost and promotion rule; the plugin, harness and "
                "calendar hashes are re-checked before each stage."
                % (retry, now_s(), retry, SANITY_MAX_RETRIES, last["plugin_sha"][:16], last["why"], amend, rel, new_sha,
                   self.idea["plugin"].get("gates_version"), self.idea["plugin"].get("gates_file"), harness_sha,
                   cal_path or "-", cal_sha or "-"))
        text = "%s: PREREG ADDENDUM %d %s (%s) - %s Prereg %s. Replies -> %s." % (
            TAG, retry, _safe_name(self.idea["proposal"]["name"]), source_ref(self.idea), line, prereg["path"], REPLY_TO)
        try:
            pid = self.poster(text)
        except Exception as e:                                   # noqa: BLE001
            self.event("prereg_addendum_post_failed", error=str(e)[:300])
            raise ToolRefused("the prereg addendum could not be posted to MANAGER (%s) - no Stage A runs without it" % e)
        if amend:
            self.idea["fsb_amendment_posted"] = pid
        for p in (prereg["path"], os.path.join(self.dir, os.path.basename(prereg["path"]))):
            try:
                with open(p, "a", encoding="utf-8", newline="\n") as f:
                    f.write("\n## Addendum %d\n%s\n" % (retry, line))
            except OSError:
                pass
        prereg.setdefault("history", []).append({k: prereg.get(k) for k in ("plugin_sha", "harness_sha",
                                                                            "calendar_sha", "sha")})
        prereg.update(plugin_sha=new_sha, plugin_path=path, harness_sha=harness_sha, calendar_path=cal_path,
                      calendar_sha=cal_sha, sha=lf_sha256_file(prereg["path"]))
        prereg.setdefault("addenda", []).append({"n": retry, "posted_id": pid, "at": now_s(), "line": line,
                                                 "sha": prereg["sha"]})
        self.event("prereg_addendum", n=retry, inbox_id=pid, plugin_sha=new_sha)

    def _record_broken(self, why):
        """Out of fix retries (or the model stopped): BROKEN PLUGIN (n trades) - recorded and posted, NOT a dead idea."""
        last = (self.idea.get("sanity") or [{}])[-1]
        nm = last.get("numbers")
        n = (nm or {}).get("trades")
        k = int(last.get("retry", 0) or 0)                              # MANAGER #153a: the retries that RE-RAN
        tries = "retries %d/%d%s" % (k, SANITY_MAX_RETRIES, " still broken" if k >= SANITY_MAX_RETRIES else "")
        verdict = "BROKEN PLUGIN (%s; %s)" % ("%d trade%s" % (n, "" if n == 1 else "s") if n is not None
                                              else "the Stage A failed", tries)
        if last.get("kind") == "first_signal_bar":                     # TTM #144
            fv = last.get("first_signal_bar_violations") or {}
            verdict = "BROKEN PLUGIN (first-signal-bar contract: %s entries before bar %s; %s)" % (
                fv.get("n"), fv.get("first_signal_bar"), tries)
        rec = dict(last.get("stage") or {}, numbers=nm, promoted=False, broken=True, window="%s..%s" % (PREWF0, PREWF1),
                   promotion="NOT PROMOTED: %s - a broken plugin, not a verdict on the idea (MANAGER #139)" % verdict,
                   numbers_json=os.path.join(self.dir, "numbers_pre_wf.json"))
        self.idea["stage_pre_wf"] = rec
        self.idea["sanity_open"] = False
        jdump(rec["numbers_json"], rec)
        self.event("broken_plugin", verdict=verdict, why=why)
        text = compose_prewf_post(self.idea)
        try:
            rec["posted_id"] = self.poster(text)
            self.idea["result_post"] = {"inbox_id": rec["posted_id"], "text": text, "at": now_s()}
            self.idea["result_posted_inline"] = True
            self.event("pre_wf_posted", inbox_id=rec["posted_id"])
        except Exception as e:                                   # noqa: BLE001
            rec["post_error"] = str(e)[:300]
            self.event("pre_wf_post_failed", error=str(e)[:300])
        jdump(rec["numbers_json"], rec)
        self.close("%s - %s" % (verdict, why))
        return {"ran": True, "verdict": verdict, "why": why, "next": "finish"}

    @staticmethod
    def prereg_calendar_pin(prereg):
        """(path, LF sha256) of the session calendar the prereg pinned: its record, or (a prereg written before the
        record kept them) the '- session calendar helpers <path>: <sha>' line of the prereg file; (None, None) when it
        names none."""
        if prereg.get("calendar_sha"):
            return prereg.get("calendar_path"), prereg["calendar_sha"]
        try:
            with open(prereg["path"], encoding="utf-8") as f:
                m = re.search(r"^- session calendar helpers (.+): ([0-9a-f]{64})\s*$", f.read(), re.M)
        except (OSError, KeyError, TypeError):
            m = None
        return (m.group(1), m.group(2)) if m else (None, None)

    def _hash_recheck(self, path, prereg, stage):
        if lf_sha256_file(path) != prereg["plugin_sha"]:
            self.event("hash_mismatch", which="plugin", stage=stage)
            raise ToolRefused("HASH MISMATCH before the %s stage: the plugin changed after the prereg - refused" % stage)
        if lf_sha256_file(HARNESS_PATH) != prereg["harness_sha"]:
            self.event("hash_mismatch", which="harness", stage=stage)
            raise ToolRefused("HASH MISMATCH before the %s stage: the harness changed after the prereg - refused" % stage)
        # review round 4: the prereg says the session-calendar sha is re-checked before EACH stage - a calendar plugin's
        # trades depend on that module, so a change after the prereg refuses the stage like the plugin / harness
        # (the sandbox then loads exactly that file and checks the hash again - _stage passes the pin)
        cal_path, cal_sha = self.prereg_calendar_pin(prereg)
        if cal_sha:
            now_sha = lf_sha256_file(cal_path) if cal_path and os.path.isfile(cal_path) else None
            if now_sha != cal_sha:
                self.event("hash_mismatch", which="calendar", stage=stage)
                raise ToolRefused("HASH MISMATCH before the %s stage: the session calendar %s changed after the prereg "
                                  "(now %s, pinned %s) - refused" % (stage, cal_path, (now_sha or "missing")[:16],
                                                                     cal_sha[:16]))
        self.event("hash_recheck", stage=stage, plugin_sha=prereg["plugin_sha"][:16],
                   calendar_sha=(cal_sha or "not pinned (older prereg)")[:24])

    def _stage(self, stretch, path, prereg, master, arrays, load_from, load_to, s0, s1, label, tag=""):
        """One Stage A run in the sandbox + the four numbers computed here. Returns (record or None, error); the record
        carries the trades under '_trades' (popped before it is stored)."""
        pr = self.idea["proposal"]
        pin = MASTERS[(pr["instrument"], pr["timeframe"])]
        cost, mult = idea_costs(self.idea, pr["instrument"])
        self.courtesy(self.lab, "Stage A (%s)" % stretch, self.idea["id"], interruptible=False)    # MANAGER #143
        self._hash_recheck(path, prereg, stretch)
        cal_path, cal_sha = self.prereg_calendar_pin(prereg)
        ev = ("pre_wf" if stretch == "pre_wf" else "stage_a") + tag
        self.event("%s_started" % ev)
        res = self.sandbox("stage_a", path, prereg["plugin_sha"],
                           dict(instrument=pr["instrument"], timeframe=pr["timeframe"], source=pin["source"],
                                session=pin["session"], master_filename=pin["filename"], cost_pts=cost, mult=mult,
                                mem_gb=SANDBOX_MEM_GB, stretch=stretch, load_from=load_from, load_to=load_to,
                                **({"calendar_path": cal_path, "calendar_sha": cal_sha} if cal_sha else {})),
                           self.dir, label=ev)
        if not res.get("ok"):
            self.event("%s_failed" % ev, error=res.get("error"))
            return None, "%s STAGE A FAILED: %s" % (label, str(res.get("error"))[:300])
        if (res.get("bars"), str(res.get("fingerprint"))) != (len(arrays["close"]), str(arrays.get("fingerprint"))):
            return None, ("%s STAGE A REFUSED: the sandbox's data (%s bars, %s) differ from the harness's (%s, %s)"
                          % (label, res.get("bars"), res.get("fingerprint"), len(arrays["close"]),
                             arrays.get("fingerprint")))
        trades = res.get("trades") or []
        if res.get("entry_times") is not None:                   # the sandbox's own entry times = the harness's slice
            n_a = len(arrays["close"])
            mine = [str(arrays["index"][t[0]])[:19] if 0 <= t[0] < n_a else None for t in trades]
            if list(res["entry_times"]) != mine:
                return None, ("%s STAGE A REFUSED: the sandbox's entry times differ from the harness's own bars"
                              % label)
        with open(os.path.join(self.dir, "%s_trades.csv" % ev), "w", encoding="utf-8", newline="\n") as f:
            f.write("entry_bar,exit_bar,pnl_points_net,side,entry_price,entry_time,exit_time\n")
            for t in trades:
                f.write("%d,%d,%.6f,%s,%s,%s,%s\n" % (t[0], t[1], t[2], t[3], t[4], arrays["index"][t[0]],
                                                     arrays["index"][min(t[1], len(arrays["close"]) - 1)]))
        nm = self.numbers_fn(trades, arrays, mult, wf0=s0, wf1=s1, label=label, cost_pts=cost)
        rec = {"numbers": nm, "peak_gb": res.get("peak_gb"), "secs": res.get("secs"), "secs_wall": res.get("secs_wall"),
               "roll": res.get("roll"), "master": master.get("filename"), "source": master.get("source"),
               "cost_pts": cost, "mult": mult, "params": res.get("params"), "trades_total_incl_warmup": len(trades),
               "loaded": "%s..%s" % (str(arrays["index"][0])[:10], str(arrays["index"][-1])[:10]),
               "bars": len(arrays["close"]), "fingerprint": arrays.get("fingerprint"),
               "trades_csv": os.path.join(self.dir, "%s_trades.csv" % ev), "_trades": trades}
        return rec, None

    def t_run_stage_a(self, name):
        if self.idea.get("stage_pre_wf"):
            raise ToolRefused("Stage A already ran for this idea - its numbers are final: PRE-WF %s%s"
                              % (fmt_four(self.idea["stage_pre_wf"].get("numbers")),
                                 ("; WF " + fmt_four(self.idea["stage_a"].get("numbers")))
                                 if self.idea.get("stage_a") else ""))
        if self.closed:
            raise ToolRefused("this idea is closed (%s)" % self.idea.get("outcome"))
        pr = self.idea.get("proposal")
        name = self._name(name)
        if not pr or name != pr.get("name"):
            raise ToolRefused("propose first; the name must be the proposal's")
        pl = self.idea["plugin"]
        # TTM #144 / MANAGER #160b: a proposal from before the timing contract is never run 'not checked' - it records
        # the missing fields first (propose again; a frozen proposal only records them)
        if missing_contract_fields(pr):
            raise ToolRefused(NO_FSB_REFUSAL % (pr["name"], ", ".join(missing_contract_fields(pr))))
        # hard gate 1: safety, re-run on the file as it is on disk now
        path = self.plugin_path(name)
        if not os.path.isfile(path):
            raise ToolRefused("no plugin written yet")
        with open(path, encoding="utf-8") as f:
            ok, reasons = safety_gate(f.read())
        sha = lf_sha256_file(path)
        if not ok:
            raise ToolRefused("safety gate fails on the file on disk: %s" % reasons[:3])
        # hard gates 2-3: contract + look-ahead passed on THIS hash
        if not pl.get("gates_ok") or pl.get("gates_sha") != sha:
            raise ToolRefused("the plugin on disk (sha %s) has not passed the contract and look-ahead gates - call "
                              "write_plugin" % sha[:12])
        if pl.get("gates_version") != GATES_VERSION:                 # gated by an older harness (TTM #144/#145)
            raise ToolRefused("the plugin on disk (sha %s) passed an OLDER version of the gates (v%s; now v%d: the "
                              "first-signal-bar contract and the entry-bar look-ahead audit, TTM #144/#145; the entry-fill "
                              "/ time-stop contract, the trade-rate check, the open-exit phase and every phase at the "
                              "knob corners, fix round 3; a fresh module per run, no caches, every searched knob value "
                              "incl. str / bool options, the entry fill at every searched value and the plugin's own "
                              "time stop, review round 4) - call write_plugin(name, code) again so the current gates run"
                              % (sha[:12], pl.get("gates_version") or 1, GATES_VERSION))
        # MANAGER #158/#162: never the same plugin twice - one a run idea already ran is refused before any Stage A
        dup = plugin_sha_ran_elsewhere(self.lab, sha, exclude=self.idea.get("id"))
        if dup:
            self.event("duplicate_plugin_refused", sha=sha, of=dup["idea"])
            raise ToolRefused("the plugin on disk (sha %s) is byte-identical to the plugin idea %s (%s) already ran (%s) "
                              "- the lab never runs the same plugin twice (MANAGER #158/#162)"
                              % (sha[:16], dup["idea"], dup["name"], dup["verdict"]))
        self.event("gate_order", gate="safety+contract+lookahead", sha=sha)
        # hard gate 4: dead list (re-run on the frozen proposal)
        dc = dead_check(pr["name"], pr["hypothesis"], pr["mechanism"], self.dead_rows_fn())
        if dc["refused"]:
            self.close("REFUSED by the dead list at Stage A: %s" % dc["reason"])
            return {"ran": False, "gate": "dead list", "reason": dc["reason"]}
        self.event("gate_order", gate="dead_list")
        retry = len(self.idea.get("sanity") or [])
        prereg = self.idea.get("prereg") if (self.idea.get("prereg") or {}).get("posted_id") else None
        # LOAD COURTESY before a new Stage A (MANAGER #143) - before anything is written or posted, so a STOP during the
        # wait leaves the idea exactly as it was
        if not self.courtesy(self.lab, "Stage A", self.idea["id"], interruptible=True):
            raise LabStopped()
        if prereg is not None:
            # a broken-plugin retry (MANAGER #139): same prereg + an ADDENDUM for the new plugin hash, posted first
            if not retry or not self.idea.get("sanity_open"):
                raise ToolRefused("Stage A already ran for this idea")
            if sha in idea_ran_shas(self.idea):                    # MANAGER #153a: an identical file never re-runs
                self.event("identical_sha_refused", sha=sha, where="run_stage_a")
                raise ToolRefused("the plugin is unchanged: sha %s already ran this idea's PRE-WF Stage A - the same "
                                  "file gives the same trades, so it never re-runs and never counts as a retry. Fix it "
                                  "with write_plugin first" % sha[:12])
            master, pre_arrays = self.master_loader(pr["instrument"], pr["timeframe"], PREWF0, PREWF1)
            assert_pre_wf(pre_arrays["index"])
            self._prereg_addendum(prereg, retry, path, sha)
            return self._pre_wf_and_after(path, prereg, master, pre_arrays, pr, sha, retry)
        # power first - mapcheck_f on the stated prior, RECORDED and posted, no longer a stop (MANAGER #134). The
        # stated Sharpe is used as stated; a stated trade rate off by more than 2x from the plugin's own pre-WF COUNT
        # (contract smoke, no P&L) is replaced by the count.
        stated_n = float(pr["trades_per_year"])
        smoke = (self.idea.get("gates") or {}).get("smoke") or {}
        counted = smoke.get("trades_per_year")
        n_map, rate_note = stated_n, "stated rate used"
        if counted and counted >= 1 and not (0.5 <= stated_n / counted <= 2.0):
            n_map = float(counted)
            rate_note = ("stated %s trades/yr disagrees with the plugin's own count %s/yr on %s..%s (count only, "
                         "pre-walk-forward) - the map uses the counted rate" % (stated_n, counted, DATA_FROM, SMOKE_TO))
        mp = self.mapcheck(pr["name"], pr["prior_sharpe_yearly"], n_map)
        mp["trade_rate"] = {"stated": stated_n, "counted_pre_wf": counted, "used": n_map, "note": rate_note}
        mp["stops_idea"] = False
        self.idea["map"] = mp
        pr["map"] = mp
        self.event("map_check", name=pr["name"], verdict=mp["verdict"], rate=rate_note, stops_idea=False)
        self.event("gate_order", gate="power_first_recorded")
        # auto prereg naming both stages, posted BEFORE any run
        master, pre_arrays = self.master_loader(pr["instrument"], pr["timeframe"], PREWF0, PREWF1)
        assert_pre_wf(pre_arrays["index"])
        prereg = self.write_prereg(master, pre_arrays)
        self.idea["prereg"] = prereg
        self.event("prereg_written", path=prereg["path"], sha=prereg["sha"])
        try:
            pid = self.poster(compose_prereg_post(self.idea, prereg))
        except Exception as e:                                   # noqa: BLE001
            self.event("prereg_post_failed", error=str(e)[:300])
            raise ToolRefused("the prereg could not be posted to MANAGER (%s) - no Stage A runs without it" % e)
        prereg["posted_id"] = pid
        prereg["posted_at"] = now_s()
        self.event("prereg_posted", inbox_id=pid)
        return self._pre_wf_and_after(path, prereg, master, pre_arrays, pr, sha, retry)

    def _pre_wf_and_after(self, path, prereg, master, pre_arrays, pr, sha, retry):
        # STAGE 1: PRE-WF Stage A
        self.idea["sanity_open"] = False
        rec, err = self._stage("pre_wf", path, prereg, master, pre_arrays, PREWF0, PREWF1, PREWF0, PREWF1, "PRE-WF",
                               tag="_r%d" % retry if retry else "")
        if rec is None and "STAGE A FAILED" not in (err or ""):        # a harness refusal, not the plugin's fault
            self.idea["stage_pre_wf"] = {"error": err, "numbers": None}
            self.close(err)
            return {"ran": False, "error": err}
        trades = rec.pop("_trades", []) if rec else []
        # FIRST-SIGNAL-BAR CONTRACT on every PRE-WF entry (TTM #144) - a plugin that enters before the bar its prereg
        # names is not the pre-registered rule: no verdict, it goes back to Qwen like a broken plugin
        fsb = pr.get("first_signal_bar") or {}
        fsb_v = None
        if rec is not None and fsb.get("index") is not None:
            fsb_v = first_bar_violations(trades, pre_arrays["day_id"], pre_arrays["index"], int(fsb["index"]),
                                         tf=pr["timeframe"])
            rec["first_signal_bar_check"] = {k: fsb_v[k] for k in ("first_signal_bar", "checked", "n",
                                                                    "earliest_session_bar", "index_by")}
        # BROKEN-PLUGIN CHECK before any verdict (MANAGER #139)
        kind = "crash" if rec is None else "sanity"
        if rec is None:
            why_broken = "the plugin crashed on the PRE-WF window: %s" % err
        elif fsb_v and fsb_v["n"]:
            kind = "first_signal_bar"
            why_broken = ("FIRST-SIGNAL-BAR CONTRACT (TTM #144): %d of %d PRE-WF entries fill before %s, the earliest "
                          "bar the prereg allows (earliest entry: session bar %s) - the plugin is not the "
                          "pre-registered rule" % (fsb_v["n"], fsb_v["checked"], fsb.get("label"),
                                                   fsb_v["earliest_session_bar"]))
        else:
            why_broken = sanity_check(rec["numbers"], self.idea)
        if why_broken:
            att = {"retry": retry, "plugin_sha": sha, "why": why_broken, "at": now_s(), "kind": kind,
                   "numbers": (rec or {}).get("numbers"), "stage": rec, "error": err,
                   **({"first_signal_bar_violations": fsb_v} if kind == "first_signal_bar" else {})}
            self.idea.setdefault("sanity", []).append(att)
            jdump(os.path.join(self.dir, "sanity_r%d.json" % retry), att)
            if retry < SANITY_MAX_RETRIES:
                self.idea["sanity_open"] = True
                self.idea["bonus_steps"] = int(self.idea.get("bonus_steps", 0)) + SANITY_BONUS_STEPS
                self.idea["bonus_attempts"] = int(self.idea.get("bonus_attempts", 0)) + SANITY_BONUS_ATTEMPTS
                self.event("sanity_retry", retry=retry + 1, why=why_broken, kind=kind)
                if kind == "first_signal_bar":
                    out = {"ran": True, "verdict": "NONE YET - hard gate: %s" % why_broken,
                           "first_signal_bar": fsb.get("label"), "offending_entries": fsb_v["examples"],
                           "fix_retries_left": SANITY_MAX_RETRIES - retry,
                           "what_to_do": "Your prereg says no entry fills before %s (0-based in-session index, bar 0 = "
                                         "the 09:30 open). The entries above fill earlier (session_bar = their "
                                         "in-session index). Fix the plugin so the FILL bar is never before %d - the "
                                         "proposal is frozen. Then write_plugin(name, code) - every gate runs again - "
                                         "and run_stage_a(name)." % (fsb.get("label"), fsb.get("index")),
                           "_cap": SANITY_RESULT_CHARS}
                    return out
                out = {"ran": True, "verdict": "NONE YET - broken-plugin check (MANAGER #139): %s" % why_broken,
                       "stated_trades_per_year": pr["trades_per_year"],
                       "fix_retries_left": SANITY_MAX_RETRIES - retry,
                       "what_to_do": "Your rule almost never fires on real bars - that is a bug until shown otherwise. "
                                     "Check your entry condition by hand against the sessions below (real %s %s bars "
                                     "from the PRE-WF window); find why it does not fire (an impossible threshold, a "
                                     "wrong index, a session-window off by one, a condition that needs several rare "
                                     "events at once). Then write_plugin(name, code) - every gate runs again - and "
                                     "run_stage_a(name). The proposal stays as it is." % (pr["instrument"],
                                                                                         pr["timeframe"]),
                       "_cap": SANITY_RESULT_CHARS}
                if rec is not None:
                    out.update(trades=rec["numbers"].get("trades"), trades_per_year=rec["numbers"].get("trades_per_year"),
                               trades_by_year=trades_by_year(trades, pre_arrays),
                               your_first_trades=[[str(pre_arrays["index"][int(t[0])]), int(t[3]), round(float(t[2]), 2)]
                                                  for t in trades[:5]],
                               sessions=sanity_sessions(pre_arrays, trades))
                else:
                    out["error"] = str(err)[:1500]
                return out
            return self._record_broken("still %s after %d fix retries" % (why_broken, retry))
        # MANAGER #153b: the shelf paper closes only now - a Stage A with a sane trade count ran (a broken plugin, a
        # crash or a duplicate never closes it)
        if self.idea.get("source", "shelf") == "shelf" and self.idea.get("shelf_n") is not None:
            self.lab.close_shelf(self.idea["shelf_n"], self.idea["id"],
                                 "the lab ran a sane PRE-WF Stage A on it (%d trades)" % rec["numbers"].get("trades", 0))
        promote, why = promotion_bar(rec["numbers"])
        rec.update(promotion=why, promoted=promote, numbers_json=os.path.join(self.dir, "numbers_pre_wf.json"),
                   window="%s..%s" % (PREWF0, PREWF1))
        self.idea["stage_pre_wf"] = rec
        jdump(rec["numbers_json"], rec)
        self.event("pre_wf_done", four=fmt_four(rec["numbers"]), promotion=why)
        text = compose_prewf_post(self.idea)
        try:
            rec["posted_id"] = self.poster(text)
            self.event("pre_wf_posted", inbox_id=rec["posted_id"])
        except Exception as e:                                   # noqa: BLE001
            rec["post_error"] = str(e)[:300]
            self.event("pre_wf_post_failed", error=str(e)[:300])
        jdump(rec["numbers_json"], rec)
        out = {"ran": True, "pre_wf_numbers": rec["numbers"], "pre_wf_four": fmt_four(rec["numbers"]),
               "promotion": why}
        if not promote:
            if rec.get("posted_id"):
                self.idea["result_post"] = {"inbox_id": rec["posted_id"], "text": text, "at": now_s()}
                self.idea["result_posted_inline"] = True
            self.close("PRE-WF DONE - not promoted (%s)" % why.replace("NOT PROMOTED: ", ""))
            out["next"] = "finish (not promoted to the WF Stage A)"
            return out
        # STAGE 2: WF Stage A (promoted)
        master2, arrays = self.master_loader(pr["instrument"], pr["timeframe"], DATA_FROM, WF1)
        rec2, err = self._stage("wf", path, prereg, master2, arrays, DATA_FROM, WF1, WF0, WF1, "WF")
        if rec2 is not None:
            rec2.pop("_trades", None)
        if rec2 is None:
            self.idea["stage_a"] = {"error": err, "numbers": None}
            self.close(err)
            out.update(error=err)
            return out
        met, bar = validate_bar(rec2["numbers"], rec2.get("peak_gb"))
        rec2.update(bar=bar, bar_met=met, numbers_json=os.path.join(self.dir, "numbers.json"),
                    window="%s..%s" % (WF0, WF1))
        self.idea["stage_a"] = rec2
        jdump(rec2["numbers_json"], rec2)
        self.event("stage_a_done", four=fmt_four(rec2["numbers"]), bar=bar)
        if not met:
            self.close("STAGE A DONE - promoted; WF bar not met, no validate")
        out.update(numbers=rec2["numbers"], four_numbers=fmt_four(rec2["numbers"]), validate_bar=bar,
                   next="queue_validate(name)" if met else "finish (the WF bar is not met; no validate)")
        return out

    def t_queue_validate(self, name):
        sa = self.idea.get("stage_a")
        name = self._name(name)
        if not sa or not sa.get("numbers"):
            raise ToolRefused("run_stage_a first")
        met, bar = validate_bar(sa["numbers"], sa.get("peak_gb"))
        if not met:
            raise ToolRefused("the Stage A bar is not met (%s) - no validate" % bar)
        if (self.idea.get("validate") or {}).get("status") in ("queued", "dry_run", "pending_review"):
            raise ToolRefused("a validate for this idea is already %s" % self.idea["validate"]["status"])
        res = queue_validate_for(self.lab, self.idea, dry_run=self.dry, sandbox=self.sandbox, live_jobs=self.live_jobs,
                                 queue_job=self.queue_job, idea_dir=self.dir)
        self.idea["validate"] = res
        self.event("validate", status=res.get("status"), why=res.get("why"))
        self.close("STAGE A DONE - bar met; validate %s" % res.get("status"))
        return res

    def t_finish(self, note=""):
        self.idea["finish_note"] = str(note or "")[:2000]            # stored, never posted
        if not self.closed and self.idea.get("sanity_open"):
            self._record_broken("the model finished without a fix")
        if not self.closed:
            if self.idea.get("stage_a"):
                self.close("STAGE A DONE - finished without a validate request")
            elif self.idea.get("stage_pre_wf"):
                self.close("PRE-WF DONE - finished")
            else:
                self.close("FINISHED BY THE MODEL before Stage A")
        return {"finished": True}

    def dispatch(self, tool, args):
        fn = getattr(self, "t_" + str(tool), None)
        if fn is None or tool not in {t["name"] for t in TOOLS}:
            return {"error": "unknown tool %r" % tool}
        try:
            sig = inspect.signature(fn)
            args = {k: v for k, v in (args or {}).items() if k in sig.parameters}
            return fn(**args)
        except ToolRefused as e:                     # logged, so a refusal loop is visible in run.log (MANAGER #153a)
            self.lab.log("%s REFUSED: %s" % (tool, str(e)[:240]), self.idea["id"])
            return {"refused": str(e)}
        except LabStopped:
            raise
        except TypeError as e:
            return {"error": "bad arguments for %s: %s" % (tool, e)}
        except Exception as e:                                   # noqa: BLE001
            self.lab.log("tool %s crashed: %s" % (tool, traceback.format_exc()[-1500:]), self.idea["id"])
            return {"error": "%s failed inside the harness: %s: %s" % (tool, type(e).__name__, str(e)[:300])}


def queue_validate_for(lab, idea, *, dry_run, sandbox=run_sandbox, live_jobs=firestore_live_jobs,
                       queue_job=firestore_queue, idea_dir=None):
    """The validate path: one at a time, reviewed-on-main, queue_guard in the sandbox, the lanes' job shape."""
    pr, sa, pl = idea["proposal"], idea["stage_a"], idea["plugin"]
    idea_dir = idea_dir or lab.idea_dir(idea["id"])
    name, sha = pr["name"], pl["sha"]
    met, bar = validate_bar(sa["numbers"], sa.get("peak_gb"))
    if not met:
        return {"status": "refused", "why": bar}
    # one Qwen-lab validate at a time: Firestore (fail closed) + the lab's own record
    try:
        live = [(i, j) for i, j in live_jobs() if _qwen_tagged(j)]
    except Exception as e:                                       # noqa: BLE001
        return {"status": "refused", "why": "could not read the queue (%s) - fail closed" % str(e)[:200]}
    if live:
        return {"status": "refused", "why": "a Qwen-lab validate is already %s (%s) - one at a time"
                % (live[0][1].get("status"), live[0][0])}
    mine = [v for v in lab.state.get("validates", []) if v.get("status") == "queued" and not v.get("dry_run")
            and v.get("job_id") not in {i for i, _ in live}]
    on_main, ref = reviewed_on_main(name, sha)
    if not on_main and not dry_run:
        pend = {"idea": idea["id"], "name": name, "sha": sha, "since": now_s(), "instrument": pr["instrument"],
                "timeframe": pr["timeframe"], "prereg": idea.get("prereg", {}).get("path")}
        lab.state.setdefault("pending_validates", [])
        if not any(p["name"] == name and p["sha"] == sha for p in lab.state["pending_validates"]):
            lab.state["pending_validates"].append(pend)
            lab.save()
        return {"status": "pending_review", "why": "augur_strategies/qwen_lab/%s.py (sha %s) is not on main yet - a "
                "Claude lane must review and ship it; then `python tools/qwen_lab.py queue-pending`" % (name, sha[:12]),
                "note": "%d earlier lab validate(s) recorded as queued" % len(mine)}
    guard_path = on_main or pl["path"]
    strategy_ref = ref or os.path.join(SHARED, "augur_strategies", "qwen_lab", name + ".py")
    pin = MASTERS[(pr["instrument"], pr["timeframe"])]
    cost, mult = idea_costs(idea, pr["instrument"])
    g = sandbox("guard", guard_path, sha, dict(instrument=pr["instrument"], timeframe=pr["timeframe"],
                                               source=pin["source"], session=pin["session"],
                                               master_filename=pin["filename"], cost_pts=cost, mult=mult,
                                               date_from=VALIDATE_FROM, date_to=VALIDATE_TO, split=split_date(),
                                               name=name, mem_gb=SANDBOX_MEM_GB), idea_dir, label="queue_guard")
    if not g.get("ok"):
        return {"status": "refused", "why": "queue_guard did not run: %s" % str(g.get("error"))[:300]}
    if g.get("verdict") == "ARTIFACT":
        return {"status": "refused", "why": "queue_guard verdict ARTIFACT: %s" % "; ".join(g.get("reasons") or [])[:400]}
    job = build_validate_job(name, strategy_ref, pr["instrument"], pr["timeframe"], sha,
                             idea.get("prereg", {}).get("path"), cost=cost, mult=mult,
                             first_signal_bar=(pr.get("first_signal_bar") or {}).get("label"))
    jdump(os.path.join(idea_dir, "validate_job.json"), job)
    if dry_run:
        rec = {"idea": idea["id"], "name": name, "status": "dry_run", "dry_run": True, "at": now_s(),
               "guard": g.get("verdict"), "strategy_ref": strategy_ref, "on_main": bool(on_main)}
        lab.state.setdefault("validates", []).append(rec)
        lab.save()
        return {"status": "dry_run", "why": "DRY RUN - job built and logged (validate_job.json), nothing written to "
                "Firestore; queue_guard %s%s" % (g.get("verdict"), "" if on_main else
                                                  "; file not on main yet (a real run would wait for review)"),
                "job_preview": {k: job[k] for k in ("strategy", "instrument", "timeframe", "source", "date_from",
                                                     "date_to", "lockbox_months", "n_trials", "cost_pts", "mult")}}
    jid = queue_job(job)
    rec = {"idea": idea["id"], "name": name, "status": "queued", "job_id": jid, "at": now_s(),
           "guard": g.get("verdict"), "strategy_ref": strategy_ref}
    lab.state.setdefault("validates", []).append(rec)
    lab.state["pending_validates"] = [p for p in lab.state.get("pending_validates", []) if p["name"] != name]
    lab.save()
    return {"status": "queued", "job_id": jid, "why": "queued 900-trial Auto-Validate; queue_guard %s" % g.get("verdict")}


# ------------------------------------------------------------------------------------------------ the loop
def pick_idea(lab, idea_n=None):
    if idea_n is None:
        papers = open_shelf_papers(lab)
        return papers[0] if papers else None
    mclosed = lab.shelf_closed_by_manager()
    if int(idea_n) in mclosed:
        raise SystemExit("shelf #%s was CLOSED by MANAGER (`shelf-close`, %s) - `shelf-open %s` re-opens it"
                         % (idea_n, mclosed[int(idea_n)], idea_n))
    if int(idea_n) not in lab.open_shelf_numbers() and str(int(idea_n)) in lab.state.get("closed_shelf", {}):
        c = lab.state["closed_shelf"][str(int(idea_n))]
        raise SystemExit("shelf #%s is CLOSED for the lab (%s, idea %s) - MANAGER reopens it with `shelf-open %s`"
                         % (idea_n, c.get("why"), c.get("idea"), idea_n))
    ideas = shelf_ideas(lab.state.get("skip_shelf", []), include_taken=True)
    hit = [p for p in ideas if int(p["n"]) == int(idea_n)]
    if not hit:
        raise SystemExit("shelf #%s not found" % idea_n)
    if hit[0].get("excluded") and int(idea_n) not in lab.open_shelf_numbers():
        raise SystemExit("shelf #%s is excluded: %s (MANAGER opens it with `shelf-open %s`)"
                         % (idea_n, hit[0]["excluded"], idea_n))
    return {k: v for k, v in hit[0].items() if k != "excluded"}


def compute_next_pick(lab, source=None):
    """The next idea source in the rotation (MANAGER #133): scalper -> own -> shelf; the shelf slot is skipped while no
    paper is open (MANAGER #142: then the rotation is scalper -> own -> scalper -> own). `source` forces one."""
    order = list(SOURCE_ORDER)
    i0 = int(lab.state.get("rotation_index", 0)) % len(order)
    cands = [source] if source else [order[(i0 + k) % len(order)] for k in range(len(order))]
    for src in cands:
        if src not in SOURCE_LABEL:
            raise SystemExit("unknown idea source %r (one of %s)" % (src, ", ".join(order)))
        if src == "shelf":
            papers = open_shelf_papers(lab)
            if not papers:
                if source:
                    raise SystemExit("no shelf paper is open for the lab - MANAGER opens one with `shelf-open N`")
                continue
            p = papers[0]
            return {"source": "shelf", "shelf": p, "label": "reading shelf #%s %s (%s %s)" % (
                p["n"], p["title"], (p.get("authors") or "").split(",")[0], p.get("year"))}
        return {"source": src, "label": SOURCE_LABEL[src]}
    return None


def compose_pick_post(lab, pick):
    open_ = ["#%s" % p["n"] for p in open_shelf_papers(lab)]
    extra = " Stage A cost for this short-hold source: NQ 0.783 / ES 0.613 pt (the 10-12 scalp hunt's basis)." \
        if pick["source"] == "scalper" else ""
    return ("%s next pick: %s. Rotation (MANAGER #133/#142): the owner's scalper ask -> Qwen's own idea -> a shelf "
            "paper MANAGER opened (`shelf-open N`); open shelf papers now: %s%s.%s One session: propose -> safety / "
            "contract / look-ahead gates -> dead list -> map (recorded) -> prereg to MANAGER -> PRE-WF Stage A "
            "(broken-plugin check first) -> WF Stage A only if promoted. Harness-written. Replies -> %s."
            % (TAG, pick["label"], ", ".join(open_) or "none",
               "" if open_ else " (the shelf slot is skipped: scalper and own ideas alternate)", extra, REPLY_TO))


def record_pick(lab, pick, poster=None, post=True):
    """Record the pick in state.json (and post it to MANAGER) - it is what the next `run` will test."""
    if pick is None:
        return None
    pick = dict(pick, at=now_s())
    if post:
        try:
            pick["posted_id"] = (poster or post_manager)(compose_pick_post(lab, pick))
        except Exception as e:                                   # noqa: BLE001
            pick["post_error"] = str(e)[:200]
    lab.state["next_pick"] = pick
    lab.state.setdefault("picks", []).append({k: v for k, v in pick.items() if k != "shelf"} |
                                             ({"shelf_n": pick["shelf"]["n"]} if pick.get("shelf") else {}))
    lab.save()
    lab.log("next pick recorded: %s%s" % (pick["label"], (" (MANAGER #%s)" % pick["posted_id"])
                                         if pick.get("posted_id") else ""))
    return pick


def pick_still_open(lab, pick):
    """A recorded shelf pick whose paper was closed since (MANAGER `shelf-close`, or the lab's own close) is stale - the
    latest shelf_open.txt line is authoritative (MANAGER #147). Other sources never go stale."""
    if not pick or pick.get("source") != "shelf":
        return True
    try:
        return int((pick.get("shelf") or {}).get("n")) in lab.open_shelf_numbers()
    except (TypeError, ValueError):
        return False


def consume_pick(lab, pick):
    """Start an idea from a pick: the rotation moves past its source."""
    order = list(SOURCE_ORDER)
    lab.state["rotation_index"] = (order.index(pick["source"]) + 1) % len(order)
    lab.state["next_pick"] = None
    tag = "shelf%02d" % int(pick["shelf"]["n"]) if pick["source"] == "shelf" else pick["source"]
    idea_id = "%s-%s" % (_dt.datetime.now().strftime("%Y%m%d-%H%M"), tag)
    idea = {"id": idea_id, "source": pick["source"], "created": now_s(), "pick": {k: v for k, v in pick.items()
                                                                                  if k != "shelf"}}
    if pick["source"] == "shelf":
        idea.update(shelf=pick["shelf"], shelf_n=int(pick["shelf"]["n"]))
    lab.state["current_idea"] = idea_id
    lab.save()
    return idea


HARNESS_UPDATE_NOTE = ("MANAGER #134: the power-first map is recorded and posted but no longer stops an idea. "
                       "run_stage_a runs a PRE-WF Stage A (%s..%s, file defaults) on every idea that passes the hard "
                       "gates, and the WF Stage A only if %s. MANAGER #139: a "
                       "plugin that barely trades on the PRE-WF window comes back to you to fix before any verdict. "
                       "MANAGER #142: GAMMA (gamma exposure / GEX / dealer gamma) is closed. Fix round 2 (MANAGER "
                       "#148, TTM #144/#145): propose() refuses an idea the lab already ran (same name, mechanism "
                       "family or a near copy - ideas() lists them); a NEW proposal needs first_signal_bar {index, "
                       "clock}, checked on the contract smoke and every PRE-WF entry; name bars 'bar k (HH:MM open)' "
                       "and say open or close fill; the look-ahead audit now also pushes the first bar at risk's "
                       "high / low (a stop / target / size from the entry bar itself fails). Fix round 3: the bar "
                       "index is counted by the clock; first_signal_bar must hold for every knob value the validate "
                       "searches; the entry-bar audit also moves that bar's close / volume and covers stop / limit "
                       "entries and knob corners; a plugin gated by the older gates must be re-gated (write_plugin), "
                       "and a proposal WITHOUT first_signal_bar must call propose again with it (a proposal the map or "
                       "a prereg froze keeps everything else and only records the bar) before run_stage_a. Fix round 3 "
                       "(MANAGER #153-#162): plugins get REAL dates (declare index=None; augur_engine.session_calendar "
                       "helpers such as is_last_n_sessions_of_month(index, n, day_id)); a proposal also states "
                       "entry_fill {at: open|close|level, bar: k or -1} and time_stop_bars N (exit at the CLOSE of entry "
                       "bar + N; 0 = none), both checked on the contract smoke, and the smoke trade rate must be within "
                       "3x of the stated rate; a plugin identical to one already run is refused and never counts as a "
                       "fix retry; one-episode is NOT TESTABLE on a single drawdown episode; the look-ahead audit runs "
                       "every phase at the knob corners and checks exits booked at a bar's open. Continue from where "
                       "you were." % (PREWF0, PREWF1, PROMOTION_RULE))


def run_idea(lab, idea, chat, *, dry_run_validate=False, max_steps=MAX_STEPS, beacon=None, session_kw=None):
    """Drive one idea to a terminal state. Resumable: messages are saved after every step."""
    sess = IdeaSession(lab, idea, dry_run_validate=dry_run_validate, **(session_kw or {}))
    tpath = os.path.join(sess.dir, "transcript.json")
    tr = jload(tpath, None) or {"messages": [{"role": "system", "content": system_prompt()},
                                             {"role": "user", "content": idea_prompt(
                                                 idea, max_steps, MAX_PLUGIN_ATTEMPTS,
                                                 ran=ran_ideas(lab, exclude=idea.get("id")))}],
                                "calls": []}
    msgs = tr["messages"]
    harness_now = lf_sha256_file(HARNESS_PATH)
    if idea.get("harness_sha") != harness_now and len(msgs) > 2:     # resumed (an idea from before the sha was kept counts)
        msgs[0] = {"role": "system", "content": system_prompt()}         # the current rules
        msgs.append({"role": "user", "content": "RESUMED after a harness update. " + HARNESS_UPDATE_NOTE
                     + ("" if idea.get("proposal") else ran_ideas_block(ran_ideas(lab, exclude=idea.get("id"))))})
        lab.log("resumed under a new harness (%s -> %s)" % ((idea.get("harness_sha") or "unrecorded")[:12],
                                                           harness_now[:12]), idea["id"])
    idea["harness_sha"] = harness_now
    t_start = time.time()
    nudges = 0
    mode = idea.setdefault("protocol", {"native_tool_calls": 0, "json_fallback": 0, "no_action": 0})
    waiter = (session_kw or {}).get("courtesy") or courtesy_wait

    def _end(why):
        if idea.get("sanity_open"):
            sess._record_broken(why + " before a fix")
        else:
            sess.close(why)
    while not sess.closed:
        if lab.stop_requested():
            lab.log("STOP file found - saving and leaving the idea open for resume", idea["id"])
            return "stopped"
        step = int(idea.get("steps", 0))
        budget = max_steps + int(idea.get("bonus_steps", 0))
        if step >= budget:
            _end("STEP BUDGET USED (%d model turns)" % budget)
            break
        if time.time() - t_start > IDEA_WALL_S:
            _end("WALL-TIME BUDGET USED")
            break
        if not waiter(lab, "Qwen generation", idea["id"]):              # MANAGER #143: a STOP during the wait
            lab.log("STOP file found - saving and leaving the idea open for resume", idea["id"])
            return "stopped"
        idea["steps"] = step + 1
        sess.save()
        try:
            msg, stats = chat.chat(compact_messages(msgs), TOOLS)
        except Exception as e:                                   # noqa: BLE001
            lab.log("model call failed: %s" % e, idea["id"])
            idea["steps"] = step                                 # the step did not happen
            sess.save()
            return "model_error"
        tr["calls"].append(dict(step=step + 1, at=now_s(), **stats))
        if beacon is not None:
            try:
                beacon.step(step + 1, max_steps)
            except Exception:
                pass
        clean = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            clean["tool_calls"] = msg["tool_calls"]
        msgs.append(clean)
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            calls.append((fn.get("name"), args, "native"))
        if not calls:
            act = parse_json_action(msg.get("content"))
            if act:
                calls.append((act[0], act[1], "json"))
        if not calls:
            mode["no_action"] += 1
            nudges += 1
            if nudges > 2:
                cut = stats.get("done_reason") == "length"
                _end("NO ACTION: the model's reply was cut off at the context limit (prompt %s + reply %s tokens, "
                     "num_ctx %s)" % (stats.get("prompt_tokens"), stats.get("eval_tokens"), getattr(chat, "num_ctx", "?"))
                     if cut else "NO ACTION: the model stopped calling tools")
                break
            msgs.append({"role": "user", "content": "Call one of the tools (or finish). If native tool calls do not "
                                                    "work, reply with only {\"tool\": ..., \"arguments\": {...}}."})
        # the look budget: before a proposal, at most MAX_LOOK_TURNS turns of pure reading (2026-10-15: the first
        # live run spent 9 turns on one-word dead_list searches and never proposed)
        looking = bool(calls) and not idea.get("proposal") and all(c[0] in LOOK_TOOLS for c in calls)
        if looking:
            idea["look_turns"] = int(idea.get("look_turns", 0)) + 1
        for name, args, how in calls:
            mode["native_tool_calls" if how == "native" else "json_fallback"] += 1
            lab.log("step %d: %s %s (%s)" % (step + 1, name, json.dumps({k: (v if k != "code" else "<%d chars>"
                                                                                 % len(str(v)))
                                                                             for k, v in args.items()},
                                                                            default=str)[:300], how), idea["id"])
            if looking and idea["look_turns"] > MAX_LOOK_TURNS:
                result = {"refused": "reading budget used (%d turns of reading before a proposal) - call propose "
                                     "now; the harness checks your proposal against the dead list itself"
                                     % MAX_LOOK_TURNS}
            else:
                try:
                    result = sess.dispatch(name, args)
                except LabStopped:
                    msgs.append({"role": "tool", "tool_name": name, "content": json.dumps(
                        {"paused": "the harness was stopped while it waited for the machine's push lock - nothing ran; "
                                   "call %s again" % name})})
                    jdump(tpath, tr)
                    sess.save()
                    lab.log("STOP during the load-courtesy wait - the idea stays open for resume", idea["id"])
                    return "stopped"
            n_cap = TOOL_RESULT_CHARS
            if isinstance(result, dict):
                n_cap = int(result.pop("_cap", TOOL_RESULT_CHARS))
                result = dict(result, steps_left=max(0, max_steps + int(idea.get("bonus_steps", 0))
                                                     - int(idea.get("steps", 0))))
            body = cap(json.dumps(result, default=str), n_cap)
            if how == "native":
                msgs.append({"role": "tool", "tool_name": name, "content": body})
            else:
                msgs.append({"role": "user", "content": "TOOL RESULT (%s): %s" % (name, body)})
            if sess.closed:
                break
        jdump(tpath, tr)
        sess.save()
    jdump(tpath, tr)
    return "closed"


def close_duplicate(lab, idea, dup, poster=None):
    """MANAGER #158/#162: a resumed open idea that repeats a run idea (the same plugin sha, rule or name) closes 'CLOSED
    AS DUPLICATE of <id> (<why>)' WITHOUT a run - recorded in state.json aborted_ideas, never in done_ideas - and the
    lab picks a fresh idea. One harness-written line to MANAGER (a failed post is logged, not fatal)."""
    outcome = "CLOSED AS DUPLICATE of %s (%s)" % (dup["of"], dup["why"])
    if idea.get("status") != "closed":
        idea.update(status="closed", outcome=outcome, closed_at=now_s(), duplicate_of=dict(dup, at=now_s()))
        idea.setdefault("events", []).append({"at": now_s(), "event": "closed_as_duplicate", **dup})
        jdump(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)
    _record_aborted(lab, idea, duplicate_of=dup["of"])
    lab.log("idea %s %s - not run; recorded in aborted_ideas, not done_ideas (MANAGER #158/#162)"
            % (idea["id"], idea.get("outcome")), idea["id"])
    if poster is not None and not idea.get("duplicate_post"):
        name = _safe_name((idea.get("proposal") or {}).get("name") or idea["id"])
        text = ("%s: %s (%s) - %s%s: NOT run (no Stage A, no verdict); recorded as aborted, never as a done idea "
                "(MANAGER #158/#162: the same plugin or rule never runs twice). The lab picks a fresh idea. Replies -> %s."
                % (TAG, name, source_ref(idea), idea.get("outcome"),
                   (", plugin LF sha256 %s" % dup["sha"][:16]) if dup.get("sha") else "", REPLY_TO))
        try:
            idea["duplicate_post"] = {"inbox_id": poster(text), "at": now_s()}
        except Exception as e:                                   # noqa: BLE001
            idea["duplicate_post"] = {"error": str(e)[:300], "text": text}
            lab.log("duplicate post FAILED: %s" % e, idea["id"])
        jdump(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)


def _record_aborted(lab, idea, **extra):
    """The aborted_ideas row of a closed idea that was no run (once); current_idea cleared."""
    ab = lab.state.setdefault("aborted_ideas", [])
    if not any((d or {}).get("id") == idea["id"] for d in ab):
        ab.append(dict({"id": idea["id"], "shelf_n": idea.get("shelf_n"), "source": idea.get("source", "shelf"),
                        "outcome": idea.get("outcome"), "at": now_s()}, **extra))
    if lab.state.get("current_idea") == idea["id"]:
        lab.state["current_idea"] = None
    lab.save()


def record_done(lab, idea, poster):
    """A closed idea's bookkeeping: the result post (unless the idea already posted it inline or tried before), the
    done_ideas row (once), current_idea cleared. Also the recovery path for an idea that closed in a run killed before
    this ran. A duplicate (MANAGER #158/#162) goes to aborted_ideas instead - never a done idea."""
    if _DUPLICATE_RX.match(str(idea.get("outcome") or "")):
        _record_aborted(lab, idea, duplicate_of=(idea.get("duplicate_of") or {}).get("of"))
        return
    if not idea.get("result_posted_inline") and not idea.get("result_post"):   # a not-promoted idea's PRE-WF post IS
        text = compose_result_post(idea)                                       # its result
        try:
            pid = poster(text)
            idea["result_post"] = {"inbox_id": pid, "text": text, "at": now_s()}
        except Exception as e:                                   # noqa: BLE001
            idea["result_post"] = {"error": str(e)[:300], "text": text}
            lab.log("result post FAILED: %s" % e, idea["id"])
    jdump(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)
    done = lab.state.setdefault("done_ideas", [])
    if not any((d or {}).get("id") == idea["id"] for d in done):
        done.append({"id": idea["id"], "shelf_n": idea.get("shelf_n"), "source": idea.get("source", "shelf"),
                     "outcome": idea.get("outcome"),
                     "pre_wf": fmt_four((idea.get("stage_pre_wf") or {}).get("numbers")),
                     "four": fmt_four((idea.get("stage_a") or {}).get("numbers")),
                     **({"retries": retries_text(idea)} if idea.get("stage_pre_wf") else {})})
    if lab.state.get("current_idea") == idea["id"]:
        lab.state["current_idea"] = None
    lab.save()
    lab.log("idea %s done: %s" % (idea["id"], idea.get("outcome")))


def run(args, chat=None, session_kw=None):
    lab = Lab(home=args.home, plugin_repo=args.plugin_repo)
    check_plugin_repo(lab.plugin_repo)
    # one runner at a time
    try:
        import psutil
        old = jload(lab.lock_path, None)
        if old and psutil.pid_exists(int(old.get("pid", -1))) and int(old["pid"]) != os.getpid():
            raise SystemExit("REFUSED: another qwen_lab run is alive (pid %s) - `stop` it first" % old["pid"])
    except ImportError:
        pass
    jdump(lab.lock_path, {"pid": os.getpid(), "since": now_s()})
    if os.path.exists(lab.stop_path):
        os.remove(lab.stop_path)
    chat = chat or OllamaChat(think=args.think)
    try:
        if hasattr(chat, "ping"):
            try:
                lab.log("Ollama %s, model %s" % (chat.ping(), getattr(chat, "model", "?")))
            except Exception as e:                               # noqa: BLE001
                lab.log("Ollama is not reachable (%s) - nothing run; start Ollama and `run` again" % e)
                return 2
        while True:
            cur = lab.state.get("current_idea")
            if cur:
                idea = jload(os.path.join(lab.idea_dir(cur), "idea.json"), None)
                if idea is not None and idea.get("status") == "closed" and not any(
                        (d or {}).get("id") == cur for d in list(lab.state.get("done_ideas") or [])
                        + list(lab.state.get("aborted_ideas") or [])):
                    # the idea CLOSED but the run died before its bookkeeping (result post, done row): finish it now,
                    # so ran_ideas / the dedupe still see it (a duplicate goes to aborted_ideas)
                    lab.log("idea %s closed without its done row (the run was killed) - recording it now" % cur)
                    record_done(lab, idea, (session_kw or {}).get("poster") or post_manager)
                    continue
                if idea is None or idea.get("status") == "closed":
                    lab.state["current_idea"] = None
                    lab.save()
                    continue
                # MANAGER #158/#162: an open idea that repeats a run idea (its plugin sha, its rule, its name) is closed
                # as a duplicate WITHOUT a run - before any model turn - and the lab picks a fresh idea
                dup = resume_duplicate(lab, idea)
                if dup:
                    close_duplicate(lab, idea, dup, (session_kw or {}).get("poster") or post_manager)
                    continue
                lab.log("resuming idea %s" % cur)
            else:
                poster0 = (session_kw or {}).get("poster") or post_manager
                if args.idea is not None:
                    sh = pick_idea(lab, args.idea)
                    pick = record_pick(lab, {"source": "shelf", "shelf": sh, "label": "reading shelf #%s %s (%s %s)"
                                             % (sh["n"], sh["title"], (sh.get("authors") or "").split(",")[0],
                                                sh.get("year"))}, poster0)
                elif getattr(args, "source", None):
                    pick = record_pick(lab, compute_next_pick(lab, args.source), poster0)
                else:
                    pick = lab.state.get("next_pick")
                    if pick is not None and not pick_still_open(lab, pick):        # MANAGER #147
                        lab.log("the recorded pick (%s) was closed since it was posted - picking again"
                                % pick.get("label"))
                        lab.state["next_pick"] = None
                        lab.save()
                        pick = None
                    pick = pick or record_pick(lab, compute_next_pick(lab), poster0)
                if pick is None:
                    lab.log("no idea source has anything left")
                    return 0
                idea = consume_pick(lab, pick)
                jdump(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)
                lab.log("new idea %s: %s" % (idea["id"], pick["label"]))
            bc = None
            if not args.no_beacon:
                try:
                    sys.path.insert(0, HERE)
                    from research_beacon import beacon
                    bc = beacon("QWEN LAB %s" % idea["id"], total=args.max_steps,
                                note="QWEN LAB: the local model tests one reading-shelf idea (tools/qwen_lab.py)").start()
                except Exception:
                    bc = None
            t0 = time.time()
            try:
                how = run_idea(lab, idea, chat, dry_run_validate=args.dry_run_validate, max_steps=args.max_steps,
                               beacon=bc, session_kw=session_kw)
            finally:
                if bc is not None:
                    bc.finish("done")
            idea = jload(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)
            idea["wall_secs"] = round(float(idea.get("wall_secs", 0)) + time.time() - t0, 1)
            jdump(os.path.join(lab.idea_dir(idea["id"]), "idea.json"), idea)
            if how in ("stopped", "model_error"):
                lab.log("idea %s left open (%s) - `run` resumes it" % (idea["id"], how))
                return 2 if how == "model_error" else 0
            record_done(lab, idea, (session_kw or {}).get("poster") or post_manager)
            if not args.no_next_pick:
                record_pick(lab, compute_next_pick(lab), (session_kw or {}).get("poster") or post_manager)
            if args.once or args.idea is not None or getattr(args, "source", None):
                return 0
    finally:
        try:
            if (jload(lab.lock_path, {}) or {}).get("pid") == os.getpid():
                os.remove(lab.lock_path)
        except OSError:
            pass


def queue_pending(args):
    lab = Lab(home=args.home, plugin_repo=args.plugin_repo)
    out = []
    for p in list(lab.state.get("pending_validates", [])):
        idea = jload(os.path.join(lab.idea_dir(p["idea"]), "idea.json"), None)
        if not idea:
            continue
        on_main, _ = reviewed_on_main(p["name"], p["sha"])
        if not on_main:
            out.append("%s: still not on main with sha %s" % (p["name"], p["sha"][:12]))
            continue
        res = queue_validate_for(lab, idea, dry_run=args.dry_run_validate)
        idea["validate"] = res
        jdump(os.path.join(lab.idea_dir(p["idea"]), "idea.json"), idea)
        out.append("%s: %s - %s" % (p["name"], res.get("status"), res.get("why")))
        if res.get("status") == "queued":
            try:
                post_manager("%s: %s - Auto-Validate queued (job %s) after lane review; prereg %s. Replies -> %s."
                             % (TAG, p["name"], res.get("job_id"), p.get("prereg"), REPLY_TO))
            except Exception as e:                               # noqa: BLE001
                out.append("post failed: %s" % e)
            break                                                # one at a time
    print("\n".join(out) or "no pending validates")
    return 0


def status(args):
    lab = Lab(home=args.home, plugin_repo=args.plugin_repo)
    s = lab.state
    print("QWEN LAB home %s | plugins -> %s" % (lab.home, lab.plugin_dir))
    print("current idea: %s | STOP file: %s" % (s.get("current_idea"), os.path.exists(lab.stop_path)))
    print("next pick: %s | rotation index %s of %s" % ((s.get("next_pick") or {}).get("label"),
                                                      s.get("rotation_index"), list(SOURCE_ORDER)))
    for d in s.get("done_ideas", [])[-10:]:
        print("  done %s (%s): %s | PRE-WF %s%s | WF %s" % (
            d["id"], d.get("source") or "shelf #%s" % d.get("shelf_n"), d.get("outcome"), d.get("pre_wf", "-"),
            (" | " + d["retries"]) if d.get("retries") else "", d.get("four")))
    for d in [x for x in s.get("aborted_ideas", []) if _DUPLICATE_RX.match(str(x.get("outcome") or ""))][-5:]:
        print("  duplicate (not run) %s: %s" % (d["id"], d.get("outcome")))
    for u in s.get("shelf_closures_undone", [])[-5:]:
        print("  shelf #%s closure undone (MANAGER #153b): %s" % (u.get("n"), u.get("undone_why")))
    for v in s.get("validates", [])[-5:]:
        print("  validate %s %s %s" % (v.get("name"), v.get("status"), v.get("job_id", "")))
    for p in s.get("pending_validates", []):
        print("  PENDING REVIEW %s sha %s since %s" % (p["name"], p["sha"][:12], p["since"]))
    print("skip list: %s" % s.get("skip_shelf"))
    print("closed shelf by the lab (a Stage A ran; the picker never takes these): %s"
          % sorted(int(k) for k in s.get("closed_shelf", {})))
    mc = lab.shelf_closed_by_manager()
    print("closed shelf by MANAGER (shelf-close; latest line wins): %s"
          % (", ".join("#%d (%s)" % (n, at) for n, at in sorted(mc.items())) or "none"))
    print("open shelf (MANAGER shelf-open): %s" % (lab.open_shelf_numbers() or "none - the shelf slot is skipped"))
    for w in lab.shelf_warnings:
        print("  WARNING %s" % w)
    ran = ran_ideas(lab)
    fams = families_taken(ran)
    retry = [r["name"] for r in ran if r.get("retry_ok")]
    print("ideas already run (refused at propose - MANAGER #148): %d names; families taken: %s%s"
          % (len(ran), ", ".join(fams) or "none",
             ("; no verdict (a new name may retry the mechanism): %s" % ", ".join(retry)) if retry else ""))
    held, who = push_lock_state()
    print("push lock: %s" % (("HELD by %s - new generations / Stage A wait" % who) if held else "free"))
    for w in s.get("courtesy_waits", [])[-5:]:
        print("  courtesy wait %s: %s s before a %s (%s)" % (w["at"], w["secs"], w["what"], w.get("holder")))
    return 0


def _append_shelf_line(path, line):
    """Append one line to shelf_open.txt; a hand-edited file without a final newline gets one first (else the new line
    would run into the last one)."""
    lead = ""
    try:
        if os.path.getsize(path) > 0:
            with open(path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                lead = "" if f.read(1) == b"\n" else "\n"
    except OSError:
        pass
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(lead + line.rstrip("\n") + "\n")


def shelf_open(args):
    """MANAGER opens shelf papers for the lab: one line appended to <home>\\shelf_open.txt (the running lab reads it at
    its next pick; no state.json race)."""
    lab = Lab(home=args.home, plugin_repo=args.plugin_repo)
    nums = sorted(set(int(x) for x in args.numbers))
    try:
        known = {int(p["n"]): p for p in shelf_ideas((), include_taken=True)}
    except OSError:
        known = {}
    _append_shelf_line(lab.shelf_open_path, "%s %s" % (now_s(), " ".join(str(n) for n in nums)))
    for n in nums:
        p = known.get(n)
        note = "" if p else "  (NOT on the reading shelf yet - skipped until it is)"
        if p and p.get("excluded"):
            note = "  (was excluded: %s - an explicit open overrides that)" % p["excluded"]
        if str(n) in lab.state.get("closed_shelf", {}):
            note += "  (re-opened after the lab closed it)"
        print("shelf #%s opened for the lab%s%s" % (n, (": " + p["title"]) if p else "", note))
    print("open now: %s" % lab.open_shelf_numbers())
    for w in lab.shelf_warnings:
        print("WARNING %s" % w)
    return 0


def shelf_close(args):
    """MANAGER closes shelf papers for the lab (MANAGER #147): one dated CLOSE line appended to <home>\\shelf_open.txt -
    the latest open / close line per paper wins, so MANAGER never hand-edits the file. Never touches state.json (the
    lab's own closures stay there); `shelf-open N` re-opens a paper."""
    lab = Lab(home=args.home, plugin_repo=args.plugin_repo)
    nums = sorted(set(int(x) for x in args.numbers))
    was_open = set(lab.open_shelf_numbers())
    why = re.sub(r"[#\r\n]+", " ", str(getattr(args, "why", None) or "")).strip()[:300]
    _append_shelf_line(lab.shelf_open_path, "%s CLOSE %s%s" % (now_s(), " ".join(str(n) for n in nums),
                                                               ("  # " + why) if why else ""))
    for n in nums:
        print("shelf #%s CLOSED for the lab%s" % (n, "" if n in was_open else " (it was not open)"))
    print("open now: %s" % (lab.open_shelf_numbers() or "none - the shelf slot is skipped"))
    for w in lab.shelf_warnings:
        print("WARNING %s" % w)
    return 0


def launch(argv):
    """Start `run` detached: no console of this shell, so closing the session does not orphan a console child."""
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(w):
        exe = w
    flags = 0x00000008 | 0x00000200 | 0x08000000 if os.name == "nt" else 0   # DETACHED | NEW_GROUP | NO_WINDOW
    os.makedirs(LAB_HOME, exist_ok=True)
    out = open(os.path.join(LAB_HOME, "launch.log"), "a", encoding="utf-8")
    p = subprocess.Popen([exe, HARNESS_PATH, "run"] + argv, cwd=LAB_REPO, stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)
    print("launched pid %d - follow %s; stop with `python tools/qwen_lab.py stop`" % (
        p.pid, os.path.join(LAB_HOME, "run.log")))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_sandbox"]:
        return sandbox_main(argv[1], argv[2])
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("run", "launch"):
        r = sub.add_parser(c)
        r.add_argument("--once", action="store_true", help="one idea, then exit")
        r.add_argument("--idea", type=int, help="the reading-shelf number to test (implies --once)")
        r.add_argument("--source", choices=SOURCE_ORDER, help="force one idea source (implies --once)")
        r.add_argument("--no-next-pick", action="store_true", help="do not record / post the following pick")
        r.add_argument("--dry-run-validate", action="store_true", help="build + log the validate job, write nothing")
        r.add_argument("--max-steps", type=int, default=MAX_STEPS)
        r.add_argument("--think", action="store_true", help="let qwen think (slower; off by default)")
        r.add_argument("--no-beacon", action="store_true", help="do not show the run on the top-bar dials")
        r.add_argument("--home", default=None)
        r.add_argument("--plugin-repo", default=None)
    np_ = sub.add_parser("next-pick", help="record the next idea pick in state.json and post it to MANAGER")
    np_.add_argument("--home", default=None)
    np_.add_argument("--plugin-repo", default=None)
    np_.add_argument("--source", choices=SOURCE_ORDER)
    np_.add_argument("--no-post", action="store_true")
    so = sub.add_parser("shelf-open", help="open reading-shelf papers for the lab (MANAGER posts the numbers)")
    so.add_argument("numbers", nargs="+", type=int)
    so.add_argument("--home", default=None)
    so.add_argument("--plugin-repo", default=None)
    sc = sub.add_parser("shelf-close", help="close reading-shelf papers for the lab (the latest open/close line wins)")
    sc.add_argument("numbers", nargs="+", type=int)
    sc.add_argument("--why", default=None, help="a short reason, stored as a comment on the CLOSE line")
    sc.add_argument("--home", default=None)
    sc.add_argument("--plugin-repo", default=None)
    for c in ("stop", "status", "queue-pending"):
        r = sub.add_parser(c)
        r.add_argument("--home", default=None)
        r.add_argument("--plugin-repo", default=None)
        if c == "queue-pending":
            r.add_argument("--dry-run-validate", action="store_true")
    a = ap.parse_args(argv)
    if getattr(a, "home", None):
        global LAB_HOME
        LAB_HOME = a.home
    if a.cmd == "run":
        return run(a)
    if a.cmd == "launch":
        return launch([x for x in argv[1:]])
    if a.cmd == "stop":
        lab = Lab(home=a.home, plugin_repo=a.plugin_repo)
        with open(lab.stop_path, "w", encoding="utf-8") as f:
            f.write(now_s())
        print("STOP written - the loop saves and exits at its next step; `run` resumes the open idea")
        return 0
    if a.cmd == "status":
        return status(a)
    if a.cmd == "next-pick":
        lab = Lab(home=a.home, plugin_repo=a.plugin_repo)
        pick = record_pick(lab, compute_next_pick(lab, a.source), post=not a.no_post)
        print("next pick: %s" % (pick["label"] if pick else "nothing left"))
        if pick and pick.get("posted_id"):
            print("posted to MANAGER #%s" % pick["posted_id"])
        return 0
    if a.cmd == "queue-pending":
        return queue_pending(a)
    if a.cmd == "shelf-open":
        return shelf_open(a)
    if a.cmd == "shelf-close":
        return shelf_close(a)
    return 1


if __name__ == "__main__":
    sys.exit(main())
