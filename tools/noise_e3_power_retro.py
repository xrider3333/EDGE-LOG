r"""E3 POWER + COST RETRO (MANAGER #162 / scope SCOPE_RESEARCH_LOOP_2026-11-03 w86): which DEAD verdicts in the 289-entry
NOISE-lane tested catalogue could never have decided?

The catalogue (C:\EdgeLog\_anatomy_cache\noise_hunt1016\catalogue\tested_catalogue.json) stores each verdict as TEXT, not as
numbers, so this tool parses what each verdict printed (trade count, trades/yr x years, PF, pts/trade, $ net) and asks,
per entry, two questions with the house's own numbers:

  POWER  - with N trades, the smallest per-trade edge a one-sided 5% test finds 4 times in 5 is
           MDE = 2.487 x sd / sqrt(N) points, sd = NOISE #382's per-trade sd on the WF chain (the lane's only measured
           intraday NQ per-trade spread; t74 rebuild). An entry is UNDERPOWERED when its MDE is above #382's own WF edge per
           trade (the effect size this lane actually lives on): it could not have found a crown-sized edge. (MDE vs the
           0.533 cost is useless: at sd ~61 pt every test needs ~80k trades.) Most verdicts print ROC / t / fold counts
           instead of N, so words and t-stats are read too: |t| < 1.645 with a positive point estimate = UNDERPOWERED.
  COST   - an entry whose verdict printed a gross edge (PF > 1, positive pts or $) but died on cost / net is COST-KILLED.

Classes: COST-KILLED (gross positive, died on cost), UNDERPOWERED (MDE > cost; could never decide), DEAD-REAL (enough
trades, still dead), NO-NUMBERS (verdict printed nothing countable - a read, a map check, a design note). Revivable =
UNDERPOWERED and gross-positive. A proxy sd from one leg is a coarse yardstick: an entry's own sd can be wider (ETH,
stocks, daily holds), which only makes it MORE underpowered - so the UNDERPOWERED count is a floor for NQ intraday ideas.

    python tools/noise_e3_power_retro.py      -> C:\EdgeLog\_anatomy_cache\e3_power_retro\retro.csv + summary.json
"""
import json
import math
import os
import re
import sys

import pandas as pd

CAT = r"C:\EdgeLog\_anatomy_cache\noise_hunt1016\catalogue\tested_catalogue.json"
CHAIN = r"C:\EdgeLog\_anatomy_cache\t74_giveback\chain_382_mfe.csv"
OUT = r"C:\EdgeLog\_anatomy_cache\e3_power_retro"
COST = 0.533
Z80 = 2.487
NUM = r"(\d[\d,]*(?:\.\d+)?)"


def _f(s):
    return float(s.replace(",", ""))


def parse(text):
    """Countable facts printed in one verdict string."""
    t = text.replace("\u2212", "-")
    out = {}
    m = re.search(r"\bn\s*=\s*" + NUM, t, re.I) or re.search(NUM + r"\s*(?:closed\s+|OOS\s+|WF\s+|IS\s+)?trades\b(?!\s*/)", t, re.I)
    if m:
        out["n"] = _f(m.group(1))
    m = re.search(NUM + r"(?:\s*-\s*" + NUM + r")?\s*trades\s*/\s*y", t, re.I)
    if m:
        out["per_yr"] = _f(m.group(2) or m.group(1)) if m.group(2) else _f(m.group(1))
    m = re.search(r"/\s*(\d+)\s*y\b", t) or re.search(r"\b(\d+)\s*(?:yrs|years)\b", t, re.I)
    if m:
        out["years"] = float(m.group(1))
    pfs = [float(x) for x in re.findall(r"PF\s*([0-9]+\.[0-9]+)", t)]
    if pfs:
        out["pf"] = max(pfs)
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\s*(?:pt|pts)\b(?:\s*(?:/|a|per)\s*trade|\s*gross)", t, re.I)
    if m:
        out["pts"] = float(m.group(1))
    out["cost_word"] = bool(re.search(r"\bcost|after cost|net of cost|0\.783|0\.533|fees?\b|slippage", t, re.I))
    out["pos_word"] = bool(re.search(r"gross\s*\+|positive|\+\$|\$\d[\d.,]*k?\s*(?:gross|before)|lift", t, re.I))
    out["thin_word"] = bool(re.search(r"\bthin\b|too few|underpowered|power\b|n too small|tiny sample", t, re.I))
    if "n" not in out and "per_yr" in out and "years" in out:
        out["n"] = out["per_yr"] * out["years"]
    return out


