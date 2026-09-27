"""tools/decide_at_close_replay.py -- replay proof for api/cloud_signal.py's decide_at_close
probe (WEBULL_PAPER_TODO.md item 16).

Runs one live leg bar by bar through the REAL live path -- cloud_signal.step(): the live
history window (leg_warmup_sessions + closed_arrays), the closed-bar cutoff, _diff_leg's
seed / stale / late rules and trade ids -- once with the leg's decide_at_close flag off
and once with it on, each in its own throwaway store (never the live ledger). Every
emitted ENTRY/EXIT is matched by trade id to the leg's FULL-HISTORY trade list (one
run_leg_trades call over every bar in the cache) and the report gives, per trade, how
long after the backtest's fill bar STARTED the engine emitted it (the close of the
newest bar it had seen at that tick), entries and exits separately, plus missed / extra
/ duplicate events and any side or exit-bar mismatch.

Reads a bar cache (epoch schema, like <EDGELOG_HOME>/ohlc/QQQ_5m.csv -- pass a COPY, e.g.
one scp'd from the box) and optionally tops it up from yfinance (--yf, network). Writes
only under --out. KEEL is dropped from the leg config: it changes a trade's size, never
when it is emitted, and its state lives on the box.

  python tools/decide_at_close_replay.py --cache <copy of QQQ_5m.csv> --leg NOISE_382 \
      --sessions 36 --out <scratch dir>
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pandas as pd                      # noqa: E402

import api.cloud_signal as cs            # noqa: E402

TICK_AFTER_CLOSE_SEC = 10   # the live loop ticks every 20 s; one tick per bar is all step() needs


def leg_cfg(leg_key, flag, legs=None):
    cfg = dict((legs or cs.CROWN_LEGS)[leg_key])
    cfg.pop("keel", None)
    cfg["decide_at_close"] = bool(flag)
    return cfg


def _exit_kind(arrays, t):
    """'open' (filled at the exit bar's open: queued at the previous close, or a gap
    through a stop), 'eod' (flattened at the session's last close), else 'intrabar'."""
    idx = arrays["index"]
    pos = idx.get_loc(pd.Timestamp(t["exit_time"]))
    if abs(float(arrays["open"][pos]) - t["exit_px"]) <= 1e-6 * abs(t["exit_px"]):
        return "open"
    last_of_day = pos == len(idx) - 1 or idx[pos + 1].date() != idx[pos].date()
    if last_of_day and abs(float(arrays["close"][pos]) - t["exit_px"]) <= 1e-6 * abs(t["exit_px"]):
        return "eod"
    return "intrabar"


def replay(epoch_df, leg_key, cfg, n_sessions, workdir):
    """-> dict(events=[...], trades={tid: trade}, state=leg_state, sessions=[dates])."""
    tf = cfg["timeframe"]
    tf_sec = cs.TIMEFRAME_SECONDS[tf]
    paths = cs._paths(home=workdir)
    os.makedirs(paths["ohlc_dir"], exist_ok=True)
    epoch_df.to_csv(os.path.join(paths["ohlc_dir"], f"QQQ_{tf}.csv"), index=False)

    arrays = cs.build_arrays(epoch_df)
    idx = arrays["index"]
    days = sorted(set(idx.date))
    sessions = days[-n_sessions:]
    bars = [ts for ts in idx if ts.date() in set(sessions)]

    full = cs.run_leg_trades(cfg, arrays, leg_key=leg_key)
    trades = {cs._entry_key(leg_key, t): t for t in full
              if pd.Timestamp(t["entry_time"]).date() in set(sessions)}

    legs = {leg_key: cfg}
    # seed tick: the newest closed bar is the session before the replay window
    first = bars[0].to_pydatetime()
    cs.step(now=first + pd.Timedelta(seconds=TICK_AFTER_CLOSE_SEC), legs=legs, paths=paths, fetch=False)
    events = []
    for b in bars:
        now = (b + pd.Timedelta(seconds=tf_sec + TICK_AFTER_CLOSE_SEC)).to_pydatetime()
        for e in cs.step(now=now, legs=legs, paths=paths, fetch=False):
            if e["event"] in ("ENTRY", "EXIT"):
                e = dict(e, emit_close=(b + pd.Timedelta(seconds=tf_sec)).isoformat())
                events.append(e)
    state = cs._load_state(paths)["legs"].get(leg_key, {})
    return {"events": events, "trades": trades, "state": state, "sessions": sessions,
            "arrays": arrays}


def score(run):
    """Per-trade lags and every mismatch between the replay's events and the full history."""
    trades, events, arrays = run["trades"], run["events"], run["arrays"]
    by = defaultdict(list)
    for e in events:
        by[(e["trade_id"], e["event"])].append(e)
    dup = {k: len(v) for k, v in by.items() if len(v) > 1}
    extra = sorted({e["trade_id"] for e in events if e["trade_id"] not in trades})
    rows, missed, side_bad, exit_bar_bad, pending_eod = [], [], [], [], []
    last_day = run["sessions"][-1]
    for tid, t in sorted(trades.items(), key=lambda kv: kv[1]["entry_time"]):
        ent = by.get((tid, "ENTRY"), [])
        ext = by.get((tid, "EXIT"), [])
        row = {"trade_id": tid, "side": t["side"], "entry_time": t["entry_time"],
               "exit_time": t["exit_time"], "exit_kind": _exit_kind(arrays, t) if t["exit_time"] else "open_at_end"}
        if t["exit_time"]:
            # 1 = exited on the bar right after its fill bar, i.e. decided ON the fill bar:
            # the one case the probe leaves to the normal path (see _decide_at_close_probe)
            row["exit_after_entry_bars"] = int(
                (pd.Timestamp(t["exit_time"]) - pd.Timestamp(t["entry_time"])).total_seconds()
                // (arrays["index"][1] - arrays["index"][0]).total_seconds())
        if not ent:
            missed.append(tid)
        else:
            e = ent[0]
            row["entry_emit_close"] = e["emit_close"]
            row["entry_lag_s"] = (pd.Timestamp(e["emit_close"]) - pd.Timestamp(t["entry_time"])).total_seconds()
            row["entry_ref_minus_fill"] = round(float(e["ref_price"]) - t["entry_px"], 4)
            row["entry_probe"] = "decide_at_close" in str(e.get("reason") or "")
            if e["side"] != t["side"]:
                side_bad.append(tid)
        if ext:
            e = ext[0]
            row["exit_emit_close"] = e["emit_close"]
            row["exit_lag_s"] = (pd.Timestamp(e["emit_close"]) - pd.Timestamp(t["exit_time"])).total_seconds()
            row["exit_ref_minus_fill"] = round(float(e["ref_price"]) - t["exit_px"], 4)
            row["exit_probe"] = "decide_at_close" in str(e.get("reason") or "")
            if e["ref_time"] != t["exit_time"]:
                exit_bar_bad.append(tid)
        elif ent and (row["exit_kind"] == "open_at_end" or (
                row["exit_kind"] == "eod" and pd.Timestamp(t["exit_time"]).date() == last_day)):
            pending_eod.append(tid)   # its EXIT would go out on the next session's first bar
        rows.append(row)

    def lag_hist(key, kind=None):
        c = Counter()
        for r in rows:
            if key in r and (kind is None or r["exit_kind"] == kind):
                c[str(int(r[key]))] += 1
        return dict(sorted(c.items(), key=lambda kv: float(kv[0])))

    exits_taken = [r for r in rows if "exit_lag_s" in r]
    return {
        "trades": len(trades), "entry_events": sum(1 for e in events if e["event"] == "ENTRY"),
        "exit_events": sum(1 for e in events if e["event"] == "EXIT"),
        "entry_lag_s": lag_hist("entry_lag_s"),
        "exit_lag_s_by_kind": {k: lag_hist("exit_lag_s", k) for k in ("open", "intrabar", "eod")},
        "probe_entries": sum(1 for r in rows if r.get("entry_probe")),
        "probe_exits": sum(1 for r in rows if r.get("exit_probe")),
        "missed_entries": missed, "extra_trade_ids": extra, "duplicates": dup,
        "side_mismatch": side_bad, "exit_bar_mismatch": exit_bar_bad,
        "exits_missing": [r["trade_id"] for r in rows if "entry_lag_s" in r and "exit_lag_s" not in r
                          and r["trade_id"] not in pending_eod],
        "eod_exit_pending_after_last_session": pending_eod,
        "exits_emitted": len(exits_taken),
        "late_skipped": run["state"].get("late_skipped", 0),
        "stale_skipped": run["state"].get("stale_skipped", 0),
        "rows": rows,
    }


def load_cache(path, use_yf=False):
    df = pd.read_csv(path)
    df = df[df["time"] > 10 ** 9]          # the cache has carried epoch-0 junk rows before
    if use_yf:
        import tools.qqq_paper as qp
        fresh = qp._to_epoch_frame(qp._fetch_yf("5m"))
        df = pd.concat([df, fresh], ignore_index=True).drop_duplicates("time", keep="first")
    return df.sort_values("time").reset_index(drop=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--cache", required=True, help="COPY of an epoch-schema QQQ_5m.csv")
    ap.add_argument("--leg", default="NOISE_382")
    ap.add_argument("--sessions", type=int, default=36)
    ap.add_argument("--yf", action="store_true", help="top up the cache from yfinance 5m (network)")
    ap.add_argument("--out", default=None, help="scratch output dir (default: a new temp dir)")
    a = ap.parse_args(argv)
    out = a.out or tempfile.mkdtemp(prefix="decide_at_close_replay_")
    os.makedirs(out, exist_ok=True)
    epoch_df = load_cache(a.cache, a.yf)
    report = {"leg": a.leg, "cache": os.path.abspath(a.cache), "yf": a.yf}
    for flag in (False, True):
        work = tempfile.mkdtemp(prefix="dac_store_", dir=out)
        try:
            run = replay(epoch_df, a.leg, leg_cfg(a.leg, flag), a.sessions, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        sc = score(run)
        report["sessions"] = [str(d) for d in run["sessions"]]
        report["flag_on" if flag else "flag_off"] = sc
        pd.DataFrame(sc["rows"]).to_csv(os.path.join(out, f"{a.leg}_{'on' if flag else 'off'}_trades.csv"),
                                        index=False)
    for k in ("flag_off", "flag_on"):
        report[k].pop("rows", None)
    with open(os.path.join(out, f"{a.leg}_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != "sessions"}, indent=2, default=str))
    print(f"sessions {report['sessions'][0]} .. {report['sessions'][-1]} ({len(report['sessions'])}); "
          f"written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
