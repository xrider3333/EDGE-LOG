r"""W93 HOLDOUT - the locked loser-anatomy SKIP test on NOISE #382's held folds 5-8 (MANAGER #165 GO, owner 11-03).

Prereg C:\EdgeLog\manager\prereg\PREREG_noise382_loser_anatomy_2026-11-03.md (locked before this file was written). Rule,
fixed there: skip a #382 entry when NQ is not leading ES in the trade's direction,
    div = (NQ close / NQ RTH open - 1) - (ES close / ES RTH open - 1) at the entry bar's close, x side,
flagged when div < 0.0011664 (folds 1-4 lower tercile, never re-fitted). Folds 1-4 were the discovery; this script reads
folds 5-8 only. The chain is tools/noise_t74_giveback.py chain() (same ~0.5% rebuild caveat); the lockbox (after the chain
end) is never loaded - ES bars are cut at the chain end and the script refuses anything past it.

    python tools/noise_w93_holdout.py      -> prints the table, writes C:\EdgeLog\_anatomy_cache\w93_loser\holdout_folds5to8.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import noise_t74_giveback as t74  # noqa: E402
from noise_w93_loser_anatomy import bars, RUN  # noqa: E402
from augur_engine.drawdowns import four_numbers  # noqa: E402

OUT = r"C:\EdgeLog\_anatomy_cache\w93_loser"
HOLDOUT = {5, 6, 7, 8}
CUT = 0.0011664


def main():
    os.makedirs(OUT, exist_ok=True)
    tr, A, idx, meta = t74.chain()
    tr = [t for t in tr if t[0] in HOLDOUT]
    run = json.load(open(RUN))
    end = run["validate"]["windows"]["optimize"][1]
    if pd.Timestamp(meta["wf"]["to"]) > pd.Timestamp(end):
        raise SystemExit("REFUSED - chain runs past the optimize end %s (lockbox)" % end)
    ix = pd.DatetimeIndex(idx)
    ix = ix.tz_convert("America/New_York").tz_localize(None) if ix.tz is not None else ix
    d0 = str(ix[tr[0][1]].date())
    es = bars("ES", run["data_source"], d0, end)
    if es.index[-1].normalize() > pd.Timestamp(end):
        raise SystemExit("REFUSED - ES bars past the optimize end (lockbox)")
    C, O = np.asarray(A["close"], float), np.asarray(A["open"], float)
    nq = pd.DataFrame({"o": O, "c": C}, index=ix)
    nq_open = nq.o.groupby(nq.index.normalize()).transform("first")
    es_open = es.o.groupby(es.index.normalize()).transform("first")
    t = ix[[x[1] for x in tr]]
    r_nq = (nq.c / nq_open - 1).iloc[[x[1] for x in tr]].values
    r_es = (es.c / es_open - 1).reindex(t).values
    side = np.asarray([x[3] for x in tr], float)
    div = (r_nq - r_es) * side
    flag = div < CUT                       # NaN (no ES bar) -> not flagged, kept
    size = np.asarray([x[6] for x in tr])
    raw = np.asarray([x[5] for x in tr])
    usd = size * (raw - meta["cost"]) * meta["mult"]
    dates = [ix[x[1] - 1].normalize() for x in tr]
    sess = pd.Index(sorted({x.normalize() for x in ix if pd.Timestamp(d0) <= x.normalize() <= pd.Timestamp(meta["wf"]["to"])}))
    years = len(sess) / 252.0
    fold = np.asarray([x[0] for x in tr])

    def arm(keep):
        daily = pd.Series(usd[keep], index=[d for d, k in zip(dates, keep) if k]).groupby(level=0).sum().reindex(sess, fill_value=0.0)
        f = four_numbers(daily, years=years)
        return f, pd.Series(usd[keep]).groupby(fold[keep]).sum()

    fh, foldh = arm(np.ones(len(tr), bool))
    fs, folds = arm(~flag)
    won = int((folds.reindex(foldh.index, fill_value=0) > foldh).sum())
    per = pd.DataFrame({"fold": fold, "usd": usd, "flag": flag})
    g = per.groupby(["fold", "flag"]).usd.mean().unstack()
    worse_folds = int((g[True] < g[False]).sum())
    flagged_net = float(usd[flag].sum())
    keys = ("roc30", "dd5_usd", "dd_pct_peak", "sortino", "net", "max_dd", "one_episode")
    rows = {n: {k: (float(f[k]) if isinstance(f[k], (int, float, np.floating)) else f[k]) for k in keys}
            for n, f in (("hold", fh), ("skip", fs))}
    ok = (fs["roc30"] > fh["roc30"] and fs["sortino"] > fh["sortino"] and won >= 3 and worse_folds >= 3
          and flagged_net < 0 and (not fs["one_episode"] or fs["one_episode"] == fh["one_episode"]))
    res = dict(rows=rows, folds_won=won, folds=len(foldh), trades=len(tr), skipped=int(flag.sum()),
               flagged_net_usd=round(flagged_net), flagged_per_trade=round(float(usd[flag].mean()), 1),
               kept_per_trade=round(float(usd[~flag].mean()), 1), flagged_worse_folds=worse_folds,
               fold_hold=foldh.round(0).to_dict(), fold_skip=folds.round(0).to_dict(), years=round(years, 2),
               window=[d0, meta["wf"]["to"]], verdict="PASS" if ok else "FAIL")
    print(json.dumps(res, indent=1, default=str))
    with open(os.path.join(OUT, "holdout_folds5to8.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)


if __name__ == "__main__":
    main()
