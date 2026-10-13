"""Q40 FAMILY LUCK BAR - the report (MANAGER #142 (c)) under the FROZEN rule bookq/RULE_family_luck_bar_FINAL.txt (witness
prereg/frontier-luckbar-1010 = 4944865c, LF d548ef10...). Eight runs: #463's four crowns (ORB #234, ENGU-Q #335, TTM #459, NOISE #422) and
the board leaders (ORB #314, NOISE #304, NOISE #382, DIP #424). For each: the engine's own Deflated Sharpe with n_cfg replaced by
E_run = rho x n_cfg and E_fam = rho x N_fam (with / without ancestors), the raw-count DSR beside it; rho from Q39 (luckbar/q39_rho.json).
    python q40_luck_bar.py run"""
import hashlib
import json
import math
import os
import sys

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
RULE = os.path.join(BQ, "RULE_family_luck_bar_FINAL.txt")
RULE_SHA = "d548ef10ea90200b658a2eb7d28b37489c345098232a65ae3b1c7c28554df615"
RHO = r"C:\EdgeLog\_anatomy_cache\luckbar\q39_rho.json"
SUMMARY = r"C:\EdgeLog\_anatomy_cache\luckbar\runs_summary.csv"
DOC_DIRS = (r"C:\EdgeLog\_anatomy_cache\runs", r"C:\EdgeLog\_anatomy_cache\luckbar\runs")
OUT = r"C:\EdgeLog\_anatomy_cache\luckbar"
RUNS = [(234, "ORB", "#463 crown"), (335, "ENGU-Q", "#463 crown"), (459, "TTM", "#463 crown"), (422, "NOISE", "#463 crown"),
        (314, "ORB", "board leader"), (304, "NOISE", "board leader"), (382, "NOISE", "board leader"), (424, "DIP", "board leader")]
GAMMA = 0.5772156649015329
PARITY_TOL = 0.001
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def load_doc(n):
    for d0 in DOC_DIRS:
        p = os.path.join(d0, f"{n}.json")
        if os.path.exists(p):
            return json.load(open(p, encoding="utf-8"))
    return None


