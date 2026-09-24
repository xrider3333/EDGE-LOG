r"""
NON-EQUITY DIP round 1 - can DIP's dip-buy rules widen the DIP book with a DIFFERENT return stream? (2026-09-24)

SECTOR DIP r1 (tools/secdip1_sector_dip_triage.py) proved sector dips are real (17/18 legs positive) but they are
the SAME days as the QQQ/IWM dips (daily corr 0.76) - no widening. The lesson: a widener must come from outside
equities. Universe, fixed before any run: rates IEF, TIP; commodities SLV, DBC, USO; currencies UUP, FXE, FXY, FXA
(Yahoo, dividend-adjusted, cached in C:\EdgeLog\_research_cache\nonequity_*.csv). SHY is excluded up front
(near-riskless, not a dip market).

RULES - identical to SECTOR DIP: RSI2 (<10 above SMA200, exit close > SMA5) and DBL7 (7-day closing low above
SMA200, exit 7-day closing high), file defaults, long only, next-open fills, 2 bp round trip.
SIZING: pool A (GLD TLT IWM QQQ) keeps the book's $100,000 per position. The new legs are RISK-MATCHED, because a
currency fund moves a fraction of QQQ: notional = $100,000 x (median trailing-60-day vol of the four A funds /
the new fund's trailing-60-day vol), measured on the signal day (causal), capped at 4x.

SELECTION WINDOW 2008-01-01 .. 2025-06-30 (every fund listed + 200-day warm-up by then); last 15 months not read.

PRE-REGISTERED BAR - NON-EQUITY DIP is PROMISING only if ALL hold:
  1. timing is real: the new legs' dollars per unit-day beat risk-matched buy-and-hold by >= 1.5x;
  2. plateau: at least 12 of the 18 new legs net positive;
  3. it widens the book: exposure-matched pool B (A + new) Sharpe beats A by >= 10%, AND beats A in all three eras
     2008-2013, 2014-2019, 2020-2025H1;
  4. not one year: B's exposure-matched excess over A survives removing its best calendar year.
"""
import os, sys
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from augur_engine.data import find_master, load_master_arrays

CACHE = r"C:\EdgeLog\_research_cache"
SECT = ["IEF", "TIP", "SLV", "DBC", "USO", "UUP", "FXE", "FXY", "FXA"]
ETFS = ["GLD", "TLT", "IWM", "QQQ"]
SEL0, SEL1 = "2008-01-01", "2025-06-30"
ERAS = [("2008-01-01", "2013-12-31"), ("2014-01-01", "2019-12-31"), ("2020-01-01", SEL1)]
NOTIONAL, COST = 100000.0, 0.0002


def load_etf(sym):
    m = find_master(sym, "1d", "rth", "yahoo_adj") or find_master(sym, "1d", None, "yahoo_adj")
    A = load_master_arrays(m)
    idx = pd.DatetimeIndex(A["index"]).tz_localize(None).normalize()
    return pd.DataFrame({"o": A["open"], "c": A["close"]}, index=idx)


SO = pd.read_csv(os.path.join(CACHE, "nonequity_open.csv"), index_col=0, parse_dates=True)
SC = pd.read_csv(os.path.join(CACHE, "nonequity_close.csv"), index_col=0, parse_dates=True)
DATA = {s: pd.DataFrame({"o": SO[s], "c": SC[s]}).dropna() for s in SECT}
for s in ETFS:
    DATA[s] = load_etf(s)
DAYS = pd.DatetimeIndex(sorted(set(SC.index) & set(DATA["QQQ"].index)))
DAYS = DAYS[(DAYS >= "2006-01-01") & (DAYS <= SEL1)]


def rsi_wilder(c, n):
    d = np.diff(c, prepend=c[0]); up = np.clip(d, 0, None); dn = np.clip(-d, 0, None)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values
    ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + au / np.where(ad == 0, 1e-12, ad))


VOL = {k: DATA[k].c.reindex(DAYS).pct_change().rolling(60).std() for k in DATA}
REFVOL = pd.concat([VOL[k] for k in ETFS], axis=1).median(axis=1)


def size(sym, t):
    if sym in ETFS:
        return NOTIONAL
    v, r = VOL[sym].iloc[t], REFVOL.iloc[t]
    if not (v > 0 and r > 0):
        return NOTIONAL
    return NOTIONAL * min(4.0, r / v)


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
            nt = size(sym, t - 1); sh = nt / o[t]; pos = 1
            pnl[t] += sh * (c[t] - o[t]) - nt * COST / 2
            pend = 0
        elif pend == -1:
            pnl[t] += sh * (o[t] - c[t - 1]) - sh * o[t] * COST / 2
            pos = 0; sh = 0.0; pend = 0
        elif pos:
            pnl[t] += sh * (c[t] - c[t - 1])
        inm[t] = pos * (sh * c[t] / NOTIONAL if pos else 0)
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
    n = pd.Series([size(sym, t) for t in range(len(DAYS))], index=DAYS).shift(1).fillna(NOTIONAL)
    return (c.pct_change().fillna(0) * n)


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
    print("LEG (unit-day = $100k at work for a day)   net $     trades-days  $/unit-day  bh $/unit-day")
    sect_rows = []
    for (s, rule), (p, m) in legs.items():
        pw, mw = win(p, SEL0, SEL1), win(m, SEL0, SEL1)
        b = win(bh(s), SEL0, SEL1)
        per = pw.sum() / max(mw.sum(), 1)
        units = win(pd.Series([size(s, t) for t in range(len(DAYS))], index=DAYS), SEL0, SEL1) / NOTIONAL
        bper = b.sum() / units.sum()
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
    print(f"POOL N (9 non-equity x 2) net ${ps.sum():,.0f}  Sharpe {sharpe(ps):.2f}  DD ${dd(ps):,.0f}  MAR {ps.sum()/yrs/dd(ps):.2f}  avg legs at work {ms.mean():.2f}")
    print(f"POOL B (all 26) scaled x{scale:.2f}: net ${pbs.sum():,.0f}  Sharpe {sharpe(pb):.2f}  DD ${dd(pbs):,.0f}  MAR {pbs.sum()/yrs/dd(pbs):.2f}")
    print(f"corr daily PnL A vs N: {pa.corr(ps):.2f}")
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
    R.to_csv("tools/r16_results/secdip2_nonequity_dip_triage.csv", index=False)
