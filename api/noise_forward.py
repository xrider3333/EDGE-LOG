"""api/noise_forward.py -- the NOISE FORWARD LOG, decision-time half (Custom ML's pre-registered
forward test, docs/PREREG_noise_shadow_forward_2026-09-28.md).

WHAT IT IS. All five NOISE sizing arms trade ONE signal stream (#382 and #422 are both run
#304 re-sized), so the test is scored as the primary's REAL per-share fill P&L x each arm's
size multiplier. This module writes ONE row per NOISE signal -- filled or not -- with what was
known when it was decided: the signal (id, decision time, side, the signal bar), the four
flags every arm sizes on, read at the decision bar exactly as each strategy / KEEL reads them,
every arm's UNCAPPED multiplier, the per-arm share count the book would send, and both learned
KEEL states' metadata. The fill half (Webull fills, exit reason, capped / refused / skipped)
lives in api/qqq_exec.py's ledgers; tools/noise_forward_log.py joins the two by trade id into
the table Custom ML reads.

  A1 m_382plain  2.0 while #382's 30-minute squeeze (16 / 1.15) is on, else 1.0
  A2 m_422plain  1.75 while #422's hourly squeeze (20 / 1.15) is on, else 1.0
  A3 m_422fixed  m_422plain x ml_keel.fixed_tilt_sizes_v12 (compression 1.5 x Friday 1.5,
                 capped 3.0, x 0.5 before a 14:00 ET FOMC statement) -- the NOISE_422_FIXED leg
  P  m_382keel   the primary's own size (NOISE_382: #382 plain x KEEL v12), from its ENTRY row
  A4 m_422keel   the NOISE_422_KEEL shadow leg's own size (#422 plain x KEEL v12, seed 42)

WHERE. <home>/cloud_signal/shadow/noise_forward_log.csv -- the SHADOW store (api/qqq_exec.py
never reads that folder), append-only, one header; every row carries LOG_VERSION.

WHO WRITES IT. api/cloud_signal.run_shadow_step, through forward_log_tick, after the shadow
step on each fetch tick. By then the live step has written the primary's ENTRY row and the
shadow step the three #422 legs' rows for the same bar, so the tick reads both ledgers (the
live one READ-ONLY) and writes a row for every NOISE entry not yet logged. A primary entry
waits up to MATCH_GRACE_SEC for its three shadow rows, then is written with whatever is
missing named in mult_check. A shadow entry with no primary entry at the same bar and side
is its own row (row_type "shadow_only") -- the primary never traded it.

THE FLAGS ARE THE LEGS' OWN. Rebuilt from the same on-disk bars with the same functions the
legs ran: cloud_signal.closed_arrays over the leg's own window, closed through the signal bar
D (the bar before the entry bar), plus the decide-at-close probe's two stand-ins
(cloud_signal._stand_in_arrays) -- exactly the arrays a probe entry was sized on, and for a
compression read at D the same answer an array that really runs past D gives. Then:
  squeezes    the plugin's own _sq._compression at dec = entry_bar - 1 (NOISE_1_8_CT304 /
              NOISE_1_8_CT304H, with the gate each run_backtest resolves)
  sq60_on     ml_keel._squeeze60 at the entry bar < 1.0 (keel_features' sq60_on column)
  Friday      the entry bar's weekday (what v12's dow tilt reads)
  FOMC        ml_keel.pre_statement_mask at the entry bar, v12's cut hour (14:00 ET)
mult_check compares every multiplier computed here with the one the leg actually emitted
("ok", or each difference named). The live step's own arrays are local to step() and are
not reached into: this runs after it, on its own copy, so it adds nothing to the live step.

KEEL FALLBACK IS NAMED. A learned KEEL leg that cannot score (state missing, unreadable or
more than KEEL_MAX_STALE_SESSIONS behind, feature columns that do not match) sizes at exactly
keel_size 1.0 -- which alone looks like a real score. keel382_fallback / keel422_fallback
(keel_fallback) say why a 1.0 was a fallback, blank when the leg scored. A keel_size other
than 1.0 is always a real score; a scoring-time exception (the leg logs it) is the one
fallback this cannot see from outside the leg.

ONE BAD ROW NEVER BLOCKS THE REST. build_rows builds each row on its own: a row that raises
is written ONCE as a stub carrying its signal id with mult_check "row failed: <error>", so it
is neither retried every tick nor in the way of later rows (tools/noise_forward_log.py
--backfill rebuilds it from the ledgers).

NEVER. It never touches the live leg, its state, the live ledger, orders, caps or pushes,
never loads a KEEL state file (a seed comes from the summary or from the state the leg
already loaded in this process), never runs a subprocess on the live thread (engine_commit
reads .git directly), and never raises into the caller: forward_log_tick logs a failure at
most once per ERROR_LOG_EVERY_SEC and returns 0.
"""
import csv
import datetime as _dt
import json
import math
import os
import re
import subprocess
import time as _time

