#!/usr/bin/env python3
"""
NOISE 2026-08-17 campaign -- PnL ATTRIBUTION + ES-TRANSFER comparison.

WHAT THIS ANSWERS
-----------------
The campaign results table in NOISE.md says WHAT each filter variant scored.
It does not say WHY. This script diffs each variant's trade list against the
#231 champion's, trade by trade, and decomposes the net delta into:

    delta = (-1 x PnL of trades the filter REMOVED)
          + (      PnL of trades the filter ADDED  )
          + (      PnL change on trades it ALTERED )

  REMOVED  a baseline trade whose entry bar the variant never enters.
  ADDED    a variant trade at an entry bar the baseline never enters. These are
           REAL and unavoidable: blocking an entry leaves the strategy flat, so
           a later signal in the SAME session that the baseline slept through
           (it was already in a position) now gets taken. A pure-veto filter is
           NOT purely subtractive.
  ALTERED  same entry bar, different exit bar / PnL. (Only possible for the
           regime knobs that change exits or stops; the entry filters here
           leave exits untouched, so ALTERED is normally 0.)

`confirm_bars` is a DELAY, not a veto: the same session signal fires N bars
later, so one baseline trade shows up as one REMOVED + one ADDED. The script
labels each variant's mechanism (veto / delay) from that removed-vs-added mix,
so the two are never read as if they were the same kind of change.

Also computed per variant: delta by SIDE, delta by YEAR, drawdown attribution
against the BASELINE's worst peak-to-trough stretch, and two CONCENTRATION
ratios that say whether the improvement is broad or is a handful of trades:
    - share of the improvement contributed by its single best year
    - share contributed by its 10 most-negative removed trades

ES TRANSFER
-----------
Same configs, same code path, on the ES 5m RTH no-adj master -- an independent
arbiter, because NOISE's own lockbox is SPENT. Reported in POINTS (the campaign
convention) and in dollars at the ES multiplier 50 (NQ is 20). Costs stay at
0.533 pts/trade, matching the campaign's ES probe.

Two pass bars exist and they are NOT the same (see NOISE.md caveat 3):
    - the engine's GENERIC cross-instrument sanity check: PF >= 1.0
    - NOISE's OWN pre-registered promotion bar:            PF >= 1.2
This script scores against BOTH and names which is which.

Source PINNED: db_noadj_rth - NQ/ES 5m rth - cost_pts 0.533 - NQ mult 20 /
ES mult 50. No master import/refresh, no runner jobs -- local library calls.

    python tools/noise_attribution.py            # gates + all tables
    python tools/noise_attribution.py --check    # reconciliation gates only
    python tools/noise_attribution.py --json out.json
"""
import os
import sys
import json
import argparse

EDGELOG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if EDGELOG_ROOT not in sys.path:
    sys.path.insert(0, EDGELOG_ROOT)

from augur_engine.data import find_master, load_master_arrays              # noqa: E402
from tools.noise_variant_research import run_variant, CHAMPION, FEE        # noqa: E402

NQ_MULT, ES_MULT = 20.0, 50.0
SEL_FROM, SEL_TO = "2010-06-07", "2025-02-10"   # run #231 optimize window (selection)
FULL_TO = "2026-08-12"                          # confirmatory, includes the SPENT lockbox


def C(**kw):
    return dict(CHAMPION, **kw)


def VS(pct):
    """NOISE_1_0's `vol_skip_pct` knob == the harness's skip_hi vol-regime mode."""
    return dict(rv_mode="skip_hi", rv_pct=float(pct))


