# -*- coding: utf-8 -*-
"""SYMBOL -> SEC CIK map for a stock universe list, delisted names included (TV, public-data scout; NETISS r1 / XBRL pulls).

Inputs (all photographs already on disk, no fetch here):
  universe   default C:\\EdgeLog\\alpaca_cache\\xgap\\wide_symbols_siporb_floor_2016_2025.txt (one symbol a line)
  names      C:\\EdgeLog\\alpaca_cache\\siporb\\assets.csv (Alpaca asset names, active + inactive)
  tickers    C:\\EdgeLog\\_research_cache\\edgar\\company_tickers.json (SEC: CURRENT ticker -> CIK)
  lookup     C:\\EdgeLog\\_research_cache\\edgar\\cik-lookup-data.txt (SEC: every entity name incl. former names -> CIK)
Method, first hit wins:
  1. current_ticker  the symbol is a current SEC ticker AND the SEC name agrees with the Alpaca name (similarity >= 0.6 after
                     normalising) - a reused ticker (old company delisted, symbol now another firm's) fails this check
  2. name_exact      the normalised Alpaca name equals exactly one CIK's normalised name in the lookup file
  3. current_ticker_name_mismatch / name_ambiguous / unmapped  - listed for review, never silently used
Output: C:\\EdgeLog\\_research_cache\\edgar\\symbol_cik_map_<universe stem>.csv (symbol, cik, method, alpaca_name, sec_name, sim)

    python tools/map_symbols_cik.py [--universe FILE]
"""
import argparse, difflib, json, os, re
from collections import defaultdict

import pandas as pd

EDGAR = r"C:\EdgeLog\_research_cache\edgar"
UNIVERSE = r"C:\EdgeLog\alpaca_cache\xgap\wide_symbols_siporb_floor_2016_2025.txt"
ASSETS = r"C:\EdgeLog\alpaca_cache\siporb\assets.csv"
DROP = set("INC INCORPORATED CORP CORPORATION CO COMPANY LTD LIMITED PLC LP LLC L P HOLDINGS HOLDING GROUP THE CLASS A B C "
           "COMMON STOCK SHARES SHARE ORDINARY AMERICAN DEPOSITARY ADS ADR SHS NEW DE NV SA AG SE CL CAP PAR VALUE USD "
           "REGISTERED SUBORDINATE VOTING UNITS UNIT DEL".split())


def norm(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper().replace("&", " AND "))
    return " ".join(w for w in s.split() if w not in DROP)


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


NONCOMMON = re.compile(r"DEBENTURE|\bNOTES?\b|PREFERRED|\bPFD\b|WARRANT|\bRIGHTS\b|\bUNITS?\b|FIXED-RATE|BABY BOND", re.I)   # "the right to receive" (ADRs) is not a rights listing


def agrees(an, t):
    """same company: similar names, or one normalised name's words all inside the other's (ADR / registry-share wording)"""
    a, b = set(norm(an).split()), set(norm(t).split())
    return sim(an, t) >= 0.6 or (bool(b) and b <= a) or (bool(a) and a <= b)


def main(universe):
    syms = [l.strip().upper() for l in open(universe) if l.strip()]
    A = pd.read_csv(ASSETS)
    A["rank"] = (A["status"] != "active").astype(int)                        # prefer the active row's name
    name_of = A.sort_values("rank").drop_duplicates("symbol").set_index("symbol")["name"].to_dict()
    tk = json.load(open(os.path.join(EDGAR, "company_tickers.json"), "rb"))
    cur = {}
    for v in tk.values():
        cur.setdefault(v["ticker"].upper(), (str(v["cik_str"]).zfill(10), v["title"]))
    by_name = defaultdict(set); title = {}
    with open(os.path.join(EDGAR, "cik-lookup-data.txt"), encoding="latin-1") as f:
        for line in f:
            parts = line.rstrip("\n").rsplit(":", 2)
            if len(parts) == 3 and parts[1].isdigit():
                n = norm(parts[0])
                if n:
                    by_name[n].add(parts[1].zfill(10)); title.setdefault(parts[1].zfill(10), parts[0])
    rows = []
    for s in syms:
        an = name_of.get(s, ""); an = an if isinstance(an, str) else ""
        if an and NONCOMMON.search(an):                                    # a debenture / preferred / unit listing: not the firm's shares
            rows.append((s, "", "non_common", an, "", 0.0)); continue
        if s in cur:
            c, t = cur[s]; r = sim(an, t) if an else 1.0
            if not an or agrees(an, t):
                rows.append((s, c, "current_ticker", an, t, round(r, 2))); continue
        hit = by_name.get(norm(an), set()) if an else set()
        if len(hit) == 1:
            c = next(iter(hit)); rows.append((s, c, "name_exact", an, title.get(c, ""), 1.0)); continue
        if s in cur:
            c, t = cur[s]; rows.append((s, "", "current_ticker_name_mismatch", an, "%s (CIK %s)" % (t, c), round(sim(an, t), 2))); continue
        rows.append((s, "", "name_ambiguous" if len(hit) > 1 else "unmapped", an, ";".join(sorted(hit))[:200], 0.0))
    M = pd.DataFrame(rows, columns=["symbol", "cik", "method", "alpaca_name", "sec_name", "sim"])
    out = os.path.join(EDGAR, "symbol_cik_map_%s.csv" % os.path.splitext(os.path.basename(universe))[0])
    M.to_csv(out, index=False)
    print("symbols %d -> %s" % (len(M), out)); print(M["method"].value_counts().to_dict())
    print("mapped %d (%.1f %%), distinct CIKs %d" % ((M["cik"] != "").sum(), 100 * (M["cik"] != "").mean(), M.loc[M["cik"] != "", "cik"].nunique()))
    return M


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--universe", default=UNIVERSE); a = ap.parse_args()
    main(a.universe)