import numpy as np

from api import trade_id as _trade_id

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_VERSION = "nfl_v1"
FORWARD_LOG_FILENAME = "noise_forward_log.csv"
PRIMARY_LEG = "NOISE_382"
PLAIN_LEG = "NOISE_422_PLAIN"
FIXED_LEG = "NOISE_422_FIXED"
KEEL_LEG = "NOISE_422_KEEL"
ARM_LEGS = (PLAIN_LEG, FIXED_LEG, KEEL_LEG)
ARMS = ("382plain", "422plain", "422fixed", "382keel", "422keel")
# the leg whose ENTRY (and EXIT) row each arm trades on -- an arm whose leg has no row for a
# signal took no trade, and tools/noise_forward_log.py scores it no dollars
ARM_LEG = {"382plain": PRIMARY_LEG, "382keel": PRIMARY_LEG, "422plain": PLAIN_LEG,
           "422fixed": FIXED_LEG, "422keel": KEEL_LEG}
MATCH_GRACE_SEC = 600          # how long a primary entry waits for its three shadow rows
LOOKBACK_DAYS = 5              # entries older than this are never picked up late
ERROR_LOG_EVERY_SEC = 600.0
# The book's sizing (api/qqq_exec.py config "shares"/"max_shares_per_leg", webull_orders rails
# "max_shares_per_leg"/"max_total_position_shares"), used only when a config file cannot be
# read.
DEFAULT_BASE_SHARES = 10
DEFAULT_MAX_SHARES_PER_LEG = 60
DEFAULT_MAX_TOTAL_SHARES = 80
KEEL_META = ("version", "seed", "data_through", "trades", "trust", "t_fast", "built_at")
MULT_TOL = 1e-9

COLS = (["log_version", "logged_at", "row_type", "signal_id", "decision_time_et", "side",
         "entry_bar_time", "signal_bar_start", "signal_bar_close", "signal_ref_price",
         "decide_at_close", "shadow_trade_ids",
         # flags at the decision (1/0)
         "sq382_30m", "sq422_60m", "keel_sq60_on", "friday", "fomc_pre14",
         # UNCAPPED multipliers, one per arm
         "m_382plain", "m_422plain", "m_422fixed", "m_382keel", "m_422keel",
         # their parts, and what the legs themselves emitted; keel*_fallback: why a learned
         # KEEL keel_size of 1.0 was a fallback, not a score (blank = scored) -- keel_fallback
         "fixed_tilt", "keel382_size", "keel422_size", "keel382_fallback", "keel422_fallback",
         "leg_m_382plain", "leg_m_422plain", "leg_m_422fixed", "mult_check",
         # the book's shares per arm: base x m, rounded, clamped at the per-leg cap
         "base_shares", "max_shares_per_leg", "max_total_shares"]
        + [f"sh_{a}" for a in ARMS]
        # each learned KEEL state's summary. keel*_trust is the STATE-level skill trust
        # (trust_now) BEFORE fast shading: the trust applied to one trade is trust_now x the
        # fast-window clip on t_fast, and 0 when the member stack has no trust -- so read the
        # trade's own keel*_size for what was applied, never trust x z.
        + [f"keel382_{k}" for k in KEEL_META] + [f"keel422_{k}" for k in KEEL_META]
        + ["engine_commit", "note"])

_ERR = {"last_logged": 0.0, "suppressed": 0}
_MEMO = {"key": None, "pending": 0}
_COMMIT = []


# ── small readers ────────────────────────────────────────────────────────────────────────
def forward_log_path(shadow_paths):
    return os.path.join(shadow_paths["state_dir"], FORWARD_LOG_FILENAME)