# key, label, short mechanism note, params
VARIANTS = [
    ("base",  "#231 champion (baseline)",           "all filter knobs OFF", C()),
    ("B4-bs", "skip_bot_short",                     "no SHORTs the day after a bottom-20% close",
     C(daytype_mode="skip_bot_short")),
    ("D2",    "skip_bot_short + vol_skip 90",       "that, plus skip the day after a top-decile-vol session",
     C(daytype_mode="skip_bot_short", **VS(90))),
    ("A2-98", "vol_skip 98",                        "skip the day after a top-2% vol session", C(**VS(98))),
    ("D3",    "confirm2 + skip_bot_short (WINNER)", "2 closes outside the band, and no shorts after a weak close",
     C(confirm_bars=2, daytype_mode="skip_bot_short")),
    ("A2-95", "vol_skip 95",                        "skip the day after a top-5% vol session", C(**VS(95))),
    ("A2-90", "vol_skip 90",                        "skip the day after a top-decile-vol session", C(**VS(90))),
    ("B4-tl", "skip_top_long (DEAD)",               "no LONGs the day after a top-20% close",
     C(daytype_mode="skip_top_long")),
    ("B1-2",  "confirm_bars 2 (DEAD-ish)",          "wait for 2 consecutive closes outside the band",
     C(confirm_bars=2)),
]
VKEYS = [k for k, _, _, _ in VARIANTS if k != "base"]

# ---------------------------------------------------------------------------
# Reconciliation gates. Every number below is quoted from NOISE.md's committed
# campaign tables; nothing here is published unless the recomputation lands on
# them. (net $, MaxDD $ positive, trades)
# ---------------------------------------------------------------------------
GATE_SEL = {   # NOISE.md "Selection-window cross-reference"
    "base":  (277123, 19482, 5113),
    "D3":    (332699, 14076, 4010),
    "B4-bs": (320530, 18560, 4748),
    "A2-90": (310690, 19041, 4309),
    "A2-95": (302963, 19176, 4697),
    "A2-98": (309055, 19176, 4868),
    "B1-2":  (299099, 18180, 4309),
}
GATE_FULL = {  # NOISE.md "Campaign results table", TOTAL / MaxDD / trades columns
    "base":  (335981, 32794, 5633),
    "B4-bs": (388181, 31191, 5214),
    "D2":    (380745, 22096, 4429),
    "A2-98": (384690, 22334, 5347),
    "D3":    (367959, 37729, 4418),
    "A2-95": (375262, 28873, 5159),
    "A2-90": (372285, 23698, 4732),
    "B4-tl": (280710, 34882, 4527),
    "B1-2":  (320914, 44189, 4762),
}
# The campaign's own ES probe, round log: baseline PF 1.037 / 645 pts ->
# filters PF 1.116 / 1,519 pts, selection window. Checked, not asserted-on
# (the round log rounds; see es_probe_check()).
ES_PROBE = {"base": (1.037, 645.0), "D3": (1.116, 1519.0)}

_ARR = {}


def arrays(sym, date_from, date_to):
    key = (sym, date_from, date_to)
    if key not in _ARR:
        m = find_master(sym, "5m", "rth", "db_noadj_rth")
        if m is None:
            raise SystemExit("NO MASTER for %s/5m/rth/db_noadj_rth" % sym)
        _ARR[key] = load_master_arrays(m, date_from=date_from, date_to=date_to)
    return _ARR[key]


def trades_of(arr, params):
    """One config -> list of per-trade dicts, NET of costs, in entry order."""
    raw = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                      arr.get("volume"), arr["day_id"], **params)
    idx = arr["index"]
    out = []
    for (eb, xb, pnl, pos, epx) in raw:
        out.append(dict(eb=int(eb), xb=int(xb), side=int(pos),
                        pts=float(pnl) - FEE,
                        edt=idx[eb], xdt=idx[xb], year=int(idx[eb].year)))
    return out


def stats(trs, mult):
    """Dollars / PF / DD for a trade list. Same convention as
    tools/noise_campaign_table.stats: peak resets at the first trade of the
    stretch, drawdown returned POSITIVE."""
    if not trs:
        return dict(n=0, net=0.0, pts=0.0, pf=0.0, dd=0.0, mar=0.0,
                    dd_from=None, dd_to=None, win_rate=0.0)
    p = [t["pts"] for t in trs]
    gw = sum(x for x in p if x > 0)
    gl = -sum(x for x in p if x < 0)
    pf = (gw / gl) if gl > 1e-9 else float("inf")
    cum = peak = 0.0
    mdd = 0.0
    peak_i = trough_i = 0
    cur_peak_i = 0
    for i, x in enumerate(p):
        cum += x
        if cum > peak:
            peak = cum
            cur_peak_i = i
        if cum - peak < mdd:
            mdd = cum - peak
            peak_i, trough_i = cur_peak_i, i
    dd = abs(mdd) * mult
    net = sum(p) * mult
    return dict(n=len(p), net=net, pts=sum(p), pf=pf, dd=dd,
                mar=(net / dd) if dd > 1e-9 else float("inf"),
                dd_from=trs[peak_i]["edt"], dd_to=trs[trough_i]["xdt"],
                win_rate=100.0 * sum(1 for x in p if x > 0) / len(p))


