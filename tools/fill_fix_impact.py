"""Price every fill fix: run each touched strategy at its defaults BEFORE (the version
committed at HEAD in the worktree) and AFTER (the worktree working copy) on the same
bars. Run this FROM THE SHARED CHECKOUT so the masters/history DB resolve."""
import io, os, subprocess, sys, shutil
sys.path.insert(0, r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
os.chdir(r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG")
from augur_engine.engine import run_backtest

WT = r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\fillfix"
TMP = os.path.join(os.environ.get("TEMP", "."), "_pre_fillfix")
os.makedirs(TMP, exist_ok=True)

CASES = [
    ("ORB_1_0.py",       "NQ", "5m", "rth", 0.533),
    ("ENGU_1_1_20.py",   "NQ", "5m", "rth", 0.533),
    ("ENGU_1_1_21.py",   "NQ", "5m", "rth", 0.533),
    ("VWAP_FADE_1_0.py", "NQ", "5m", "rth", 0.533),
    ("VWAP_FADE_2_0.py", "NQ", "5m", "rth", 0.533),
    ("ENGU_1_3_1.py",    "NQ", "5m", "rth", 0.533),
    ("ENGU_1_3_2.py",    "NQ", "5m", "rth", 0.533),
    ("ENGU_1_3_3.py",    "NQ", "5m", "rth", 0.533),
    ("ENGU_1_3_4.py",    "NQ", "5m", "rth", 0.533),
    ("ENGU_1_3_5.py",    "NQ", "5m", "rth", 0.533),
    ("REVERT_1_0.py",    "NQ", "5m", "rth", 0.533),
    ("REVERT_1_1.py",    "NQ", "5m", "rth", 0.533),
    ("REVERT_1_2.py",    "NQ", "5m", "rth", 0.533),
]


def one(path, inst, tf, sess, cost):
    try:
        m = run_backtest(path, instrument=inst, timeframe=tf, session=sess, cost_pts=cost)
    except Exception as e:
        return {"err": "%s: %s" % (type(e).__name__, str(e)[:40])}
    if not m:
        return {"err": "no trades"}
    return {"n": m.get("num_trades"), "pnl": m.get("total_pnl"), "pf": m.get("profit_factor")}


def fmt(d):
    if "err" in d:
        return d["err"][:34]
    return "%5s / %11.1f / %5.2f" % (d["n"], d["pnl"] or 0, d["pf"] or 0)


print("%-18s %-34s %-34s %s" % ("strategy", "BEFORE  n / net pts / PF", "AFTER  n / net pts / PF", "delta pts"))
print("-" * 104)
for f, inst, tf, sess, cost in CASES:
    blob = subprocess.run(["git", "-C", WT, "show", "HEAD:augur_strategies/" + f], capture_output=True)
    if blob.returncode != 0:
        print("%-18s ! could not read HEAD version" % f); continue
    old_path = os.path.join(TMP, f)
    io.open(old_path, "wb").write(blob.stdout)

    b = one(old_path, inst, tf, sess, cost)
    a = one(os.path.join(WT, "augur_strategies", f), inst, tf, sess, cost)
    d = ""
    if "err" not in b and "err" not in a:
        d = "%+.1f" % ((a["pnl"] or 0) - (b["pnl"] or 0))
    print("%-18s %-34s %-34s %s" % (f.replace(".py", ""), fmt(b), fmt(a), d))

shutil.rmtree(TMP, ignore_errors=True)
