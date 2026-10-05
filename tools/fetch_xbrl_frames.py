# -*- coding: utf-8 -*-
"""SEC XBRL FRAMES - share counts for every filer, 2015-2025 (TV, public-data scout; MANAGER #72 for STRATEGY-BEATING NETISS r1).

SOURCES (public, no key):
  https://data.sec.gov/api/xbrl/frames/<taxonomy>/<concept>/shares/<period>.json   one fact per filer per calendar period
      dei:EntityCommonStockSharesOutstanding            instants CY2015Q1I .. CY2025Q2I   (cover-page count)
      us-gaap:CommonStockSharesOutstanding              instants CY2015Q1I .. CY2025Q2I   (balance-sheet count)
      us-gaap:WeightedAverageNumberOfSharesOutstandingBasic  quarters CY2015Q1 .. CY2025Q2 + years CY2015 .. CY2024
  https://www.sec.gov/Archives/edgar/full-index/<YYYY>/QTR<n>/master.gz          2015Q1 .. 2025Q2: accession -> form, date filed
WHY THE INDEX: a frame row carries the accession number of the filing it came from but NOT its filing date, and a frame keeps
the LAST-FILED fact for the period (often the next year's comparative). The quarterly master index gives every accession's date
filed, so each fact is stamped with the day the market could know it, and facts filed on/after 2025-06-30 (or not found in the
2015Q1-2025Q2 indexes) are CUT from the derived file - the lockbox never reaches it.
PHOTOGRAPH RULE: every response saved byte for byte under C:\\EdgeLog\\_research_cache\\xbrl_frames\\ with URL / time / bytes /
sha256 in xbrl_frames_provenance.json; files already saved are never refetched. Neutral contact string, never the owner's address.

DERIVED: xbrl_shares_frames.csv  concept, frame, kind (instant / quarter / year), cik, entity, start, end, val, accn, form,
         filed, ticker_now (EDGAR's CURRENT ticker for the CIK - delisted names have none; map them by CIK, not ticker)
         xbrl_shares_manifest.json  counts per concept and frame, rows cut, the source shas.

    python tools/fetch_xbrl_frames.py            # fetch what is not saved yet + build
    python tools/fetch_xbrl_frames.py --build    # rebuild from the saved photographs only
"""
import argparse, datetime, gzip, hashlib, io, json, os, time, urllib.request

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\xbrl_frames"
EDGAR = r"C:\EdgeLog\_research_cache\edgar"
PROV = os.path.join(RAW, "xbrl_frames_provenance.json")
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
CUT = "2025-06-30"
CONCEPTS = [("dei", "EntityCommonStockSharesOutstanding", "instant"),
            ("us-gaap", "CommonStockSharesOutstanding", "instant"),
            ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "quarter"),
            ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "year")]
QUARTERS = [(y, q) for y in range(2015, 2026) for q in range(1, 5) if (y, q) <= (2025, 2)]


def frames():
    for tax, con, kind in CONCEPTS:
        if kind == "year":
            for y in range(2015, 2025):
                yield tax, con, kind, "CY%d" % y
        else:
            for y, q in QUARTERS:
                yield tax, con, kind, "CY%dQ%d%s" % (y, q, "I" if kind == "instant" else "")


