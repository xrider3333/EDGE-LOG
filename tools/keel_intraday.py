r"""tools/keel_intraday.py -- LIVE KEEL on the box: appends each CLOSED live Webull NOISE_382 trade to
the leg's LIVE KEEL v12 state (owner call 10-12 via MANAGER #143: per-trade KEEL learns from the box's
OWN live QQQ trades, not NQ bars -- the owner was told this is no longer the exact NQ backtest and
chose it; Custom ML, KEEL's owner, confirmed the rules 10-12). The whole flow: api/cloud_signal.py,
LIVE KEEL (above _keel_live_pick).

THE CUT (Custom ML 10-12): the live state starts from the nightly NQ state built on the night of
2026-10-12 and learns the live QQQ trades ENTERED from LIVE_FROM_DAY (2026-10-13) on -- NO backfill of
the 09-24..10-12 trades. It is made ONCE: by hand right after that nightly (--cut), else by the first
trade that needs it. A cut is refused from a nightly whose data_through is before the session before
LIVE_FROM_DAY. The cut state is kept as <leg>_<v>_live_cut.joblib, beside the live state.

ONE RUN = EMPTY THE INBOX (edgelog-keel-append.path fires on a file in it; safe to run by hand):
  IN   api/qqq_exec.py drops <home>/cloud_signal/keel_inbox/<trade_id>.json for each FULLY closed live
       NOISE_382 trade: {leg, trade_id, entry_ts, exit_ts, side, shares, pnl_usd, entry_px, exit_px,
       pnl_source, prev_trade_id, ...} -- pnl_usd is the P&L of record (Webull's fills, else the
       book's price); prev_trade_id the previous live NOISE_382 close that book queued.
  0. CATCH-UP: the live state is first brought level with the APPEND LOG (a run that died between
     writing a log row and writing the state): each log row it lacks is applied, in order.
  1. the trades are processed in EXIT order (exit_ts, then entry_ts, then trade_id);
  2. per trade, in order: already appended (its trade_id in the live state's own record) -> done, a
     no-op. BEFORE THE CUT (entered before LIVE_FROM_DAY, or on / before the cut's data_through) ->
     refused, nothing made. THE CHAIN (Custom ML 10-12, MUST d -- refused AND alerted): its
     prev_trade_id must be the last trade this ledger handled (appended or refused) -- else a close
     was missed or doubled and the trade's n_before would not be the live state's n. Then the cut
     is made if there is none yet. Its ENTRY RECORD (<leg>_xrows.jsonl, written by api/cloud_signal
     at the entry: the exact feature row KEEL scored) missing -> REJECTED, recorded, the next trade
     still goes. REFUSED when its entry is before the last appended exit (an overlap: the walk's
     ledger has none), the record's feature names are not the state's, or its numbers are unusable
     (pnl, shares, sizes, no NQ/QQQ price ratio). Else P = qqq_trade_to_walk_pnl(...);
  3. the APPEND LOG row first (<leg>_live_appends.jsonl, append-only: trade_id, n_before / n_after,
     x_row, P and its three inputs -- pnl_usd / shares, the plugin size, the ratio with the NQ and
     QQQ closes, their session and bar -- entry / exit stamps and bars), THEN
     live = ml_keel.keel_append_trade(live, x_row, P, entry_bar, exit_bar) from that row, then
     <leg>_<v>_live_prev.joblib (the state before it -- the scorer's same-bar rule), _live.joblib,
     and the ack <leg>_<v>_live_ack.json (n, the last appended and the last handled trade, the cut,
     the rejected trade ids) -- each written beside its target and os.replace'd in;
  OUT  every file leaves the inbox: keel_inbox_done/ or keel_inbox_rejected/ (+ <name>.reason.json),
       SIBLINGS of the inbox (a subdirectory would keep the DirectoryNotEmpty trigger firing).
  ALERTS no push from here: a chain refusal, or the live state and its append log disagreeing, is
       recorded in the ack's "alerts" (kind chain / ledger, trade_id, at, reason); the nightly
       tools/keel_live_state.live_check folds the ones since its last check into
       keel/keel_live_check.json, and the box monitor (tools/webull_freshness.py keel_live:<leg>)
       pushes ONE plain note per episode (Custom ML 10-12, the final alert rules). Every other
       refusal is in the ack and the log only.

REPRODUCIBLE (Custom ML 10-12, MUST b): live state == the cut + a replay of the append log, at any
time -- rebuild_from() / rebuild_live_state() replay it; exact_mismatches() is THE EXACT test (n,
n_fits, fitted_on, trust_now, t_fast_now and the last z to EXACT_TOL = 1e-9), used by the nightly
alert (tools/keel_live_state.live_check) and by verify_live_state() / --verify.

IDEMPOTENT: the live state's own record (KEEL_LIVE_META "appended") is the truth for "done", the
append log for "decided" -- a run killed between the log and the state is completed by the next
run's catch-up; a log row is never written twice for one trade.

DECIDED HERE (beyond the spec):
  * the overlap refusal is strict: entry_ts < the last appended exit_ts. The executor closes a lot
    and opens the next one in ONE tick on a reversal, so both stamps may be the same second; one
    NOISE lot at a time means equal stamps are never an overlap.
  * entry_bar / exit_bar passed to keel_append_trade are 5-minute BAR NUMBERS (epoch seconds // 300
    of the bar's start: the engine's entry bar, the bar holding the executor's exit) -- the live
    ledger spans many days, so an index into one day's QQQ arrays would mean nothing. Live scoring
    (cross_series=True) never reads them.
  * the NQ/QQQ ratio uses the entry's prior session; when either file lacks it, the latest session
    before the entry both files hold, at most RATIO_MAX_SESSIONS back (the ratio session is kept
    on the log row); none -> refused.
  * the chain: the executor cannot know KEEL's n, so it sends prev_trade_id and this handler checks
    it (its n_before is then the live state's n by construction). A trade with no prev_trade_id key
    (a hand-made file) or a null one (the executor's first close on record) is not checked; a trade
    re-sent by hand after a refusal is not checked (the overlap rule still guards the order) and
    does not move the chain.
  * no nightly state to cut from -> every trade of the run is rejected (moved to rejected/; a hand
    re-run moves them back into the inbox).

USAGE (the box's edgelog-keel-append.service):
    python tools/keel_intraday.py --nq-file <home>/nq/NOADJ_NQ_5m_RTH.csv --home <home>
  by hand: --cut (make the cut now, from the current nightly; refused once a live state exists),
           --verify (live state == cut + append log replay? exit 1 when not).
"""
import argparse
import csv
import datetime as _dt
import json
import math
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LEG_KEY = "NOISE_382"             # api/cloud_signal.KEEL_LIVE_LEARN_LEGS
MASTER_NAME = "NOADJ_NQ_5m_RTH.csv"
INBOX = "keel_inbox"              # under <home>/cloud_signal/ -- the path unit watches it
INBOX_TMP = "keel_inbox_tmp"      # api/qqq_exec.py writes here first, then os.replace's in
DONE = "keel_inbox_done"          # siblings of INBOX, never inside it (DirectoryNotEmpty)
REJECTED = "keel_inbox_rejected"
LOCK_NAME = "keel_inbox.lock"     # under <home>/cloud_signal/, outside the inbox
KEEP_FILES = 400                  # newest files kept in done/ and rejected/
REJECTED_KEEP = 200               # rejected trade ids kept in the ack
TF_SECONDS = 300                  # NOISE_382's 5-minute bar
RATIO_MAX_SESSIONS = 5
TAIL_BYTES = 512 * 1024           # the price files are read from their tail (~a month of 5m bars)
ET = "America/New_York"
TS_FMT = "%Y-%m-%d %H:%M:%S"      # api/qqq_exec.py's entry_ts / exit_ts (New York wall clock)
TRADE_KEYS = ("leg", "trade_id", "entry_ts", "exit_ts", "side", "shares", "pnl_usd", "pnl_source")
# THE CUT (Custom ML 10-12): live trades ENTERED on / after this day are learned; nothing before it
# (no backfill of 09-24..10-12). A cut needs a nightly through the session before it (cut_floor).
LIVE_FROM_DAY = "2026-10-13"
ALERTS_KEEP = 50                  # chain / ledger alerts kept in the ack
EXACT_TOL = 1e-9                  # THE EXACT test's tolerance (Custom ML 10-12)