def by(trs, keyfn, mult):
    d = {}
    for t in trs:
        d[keyfn(t)] = d.get(keyfn(t), 0.0) + t["pts"] * mult
    return d


def attribute(base, var, mult):
    """Trade-by-trade diff of one variant against the baseline."""
    bmap = {t["eb"]: t for t in base}
    vmap = {t["eb"]: t for t in var}
    removed = [bmap[k] for k in bmap if k not in vmap]
    added = [vmap[k] for k in vmap if k not in bmap]
    altered = [(bmap[k], vmap[k]) for k in bmap
               if k in vmap and (bmap[k]["xb"] != vmap[k]["xb"]
                                 or abs(bmap[k]["pts"] - vmap[k]["pts"]) > 1e-9)]
    removed.sort(key=lambda t: t["eb"])
    added.sort(key=lambda t: t["eb"])

    bs, vs = stats(base, mult), stats(var, mult)
    delta = vs["net"] - bs["net"]
    rm_pnl = sum(t["pts"] for t in removed) * mult
    ad_pnl = sum(t["pts"] for t in added) * mult
    al_pnl = sum(v["pts"] - b["pts"] for b, v in altered) * mult
    recon = (-rm_pnl) + ad_pnl + al_pnl

    # mechanism label: a veto removes and adds little back; a delay swaps 1-for-1
    mech = "veto"
    if removed and len(added) >= 0.5 * len(removed):
        mech = "delay+veto" if len(added) < 0.9 * len(removed) else "delay"

    def split(trs):
        L = [t for t in trs if t["side"] > 0]
        S = [t for t in trs if t["side"] < 0]
        return len(L), len(S), sum(t["pts"] for t in L) * mult, sum(t["pts"] for t in S) * mult

    rmL, rmS, rmLp, rmSp = split(removed)
    adL, adS, adLp, adSp = split(added)

    bside, vside = by(base, lambda t: t["side"], mult), by(var, lambda t: t["side"], mult)
    byear, vyear = by(base, lambda t: t["year"], mult), by(var, lambda t: t["year"], mult)
    years = sorted(set(byear) | set(vyear))
    dyear = {y: vyear.get(y, 0.0) - byear.get(y, 0.0) for y in years}

    # drawdown attribution: what the variant did across the BASELINE's worst stretch
    d0, d1 = bs["dd_from"], bs["dd_to"]
    b_in = [t for t in base if d0 <= t["edt"] <= d1]
    v_in = [t for t in var if d0 <= t["edt"] <= d1]
    r_in = [t for t in removed if d0 <= t["edt"] <= d1]

    # ... and the mirror image: what the BASELINE did across the VARIANT's own
    # worst stretch (a variant can invent a drawdown the baseline never had).
    e0, e1 = vs["dd_from"], vs["dd_to"]
    vb_in = [t for t in base if e0 <= t["edt"] <= e1]
    vv_in = [t for t in var if e0 <= t["edt"] <= e1]

    # concentration
    worst10 = sorted(removed, key=lambda t: t["pts"])[:10]
    w10 = -sum(t["pts"] for t in worst10) * mult
    best_year = max(dyear.items(), key=lambda kv: kv[1]) if dyear else (None, 0.0)
    denom = delta if abs(delta) > 1e-9 else float("nan")

    return dict(
        base=bs, var=vs, delta=delta, mech=mech,
        n_removed=len(removed), n_added=len(added), n_altered=len(altered),
        rm_pnl=rm_pnl, ad_pnl=ad_pnl, al_pnl=al_pnl, recon=recon,
        recon_ok=abs(recon - delta) < 1.0,
        rm_avg=(rm_pnl / len(removed)) if removed else 0.0,
        rm_win=(100.0 * sum(1 for t in removed if t["pts"] > 0) / len(removed)) if removed else 0.0,
        rm_long=rmL, rm_short=rmS, rm_long_pnl=rmLp, rm_short_pnl=rmSp,
        ad_long=adL, ad_short=adS, ad_long_pnl=adLp, ad_short_pnl=adSp,
        d_long=vside.get(1, 0.0) - bside.get(1, 0.0),
        d_short=vside.get(-1, 0.0) - bside.get(-1, 0.0),
        dyear=dyear, byear=byear, vyear=vyear,
        dd_from=d0, dd_to=d1,
        dd_base_stretch=sum(t["pts"] for t in b_in) * mult, dd_base_n=len(b_in),
        dd_var_stretch=sum(t["pts"] for t in v_in) * mult, dd_var_n=len(v_in),
        dd_removed_n=len(r_in), dd_removed_pnl=sum(t["pts"] for t in r_in) * mult,
        vdd_base_stretch=sum(t["pts"] for t in vb_in) * mult, vdd_base_n=len(vb_in),
        vdd_var_stretch=sum(t["pts"] for t in vv_in) * mult, vdd_var_n=len(vv_in),
        years_up=sum(1 for v in dyear.values() if v > 0),
        years_dn=sum(1 for v in dyear.values() if v < 0),
        delta_ex_top10=delta - w10,
        best_year=best_year[0], best_year_delta=best_year[1],
        conc_year=best_year[1] / denom, conc_top10=w10 / denom, top10_pnl=w10,
        worst10=[(str(t["edt"]), "L" if t["side"] > 0 else "S", t["pts"] * mult) for t in worst10],
    )


