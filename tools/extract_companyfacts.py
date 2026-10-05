# -*- coding: utf-8 -*-
"""SEC bulk COMPANYFACTS -> one flat file of share-count facts, AS FILED (TV, public-data scout; MANAGER #73 GO BULK for
STRATEGY-BEATING NETISS r1, docs/PREREG ../tools/rocfrontier/PREREG_NETISS_R1.txt [D1]-[D2]).

SOURCE (public, no key; one request): https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip - every XBRL fact
of every filer, one JSON per CIK, and EVERY filing that carried each fact (accn, fy, fp, form, filed, frame) - so the FIRST
filed date of a value is known, which the frames API cannot give (it keeps only the last-filed fact).
PHOTOGRAPH: C:\\EdgeLog\\_research_cache\\xbrl_companyfacts\\companyfacts.zip, byte for byte, with URL / UTC start + finish /
bytes / sha256 in companyfacts_provenance.json (written by --provenance from the fetch stamps); never refetched into a result.

EXTRACT: concepts dei:EntityCommonStockSharesOutstanding, us-gaap:CommonStockSharesOutstanding,
us-gaap:WeightedAverageNumberOfSharesOutstandingBasic (unit 'shares'), for the CIKs of a symbol map
(tools/map_symbols_cik.py output; optionally restricted to a symbol file), one row per (fact x filing):
  cik, symbols (';' list of the universe symbols on that CIK), concept, unit, val, start, end, accn, fy, fp, form, filed, frame
Facts FILED on or after 2025-06-30 are not extracted (the sealed year); consumers cut again at read.

    python tools/extract_companyfacts.py --provenance                       # write the provenance JSON from the fetch stamps
    python tools/extract_companyfacts.py [--map CSV] [--symbols FILE] [--out CSV]
"""
import argparse, datetime, hashlib, io, json, os, zipfile

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\xbrl_companyfacts"
ZIP = os.path.join(RAW, "companyfacts.zip")
URL = "https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip"
MAP = r"C:\EdgeLog\_research_cache\edgar\symbol_cik_map_wide_symbols_siporb_floor_2016_2025.csv"
CUT = "2025-06-30"
CONCEPTS = [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"),
            ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic")]


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 22), b""):
            h.update(b)
    return h.hexdigest()


def provenance():
    st = open(os.path.join(RAW, "fetch_started_utc.txt")).read().strip()
    fi = open(os.path.join(RAW, "fetch_finished_utc.txt")).read().strip()
    d = dict(url=URL, fetched_started_utc=st, fetched_finished_utc=fi, bytes=os.path.getsize(ZIP), sha256=sha(ZIP),
             user_agent="EdgeLog research tool edgelog-research@example.com", method="curl, one GET, saved byte for byte")
    json.dump({"companyfacts.zip": d}, open(os.path.join(RAW, "companyfacts_provenance.json"), "w"), indent=1)
    print(json.dumps(d, indent=1))


def extract(map_csv, symbols_file, out):
    M = pd.read_csv(map_csv, dtype=str, keep_default_na=False)          # tickers like NA / NAN / NULL stay strings
    M = M[M["cik"] != ""]
    if symbols_file:
        want = set(l.strip().upper() for l in open(symbols_file) if l.strip())
        M = M[M["symbol"].isin(want)]
    syms = M.groupby("cik")["symbol"].apply(lambda x: ";".join(sorted(set(x)))).to_dict()
    rows, found, late = [], set(), 0
    with zipfile.ZipFile(ZIP) as z:
        names = set(z.namelist())
        for cik, sy in syms.items():
            fn = "CIK%s.json" % cik.zfill(10)
            if fn not in names:
                continue
            d = json.loads(z.read(fn)); found.add(cik)
            facts = d.get("facts", {})
            for tax, con in CONCEPTS:
                units = facts.get(tax, {}).get(con, {}).get("units", {})
                for unit, lst in units.items():
                    for f in lst:
                        if str(f.get("filed", "")) >= CUT:
                            late += 1; continue
                        rows.append((cik, sy, "%s:%s" % (tax, con), unit, f.get("val"), f.get("start"), f.get("end"), f.get("accn"),
                                     f.get("fy"), f.get("fp"), f.get("form"), f.get("filed"), f.get("frame")))
    F = pd.DataFrame(rows, columns=["cik", "symbols", "concept", "unit", "val", "start", "end", "accn", "fy", "fp", "form", "filed", "frame"])
    F.to_csv(out, index=False)
    man = dict(built_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), zip_sha256=sha(ZIP), map=map_csv,
               map_sha256=sha(map_csv), symbols_file=symbols_file, symbols_file_sha256=sha(symbols_file) if symbols_file else None,
               ciks_requested=len(syms), ciks_found_in_zip=len(found), ciks_missing=sorted(set(syms) - found)[:500],
               rows=len(F), rows_cut_filed_on_or_after_2025_06_30=late, out=out, out_sha256=sha(out),
               per_concept={c: int(n) for c, n in F.groupby("concept").size().items()},
               ciks_per_concept={c: int(n) for c, n in F.groupby("concept")["cik"].nunique().items()},
               filed_range=[str(F["filed"].min()), str(F["filed"].max())])
    json.dump(man, open(os.path.splitext(out)[0] + "_manifest.json", "w"), indent=1)
    print("companyfacts extract: %d rows, %d of %d CIKs found, %d facts cut (filed >= %s) -> %s" % (len(F), len(found), len(syms), late, CUT, out))
    print("per concept:", man["per_concept"], "| CIKs per concept:", man["ciks_per_concept"], "| filed", man["filed_range"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--provenance", action="store_true"); ap.add_argument("--map", default=MAP)
    ap.add_argument("--symbols", default=None); ap.add_argument("--out", default=os.path.join(RAW, "shares_asfiled_wide.csv")); a = ap.parse_args()
    if a.provenance:
        provenance()
    else:
        extract(a.map, a.symbols, a.out)