class TradeError(ValueError):
    """An inbox file this handler will not use."""


def _log(msg):
    print(f"{_dt.datetime.now(_dt.timezone.utc).isoformat(timespec='seconds')} [keel-live] {msg}",
          flush=True)


def _now_iso():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# ── the P conversion: ONE function, switchable ──────────────────────────────────────────────────
def qqq_trade_to_walk_pnl(pnl_usd, shares, engine_size, keel_size, ratio):
    """A live QQQ trade's P in the KEEL walk's own units -- the ONE place this conversion lives
    (Custom ML to confirm the rule; swap the body, keep the signature).

    RULE (default, owner spec 10-12 via MANAGER #143):
        P = (pnl_usd / shares) x plugin_size x ratio
      pnl_usd / shares   the P&L of record per share (Webull's fills, slippage included -- so NO
                         extra cost is charged here);
      plugin_size        engine_size / keel_size from the trade's entry record: run #382's own
                         plugin sizing (NOISE_1_8_CT304's 2.0x tilt), which the walk's P carries
                         (tools/keel_live_state.run_nq_backtest);
      ratio              NQ/QQQ price ratio = the box NQ master's close / the QQQ cache's close on
                         the entry's prior session -- QQQ dollars per share to NQ points.
    Raises ValueError on any non-finite or non-positive input (shares, sizes, ratio) or a
    non-finite pnl."""
    vals = {"pnl_usd": pnl_usd, "shares": shares, "engine_size": engine_size,
            "keel_size": keel_size, "ratio": ratio}
    f = {}
    for k, v in vals.items():
        try:
            f[k] = float(v)
        except (TypeError, ValueError):
            raise ValueError(f"{k} is not a number: {v!r}")
        if not math.isfinite(f[k]):
            raise ValueError(f"{k} is not finite: {v!r}")
        if k != "pnl_usd" and f[k] <= 0:
            raise ValueError(f"{k} must be > 0: {v!r}")
    plugin_size = f["engine_size"] / f["keel_size"]
    return (f["pnl_usd"] / f["shares"]) * plugin_size * f["ratio"]


# ── the NQ/QQQ price ratio ──────────────────────────────────────────────────────────────────────
def _et_date(epoch):
    from zoneinfo import ZoneInfo
    return _dt.datetime.fromtimestamp(int(epoch), tz=ZoneInfo(ET)).date()


def _sessions_before(day, n):
    """The `n` trading sessions before `day` (an ISO date or date), newest first."""
    from api import market_calendar as mc
    d = _dt.date.fromisoformat(str(day)) if not isinstance(day, _dt.date) else day
    out = []
    for _ in range(n * 4 + 10):
        d -= _dt.timedelta(days=1)
        if mc.is_session(d):
            out.append(d)
            if len(out) == n:
                break
    return out


def _rth_window(day):
    """(first, last) bar START epochs of `day`'s regular session (09:30 .. close - 5 min)."""
    from zoneinfo import ZoneInfo
    from api import market_calendar as mc
    tz = ZoneInfo(ET)
    hh, mm = (int(x) for x in mc.session_close_et(day).split(":"))
    first = _dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=tz).timestamp()
    last = _dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz).timestamp() - TF_SECONDS
    return int(first), int(last)


