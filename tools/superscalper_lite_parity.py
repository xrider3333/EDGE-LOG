# SUPERSCALPER LITE PARITY (MANAGER #165): the memory-light port MISC_SUPERSCALPER_LITE_1_0 against the PINNED port
# MISC_SUPERSCALPER_1_0 (LF sha256 b8ef032f...), trade for trade, every number identical, on PRE-WF rows only
# (NQ 1m ETH no-adjust master id 34, bars before 2016-07-01; the walk-forward window and the lockbox are never read).
#   python tools/superscalper_lite_parity.py parity [--configs N] [--chunks 50000,7919] [--periods 2010H2,2013,...]
#   python tools/superscalper_lite_parity.py peak --port lite|pin --period 2015 [--chunk 50000]
# parity: for each config x period, runs the pinned port once and the lite port at each chunk size; compares every
# trade_detail field bit for bit (floats by float.hex) plus the run summary. Exit 1 on any mismatch.
# peak: one run in a fresh process, prints the peak working set (Windows peak_wset) and bytes per bar.
import argparse, hashlib, json, os, random, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_ROOT = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"          # the live engine + data registry (shared checkout)
PIN = os.path.join(ENGINE_ROOT, "augur_strategies", "MISC_SUPERSCALPER_1_0.py")
PIN_LF_SHA = "b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1"
LITE = os.path.join(HERE, "..", "augur_strategies", "MISC_SUPERSCALPER_LITE_1_0.py")
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\lite_parity.json"
VALIDATE_FIRST_DAY = "2016-07-01"
PERIODS = {"2010H2": ("2010-06-06", "2010-12-31"), "2011": ("2011-01-01", "2011-12-31"),
           "2012": ("2012-01-01", "2012-12-31"), "2013": ("2013-01-01", "2013-12-31"),
           "2014": ("2014-01-01", "2014-12-31"), "2015": ("2015-01-01", "2015-12-31"),
           "2016H1": ("2016-01-01", "2016-06-30")}
MECH = dict(intrabar="worst", close_rule="fifo", _detail=True)    # the validate's pinned mechanics
TARGETED = [
    dict(bos_len=5, sweep_len=30, hvb_lookback=75, hvb_bins=22, ob_lookback=30, adx_min=12, pyramiding=30),
    dict(bos_len=15, sweep_len=10, hvb_lookback=25, hvb_bins=8, ob_lookback=10, adx_min=38, pyramiding=1,
         sl_cap_atr="3.0", max_hold_bars=240, be_trigger=0.0, vix_feed="none", session_filter="rth"),
    dict(longs_enabled=False, eth_enabled=False, use_orb=False, use_fvg=False, use_ote=False, use_bos=False,
         use_sweep=False, use_od=False, use_ob=False, use_ob_trade=False, show_qqq_levels=False, show_orb_mid=False,
         show_on_range=False, session_filter="outside_rth", qqq_increment="10.0"),
]


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def lattice_draw(params, rng):
    """One random point on every searchable knob's lattice (single-option mechanics stay pinned)."""
    out = {}
    for k, meta in params.items():
        t = meta.get("type")
        if meta.get("options") is not None:
            if len(meta["options"]) > 1:
                out[k] = rng.choice(list(meta["options"]))
        elif t == "bool":
            out[k] = rng.random() < 0.5
        elif t == "int":
            step = int(meta.get("step") or 1)
            out[k] = rng.randrange(int(meta["min"]), int(meta["max"]) + 1, step)
        elif t == "float":
            steps = int(round((meta["max"] - meta["min"]) / meta["step"]))
            out[k] = round(meta["min"] + meta["step"] * rng.randint(0, steps), 10)
    return out


def setup():
    sys.path.insert(0, ENGINE_ROOT)
    sys.dont_write_bytecode = True
    from augur_engine.engine import run_backtest
    from augur_engine.data import find_master, load_master_arrays
    m = find_master("NQ", "1m", "eth", "db_noadj_eth")
    if not m or (int(m.get("id") or 0), m.get("filename")) != (34, "NOADJ_NQ_1m_ETH.csv"):
        sys.exit("refused: NQ master is not id 34 NOADJ_NQ_1m_ETH.csv: %r" % (m,))
    return run_backtest, m, load_master_arrays


def load(m, loader, period):
    d0, d1 = PERIODS[period]
    if d1 >= VALIDATE_FIRST_DAY:
        sys.exit("refused: period %s reaches the walk-forward window" % period)
    a = loader(m, date_from=d0, date_to=d1)
    return a


def trades_key(r):
    rows = (r or {}).get("trade_detail") or []
    out = []
    for x in rows:
        out.append(tuple((k, float(v).hex() if isinstance(v, float) else v) for k, v in sorted(x.items())))
    summ = {k: (float(v).hex() if isinstance(v, float) else v) for k, v in (r or {}).items()
            if k not in ("trade_detail", "trades")}
    return out, summ


