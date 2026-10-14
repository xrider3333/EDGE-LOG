"""N2 power, regime-aware: the failed-break share in rolling windows of #422's WF trades (no lockbox, no forward rows)."""
import numpy as np, pandas as pd
import noise_next3_power as P
T, _, _ = P.trades()
f = (T.kind == "vwap").to_numpy().astype(float)
yrs = pd.DatetimeIndex(T.date).year
print("WF failed share %.3f; by calendar year:" % f.mean(), {y: round(f[yrs == y].mean(), 3) for y in sorted(set(yrs))})
for w in (60, 120, 240):
    r = pd.Series(f).rolling(w).mean().dropna().to_numpy()
    lo = np.percentile(r, 97.5)
    # a +10-point shift in the true share, read on the same WF window spread
    det = (r + 0.10 >= lo).mean()
    print("  window %3d trades (%.1f months): share p50 %.3f p97.5 %.3f p99 %.3f | +10 pts clears p97.5 in %.0f%% of windows"
          % (w, 12 * w / (len(T) / P.YRS), np.median(r), lo, np.percentile(r, 99), 100 * det))