def _closes_by_day(path, days):
    """{date: {bar start epoch: close}} for the regular-session bars of `days` in a price CSV with
    "time" (epoch seconds, the bar start) and "close" columns -- read from its tail, the whole file
    only when the tail does not reach back to the oldest day. Rows it cannot parse are skipped."""
    want = {d: _rth_window(d) for d in days}
    oldest = min(want.values())[0] if want else None

    def scan(lines, header):
        ti, ci = header.index("time"), header.index("close")
        out = {d: {} for d in want}
        first_t = None
        for r in csv.reader(lines):
            if len(r) <= max(ti, ci):
                continue
            try:
                t = int(float(r[ti]))
                c = float(r[ci])
            except ValueError:
                continue
            first_t = t if first_t is None else min(first_t, t)
            if not math.isfinite(c):
                continue
            for d, (lo, hi) in want.items():
                if lo <= t <= hi:
                    out[d][t] = c
        return out, first_t

    with open(path, encoding="utf-8", newline="") as f:
        header = next(csv.reader([f.readline()]))
        f.seek(0, os.SEEK_END)
        size = f.tell()
    if "time" not in header or "close" not in header:
        raise ValueError(f"{path} has no time/close columns")
    with open(path, "rb") as fb:
        start = max(0, size - TAIL_BYTES)
        fb.seek(start)
        blob = fb.read().decode("utf-8", errors="replace")
    # drop the first line: the header (start 0) or a partial line (a tail read)
    lines = blob.splitlines()[1:]
    out, first_t = scan(lines, header)
    if start > 0 and (first_t is None or (oldest is not None and first_t > oldest)):
        with open(path, encoding="utf-8", newline="") as f:
            next(f)
            out, _ = scan(f, header)
    return out


def price_ratio(nq_file, qqq_file, entry_day):
    """(ratio, info): NQ close / QQQ close at the LAST regular-session bar both files hold on the
    entry's prior session -- else on the latest of the RATIO_MAX_SESSIONS sessions before the
    entry both hold. info: {session, bar_epoch, nq_close, qqq_close, fallback}. Raises ValueError
    when there is none."""
    days = _sessions_before(entry_day, RATIO_MAX_SESSIONS)
    nq = _closes_by_day(nq_file, days)
    qq = _closes_by_day(qqq_file, days)
    for i, d in enumerate(days):
        common = sorted(set(nq.get(d) or {}) & set(qq.get(d) or {}))
        if common:
            t = common[-1]
            n, q = nq[d][t], qq[d][t]
            if n > 0 and q > 0:
                return n / q, {"session": d.isoformat(), "bar_epoch": t, "nq_close": n,
                               "qqq_close": q, "fallback": i > 0}
    raise ValueError(f"no session before {entry_day} (last {RATIO_MAX_SESSIONS}) has a bar in both "
                     f"the NQ master and the QQQ cache")


# ── the inbox trade ─────────────────────────────────────────────────────────────────────────────
def _parse_ts(s):
    """An executor stamp ("YYYY-mm-dd HH:MM:SS", New York) or ISO -> tz-aware ET datetime."""
    from zoneinfo import ZoneInfo
    s = str(s or "").strip()
    try:
        d = _dt.datetime.strptime(s, TS_FMT)
    except ValueError:
        d = _dt.datetime.fromisoformat(s)
    return d.replace(tzinfo=ZoneInfo(ET)) if d.tzinfo is None else d.astimezone(ZoneInfo(ET))


def bar_number(ts):
    """The 5-minute bar number (epoch seconds // 300 of its start) holding `ts`."""
    return int(_parse_ts(ts).timestamp()) // TF_SECONDS


def bar_start_iso(ts):
    from zoneinfo import ZoneInfo
    return _dt.datetime.fromtimestamp(bar_number(ts) * TF_SECONDS, tz=ZoneInfo(ET)).isoformat()


def read_trade(path, leg_key=LEG_KEY):
    """The inbox trade at `path`, validated; raises TradeError(reason)."""
    name = os.path.basename(path)
    if not name.endswith(".json"):
        raise TradeError(f"not a trade file: {name}")
    try:
        with open(path, encoding="utf-8") as f:
            tr = json.load(f)
    except (OSError, ValueError) as e:
        raise TradeError(f"unreadable JSON: {type(e).__name__}: {e}")
    if not isinstance(tr, dict):
        raise TradeError("not a JSON object")
    missing = [k for k in TRADE_KEYS if k not in tr]
    if missing:
        raise TradeError(f"missing {', '.join(missing)}")
    if tr["leg"] != leg_key:
        raise TradeError(f"leg {tr['leg']!r} is not {leg_key}")
    if not str(tr["trade_id"]).startswith(leg_key + "-"):
        raise TradeError(f"trade id {tr['trade_id']!r} is not a {leg_key} id")
    try:
        _parse_ts(tr["entry_ts"])
        _parse_ts(tr["exit_ts"])
    except ValueError as e:
        raise TradeError(f"bad entry_ts / exit_ts: {e}")
    return tr


def _order_key(tr):
    return (_parse_ts(tr["exit_ts"]), _parse_ts(tr["entry_ts"]), str(tr["trade_id"]))


# ── files ──────────────────────────────────────────────────────────────────────────────────────
def inbox_paths(home):
    d = os.path.join(home, "cloud_signal")
    return {"cloud_signal": d, "inbox": os.path.join(d, INBOX), "tmp": os.path.join(d, INBOX_TMP),
            "done": os.path.join(d, DONE), "rejected": os.path.join(d, REJECTED),
            "lock": os.path.join(d, LOCK_NAME)}


def leg_files(home, leg_key, version):
    from api import cloud_signal as cs
    p = cs.keel_paths(leg_key, version, home=home)
    if "live_path" not in p:
        raise ValueError(f"{leg_key} is not a live-learning KEEL leg (cloud_signal.KEEL_LIVE_LEARN_LEGS)")
    p["qqq_5m"] = cs._cache_path("5m", cs._paths(home=home))
    return p


def _drop_tmp(tmp):
    try:
        os.remove(tmp)
    except OSError:
        pass


