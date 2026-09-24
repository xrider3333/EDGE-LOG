"""
SECTOR DIP round 1 - do the DIP book's dip-buy rules WIDEN onto the nine S&P sector funds? (2026-09-24)

WHY. SECTOR round 1 (tools/sec1_sector_triage.py) closed sector ROTATION: 0 of 33 momentum/reversal cells beat
equal-weight. The one daily-scale thing that has worked here is the DIP weak-edge book (r25), and its key lesson was
that leg-level performance does not persist - only diversification does. So the honest question is not "which
sector dips best" (that is leg picking) but "does adding ALL nine sectors as legs make the DIP pool better per unit
of risk, or are sector dips the same days as QQQ/IWM dips?"

RULES - the two close-only DIP rules at their FILE DEFAULTS, no tuning (PB20 needs daily lows the sector cache
does not carry, so it is out on both sides of the comparison):
  RSI2 : Wilder RSI(2) < 10 while close > SMA200 -> buy next open; exit next open after a close above SMA5.
  DBL7 : close = lowest close of 7 days while close > SMA200 -> buy next open; exit next open after the 7-day high.
Long only, $100,000 per position, one position per leg, 2 bp round trip. Daily mark-to-market PnL.

POOLS. A = the four DIP ETFs (GLD TLT IWM QQQ) x 2 rules = 8 legs. B = A + 9 sectors x 2 rules = 26 legs.
S = the 18 sector legs alone. Pools are compared per unit of risk (Sharpe of daily PnL, and MAR on a pool scaled
to A's average dollars at work), never on raw dollars - B simply holds more money.

SELECTION WINDOW 2001-01-01 .. 2025-06-30 (warm-up 2000), the last 15 months are not read.

PRE-REGISTERED BAR - SECTOR DIP is PROMISING only if ALL hold:
  1. timing is real: S's dollars per unit-day at work beat buy-and-hold of the same sectors by >= 1.5x
     (DIP on NQ/ES was ~2x);
  2. plateau: at least 12 of the 18 sector legs are net positive;
  3. it widens the book: B's Sharpe beats A's by >= 10%, AND B beats A on Sharpe in all three eras
     2001-2008, 2009-2016, 2017-2025H1;
  4. not one year: B's excess over A (exposure-matched) survives removing its best calendar year.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays

CACHE = r"C:\EdgeLog\_research_cache"
SECT = ["XLK", "XLF", "XLE", "XLV", "XLY", "XLP", "XLI", "XLU", "XLB"]
ETFS = ["GLD", "TLT", "IWM", "QQQ"]
SEL0, SEL1 = "2001-01-01", "2025-06-30"
ERAS = [("2001-01-01", "2008-12-31"), ("2009-01-01", "2016-12-31"), ("2017-01-01", SEL1)]
NOTIONAL, COST = 100000.0, 0.0002


def load_etf(sym):
    m = find_master(sym, "1d", "rth", "yahoo_adj") or find_master(sym, "1d", None, "yahoo_adj")
    A = load_master_arrays(m)
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
    return pd.DataFrame({"o": A["open"], "c": A["close"]}, index=idx)


SO = pd.read_csv(os.path.join(CACHE, "sector_open.csv"), index_col=0, parse_dates=True)
SC = pd.read_csv(os.path.join(CACHE, "sector_close.csv"), index_col=0, parse_dates=True)
DATA = {s: pd.DataFrame({"o": SO[s], "c": SC[s]}).dropna() for s in SECT}
for s in ETFS:
    DATA[s] = load_etf(s)
DAYS = pd.DatetimeIndex(sorted(set(SC.index) & set(DATA["QQQ"].index)))
DAYS = DAYS[(DAYS >= "2000-01-01") & (DAYS <= SEL1)]


def rsi_wilder(c, n):
    d = np.diff(c, prepend=c[0]); up = np.clip(d, 0, None); dn = np.clip(-d, 0, None)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values
    ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + au / np.where(ad == 0, 1e-12, ad))


def leg(sym, rule):
    """Daily $ PnL and a 0/1 in-market series on DAYS (NaN days = not listed yet -> flat)."""
    df = DATA[sym].reindex(DAYS)
    o, c = df.o.values, df.c.values
    sma200 = pd.Series(c).rolling(200).mean().values
    if rule == "RSI2":
        r = rsi_wilder(np.nan_to_num(c, nan=np.nanmean(c)), 2); sma5 = pd.Series(c).rolling(5).mean().values
    else:
        lo7 = pd.Series(c).rolling(7).min().values; hi7 = pd.Series(c).rolling(7).max().values
    pnl = np.zeros(len(c)); inm = np.zeros(len(c))
    pos = 0.0; sh = 0.0; pend = 0  # pend +1 = buy next open, -1 = sell next open
    for t in range(1, len(c)):
        if np.isnan(c[t]) or np.isnan(c[t - 1]) or np.isnan(o[t]):
            continue
        if pend == 1:
            sh = NOTIONAL / o[t]; pos = 1
            pnl[t] += sh * (c[t] - o[t]) - NOTIONAL * COST / 2
            pend = 0
        elif pend == -1:
            pnl[t] += sh * (o[t] - c[t - 1]) - sh * o[t] * COST / 2
            pos = 0; sh = 0.0; pend = 0
        elif pos:
            pnl[t] += sh * (c[t] - c[t - 1])
        inm[t] = pos
        if t < 210 or np.isnan(sma200[t]):
            continue
        if not pos:
            sig = (r[t] < 10 and c[t] > sma200[t]) if rule == "RSI2" else (c[t] <= lo7[t] and c[t] > sma200[t])
            if sig:
                pend = 1
        else:
            ex = (c[t] > sma5[t]) if rule == "RSI2" else (c[t] >= hi7[t])
            if ex:
                pend = -1
    return pd.Series(pnl, index=DAYS), pd.Series(inm, index=DAYS)


def bh(sym):
    c = DATA[sym].c.reindex(DAYS)
    return (c.pct_change().fillna(0) * NOTIONAL)


def win(s, lo, hi):
    return s[(s.index >= pd.Timestamp(lo)) & (s.index <= pd.Timestamp(hi))]


def sharpe(p):
    return float(p.mean() / p.std() * np.sqrt(252)) if p.std() > 0 else 0.0


def dd(p):
    cu = p.cumsum(); return float(-(cu - cu.cummax()).min())


if __name__ == "__main__":
    legs = {}
    for s in SECT + ETFS:
        for rule in ("RSI2", "DBL7"):
            legs[(s, rule)] = leg(s, rule)
    print("LEG                net $     trades-days  $/unit-day  bh $/unit-day")
    sect_rows = []
    for (s, rule), (p, m) in legs.items():
        pw, mw = win(p, SEL0, SEL1), win(m, SEL0, SEL1)
        b = win(bh(s), SEL0, SEL1)
        per = pw.sum() / max(mw.sum(), 1); bper = b.sum() / len(b)
        print(f"  {s:4} {rule}   ${pw.sum():>10,.0f}   {int(mw.sum()):>6}      ${per:>7.1f}     ${bper:>7.1f}")
        if s in SECT:
            sect_rows.append(dict(sym=s, rule=rule, net=pw.sum(), days=mw.sum(), per=per, bhper=bper))
    R = pd.DataFrame(sect_rows)
    timing = R.net.sum() / R.days.sum() / (R.bhper.mean())
    plateau = int((R.net > 0).sum())

    def pool(keys):
        p = sum(legs[k][0] for k in keys); m = sum(legs[k][1] for k in keys)
        return win(p, SEL0, SEL1), win(m, SEL0, SEL1)
    KA = [(s, r) for s in ETFS for r in ("RSI2", "DBL7")]
    KS = [(s, r) for s in SECT for r in ("RSI2", "DBL7")]
    pa, ma = pool(KA); pb, mb = pool(KA + KS); ps, ms = pool(KS)
    scale = ma.mean() / mb.mean()                  # B scaled to A's average legs at work
    pbs = pb * scale
    yrs = (pa.index[-1] - pa.index[0]).days / 365.25
    print(f"\nPOOL A (4 ETFs x 2)  net ${pa.sum():,.0f}  Sharpe {sharpe(pa):.2f}  DD ${dd(pa):,.0f}  MAR {pa.sum()/yrs/dd(pa):.2f}  avg legs at work {ma.mean():.2f}")
    print(f"POOL S (9 sectors x 2) net ${ps.sum():,.0f}  Sharpe {sharpe(ps):.2f}  DD ${dd(ps):,.0f}  MAR {ps.sum()/yrs/dd(ps):.2f}  avg legs at work {ms.mean():.2f}")
    print(f"POOL B (all 26) scaled x{scale:.2f}: net ${pbs.sum():,.0f}  Sharpe {sharpe(pb):.2f}  DD ${dd(pbs):,.0f}  MAR {pbs.sum()/yrs/dd(pbs):.2f}")
    print(f"corr daily PnL A vs S: {pa.corr(ps):.2f}")
    era = [(sharpe(win(pa, *e)), sharpe(win(pb, *e))) for e in ERAS]
    print("eras Sharpe A -> B: " + "  ".join(f"{a:.2f}->{b:.2f}" for a, b in era))
    exc = (pbs - pa).groupby(pa.index.year).sum()
    print("calendar-year excess of scaled B over A: " + " ".join(f"{y}:{v/1000:+.0f}k" for y, v in exc.items()))
    c1 = timing >= 1.5
    c2 = plateau >= 12
    c3 = sharpe(pb) >= 1.10 * sharpe(pa) and all(b > a for a, b in era)
    c4 = (exc.sum() - exc.max()) > 0
    print(f"\n1 timing x{timing:.2f} (needs 1.5): {'PASS' if c1 else 'FAIL'}")
    print(f"2 plateau {plateau}/18 sector legs positive (needs 12): {'PASS' if c2 else 'FAIL'}")
    print(f"3 widens the book: Sharpe {sharpe(pa):.2f} -> {sharpe(pb):.2f} (needs +10%) and all eras: {'PASS' if c3 else 'FAIL'}")
    print(f"4 not one year: {'PASS' if c4 else 'FAIL'}")
    print("VERDICT:", "PROMISING" if (c1 and c2 and c3 and c4) else "DEAD")
    os.makedirs("tools/r16_results", exist_ok=True)
    R.to_csv("tools/r16_results/secdip1_sector_dip_triage.csv", index=False)
