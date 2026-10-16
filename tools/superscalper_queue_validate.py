"""AUTO-VALIDATE 900 - MISC_SUPERSCALPER (our port), owner 10-14 via MANAGER #116 / #119 / #122.

Prereg docs/PREREG_tv_superscalper_r1_2026-10-14.md (Amendments 1-5, witness branch
prereg/tv-superscalper-1014). The ranged port file MISC_SUPERSCALPER_1_0.py - never a pinned copy - with the defaults the
improvement round chose (or the as-ported ones), the exit / VIX knobs OPEN on their registered lattices, the script's knobs
on their ranges, the fill model and stand-in feeds pinned to one option. NQ 1-minute ETH no-adjust master pinned by filename
(NOADJ_NQ_1m_ETH.csv, id 34), window 2016-07-01 .. 2026-06-30 (12-month lockbox = the final year, read once by the validate
itself), cost 0.706 points a round trip (commission + 1 tick each side, owner rule), 900 trials (OWNER RULE, never lowered),
8 folds, warm 300 days (house default). Queued behind NOISE #422+TP (vAUrpEP13IanjkYuzGHN): the runner takes jobs oldest first.

Refuses unless: the port and the prereg are in the shared checkout with the expected LF sha256s; the master is id 34 /
NOADJ_NQ_1m_ETH.csv; every chosen default lies on its knob's lattice; the mechanics knobs offer one option; no live job
carries this label or the same file + window.
    python tools/superscalper_queue_validate.py --port-sha <LF sha256 of the shipped port> --dry
    python tools/superscalper_queue_validate.py --port-sha <...>
"""
import argparse
import datetime
import hashlib
import importlib.util
import os
import sys
import time

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
os.chdir(REPO)
sys.path.insert(0, REPO)
UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
TAG = "AUTO-VALIDATE 900 MISC_SUPERSCALPER (our port, owner 10-14)"
STRATEGY = "MISC_SUPERSCALPER_1_0.py"
PREREG = os.path.join("docs", "PREREG_tv_superscalper_r1_2026-10-14.md")
PREREG_LF_SHA = "b664af51afb85ffafb25aabae1ac775a69fc7aab5029fe84c2f3dda8639b0017"
NOISE_JOB = "vAUrpEP13IanjkYuzGHN"
LOGDIR = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper"
JOB = dict(
    type="validate", strategy=STRATEGY,
    instrument="NQ", timeframe="1m", session="eth", source="db_noadj_eth",
    commission_usd=0.0, slippage_pts=0.0, cost_pts=0.706, mult=20,
    date_from="2016-07-01", date_to="2026-06-30",
    lockbox_months=12, wf_folds=8, warm_days=300,
    n_trials=900, min_trades=30, mc_sims=2000, n_rounds=0, select_oos_topk=10,
    discover="auto", provider="ollama",
    dsr=True, neighbors=True, regime=True, pills=True, context=True, equity_points=400,
)
LATTICE = dict(sl_scale=(0.40, 1.20, 0.05), tp_scale=(1.0, 2.0, 0.25), max_hold_bars=(0, 240, 30), be_trigger=(0.0, 2.0, 0.5))
CATS = dict(sl_cap_atr=["off", "3.0"], vix_feed=["none", "daily"], session_filter=["all", "outside_rth", "rth"])
PINNED = ("intrabar", "close_rule", "spy_proxy", "footprint", "daily_close")


