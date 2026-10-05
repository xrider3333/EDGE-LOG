# -*- coding: utf-8 -*-
"""SEC INSIDER TRANSACTIONS (Forms 3 / 4 / 5) - the quarterly data sets, 2006Q1 on (TV, public-data scout, MANAGER #62).

SOURCE (public, no key): https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/YYYYqN_form345.zip
Each zip holds tab-separated tables: SUBMISSION (accession, filing date, issuer CIK + ticker), REPORTINGOWNER (who, and the
relationship: director / officer / ten-percent owner), NONDERIV_TRANS (date, code, shares, price, acquired/disposed).
PHOTOGRAPH RULE: zips saved byte for byte under C:\\EdgeLog\\_research_cache\\form4\\ with URL / time / bytes / sha256 in
form4_provenance.json; a second fetch REFUSES to overwrite. CONTACT STRING: the house's neutral one, never the owner's address.

DERIVED (rebuilt from the zips only): form4_ndx_open_market.csv - Nasdaq-100 members' (tools/data/ndx_members.csv tickers, via
the EDGAR ticker map of tools/fetch_edgar_calendar.py) OPEN-MARKET purchases (code P) and sales (code S) of non-derivative
stock, one row per transaction: filing_date, trans_date, ticker, issuer_cik, owner, roles, code, shares, price, value.
Filing date is the date the market could know it (Form 4 is due within two business days of the trade).

    python tools/fetch_form4.py            # fetch every quarter not yet saved (refuses existing files) + build
    python tools/fetch_form4.py --build    # rebuild the derived CSV from the saved zips only
"""
import argparse, datetime, hashlib, io, json, os, sys, time, urllib.request, zipfile

import pandas as pd

RAW = r"C:\EdgeLog\_research_cache\form4"
EDGAR = r"C:\EdgeLog\_research_cache\edgar"
PROV = os.path.join(RAW, "form4_provenance.json")
OUT = os.path.join(RAW, "form4_ndx_open_market.csv")
URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/%dq%d_form345.zip"
UA = {"User-Agent": "EdgeLog research tool edgelog-research@example.com", "Accept-Encoding": "identity"}
LAST = (2025, 2)                      # the quarter holding 2025-06-29; later quarters are lockbox-era and not fetched here


def quarters():
    y, q = 2006, 1
    while (y, q) <= LAST:
        yield y, q
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)


def do_fetch():
    os.makedirs(RAW, exist_ok=True)
    prov = json.load(open(PROV)) if os.path.exists(PROV) else {}
    for y, q in quarters():
        dst = os.path.join(RAW, "%dq%d_form345.zip" % (y, q))
        if os.path.exists(dst):
            continue                                           # already photographed: never refetched
        time.sleep(0.3)
        raw = urllib.request.urlopen(urllib.request.Request(URL % (y, q), headers=UA), timeout=300).read()
        with open(dst, "wb") as f:
            f.write(raw)
        prov[os.path.basename(dst)] = dict(url=URL % (y, q), fetched_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                                           bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        json.dump(prov, open(PROV, "w"), indent=1)
        print("  %dq%d %.1f MB" % (y, q, len(raw) / 1e6), flush=True)


def ndx_ciks():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    want = set(pd.read_csv(os.path.join(root, "tools", "data", "ndx_members.csv"))["ticker"].str.upper())
    tk = json.load(open(os.path.join(EDGAR, "company_tickers.json"), "rb"))
    return {int(v["cik_str"]): v["ticker"].upper() for v in tk.values() if v["ticker"].upper() in want}


def read(z, name):
    hit = [n for n in z.namelist() if n.upper().endswith(name)]
    return pd.read_csv(io.BytesIO(z.read(hit[0])), sep="\t", dtype=str, low_memory=False) if hit else pd.DataFrame()


def build():
    ciks = ndx_ciks(); out = []
    for fn in sorted(f for f in os.listdir(RAW) if f.endswith("_form345.zip")):
        with zipfile.ZipFile(os.path.join(RAW, fn)) as z:
            S, O, T = read(z, "SUBMISSION.TSV"), read(z, "REPORTINGOWNER.TSV"), read(z, "NONDERIV_TRANS.TSV")
        if S.empty or T.empty:
            print("  %s: missing tables" % fn); continue
        S = S[pd.to_numeric(S["ISSUERCIK"], errors="coerce").isin(ciks.keys())]
        T = T[T["TRANS_CODE"].isin(["P", "S"]) & T["ACCESSION_NUMBER"].isin(S["ACCESSION_NUMBER"])]
        roles = O.groupby("ACCESSION_NUMBER").agg(owner=("RPTOWNERNAME", "first"),
                                                  roles=("RPTOWNER_RELATIONSHIP", lambda x: ";".join(sorted(set(";".join(x.dropna()).split(";"))))))
        m = T.merge(S[["ACCESSION_NUMBER", "FILING_DATE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"]], on="ACCESSION_NUMBER").merge(roles, on="ACCESSION_NUMBER", how="left")
        m["ticker"] = pd.to_numeric(m["ISSUERCIK"]).map(ciks)
        out.append(m)
        print("  %s: %d open-market rows" % (fn, len(m)), flush=True)
    D = pd.concat(out, ignore_index=True)
    D["shares"] = pd.to_numeric(D["TRANS_SHARES"], errors="coerce"); D["price"] = pd.to_numeric(D["TRANS_PRICEPERSHARE"], errors="coerce")
    D["value"] = D["shares"] * D["price"]
    D = D.rename(columns={"FILING_DATE": "filing_date", "TRANS_DATE": "trans_date", "ISSUERCIK": "issuer_cik", "TRANS_CODE": "code",
                          "TRANS_ACQUIRED_DISP_CD": "acq_disp", "ACCESSION_NUMBER": "accession"})
    for c in ("filing_date", "trans_date"):              # the data sets write 31-MAR-2006; consumers get ISO dates
        D[c] = pd.to_datetime(D[c], format="%d-%b-%Y", errors="coerce").dt.strftime("%Y-%m-%d")
    cols = ["filing_date", "trans_date", "ticker", "issuer_cik", "owner", "roles", "code", "acq_disp", "shares", "price", "value", "accession"]
    D[cols].to_csv(OUT, index=False)
    print("form4 open-market rows %d (P %d / S %d), %d tickers -> %s" % (len(D), (D["code"] == "P").sum(), (D["code"] == "S").sum(),
          D["ticker"].nunique(), OUT))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--build", action="store_true"); a = ap.parse_args()
    if not a.build:
        do_fetch()
    build()
