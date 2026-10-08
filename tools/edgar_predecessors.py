# -*- coding: utf-8 -*-
"""PREDECESSOR CIKs for Nasdaq-100 members whose company changed its SEC registrant (TV, public-data scout; STRATEGY-BEATING #94
for EAP r1). The pinned earnings calendar (earnings_calendar_ndx.csv, 8f4f9f4b) joins members by their CURRENT CIK, so member
months before a re-domicile / spin / holding-company change have no release. This tool NEVER rebuilds that pinned file; it writes
two side files:
  edgar_predecessor_map.csv            symbol, predecessor_cik, predecessor_name, successor_cik, first_8k_date, last_8k_date,
                                       edgar_source_url, note   (one row per symbol x predecessor; non-CIK gaps listed with why)
  earnings_calendar_predecessors.csv   the predecessors' 8-K item-2.02 releases in the calendar's own columns, accepted before
                                       2025-06-30, only those not already rows of the pinned calendar
Submissions indexes are photographed into the calendar's raw folder with provenance (tools/fetch_edgar_calendar.py's fetch()).

    python tools/edgar_predecessors.py
"""
import json, os, sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_edgar_calendar as C  # noqa: E402

CUT = "2025-06-30"
# symbol, predecessor CIK, successor CIK, why (from SEC's cik-lookup-data.txt names + each CIK's own submissions index)
PRED = [("AVGO", "0001649338", "0001730168", "Broadcom Ltd (Singapore), the listed parent 2016-02 .. 2018-04; Broadcom Inc re-domiciled to Delaware 2018-04"),
        ("FOX", "0001308161", "0001754301", "Twenty-First Century Fox, Inc. carried FOX / FOXA until the 2019-03 Disney deal spun off Fox Corp"),
        ("FOXA", "0001308161", "0001754301", "as FOX"),
        ("MRVL", "0001058057", "0001835632", "Marvell Technology Group Ltd (Bermuda) until the 2021-04 re-domicile to Marvell Technology, Inc. (Delaware)"),
        ("CEG", "0001168165", "0001868275", "Constellation Energy Generation LLC (ex Exelon Generation) co-files the parent's 8-Ks; neither CIK has an item-2.02 8-K before 2022-05-12, so CEG's 2022-03..05 gap stays (checked, nothing to add)")]
NOT_CIK = [("TEAM", "0001650372", "same CIK: a foreign private issuer filing 6-K (no item codes) until the 2022-10 US re-domicile - 6-K releases cannot be told apart by item"),
           ("NXPI", "0001413447", "same CIK: a foreign private issuer filing 6-K until it moved to 10-K / 8-K in 2019 - same limit as TEAM"),
           ("DISH", "0001001082", "same CIK: DISH filed no item-2.02 8-K for its quarterly results in 2016-18 (press release + 10-Q only)"),
           ("SIRI", "0000908937", "same CIK: two results 8-Ks (2021-07-27, 2021-10-28) were tagged with item 9.01 only, no 2.02 - a tagging gap, not a CIK change")]


def main():
    prov = json.load(open(C.PROV))
    sub = os.path.join(C.RAW, "submissions")
    for cik in sorted(set(p[1] for p in PRED)):
        dst = os.path.join(sub, "CIK%s.json" % cik)
        if not os.path.exists(dst):
            d = json.loads(C.fetch("https://data.sec.gov/submissions/CIK%s.json" % cik, dst, prov))
            for f in d["filings"].get("files", []):
                C.fetch("https://data.sec.gov/submissions/" + f["name"], os.path.join(sub, f["name"]), prov, skip_existing=True)
    json.dump(prov, open(C.PROV, "w"), indent=1)
    pinned = pd.read_csv(C.OUT_EARN, dtype=str, keep_default_na=False)
    have = set(pinned["accession"])
    rows, maprows = [], []
    for sym, pc, sc, why in PRED:
        d = json.load(open(os.path.join(sub, "CIK%s.json" % pc), "rb"))
        blocks = [d["filings"]["recent"]] + [json.load(open(os.path.join(sub, f["name"]), "rb")) for f in d["filings"].get("files", [])]
        k8 = []
        for b in blocks:
            for i, form in enumerate(b["form"]):
                if form in ("8-K", "8-K/A"):
                    k8.append(dict(form=form, accepted=b["acceptanceDateTime"][i], items=b["items"][i] or "", accession=b["accessionNumber"][i],
                                   filing_date=b["filingDate"][i]))
        K = pd.DataFrame(k8)
        maprows.append(dict(symbol=sym, predecessor_cik=pc, predecessor_name=d.get("name"), successor_cik=sc,
                            first_8k_date=K["filing_date"].min() if len(K) else "", last_8k_date=K["filing_date"].max() if len(K) else "",
                            edgar_source_url="https://data.sec.gov/submissions/CIK%s.json" % pc, note=why))
        E = K[K["form"].isin(["8-K", "8-K/A"]) & K["items"].str.contains("2.02", regex=False)] if len(K) else K
        for _, r in E.iterrows():
            acc = pd.Timestamp(r["accepted"]).tz_convert("UTC") if pd.Timestamp(r["accepted"]).tzinfo else pd.Timestamp(r["accepted"], tz="UTC")
            et = acc.tz_convert("US/Eastern")
            if et.strftime("%Y-%m-%d") >= CUT or r["accession"] in have:
                continue
            rs, tm = C.reaction_session(acc)
            rows.append(dict(ticker=sym, ndx_tickers=sym, cik=pc, name=d.get("name"), form=r["form"], accepted_et=et.strftime("%Y-%m-%d %H:%M"),
                             reaction_session=rs, timing=tm, items=r["items"], accession=r["accession"]))
    for sym, cik, why in NOT_CIK:
        maprows.append(dict(symbol=sym, predecessor_cik="", predecessor_name="", successor_cik=cik, first_8k_date="", last_8k_date="",
                            edgar_source_url="", note="NOT A CIK CHANGE - " + why))
    A = pd.DataFrame(rows, columns=list(pinned.columns)).drop_duplicates(["ticker", "accession"]).sort_values(["ticker", "accepted_et"])
    mp = os.path.join(C.RAW, "edgar_predecessor_map.csv"); ap = os.path.join(C.RAW, "earnings_calendar_predecessors.csv")
    pd.DataFrame(maprows).to_csv(mp, index=False); A.to_csv(ap, index=False)
    print("map %d rows -> %s" % (len(maprows), mp))
    print("additions %d rows (%s) -> %s" % (len(A), A.groupby("ticker").size().to_dict(), ap))
    print("range:", A.groupby("ticker")["accepted_et"].agg(["min", "max"]).to_dict("index"))


if __name__ == "__main__":
    main()
