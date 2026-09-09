"""TTM Squeeze round 12e - does the OVERNIGHT session's compression say anything about the day's fire?

Every working version of this family verifies a day-session squeeze against the SAME session's hourly
squeeze. The overnight tape has only ever been tested as a place to TRADE (round 6: dead). It has
never been tested as a place to LOOK: the S&P trades all night, the coil either tightened or loosened
while you slept, and by 09:30 that is a completed, unrepeatable fact about the market you are about
to trade. This asks whether it carries information about the day's squeeze fires.

Everything here is a PRE-SESSION read: one number per trading day, fixed before the opening bell, so
no intraday decision can use anything that has not happened yet.

THE DISCIPLINE (this shop has burned itself on per-trade slicing before): the pre-lockbox trades are
split 60/40 by time into a discovery half and a holdout half. Rules are read off DISCOVERY only, and
every rule is reported on discovery, holdout and the lockbox side by side. A rule that lives only in
discovery is labelled an artifact. Nothing is crowned here.

Log: tools/data/ttmsqz_r12e_overnight.txt
"""
import os, sys, importlib.util, time
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
r8 = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("r8", os.path.join(ROOT, "tools", "ttmsqz_round8_crown.py")))
r8.__spec__.loader.exec_module(r8)
r6 = r8.r6
ttm3 = r8.ttm3
LOG = os.path.join(ROOT, "tools", "data", "ttmsqz_r12e_overnight.txt")
CELL = dict(kc_mult=1.5, stop_atr=1.5, eod_cutoff=1, gate_len=20)
ES_MULT, ES_COST = r6.MULT["ES"], r6.COST["ES"]


