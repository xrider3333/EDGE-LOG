"""How well does the house detect_roll_seams find the REAL contract switches, per way of feeding it?

Truth = switches_<ROOT>.csv (ground_truth.py: databento_raw, the masters' own stitch rule).
Feeds measured (day bounds -> day_open = first bar open, day_close = last bar close, day_ts = first bar ts):
  rth_1m / rth_5m    : ET calendar days of the RTH master (the engine's day_id on an RTH master)
  eth_mid_1m         : ET calendar (midnight) days of the 24h master (the engine's day_id on an ETH master)
  eth_sess_1m        : 18:00 ET sessions of the 24h master
A truth switch is "caught" when the detector flags the day whose open is the first bar at/after the switch
(i.e. the day boundary the switch falls on). On midnight/session feeds a switch INSIDE a day cannot be caught.
Output: detector_accuracy.json + printed summary. Window: every switch in the raw ground truth.
"""
import os, sys, json
import numpy as np
import pandas as pd
REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, REPO)
import importlib.util as ilu
sp = ilu.spec_from_file_location("aost", os.path.join(REPO, "augur_strategies", "AOSTOCH_1_0.py"))
A = ilu.module_from_spec(sp); sp.loader.exec_module(A)
detect = A.detect_roll_seams
HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = os.path.join(os.path.dirname(HERE), "data")
OUTDIR = r"C:\EdgeLog\_anatomy_cache\rollaudit"


def load(root, tf, sess):
    m = pd.read_csv(os.path.join(REPO, "augur_uploads", f"NOADJ_{root}_{tf}_{sess.upper()}.csv"),
                    usecols=["time", "open", "close"])
    ix = pd.to_datetime(m["time"], unit="s", utc=True).dt.tz_convert("US/Eastern")
    return m["time"].to_numpy(np.int64), m["open"].to_numpy(float), m["close"].to_numpy(float), pd.DatetimeIndex(ix)


def day_bounds(ix, mode):
    if mode == "sess":
        sh = (ix + pd.Timedelta(hours=6)).tz_localize(None).normalize()
        key = pd.factorize(sh.asi8)[0]
    else:
        key = pd.factorize(ix.tz_localize(None).normalize().asi8)[0]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    ends = np.r_[starts[1:], len(key)]
    return starts, ends


def run(root, feed):
    tf = "5m" if feed.endswith("5m") else "1m"
    sess = "rth" if feed.startswith("rth") else "eth"
    sec, o, c, ix = load(root, tf, sess)
    starts, ends = day_bounds(ix, "sess" if "sess" in feed else "day")
    day_open = o[starts]; day_close = c[ends - 1]; day_ts = [ix[a] for a in starts]
    flagged = set(detect(day_open, day_close, day_ts))
    sw = pd.read_csv(os.path.join(TABLES, f"contract_switches_{root}.csv"))
    sw = sw[sw.source == "databento_raw"]
    caught, missed, inside = [], [], []
    truth_days = set()
    for _, r in sw.iterrows():
        s = int(r.switch_sec)
        d = int(np.searchsorted(sec[starts], s))          # first day whose first bar >= switch
        if d >= len(starts) or d == 0:
            continue
        on_boundary = sec[ends[d - 1] - 1] < s <= sec[starts[d]]
        if not on_boundary:
            inside.append(r.switch_et); continue
        truth_days.add(d)
        (caught if d in flagged else missed).append(r.switch_et)
    false_flags = sorted(flagged - truth_days)
    res = dict(root=root, feed=feed, n_truth=int(len(sw)), on_boundary=len(caught) + len(missed),
               inside_a_day=len(inside), caught=len(caught), missed=len(missed), flagged=len(flagged),
               false_flags=len(false_flags), false_flag_days=[str(day_ts[d].date()) for d in false_flags][:80],
               missed_switches=missed[:80], caught_switches=caught[:80])
    print("%s %-11s truth %d | on a day boundary %d, inside a day %d | caught %d, missed %d | flagged %d, false %d" % (
        root, feed, res["n_truth"], res["on_boundary"], res["inside_a_day"], res["caught"], res["missed"],
        res["flagged"], res["false_flags"]), flush=True)
    return res


if __name__ == "__main__":
    out = []
    for root in ("NQ", "ES"):
        for feed in ("rth_5m", "rth_1m", "eth_mid_1m", "eth_sess_1m"):
            out.append(run(root, feed))
    os.makedirs(OUTDIR, exist_ok=True)
    json.dump(out, open(os.path.join(OUTDIR, "detector_accuracy.json"), "w"), indent=1)
