"""Paired Sharpe-ratio difference test of Ledoit & Wolf (2008), "Robust performance hypothesis testing with the Sharpe ratio",
Journal of Empirical Finance 15, 850-859 (reading shelf No. 44).

Two daily P&L series on the SAME days (candidate vs crown). The difference of their Sharpe ratios is tested two ways, both as in the authors'
own reference code:
- HAC: delta-method standard error with a prewhitened Parzen-kernel long-run covariance (Andrews 1991 plug-in bandwidth, VAR(1) prewhitening,
  Andrews & Monahan 1992);
- BOOTSTRAP (the paper's preferred test): studentized circular block bootstrap with block length b; each draw's standard error is the
  Goetze-Kuensch block estimate. p-value = (1 + #{|d* - d| / se* >= |d| / se}) / (M + 1); the 1 - alpha interval is d +/- q * se with q the
  1 - alpha quantile of |d* - d| / se*.

Fat tails and serial correlation are allowed for; nothing is assumed normal or independent. Sharpe ratios are per day here (the scale cancels in
the test); `annualise` multiplies the reported ratios by sqrt(252).
"""
import math

import numpy as np


def _sr(r):
    mu = r.mean(axis=0)
    g = (r ** 2).mean(axis=0)
    return mu / np.sqrt(g - mu ** 2)


def _grad(mu1, mu2, g1, g2):
    v1, v2 = g1 - mu1 ** 2, g2 - mu2 ** 2
    return np.array([g1 / v1 ** 1.5, -g2 / v2 ** 1.5, -0.5 * mu1 / v1 ** 1.5, 0.5 * mu2 / v2 ** 1.5])


def _moments(x, y):
    mu1, mu2 = x.mean(), y.mean()
    g1, g2 = (x ** 2).mean(), (y ** 2).mean()
    V = np.column_stack([x - mu1, y - mu2, x ** 2 - g1, y ** 2 - g2])
    return mu1, mu2, g1, g2, V


def _parzen(z):
    z = abs(z)
    if z <= 0.5:
        return 1 - 6 * z ** 2 + 6 * z ** 3
    if z <= 1:
        return 2 * (1 - z) ** 3
    return 0.0


def _gamma(V, j):
    T = len(V)
    return V[j:].T @ V[:T - j] / T


def _psi_parzen(V):
    """Parzen-kernel long-run covariance with the Andrews (1991) AR(1) plug-in bandwidth, as in Ledoit & Wolf's compute.Psi.hat"""
    T, p = V.shape
    num = den = 0.0
    for i in range(p):
        x = V[:, i]
        rho = float(np.dot(x[1:], x[:-1]) / np.dot(x[:-1], x[:-1])) if np.dot(x[:-1], x[:-1]) > 0 else 0.0
        rho = max(min(rho, 0.97), -0.97)
        s2 = float(np.mean((x[1:] - rho * x[:-1]) ** 2))
        num += 4 * rho ** 2 * s2 ** 2 / (1 - rho) ** 8          # Andrews' alpha(2), the Parzen kernel's (q = 2)
        den += s2 ** 2 / (1 - rho) ** 4
    alpha = num / den if den > 0 else 0.0
    S = 2.6614 * (alpha * T) ** 0.2
    psi = _gamma(V, 0)
    j = 1
    while j < S and j < T:
        G = _gamma(V, j)
        psi = psi + _parzen(j / S) * (G + G.T)
        j += 1
    return (T / (T - 4)) * psi


def _psi_parzen_pw(V):
    """prewhitened (VAR(1)) Parzen long-run covariance, recoloured, as in compute.Psi.hat.pw (Andrews & Monahan 1992)"""
    X, Y = V[:-1], V[1:]
    A = np.linalg.lstsq(X, Y, rcond=None)[0].T              # Y_t = A Y_{t-1} + e_t
    E = Y - X @ A.T
    psi_e = _psi_parzen(E)
    D = np.linalg.inv(np.eye(V.shape[1]) - A)
    return D @ psi_e @ D.T


def hac_se(x, y, prewhiten=True):
    """delta-method standard error of SR(x) - SR(y) (per-day ratios)"""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mu1, mu2, g1, g2, V = _moments(x, y)
    psi = _psi_parzen_pw(V) if prewhiten else _psi_parzen(V)
    gr = _grad(mu1, mu2, g1, g2)
    return float(math.sqrt(max(gr @ psi @ gr, 0.0) / len(x)))


def _cbb_index(T, b, rng):
    k = int(math.ceil(T / b))
    starts = rng.integers(0, T, size=k)
    return ((starts[:, None] + np.arange(b)[None, :]) % T).ravel()[:T]


def sharpe_diff_test(x, y, b=20, M=4999, alpha=0.05, seed=7, annualise=True):
    """Ledoit-Wolf (2008) paired Sharpe difference, candidate x vs baseline y on the same days -> dict:
    sr_x, sr_y, diff (x - y), se_hac, p_hac, ci_hac, p_boot, ci_boot (1 - alpha), b, M, T. Ratios annualised by sqrt(252) when asked
    (p-values do not depend on it)."""
    from scipy import stats
    x, y = np.asarray(x, float), np.asarray(y, float)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("x and y must be 1-D series of the same length (the same days)")
    T = len(x)
    if T < 3 * b:
        raise ValueError("too few days (%d) for block length %d" % (T, b))
    R = np.column_stack([x, y])
    sr = _sr(R)
    d = float(sr[0] - sr[1])
    se = hac_se(x, y, prewhiten=True)
    if se == 0.0:                                           # identical series: no difference to test
        k = math.sqrt(252) if annualise else 1.0
        return {"sr_x": float(sr[0]) * k, "sr_y": float(sr[1]) * k, "diff": 0.0, "se_hac": 0.0, "p_hac": 1.0, "ci_hac": [0.0, 0.0],
                "p_boot": 1.0, "ci_boot": [0.0, 0.0], "b": b, "M": M, "T": T}
    z = abs(d) / se
    p_hac = float(2 * (1 - stats.norm.cdf(z)))
    zq = float(stats.norm.ppf(1 - alpha / 2))
    rng = np.random.default_rng(seed)
    l = T // b
    count, dstar = 0, np.empty(M)
    for m in range(M):
        idx = _cbb_index(T, b, rng)
        xs, ys = x[idx], y[idx]
        mu1, mu2, g1, g2, Vs = _moments(xs, ys)
        d_s = float(mu1 / math.sqrt(g1 - mu1 ** 2) - mu2 / math.sqrt(g2 - mu2 ** 2))
        Z = math.sqrt(b) * Vs[: l * b].reshape(l, b, 4).mean(axis=1)
        psi_s = Z.T @ Z / l
        gr = _grad(mu1, mu2, g1, g2)
        se_s = math.sqrt(max(gr @ psi_s @ gr, 1e-300) / T)
        ds = abs(d_s - d) / se_s
        dstar[m] = ds
        count += ds >= z
    p_boot = (count + 1) / (M + 1)
    q = float(np.quantile(dstar, 1 - alpha))
    k = math.sqrt(252) if annualise else 1.0
    return {"sr_x": float(sr[0]) * k, "sr_y": float(sr[1]) * k, "diff": d * k, "se_hac": se * k, "p_hac": p_hac,
            "ci_hac": [(d - zq * se) * k, (d + zq * se) * k], "p_boot": float(p_boot), "ci_boot": [(d - q * se) * k, (d + q * se) * k],
            "b": b, "M": M, "T": T}
