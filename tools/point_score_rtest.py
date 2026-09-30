"""point_score_rtest.py - the PRE-REGISTERED backfill test for the POINT SCORE (docs/POINT_SCORE_SPEC.md s.5).

Reads the scores written by `python tools/point_score.py backfill` (one row per real futures trade, no
outcomes) and computes, exactly as pre-registered on main in 9b7c89b9 (docs/POINT_SCORE_SPEC.md s.5) before any score met any result:

  R        = side x (exit - entry) / risk, risk = |entry - stop|, stop = drawn stop > journal stop >
             signal-bar low (long) / high (short); risk <= 0 excluded and listed.
  pts      = side x (exit - entry)   (points per contract, needs no stop)
  pct      = total / max over the 9 points (trend separate)
  PRIMARY  = Spearman(pct, R) with a bootstrap 95% CI (10,000 resamples, seed 0)
  SECONDARY= top vs bottom half by pct (median split, ties at the median -> bottom): mean R, win rate
             (R > 0), and mean pts
  EXPLORATORY (flagged, 9 comparisons): per point hit rate and mean R hit vs miss; points by time of
             day (09:30-09:59, 10:00-11:59, 12:00-16:00); the trend point vs R.

    python tools/point_score_rtest.py [--scores C:\\EdgeLog\\point_score\\backfill_scores.csv]
"""
import argparse
import numpy as np
import pandas as pd

POINTS = ['ma200_10s', 'ma200_1m', 'ma200_5m', 'ma200_30m', 'y_low', 'y_close', 'y_high', 'big_body', 'big_vol']


def spearman(x, y):
    rx = pd.Series(x).rank().to_numpy(); ry = pd.Series(y).rank().to_numpy()
    if np.std(rx) == 0 or np.std(ry) == 0:
        return float('nan')
    return float(np.corrcoef(rx, ry)[0, 1])


def boot_ci(x, y, n=10000, seed=0):
    rng = np.random.default_rng(seed)
    x = np.asarray(x); y = np.asarray(y); k = len(x); out = []
    for _ in range(n):
        i = rng.integers(0, k, k)
        v = spearman(x[i], y[i])
        if np.isfinite(v):
            out.append(v)
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def pick_stop(r):
    for c in ('drawn_stop', 'journal_stop'):
        v = r.get(c)
        if pd.notna(v) and str(v).strip() != '':
            return float(v), c
    c = 'sig_low' if r['side'] == 'LONG' else 'sig_high'
    off = r.get('px_offset'); off = float(off) if pd.notna(off) else 0.0
    return float(r[c]) + off, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scores', default=r'C:\EdgeLog\point_score\backfill_scores.csv')
    a = ap.parse_args()
    d = pd.read_csv(a.scores)
    sgn = np.where(d.side.str.upper() == 'LONG', 1.0, -1.0)
    stops = d.apply(pick_stop, axis=1)
    d['stop_used'] = [s[0] for s in stops]; d['stop_src'] = [s[1] for s in stops]
    d['risk'] = (d.entry - d.stop_used).abs()
    d['pts'] = sgn * (d.exit - d.entry)
    d['R'] = np.where(d.risk > 0, d.pts / d.risk.replace(0, np.nan), np.nan)
    d['pct'] = d.total / d['max']
    bad = d[~(d.risk > 0) | d.pct.isna()]
    ok = d[(d.risk > 0) & d.pct.notna()].copy()
    print('trades %d, used %d, excluded %d' % (len(d), len(ok), len(bad)))
    for _, r in bad.iterrows():
        print('  excluded:', r.trade_id, r.date, r.sym, r.side, 'risk', r.risk, 'pct', r.pct)
    print('stop source:', ok.stop_src.value_counts().to_dict())
    print('R: mean %.3f median %.3f sd %.3f' % (ok.R.mean(), ok.R.median(), ok.R.std()))

    rho = spearman(ok.pct, ok.R); lo, hi = boot_ci(ok.pct.to_numpy(), ok.R.to_numpy())
    print('\nPRIMARY  Spearman(pct, R) = %.3f  95%% CI [%.3f, %.3f]  n=%d' % (rho, lo, hi, len(ok)))
    rho2 = spearman(ok.pct, ok.pts); lo2, hi2 = boot_ci(ok.pct.to_numpy(), ok.pts.to_numpy())
    print('         Spearman(pct, points/contract) = %.3f  95%% CI [%.3f, %.3f]' % (rho2, lo2, hi2))

    med = ok.pct.median()
    top = ok[ok.pct > med]; bot = ok[ok.pct <= med]
    print('\nSECONDARY median pct %.3f: top n=%d mean R %.3f win %.0f%% pts %.2f | bottom n=%d mean R %.3f win %.0f%% pts %.2f'
          % (med, len(top), top.R.mean(), 100 * (top.R > 0).mean(), top.pts.mean(),
             len(bot), bot.R.mean(), 100 * (bot.R > 0).mean(), bot.pts.mean()))
    se = np.sqrt(top.R.var() / max(len(top), 1) + bot.R.var() / max(len(bot), 1))
    print('          top - bottom mean R = %.3f (+- %.3f at 95%%)' % (top.R.mean() - bot.R.mean(), 1.96 * se))

    print('\nEXPLORATORY (9 comparisons - expect ~0.5 false "differences" by luck):')
    for p in POINTS:
        h = ok[p + '_hit']
        hit = ok[h == 1]; miss = ok[h == 0]
        print('  %-10s hit %2d miss %2d NA %2d | mean R hit %6.3f miss %6.3f'
              % (p, len(hit), len(miss), int(h.isna().sum()), hit.R.mean() if len(hit) else np.nan,
                 miss.R.mean() if len(miss) else np.nan))
    hm = pd.to_datetime(ok.signal_bar).dt.strftime('%H:%M')
    band = np.where(hm < '10:00', '09:30-09:59', np.where(hm < '12:00', '10:00-11:59', '12:00-16:00'))
    ok['band'] = band
    print('\n  by time of day (signal bar):')
    print(ok.groupby('band').agg(n=('R', 'size'), mean_pct=('pct', 'mean'), mean_R=('R', 'mean')).round(3).to_string())
    if 'd_trend_hit' in ok:
        t = ok['d_trend_hit']
        print('\n  trend point: hit %d mean R %.3f | miss %d mean R %.3f | NA %d'
              % ((t == 1).sum(), ok[t == 1].R.mean(), (t == 0).sum(), ok[t == 0].R.mean(), t.isna().sum()))
    print('\n  score distribution (total/max):', ok.apply(lambda r: '%d/%d' % (r.total, r['max']), axis=1).value_counts().sort_index().to_dict())


if __name__ == '__main__':
    main()
