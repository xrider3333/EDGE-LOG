"""Ground truth contract switches for the no-adj NQ/ES masters, rebuilt from databento_raw with
the SAME rule the masters were stitched with (tools/stitch_databento._active_by_day: the
max-volume contract per UTC day, forward-only). For every switch: the first master bar of the
new contract, its ET time, the old/new contract, the jump in the master (open - prior close) and
the true contract offset (new close - old close at the last minute both traded before the switch).
Master data after the raw files end (2026-06-07) is flagged; the June 2026 switch there is
inferred from the largest 00:00-UTC / session-open jump in its quarterly window.

Output: C:\\EdgeLog\\_anatomy_cache\\rollaudit\\switches_<ROOT>.csv - copy it to
tools/data/contract_switches_<ROOT>.csv to update the committed table.
"""
import os, sys, json
import numpy as np
import pandas as pd

REPO = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, REPO)
import stitch_databento as S                       # noqa: E402
OUT = r"C:\EdgeLog\_anatomy_cache\rollaudit"
os.makedirs(OUT, exist_ok=True)


def master_1m_eth(root):
    p = os.path.join(REPO, "augur_uploads", f"NOADJ_{root}_1m_ETH.csv")
    m = pd.read_csv(p, usecols=["time", "open", "close"])
    return m


def main(root):
    df = S._load_root(root)
    active = S._active_by_day(df)
    sym = df.groupby("cid")["symbol"].agg(lambda s: s.iloc[-1]).to_dict()
    closes = {c: g.groupby("sec")["close"].last().sort_index() for c, g in df.groupby("cid")}
    days = sorted(active)
    m = master_1m_eth(root)
    msec = m["time"].to_numpy(np.int64)
    rows = []
    for a, b in zip(days[:-1], days[1:]):
        if active[a] == active[b]:
            continue
        old, new = active[a], active[b]
        k = int(np.searchsorted(msec, b * 86400))        # first master bar of UTC day b
        if k <= 0 or k >= len(msec):
            continue
        # true offset at the last minute both traded before the switch
        co, cn = closes[old], closes[new]
        common = co.index.intersection(cn.index)
        common = common[common < msec[k]]
        off = float(cn.loc[common[-1]] - co.loc[common[-1]]) if len(common) else float("nan")
        ts = pd.Timestamp(int(msec[k]), unit="s", tz="UTC").tz_convert("US/Eastern")
        rows.append(dict(root=root, switch_sec=int(msec[k]), switch_et=str(ts)[:16], utc_day=str(pd.Timestamp(b * 86400, unit="s").date()),
                         old=sym.get(old), new=sym.get(new), master_idx_1m_eth=k,
                         master_jump=float(m["open"].iat[k] - m["close"].iat[k - 1]),
                         prev_bar_et=str(pd.Timestamp(int(msec[k - 1]), unit="s", tz="UTC").tz_convert("US/Eastern"))[:16],
                         contract_offset=off, source="databento_raw"))
    raw_end = int(df["sec"].max())
    # after the raw files end: infer (largest 00:00 UTC or session-open jump per quarterly window)
    after = msec > raw_end
    if after.any():
        from augur_engine import setup_kit as SK
        mi = pd.to_datetime(msec, unit="s", utc=True).tz_convert("US/Eastern")
        sess, *_ = SK.sessions(mi)
        o = m["open"].to_numpy(float); c = m["close"].to_numpy(float)
        sw = SK.contract_switch_sessions(o, c, mi, sess)
        for s_ in sorted(sw):
            idx = np.flatnonzero(sess == s_)
            if msec[idx[0]] <= raw_end:
                continue
            utc = mi[idx].tz_convert("UTC")
            cand = idx[((np.asarray(utc.hour) == 0) & (np.asarray(utc.minute) == 0))]
            cand = np.r_[cand, idx[0]]
            cand = cand[cand > 0]
            k = int(cand[np.argmax(np.abs(o[cand] - c[cand - 1]))])
            rows.append(dict(root=root, switch_sec=int(msec[k]), switch_et=str(mi[k])[:16], utc_day=str(mi[k].tz_convert("UTC").date()),
                             old=None, new=None, master_idx_1m_eth=k, master_jump=float(o[k] - c[k - 1]),
                             prev_bar_et=str(mi[k - 1])[:16], contract_offset=float("nan"), source="inferred_after_raw_end"))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(OUT, f"switches_{root}.csv"), index=False)
    print(root, "switches:", len(out), "| raw end", pd.Timestamp(raw_end, unit="s").date(),
          "| sources", out.source.value_counts().to_dict())
    print(out[["switch_et", "old", "new", "master_jump", "contract_offset", "prev_bar_et"]].tail(8).to_string(index=False))
    print("  switch ET hour/min counts:", pd.Series([r["switch_et"][11:16] for r in rows]).value_counts().head(6).to_dict())


if __name__ == "__main__":
    for r in sys.argv[1:] or ["NQ", "ES"]:
        main(r)
