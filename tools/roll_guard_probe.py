"""ROLL GUARD PROBE - what the engine roll guard does to a saved run (MANAGER #54 / #58, 2026-10-08).

For each run spec it prints, side by side:
  * RAW     - the file on the unadjusted master as before the guard's plan (raw prices, the true
              seam calendar, crossings counted not refused: roll_treatment "raw" in report mode);
  * PLANNED - the same run through the guarded engine: the signal method it gets (difference /
              ratio / raw, declared or by test), fills and P&L at raw contract prices with the roll
              step out, or the plain refusal it now meets;
plus the roll stamp and TTM's raw-vs-adjusted trade diff. This is the input DISC's restatement of the
22 pre-guard runs uses (#424 first). Nothing is written anywhere but stdout / --out.

Usage
  python tools/roll_guard_probe.py --strategy TTIBS_1_0.py --instrument NQ --source db_noadj_rth \
      --date-from 2016-07-01 --date-to 2025-06-29 --params "{}" --cost 0.533
  python tools/roll_guard_probe.py --runs runs.json [--out probe.jsonl]
runs.json = a list of {"id", "strategy", "instrument", "timeframe", "session", "source",
"date_from", "date_to", "params", "cost_pts"} (timeframe "5m" and session "rth" by default).
Run it from a checkout that has the masters (augur_uploads/), or pass --data-root.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)


def _num(x):
    try:
        return round(float(x), 3)
    except (TypeError, ValueError):
        return None


def probe(spec, ae, D, R):
    inst = spec.get("instrument", "NQ")
    tf = spec.get("timeframe", "5m")
    sess = spec.get("session", "rth")
    src = spec.get("source")
    master = D.find_master(inst, tf, sess, src)
    if master is None:
        return dict(id=spec.get("id"), error="no master for %s %s %s %s" % (inst, tf, sess, src))
    kw = dict(master=master, params=dict(spec.get("params") or {}),
              cost_pts=float(spec.get("cost_pts") or 0.0),
              date_from=spec.get("date_from") or None, date_to=spec.get("date_to") or None)
    out = dict(id=spec.get("id"), strategy=spec.get("strategy"), master=master.get("name"))
    with R.guard_mode("report"):
        raw = ae.run_backtest(spec["strategy"], **dict(kw, params=dict(kw["params"], roll_treatment="raw")))
    out["raw"] = dict(trades=raw.get("num_trades"), pnl_pts=_num(raw.get("total_pnl")),
                      max_dd_pts=_num(raw.get("max_drawdown")),
                      crossing=((raw.get("_meta") or {}).get("roll_stamp") or {}).get("trades_crossing"),
                      usd_roll_step=_num(((raw.get("_meta") or {}).get("roll_stamp") or {}).get("usd_roll_step")))
    try:
        pl = ae.run_backtest(spec["strategy"], roll_diff=True, **kw)
        st = (pl.get("_meta") or {}).get("roll_stamp") or {}
        out["planned"] = dict(trades=pl.get("num_trades"), pnl_pts=_num(pl.get("total_pnl")),
                              max_dd_pts=_num(pl.get("max_drawdown")), calendar=st.get("calendar"),
                              signal_method=st.get("signal_method"), method_source=st.get("method_source"),
                              method_tests=st.get("method_tests"), warning=st.get("warning"))
        out["stamp"] = st
    except R.RollGuardError as e:
        out["planned"] = dict(refused=str(e))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs")
    ap.add_argument("--strategy")
    ap.add_argument("--instrument", default="NQ")
    ap.add_argument("--timeframe", default="5m")
    ap.add_argument("--session", default="rth")
    ap.add_argument("--source", default="db_noadj_rth")
    ap.add_argument("--date-from")
    ap.add_argument("--date-to")
    ap.add_argument("--params", default="{}")
    ap.add_argument("--cost", type=float, default=0.0)
    ap.add_argument("--data-root", help="checkout whose augur_uploads/ and optimizer_history.db to read")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    os.environ.setdefault("AUGUR_TRIAL_CACHE", "0")
    import augur_engine as ae
    import augur_engine.data as D
    from augur_engine import rolls as R
    if a.data_root:
        D.UPLOADS = os.path.join(a.data_root, "augur_uploads")
        D.DB_PATH = os.path.join(a.data_root, "optimizer_history.db")
    if a.runs:
        with open(a.runs, encoding="utf-8") as fh:
            specs = json.load(fh)
    elif a.strategy:
        specs = [dict(id="cli", strategy=a.strategy, instrument=a.instrument, timeframe=a.timeframe,
                      session=a.session, source=a.source, date_from=a.date_from, date_to=a.date_to,
                      params=json.loads(a.params), cost_pts=a.cost)]
    else:
        ap.error("give --runs or --strategy")
    fh = open(a.out, "w", encoding="utf-8") if a.out else None
    for s in specs:
        try:
            row = probe(s, ae, D, R)
        except Exception as e:
            row = dict(id=s.get("id"), error="%s: %s" % (type(e).__name__, str(e)[:400]))
        line = json.dumps(row, default=str)
        print(line, flush=True)
        if fh:
            fh.write(line + "\n")
    if fh:
        fh.close()


if __name__ == "__main__":
    main()
