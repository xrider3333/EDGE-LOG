# -*- coding: utf-8 -*-
"""NOISE LIVE-PATH MISTAKE HUNT (MANAGER #50 item 1, 2026-10-05): did the box emit every NOISE signal the engine would
take, on time, at the right size - and what did each miss cost?

Three views of the same sessions, all on the BOX'S OWN bar cache (a read-only copy):
  BOX      what the box actually emitted (cloud_signal/signals.csv for NOISE_382, shadow/signals.csv for #422)
  REPLAY   the live code path (api/cloud_signal.step, bar by bar, throwaway store) on today's copy of the cache -
           tools/decide_at_close_replay.replay, the leg's own decide_at_close setting, KEEL dropped (size only)
  ENGINE   the leg's full-history trade list on the same cache (run_leg_trades once over every bar)
BOX vs ENGINE is the hunt. REPLAY tells a code-path cause (the live window, seed / stale / late rules) from a data cause
(the box saw different bars at the time - feeds restate recent bars - or was down). Every mismatch is listed with a
dollar effect at the box's own share count: a missed or extra trade = the engine trade's P&L; a wrong exit bar or a
late entry = the price difference x shares x side. Then the Webull layer: each box ENTRY joined by trade id to the
qqq_exec trade ledger (filled, refused, or open), with fill slippage against the signal's reference price.

READ-ONLY on the box (scp copies, like tools/pull_box_ledgers.py). Writes only under --out. Changes nothing live.

  python tools/noise_live_parity.py --out <dir> [--since 2026-09-24] [--copy <dir with an existing copy>]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.environ.get("EDGELOG_REPO_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import pandas as pd                                                   # noqa: E402

import api.cloud_signal as cs                                         # noqa: E402
import decide_at_close_replay as R                                    # noqa: E402
import pull_box_ledgers as PB                                         # noqa: E402

FILES = ["ohlc/QQQ_5m.csv", "ohlc/QQQ_5m_backfill.csv", "ohlc/QQQ_1d.csv",
         "cloud_signal/signals.csv", "cloud_signal/shadow/signals.csv",
         "cloud_signal/state.json", "cloud_signal/shadow/state.json", "cloud_signal/heartbeat.json",
         "qqq_exec/trades.csv", "qqq_exec/orders.csv", "qqq_exec/broker_orders.csv", "qqq_exec/config.json"]
LEGS = (("NOISE_382", "live", "cloud_signal/signals.csv"),
        ("NOISE_422_PLAIN", "shadow", "cloud_signal/shadow/signals.csv"))
LATE_S = 60.0                                                         # an emit more than this after its decision close


def fetch(dest):
    got = {}
    for f in FILES:
        loc = os.path.join(dest, *f.split("/"))
        os.makedirs(os.path.dirname(loc), exist_ok=True)
        r = subprocess.run(["scp"] + PB.SSH_OPTS + ["%s:%s/%s" % (PB.HOST, PB.REMOTE_HOME, f), loc],
                           capture_output=True, text=True)
        got[f] = r.returncode == 0 and os.path.exists(loc)
    return got


def box_rows(path, leg, since):
    """The leg's ENTRY/EXIT rows emitted from `since`, and the leg's start: its last cold-start SEED at or after
    `since` (a leg that seeded later cannot have missed the trades before its seed)."""
    d = pd.read_csv(path, dtype=str).fillna("")
    d = d[d.leg == leg].copy()
    d["emitted"] = pd.to_datetime(d.emitted_at, utc=True)
    t0 = pd.Timestamp(since, tz="America/New_York")
    seeds = d[(d.event == "SEED") & (d.emitted >= t0)]
    start = seeds.emitted.max() if len(seeds) else t0
    d = d[d.event.isin(["ENTRY", "EXIT"]) & (d.emitted >= t0)]
    return d, start


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2026-09-24")
    ap.add_argument("--copy", default=None, help="use an existing copy instead of fetching")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    copy = a.copy or os.path.join(a.out, "box_copy")
    if not a.copy:
        got = fetch(copy)
        print("box copy -> %s: %s" % (copy, ", ".join("%s %s" % (k, "ok" if v else "MISSING") for k, v in got.items())))
    epoch = R.load_cache(os.path.join(copy, "ohlc", "QQQ_5m.csv"))
    ix = pd.to_datetime(epoch["time"], unit="s", utc=True).dt.tz_convert("America/New_York")
    sessions = sorted({t.date() for t in ix if t.date() >= pd.Timestamp(a.since).date()})
    print("bar cache: %d rows, %s .. %s; %d sessions from %s" % (len(epoch), ix.iloc[0], ix.iloc[-1], len(sessions),
                                                                  a.since))
    daily = os.path.join(copy, "ohlc", "QQQ_1d.csv")
    daily = daily if os.path.exists(daily) else None
    trades_csv = os.path.join(copy, "qqq_exec", "trades.csv")
    fills = pd.read_csv(trades_csv, dtype=str).fillna("") if os.path.exists(trades_csv) else pd.DataFrame()
    report = {"since": a.since, "sessions": [str(s) for s in sessions], "legs": {}}
    all_rows = []
    for leg, kind, sig in LEGS:
        legs = cs.CROWN_LEGS if kind == "live" else cs.SHADOW_LEGS
        cfg = R.leg_cfg(leg, legs[leg].get("decide_at_close", False), legs)
        work = tempfile.mkdtemp(prefix="nlp_%s_" % leg, dir=a.out)
        bf = os.path.join(copy, "ohlc", "QQQ_5m_backfill.csv")
        if os.path.exists(bf):
            os.makedirs(os.path.join(work, "ohlc"), exist_ok=True)
            shutil.copyfile(bf, os.path.join(work, "ohlc", "QQQ_5m_backfill.csv"))
        run = R.replay(epoch, leg, cfg, len(sessions), work, daily=daily)
        shutil.rmtree(work, ignore_errors=True)
        eng = run["trades"]                                           # trade id -> engine trade (window only)
        rep_ids = {e["trade_id"] for e in run["events"] if e["event"] == "ENTRY"}
        box, start = box_rows(os.path.join(copy, *sig.split("/")), leg, a.since)
        eng = {k: v for k, v in eng.items() if pd.Timestamp(v["entry_time"]) >= start}
        bent = {r.trade_id: r for r in box[box.event == "ENTRY"].itertuples()}
        bext = {r.trade_id: r for r in box[box.event == "EXIT"].itertuples()}
        sh = pd.to_numeric(box[box.event == "ENTRY"].shares, errors="coerce")
        sz = pd.to_numeric(box[box.event == "ENTRY"]["size"], errors="coerce").replace(0, float("nan"))
        unit = float((sh / sz).median()) if len(sh) else 10.0          # shares per unit of size on the box
        rows = []
        for tid, t in sorted(eng.items(), key=lambda kv: kv[1]["entry_time"]):
            sgn = 1.0 if str(t["side"]).lower().startswith("l") else -1.0
            pnl_ps = (float(t["exit_px"]) - float(t["entry_px"])) * sgn if t.get("exit_px") is not None else float("nan")
            r = {"leg": leg, "trade_id": tid, "side": t["side"], "engine_entry": t["entry_time"],
                 "engine_exit": t.get("exit_time"), "engine_size": float(t.get("size") or 1.0),
                 "engine_pnl_per_share": pnl_ps, "in_replay": tid in rep_ids, "box_entry": tid in bent}
            if tid in bent:
                b = bent[tid]
                shares = float(b.shares or 0)
                ks = float(b.keel_size or 1.0) if b.keel_size not in ("", None) else 1.0
                plug = float(b.size or 1.0) / (ks or 1.0) if leg == "NOISE_382" else float(b.size or 1.0)
                r.update(box_shares=shares, box_plugin_size=plug,
                         size_ok=abs(plug - r["engine_size"]) < 1e-6,
                         entry_px_diff=round((float(b.ref_price) - float(t["entry_px"])) * sgn, 4),
                         entry_lag_s=(pd.Timestamp(b.emitted_at) - pd.Timestamp(b.ref_time)).total_seconds() - 300.0)
                r["entry_cost_usd"] = round(r["entry_px_diff"] * shares, 2)
                if tid in bext:
                    e = bext[tid]
                    r["box_exit_bar"] = e.ref_time
                    r["exit_bar_ok"] = pd.Timestamp(e.ref_time) == pd.Timestamp(t["exit_time"]) if t.get("exit_time") else False
                    r["exit_px_diff"] = round((float(t["exit_px"]) - float(e.ref_price)) * sgn, 4) if t.get("exit_px") else float("nan")
                    r["exit_cost_usd"] = round(r["exit_px_diff"] * shares, 2) if t.get("exit_px") else float("nan")
                else:
                    r["box_exit_bar"] = ""
                    r["exit_bar_ok"] = False
                if len(fills) and "trade_id" in fills:
                    f = fills[fills.trade_id == tid]
                    r["webull"] = "filled" if len(f) else "no fill row"
                    if len(f):
                        r["webull_pnl"] = float(pd.to_numeric(f.pnl, errors="coerce").sum())
                        r["webull_shares"] = float(pd.to_numeric(f.shares, errors="coerce").sum())
            else:
                r["missed_cost_usd"] = round(pnl_ps * unit * r["engine_size"], 2) if pnl_ps == pnl_ps else float("nan")
            rows.append(r)
        extra = [tid for tid in bent if tid not in eng]
        for tid in extra:
            b = bent[tid]
            x = {"leg": leg, "trade_id": tid, "side": b.side, "box_entry": True, "engine_entry": "",
                 "in_replay": tid in rep_ids, "box_shares": float(b.shares or 0), "EXTRA": True}
            if len(fills) and "trade_id" in fills:
                f = fills[fills.trade_id == tid]
                x["webull"] = "filled" if len(f) else "no fill row"
                if len(f):
                    x["webull_pnl"] = float(pd.to_numeric(f.pnl, errors="coerce").sum())
                    x["webull_shares"] = float(pd.to_numeric(f.shares, errors="coerce").sum())
            rows.append(x)
        df = pd.DataFrame(rows)
        all_rows.append(df)
        missed = df[(~df.box_entry.astype(bool))]
        late = df[pd.to_numeric(df.get("entry_lag_s"), errors="coerce") > LATE_S] if "entry_lag_s" in df else df.iloc[0:0]
        badsize = df[df.get("size_ok", pd.Series(True, index=df.index)).eq(False)]
        badexit = df[df.box_entry.astype(bool) & df.get("exit_bar_ok", pd.Series(True, index=df.index)).eq(False)
                     & df.engine_exit.notna() & ~df.engine_exit.astype(str).isin(["", "None", "nan"])]
        rl = {"engine_trades": int(len(eng)), "replay_entries": len(rep_ids), "box_entries": len(bent),
              "missed": missed.trade_id.tolist(), "missed_in_replay_too": missed[missed.in_replay.astype(bool)].trade_id.tolist(),
              "missed_usd": float(pd.to_numeric(missed.get("missed_cost_usd"), errors="coerce").sum()) if len(missed) else 0.0,
              "extra": extra, "late": late.trade_id.tolist(), "wrong_size": badsize.trade_id.tolist(),
              "wrong_exit_bar": badexit.trade_id.tolist(),
              "entry_cost_usd": float(pd.to_numeric(df.get("entry_cost_usd"), errors="coerce").sum()),
              "exit_cost_usd": float(pd.to_numeric(df.get("exit_cost_usd"), errors="coerce").sum()),
              "shares_per_unit": unit}
        if kind == "live" and "webull" in df:
            rl["webull"] = df.webull.value_counts(dropna=True).to_dict()
        report["legs"][leg] = rl
        print("\n%s (%s): engine %d trades, replay %d entries, box %d entries" % (leg, kind, rl["engine_trades"],
                                                                              rl["replay_entries"], rl["box_entries"]))
        for k in ("missed", "missed_in_replay_too", "extra", "late", "wrong_size", "wrong_exit_bar"):
            print("  %-22s %d  %s" % (k, len(rl[k]), ", ".join(rl[k][:8])))
        print("  missed-trade $ %+.0f | entry price vs engine $ %+.0f | exit price vs engine $ %+.0f (+ = cost to the box)" % (
            rl["missed_usd"], rl["entry_cost_usd"], rl["exit_cost_usd"]))
        if "webull" in rl:
            print("  Webull layer: %s" % rl["webull"])
    pd.concat(all_rows, ignore_index=True).to_csv(os.path.join(a.out, "noise_live_parity_rows.csv"), index=False)
    json.dump(report, open(os.path.join(a.out, "noise_live_parity.json"), "w"), indent=1, default=str)
    print("\nrows -> %s" % os.path.join(a.out, "noise_live_parity_rows.csv"))


if __name__ == "__main__":
    main()