def classify(f, sd, edge, text):
    """One class per verdict, first rule that fires wins (order = how decisive the evidence is)."""
    t = text
    n = f.get("n")
    mde = Z80 * sd / math.sqrt(n) if n and n > 0 else None
    tm = re.search(r"t\s*=?\s*(-?\d+\.\d+)", t)
    tstat = float(tm.group(1)) if tm else None
    km = re.findall(r"(\d+)\s*(?:/|of)\s*(\d+)(?!\s*(?:trade|y))", t)
    wins = [(int(a), int(b)) for a, b in km if int(b) >= 3 and int(a) <= int(b)]
    gross_pos = ((f.get("pf") or 0) > 1.0 or (f.get("pts") or 0) > 0 or f["pos_word"]
                 or bool(re.search(r"gross\s*(?:~|about)?\s*\+?\$?\d", t, re.I) and not re.search(r"gross\s*~\s*0", t, re.I))
                 or (tstat is not None and tstat > 0))
    if re.search(r"look-?ahead|leak|artifact|oracle|placebo|not reproducible|bug", t, re.I):
        return "DEAD-REAL", mde, gross_pos, "mechanism invalid (leak / artifact / oracle)"
    if re.search(r"^\s*OPEN|forward shadow|read at \d+", t, re.I):
        return "OPEN", mde, gross_pos, "still open / forward"
    if re.search(r"cost", t, re.I) and (re.search(r"gross", t, re.I) or (f.get("pf") or 0) > 1.0):
        if not re.search(r"gross\s*~\s*0", t, re.I):
            return "COST-KILLED", mde, gross_pos, "gross edge printed, died on cost"
    if re.search(r"MDE|underpowered|thin|too few|power", t, re.I) or (mde is not None and mde > edge):
        why = "MDE %.1f pt > crown edge %.1f pt" % (mde, edge) if mde is not None and mde > edge else "verdict says thin / MDE / power"
        return "UNDERPOWERED", mde, gross_pos, why
    if tstat is not None and 0 < tstat < 1.645:
        return "UNDERPOWERED", mde, gross_pos, "positive point estimate, t %.2f < 1.645" % tstat
    if wins and all(a / b < 0.5 for a, b in wins):
        return "DEAD-REAL", mde, gross_pos, "decisive count %s" % ",".join("%d/%d" % w for w in wins)
    if re.search(r"gross\s*~\s*0|negative|loses to|below null|fails?|DEAD|CLOSED|KILLED|0 of|no lift|nothing", t, re.I):
        return "DEAD-REAL", mde, gross_pos, "verdict decisive in words"
    return "NO-NUMBERS", mde, gross_pos, "nothing countable"


def main():
    chain = pd.read_csv(CHAIN)
    sd = float(chain["raw"].std(ddof=1))
    edge = float(chain["raw"].mean())         # #382's own WF edge per trade (pts): the effect size the lane lives on
    cat = json.load(open(CAT, encoding="utf-8"))
    rows = []
    for i, e in enumerate(cat):
        f = parse(e["verdict"])
        cls, mde, gp, why = classify(f, sd, edge, e["verdict"])
        rows.append({"i": i, "cat": e["cat"], "mechanism": e["mechanism"], "verdict": e["verdict"], "ref": e["ref"],
                     "n": f.get("n"), "pf": f.get("pf"), "pts": f.get("pts"), "mde_pts": round(mde, 3) if mde else None,
                     "gross_pos": gp, "class": cls, "why": why, "revivable": cls == "UNDERPOWERED" and gp})
    df = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    df.to_csv(os.path.join(OUT, "retro.csv"), index=False)
    summ = {"entries": len(df), "sd_pts_proxy": round(sd, 3), "crown_edge_pts": round(edge, 3), "cost_pts": COST,
            "n_for_mde_at_crown_edge": math.ceil((Z80 * sd / edge) ** 2),
            "classes": df["class"].value_counts().to_dict(), "revivable": int(df["revivable"].sum()),
            "revivable_list": df[df["revivable"]][["i", "cat", "mechanism", "n", "pf", "mde_pts", "why", "verdict"]].to_dict("records")}
    json.dump(summ, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), indent=1, default=str)
    print(json.dumps({k: v for k, v in summ.items() if k != "revivable_list"}, indent=1))
    for r in summ["revivable_list"]:
        print("REVIVE #%d [%s] %s | %s || %s" % (r["i"], r["cat"], r["why"], r["mechanism"][:80], r["verdict"][:110]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