def top_years(dyear, k=3):
    return sorted(dyear.items(), key=lambda kv: -abs(kv[1]))[:k]


def driver_sentence(key, a):
    """The one-liner meant for a results-table 'what drove it' column.

    Two shapes, because the two mechanisms are not comparable:
      VETO  -> name the side that carries most of the removed PnL, its count and
               its average, then where in time the delta sits.
      DELAY -> a veto sentence would lie (nearly every trade is swapped for a
               later one), so name the swap and where the delta lands instead.
    """
    # rank years by contribution IN THE DIRECTION OF THE DELTA -- ranking by
    # absolute size pairs a big gain year with a big give-back year and the
    # share then reads as ~0%, which is not what "dominant years" means.
    sgn = 1.0 if a["delta"] >= 0 else -1.0
    ty = [y for y, _ in sorted(a["dyear"].items(), key=lambda kv: -sgn * kv[1])[:2]]
    yrs = " and ".join(str(y) for y in ty)
    sign = "+" if a["delta"] >= 0 else "-"
    d = "%s$%s" % (sign, format(abs(a["delta"]), ",.0f"))
    if a["mech"] == "veto":
        # dominant side = the one carrying the larger |removed PnL|
        if abs(a["rm_short_pnl"]) >= abs(a["rm_long_pnl"]):
            side, n, tot = "shorts", a["rm_short"], a["rm_short_pnl"]
        else:
            side, n, tot = "longs", a["rm_long"], a["rm_long_pnl"]
        avg = (tot / n) if n else 0.0
        return ("cuts %d %s that averaged %s$%s each (%d trades cut in total, "
                "%.0f%% of them winners); net %s, %.0f%% of it in %s"
                % (n, side, "-" if avg < 0 else "+", format(abs(avg), ",.0f"),
                   a["n_removed"], a["rm_win"], d,
                   100 * sum(a["dyear"].get(y, 0) for y in ty) / (a["delta"] or float("nan")),
                   yrs))
    return ("swaps %d entries for %d later ones (a DELAY, not a cut; net %+d trades); "
            "net %s, %.0f%% of it in %s"
            % (a["n_removed"], a["n_added"], a["var"]["n"] - a["base"]["n"], d,
               100 * sum(a["dyear"].get(y, 0) for y in ty) / (a["delta"] or float("nan")),
               yrs))


# combo -> the components it is built from, for the incremental view
INCREMENTAL = [("D3", "B1-2"), ("D3", "B4-bs"), ("D2", "A2-90"), ("D2", "B4-bs")]