def lf_sha(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def on_lattice(v, lo, hi, step):
    if not (lo - 1e-9 <= v <= hi + 1e-9):
        return False
    k = round((v - lo) / step)
    return abs(lo + step * k - v) <= 1e-9


def note(dp):
    d = {k: dp[k]["default"] for k in list(LATTICE) + list(CATS)}
    return ("%s. MANAGER #116/#119/#122 (owner 10-14: 'either validate it or improve it'). OUR PORT of Crispigino's NQ/MNQ Super "
            "Scalper (TradingView PUB;46d5b263 v1.0) - NOT the published script: Stage 0 matched 52.7%% of its 273 published trades "
            "(bar 80%%) because it reads footprint, NYSE TICK and 1-minute VIX the house does not hold. Prereg %s (LF sha256 %s, "
            "Amendments 1-5, witness prereg/tv-superscalper-1014). Exit / VIX knobs ours (stop cap on the author's session stops, "
            "stop scale, target scale, max hold, breakeven, daily VIX stand-in, entry session), defaults %s chosen on the 2024 "
            "development year - and that pick DID NOT HOLD on 2023 (net PF 1.071 vs as-ported 1.073). 2023 and 2024 are both "
            "development years inside the walk-forward window: read the WF chain with their folds apart AND without them. "
            "SESSION READING RULE (NOISE, MANAGER #139): if the crown's session_filter is not 'all', print the per-fold "
            "session picks; picks that change fold to fold = noise, not a session edge. Dev hypothesis (MANAGER #143, r2b/r2c): "
            "2023 RTH carried the net (its first hour 09:30-10:29 = 93%% of RTH net), 2024 RTH lost and its first hour was flat - "
            "the walk-forward confirms a session edge only if the folds keep choosing RTH. PRE-SET VERDICT: per-fold session "
            "picks + WF four numbers; DEAD if WF ROC@30k < 15 or the WF gain is one episode. "
            "Fill model 'worst', "
            "stand-in feeds pinned. NQ 1m ETH no-adjust master id 34 NOADJ_NQ_1m_ETH.csv pinned, window %s..%s, 12-month lockbox, "
            "8 folds, warm 300 days, cost 0.706 pt, 900 trials (OWNER RULE). Reported: run number + ROC@30k, DD5, DD%% from peak, "
            "Sortino, WF and LB apart; PBO, DSR, win rate, avg win / loss. Priors (NOISE, STRATEGY-BEATING): 5-10%% that WF clears "
            "ROC 15. Nothing live or paper changes. Driver tools/superscalper_queue_validate.py."
            % (TAG, PREREG.replace(os.sep, "/"), PREREG_LF_SHA, d, JOB["date_from"], JOB["date_to"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port-sha", required=True, help="LF sha256 the shipped port must have")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    spath = os.path.join(REPO, "augur_strategies", STRATEGY)
    for need in (spath, os.path.join(REPO, PREREG)):
        if not os.path.exists(need):
            sys.exit("ABORT - not in the shared checkout, the runner would not see it: " + need)
    if lf_sha(os.path.join(REPO, PREREG)) != PREREG_LF_SHA:
        sys.exit("ABORT - the prereg on main is not the pinned one")
    got = lf_sha(spath)
    if got != a.port_sha:
        sys.exit("ABORT - port sha %s is not the expected %s" % (got, a.port_sha))
    print("prereg + port sha OK (%s)" % got)
    spec = importlib.util.spec_from_file_location("ss", spath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dp = mod.DEFAULT_PARAMS
    bad = []
    for k, (lo, hi, st) in LATTICE.items():
        s = dp[k]
        if (float(s["min"]), float(s["max"]), float(s["step"])) != (lo, hi, st):
            bad.append("%s fence %s..%s step %s, registered %s..%s step %s" % (k, s["min"], s["max"], s["step"], lo, hi, st))
        if not on_lattice(float(s["default"]), lo, hi, st):
            bad.append("%s default %s off its lattice" % (k, s["default"]))
    for k, opts in CATS.items():
        if dp[k]["options"] != opts or dp[k]["default"] not in opts:
            bad.append("%s options %s" % (k, dp[k]["options"]))
    for k in PINNED:
        if dp[k]["options"] != [dp[k]["default"]]:
            bad.append("%s is searchable: %s" % (k, dp[k]["options"]))
    if dp["intrabar"]["default"] != "worst":
        bad.append("intrabar default is not 'worst'")
    for k, s in dp.items():
        if s.get("type") in ("int", "float") and s.get("step") and not on_lattice(float(s["default"]), float(s["min"]),
                                                                                  float(s["max"]), float(s["step"])):
            bad.append("%s default %s off %s..%s step %s" % (k, s["default"], s["min"], s["max"], s["step"]))
    if bad:
        sys.exit("ABORT - knob check:\n  " + "\n  ".join(bad))
    print("knobs OK: defaults on their lattices, mechanics pinned;", {k: dp[k]["default"] for k in list(LATTICE) + list(CATS)})
    from augur_engine import data as D
    m = D.find_master("NQ", "1m", "eth", JOB["source"])
    if not m or m.get("filename") != "NOADJ_NQ_1m_ETH.csv" or int(m.get("id") or 0) != 34:
        sys.exit("ABORT - the NQ 1m ETH no-adjust master is not id 34 NOADJ_NQ_1m_ETH.csv: %r" % (m,))
    if str(m.get("date_to"))[:10] < JOB["date_to"]:
        sys.exit("ABORT - master ends %s, before the window end" % m.get("date_to"))
    vpath, vsha = mod._VIX_FILES["raw"][0], mod._VIX_FILES["raw"][1]
    if not os.path.exists(vpath) or hashlib.sha256(open(vpath, "rb").read()).hexdigest() != vsha:
        sys.exit("ABORT - the raw VIX photograph %s is missing or not its pinned sha %s" % (vpath, vsha))
    print("VIX file OK: %s" % vpath)
    print("master OK: id %s %s rows=%s %s..%s" % (m.get("id"), m.get("filename"), m.get("rows"), m.get("date_from"), m.get("date_to")))

    import firebase_admin
    from firebase_admin import credentials, firestore
    from google.api_core import exceptions as _gx
    from google.cloud.firestore_v1.base_query import FieldFilter as _FF
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(os.path.join(REPO, "serviceAccount.json")))
    u = firestore.client().collection("users").document(UID)

    def _retry(fn, tries=4, wait=120):
        for i in range(tries):
            try:
                return fn()
            except (_gx.ResourceExhausted, _gx.ServiceUnavailable, _gx.DeadlineExceeded) as e:
                print("attempt %d blocked (%s); waiting %ds" % (i + 1, type(e).__name__, wait), flush=True)
                if i == tries - 1:
                    raise
                time.sleep(wait)

    nz = _retry(lambda: u.collection("backtests").document(NOISE_JOB).get())
    print("NOISE #422+TP job %s: %s" % (NOISE_JOB, (nz.to_dict() or {}).get("status") if nz.exists else "MISSING"))
    live = _retry(lambda: [(d.id, d.to_dict() or {}) for st in ("queued", "running", "paused")
                           for d in u.collection("backtests").where(filter=_FF("status", "==", st)).stream()])
    print("queue depth", len(live))
    for did, x in live:
        print("  live %s %-8s %-28s %-4s %s..%s" % (did, x.get("status"), str(x.get("strategy"))[:28], x.get("instrument"),
                                                   x.get("date_from"), x.get("date_to")))
    clash = []
    for did, x in live:
        if TAG in str(x.get("note") or "") or TAG in str(x.get("preset") or ""):
            clash.append("%s already carries this label (%s)" % (did, x.get("status")))
        if (x.get("strategy") == STRATEGY and str(x.get("date_from")) == JOB["date_from"]
                and str(x.get("date_to")) == JOB["date_to"]):
            clash.append("%s: same file and window already %s" % (did, x.get("status")))
    if clash:
        sys.exit("ABORT - would double-queue:\n  " + "\n  ".join(sorted(set(clash))))
    if len(live) > 9:
        sys.exit("ABORT - queue too deep (%d)" % len(live))
    job = dict(JOB, status="queued", progress=0, preset="%s: exit knobs open, fill 'worst'" % TAG, note=note(dp))
    if a.dry:
        for k in sorted(job):
            print("    %-16s %s" % (k, job[k]))
        return
    job["createdAt"] = datetime.datetime.now(datetime.timezone.utc)
    ref = u.collection("backtests").document()
    _retry(lambda: ref.set(job))
    print("queued users/%s/backtests/%s" % (UID, ref.id))
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, "validate_queued.txt"), "a") as fh:
        fh.write("%s MISC_SUPERSCALPER validate %s port %s\n" % (
            datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), ref.id, got))


if __name__ == "__main__":
    main()
