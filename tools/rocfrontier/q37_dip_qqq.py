"""Q37 DIP #424 UNDER THE WEBULL EXECUTOR ON QQQ PRINTS (MANAGER #141 item 2) - a REPORT, walk-forward only, per the pre-data note
bookq/PREDATA_Q37_DIP_QQQ.txt. DIP decides on the daily close and fills at the next 09:30 open (= the executor's rule), so the executor read
is the same file on QQQ prints. Both arms go through the KEEL decomposition's own decompose() (bookq/r28_keel_decomp_ref.py = witness
prereg/sb-keel-decomp-424 64b53458, LF 4b775ff5, unchanged): RAW, F (fixed at KEEL's mean size), KEEL v12, FT, LO, the Kim-Tse-Wald split,
the shuffle nulls. NQ = #424's PURE roll-restated list (parity with the published JSON first); QQQ = NQDIP_1_1.py at #424's parameters
with asset="ETF" on the QQQ 5m Alpaca master. Common window = [QQQ's first entry .. 2025-08-24). Power lines BEFORE any lead.
    python q37_dip_qqq.py run"""
import hashlib
import json
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
NOTE = os.path.join(BQ, "PREDATA_Q37_DIP_QQQ.txt")
NOTE_SHA = "c9eec4b4860591f3e34a242aeb07715661682cb7912b276ee9019e7a5e48a270"
R28_SHA = "4b775ff5e99e63cedbba7996cdb4ea05387f6b4e1d914ad5be60cfb225153dab"
PURE = r"C:\EdgeLog\_anatomy_cache\restate_roll\dip424_pure_trades.csv"
PURE_SHA = "ce5750975ed07ca935c4e602d037ddf8c95916f07ed44da874ad1c101a1e46e0"
QQQ5_SHA = "782dabdd7dd7d265c9a31626f03c6940cdaaf4d7511da95bf8a8efc41fba5a1d"
PUBLISHED = r"C:\EdgeLog\_anatomy_cache\rocfrontier\keel424\keel_decomp_424.json"
OUT = r"C:\EdgeLog\_anatomy_cache\q37"
WF0, WF1 = "2016-07-18", "2025-08-24"                                  # #424's own walk-forward (gate_validate.wf_range)
# DIP_424_PARAMS as PAPER-WB's shadow legs carry them (worktree wb-dip-shadow api/cloud_signal.py), cross-checked against #424's own doc
DIP_424_PARAMS = {"notional": 100000, "cost_pts_rt": 0.783, "cost_bps": 2.0,
                  "trend_len": 400, "rsi_len": 3, "rsi_thr": 45, "rsi_exit": 6,
                  "dbl_n": 5, "pb_ema": 10, "pb_hold": 30,
                  "cap_mult": 0.75, "cap_q": 0.35, "cap_hold": 5,
                  "ibs_thr": 0.25, "ibs_exit": 1.0, "ibs_hold": 10,
                  "streak_n": 0, "streak_hold": 4, "gap_atr": 0.0, "gap_hold": 1,
                  "use_rsi": True, "use_dbl": True, "use_pb": True, "use_cap": True,
                  "use_ibs": True, "use_streak": True, "use_gapdn": True}
import numpy as np
import pandas as pd

lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def run():
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "tools"))
    sys.path.insert(0, BQ)
    os.chdir(REPO)
    import r28_keel_decomp_ref as R28
    from augur_engine import ml_keel as ML
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    from power_line import power_line
    qm = find_master("QQQ", "5m", "rth", "alpaca_split_rth")
    qpath = os.path.join(REPO, "augur_uploads", qm["filename"])
    pins = {"note": lf(NOTE), "r28": lf(os.path.join(BQ, "r28_keel_decomp_ref.py")), "pure": sha(PURE), "qqq5m": sha(qpath)}
    print(f"PINS: note LF {pins['note']}; script LF {lf(__file__)}; r28 copy LF {pins['r28']}; PURE {pins['pure']}; QQQ 5m {qm['filename']} "
          f"{pins['qqq5m']}", flush=True)
    if (pins["note"], pins["r28"], pins["pure"], pins["qqq5m"]) != (NOTE_SHA, R28_SHA, PURE_SHA, QQQ5_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    os.makedirs(OUT, exist_ok=True)

    # #424's own doc (ONE Firestore read, by id): the master and window the KEEL walk ran on, and its champion parameters
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    d = firestore.client().collection("users").document(R28.UID).collection("runs").document("424").get().to_dict()
    print("Firestore reads: 1 (users/<uid>/runs/424)", flush=True)
    cands = [d.get("best_params"), ((d.get("validate") or {}).get("champion") or {}).get("params"), (d.get("validate") or {}).get("champion")]
    champ = next((c for c in cands if isinstance(c, dict) and sum(k in c for k in DIP_424_PARAMS) >= 10), {})
    diff = {k: (v, champ.get(k)) for k, v in DIP_424_PARAMS.items() if k in champ and champ.get(k) != v}
    n_chk = sum(k in champ for k in DIP_424_PARAMS)
    print(f"#424 {d['strategy']} {d['instrument']} {d['timeframe']} {d.get('date_from')}..{d.get('date_to')}; champion params checked on "
          f"{n_chk} keys, differences: {diff or 'none'}", flush=True)
    assert n_chk >= 10, "#424's champion parameters not found in its doc - look first"
    assert not diff, "PAPER-WB's DIP_424_PARAMS differ from #424's champion - look first"
    an = load_master_arrays(find_master(d["instrument"], d["timeframe"], R28.SESSION[d["data_source"]], d["data_source"]),
                            date_from=d.get("date_from"), date_to=d.get("date_to"))
    T_nq = R28.load_list(PURE, an)

    SER = {}
    orig = R28.reading

    def reading(name, sizes, r, exit_day, days, s_bar=None):                       # the original, plus the daily $ series it builds
        SER[name] = pd.Series(R28.daily(np.asarray(sizes, float) * np.asarray(r, float), exit_day, days), index=days)
        return orig(name, sizes, r, exit_day, days, s_bar)
    R28.reading = reading

    # parity: #424's full walk-forward must reproduce the published decomposition
    pub = json.load(open(PUBLISHED))["PURE"]["readings"]
    par = R28.decompose(an, T_nq, WF0, WF1, ML)
    for k in ("RAW", "KEEL", "F"):
        a, b = par["readings"][k]["roc"], pub[k]["roc"]
        print(f"PARITY {k}: ROC@30k {a:.4f} vs published {b:.4f}", flush=True)
        assert abs(a - b) < 1e-6 * max(1.0, abs(b)), "parity failed - nothing further is read"
    SER.clear()

    # QQQ arm
    aq = load_master_arrays(qm)
    rq = run_backtest(d["strategy"], arrays=aq, params=dict(DIP_424_PARAMS, asset="ETF"), cost_pts=0.0, return_trades=True)
    T_q = sorted([(int(t[0]), int(t[1]), float(t[2])) for t in rq["trades"]], key=lambda t: t[0])
    wq = pd.DatetimeIndex(aq["index"]).tz_localize(None)
    c0 = str(wq[T_q[0][0]].date())
    print(f"QQQ arm: {len(T_q)} trades on {qm['filename']}; first entry {c0} -> common window [{c0} .. {WF1})", flush=True)
    resq = R28.decompose(aq, T_q, c0, WF1, ML)
    Sq = dict(SER); SER.clear()
    resn = R28.decompose(an, T_nq, c0, WF1, ML)
    Sn = dict(SER); SER.clear()
    yrs = (pd.Timestamp(WF1) - pd.Timestamp(c0)).days / 365.25

    def al(a, b):
        u = a.index.union(b.index)
        return a.reindex(u, fill_value=0.0).to_numpy(float), b.reindex(u, fill_value=0.0).to_numpy(float)
    PL = {}
    for nm, a, b in (("NQ RAW vs QQQ RAW", Sn["RAW"], Sq["RAW"]), ("QQQ KEEL vs QQQ F", Sq["KEEL v12 (today's walk)"], Sq["F fixed at s_bar"])):
        x, y = al(a, b)
        PL[nm] = power_line(x, y, yrs)
        print(f"POWER LINE {nm}: SD {PL[nm]['sd']:.2f}; 50% line {PL[nm]['line_5pct']:.2f}; 80% line {PL[nm]['line_80pct']:.2f} ROC points", flush=True)

    for arm, res in (("NQ (PURE)", resn), ("QQQ prints", resq)):
        R = res["readings"]
        print(f"{arm}: {res['n_wf']} trades in the window; KEEL mean size {res['s_bar']:.3f} (sd {res['s_sd']:.3f}), trust on {100 * res['trust_on_wf']:.0f}%")
        for k in ("RAW", "F", "KEEL", "FT", "LO"):
            r = R[k]
            print(f"   {r['name']:<26} ROC@30k {r['roc']:6.2f}  DD5 ${r['dd5']:>8,.0f}{' (ONE EPISODE)' if r['one_episode'] else '              '}  "
                  f"${r['usd_year']:>8,.0f}/yr  Sortino {r['sortino']:.2f}" + (f"  timing ${r['timing']:>9,.0f}" if r.get("timing") is not None else ""))
        s, nl = res["split"], res["nulls"]
        print(f"   split: KEEL - RAW ${s['keel_minus_raw']:,.0f} = leverage ${s['leverage']:,.0f} + timing ${s['timing']:,.0f} (FT ${s['timing_ft']:,.0f}, "
              f"LO ${s['timing_lo']:,.0f}); timing percentile in its shuffle null {nl['KEEL']['plain_pct']:.1f} (blocks {nl['KEEL']['block_pct']:.1f}); "
              f"FT {nl['FT']['plain_pct']:.1f}, LO {nl['LO']['plain_pct']:.1f}")
    Rn, Rq = resn["readings"], resq["readings"]
    keeps = Rq["RAW"]["usd_year"] / Rn["RAW"]["usd_year"]
    de = Rq["RAW"]["roc"] - Rn["RAW"]["roc"]
    le = PL["NQ RAW vs QQQ RAW"]["line_5pct"]
    v1 = (f"EDGE: on QQQ prints DIP keeps {100 * keeps:.0f}% of its NQ $ a year at the same notional; ROC@30k {Rq['RAW']['roc']:.2f} vs NQ "
          f"{Rn['RAW']['roc']:.2f} ({de:+.2f} against a line of {le:.2f}): " +
          ("not distinguishable at this resolution" if abs(de) < le else ("QQQ costs DIP" if de < 0 else "QQQ beats NQ")))
    dk = Rq["KEEL"]["roc"] - Rq["F"]["roc"]
    lk = PL["QQQ KEEL vs QQQ F"]["line_5pct"]
    v2 = (f"SIZING on QQQ: KEEL {Rq['KEEL']['roc']:.2f} vs F {Rq['F']['roc']:.2f} ({dk:+.2f} against a line of {lk:.2f}) -> " +
          ("KEEL" if dk > lk else "fixed 1.245x") + f"; KEEL's timing ${resq['split']['timing']:,.0f} ({resq['nulls']['KEEL']['plain_pct']:.1f} pct of its null)")
    print("READ (pre-set wording):", v1, "|", v2)
    for k, S in (("NQ", Sn), ("QQQ", Sq)):
        by = S["RAW"].groupby(S["RAW"].index.year).sum()
        print(f"{k} RAW by calendar year: " + ", ".join(f"{int(y)} ${v:,.0f}" for y, v in by.items()))
    pd.DataFrame({f"{a} {k}": v for a, S in (("NQ", Sn), ("QQQ", Sq)) for k, v in S.items()}).fillna(0.0).to_csv(os.path.join(OUT, "q37_daily.csv"))
    json.dump({"pins": pins, "window": [c0, WF1], "parity": {k: [par["readings"][k]["roc"], pub[k]["roc"]] for k in ("RAW", "KEEL", "F")},
               "power": PL, "NQ": resn, "QQQ": resq, "reads": [v1, v2]},
              open(os.path.join(OUT, "q37_dip_qqq.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q37_dip_qqq.json"))


if __name__ == "__main__":
    run()