def _atomic_joblib(obj, path):
    """Write beside `path`, then rename over it: a reader sees the old file or the new one."""
    import joblib
    tmp = path + ".tmp"
    try:
        joblib.dump(obj, tmp)
        os.replace(tmp, path)
    except BaseException:
        _drop_tmp(tmp)
        raise


def _atomic_json(obj, path):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        _drop_tmp(tmp)
        raise


def _load_joblib(path):
    import joblib
    try:
        return joblib.load(path) if os.path.exists(path) else None
    except Exception as e:
        _log(f"could not read {path}: {type(e).__name__}: {e}")
        return None


def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ── the cut ─────────────────────────────────────────────────────────────────────────────────────
def _day(x):
    return x if isinstance(x, _dt.date) else _dt.date.fromisoformat(str(x)[:10])


def cut_floor(live_from=None):
    """The oldest nightly data_through a cut may come from: the session before `live_from`
    (default LIVE_FROM_DAY) -- the nightly built on that session's evening."""
    return _sessions_before(_day(live_from or LIVE_FROM_DAY), 1)[0]


def make_cut(files, leg_key, version, first_exit_ts, now_iso, live_from=None):
    """The live state at the CUT: a copy of the current nightly state + its KEEL_LIVE_META record
    (cut: the nightly's built_at / n / data_through, cut_at, from_exit_ts = the first trade's exit,
    None for a cut made by hand, live_from). Raises ValueError when there is no readable nightly
    state + summary, or its data_through is before cut_floor(live_from)."""
    from api import cloud_signal as cs
    nightly = _load_joblib(files["state_path"])
    summary = _load_json(files["summary_path"])
    if not isinstance(nightly, dict) or not isinstance(summary, dict):
        raise ValueError("no readable nightly state + summary to cut from")
    if summary.get("n_trades") is not None and int(summary["n_trades"]) != int(nightly["n"]):
        raise ValueError("the nightly summary and state disagree on n (a build mid-swap?)")
    through = summary.get("data_through") or summary.get("last_nq_session")
    floor = cut_floor(live_from)
    if not through or _day(through) < floor:
        raise ValueError(f"the nightly holds NQ through {through}: the cut needs one through "
                         f"{floor} or later (tonight's) -- not cut")
    cut = {"built_at": summary.get("built_at"), "n": int(nightly["n"]), "data_through": str(through),
           "cut_at": now_iso, "from_exit_ts": (str(first_exit_ts) if first_exit_ts else None),
           "live_from": str(_day(live_from or LIVE_FROM_DAY))}
    meta = {"leg": leg_key, "version": version, "cut": cut, "appended": [], "last_trade_id": None,
            "last_entry_ts": None, "last_exit_ts": None, "last_exit_bar_ts": None,
            "written_at": now_iso}
    return dict(nightly, **{cs.KEEL_LIVE_META: meta})


def _install_cut(files, live, log=_log):
    """The cut file first, then the live state (both atomic): a live state never exists without
    its cut."""
    from api import cloud_signal as cs
    _atomic_joblib(live, files["live_cut_path"])
    _atomic_joblib(live, files["live_path"])
    c = cs.keel_live_meta(live)["cut"]
    log(f"CUT: the live state starts from the nightly (n={live['n']}, built {c['built_at']}, data "
        f"through {c['data_through']}); live trades entered from {c['live_from']} on")


def before_the_cut(tr, cut_through, live_from=None):
    """Why the trade is before the cut (never learned: no backfill), else None. `cut_through` is
    the cut's data_through -- or, before the cut, the nightly's that the cut would copy."""
    day = _parse_ts(tr["entry_ts"]).date()
    first = _day(live_from or LIVE_FROM_DAY)
    if day < first:
        return f"before the cut (no backfill): entered {day}, live learning starts {first}"
    if cut_through and day <= _day(cut_through):
        return (f"before the cut (no backfill): entered {day}, on or before the cut's NQ data "
                f"(through {cut_through})")
    return None


# ── the append ──────────────────────────────────────────────────────────────────────────────────
def live_append_row(live, tr, xrec, ratio, ratio_info, now_iso):
    """The APPEND LOG row for inbox trade `tr` on `live` with its entry record `xrec` (Custom ML
    10-12, MUST b): everything the append uses -- n_before / n_after, x_row, P and its three inputs
    (pnl_usd / shares, the plugin size, the ratio with the two closes, their session and bar),
    entry / exit stamps and bars. Raises ValueError on a refusal (see the module docstring)."""
    from api import cloud_signal as cs
    meta = cs.keel_live_meta(live)
    if meta is None:
        raise ValueError("the live state has no live record")
    if meta.get("last_exit_ts") and _parse_ts(tr["entry_ts"]) < _parse_ts(meta["last_exit_ts"]):
        raise ValueError(f"entry {tr['entry_ts']} is before the last appended exit "
                         f"{meta['last_exit_ts']} ({meta.get('last_trade_id')})")
    if list(xrec.get("feature_names") or []) != list(live.get("feature_names") or []):
        raise ValueError("the entry record's feature names differ from the live state's")
    x = xrec.get("x_row")
    if not isinstance(x, list) or len(x) != len(live["feature_names"]):
        raise ValueError("the entry record's x_row is not one value per feature")
    P = qqq_trade_to_walk_pnl(tr.get("pnl_usd"), tr.get("shares"), xrec.get("engine_size"),
                              xrec.get("keel_size"), ratio)
    ri = ratio_info or {}
    rbar = ri.get("bar_epoch")
    return {"leg": meta.get("leg"), "trade_id": tr["trade_id"],
            "n_before": int(live["n"]), "n_after": int(live["n"]) + 1,
            "prev_trade_id": tr.get("prev_trade_id"),
            "entry_ts": tr["entry_ts"], "exit_ts": tr["exit_ts"],
            "entry_bar_time": xrec.get("entry_bar_time"), "exit_bar_time": bar_start_iso(tr["exit_ts"]),
            "entry_bar": bar_number(xrec.get("entry_bar_time") or xrec.get("entry_time")),
            "exit_bar": bar_number(tr["exit_ts"]), "side": tr.get("side"),
            "shares": tr.get("shares"), "pnl_usd": tr.get("pnl_usd"), "pnl_source": tr.get("pnl_source"),
            "pnl_per_share": float(tr["pnl_usd"]) / float(tr["shares"]),
            "engine_size": xrec.get("engine_size"), "keel_size": xrec.get("keel_size"),
            "plugin_size": float(xrec["engine_size"]) / float(xrec["keel_size"]),
            "ratio": ratio, "nq_close": ri.get("nq_close"), "qqq_close": ri.get("qqq_close"),
            "ratio_session": ri.get("session"), "ratio_fallback": ri.get("fallback"),
            "ratio_bar_time": (_dt.datetime.fromtimestamp(int(rbar), _dt.timezone.utc)
                               .astimezone(_parse_ts(tr["entry_ts"]).tzinfo).isoformat()
                               if rbar is not None else None),
            "P": P, "x_row": list(x),
            "scored_on": xrec.get("state_source"), "scored_n": xrec.get("state_n"),
            "appended_at": now_iso}