def first_diff(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, dict(x), dict(y)
    return min(len(a), len(b)), (dict(a[len(b)]) if len(a) > len(b) else None), (dict(b[len(a)]) if len(b) > len(a) else None)


def cmd_parity(args):
    if lf_sha(PIN) != PIN_LF_SHA:
        sys.exit("refused: pinned port is not LF %s" % PIN_LF_SHA)
    run_bt, m, loader = setup()
    import importlib.util
    spec = importlib.util.spec_from_file_location("ss_pin_params", PIN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = random.Random(20261020)
    configs = [("defaults", {})] + [("targeted%d" % i, c) for i, c in enumerate(TARGETED)]
    configs += [("random%02d" % i, lattice_draw(mod.DEFAULT_PARAMS, rng)) for i in range(args.configs)]
    chunks = [int(x) for x in args.chunks.split(",")]
    periods = args.periods.split(",")
    lite_sha = lf_sha(LITE)
    print("pinned LF %s OK; lite LF %s; %d configs x %d periods x chunks %s" % (PIN_LF_SHA[:12], lite_sha[:12],
          len(configs), len(periods), chunks), flush=True)
    rows, bad = [], 0
    for period in periods:
        a = load(m, loader, period)
        for name, cfg in configs:
            if args.only and name not in args.only.split(","):
                continue
            params = dict(cfg, **MECH)
            t0 = time.time()
            rp = run_bt(PIN, arrays=a, master=m, params=params, cost_pts=0.0, return_trades=True)
            tp = time.time() - t0
            kp, sp = trades_key(rp)
            for cb in chunks:
                t0 = time.time()
                rl = run_bt(LITE, arrays=a, master=m, params=dict(params, _chunk_bars=cb), cost_pts=0.0,
                            return_trades=True)
                tl = time.time() - t0
                kl, sl = trades_key(rl)
                ok = (kp == kl) and (sp == sl)
                row = dict(period=period, config=name, chunk=cb, ok=ok, trades=len(kp), bars=len(a["close"]),
                           sec_pin=round(tp, 1), sec_lite=round(tl, 1))
                if not ok:
                    bad += 1
                    i, x, y = first_diff(kp, kl)
                    row.update(first_diff_trade=i, pin=x, lite=y, summary_pin=sp, summary_lite=sl, cfg=cfg)
                rows.append(row)
                print("  %-7s %-10s chunk %6d  %s  trades %5d  pin %5.1fs lite %5.1fs" % (
                    period, name, cb, "IDENTICAL" if ok else "MISMATCH", len(kp), tp, tl), flush=True)
        del a
    res = dict(pin_lf=PIN_LF_SHA, lite_lf=lite_sha, configs=dict(configs), rows=rows, mismatches=bad,
               verdict="IDENTICAL" if bad == 0 else "MISMATCH")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print("VERDICT", res["verdict"], "- %d of %d runs identical" % (len(rows) - bad, len(rows)), flush=True)
    sys.exit(0 if bad == 0 else 1)


def cmd_peak_child(args):
    import psutil
    run_bt, m, loader = setup()
    a = load(m, loader, args.period)
    port = LITE if args.port == "lite" else PIN
    params = dict(MECH)
    if args.port == "lite":
        params["_chunk_bars"] = args.chunk
    base = psutil.Process().memory_info()
    t0 = time.time()
    r = run_bt(port, arrays=a, master=m, params=params, cost_pts=0.0, return_trades=True)
    mi = psutil.Process().memory_info()
    n = len(a["close"])
    print(json.dumps(dict(port=args.port, period=args.period, bars=n, trades=(r or {}).get("num_trades"),
                          base_gb=round(base.rss / 2 ** 30, 3), peak_gb=round(mi.peak_wset / 2 ** 30, 3),
                          run_bytes_per_bar=round((mi.peak_wset - base.rss) / n), sec=round(time.time() - t0, 1))))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parity")
    p.add_argument("--configs", type=int, default=12)
    p.add_argument("--chunks", default="50000,7919")
    p.add_argument("--periods", default=",".join(PERIODS))
    p.add_argument("--only", default="")
    q = sub.add_parser("peak")
    q.add_argument("--port", choices=["lite", "pin"], required=True)
    q.add_argument("--period", default="2015")
    q.add_argument("--chunk", type=int, default=50000)
    q.add_argument("--child", action="store_true")
    args = ap.parse_args()
    if args.cmd == "parity":
        cmd_parity(args)
    elif args.child:
        cmd_peak_child(args)
    else:                                   # a fresh process, so the peak is this run's own
        cmd = [sys.executable, "-u", os.path.abspath(__file__), "peak", "--port", args.port, "--period", args.period,
               "--chunk", str(args.chunk), "--child"]
        sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