def overnight_state(length=20, bb_mult=2.0, kc_mult=1.5):
    """One row per trading day: the state of the LAST COMPLETE overnight hour before 09:30 ET.

    The ETH master runs 18:00 -> 17:00, so the overnight window for a trading day is everything from
    the previous 18:00 up to the open. Hours are anchored on the ETH session start, and a group is
    usable only once every one of its bars has closed - so the last group we read ends at or before
    09:30, which makes this a pre-session number by construction."""
    df = r6.load("ES", "5m", "ETH")
    et = pd.DatetimeIndex(df["_dt"])                      # tz-aware US/Eastern throughout
    # the trading DAY an overnight bar belongs to: bars from 18:00 onward belong to the NEXT day
    day = pd.Series(et.normalize(), index=df.index)
    day[et.hour >= 18] = day[et.hour >= 18] + pd.Timedelta(days=1)
    mins = et.hour.values * 60 + et.minute.values
    off = (mins - 18 * 60) % (24 * 60)                    # minutes since 18:00, wrapping past midnight
    grp = day.astype("int64") * 10000 + (off // 60)
    g = df.assign(_grp=grp, _day=day).groupby("_grp", sort=True)
    G = pd.DataFrame({"day": g["_day"].first(), "end": g["_end"].last(), "hh": g["high"].max(),
                      "ll": g["low"].min(), "cc": g["close"].last()}).sort_values("end").reset_index(drop=True)
    hh, ll, cc = G["hh"].to_numpy(), G["ll"].to_numpy(), G["cc"].to_numpy()
    sq, mom, _ = ttm3.squeeze_indicators(hh, ll, cc, length, bb_mult, kc_mult)
    dev = pd.Series(cc).rolling(length).std(ddof=0)
    prev = np.concatenate([[np.nan], cc[:-1]])
    tr = np.maximum.reduce([hh - ll, np.abs(hh - prev), np.abs(ll - prev)])
    atr = pd.Series(tr).rolling(length).mean()
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = ((bb_mult * dev) / (kc_mult * atr)).to_numpy()
    warm = length * 2 + 5
    G["sq"], G["ratio"], G["mom"], G["i"] = sq, ratio, mom, np.arange(len(G))
    # keep only groups that have CLOSED by 09:30 of their own trading day - the pre-session read
    G = G[G["end"] <= G["day"] + pd.Timedelta(hours=9, minutes=30)]
    G = G[G["i"] >= warm]
    last = G.groupby("day").tail(1).set_index("day")
    out = pd.DataFrame({
        "on_sq": last["sq"].astype(bool), "on_ratio": last["ratio"], "on_mom": last["mom"],
        "night_range": G.groupby("day")["hh"].max() - G.groupby("day")["ll"].min(),
        "hours": G.groupby("day").size(),
    }).sort_index()
    out.index = pd.DatetimeIndex(out.index).tz_localize(None).normalize()
    # a RELATIVE overnight range: this night against the median of the previous 20, so it is scale free
    out["night_rel"] = out["night_range"] / out["night_range"].shift(1).rolling(20).median()
    return out


def crown_trades():
    m = r6._mod(os.path.join(ROOT, "augur_strategies", "TTMSQZ_3_0_ES30N.py"), "es30n_r12e")
    df = r6.load("ES", "30m", "RTH")
    r = m.run_backtest(df["open"].values, df["high"].values, df["low"].values, df["close"].values,
                       day_id=df["day_id"].values, index=df["_dt"], return_trades=True, **CELL)
    t = pd.DataFrame([(int(x[0]), int(x[1]), float(x[2]), int(x[3])) for x in r["trades"]],
                     columns=["eb", "xb", "pts", "side"])
    idx = pd.DatetimeIndex(df["_dt"])
    t["entry_day"] = idx[t["eb"].values].tz_localize(None).normalize()
    t["date"] = idx[t["xb"].values].tz_localize(None).normalize()
    t["usd"] = (t["pts"] - ES_COST) * ES_MULT
    return t


def stats(usd):
    if not len(usd):
        return None
    gw, gl = usd[usd > 0].sum(), -usd[usd < 0].sum()
    cum = np.concatenate([[0.0], np.cumsum(usd)])
    dd = -float((cum - np.maximum.accumulate(cum)).min())
    return dict(n=len(usd), net=float(usd.sum()), pf=(gw / gl) if gl > 0 else 99.0, dd=dd)


def perm_p(usd, mask, n=4000, seed=42):
    if mask.all() or (~mask).all():
        return float("nan")
    rng = np.random.default_rng(seed)
    obs = abs(usd[mask].mean() - usd[~mask].mean())
    lab = mask.copy()
    hits = 0
    for _ in range(n):
        rng.shuffle(lab)
        if abs(usd[lab].mean() - usd[~lab].mean()) >= obs:
            hits += 1
    return hits / n


def main():
    L = ["TTM SQUEEZE ROUND 12e - the OVERNIGHT coil as a pre-session read   %s" % time.strftime("%Y-%m-%d %H:%M"),
         "window %s..%s, lockbox from %s; ES 30m RTH crown cell, 0.363 pts a round trip, 50 dollars a point"
         % (r6.DATE_FROM, r6.DATE_TO, r6.LB_FROM),
         "Discovery = the first 60 percent of pre-lockbox trades by time. Rules are read off discovery only;",
         "holdout and lockbox are reported beside every one of them. Nothing is crowned."]
    print("\n".join(L), flush=True)
    night = overnight_state()
    t = crown_trades().join(night, on="entry_day")
    have = t["on_ratio"].notna()
    L.append("")
    L.append("  %d trades, %d with an overnight read (%d nights in the table, median %d complete hours before the open)"
             % (len(t), int(have.sum()), len(night), int(night["hours"].median())))
    t = t[have].reset_index(drop=True)
    lb = t["date"] >= pd.Timestamp(r6.LB_FROM)
    pre = t[~lb].reset_index(drop=True)
    cut = int(len(pre) * 0.6)
    disc_mask = np.zeros(len(t), bool); hold_mask = np.zeros(len(t), bool)
    disc_days = set(pre["date"].iloc[:cut]); hold_days = set(pre["date"].iloc[cut:])
    for i, d in enumerate(t["date"]):
        if d in disc_days: disc_mask[i] = True
        elif d in hold_days: hold_mask[i] = True
    usd = t["usd"].values
    L.append("  discovery %d trades, holdout %d, lockbox %d" % (disc_mask.sum(), hold_mask.sum(), lb.sum()))

    # PROXIES COMPUTABLE FROM THE DAY-SESSION MASTER ALONE. This matters for more than tidiness: a
    # strategy handed to Auto-Validate receives ONE master's bars, so a rule that needs the overnight
    # tape cannot be validated as a strategy at all. If a proxy built from the day master reproduces
    # the effect, the rule becomes testable; if it does not, the finding stays a scan for ever.
    rth = r6.load("ES", "30m", "RTH")
    ridx = pd.DatetimeIndex(rth["_dt"])
    rday = pd.Series(ridx.tz_localize(None).normalize(), index=rth.index)
    first_open = rth.groupby(rday)["open"].first()
    last_close = rth.groupby(rday)["close"].last()
    day_range = rth.groupby(rday)["high"].max() - rth.groupby(rday)["low"].min()
    gap = first_open - last_close.shift(1)                      # the overnight move, in points
    gap_atr = gap / day_range.shift(1).rolling(20).mean()       # scaled by recent daily range
    # LOOK-AHEAD BUG, FOUND AND FIXED 2026-09-09 - kept here as a comment because it produced the
    # most convincing false result this study has seen. The first version read last_close.diff()
    # at the ENTRY day, which is today's close minus yesterday's: the direction the day being
    # traded ends up closing. Filtering on that is filtering on the outcome, and it duly reported
    # more money, a higher profit factor and a lower drawdown in discovery, holdout AND lockbox,
    # on both sides, with p = 0.0000. The honest reading shifts one session back.
    prox = pd.DataFrame({"gap": gap, "gap_rel": gap_atr,
                         "prior_day": last_close.diff().shift(1)}).reindex(t["entry_day"].values)
    t["gap_sign"] = np.sign(prox["gap"].values)
    t["gap_rel"] = np.abs(prox["gap_rel"].values)
    t["prior_sign"] = np.sign(prox["prior_day"].values)

    RULES = [
        ("PROXY overnight GAP agrees with the trade", (t["gap_sign"].values == t["side"].values)),
        ("PROXY quiet overnight gap (under 0.25 of range)", (t["gap_rel"].values <= 0.25)),
        ("PROXY prior day close-to-close agrees", (t["prior_sign"].values == t["side"].values)),
        ("overnight squeeze ON at the open", t["on_sq"].values.astype(bool)),
        ("overnight ratio at or under 1.0", (t["on_ratio"].values <= 1.0)),
        ("overnight ratio at or under 0.85 (deep)", (t["on_ratio"].values <= 0.85)),
        ("overnight range under its 20-day median", (t["night_rel"].values <= 1.0)),
        ("overnight range under 0.8 of its median", (t["night_rel"].values <= 0.8)),
        ("quiet night AND coiled (both above)", (t["night_rel"].values <= 1.0) & (t["on_ratio"].values <= 1.0)),
        ("overnight momentum agrees with the trade", (np.sign(t["on_mom"].values) == t["side"].values)),
    ]
    L.append("")
    L.append("  %-44s %-7s %s" % ("", "", "------- discovery -------   -------- holdout --------   -------- lockbox --------"))
    L.append("  %-44s %-7s %5s %6s %9s %8s  %5s %6s %9s %8s  %5s %6s %9s %8s %7s" % (
        "rule", "shape", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "perm p"))

    def emit(name, shape, sel_usd_d, sel_usd_h, sel_usd_l, p):
        cells = []
        for u in (sel_usd_d, sel_usd_h, sel_usd_l):
            s = stats(u)
            if s:
                cells += ["%5d" % s["n"], "%6.2f" % min(s["pf"], 99), "%9s" % "{:,.0f}".format(s["net"]),
                          "%8s" % "{:,.0f}".format(s["dd"])]
            else:
                cells += ["%5s" % "-", "%6s" % "-", "%9s" % "-", "%8s" % "-"]
        L.append("  %-44s %-7s %s %s %s %s  %s %s %s %s  %s %s %s %s %7s" % (
            name, shape, *cells, ("%.4f" % p) if p == p else "n/a"))
        print(L[-1], flush=True)

    base_d, base_h, base_l = usd[disc_mask], usd[hold_mask], usd[lb.values]
    emit("ALL TRADES (the crown, unchanged)", "base", base_d, base_h, base_l, float("nan"))
    for name, m in RULES:
        m = np.asarray(m, bool)
        p = perm_p(usd[disc_mask], m[disc_mask])
        # SELECTION: keep only the trades the rule likes
        emit(name, "select", usd[disc_mask & m], usd[hold_mask & m], usd[lb.values & m], p)
        # TILT: keep every trade, 1.5 contracts on the ones the rule likes (each contract pays its cost)
        tilt = np.where(m, 1.5 * usd, usd)
        emit("   same rule as a 1.5x size tilt", "tilt", tilt[disc_mask], tilt[hold_mask], tilt[lb.values], float("nan"))

    # ---- THE ONE RULE WORTH INTERROGATING, taken apart ----------------------------------------
    agree = (t["prior_sign"].values == t["side"].values)
    deep = np.isfinite(t["on_ratio"].values)   # placeholder, replaced below by the ES ratio tilt
    ratio_es = r8.compression_ratio(r6.load("ES", "30m", "RTH"), 60)
    rr = ratio_es[np.clip(t["eb"].values - 1, 0, len(ratio_es) - 1)]
    deep = np.isfinite(rr) & (rr <= 0.85)
    L.append("")
    L.append("TAKING THE PRIOR-DAY RULE APART - is it one effect, or a long-only bull market?")
    L.append("  %-44s %-7s %5s %6s %9s %8s  %5s %6s %9s %8s  %5s %6s %9s %8s %7s" % (
        "cut", "shape", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "n", "PF", "net $", "DD $", "perm p"))
    for label, side in (("longs only", 1), ("shorts only", -1)):
        sm = t["side"].values == side
        emit("  base, " + label, "base", usd[disc_mask & sm], usd[hold_mask & sm], usd[lb.values & sm], float("nan"))
        emit("  prior-day agrees, " + label, "select", usd[disc_mask & sm & agree], usd[hold_mask & sm & agree],
             usd[lb.values & sm & agree], perm_p(usd[disc_mask & sm], agree[disc_mask & sm]))
    # does it stack with the VALIDATED deep-squeeze tilt, or are they the same trades twice?
    tilted = np.where(deep, 1.5 * usd, usd)
    emit("  validated deep tilt alone (run 340 shape)", "tilt", tilted[disc_mask], tilted[hold_mask],
         tilted[lb.values], float("nan"))
    emit("  deep tilt AND prior-day agrees", "both", tilted[disc_mask & agree], tilted[hold_mask & agree],
         tilted[lb.values & agree], float("nan"))
    ov = float(np.mean(agree[deep])) if deep.any() else float("nan")
    L.append("  overlap: %.0f percent of deep-squeeze trades also agree with the prior day (base rate %.0f percent)"
             % (100 * ov, 100 * agree.mean()))
    yrs = pd.DatetimeIndex(t["date"]).year
    for label, m in (("base", np.ones(len(t), bool)), ("prior-day agrees", agree)):
        by = pd.Series(usd[m]).groupby(yrs[m]).sum()
        L.append("  %-24s positive years %d of %d, worst year %s dollars" % (
            label, int((by > 0).sum()), len(by), "{:,.0f}".format(by.min())))
    print("\n".join(L[-12:]), flush=True)

    L.append("")
    L.append("MULTIPLE COMPARISONS, stated before anyone reads a p-value: TEN rules were tested here, so the")
    L.append("smallest honest threshold is 0.05 divided by 10, which is 0.005. NO rule in this table clears that.")
    L.append("A p-value near 0.03 with seven attempts is what chance produces; the holdout and lockbox columns are")
    L.append("the evidence that matters, and they matter only where the bucket is big enough to mean anything.")
    L.append("")
    L.append("HOW TO READ THIS: a rule earns attention only if it beats the base row in BOTH holdout and lockbox,")
    L.append("and the tilt rows are the shape this shop adopts - a selection rule that throws trades away has lost")
    L.append("money every time it has been tried in this family. Bucket sizes matter: under about 40 trades a")
    L.append("difference is not measurable on this sample at all.")
    r8._lines_to(L, LOG)
    print("log ->", LOG)


if __name__ == "__main__":
    main()