# ---------------------------------------------------------------------------
def gate(rows, expect, tag):
    print("\nRECONCILIATION GATE -- %s (vs NOISE.md's committed campaign table)" % tag)
    ok = True
    for k, (net, dd, n) in expect.items():
        s = rows[k]["var"] if k != "base" else rows[k]["base"]
        good = (abs(s["net"] - net) < 1.5 and abs(s["dd"] - dd) < 1.5 and s["n"] == n)
        ok = ok and good
        print("  %-6s net $%-10s vs $%-10s | DD $%-9s vs $%-9s | n %-5d vs %-5d -> %s"
              % (k, format(s["net"], ",.0f"), format(net, ",d"),
                 format(s["dd"], ",.0f"), format(dd, ",d"), s["n"], n,
                 "MATCH" if good else "MISMATCH"))
    print("  %s OVERALL: %s" % (tag, "PASS" if ok else "FAIL"))
    return ok


_TR = {}


def compute(sym, date_to, mult, date_from=None):
    arr = arrays(sym, date_from, date_to)
    tr = {k: trades_of(arr, p) for k, _, _, p in VARIANTS}
    _TR[(sym, date_to)] = (tr, mult)
    rows = {}
    for k, _, _, _ in VARIANTS:
        rows[k] = attribute(tr["base"], tr[k], mult)
    return rows


def print_incremental(sym, date_to, tag):
    """What a COMBO adds ON TOP of each of its own components -- the only honest
    way to read a combo whose components overlap on the same bad days."""
    tr, mult = _TR[(sym, date_to)]
    print("\nINCREMENTAL -- each combo measured against its OWN components (%s)" % tag)
    print("%-24s %-24s %8s %8s %8s %12s %12s %s"
          % ("combo", "vs component", "removed", "added", "d n", "delta $",
             "combo net $", "top years"))
    for combo, comp in INCREMENTAL:
        a = attribute(tr[comp], tr[combo], mult)
        ty = ", ".join("%d %s" % (y, money(v)) for y, v in top_years(a["dyear"], 3))
        print("%-24s %-24s %8d %8d %+8d %12s %12s %s"
              % (label(combo)[:24], label(comp)[:24], a["n_removed"], a["n_added"],
                 a["var"]["n"] - a["base"]["n"], money(a["delta"]),
                 money(a["var"]["net"]), ty))


def label(key):
    for k, lab, _, _ in VARIANTS:
        if k == key:
            return lab
    return key


def note(key):
    for k, _, nt, _ in VARIANTS:
        if k == key:
            return nt
    return ""


def money(x):
    return ("-$" if x < 0 else "$") + format(abs(x), ",.0f")