def fetch(url, dst, prov):
    if os.path.exists(dst):
        return False
    time.sleep(0.3)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120).read()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "wb") as f:
        f.write(raw)
    prov[os.path.relpath(dst, RAW)] = dict(url=url, fetched_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                          bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return True


def do_fetch():
    prov = json.load(open(PROV)) if os.path.exists(PROV) else {}
    n = 0
    for tax, con, kind, per in frames():
        url = "https://data.sec.gov/api/xbrl/frames/%s/%s/shares/%s.json" % (tax, con, per)
        try:
            n += fetch(url, os.path.join(RAW, "frames", "%s_%s_%s.json" % (tax, con, per)), prov)
        except urllib.error.HTTPError as e:              # a period with no facts answers 404: recorded, not fatal
            prov["frames/%s_%s_%s.json" % (tax, con, per)] = dict(url=url, http_error=e.code)
        json.dump(prov, open(PROV, "w"), indent=1)
    for y, q in QUARTERS:
        url = "https://www.sec.gov/Archives/edgar/full-index/%d/QTR%d/master.gz" % (y, q)
        n += fetch(url, os.path.join(RAW, "full_index", "master_%dQ%d.gz" % (y, q)), prov)
        json.dump(prov, open(PROV, "w"), indent=1)
    print("fetched %d new files" % n)


def index_dates():
    """accession -> (form, date filed) from the saved quarterly master indexes."""
    out = {}
    for y, q in QUARTERS:
        fn = os.path.join(RAW, "full_index", "master_%dQ%d.gz" % (y, q))
        text = gzip.decompress(open(fn, "rb").read()).decode("latin-1")
        body = text.split("\n--------------------------------------------------------------------------------\n", 1)[-1]
        for line in body.splitlines():
            parts = line.split("|")
            if len(parts) == 5 and parts[4].endswith(".txt"):
                out[parts[4].rsplit("/", 1)[-1][:-4]] = (parts[2], parts[3])
    return out


def build():
    prov = json.load(open(PROV))
    acc = index_dates()
    tk = json.load(open(os.path.join(EDGAR, "company_tickers.json"), "rb"))
    now = {}
    for v in tk.values():
        now.setdefault(int(v["cik_str"]), v["ticker"].upper())
    rows, missing = [], []
    for tax, con, kind, per in frames():
        fn = os.path.join(RAW, "frames", "%s_%s_%s.json" % (tax, con, per))
        if not os.path.exists(fn):
            missing.append(per + " " + con); continue
        d = json.load(open(fn, "rb"))
        for r in d.get("data", []):
            rows.append(dict(concept="%s:%s" % (tax, con), frame=per, kind=kind, cik=int(r["cik"]), entity=r.get("entityName"),
                             start=r.get("start"), end=r.get("end"), val=r.get("val"), accn=r.get("accn")))
    F = pd.DataFrame(rows)
    hit = F["accn"].map(acc)
    F["form"] = hit.map(lambda x: x[0] if isinstance(x, tuple) else None)
    F["filed"] = hit.map(lambda x: x[1] if isinstance(x, tuple) else None)
    F["ticker_now"] = F["cik"].map(now)
    n_all = len(F); unknown = int(F["filed"].isna().sum()); late = int((F["filed"] >= CUT).sum())
    F = F[F["filed"].notna() & (F["filed"] < CUT)]
    out = os.path.join(RAW, "xbrl_shares_frames.csv")
    F.to_csv(out, index=False)
    man = dict(built_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), rows=len(F), rows_fetched=n_all,
               cut_filed_on_or_after_2025_06_30=late, cut_filing_not_in_2015Q1_2025Q2_index=unknown, missing_frames=missing,
               ciks=int(F["cik"].nunique()), ciks_with_current_ticker=int(F.loc[F["ticker_now"].notna(), "cik"].nunique()),
               per_concept={c: int(n) for c, n in F.groupby("concept").size().items()},
               per_frame={"%s %s" % k: int(n) for k, n in F.groupby(["concept", "frame"]).size().items()},
               sources={k: v.get("sha256") for k, v in prov.items()})
    json.dump(man, open(os.path.join(RAW, "xbrl_shares_manifest.json"), "w"), indent=1)
    print("xbrl_shares_frames: %d rows (%d fetched; cut %d filed >= %s, %d not in the 2015Q1-2025Q2 index), %d CIKs (%d with a "
          "current ticker) -> %s" % (len(F), n_all, late, CUT, unknown, man["ciks"], man["ciks_with_current_ticker"], out))
    print("per concept:", man["per_concept"], "| missing frames:", missing)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); a = ap.parse_args()
    if not a.build:
        do_fetch()
    build()