def run():
    sys.path.insert(0, REPO)
    os.chdir(REPO)
    import pandas as pd
    from scipy.stats import norm
    from augur_engine.analytics import annualized_sr, deflated_sharpe
    from augur_engine.data import find_master, load_master_arrays
    from augur_engine.engine import run_backtest
    pins = {"rule": lf(RULE), "rho": sha(RHO), "summary": sha(SUMMARY)}
    print(f"PINS: rule LF {pins['rule']}; script LF {lf(__file__)}; q39_rho.json {pins['rho']}; runs_summary.csv {pins['summary']}", flush=True)
    if pins["rule"] != RULE_SHA:
        raise SystemExit("refused: the rule text is not the frozen one (nothing computed)")
    K = lambda n: (1 - GAMMA) * norm.ppf(1 - 1.0 / n) + GAMMA * norm.ppf(1 - 1.0 / (n * math.e))
    R = json.load(open(RHO))["families"]
    rho = {f: float(v["rho"]) for f, v in R.items()}
    rho_max = max(rho.values())
    print("rho (Q39): " + ", ".join(f"{f} {v:.3f}" for f, v in rho.items()) + f"; unmeasured families take {rho_max:.3f}", flush=True)
    S = pd.read_csv(SUMMARY)
    S["lin"] = S["lin"].replace({"NQDIP": "DIP", "ETFDIP": "DIP"})
    S["ancestor"] = S["ancestor"].astype(bool)
    out = {"rule_sha256_lf": pins["rule"], "pins": pins, "rho": rho, "runs": {}}
    for n, fam, role in RUNS:
        d = load_doc(n)
        r = {"family": fam, "role": role}
        st = (d or {}).get("dsr")
        if not isinstance(st, dict) or not st.get("n_cfg"):
            r["verdict"] = "no stored DSR (a one-config run) - not scored"
            print(f"#{n} {fam} ({role}): {r['verdict']}", flush=True)
            out["runs"][n] = r
            continue
        n_cfg, sdv = int(st["n_cfg"]), float(st["luck_bar"]) / K(int(st["n_cfg"]))
        bp = d["best_params"]
        bp = json.loads(bp.replace("'", '"').replace("True", "true").replace("False", "false")) if isinstance(bp, str) else bp
        src = str(d.get("data_source") or "")
        m = find_master(d["instrument"], d["timeframe"], "eth" if src.endswith("_eth") else "rth", d.get("data_source"))
        w_end = (((d.get("validate") or {}).get("windows") or {}).get("optimize") or [None, None])[1]
        arr = load_master_arrays(m, date_from=d.get("date_from"), date_to=w_end)
        try:                                                          # POST-RUN FIX 10-12 (disclosed): a refused rebuild = not reproducible
            bt = run_backtest(d["strategy"], arrays=arr, params=bp, cost_pts=0.0, return_trades=True)
        except Exception as e:
            r["verdict"] = "not reproducible - not scored (the rebuild is refused today: %s: %s)" % (type(e).__name__, str(e)[:160])
            print(f"#{n} {fam} ({role}): {r['verdict']}", flush=True)
            out["runs"][n] = r
            continue
        pn = [float(t[2]) - float(d.get("cost_pts") or 0.0) for t in bt["trades"]]
        ix = arr["index"]
        yrs = max(0.1, (ix[-1] - ix[0]).days / 365.25)
        w = dict(annualized_sr(pn, yrs), sr=float(st["winner_sharpe"]))
        a = math.sqrt(15.0 * sdv ** 2 / 16.0)
        samp = [-a, a] * 8                                            # any sample whose variance (ddof 1) is the run's own V
        dsr = lambda N: deflated_sharpe(w, samp, max(2.0, float(N)), yrs)
        par = dsr(n_cfg)
        r.update({"run_strategy": d["strategy"], "master": m["filename"], "window": [d.get("date_from"), w_end], "n_cfg": n_cfg,
                  "winner_sharpe": w["sr"], "trades": w["n"], "years": yrs, "skew": w["skew"], "kurt": w["kurt"], "sd_sample_sr": sdv,
                  "stored_dsr": float(st["dsr"]), "rebuilt_dsr": par["dsr"]})
        if abs(par["dsr"] - float(st["dsr"])) > PARITY_TOL:
            r["verdict"] = "not reproducible - not scored (rebuilt %.4f vs stored %.4f)" % (par["dsr"], float(st["dsr"]))
            print(f"#{n} {fam} ({role}): {r['verdict']}", flush=True)
            out["runs"][n] = r
            continue
        rh = rho.get(fam, rho_max)
        x = S[(S["lin"] == fam) & (S["id"] <= n)]
        N_no, N_all = float(x[~x["ancestor"]]["n_valid"].sum()), float(x["n_valid"].sum())
        E = {"E_run": rh * n_cfg, "E_fam": rh * N_no, "E_fam_anc": rh * N_all, "raw_N_fam": N_no, "raw_N_fam_anc": N_all}
        D = {k: dsr(v) for k, v in E.items()}
        if D["E_fam"]["dsr"] >= 0.95:
            verdict = "beats the family luck bar"
        elif D["E_run"]["dsr"] >= 0.95:
            verdict = "beats its own run's luck bar, not the family's"
        else:
            verdict = "does not beat the luck bar"
        r.update({"rho": rh, "counts": E, "dsr": {k: v["dsr"] for k, v in D.items()}, "luck_bar": {k: v["luck_bar"] for k, v in D.items()},
                  "verdict": verdict, "harsh_with_ancestors": "beats" if D["E_fam_anc"]["dsr"] >= 0.95 else "does not beat"})
        print(f"#{n} {fam} ({role}; {d['strategy']}): Sharpe {w['sr']:.2f} a year, {w['n']} trades / {yrs:.1f} yrs; parity {par['dsr']:.4f} vs stored "
              f"{float(st['dsr']):.4f} at n_cfg {n_cfg}", flush=True)
        print(f"   rho {rh:.3f}: E_run {E['E_run']:,.1f} -> DSR {D['E_run']['dsr']:.3f} (bar {D['E_run']['luck_bar']:.2f}); E_fam {E['E_fam']:,.0f} -> "
              f"{D['E_fam']['dsr']:.3f} (bar {D['E_fam']['luck_bar']:.2f})" + (f"; with ancestors {E['E_fam_anc']:,.0f} -> {D['E_fam_anc']['dsr']:.3f}"
              if N_all != N_no else "") + f"; raw N_fam {N_no:,.0f} -> {D['raw_N_fam']['dsr']:.3f} (harsh bound) => {verdict.upper()}", flush=True)
        out["runs"][n] = r
    json.dump(out, open(os.path.join(OUT, "q40_luck_bar.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "q40_luck_bar.json"))


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    run()