def print_attribution(rows, tag):
    print("\n" + "=" * 118)
    print("ATTRIBUTION -- %s" % tag)
    print("=" * 118)
    h = ("%-30s %7s %10s %6s %6s %7s %11s %10s %10s %6s %6s"
         % ("variant", "trades", "net $", "PF", "MAR", "d n", "delta $",
            "d long $", "d short $", "yr%", "t10%"))
    print(h)
    print("-" * len(h))
    b = rows["base"]["base"]
    print("%-30s %7d %10s %6.2f %6.2f %7s %11s %10s %10s %6s %6s"
          % ("#231 champion (baseline)", b["n"], money(b["net"]), b["pf"], b["mar"],
             "-", "-", "-", "-", "-", "-"))
    for k in VKEYS:
        a = rows[k]
        v = a["var"]
        print("%-30s %7d %10s %6.2f %6.2f %+7d %11s %10s %10s %5.0f%% %5.0f%%"
              % (label(k), v["n"], money(v["net"]), v["pf"], v["mar"],
                 v["n"] - b["n"], money(a["delta"]), money(a["d_long"]),
                 money(a["d_short"]), 100 * a["conc_year"], 100 * a["conc_top10"]))

    print("\nDECOMPOSITION -- does removed+added+altered tie back to the net delta?")
    print("%-30s %8s %11s %8s %11s %8s %11s %12s %12s %s"
          % ("variant", "removed", "removed $", "added", "added $", "altered",
             "altered $", "sum", "net delta", "tie"))
    for k in VKEYS:
        a = rows[k]
        print("%-30s %8d %11s %8d %11s %8d %11s %12s %12s %s"
              % (label(k), a["n_removed"], money(a["rm_pnl"]), a["n_added"],
                 money(a["ad_pnl"]), a["n_altered"], money(a["al_pnl"]),
                 money(a["recon"]), money(a["delta"]),
                 "OK" if a["recon_ok"] else "**MISMATCH**"))

    print("\nREMOVED-TRADE PROFILE (what the filter actually threw away)")
    print("%-30s %8s %10s %8s %9s %9s %11s %11s %s"
          % ("variant", "removed", "avg $", "win %", "longs", "shorts",
             "long $", "short $", "mechanism"))
    for k in VKEYS:
        a = rows[k]
        print("%-30s %8d %10s %7.1f%% %9d %9d %11s %11s %s"
              % (label(k), a["n_removed"], money(a["rm_avg"]), a["rm_win"],
                 a["rm_long"], a["rm_short"], money(a["rm_long_pnl"]),
                 money(a["rm_short_pnl"]), a["mech"]))

    print("\nDELTA BY YEAR ($)")
    years = sorted(rows["base"]["byear"])
    print("%-30s %s" % ("variant", " ".join("%8d" % y for y in years)))
    print("%-30s %s" % ("BASELINE net", " ".join("%8s" % format(rows["base"]["byear"].get(y, 0), ",.0f")
                                                 for y in years)))
    for k in VKEYS:
        a = rows[k]
        print("%-30s %s" % (label(k),
                            " ".join("%8s" % format(a["dyear"].get(y, 0), ",.0f") for y in years)))

    print("\nDRAWDOWN ATTRIBUTION -- against the BASELINE's worst peak-to-trough stretch")
    print("baseline worst DD %s: %s -> %s (%d baseline trades, %s across it)"
          % (money(b["dd"]), b["dd_from"], b["dd_to"],
             rows["base"]["dd_base_n"], money(rows["base"]["dd_base_stretch"])))
    print("%-30s %10s %12s %12s %10s %10s  %s"
          % ("variant", "own DD $", "in-stretch $", "removed in it", "d DD $",
             "", "own worst DD stretch"))
    for k in VKEYS:
        a = rows[k]
        v = a["var"]
        print("%-30s %10s %12s %6d / %s %10s %10s  %s -> %s"
              % (label(k), money(v["dd"]), money(a["dd_var_stretch"]),
                 a["dd_removed_n"], money(a["dd_removed_pnl"]),
                 money(v["dd"] - b["dd"]), "",
                 v["dd_from"], v["dd_to"]))

    print("\nVARIANT'S OWN WORST STRETCH -- and what the baseline did over the same dates")
    print("%-30s %12s %12s %12s  %s"
          % ("variant", "own DD $", "variant $", "baseline $", "stretch"))
    for k in VKEYS:
        a = rows[k]
        print("%-30s %12s %12s %12s  %s -> %s"
              % (label(k), money(a["var"]["dd"]), money(a["vdd_var_stretch"]),
                 money(a["vdd_base_stretch"]), a["var"]["dd_from"], a["var"]["dd_to"]))

    print("\nCONCENTRATION -- is the edge broad, or a handful of trades?")
    print("%-30s %12s %10s %12s %8s %12s %8s %12s %8s"
          % ("variant", "delta $", "best yr", "best-yr $", "share", "top-10 rm $",
             "share", "delta ex-10", "yrs +/-"))
    for k in VKEYS:
        a = rows[k]
        print("%-30s %12s %10s %12s %7.0f%% %12s %7.0f%% %12s %4d/%-4d"
              % (label(k), money(a["delta"]), a["best_year"],
                 money(a["best_year_delta"]), 100 * a["conc_year"],
                 money(a["top10_pnl"]), 100 * a["conc_top10"],
                 money(a["delta_ex_top10"]), a["years_up"], a["years_dn"]))

    print("\nDRIVER SENTENCES (drop-in 'what drove it' column)")
    for k in VKEYS:
        print("  %-30s %s" % (label(k), driver_sentence(k, rows[k])))