def apply_append_row(live, row, now_iso=None):
    """The live state after log row `row`: ml_keel.keel_append_trade(live, x_row, P, entry_bar,
    exit_bar) with the row's own values, and (a live state) its record of the trade = the row
    without x_row. `live` is never changed. Raises ValueError when the row's n_before is not
    the state's n."""
    import numpy as np
    from api import cloud_signal as cs
    from augur_engine import ml_keel as K
    if int(row["n_before"]) != int(live["n"]):
        raise ValueError(f"log row {row['trade_id']}: n_before {row['n_before']}, the state's n is "
                         f"{live['n']}")
    x = np.array([np.nan if v is None else float(v) for v in row["x_row"]], float).reshape(1, -1)
    new = K.keel_append_trade(live, x, float(row["P"]), entry_bar=int(row["entry_bar"]),
                              exit_bar=int(row["exit_bar"]))
    meta = cs.keel_live_meta(live)
    if meta is not None:
        rec = {k: v for k, v in row.items() if k != "x_row"}
        new[cs.KEEL_LIVE_META] = dict(
            meta, appended=list(meta.get("appended") or []) + [rec], last_trade_id=row["trade_id"],
            last_entry_ts=row["entry_ts"], last_exit_ts=row["exit_ts"],
            last_exit_bar_ts=row.get("exit_bar_time") or bar_start_iso(row["exit_ts"]),
            written_at=now_iso or row.get("appended_at"))
    return new


def append_live_trade(live, tr, xrec, ratio, ratio_info, now_iso):
    """(new_live, log_row): live_append_row, then apply_append_row."""
    row = live_append_row(live, tr, xrec, ratio, ratio_info, now_iso)
    return apply_append_row(live, row, now_iso), row


# ── the append log: live state == the cut + its replay (Custom ML 10-12, MUST b) ────────────────
class LedgerError(ValueError):
    """The live state and its append log disagree: nothing is appended until a hand fix."""


def read_appends(path):
    """The append log's rows in file order (a torn or bad line skipped). Missing file -> []."""
    out = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("trade_id"):
                    out.append(r)
    except OSError:
        return []
    return out


def _append_log(path, row):
    """The log's row for this trade: `row`, appended (one JSON line, one write, fsynced; a torn last
    line is closed first) -- or the row already there for its trade_id (the log is the truth), when
    it has the same n_before; else LedgerError."""
    for r in read_appends(path):
        if r["trade_id"] == row["trade_id"]:
            if int(r.get("n_before", -1)) != int(row["n_before"]):
                raise LedgerError(f"the append log already holds {row['trade_id']} at n_before "
                                  f"{r.get('n_before')}, not {row['n_before']}")
            return r
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lead = ""
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            lead = "" if f.read(1) == b"\n" else "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(lead + json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return row


def _catch_up(live, files, log=_log):
    """(live, applied): `live` brought level with the append log -- each row it lacks applied in
    order and written (prev, then the state). LedgerError when they disagree: a trade the state
    holds is not in the log, or a missing row's n_before is not the state's n."""
    from api import cloud_signal as cs
    meta = cs.keel_live_meta(live) or {}
    have = [str(a.get("trade_id")) for a in meta.get("appended") or [] if isinstance(a, dict)]
    rows = read_appends(files["appends_path"])
    logged = {str(r["trade_id"]) for r in rows}
    lost = [t for t in have if t not in logged]
    if lost:
        raise LedgerError(f"the append log lacks {len(lost)} trade(s) the live state holds "
                          f"({lost[0]}...) -- the live state cannot be rebuilt")
    applied = 0
    for r in rows:
        if str(r["trade_id"]) in have:
            continue
        try:
            nxt = apply_append_row(live, r, _now_iso())
        except ValueError as e:
            raise LedgerError(f"the append log is ahead of the live state and does not fit it: {e}")
        _atomic_joblib(live, files["live_prev_path"])
        _atomic_joblib(nxt, files["live_path"])
        live = nxt
        have.append(str(r["trade_id"]))
        applied += 1
        log(f"CAUGHT UP {r['trade_id']} from the append log (n={live['n']})")
    return live, applied


def replay(cut_state, rows):
    """`cut_state` + the append-log `rows`, row by row (apply_append_row ->
    ml_keel.keel_append_trade; each row's n_before must be the state's n). Raises ValueError when
    there is no cut state or a row does not fit."""
    if not isinstance(cut_state, dict):
        raise ValueError("no cut state")
    st = cut_state
    for r in rows:
        st = apply_append_row(st, r)
    return st


