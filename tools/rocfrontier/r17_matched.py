# Round 17 (2026-10-05): MATCHED READ r1 - the power of a forward read on a statistic MATCHED to each shadow line's mechanism, walk-forward only.
# Pre-registered: tools/rocfrontier/PREREG_MATCHED_R1.txt - PREREG_SHA below is that file's canonical-LF sha256 (R11.sha_lf); "TBD" until it is
# registered, and every command but `smoke` refuses while it is "TBD". Every rule, seed, horizon and tolerance is that file; where it is silent
# the choice is marked CHOICE.
#   python r17_matched.py parity MANIFEST   the manifest csv (exported on the box from Q16's parity rebuild and the leg caches) -> b463 reproduces
#                                           WF 93.81 / 3.816 / $44,849, line ORB314 = b463 - orb463 + orb314 reproduces 125.6 / 3.95 / $33,735,
#                                           ORB239 101.8 / 3.84 / $41,319, KEEL (its own convention, if keel_line is supplied) 118.545 / 4.2755 /
#                                           $41,376; a line that misses is EXCLUDED and named, a b463 miss refuses everything; READY on a pass
#   python r17_matched.py run MANIFEST      NULL (20,000 joint block draws with the within-pair swap) + TRUTH (the same draws, no swap, at SHRINK
#                                           1.0 and 0.5) -> per statistic x horizon: single false pass, power, critical value -> MATCHED.txt,
#                                           matched.json, power.csv; refuses without READY or when the prereg or the manifest changed after parity
#   python r17_matched.py smoke DIR [planted|null]   offline synthetic manifest (DIR's name must contain 'smoke', never under C:\EdgeLog): a
#                                           planted giveback-cut must be readable by M1 and not by the dollar rule; a null world must not be
#   Nothing here reads a forward P&L, commits, pushes, queues a job or writes anywhere but OUT.
"""MATCHED READ r1 - a planning computation on the walk-forward only.

THE QUESTION. Q16 (BOOK.md 10y) showed that the registered forward-read rules - a ROC margin over #463, or the summed dollar difference
(R2) - have power 1-7% for the forward shadow lines ORB314 and ORB239, because those lines earn about the same money as #463 on the
walk-forward: their gain is a SMALLER DRAWDOWN, not more dollars, and a mean-type rule cannot see a drawdown difference. KEEL earns more,
but in a few large TTM trades. This harness asks: if the forward read is made on a statistic MATCHED to the line's mechanism, what is its
power at 12 / 24 / 36 months (252 / 504 / 756 weekday rows) with the family-wise false pass held at 5%?

THE STATISTICS, per ORB line, on a window of n rows, with a = the ORB leg of #463 (orb463) and b = the line's own ORB leg:
  M1 DOWNSIDE RATIO (primary)  DSD(b) / DSD(a) - 1, where DSD(x) = sqrt(mean(min(x, 0)^2)); the claim is M1 < 0 (the line loses less).
  M2 LOSS-DAY GAIN             mean(b - a) over the rows where a < 0; claim > 0 (NaN when the window has no such row).
  M3 TAIL                      q05(b) - q05(a), the 5% quantiles of the daily leg dollars; claim > 0.
  R2 DOLLARS (Q16's rule)      sum(b - a) / its null sd; claim > 0 - here for contrast, not as a candidate.
  KEEL                         T = mean(keel_d) / (sd(keel_d, ddof 1) / sqrt(n)) over the rows where keel_d is not NaN (keel_d = the sum over
                               that day's TTM trades of the paired difference vs #463, 0 on days without a TTM trade); claim > 0. KEEL's
                               matched statistic IS the mean; it sits here so the family is read together.

THE NULL (no edge) is within-pair exchangeability: a circular block bootstrap of the JOINT walk-forward rows (every column together, the
same block starts), block 21, draws of 756 rows; inside a draw every block gets ONE swap flag with probability 1/2, shared by every line:
when set, (a, b) are exchanged for both ORB lines in that block and keel_d's sign is flipped. TRUTH = the same draws with no swap and no
flip; at SHRINK 0.5, b is replaced by a + 0.5 (b - a) and keel_d by 0.5 keel_d before anything is computed.

THE READING RULE. For each statistic kind S (M1, M2, M3, R2) and horizon n, every line's statistic is computed on the first n rows of every
null draw and standardised by its own null mean and sd, sign-oriented so that the claim direction is positive (M1 enters as -M1). The family is the
ORB lines on S plus KEEL on its T (for R2: KEEL on dollars). The family-wise 5% critical value c(S, n) is the 95th percentile over null draws
of the family MAX of the standardised statistic. A line's single false pass = the share of null draws where its standardised statistic is
at or above c; its POWER = the share of TRUTH draws at or above c, at SHRINK 1.0 and 0.5. The headline, per line, is the read length at which
the primary statistic (M1 for the ORB lines, T for KEEL) first reaches power 0.5 and 0.8, beside Q16's months for the registered rules.

TRUTH IS AN UPPER BOUND: the lines were chosen on the walk-forward, so their face-value edge carries the winner's curse. Report-only: the
minimum track record length (Bailey and Lopez de Prado 2012) of each line's paired daily difference, at z 1.645.
"""
import csv, json, math, os, sys, time, warnings
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("EDGELOG_ROOT", r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"); sys.path.insert(0, REPO); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import r11_risk as R11

OUT = os.environ.get("EDGELOG_ROCFRONTIER_MATCHED", r"C:\EdgeLog\_anatomy_cache\rocfrontier\matched_r1")
PREREG = os.path.join(HERE, "PREREG_MATCHED_R1.txt")
PREREG_SHA = "TBD"                                           # canonical-LF sha256 of the prereg once it is registered; every command but smoke refuses "TBD"
WF0, WF1 = "2016-07-01", "2025-06-29"                        # the walk-forward, inclusive; the manifest holds one weekday row per day of it
BLOCK, NDRAW, CHUNK, SEED = 21, 20000, 2500, 20261020
HORIZONS = (252, 504, 756)                                   # 12 / 24 / 36 months of weekday rows
LEVEL = 0.05                                                 # family-wise false pass
LINES = ("ORB314", "ORB239", "KEEL")
REF = {"b463": (93.81, 3.816, 44849.0), "ORB314": (125.6, 3.95, 33735.0), "ORB239": (101.8, 3.84, 41319.0),
       "KEEL": (118.545, 4.2755, 41376.0)}                    # recorded WF figures: ROC at $30k, Sortino, max drawdown $
TOL = {"roc": 0.06, "sort": 0.01, "dd": 1.0}
KEEL_TOL = {"roc": 0.6, "sort": 0.05, "dd": 10.0}            # KEEL's own convention (keel_eval: WF from 2016-07-27, years to 2025-06-30) - checked loosely
SHRINK = (1.0, 0.5)                                          # TRUTH at the walk-forward edge taken at face value, and at half of it
Q16_MONTHS = {"ORB314": "> 36", "ORB239": "> 36", "KEEL": "> 36"}    # the house's earlier read lengths (Q16, BOOK.md 10y) for the registered rules
REQUIRED = ("date", "b463", "orb463", "orb314", "orb239", "keel_d")
OPTIONAL = ("keel_line",)
NONAN = ("b463", "orb463", "orb314", "orb239")
ORB_LEG = {"ORB314": "orb314", "ORB239": "orb239"}
FAMILIES = ("M1", "M2", "M3", "R2")
PRIMARY = "M1"                                               # the headline family: M1 for the ORB lines, KEEL's T read in it
SIGN = {"M1": -1.0, "M2": 1.0, "M3": 1.0, "R2": 1.0, "T": 1.0}   # orientation so that the claim direction is positive
Z_ALPHA = 1.645
CHECK_REFS = True        # a real run holds every figure to the recorded ones; only smoke() switches it (a synthetic world cannot match them)
SMOKE_TBD_OK = False     # only smoke() tolerates PREREG_SHA == "TBD"


def asc(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")        # console and files stay ASCII (cp1252 on the box)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        f.write(json.dumps(obj, indent=1, default=R11.js))


def _ready_path():
    return os.path.join(OUT, "READY")


def check_prereg(path=None, want=None):
    """The prereg's canonical-LF sha against the registered one; 'TBD' refuses unless smoke() set SMOKE_TBD_OK."""
    path, want = path or PREREG, want or PREREG_SHA
    got = R11.sha_lf(path) if os.path.isfile(path) else None
    if want == "TBD":
        if SMOKE_TBD_OK:
            return "TBD"
        raise SystemExit(f"refused: PREREG_SHA is 'TBD' - the prereg is not registered yet (the file hashes to {got or 'absent'})")
    if got is None:
        raise SystemExit(f"refused: prereg {os.path.basename(path)} not found at {path}")
    if got != want:
        raise SystemExit(f"refused: {os.path.basename(path)} sha256 {got} is not the registered {want} - the plan changed after it was registered")
    return got


def months(n):
    return int(round(n / 21.0))


# ------------------------------------------------------------------ the manifest: format, validation, sha
def manifest_sha(path):
    if not os.path.isfile(path):
        raise SystemExit(f"refused: manifest not found: {path}")
    return R11.sha_lf(path)


def _col(df, c):
    return pd.to_numeric(df[c], errors="coerce").to_numpy(float)


def read_manifest(path):
    """The manifest csv -> arrays. Columns: date (weekday rows WF0..WF1 inclusive, strictly increasing), b463 (the adopted book's valued-daily $),
    orb463 (the ORB leg of #463, daily $, as sized in the book), orb314 / orb239 (the lines' ORB legs, daily $, as sized in the lines), keel_d
    (KEEL's daily paired difference vs #463; NaN allowed only on the rows BEFORE KEEL's first WF day, which are excluded for KEEL only),
    keel_line (optional: KEEL line's daily $ for the keel_eval parity figure; NaN allowed on the same leading rows). Refuses: a missing column,
    a date outside WF0..WF1, a non-increasing date, NaN in b463 / orb463 / orb314 / orb239, keel_d NaN after its first finite row."""
    sha = manifest_sha(path)
    df = pd.read_csv(path)
    df.columns = [str(c).strip() for c in df.columns]
    miss = [c for c in REQUIRED if c not in df.columns]
    if miss:
        raise SystemExit(f"refused: manifest lacks column(s) {miss}; expected {list(REQUIRED)} plus optional {list(OPTIONAL)}")
    if len(df) < 2:
        raise SystemExit("refused: manifest has fewer than 2 rows")
    dates = pd.to_datetime(df["date"], errors="coerce")
    if dates.isna().any():
        raise SystemExit(f"refused: manifest date unreadable at row {int(np.flatnonzero(dates.isna().to_numpy())[0])}")
    dv = dates.to_numpy()
    if not (np.diff(dv) > np.timedelta64(0, "ns")).all():
        i = int(np.flatnonzero(~(np.diff(dv) > np.timedelta64(0, "ns")))[0]) + 1
        raise SystemExit(f"refused: manifest dates are not strictly increasing at row {i} ({str(dates.iloc[i].date())})")
    lo, hi = pd.Timestamp(WF0), pd.Timestamp(WF1)
    bad = (dates < lo) | (dates > hi)
    if bad.any():
        i = int(np.flatnonzero(bad.to_numpy())[0])
        raise SystemExit(f"refused: manifest date {str(dates.iloc[i].date())} (row {i}) is outside the walk-forward {WF0}..{WF1}")
    cols = {}
    for c in NONAN:
        v = _col(df, c)
        if not np.isfinite(v).all():
            i = int(np.flatnonzero(~np.isfinite(v))[0])
            raise SystemExit(f"refused: manifest column {c} is NaN / not a number at row {i} ({str(dates.iloc[i].date())})")
        cols[c] = v
    kd = _col(df, "keel_d")
    ok = np.isfinite(kd)
    if not ok.any():
        raise SystemExit("refused: manifest keel_d has no finite row - KEEL cannot be read")
    k0 = int(np.flatnonzero(ok)[0])
    if not ok[k0:].all():
        i = k0 + int(np.flatnonzero(~ok[k0:])[0])
        raise SystemExit(f"refused: manifest keel_d is NaN at row {i} ({str(dates.iloc[i].date())}), after KEEL's first row {k0} ({str(dates.iloc[k0].date())})")
    kl = None
    if "keel_line" in df.columns:
        kl = _col(df, "keel_line")
        okl = np.isfinite(kl)
        if not okl.any():
            raise SystemExit("refused: manifest keel_line is present but has no finite row (drop the column to mark it 'not supplied')")
        l0 = int(np.flatnonzero(okl)[0])
        if not okl[l0:].all():
            i = l0 + int(np.flatnonzero(~okl[l0:])[0])
            raise SystemExit(f"refused: manifest keel_line is NaN at row {i} ({str(dates.iloc[i].date())}), after its first finite row {l0}")
    idx = pd.DatetimeIndex(dates)
    M = {"path": path, "sha": sha, "dates": idx, "n": int(len(df)), "keel_d": kd, "keel_line": kl, "keel_first_row": k0,
         "keel_first": str(idx[k0].date()), "keel_rows": int(ok.sum()), "weekend_rows": int((idx.dayofweek >= 5).sum())}
    M.update(cols)
    return M


def line_series(M, line):
    """The line's valued-daily $: b463 with #463's ORB leg replaced by the line's (KEEL: the supplied keel_line, or None)."""
    if line in ORB_LEG:
        return M["b463"] - M["orb463"] + M[ORB_LEG[line]]
    return M["keel_line"]


def figures(x, dates):
    s = R11.stats(np.asarray(x, float), dates)
    return {"roc": s["roc"], "sort": s["sort"], "dd": s["max_dd"], "net": s["net"]}


def within(got, ref, tol):
    """ROC and Sortino strictly inside their tolerance, max drawdown at or inside its dollar tolerance (as r11's P3)."""
    d = {"roc": abs(got["roc"] - ref[0]), "sort": abs(got["sort"] - ref[1]), "dd": abs(got["dd"] - ref[2])}
    ok = bool(np.isfinite(got["roc"]) and np.isfinite(got["sort"]) and d["roc"] < tol["roc"] and d["sort"] < tol["sort"] and d["dd"] <= tol["dd"])
    return ok, d


def _fig_line(name, g, ref, ok, tag=""):
    return (f"{name:7s} roc {g['roc']:8.3f} sort {g['sort']:7.4f} dd {g['dd']:10,.0f} net {g['net']:11,.0f} vs recorded {ref[0]:.3f} / {ref[1]:.4f} / "
            f"{ref[2]:,.0f} -> {'ok' if ok else 'MISS'}{tag}")


# ------------------------------------------------------------------ parity: the manifest reproduces every recorded figure, else the line is out
def parity(path):
    t0 = time.time()
    psha = check_prereg()
    M = read_manifest(path)
    out = {"manifest": os.path.abspath(path), "manifest_sha256": M["sha"], "prereg_sha256": psha, "rows": M["n"], "first": str(M["dates"][0].date()),
           "last": str(M["dates"][-1].date()), "weekend_rows": M["weekend_rows"], "keel_first": M["keel_first"], "keel_rows": M["keel_rows"],
           "refs_checked": CHECK_REFS, "figures": {}, "lines_in": [], "lines_out": {}, "keel_parity": None, "keel_flag": False}
    print(f"manifest {os.path.basename(path)} sha256 {M['sha']}: {M['n']} rows {out['first']}..{out['last']}"
          + (f"; NOTE {M['weekend_rows']} weekend rows (the box folds weekend stamps into the Friday)" if M["weekend_rows"] else "")
          + f"; KEEL rows from {M['keel_first']} ({M['keel_rows']} of {M['n']})", flush=True)
    g = figures(M["b463"], M["dates"])
    ok, d = within(g, REF["b463"], TOL)
    out["figures"]["b463"] = {"got": g, "ref": REF["b463"], "tol": TOL, "diff": d, "ok": ok}
    print(_fig_line("b463", g, REF["b463"], ok), flush=True)
    if not ok and CHECK_REFS:
        out["pass"] = False
        save("parity.json", out)
        if os.path.exists(_ready_path()):
            os.remove(_ready_path())
        raise SystemExit("parity FAILED on b463 - the manifest does not reproduce the adopted book's recorded WF figures; nothing else is computed (see parity.json)")
    for line in ("ORB314", "ORB239"):
        g = figures(line_series(M, line), M["dates"])
        ok, d = within(g, REF[line], TOL)
        out["figures"][line] = {"got": g, "ref": REF[line], "tol": TOL, "diff": d, "ok": ok}
        print(_fig_line(line, g, REF[line], ok), flush=True)
        if ok or not CHECK_REFS:
            out["lines_in"].append(line)
        else:
            out["lines_out"][line] = f"parity miss: roc off {d['roc']:.3f} (tol {TOL['roc']}), sort off {d['sort']:.4f} (tol {TOL['sort']}), dd off {d['dd']:,.0f} (tol {TOL['dd']})"
    if M["keel_line"] is not None:
        rows = np.isfinite(M["keel_line"])
        g = figures(M["keel_line"][rows], M["dates"][rows])
        ok, d = within(g, REF["KEEL"], KEEL_TOL)
        out["figures"]["KEEL"] = {"got": g, "ref": REF["KEEL"], "tol": KEEL_TOL, "diff": d, "ok": ok, "convention": "keel_eval convention", "rows": int(rows.sum())}
        print(_fig_line("KEEL", g, REF["KEEL"], ok, " (keel_eval convention, loose tolerance)"), flush=True)
        if ok or not CHECK_REFS:
            out["lines_in"].append("KEEL")
            out["keel_parity"] = "checked ok" if ok else "checked - refs not held (smoke)"
        else:
            out["lines_out"]["KEEL"] = f"parity miss (keel_eval convention): roc off {d['roc']:.3f}, sort off {d['sort']:.4f}, dd off {d['dd']:,.0f}"
    else:
        out["lines_in"].append("KEEL")
        out["keel_parity"], out["keel_flag"] = "not supplied", True
        print("KEEL parity: not supplied (no keel_line column) - KEEL is run but FLAGGED: its paired difference is unverified against the recorded figure", flush=True)
    for line, why in out["lines_out"].items():
        print(f"{line} EXCLUDED from run - {why}", flush=True)
    out["pass"] = bool(out["lines_in"])
    out["seconds"] = round(time.time() - t0, 1)
    save("parity.json", out)
    if not out["pass"]:
        if os.path.exists(_ready_path()):
            os.remove(_ready_path())
        raise SystemExit("parity FAILED - no line reproduces its recorded figure; see parity.json")
    with open(_ready_path(), "w") as f:
        f.write(json.dumps({"parity": "passed", "manifest": out["manifest"], "manifest_sha256": M["sha"], "prereg_sha256": psha, "lines_in": out["lines_in"],
                            "lines_out": out["lines_out"], "keel_parity": out["keel_parity"], "keel_flag": out["keel_flag"], "refs_checked": CHECK_REFS,
                            "figures": out["figures"]}, indent=1, default=R11.js))
    print(f"parity PASS - READY; lines in: {out['lines_in']}" + (f"; out: {list(out['lines_out'])}" if out["lines_out"] else "") + f" ({out['seconds']}s)", flush=True)
    return out


# ------------------------------------------------------------------ the statistics (vectorised over draws: the last axis is the rows of one window)
def dsd(x):
    """Downside semi-deviation: sqrt(mean(min(x, 0)^2)) along the last axis."""
    x = np.asarray(x, float)
    return np.sqrt(np.mean(np.minimum(x, 0.0) ** 2, axis=-1))


def m1(a, b):
    """M1 DOWNSIDE RATIO: DSD(b) / DSD(a) - 1 (claim < 0); NaN when a has no losing row."""
    da, db = dsd(a), dsd(b)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(da > 0, db / np.where(da > 0, da, 1.0) - 1.0, np.nan)


def m2(a, b):
    """M2 LOSS-DAY GAIN: mean(b - a) over the rows where a < 0 (claim > 0); NaN when there is no such row."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    loss = a < 0
    cnt = loss.sum(axis=-1)
    s = np.where(loss, b - a, 0.0).sum(axis=-1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(cnt > 0, s / np.maximum(cnt, 1), np.nan)


def m3(a, b):
    """M3 TAIL: q05(b) - q05(a), the 5% quantiles of the daily leg dollars (numpy's default linear interpolation; claim > 0)."""
    return np.quantile(np.asarray(b, float), 0.05, axis=-1) - np.quantile(np.asarray(a, float), 0.05, axis=-1)


def r2(a, b):
    """R2 DOLLARS, Q16's rule: the summed daily difference (standardised by its null sd in the family read; claim > 0)."""
    return (np.asarray(b, float) - np.asarray(a, float)).sum(axis=-1)


def keel_t(d):
    """KEEL's registered paired form: mean(d) / (sd(d, ddof 1) / sqrt(n)) over the rows where d is not NaN (claim > 0)."""
    d = np.asarray(d, float)
    n = np.isfinite(d).sum(axis=-1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mu = np.nanmean(d, axis=-1)
        sd = np.nanstd(d, axis=-1, ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where((n > 1) & (sd > 0), mu / (np.where(sd > 0, sd, 1.0) / np.sqrt(np.maximum(n, 1))), np.nan)


def keel_sum(d):
    """KEEL on dollars (the R2 family): the summed paired difference over the rows where it is not NaN."""
    return np.nansum(np.asarray(d, float), axis=-1)


def orb_stats(a, b, n):
    a, b = np.asarray(a, float)[..., :n], np.asarray(b, float)[..., :n]
    return {"M1": m1(a, b), "M2": m2(a, b), "M3": m3(a, b), "R2": r2(a, b)}


def keel_stats(d, n):
    d = np.asarray(d, float)[..., :n]
    return {"T": keel_t(d), "R2": keel_sum(d)}


def own_stat(line, S):
    """The statistic a line contributes to family S: the ORB lines S itself; KEEL its T, or dollars in the R2 family."""
    return S if line in ORB_LEG else ("R2" if S == "R2" else "T")


def kinds_of(line):
    return ("M1", "M2", "M3", "R2") if line in ORB_LEG else ("T", "R2")


# ------------------------------------------------------------------ the draws: joint circular block bootstrap with one swap flag per block
def block_draws(rng, n_rows, n_draws, n_out, block=BLOCK):
    """n_draws windows of n_out rows: blocks of `block` consecutive rows (circular) from uniform random starts, laid end to end; and the swap flag
    per row - one Bernoulli(1/2) per block, shared by every column. The rng is used in this order: the starts, then the flags."""
    nb = -(-n_out // block)
    starts = rng.integers(n_rows, size=(n_draws, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n_rows
    flag = rng.random((n_draws, nb)) < 0.5
    return idx.reshape(n_draws, nb * block)[:, :n_out], np.repeat(flag, block, axis=1)[:, :n_out]


def _variant_key(s):
    return f"truth_{s:g}"


def simulate(M, lines_in, ndraw=None, chunk=None, seed=None):
    """NULL and TRUTH statistics for every line in lines_in, kind and horizon: raw[variant][line][kind][n] = one value per draw.
    variant = 'null' (the swap / flip applied) or 'truth_<shrink>' (the same draws, no swap; b = a + shrink (b - a), keel_d = shrink keel_d).
    M needs n, orb463, orb314 / orb239 for the ORB lines in, keel_d for KEEL."""
    ndraw, chunk = int(ndraw or NDRAW), int(chunk or CHUNK)
    seed = SEED if seed is None else seed
    hmax, N = max(HORIZONS), int(M["n"])
    orb = [l for l in lines_in if l in ORB_LEG]
    keel = "KEEL" in lines_in
    variants = ["null"] + [_variant_key(s) for s in SHRINK]
    raw = {v: {l: {k: {n: np.full(ndraw, np.nan) for n in HORIZONS} for k in kinds_of(l)} for l in lines_in} for v in variants}
    rng = np.random.default_rng(seed)
    A0 = np.asarray(M["orb463"], float)
    B0 = {l: np.asarray(M[ORB_LEG[l]], float) for l in orb}
    D0 = np.asarray(M["keel_d"], float) if keel else None
    for c0 in range(0, ndraw, chunk):
        m = min(chunk, ndraw - c0)
        idx, swap = block_draws(rng, N, m, hmax)
        A = A0[idx]
        D = D0[idx] if keel else None
        for v, s in [("null", None)] + [(_variant_key(s), s) for s in SHRINK]:
            for l in orb:
                B = B0[l][idx]
                if s is None:
                    a, b = np.where(swap, B, A), np.where(swap, A, B)
                else:
                    a, b = A, (B if s == 1.0 else A + s * (B - A))
                for n in HORIZONS:
                    for k, val in orb_stats(a, b, n).items():
                        raw[v][l][k][n][c0:c0 + m] = val
            if keel:
                d = np.where(swap, -D, D) if s is None else (D if s == 1.0 else s * D)
                for n in HORIZONS:
                    for k, val in keel_stats(d, n).items():
                        raw[v]["KEEL"][k][n][c0:c0 + m] = val
    meta = {"ndraw": ndraw, "chunk": chunk, "seed": seed, "block": BLOCK, "rows_per_draw": hmax, "blocks_per_draw": -(-hmax // BLOCK), "rows": N,
            "rng": "numpy default_rng(seed); per chunk: block starts, then swap flags - SEED and CHUNK together fix the draws", "shrink": list(SHRINK)}
    return raw, meta


# ------------------------------------------------------------------ the family read: standardise, the family max, c(S, n), false pass and power
def _z(x, mu, sd):
    """Standardise by the line's own null mean and sd (claim-positive orientation applied by the caller); a draw without a statistic never passes."""
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (np.asarray(x, float) - mu) / sd if (np.isfinite(sd) and sd > 0) else np.full(len(x), np.nan)
    return np.where(np.isfinite(z), z, -np.inf)


def crit(maxz, level=LEVEL):
    """The family-wise critical value: the (1 - level) percentile of the family max over null draws (numpy's linear percentile)."""
    mz = np.asarray(maxz, float)
    with np.errstate(invalid="ignore"):                                   # a -inf draw (no statistic) can make the interpolated percentile -inf
        c = float(np.percentile(mz, 100.0 * (1.0 - level)))
    if not np.isfinite(c):
        fin = mz[np.isfinite(mz)]
        c = float(np.percentile(fin, 100.0 * (1.0 - level))) if len(fin) else float("inf")
    return c


def family_read(raw, lines_in, level=LEVEL):
    """fam[S][n] = {crit, fwer, lines: {line: {own_stat, sd_null, null_mean, false_pass, power: {shrink: p}}}}.
    Each line's statistic is oriented claim-positive and standardised by its OWN null mean and sd (CHOICE: the null mean is about zero for
    M1, M3, R2 and T by the swap's symmetry, but M2 conditions on a's losing days and its null mean need not be - centring keeps the family
    max from being owned by the line with the largest offset; for a single line the pass decision is the same either way)."""
    fam = {}
    for S in FAMILIES:
        members = [(l, own_stat(l, S)) for l in lines_in]
        fam[S] = {}
        for n in HORIZONS:
            z0, zt, info = {}, {}, {}
            for l, k in members:
                x0 = SIGN[k] * raw["null"][l][k][n]
                fin = x0[np.isfinite(x0)]
                mu = float(fin.mean()) if len(fin) else float("nan")
                sd = float(np.std(fin, ddof=1)) if len(fin) > 1 else float("nan")
                z0[l] = _z(x0, mu, sd)
                zt[l] = {s: _z(SIGN[k] * raw[_variant_key(s)][l][k][n], mu, sd) for s in SHRINK}
                info[l] = {"own_stat": k, "sd_null": sd, "null_mean": mu, "n_null_nan": int(len(x0) - len(fin)),
                           "truth_mean": {s: float(np.nanmean(SIGN[k] * raw[_variant_key(s)][l][k][n])) for s in SHRINK}}
            maxz = np.max(np.stack([z0[l] for l, _ in members]), axis=0)
            c = crit(maxz, level)
            for l, k in members:
                info[l]["false_pass"] = float(np.mean(z0[l] >= c))
                info[l]["power"] = {s: float(np.mean(zt[l][s] >= c)) for s in SHRINK}
            fam[S][n] = {"crit": c, "fwer": float(np.mean(maxz >= c)), "members": [l for l, _ in members], "lines": info}
    return fam


def first_horizon(power_by_n, target):
    """The first horizon (in months) at which power reaches target, else '> 36 months'."""
    for n in HORIZONS:
        p = power_by_n.get(n, float("nan"))
        if np.isfinite(p) and p >= target:
            return f"{months(n)} months"
    return f"> {months(max(HORIZONS))} months"


def headline(fam, lines_in):
    H = {}
    for l in lines_in:
        k = own_stat(l, PRIMARY)
        pw = {s: {n: fam[PRIMARY][n]["lines"][l]["power"][s] for n in HORIZONS} for s in SHRINK}
        H[l] = {"statistic": k, "family": PRIMARY, "q16_months": Q16_MONTHS.get(l, "n/a"), "power": pw,
                "months": {s: {"0.5": first_horizon(pw[s], 0.5), "0.8": first_horizon(pw[s], 0.8)} for s in SHRINK}}
    return H


def min_trl(d, z_alpha=Z_ALPHA):
    """Minimum track record length (Bailey and Lopez de Prado 2012) of a paired daily difference d, in rows: 1 + (1 - skew SR + (kurt - 1) / 4 SR^2)
    (z_alpha / SR)^2, with SR = mean / sd (ddof 1) per row, skew = mean(z^3), kurt = mean(z^4) (raw, not excess); 'undefined' when SR <= 0."""
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    out = {"n": int(len(d)), "z_alpha": z_alpha, "min_trl_rows": None, "min_trl_months": None, "printed": "undefined"}
    if len(d) < 4:
        out.update({"mean": float("nan"), "sd": float("nan"), "sr": float("nan"), "skew": float("nan"), "kurt": float("nan")})
        return out
    mu, sd = float(d.mean()), float(d.std(ddof=1))
    if not sd > 0:
        out.update({"mean": mu, "sd": sd, "sr": float("nan"), "skew": float("nan"), "kurt": float("nan")})
        return out
    z = (d - mu) / sd
    sr, skew, kurt = mu / sd, float(np.mean(z ** 3)), float(np.mean(z ** 4))
    out.update({"mean": mu, "sd": sd, "sr": sr, "skew": skew, "kurt": kurt})
    if sr <= 0:
        return out
    rows = 1.0 + (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr ** 2) * (z_alpha / sr) ** 2
    out.update({"min_trl_rows": float(rows), "min_trl_months": float(rows / 21.0), "printed": f"{rows:,.0f} rows (about {rows / 21.0:,.0f} months)"})
    return out


def m1_ex_worst(a, b, dates=None):
    """Report only (prereg COULD FOOL US): M1 on the whole window, and without each leg's single worst day (that row dropped from BOTH legs),
    and without both - how much of the downside ratio one extreme day carries."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ia, ib = int(np.argmin(a)), int(np.argmin(b))

    def ex(*rows):
        keep = np.ones(len(a), bool)
        keep[list(rows)] = False
        return float(m1(a[keep], b[keep]))
    out = {"M1": float(m1(a, b)), "a_worst_row": ia, "a_worst": float(a[ia]), "b_worst_row": ib, "b_worst": float(b[ib]),
           "M1_ex_a_worst": ex(ia), "M1_ex_b_worst": ex(ib), "M1_ex_both": ex(ia, ib), "same_row": bool(ia == ib)}
    if dates is not None:
        out["a_worst_day"], out["b_worst_day"] = str(dates[ia].date()), str(dates[ib].date())
    return out


def wf_face_value(M, lines_in):
    """Each line's statistics on the whole walk-forward (report only), M1 without the worst day, and the minTRL of its paired difference."""
    wf = {}
    for l in lines_in:
        if l in ORB_LEG:
            a, b = M["orb463"], M[ORB_LEG[l]]
            wf[l] = {"M1": float(m1(a, b)), "M2": float(m2(a, b)), "M3": float(m3(a, b)), "R2_sum": float(r2(a, b)), "rows": int(M["n"]), "min_trl": min_trl(b - a),
                     "M1_ex_worst": m1_ex_worst(a, b, M["dates"])}
        else:
            d = M["keel_d"][np.isfinite(M["keel_d"])]
            wf[l] = {"T": float(keel_t(d)), "R2_sum": float(keel_sum(d)), "rows": int(len(d)), "trade_rows": int((d != 0).sum()), "min_trl": min_trl(d)}
    return wf


# ------------------------------------------------------------------ run
def run(path):
    t0 = time.time()
    psha = check_prereg()
    if not os.path.exists(_ready_path()):
        raise SystemExit("refused: parity has not passed - run parity MANIFEST first")
    with open(_ready_path()) as f:
        ready = json.loads(f.read() or "{}")
    if ready.get("prereg_sha256") != psha:
        raise SystemExit("refused: the prereg changed after parity passed - run parity again")
    msha = manifest_sha(path)
    if ready.get("manifest_sha256") != msha:
        raise SystemExit("refused: the manifest changed after parity passed (or this is not the file parity read) - run parity again")
    M = read_manifest(path)
    lines_in = [l for l in LINES if l in (ready.get("lines_in") or [])]
    if not lines_in:
        raise SystemExit("refused: READY lists no line - run parity again")
    print(f"MATCHED READ r1: {M['n']} rows {str(M['dates'][0].date())}..{str(M['dates'][-1].date())}; lines in {lines_in}"
          + (f"; out {list(ready.get('lines_out') or {})}" if ready.get("lines_out") else "") + f"; KEEL parity {ready.get('keel_parity')}", flush=True)
    wf = wf_face_value(M, lines_in)
    t1 = time.time()
    raw, meta = simulate(M, lines_in)
    t2 = time.time()
    fam = family_read(raw, lines_in)
    H = headline(fam, lines_in)
    summ = {"prereg_sha256": psha, "manifest": os.path.abspath(path), "manifest_sha256": msha, "rows": M["n"], "first": str(M["dates"][0].date()),
            "last": str(M["dates"][-1].date()), "keel_first": M["keel_first"], "keel_rows": M["keel_rows"], "lines_in": lines_in,
            "lines_out": ready.get("lines_out") or {}, "keel_parity": ready.get("keel_parity"), "keel_flag": bool(ready.get("keel_flag")),
            "refs_checked": bool(ready.get("refs_checked", CHECK_REFS)), "parity_figures": ready.get("figures"), "settings": meta,
            "horizons": list(HORIZONS), "level": LEVEL, "families": {S: {n: fam[S][n] for n in HORIZONS} for S in FAMILIES}, "primary": PRIMARY,
            "wf_face_value": wf, "headline": H, "q16_months": Q16_MONTHS,
            "truth_note": "TRUTH is an UPPER bound: the lines were chosen on the walk-forward (winner's curse); SHRINK 0.5 halves the day-by-day "
                          "difference and with it the noise in it - a planning sensitivity, not a second truth",
            "seconds": {"draws": round(t2 - t1, 1), "total": round(time.time() - t0, 1)}}
    save("matched.json", summ)
    rows = []
    for S in FAMILIES:
        for n in HORIZONS:
            for l in lines_in:
                r = fam[S][n]["lines"][l]
                for s in SHRINK:
                    rows.append({"line": l, "statistic": S, "horizon": n, "shrink": s, "false_pass": r["false_pass"], "power": r["power"][s], "crit": fam[S][n]["crit"],
                                 "own_stat": r["own_stat"]})
    os.makedirs(OUT, exist_ok=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "power.csv"), index=False)
    lines = report_lines(summ)
    with open(os.path.join(OUT, "MATCHED.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return summ


def report_lines(s):
    fam, H, wf = s["families"], s["headline"], s["wf_face_value"]
    st = s["settings"]
    out = [f"MATCHED READ r1 - the power of a forward read on a statistic matched to each line's mechanism (walk-forward only; no forward P&L read)",
           f"prereg sha256 {s['prereg_sha256']}; manifest sha256 {s['manifest_sha256']}; {s['rows']} rows {s['first']}..{s['last']}; KEEL rows from {s['keel_first']} "
           f"({s['keel_rows']})",
           f"lines in: {', '.join(s['lines_in'])}" + ("; out: " + "; ".join(f"{l} ({w})" for l, w in s["lines_out"].items()) if s["lines_out"] else "")
           + f"; KEEL parity: {s['keel_parity']}" + (" - FLAG: KEEL's paired difference is unverified" if s["keel_flag"] else "")
           + ("" if s["refs_checked"] else "; recorded figures NOT held (smoke)"),
           f"draws: {st['ndraw']:,} x {st['rows_per_draw']} rows ({st['blocks_per_draw']} blocks of {st['block']}), seed {st['seed']}, chunks of {st['chunk']}; "
           f"null = within-pair exchangeability (one swap flag per block, p 1/2, shared by every line: (a, b) exchanged for both ORB lines, keel_d's sign flipped); "
           f"truth = the same draws unswapped at shrink {', '.join(f'{x:g}' for x in SHRINK)}",
           f"family-wise false pass {s['level']:.0%} per statistic and horizon: c(S, n) = the 95th percentile over null draws of the family max of the standardised "
           f"(own null mean and sd, claim-positive) statistic; family = the ORB lines on S plus KEEL on T (R2: KEEL on dollars)",
           "TRUTH is an UPPER bound: the lines were chosen on the walk-forward, so their face-value edge carries the winner's curse; SHRINK 0.5 halves the "
           "day-by-day difference and with it the noise in it - read it as a planning sensitivity, not a second truth"]
    if s.get("parity_figures"):
        for l, p in s["parity_figures"].items():
            g = p["got"]
            out.append(f"parity {l:7s} roc {g['roc']:.3f} sort {g['sort']:.4f} dd {g['dd']:,.0f} net {g['net']:,.0f} (recorded {p['ref'][0]} / {p['ref'][1]} / {p['ref'][2]:,.0f}) "
                       f"-> {'ok' if p['ok'] else 'MISS'}" + (f" [{p['convention']}]" if p.get("convention") else ""))
    for l in s["lines_in"]:
        w = wf[l]
        if l in ORB_LEG:
            out.append(f"WF face value {l}: M1 {w['M1']:+.4f}, M2 {w['M2']:+,.1f} $/loss-day, M3 {w['M3']:+,.1f} $, summed difference {w['R2_sum']:+,.0f} $ over {w['rows']} rows")
        else:
            out.append(f"WF face value {l}: T {w['T']:+.3f} over {w['rows']} rows ({w['trade_rows']} with a TTM trade), summed difference {w['R2_sum']:+,.0f} $")
    out.append("statistic x horizon (single false pass | power at shrink 1.0 | power at shrink 0.5 | c(S, n) | family-wise false pass):")
    out.append(f"  {'line':7s} {'stat':5s} {'own':4s} {'months':>6s} {'false':>7s} {'pow1.0':>7s} {'pow0.5':>7s} {'crit':>7s} {'fwer':>6s} {'sd_null':>12s}")
    for S in FAMILIES:
        for n in HORIZONS:
            f = fam[S][n]
            for l in s["lines_in"]:
                r = f["lines"][l]
                out.append(f"  {l:7s} {S:5s} {r['own_stat']:4s} {months(n):6d} {r['false_pass']:7.3f} {r['power'][1.0]:7.3f} {r['power'][0.5]:7.3f} {f['crit']:7.3f} "
                           f"{f['fwer']:6.3f} {r['sd_null']:12.4g}")
    for l in s["lines_in"]:
        t = wf[l]["min_trl"]
        out.append(f"minTRL (report only) {l}: paired daily difference mean {t.get('mean', float('nan')):,.1f} sd {t.get('sd', float('nan')):,.1f} SR/row "
                   f"{t.get('sr', float('nan')):.4f} skew {t.get('skew', float('nan')):.2f} kurt {t.get('kurt', float('nan')):.1f} -> {t['printed']}")
    for l in s["lines_in"]:
        w = wf[l].get("M1_ex_worst")
        if w:
            out.append(f"M1 without the worst day (report only) {l}: whole WF {w['M1']:+.4f}; without a's worst day {w['a_worst_day']} ({w['a_worst']:+,.0f}) "
                       f"{w['M1_ex_a_worst']:+.4f}; without b's worst day {w['b_worst_day']} ({w['b_worst']:+,.0f}) {w['M1_ex_b_worst']:+.4f}; without both {w['M1_ex_both']:+.4f}"
                       + (" (the same day)" if w["same_row"] else ""))
    out.append(f"HEADLINE - read length at which the primary statistic ({PRIMARY} for the ORB lines, T for KEEL) first reaches power 0.5 / 0.8, family-wise false pass "
               f"{s['level']:.0%}; beside it Q16's months for the registered rules (ROC margin / dollars):")
    out.append(f"  {'line':7s} {'stat':4s} {'power 12/24/36 at 1.0':>22s} {'to 0.5 at 1.0':>14s} {'to 0.8 at 1.0':>14s} {'to 0.5 at 0.5':>14s} {'to 0.8 at 0.5':>14s} {'Q16':>6s}")
    for l in s["lines_in"]:
        h = H[l]
        p = h["power"][1.0]
        out.append(f"  {l:7s} {h['statistic']:4s} {' / '.join(f'{p[n]:.2f}' for n in HORIZONS):>22s} {h['months'][1.0]['0.5']:>14s} {h['months'][1.0]['0.8']:>14s} "
                   f"{h['months'][0.5]['0.5']:>14s} {h['months'][0.5]['0.8']:>14s} {h['q16_months']:>6s}")
    out.append(f"wall time: draws {s['seconds']['draws']}s, total {s['seconds']['total']}s")
    return [asc(x) for x in out]


# ------------------------------------------------------------------ smoke: a synthetic manifest, the whole round, the refusals
def _planted(a, p_loss, p_win, rng):
    """a with a giveback-cut: on a share p_loss of a's losing days (random) the loss is cut by 60%; on the share p_win of a's winning days with
    the LARGEST gains the gain is cut by 50% - a smaller downside that gives back on the best days, so the mean difference stays near zero."""
    b = a.copy()
    loss, win = a < 0, a > 0
    cut = loss & (rng.random(len(a)) < p_loss)
    b[cut] = 0.4 * a[cut]
    wi = np.flatnonzero(win)
    k = int(round(p_win * len(wi)))
    if k:
        top = wi[np.argsort(a[wi])[-k:]]
        b[top] = 0.5 * a[top]
    return b


def synth_manifest(path, world="planted", seed=7):
    """2,346 weekday rows WF0..WF1: a = orb463 fat-tailed (t df 4, scaled, small positive edge) with persistent volatility; planted: orb314 = a with
    the 25% / 60% + 8% / 50% giveback-cut, orb239 the weaker 10% / 3% cut; null: orb314 / orb239 = a's volatility path with independent t
    innovations (same distribution, no cut); keel_d = a TTM trade on 30% of rows with a small positive mean, NaN before 2016-07-27;
    b463 = a + two other synthetic legs; keel_line omitted. Returns the planted facts (the mean differences) for the smoke print."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(WF0, WF1)
    N = len(dates)
    lv = np.zeros(N)
    for i in range(1, N):
        lv[i] = 0.97 * lv[i - 1] + rng.normal(0.0, 0.15)
    sig = np.exp(lv)
    a = 40.0 + 600.0 * sig * rng.standard_t(4, N)
    if world == "planted":
        b314, b239 = _planted(a, 0.25, 0.08, rng), _planted(a, 0.10, 0.03, rng)
    elif world == "null":
        b314, b239 = 40.0 + 600.0 * sig * rng.standard_t(4, N), 40.0 + 600.0 * sig * rng.standard_t(4, N)
    else:
        raise SystemExit(f"refused: unknown smoke world {world!r} (planted | null)")
    trade = rng.random(N) < 0.30
    keel = np.where(trade, 150.0 + 1500.0 * rng.standard_t(4, N), 0.0)
    k0 = int(np.searchsorted(dates.values, np.datetime64("2016-07-27")))
    keel[:k0] = np.nan
    leg2 = 60.0 + 900.0 * sig * rng.standard_t(4, N)
    leg3 = 30.0 + 400.0 * sig * rng.standard_t(4, N)
    b463 = a + leg2 + leg3
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(REQUIRED)
        for i in range(N):
            w.writerow([str(dates[i].date()), f"{b463[i]:.4f}", f"{a[i]:.4f}", f"{b314[i]:.4f}", f"{b239[i]:.4f}", "" if not np.isfinite(keel[i]) else f"{keel[i]:.4f}"])
    return {"rows": N, "keel_first_row": k0, "mean_diff_314": float((b314 - a).mean()), "sd_diff_314": float((b314 - a).std()),
            "mean_diff_239": float((b239 - a).mean()), "M1_314": float(m1(a, b314)), "M1_239": float(m1(a, b239)), "keel_mean": float(np.nanmean(keel))}


def smoke(d, world="planted"):
    """A synthetic manifest under DIR (name contains 'smoke', never under C:\\EdgeLog), then: the refusals before parity, parity (recorded figures
    reported, not held; KEEL 'not supplied'), run at NDRAW 400 / CHUNK 200, the assertions of the world, the refusals after. The numbers mean
    nothing; the world only shows the read has power where it should and none where it should not."""
    global OUT, CHECK_REFS, SMOKE_TBD_OK, NDRAW, CHUNK
    root = os.path.abspath(d)
    assert "smoke" in os.path.basename(root).lower() and not os.path.normcase(root).startswith(os.path.normcase(r"C:\EdgeLog")), \
        "smoke needs its own scratch folder (name contains 'smoke'), never a real cache"
    os.makedirs(root, exist_ok=True)
    t0 = time.time()
    OUT = os.path.join(root, "matched")
    CHECK_REFS, SMOKE_TBD_OK, NDRAW, CHUNK = False, True, 400, 200
    man = os.path.join(root, f"manifest_smoke_{world}.csv")
    facts = synth_manifest(man, world)
    print(f"smoke {world}: {facts['rows']} rows; planted mean difference ORB314 {facts['mean_diff_314']:+.1f} $/day (sd {facts['sd_diff_314']:.0f}), "
          f"ORB239 {facts['mean_diff_239']:+.1f}; WF M1 ORB314 {facts['M1_314']:+.4f}, ORB239 {facts['M1_239']:+.4f}; keel_d mean {facts['keel_mean']:+.1f}", flush=True)
    if os.path.exists(_ready_path()):
        os.remove(_ready_path())
    try:
        run(man)
        raise AssertionError("smoke: run() must refuse without READY")
    except SystemExit:
        pass
    SMOKE_TBD_OK = False
    try:
        check_prereg()
        raise AssertionError("smoke: check_prereg() must refuse a TBD prereg outside the smoke")
    except SystemExit:
        pass
    SMOKE_TBD_OK = True
    p = parity(man)
    assert p["lines_in"] == list(LINES) and p["keel_parity"] == "not supplied" and p["keel_flag"], p
    s = run(man)
    fam = s["families"]
    # the M1 family's null false pass at every horizon: the family-wise rate within 0.05 +/- 0.03 (it is the 95th percentile by construction);
    # each line's single false pass is a share of that (its pass set is inside the family-max pass set), the three together cover it (union
    # bound), and every ORB line takes part - with three lines in one family a single rate near 0.05 itself is impossible
    for n in HORIZONS:
        f = fam["M1"][n]
        assert 0.02 <= f["fwer"] <= 0.08, f"smoke: M1 family-wise false pass at {n} rows is {f['fwer']:.3f}, not within 0.05 +/- 0.03"
        singles = {l: f["lines"][l]["false_pass"] for l in f["members"]}
        assert all(v <= f["fwer"] + 1e-12 for v in singles.values()) and sum(singles.values()) >= f["fwer"] - 1e-12, (n, singles, f["fwer"])
        assert all(singles[l] >= 0.003 for l in ("ORB314", "ORB239")), f"smoke: an ORB line never passes the M1 null at {n} rows: {singles}"
        for l in ("ORB314", "ORB239"):                                             # the swap null is centred: M1's null mean is small against its sd
            r = f["lines"][l]
            assert abs(r["null_mean"]) <= 0.25 * r["sd_null"], (n, l, r["null_mean"], r["sd_null"])
    p314 = {n: fam["M1"][n]["lines"]["ORB314"]["power"][1.0] for n in HORIZONS}
    p239 = {n: fam["M1"][n]["lines"]["ORB239"]["power"][1.0] for n in HORIZONS}
    r314 = {n: fam["R2"][n]["lines"]["ORB314"]["power"][1.0] for n in HORIZONS}
    if world == "planted":
        assert p314[756] > p314[252] and p314[756] > 0.5, f"smoke: M1 power for ORB314 must grow with the read and pass 0.5 at 36 months: {p314}"
        assert p239[756] < p314[756], f"smoke: the weaker cut must read weaker: ORB239 {p239[756]:.3f} vs ORB314 {p314[756]:.3f}"
        assert r314[756] < p314[756], f"smoke: the dollar rule must read a near-zero mean difference below M1: R2 {r314[756]:.3f} vs M1 {p314[756]:.3f}"
    else:
        assert p314[252] <= 0.10, f"smoke: a line with no edge must not be read by M1: power {p314[252]:.3f} at 12 months"
    for n in ("MATCHED.txt", "matched.json", "power.csv", "parity.json", "READY"):
        assert os.path.exists(os.path.join(OUT, n)), n
    open(os.path.join(OUT, "MATCHED.txt"), encoding="utf-8").read().encode("ascii")
    pw = pd.read_csv(os.path.join(OUT, "power.csv"))
    assert list(pw.columns)[:7] == ["line", "statistic", "horizon", "shrink", "false_pass", "power", "crit"] and len(pw) == len(FAMILIES) * len(HORIZONS) * 3 * len(SHRINK)
    # refusals after a pass: the manifest changed after parity; READY gone
    with open(man) as f:
        txt = f.read()
    with open(man, "w") as f:
        f.write(txt.replace("\n2016-07-05,", "\n2016-07-05,0.0001", 1) if "\n2016-07-05," in txt else txt + " ")
    try:
        run(man)
        raise AssertionError("smoke: run() must refuse when the manifest changed after parity")
    except SystemExit:
        pass
    with open(man, "w") as f:
        f.write(txt)
    os.remove(_ready_path())
    try:
        run(man)
        raise AssertionError("smoke: run() must refuse without READY")
    except SystemExit:
        pass
    print(f"SMOKE PASS ({world}; M1 power ORB314 {' / '.join(f'{p314[n]:.2f}' for n in HORIZONS)}, ORB239 {' / '.join(f'{p239[n]:.2f}' for n in HORIZONS)}, "
          f"R2 ORB314 {' / '.join(f'{r314[n]:.2f}' for n in HORIZONS)} - meaningless; {time.time() - t0:.0f}s)", flush=True)
    return s


if __name__ == "__main__":
    cmd = sys.argv[1:]
    if len(cmd) == 2 and cmd[0] == "parity":
        parity(cmd[1])
    elif len(cmd) == 2 and cmd[0] == "run":
        run(cmd[1])
    elif len(cmd) in (2, 3) and cmd[0] == "smoke":
        smoke(cmd[1], *(cmd[2:] or ["planted"]))
    else:
        print("usage: r17_matched.py parity MANIFEST | run MANIFEST | smoke DIR [planted|null]")
        sys.exit(2)
