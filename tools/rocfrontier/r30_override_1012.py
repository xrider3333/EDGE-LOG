"""OWNER-OVERRIDE RUNS 10-12 (STRATEGY-BEATING; MANAGER #169, record 'owner override 10-12'): docs/PREREG_SB_OVERRIDE_RUNS_2026-10-12.md.

    python tools/rocfrontier/r30_override_1012.py           parity gate, then A (three scalp cells) and B (MEGACAP-EARN)

A: round 37's own code for M4 RANGE-BURST x4/T1, M3 PDH/PDL stop0.10/T2 and M1 MICRO-ORB or5/first/T1 (tools/r37_scalp_triage.py),
copied unchanged except that each trade's session is kept; parity against the stored GROSS file first. B: NQ 09:31 open -> RTH close
on the session after a top-9 Nasdaq-100 member's earnings release, side = the sign of its opening gap. C (AUCTION-1300) is not run:
the held Treasury file has no bid-to-cover. Writes only C:/EdgeLog/_anatomy_cache/rocfrontier/override1012/.
"""
import hashlib
import importlib.util as ilu
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
DATA_REPO = REPO if os.path.exists(os.path.join(REPO, "optimizer_history.db")) else r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
for p in (DATA_REPO, os.path.join(DATA_REPO, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
from augur_engine.data import find_master, load_master_arrays          # noqa: E402
from augur_engine import seat_pipeline as SP, drawdowns as DD           # noqa: E402
from augur_engine import rolls as RL                                   # noqa: E402

_sp = ilu.spec_from_file_location("gapgo", os.path.join(DATA_REPO, "augur_strategies", "GAPGO_1_0.py"))
_gg = ilu.module_from_spec(_sp); _sp.loader.exec_module(_gg)
detect_roll_seams = _gg.detect_roll_seams

NOTE = os.path.join(REPO, "docs", "PREREG_SB_OVERRIDE_RUNS_2026-10-12.md")
NOTE_SHA = "6d11c2759461692be465e4e31c3457d74bb3da77bc54a5df14fc0566a272ec4b"                                                      # LF sha256 of the note as frozen on the witness branch
OUT = r"C:\EdgeLog\_anatomy_cache\rocfrontier\override1012"
TS = pd.Timestamp
MULT = 20.0
PRIMARY = 0.783
COSTS = (("gross", 0.0), ("house 0.533", 0.533), ("0.706", 0.706), ("owner 0.783", 0.783), ("MNQ 1.20", 1.20))
WF = (TS("2016-07-01"), TS("2025-06-29"))
AFTER0 = TS("2025-06-30")
R37_WIN = dict(date_from="2010-06-07", date_to="2025-06-29")
NEWEST = "2026-10-09"                                                     # the last COMPLETE RTH session on file (10-12 is in progress)
# ADDENDUM 1: parity against the roll audit's TRUE-calendar restatement of round 37 at 0.533 pt (rollaudit/work/harness-r35-38/r37_scalp_triage_true.csv)
PARITY_COST = 0.533
GROSS_REF = {"M4-RANGEBURST x4/T1": (677, 13403), "M3-PDHL stop0.10/T2": (3468, 9410), "M1-MICROORB or5/first/T1": (2659, -20155)}
EDGAR = r"C:\EdgeLog\_research_cache\edgar\earnings_calendar_ndx.csv"
MEMBERS = os.path.join(DATA_REPO, "tools", "data", "ndx_members.csv")
DAILY = r"C:\EdgeLog\alpaca_cache\siporb"
B_FROM, B_TO = TS("2016-06-01"), TS("2026-06-30")


def sha_lf(path):
    return hashlib.sha256(open(path, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


# ------------------------------------------------------------------ round 37's code (copied; the trade's session is the only addition)
def ride(o, h, l, c, i_open, i_end, entry, stop0, side, mode):
    R = side * (entry - stop0); stop = stop0
    tgt = entry + side * R * (1.0 if mode == "T1" else 2.0) if mode != "RIDE" else None
    be = False; be_next = False
    for i in range(i_open, i_end):
        if be_next:
            if (side == 1 and entry > stop) or (side == -1 and entry < stop):
                stop = entry
            be_next = False
        if side == 1:
            if o[i] <= stop: return o[i], i - i_open + 1
            if l[i] <= stop: return stop, i - i_open + 1
            if tgt is not None and h[i] >= tgt: return tgt, i - i_open + 1
            if tgt is None and not be and c[i] >= entry + R: be = True; be_next = True
        else:
            if o[i] >= stop: return o[i], i - i_open + 1
            if h[i] >= stop: return stop, i - i_open + 1
            if tgt is not None and l[i] <= tgt: return tgt, i - i_open + 1
            if tgt is None and not be and c[i] <= entry - R: be = True; be_next = True
    return c[i_end - 1], i_end - i_open


def world(**win):
    A = load_master_arrays(find_master("NQ", "1m", "rth", "db_noadj_rth"), **win)
    o, h, l, c, v, did = A["open"], A["high"], A["low"], A["close"], A["volume"], A["day_id"]
    idx = pd.DatetimeIndex(A["index"]); mins = (idx.hour * 60 + idx.minute).values
    n = len(c)
    sess = []; a = 0
    while a < n:
        b = a
        while b < n and did[b] == did[a]: b += 1
        sess.append((a, b)); a = b
    nd = len(sess)
    do = np.array([o[x] for x, y in sess]); dc = np.array([c[y - 1] for x, y in sess])
    dh = np.array([h[x:y].max() for x, y in sess]); dl = np.array([l[x:y].min() for x, y in sess])
    with RL.roll_context("NQ", idx, 60):                                 # ADDENDUM 1: the house TRUE roll calendar (10-08 roll fix)
        seams = set(detect_roll_seams(do, dc, [idx[x] for x, y in sess]))
    atr20 = np.full(nd, np.nan)
    for d in range(20, nd): atr20[d] = (dh[d - 20:d] - dl[d - 20:d]).mean()
    days = pd.DatetimeIndex([idx[x].normalize() for x, y in sess])
    return dict(o=o, h=h, l=l, c=c, v=v, mins=mins, sess=sess, nd=nd, dh=dh, dl=dl, seams=seams, atr20=atr20, days=days, n=n)


def cells(W):
    """-> {cell: [(session index, gross points, bars held)]} for the three pre-registered cells, round 37's code at zero cost"""
    o, h, l, c, mins, sess, nd = W["o"], W["h"], W["l"], W["c"], W["mins"], W["sess"], W["nd"]
    dh, dl, seams, atr20, n = W["dh"], W["dl"], W["seams"], W["atr20"], W["n"]
    out = {}
    # M1 MICRO-ORB, orb 5, first-candle direction, T1
    orb, dirmode, ex, tr = 5, "first", "T1", []
    for d in range(21, nd):
        if d in seams: continue
        a, b = sess[d]
        if b - a < orb + 5: continue
        rh = h[a:a + orb].max(); rl = l[a:a + orb].min()
        if rh - rl <= 0: continue
        fc = 1 if c[a] > o[a] else (-1 if c[a] < o[a] else 0)
        if dirmode == "first" and fc == 0: continue
        for k in range(a + orb, min(a + 60, b - 1)):
            side = 1 if c[k] > rh else (-1 if c[k] < rl else 0)
            if side == 0 or (dirmode == "first" and side != fc): continue
            entry = o[k + 1]; stop0 = rl if side == 1 else rh
            if side * (entry - stop0) <= 0: break
            i_end = b if ex == "RIDE" else min(k + 1 + 30, b)
            px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
            tr.append((d, side * (px - entry), hb))
            break
    out["M1-MICROORB or5/first/T1"] = tr
    # M3 PDH/PDL, stop 0.10 x ATR20d, T2
    sk, ex, tr = 0.10, "T2", []
    for d in range(21, nd):
        if d in seams or np.isnan(atr20[d]) or (d - 1) in seams: continue
        a, b = sess[d]
        pdh, pdl = dh[d - 1], dl[d - 1]
        done = {1: False, -1: False}; busy_until = a
        for k in range(a + 1, b - 1):
            if mins[k] >= 900 or k < busy_until: continue
            side = 1 if (c[k] > pdh and not done[1]) else (-1 if (c[k] < pdl and not done[-1]) else 0)
            if side == 0: continue
            entry = o[k + 1]; stop0 = entry - side * sk * atr20[d]
            i_end = b if ex == "RIDE" else min(k + 1 + 60, b)
            px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
            tr.append((d, side * (px - entry), hb))
            done[side] = True; busy_until = k + 1 + hb
            if done[1] and done[-1]: break
    out["M3-PDHL stop0.10/T2"] = tr
    # M4 RANGE-BURST, 4 x the trailing 20-bar mean range, T1
    rng = h - l
    cs = np.concatenate([[0.0], np.cumsum(rng)])
    avg20 = np.full(n, np.nan); avg20[20:] = (cs[20:n] - cs[:n - 20]) / 20.0
    thr, ex, tr = 4.0, "T1", []
    for d in range(21, nd):
        if d in seams: continue
        a, b = sess[d]; cnt = 0; busy_until = a
        for k in range(a + 1, b - 1):
            if k < busy_until or mins[k] < 575 or mins[k] > 930: continue
            if np.isnan(avg20[k]) or rng[k] < thr * avg20[k] or rng[k] <= 0: continue
            pos = (c[k] - l[k]) / rng[k]
            daydir = 1 if c[k] > o[a] else (-1 if c[k] < o[a] else 0)
            side = 1 if (pos >= 0.75 and daydir == 1) else (-1 if (pos <= 0.25 and daydir == -1) else 0)
            if side == 0: continue
            entry = o[k + 1]; stop0 = l[k] if side == 1 else h[k]
            if side * (entry - stop0) <= 0: continue
            i_end = b if ex == "RIDE" else min(k + 1 + 30, b)
            px, hb = ride(o, h, l, c, k + 1, i_end, entry, stop0, side, ex)
            tr.append((d, side * (px - entry), hb))
            cnt += 1; busy_until = k + 1 + hb
            if cnt >= 3: break
    out["M4-RANGEBURST x4/T1"] = tr
    return out


# ------------------------------------------------------------------ B: MEGACAP-EARN
def megacap_trades(W):
    """-> ([(session index, gross points, bars held)], info) for B on the full NQ world W"""
    cal = pd.read_csv(EDGAR, dtype=str, keep_default_na=False)
    cal = cal[cal["timing"].isin(["after-close", "pre-open"])].copy()
    cal["rs"] = pd.to_datetime(cal["reaction_session"], errors="coerce")
    cal = cal[(cal.rs >= B_FROM) & (cal.rs <= B_TO)]
    mem = pd.read_csv(MEMBERS, dtype=str, keep_default_na=False)
    mem["f"] = pd.to_datetime(mem["from"]); mem["t"] = pd.to_datetime(mem["to"].replace("", "2100-01-01"))
    tick2cik = {}
    for _, r in pd.read_csv(EDGAR, dtype=str, keep_default_na=False).iterrows():
        for t in str(r["ndx_tickers"]).split(";"):
            if t:
                tick2cik.setdefault(t.strip(), r["cik"])
    syms = sorted(set(mem["ticker"]) | {t.strip() for x in cal["ndx_tickers"] for t in x.split(";") if t})
    import pyarrow.parquet as pq
    raw = pq.read_table(os.path.join(DAILY, "daily_raw.parquet"), filters=[("symbol", "in", syms)]).to_pandas()
    spl = pq.read_table(os.path.join(DAILY, "daily_split.parquet"), filters=[("symbol", "in", syms)]).to_pandas()
    raw["dv"] = raw["c"] * raw["v"]
    dv = raw.pivot_table(index="date", columns="symbol", values="dv").sort_index()
    dv60 = dv.rolling(60, min_periods=60).mean().shift(1)                   # the 60 sessions BEFORE the row's session
    so = spl.pivot_table(index="date", columns="symbol", values="o").sort_index()
    sc = spl.pivot_table(index="date", columns="symbol", values="c").sort_index()
    pos = {d: i for i, d in enumerate(W["days"])}
    cik2ticks = {}
    for k, v in tick2cik.items():
        cik2ticks.setdefault(v, set()).add(k)
    tops = {}

    def top9(t):
        """the top 9 member companies by 60-session mean dollar volume before session t (one id per company: its CIK, else its ticker)"""
        if t not in tops:
            ids = {}
            for m in mem[(mem.f <= t) & (t < mem.t)]["ticker"]:
                ids.setdefault(tick2cik.get(m, m), set()).add(m)
            score = {}
            for cid, ts in ids.items():
                vals = [dv60.at[t, s] for s in ts | cik2ticks.get(cid, set()) if s in dv60.columns and np.isfinite(dv60.at[t, s])]
                if vals:
                    score[cid] = float(np.sum(vals))
            tops[t] = set(sorted(score, key=score.get, reverse=True)[:9])
        return tops[t]

    events, sigs = [], {}
    for _, r in cal.iterrows():
        t = r["rs"]
        if t not in dv60.index or t not in pos:
            continue
        if r["cik"] not in top9(t):
            continue
        gap = None
        for s in [x.strip() for x in r["ndx_tickers"].split(";") if x.strip()]:
            if s in so.columns and t in so.index:
                prev = sc[s].loc[:t].iloc[:-1].dropna()
                if np.isfinite(so.at[t, s]) and len(prev):
                    gap = so.at[t, s] / prev.iloc[-1] - 1.0
                    break
        if gap is None:
            continue
        events.append(dict(session=t, ticker=r["ticker"], cik=r["cik"], timing=r["timing"], gap=gap))
        sigs[t] = sigs.get(t, 0.0) + gap
    o, c, sess = W["o"], W["c"], W["sess"]
    tr = []
    for t, g in sorted(sigs.items()):
        side = 1 if g > 0 else (-1 if g < 0 else 0)
        if side == 0:
            continue
        a, b = sess[pos[t]]
        if b - a < 3:
            continue
        tr.append((pos[t], side * (c[b - 1] - o[a + 1]), b - 1 - (a + 1)))
    ev = pd.DataFrame(events)
    yrs = (B_TO - B_FROM).days / 365.25
    info = dict(events=len(ev), sessions=len(tr), events_per_year=round(len(ev) / yrs, 1),
                by_ticker=ev["ticker"].value_counts().head(15).to_dict() if len(ev) else {})
    return tr, info, ev


# ------------------------------------------------------------------ reading
def daily_series(trades, days, cost):
    s = pd.Series(0.0, index=days)
    for d, g, hb in trades:
        s.iloc[d] += (g - cost) * MULT
    return s


def stretch(trades, days, cost, start, end):
    s = daily_series(trades, days, cost)
    f = SP.figures(s, start, end)
    w = SP.window(s, start, end)
    pts = np.array([(g - cost) * MULT for d, g, hb in trades if start <= days[d] <= end])
    holds = np.array([hb for d, g, hb in trades if start <= days[d] <= end])
    yrs = (end - start).days / 365.25
    wins, losses = pts[pts > 0], pts[pts <= 0]
    return dict(roc30=f["roc30"], dd5=f["dd5"], one_episode=f["one_episode"], dd_pct=DD.dd_pct_peak(w.to_numpy(float), start=100000.0),
                sortino=f["sortino"], net_per_year=f["net_per_year"], max_dd=f["dd"], trades=len(pts),
                trades_per_year=len(pts) / yrs if yrs > 0 else float("nan"), win=float((pts > 0).mean()) if len(pts) else float("nan"),
                avg_win=float(wins.mean()) if len(wins) else float("nan"), avg_loss=float(-losses.mean()) if len(losses) else float("nan"),
                hold_med=float(np.median(holds)) if len(holds) else float("nan"))


def line(name, st):
    wl = st["avg_win"] / st["avg_loss"] if st["avg_loss"] and np.isfinite(st["avg_loss"]) else float("nan")
    return (f"  {name}: ROC @ $30k {st['roc30']:.1f} | DD5 ${st['dd5']:,.0f}{' (one episode)' if st['one_episode'] else ''} | DD% from peak "
            f"{st['dd_pct']:.1f}% | Sortino {st['sortino']:.2f} || net ${st['net_per_year']:,.0f} a year, {st['trades']:,} trades "
            f"({st['trades_per_year']:.0f} a year), win {100 * st['win']:.1f}%, avg win ${st['avg_win']:,.0f} / avg loss ${st['avg_loss']:,.0f} "
            f"(x{wl:.2f}), hold median {st['hold_med']:.0f} min")


def report(label, trades, days, end_after):
    rows = []
    print(f"\n{label}: {len(trades):,} trades {days[trades[0][0]].date() if trades else '-'} .. {days[trades[-1][0]].date() if trades else '-'}")
    for nm, (a, b) in (("WF 2016-07-01..2025-06-29", WF), (f"AFTER 2025-06-30..{end_after.date()} (lockbox spent + newest)", (AFTER0, end_after))):
        st = stretch(trades, days, PRIMARY, a, b)
        print(line(nm + f" @ {PRIMARY} pt", st))
        rows.append(dict(cell=label, stretch=nm.split(" ")[0], cost=PRIMARY, **st))
    curve = []
    for cn, cv in COSTS:
        st = stretch(trades, days, cv, *WF)
        curve.append(f"{cn} {st['roc30']:.1f} (win {100 * st['win']:.0f}%)")
        rows.append(dict(cell=label, stretch="WF", cost=cv, **st))
    print("  WF cost curve, ROC @ $30k: " + "; ".join(curve))
    return rows


def main():
    t0 = time.time()
    got = sha_lf(NOTE)
    if got != NOTE_SHA:
        raise SystemExit(f"refused: the prereg note's LF sha256 is {got[:16]}..., not the frozen {NOTE_SHA[:16]}... (nothing run)")
    os.makedirs(OUT, exist_ok=True)
    print(f"note {got[:16]}... verified; owner override 10-12 (MANAGER #169)", flush=True)
    # parity: round 37's own window, zero cost
    W0 = world(**R37_WIN)
    ref = cells(W0)
    for k, (n_ref, net_ref) in GROSS_REF.items():
        n, net = len(ref[k]), round(sum((g - PARITY_COST) * MULT for d, g, hb in ref[k]))
        print(f"parity {k}: {n} trades / ${net:,} at {PARITY_COST} pt vs the roll audit's true-calendar {n_ref} / ${net_ref:,}", flush=True)
        if (n, net) != (n_ref, net_ref):
            raise SystemExit(f"refused: {k} does not reproduce round 37 on its own window (nothing read)")
    del W0, ref
    W = world(date_from="2010-06-07", date_to=NEWEST)
    days = W["days"]
    print(f"world: {W['nd']:,} sessions {days[0].date()} .. {days[-1].date()}, {len(W['seams'])} seam sessions skipped ({time.time() - t0:.0f}s)", flush=True)
    rows = []
    for k, tr in cells(W).items():
        rows += report("A " + k, tr, days, days[-1])
        pd.DataFrame([(days[d].date(), g, hb) for d, g, hb in tr], columns=["session", "gross_pts", "bars"]).to_csv(
            os.path.join(OUT, "trades_" + k.replace(" ", "_").replace("/", "-") + ".csv"), index=False)
    trB, info, ev = megacap_trades(W)
    print(f"\nB MEGACAP-EARN events: {info['events']} ({info['events_per_year']} a year) on {info['sessions']} NQ sessions; top tickers {info['by_ticker']}")
    rows += report("B MEGACAP-EARN continuation", trB, days, B_TO)
    rows += report("B MEGACAP-EARN fade (mirror, report only)", [(d, -g, hb) for d, g, hb in trB], days, B_TO)
    ev.to_csv(os.path.join(OUT, "megacap_events.csv"), index=False)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "override1012_summary.csv"), index=False)
    json.dump(dict(note_sha=got, newest=NEWEST, primary_cost=PRIMARY, megacap=info), open(os.path.join(OUT, "override1012_meta.json"), "w"), indent=1, default=str)
    print(f"\ndone in {time.time() - t0:.0f}s -> {OUT}")


if __name__ == "__main__":
    main()