def rebuild_from(cut_path, appends_path):
    """The live state rebuilt from scratch: the CUT state at `cut_path` + a replay of the append log
    at `appends_path` (replay). Raises ValueError when the cut is missing or a row does not fit."""
    st = _load_joblib(cut_path)
    if not isinstance(st, dict):
        raise ValueError(f"no cut state at {cut_path}")
    return replay(st, read_appends(appends_path))


def rebuild_live_state(home, leg_key=LEG_KEY, version=None):
    """rebuild_from the leg's own cut file and append log under `home`."""
    from tools import keel_live_state as L
    version = version or L.resolve_leg(leg_key)["version"]
    files = leg_files(home, leg_key, version)
    return rebuild_from(files["live_cut_path"], files["appends_path"])


EXACT_KEYS = ("n", "n_fits", "fitted_on", "trust_now", "t_fast_now", "last_z")


def _exact_value(state, key):
    if key == "last_z":
        z = state.get("z")
        return float(z[-1]) if z is not None and len(z) else None
    v = state.get(key)
    return None if v is None else (int(v) if key in ("n", "n_fits", "fitted_on") else float(v))


def exact_mismatches(live, rebuilt, tol=EXACT_TOL):
    """THE EXACT test (Custom ML 10-12): ({key: [live, rebuilt]} for EXACT_KEYS, the keys that
    differ). n, n_fits, fitted_on must be equal; trust_now, t_fast_now and the last z within
    `tol` (None == None, NaN == NaN)."""
    import math
    fields, bad = {}, []
    for k in EXACT_KEYS:
        a, b = _exact_value(live, k), _exact_value(rebuilt, k)
        fields[k] = [a, b]
        if a is None or b is None:
            same = a is None and b is None
        elif k in ("n", "n_fits", "fitted_on"):
            same = a == b
        elif math.isnan(a) or math.isnan(b):
            same = math.isnan(a) and math.isnan(b)
        else:
            same = abs(a - b) <= tol
        if not same:
            bad.append(k)
    return fields, bad


def verify_live_state(home, leg_key=LEG_KEY, version=None, log=_log):
    """Does the stored live state equal the cut + the replayed append log (exact_mismatches)?
    {ok, n_live, n_rebuilt, fields, mismatches}. Never raises."""
    out = {"ok": False, "n_live": None, "n_rebuilt": None, "fields": {}, "mismatches": []}
    try:
        from tools import keel_live_state as L
        version = version or L.resolve_leg(leg_key)["version"]
        files = leg_files(home, leg_key, version)
        live = _load_joblib(files["live_path"])
        if not isinstance(live, dict):
            raise ValueError("no readable live state")
        reb = rebuild_from(files["live_cut_path"], files["appends_path"])
        out.update(n_live=int(live["n"]), n_rebuilt=int(reb["n"]))
        out["fields"], bad = exact_mismatches(live, reb)
        out.update(ok=not bad, mismatches=bad)
    except Exception as e:
        out["mismatches"] = [f"{type(e).__name__}: {e}"]
    log(f"verify: {'OK' if out['ok'] else 'MISMATCH'} -- live n={out['n_live']}, cut + log replay "
        f"n={out['n_rebuilt']}" + (f"; {', '.join(out['mismatches'])}" if out["mismatches"] else ""))
    return out


# ── the chain: a missed or doubled close (Custom ML 10-12, MUST d) ─────────────────────────────
class ChainError(ValueError):
    """The trade's previous close is not the last trade this ledger handled."""


def chain_problem(tr, last_tid, n):
    """None when inbox trade `tr` follows `last_tid` (the last trade handled since the cut,
    appended or refused; None = none yet), else why it is refused. See the module docstring for
    the trades that are not checked (no prev_trade_id key, a null one)."""
    if "prev_trade_id" not in tr or tr["prev_trade_id"] is None:
        return None
    prev = str(tr["prev_trade_id"])
    if last_tid is not None and prev == str(last_tid):
        return None
    return (f"missed or doubled close: its previous close is {prev}, the last trade this ledger "
            f"handled is {last_tid or 'none'} -- its n_before would not be the live state's n={n}")


def _last_handled(ack, meta):
    """The last trade handled since the cut: the ack's last_processed, or the live state's last
    appended trade when that is later (an ack write that failed)."""
    lp = (ack or {}).get("last_processed") if isinstance(ack, dict) else None
    lp = lp if isinstance(lp, dict) and lp.get("trade_id") else None
    m_tid, m_exit = (meta or {}).get("last_trade_id"), (meta or {}).get("last_exit_ts")
    if lp is None:
        return m_tid
    if m_tid and m_exit and lp.get("exit_ts"):
        try:
            if _parse_ts(m_exit) > _parse_ts(lp["exit_ts"]):
                return m_tid
        except ValueError:
            pass
    return lp["trade_id"]


# ── the inbox ───────────────────────────────────────────────────────────────────────────────────
class _Lock:
    """An OS lock on <home>/cloud_signal/keel_inbox.lock (fcntl.flock; msvcrt on Windows), so a
    hand run never races the service. Released by the kernel when the process ends."""

    def __init__(self, path):
        self.path = path
        self.f = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.f = open(self.path, "a+")
        try:
            import fcntl
            fcntl.flock(self.f.fileno(), fcntl.LOCK_EX)
        except ImportError:
            import msvcrt
            for _ in range(600):
                try:
                    self.f.seek(0)
                    msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    time.sleep(0.1)
        return self

    def __exit__(self, *exc):
        try:
            self.f.close()
        except OSError:
            pass
        return False


def _move(src, dest_dir, log=_log):
    """Move an inbox entry out (replacing a same-named one there); delete it when it cannot move.
    True when the inbox no longer holds it."""
    try:
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(src))
        if os.path.isdir(dest) and not os.path.isdir(src):
            shutil.rmtree(dest, ignore_errors=True)
        os.replace(src, dest)
        return True
    except OSError as e:
        log(f"could not move {src} to {dest_dir} ({type(e).__name__}: {e}) -- deleting it")
    try:
        if os.path.isdir(src):
            shutil.rmtree(src)
        else:
            os.remove(src)
        return True
    except OSError as e:
        log(f"COULD NOT EMPTY THE INBOX: {src} ({type(e).__name__}: {e})")
        return False