def print_es(rows_sel, rows_full):
    print("\n" + "=" * 118)
    print("ES TRANSFER -- ES 5m RTH no-adj (master 'ES 5m RTH - no-adj'), same 0.533 pts cost, mult 50")
    print("=" * 118)
    for tag, rows in (("SELECTION window 2010-06-07 -> 2025-02-10", rows_sel),
                      ("FULL window 2010-06-07 -> 2026-08-12", rows_full)):
        print("\n%s" % tag)
        h = ("%-30s %7s %10s %11s %7s %10s %7s %8s %8s"
             % ("variant", "trades", "net pts", "net $", "PF", "MaxDD $", "MAR",
                "PF>=1.0", "PF>=1.2"))
        print(h)
        print("-" * len(h))
        order = sorted(rows, key=lambda k: -rows[k]["var"]["pf"] if k != "base"
                       else -rows[k]["base"]["pf"])
        for k in order:
            s = rows[k]["base"] if k == "base" else rows[k]["var"]
            print("%-30s %7d %10.1f %11s %7.3f %10s %7.2f %8s %8s"
                  % (label(k), s["n"], s["pts"], money(s["net"]), s["pf"],
                     money(s["dd"]), s["mar"],
                     "pass" if s["pf"] >= 1.0 else "FAIL",
                     "pass" if s["pf"] >= 1.2 else "FAIL"))
        print("  PF>=1.0 = the engine's GENERIC cross-instrument sanity check.")
        print("  PF>=1.2 = NOISE's OWN pre-registered promotion bar (the one that matters).")


def es_probe_check(rows_sel):
    print("\nES PROBE CROSS-CHECK -- vs the campaign round log (baseline PF 1.037 / 645 pts;"
          " filters PF 1.116 / 1,519 pts)")
    for k, (pf, pts) in ES_PROBE.items():
        s = rows_sel[k]["base"] if k == "base" else rows_sel[k]["var"]
        print("  %-6s PF %.3f vs %.3f | pts %.1f vs %.1f -> %s"
              % (k, s["pf"], pf, s["pts"], pts,
                 "MATCH" if (abs(s["pf"] - pf) < 0.002 and abs(s["pts"] - pts) < 1.0)
                 else "differs"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    print("NOISE variant PnL attribution + ES transfer")
    print("Source PINNED: db_noadj_rth - 5m RTH - cost 0.533 pts - NQ mult 20 / ES mult 50")

    sel = compute("NQ", SEL_TO, NQ_MULT)
    full = compute("NQ", FULL_TO, NQ_MULT)
    g1 = gate(sel, GATE_SEL, "NQ selection window 2010-06-07 -> 2025-02-10")
    g2 = gate(full, GATE_FULL, "NQ full window 2010-06-07 -> 2026-08-12")
    bad = [k for k in VKEYS for r in (sel, full) if not r[k]["recon_ok"]]
    print("\nDECOMPOSITION TIE-BACK: %s%s"
          % ("PASS" if not bad else "FAIL", "" if not bad else " -- " + ",".join(sorted(set(bad)))))
    if not (g1 and g2 and not bad):
        raise SystemExit("RECONCILIATION FAILED -- not publishing numbers")
    if a.check:
        return

    print_attribution(sel, "NQ SELECTION window 2010-06-07 -> 2025-02-10 (pre-lockbox; where the bar was set)")
    print_incremental("NQ", SEL_TO, "selection window")
    print_attribution(full, "NQ FULL window 2010-06-07 -> 2026-08-12 (includes the SPENT lockbox)")
    print_incremental("NQ", FULL_TO, "full window")

    es_sel = compute("ES", SEL_TO, ES_MULT)
    es_full = compute("ES", FULL_TO, ES_MULT)
    es_probe_check(es_sel)
    print_es(es_sel, es_full)

    if a.json:
        def clean(o):
            if isinstance(o, dict):
                return {str(k): clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            if isinstance(o, float) and o in (float("inf"), float("-inf")):
                return None
            if isinstance(o, (int, float, str)) or o is None:
                return o
            return str(o)
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(clean(dict(nq_sel=sel, nq_full=full, es_sel=es_sel, es_full=es_full)),
                      f, indent=1)
        print("\nwrote %s" % a.json)


if __name__ == "__main__":
    main()