def read_csv_rows(path):
    """Every row of a CSV as a dict; [] when missing or unreadable."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except (OSError, csv.Error, UnicodeDecodeError):
        return []


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _num(v):
    """A float as the CSV writes it; blank for None."""
    return "" if v is None else float(v)


def _flag(v):
    return "" if v is None else int(bool(v))


def entry_rows(rows, legs):
    """ENTRY rows of `legs` that carry a valid trade id, one per id (first wins), each with
    "_key" = (entry bar UTC, side) -- the same for every leg's entry at one bar and side."""
    out, seen = [], set()
    for r in rows:
        if str(r.get("event") or "").strip().upper() != "ENTRY" or r.get("leg") not in legs:
            continue
        tid = str(r.get("trade_id") or "").strip()
        p = _trade_id.parse(tid)
        if p is None or tid in seen:
            continue
        seen.add(tid)
        out.append(dict(r, _key=(p["entry_utc"], p["side"]), _tid=tid))
    return out


_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def git_head_sha(root=ROOT):
    """HEAD's commit read straight from the checkout's .git files -- no subprocess, so it
    costs a few file reads on the live thread. Handles a plain repo (.git folder), a linked
    worktree (.git file -> gitdir, refs in its commondir), a detached HEAD, loose refs and
    packed-refs. "" when it cannot tell (the caller then asks git itself)."""
    try:
        git = os.path.join(root, ".git")
        gitdir = git
        if os.path.isfile(git):
            line = _read_text(git)
            if not line.startswith("gitdir:"):
                return ""
            gitdir = line[len("gitdir:"):].strip()
            if not os.path.isabs(gitdir):
                gitdir = os.path.normpath(os.path.join(root, gitdir))
        head = _read_text(os.path.join(gitdir, "HEAD"))
        if not head.startswith("ref:"):
            return head if _SHA_RE.fullmatch(head) else ""
        ref = head[len("ref:"):].strip()
        common = gitdir
        if os.path.isfile(os.path.join(gitdir, "commondir")):
            common = os.path.normpath(os.path.join(gitdir, _read_text(os.path.join(gitdir, "commondir"))))
        for d in (gitdir, common):
            p = os.path.join(d, *ref.split("/"))
            if os.path.isfile(p):
                sha = _read_text(p)
                return sha if _SHA_RE.fullmatch(sha) else ""
        packed = os.path.join(common, "packed-refs")
        if os.path.isfile(packed):
            with open(packed, encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split(" ", 1)
                    if len(parts) == 2 and parts[1] == ref and _SHA_RE.fullmatch(parts[0]):
                        return parts[0]
    except Exception:
        return ""
    return ""


def engine_commit():
    """The running checkout's HEAD commit, resolved once per process; "" on any failure.
    Read from the .git files (git_head_sha); only when that cannot tell does it ask `git
    rev-parse HEAD`, with a 1 s timeout. api/cloud_signal.run_thread resolves it at thread
    start, so the first NOISE row never waits on it."""
    if not _COMMIT:
        sha = git_head_sha()
        if not sha:
            try:
                r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                                   text=True, timeout=1,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode == 0:
                    sha = (r.stdout or "").strip()
            except Exception:
                sha = ""
        _COMMIT.append(sha)
    return _COMMIT[0]


def book_caps(qqq_exec_config, orders_config):
    """(base_shares, max_shares_per_leg, max_total_shares, note) from the book's own config
    files -- qqq_exec's shares["NOISE"] and max_shares_per_leg (it CLAMPS a sized entry
    there), webull_orders' rails max_shares_per_leg and max_total_position_shares (it
    REFUSES an order past either). max_shares_per_leg is the smaller of the two per-leg caps
    that are set (0 = neither): the most one leg can hold. Strictly, a size between the two
    would be clamped by qqq_exec and then refused by the rail; both are 60 on the box today.
    Defaults for any value it cannot read, named in `note`."""
    base, total, missing = DEFAULT_BASE_SHARES, DEFAULT_MAX_TOTAL_SHARES, []
    exec_cap = rail_cap = None
    try:
        with open(qqq_exec_config, encoding="utf-8") as f:
            c = json.load(f)
        base = int(c["shares"]["NOISE"])
        exec_cap = int(c.get("max_shares_per_leg") or 0)
    except Exception:
        missing.append("qqq_exec config")
    try:
        with open(orders_config, encoding="utf-8") as f:
            rails = json.load(f).get("rails") or {}
        total = int(rails["max_total_position_shares"])
        rail_cap = int(rails.get("max_shares_per_leg") or 0)
    except Exception:
        missing.append("webull_orders rails")
    if exec_cap is None and rail_cap is None:
        per_leg = DEFAULT_MAX_SHARES_PER_LEG
    else:
        caps = [c for c in (exec_cap, rail_cap) if c]
        per_leg = min(caps) if caps else 0
    note = ("book caps default for unreadable " + ", ".join(missing)) if missing else ""
    return base, per_leg, total, note


def sized_shares(base, m, cap):
    """Shares the book would open for multiplier `m`: api/qqq_exec._sized_shares (base x m,
    rounded, at least 1; a 0-share leg stays 0) clamped at max_shares_per_leg, exactly as
    its sized-entry branch clamps. None for no multiplier."""
    if m is None:
        return None
    if base <= 0:
        return 0
    wanted = max(1, int(round(base * m)))
    return min(wanted, cap) if cap else wanted


def keel_meta(keel_cfg):
    """A learned KEEL leg's state metadata from its summary JSON: {version, seed,
    data_through, trades, trust, t_fast, built_at}, blanks where unknown. The seed is the
    summary's (tools/keel_live_state.py writes it from 2026-09-29) or, failing that, the
    state this process's leg already loaded (cloud_signal._KEEL_STATE_CACHE) -- a state file
    is never loaded here."""
    out = {k: "" for k in KEEL_META}
    if not keel_cfg:
        return out
    s = {}
    try:
        with open(keel_cfg.get("summary_path") or "", encoding="utf-8") as f:
            s = json.load(f) or {}
    except Exception:
        s = {}
    seed = s.get("seed")
    if seed is None:
        try:
            from api import cloud_signal as cs
            hit = cs._KEEL_STATE_CACHE.get(keel_cfg.get("state_path"))
            if hit and isinstance(hit[1], dict):
                seed = hit[1].get("seed")
        except Exception:
            seed = None
    vals = {"version": s.get("version") or keel_cfg.get("version"), "seed": seed,
            "data_through": s.get("data_through") or s.get("last_nq_session"),
            "trades": s.get("n_trades"), "trust": s.get("trust_now"),
            "t_fast": s.get("t_fast_now"), "built_at": s.get("built_at")}
    for k, v in vals.items():
        out[k] = "" if v is None else v
    return out


def keel_fallback(keel_cfg, entry_time, keel_size, arrays=None):
    """Why a learned KEEL leg's `keel_size` at this entry was the 1.0 FALLBACK
    (cloud_signal._keel_size_for_entry) rather than a model score; "" when it scored.

    A fallback is always exactly 1.0, so any other keel_size is a real score and nothing is
    checked. At 1.0 (a real score can be 1.0 too -- zero trust) the leg's own checks are
    replayed without ever loading a state file: the config, the state file on disk, the
    summary's data_through more than KEEL_MAX_STALE_SESSIONS sessions before the entry's
    session, the state having been loaded in THIS process (the leg loaded it moments ago;
    not there = it could not be read), and -- with `arrays` -- its feature columns. A
    scoring-time exception is not visible from here (the leg logs it). "" too for no KEEL
    block, a blank keel_size and a mode="fixed" block (no state, nothing to fall back
    from). Never raises: a failing check is its own reason."""
    ks = _f(keel_size)
    if not keel_cfg or ks is None or ks != 1.0:
        return ""
    try:
        from api import cloud_signal as cs
        mode = cs.keel_mode(keel_cfg)
        if mode == cs.KEEL_MODE_FIXED:
            return ""
        if mode != cs.KEEL_MODE_LEARNED:
            return f"unknown keel mode {mode!r}"
        state_path = keel_cfg.get("state_path")
        if not state_path:
            return "keel config has no state_path"
        if not os.path.exists(state_path):
            return "keel state unavailable (no state file)"
        s = {}
        try:
            with open(keel_cfg.get("summary_path") or "", encoding="utf-8") as f:
                s = json.load(f) or {}
        except Exception:
            s = {}
        last = s.get("data_through") or s.get("last_nq_session")
        if last:
            entered = _dt.datetime.fromisoformat(str(entry_time))
            sessions = cs.market_calendar.sessions_between(last, entered.date().isoformat())
            n_stale = max(0, len(sessions) - 1)
            if n_stale > cs.KEEL_MAX_STALE_SESSIONS:
                return f"keel state stale: {n_stale} session(s) since {last}"
        hit = cs._KEEL_STATE_CACHE.get(state_path)
        if not hit or hit[1] is None:
            return ("keel state not loaded in this process (unreadable at the entry, or a "
                    "backfill in another process: unverified)")
        if arrays is not None:
            from augur_engine import ml_keel as K
            names = K.keel_features(arrays)[1]
            if list(names) != list((hit[1] or {}).get("feature_names") or []):
                return "keel feature columns do not match the state"
        return ""
    except Exception as e:
        return f"keel fallback check failed: {type(e).__name__}: {e}"


# ── the decision bar ─────────────────────────────────────────────────────────────────────
def decision_arrays(epoch_df, entry_time, warmup_sessions, tf="5m"):
    """(arrays, entry_bar, None) -- the arrays a decide-at-close probe sized this entry on:
    every bar closed through the signal bar D (the bar before `entry_time`) over the leg's
    own window, plus the two flat stand-ins; entry_bar = the first stand-in, stamped
    `entry_time`. (None, None, reason) when D is not in the bars."""
    import pandas as pd
    from api import cloud_signal as cs
    et = pd.Timestamp(entry_time)
    if et.tzinfo is None:
        et = et.tz_localize(cs.TZ)
    now_d = (et + pd.Timedelta(seconds=cs.CLOSE_GRACE_SECONDS)).to_pydatetime()
    arrays = cs.closed_arrays(epoch_df, now_d, tf, warmup_sessions)
    if arrays is None or len(arrays["close"]) < 2:
        return None, None, "no bars before the entry bar"
    step = pd.Timedelta(seconds=cs.TIMEFRAME_SECONDS[tf])
    last = pd.Timestamp(arrays["index"][-1])
    if last + step != et:
        return None, None, f"signal bar missing (newest bar before the entry is {last.isoformat()})"
    return cs._stand_in_arrays(arrays, tf), len(arrays["close"]), None


def _plugin_gate(cfg):
    """(module, gate_tf_min, gate_len, gate_ratio, tilt_mult) as the plugin's run_backtest
    resolves them: its signature defaults, then the leg's params, then a frame the file
    freezes itself (NOISE_1_8_CT304H's _GATE_TF_MIN)."""
    import inspect
    from augur_engine.strategies import load_strategy
    mod = load_strategy(cfg["strategy"])
    kw = {k: p.default for k, p in inspect.signature(mod.run_backtest).parameters.items()
          if p.default is not inspect.Parameter.empty}
    kw.update(cfg.get("params") or {})
    tf = getattr(mod, "_GATE_TF_MIN", None)
    if tf is None:
        tf = kw["gate_tf_min"]
    return mod, tf, kw["gate_len"], kw["gate_ratio"], float(kw["tilt_mult"])


def plugin_squeeze(cfg, arrays, entry_bar):
    """(on, size): the plugin's own compression at dec = entry_bar - 1 and the size it gives
    (tilt_mult when on, else 1.0) -- NOISE_1_8_CT304(H).run_backtest's own loop."""
    mod, tf, length, ratio, tilt = _plugin_gate(cfg)
    comp = mod._sq._compression(np.asarray(arrays["high"], float), np.asarray(arrays["low"], float),
                                np.asarray(arrays["close"], float), arrays["day_id"],
                                arrays["index"], tf, length, ratio)
    dec = int(entry_bar) - 1
    on = 0 <= dec < len(arrays["close"]) and bool(comp[dec])
    return on, (tilt if on else 1.0)


def keel_flags(arrays, entry_bar):
    """(sq60_on, friday, fomc_pre, fixed_tilt) at the entry bar, as KEEL v12 reads them."""
    import pandas as pd
    from augur_engine import ml_keel as K
    e = int(entry_bar)
    sq = float(K._squeeze60(arrays)[e])
    sq60_on = bool(np.isfinite(sq) and sq < 1.0)
    friday = int(pd.DatetimeIndex(arrays["index"])[e].dayofweek) == 4
    cut = int(K.FIXED_V12_EVENT.get("cut_hour", 14))
    fomc = bool(K.pre_statement_mask(arrays, np.array([e]), cut)[0])
    tilt = float(K.fixed_tilt_sizes_v12(arrays, [e])[0])
    return sq60_on, friday, fomc, tilt


def _close(a, b):
    return a is not None and b is not None and abs(a - b) <= MULT_TOL * max(1.0, abs(a))


# ── rows ─────────────────────────────────────────────────────────────────────────────────
def _row(row_type, sid, primary, arms, bars, ctx, now):
    """One forward-log row. `primary` is the NOISE_382 ENTRY row (None for shadow_only),
    `arms` {leg: ENTRY row} of the #422 legs at the same bar and side."""
    import pandas as pd
    from api import cloud_signal as cs
    base = primary or next(arms[k] for k in ARM_LEGS if k in arms)
    ref_time = str(base.get("ref_time") or "")
    et = pd.Timestamp(ref_time)
    if et.tzinfo is None:
        et = et.tz_localize(cs.TZ)
    bar = pd.Timedelta(seconds=cs.TIMEFRAME_SECONDS["5m"])
    r = {c: "" for c in COLS}
    r.update({"log_version": LOG_VERSION, "logged_at": now.isoformat(), "row_type": row_type,
              "signal_id": sid, "decision_time_et": base.get("emitted_at") or "",
              "side": base.get("side") or "", "entry_bar_time": ref_time,
              "signal_bar_start": (et - bar).isoformat(), "signal_bar_close": et.isoformat(),
              "signal_ref_price": base.get("ref_price") or "",
              "decide_at_close": int("decide_at_close" in str(base.get("reason") or "")),
              "shadow_trade_ids": ";".join(arms[k]["_tid"] for k in ARM_LEGS if k in arms),
              "base_shares": ctx["base"], "max_shares_per_leg": ctx["per_leg"],
              "max_total_shares": ctx["total"], "engine_commit": ctx["commit"]})
    for k in KEEL_META:
        r[f"keel382_{k}"] = ctx["keel382"].get(k, "")
        r[f"keel422_{k}"] = ctx["keel422"].get(k, "")
    notes = [n for n in (ctx.get("note"),) if n]
    problems = []

    m = {a: None for a in ARMS}
    arrays, eb, why = decision_arrays(bars(), ref_time, ctx["warmup"])
    if arrays is None:
        notes.append(f"flags unavailable: {why}")
        problems.append("flags unavailable")
    else:
        on382, m["382plain"] = plugin_squeeze(ctx["primary_cfg"], arrays, eb)
        on422, m["422plain"] = plugin_squeeze(ctx["plain_cfg"], arrays, eb)
        sq60, fri, fomc, tilt = keel_flags(arrays, eb)
        m["422fixed"] = m["422plain"] * tilt
        r.update({"sq382_30m": _flag(on382), "sq422_60m": _flag(on422), "keel_sq60_on": _flag(sq60),
                  "friday": _flag(fri), "fomc_pre14": _flag(fomc), "fixed_tilt": tilt})

    # what the legs themselves emitted
    if primary is not None:
        size, ks = _f(primary.get("size")), _f(primary.get("keel_size"))
        m["382keel"] = size
        r["keel382_size"] = _num(ks)
        r["keel382_fallback"] = keel_fallback(ctx.get("keel382_cfg"), ref_time, ks, arrays)
        leg_plain = (size / ks) if (size is not None and ks) else size
        r["leg_m_382plain"] = _num(leg_plain)
        if m["382plain"] is not None and not _close(m["382plain"], leg_plain):
            problems.append(f"m_382plain {m['382plain']:g} vs leg {leg_plain}")
    else:
        problems.append(f"no {PRIMARY_LEG} entry (shadow-only signal)")
    for leg, col, arm in ((PLAIN_LEG, "leg_m_422plain", "422plain"),
                          (FIXED_LEG, "leg_m_422fixed", "422fixed")):
        if leg not in arms:
            problems.append(f"no {leg} row")
            continue
        v = _f(arms[leg].get("size"))
        r[col] = _num(v)
        if m[arm] is not None and not _close(m[arm], v):
            problems.append(f"m_{arm} {m[arm]:g} vs leg {v}")
    if KEEL_LEG in arms:
        size, ks = _f(arms[KEEL_LEG].get("size")), _f(arms[KEEL_LEG].get("keel_size"))
        m["422keel"] = size
        r["keel422_size"] = _num(ks)
        r["keel422_fallback"] = keel_fallback(ctx.get("keel422_cfg"), ref_time, ks, arrays)
        plugin = (size / ks) if (size is not None and ks) else size
        if m["422plain"] is not None and not _close(m["422plain"], plugin):
            problems.append(f"{KEEL_LEG} plugin size {plugin} vs m_422plain {m['422plain']:g}")
    else:
        problems.append(f"no {KEEL_LEG} row")

    for a in ARMS:
        r[f"m_{a}"] = _num(m[a])
        sh = sized_shares(ctx["base"], m[a], ctx["per_leg"])
        r[f"sh_{a}"] = "" if sh is None else sh
    r["mult_check"] = "ok" if not problems else "; ".join(problems)
    r["note"] = "; ".join(notes)
    return r


ROW_FAILED = "row failed: "


def _failed_row(row_type, sid, primary, arms, ctx, now, err):
    """The stub a row that raised is logged as: its signal id, side, entry bar and shadow
    ids, mult_check "row failed: <error>" -- written once, so the id counts as logged."""
    base = primary or next((arms[k] for k in ARM_LEGS if k in arms), {})
    r = {c: "" for c in COLS}
    r.update({"log_version": LOG_VERSION, "logged_at": now.isoformat(), "row_type": row_type,
              "signal_id": sid, "decision_time_et": base.get("emitted_at") or "",
              "side": base.get("side") or "", "entry_bar_time": str(base.get("ref_time") or ""),
              "signal_ref_price": base.get("ref_price") or "",
              "shadow_trade_ids": ";".join(arms[k].get("_tid", "") for k in ARM_LEGS if k in arms),
              "engine_commit": ctx.get("commit", ""),
              "mult_check": f"{ROW_FAILED}{type(err).__name__}: {err}"[:500]})
    return r


def _safe_row(row_type, sid, primary, arms, bars, ctx, now):
    try:
        return _row(row_type, sid, primary, arms, bars, ctx, now)
    except Exception as e:
        return _failed_row(row_type, sid, primary, arms, ctx, now, e)


def build_rows(primary_rows, shadow_rows, bars, now, ctx, logged_ids, since_date,
               grace_sec=MATCH_GRACE_SEC, force=False):
    """(rows, pending): a row for every NOISE entry on/after `since_date` (YYYY-MM-DD, the
    entry bar's ET date) not in `logged_ids` -- each primary entry, and each #422 entry with
    no primary entry at its bar and side (row_type "shadow_only", signal_id = the plain
    leg's id, else the fixed, else the KEEL one's). An entry still waiting for its other
    side is held (counted in `pending`) until `grace_sec` after its entry bar opened;
    `force` writes it now. `bars()` returns the 5m epoch frame (called only when a row is
    built). Each row is built on its own: one that raises comes back as a "row failed"
    stub (_failed_row) and every other row is still built."""
    import pandas as pd
    from api import cloud_signal as cs
    prim = {p["_key"]: p for p in entry_rows(primary_rows, (PRIMARY_LEG,))}
    shadow = {}
    for s in entry_rows(shadow_rows, ARM_LEGS):
        shadow.setdefault(s["_key"], {})[s["leg"]] = s

    def _age_ok(entry_utc):
        return force or (now - entry_utc).total_seconds() >= grace_sec

    def _day(entry_utc):
        return pd.Timestamp(entry_utc).tz_convert(cs.TZ).date().isoformat()

    rows, pending = [], 0
    for key in sorted(set(prim) | set(shadow)):
        p, arms = prim.get(key), shadow.get(key, {})
        if _day(key[0]) < since_date:
            continue
        if p is not None:
            sid = p["_tid"]
            if sid in logged_ids:
                continue
            if len(arms) < len(ARM_LEGS) and not _age_ok(key[0]):
                pending += 1
                continue
            rows.append(_safe_row("primary", sid, p, arms, bars, ctx, now))
        else:
            sid = next(arms[k]["_tid"] for k in ARM_LEGS if k in arms)
            if sid in logged_ids:
                continue
            if not _age_ok(key[0]):
                pending += 1
                continue
            rows.append(_safe_row("shadow_only", sid, None, arms, bars, ctx, now))
    return rows, pending


def append_rows(path, rows):
    """Append `rows` under the header already on disk (COLS for a new file), creating the
    folder. Never rewrites a line already there."""
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new_file = not os.path.exists(path) or os.path.getsize(path) == 0
    fieldnames = COLS
    if not new_file:
        try:
            with open(path, encoding="utf-8", newline="") as f:
                fieldnames = next(csv.reader(f), None) or COLS
        except OSError:
            fieldnames = COLS
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def since_date_for(logged, today, lookback_days=LOOKBACK_DAYS):
    """The oldest entry date a tick may still log: today on a new log (nothing from before
    the log went live is ever back-filled), else the later of the log's own first entry
    date and `lookback_days` before today."""
    firsts = sorted(str(r.get("entry_bar_time") or "")[:10] for r in logged
                    if r.get("entry_bar_time"))
    if not firsts:
        return today.isoformat()
    return max(firsts[0], (today - _dt.timedelta(days=lookback_days)).isoformat())


def context(live_legs, shadow_legs, caps):
    """What every row of one tick shares: both legs' cfgs (the #422 one from the plain shadow
    leg, else NOISE_422_PARAMS on NOISE_1_8_CT304H.py), the window, book caps, both KEEL
    states' metadata and the engine commit."""
    from api import cloud_signal as cs
    primary_cfg = live_legs[PRIMARY_LEG]
    plain_cfg = (shadow_legs or {}).get(PLAIN_LEG) or {
        "strategy": "NOISE_1_8_CT304H.py", "timeframe": "5m",
        "params": dict(cs.NOISE_422_PARAMS), "warmup_sessions": cs.DEFAULT_WARMUP_SESSIONS}
    base, per_leg, total, note = caps
    keel382_cfg = primary_cfg.get("keel")
    keel422_cfg = ((shadow_legs or {}).get(KEEL_LEG) or {}).get("keel")
    return {"primary_cfg": primary_cfg, "plain_cfg": plain_cfg,
            "keel382_cfg": keel382_cfg, "keel422_cfg": keel422_cfg,
            "warmup": max(cs.leg_warmup_sessions(primary_cfg), cs.leg_warmup_sessions(plain_cfg)),
            "base": base, "per_leg": per_leg, "total": total, "note": note,
            "keel382": keel_meta(keel382_cfg), "keel422": keel_meta(keel422_cfg),
            "commit": engine_commit()}


def _book_config_paths(live_paths):
    """(qqq_exec config, webull_orders config): the env overrides those two modules honour
    when this is the real store, else <home>/qqq_exec/config.json and
    <home>/webull_orders/config.json of the store being written (a test home)."""
    from api import cloud_signal as cs
    home = live_paths["home"]
    q = os.path.join(home, "qqq_exec", "config.json")
    o = os.path.join(home, "webull_orders", "config.json")
    if os.path.abspath(home) == os.path.abspath(cs.edgelog_home()):
        q = cs._qqq_exec_config_path()
        o = os.environ.get("EDGELOG_WEBULL_ORDERS_CONFIG") or o
    return q, o


def _stat(path):
    try:
        st = os.stat(path)
        return (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _tick(now, live_paths, shadow_paths, live_legs, shadow_legs):
    if PRIMARY_LEG not in (live_legs or {}):
        return 0
    from api import cloud_signal as cs
    live_sig, shadow_sig = live_paths["signals_path"], shadow_paths["signals_path"]
    fwd = forward_log_path(shadow_paths)
    key = (fwd, _stat(live_sig), _stat(shadow_sig), _stat(fwd))
    if _MEMO["key"] == key and not _MEMO["pending"]:
        return 0
    logged = read_csv_rows(fwd)
    logged_ids = {r.get("signal_id") for r in logged}
    since = since_date_for(logged, now.date())
    ctx = context(live_legs, shadow_legs, book_caps(*_book_config_paths(live_paths)))
    cache = {}

    def bars():
        if "df" not in cache:
            cache["df"] = cs.historical_bars("5m", live_paths)
        return cache["df"]
    rows, pending = build_rows(read_csv_rows(live_sig), read_csv_rows(shadow_sig), bars, now,
                               ctx, logged_ids, since)
    append_rows(fwd, rows)
    _MEMO.update(key=(fwd, _stat(live_sig), _stat(shadow_sig), _stat(fwd)), pending=pending)
    return len(rows)


def forward_log_tick(now, live_paths, shadow_paths, live_legs, shadow_legs, log=print):
    """run_shadow_step's one call: write any NOISE forward-log rows now due. Returns how many
    were written; NEVER raises -- a failure is logged at most once per ERROR_LOG_EVERY_SEC
    (with how many were held back) and returns 0. Cheap when nothing changed: the ledgers'
    size/mtime are compared first and nothing is read or computed."""
    try:
        from api import cloud_signal as cs
        if now is None:
            now = _dt.datetime.now(tz=cs._zi(cs.TZ))
        elif now.tzinfo is None:
            now = now.replace(tzinfo=cs._zi(cs.TZ))
        return _tick(now, live_paths, shadow_paths, live_legs, shadow_legs)
    except Exception as e:
        try:
            wall = _time.time()
            if wall - _ERR["last_logged"] >= ERROR_LOG_EVERY_SEC:
                held = _ERR["suppressed"]
                _ERR["last_logged"], _ERR["suppressed"] = wall, 0
                log(f"[cloud-signal] NOISE forward log failed (live and shadow legs unaffected): "
                    f"{type(e).__name__}: {e}" + (f" [+{held} more since the last line]" if held else ""))
            else:
                _ERR["suppressed"] += 1
        except Exception:
            pass
        return 0