def _prune(d, keep=KEEP_FILES):
    try:
        names = [os.path.join(d, n) for n in os.listdir(d)]
        names = [p for p in names if os.path.isfile(p)]
        names.sort(key=os.path.getmtime)
        for p in names[:-keep] if len(names) > keep else []:
            os.remove(p)
    except OSError:
        pass


def _reject_record(paths, name, ack):
    try:
        os.makedirs(paths["rejected"], exist_ok=True)
        _atomic_json(ack, os.path.join(paths["rejected"], name + ".reason.json"))
    except OSError:
        pass


def _write_ack(files, live, rejected, last, last_processed=None, alerts=None, log=_log):
    """The ack: n, the last appended trade, the last trade handled (the chain), the cut, the
    rejected trade ids (newest REJECTED_KEEP), the chain / ledger alerts (newest ALERTS_KEEP).
    Written before the cut too (n null)."""
    from api import cloud_signal as cs
    meta = cs.keel_live_meta(live) or {}
    keep = dict(list(rejected.items())[-REJECTED_KEEP:])
    ack = {"leg": meta.get("leg"), "version": meta.get("version"),
           "n": int(live["n"]) if isinstance(live, dict) and "n" in live else None,
           "last_trade_id": meta.get("last_trade_id"), "last_exit_ts": meta.get("last_exit_ts"),
           "appended": len(meta.get("appended") or []), "cut": meta.get("cut"),
           "last_processed": last_processed, "rejected": keep,
           "alerts": list(alerts or [])[-ALERTS_KEEP:], "last": last, "updated_at": _now_iso()}
    try:
        _atomic_json(ack, files["live_ack_path"])
    except OSError as e:
        log(f"could not write the ack: {type(e).__name__}: {e}")
    return ack


def process_inbox(home, nq_file, leg_key=LEG_KEY, log=_log, max_rounds=20, ratio_fn=None,
                  live_from=None):
    """Empty the inbox -- see the module docstring. `ratio_fn(entry_day)` -> (ratio, info) is a
    test seam (default: price_ratio on the NQ master and <home>/ohlc/QQQ_5m.csv); `live_from`
    the first entry day learned (default LIVE_FROM_DAY). Returns one result dict per inbox file
    ({file, trade_id, status: appended / noop / rejected, reason, n_before, alert})."""
    from api import cloud_signal as cs
    from tools import keel_live_state as L
    paths = inbox_paths(home)
    os.makedirs(paths["inbox"], exist_ok=True)
    results = []
    with _Lock(paths["lock"]):
        leg = L.resolve_leg(leg_key)
        version = leg["version"]
        files = leg_files(home, leg_key, version)
        if ratio_fn is None:
            def ratio_fn(day):
                return price_ratio(nq_file, files["qqq_5m"], day)
        old_ack = _load_json(files["live_ack_path"])
        old_ack = old_ack if isinstance(old_ack, dict) else {}
        rejected = dict(old_ack.get("rejected") or {})
        last_processed = old_ack.get("last_processed") if isinstance(
            old_ack.get("last_processed"), dict) else None
        last_tid = _last_handled(old_ack, None)
        alerts = [a for a in old_ack.get("alerts") or [] if isinstance(a, dict)]
        live = None
        ledger_error = None
        for _round in range(max_rounds):
            names = sorted(os.listdir(paths["inbox"]))
            if not names:
                break
            trades = []
            for n in names:
                src = os.path.join(paths["inbox"], n)
                try:
                    if not os.path.isfile(src):
                        raise TradeError("not a file")
                    trades.append((n, src, read_trade(src, leg_key)))
                except TradeError as e:
                    res = {"file": n, "trade_id": None, "status": "rejected",
                           "reason": f"bad trade file: {e}", "processed_at": _now_iso()}
                    log(f"REJECTED {n}: {res['reason']}")
                    _reject_record(paths, n, res)
                    _move(src, paths["rejected"], log=log)
                    results.append(res)
            trades.sort(key=lambda x: _order_key(x[2]))
            xrows = None
            for n, src, tr in trades:
                tid = tr["trade_id"]
                res = {"file": n, "trade_id": tid, "status": "rejected", "reason": None,
                       "n_before": None, "alert": False, "processed_at": _now_iso()}
                resent = tid in rejected
                try:
                    if ledger_error is not None:
                        raise ledger_error
                    if live is None and os.path.exists(files["live_path"]):
                        live = _load_joblib(files["live_path"])
                        if live is None:
                            raise ValueError("the live state file exists but cannot be read -- "
                                             "refused (a live state is never re-cut over it)")
                        live, applied = _catch_up(live, files, log=log)
                        if applied:
                            for a in (cs.keel_live_meta(live) or {}).get("appended") or []:
                                rejected.pop(a.get("trade_id"), None)
                        last_tid = _last_handled(old_ack if not applied else {},
                                                 cs.keel_live_meta(live))
                    meta = cs.keel_live_meta(live) if live is not None else None
                    if live is not None and meta is None:
                        raise ValueError("the live state has no live record (not written by this "
                                         "handler)")
                    if meta is not None and any(a.get("trade_id") == tid
                                                for a in meta.get("appended") or []):
                        res.update(status="noop", reason="already appended")
                    else:
                        if meta is not None:
                            through = (meta.get("cut") or {}).get("data_through")
                        else:
                            s = _load_json(files["summary_path"])
                            through = (s.get("data_through") or s.get("last_nq_session")) \
                                if isinstance(s, dict) else None
                        why = before_the_cut(tr, through, live_from)
                        if why:
                            raise ValueError(why)
                        n_now = int(live["n"]) if live is not None else None
                        why = None if resent else chain_problem(tr, last_tid, n_now)
                        if why:
                            raise ChainError(why)
                        if live is None:
                            live = make_cut(files, leg_key, version, tr["exit_ts"], _now_iso(),
                                            live_from=live_from)
                            _install_cut(files, live, log=log)
                        if xrows is None:
                            xrows = cs.read_keel_xrows(files["xrows_path"])
                        xrec = xrows.get(tid)
                        if xrec is None:
                            xrows = cs.read_keel_xrows(files["xrows_path"])   # written meanwhile?
                            xrec = xrows.get(tid)
                        if xrec is None:
                            raise ValueError("no entry record (x_row) for this trade in "
                                             f"{os.path.basename(files['xrows_path'])}")
                        ratio, rinfo = ratio_fn(_parse_ts(tr["entry_ts"]).date())
                        row = live_append_row(live, tr, xrec, ratio, rinfo, _now_iso())
                        res["n_before"] = row["n_before"]
                        # the log row FIRST (the decision), then prev, then the state: a run that
                        # dies in between is completed by the next run's catch-up
                        row = _append_log(files["appends_path"], row)
                        nxt = apply_append_row(live, row, _now_iso())
                        try:
                            _atomic_joblib(live, files["live_prev_path"])
                            _atomic_joblib(nxt, files["live_path"])
                        except Exception as e:
                            raise ValueError(f"the live state was not written ({type(e).__name__}: "
                                             f"{e}); the append log holds the trade -- the next "
                                             f"run applies it")
                        live = nxt
                        rejected.pop(tid, None)
                        res.update(status="appended", n=int(live["n"]), P=row["P"],
                                   ratio=row["ratio"], pnl_source=tr.get("pnl_source"))
                except Exception as e:      # never leave the file in the inbox (the trigger loops)
                    res.update(status="rejected",
                               reason=(str(e) if isinstance(e, ValueError)
                                       else f"handler error: {type(e).__name__}: {e}"))
                    if isinstance(e, LedgerError):
                        ledger_error = e
                    if isinstance(e, (ChainError, LedgerError)):
                        res["alert"] = True
                        alerts.append({"kind": "chain" if isinstance(e, ChainError) else "ledger",
                                       "trade_id": tid, "at": res["processed_at"],
                                       "reason": res["reason"]})
                    if res["n_before"] is None and live is not None:
                        res["n_before"] = int(live["n"])
                ok = res["status"] in ("appended", "noop")
                if res["status"] != "noop" and not resent:
                    last_tid = tid
                    last_processed = {"trade_id": tid, "exit_ts": tr["exit_ts"],
                                      "status": res["status"], "at": res["processed_at"]}
                if not ok:
                    rejected[tid] = res["reason"]
                    _reject_record(paths, n, res)
                _move(src, paths["done"] if ok else paths["rejected"], log=log)
                _write_ack(files, live, rejected, res, last_processed, alerts, log=log)
                log(_result_line(res))
                results.append(res)
        _prune(paths["done"])
        _prune(paths["rejected"])
    return results


def make_live_cut(home, leg_key=LEG_KEY, live_from=None, log=_log):
    """--cut: make the cut NOW from the current nightly (the hand step right after the nightly the
    cut must copy). Refused once a live state exists (never re-cut). Returns {status, ...}."""
    from api import cloud_signal as cs
    from tools import keel_live_state as L
    paths = inbox_paths(home)
    with _Lock(paths["lock"]):
        version = L.resolve_leg(leg_key)["version"]
        files = leg_files(home, leg_key, version)
        if os.path.exists(files["live_path"]):
            log(f"no cut: a live state already exists ({files['live_path']}) -- never re-cut")
            return {"status": "exists"}
        try:
            live = make_cut(files, leg_key, version, None, _now_iso(), live_from=live_from)
            _install_cut(files, live, log=log)
        except Exception as e:
            log(f"no cut: {type(e).__name__}: {e}")
            return {"status": "refused", "reason": str(e)}
        old = _load_json(files["live_ack_path"])
        old = old if isinstance(old, dict) else {}
        _write_ack(files, live, dict(old.get("rejected") or {}), {"status": "cut"},
                   old.get("last_processed"), old.get("alerts"), log=log)
        return {"status": "cut", "cut": cs.keel_live_meta(live)["cut"]}


def _result_line(res):
    s = str(res.get("status") or "?").upper()
    head = f"{s} {res.get('trade_id') or res.get('file')}"
    if res.get("status") == "appended":
        return (f"{head}: n={res.get('n')} P={res.get('P'):.6f} (ratio {res.get('ratio'):.4f}, "
                f"{res.get('pnl_source')})")
    return f"{head}: {res.get('reason')}" + (" [ALERT]" if res.get("alert") else "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None, help="EDGELOG_HOME (default: the env var, as "
                    "api/cloud_signal.edgelog_home)")
    ap.add_argument("--nq-file", default=None, help="the box's NQ 5m RTH master, for the NQ/QQQ "
                    "price ratio (default: <home>/nq/NOADJ_NQ_5m_RTH.csv)")
    ap.add_argument("--leg", default=LEG_KEY)
    ap.add_argument("--cut", action="store_true", help="make the cut now from the current nightly "
                    "(refused once a live state exists)")
    ap.add_argument("--verify", action="store_true", help="check live state == cut + append log "
                    "replay (exit 1 when not)")
    a = ap.parse_args(argv)
    from api import cloud_signal as cs
    home = a.home or cs.edgelog_home()
    if a.verify:
        return 0 if verify_live_state(home, a.leg)["ok"] else 1
    if a.cut:
        return 0 if make_live_cut(home, a.leg)["status"] == "cut" else 1
    nq_file = a.nq_file or os.path.join(home, "nq", MASTER_NAME)
    if not os.path.exists(nq_file):
        _log(f"NQ master not found: {nq_file} -- every trade will be refused (no price ratio)")
    process_inbox(home, nq_file, a.leg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
