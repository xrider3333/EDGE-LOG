# -*- coding: utf-8 -*-
"""SEC bulk COMPANYFACTS -> FUNDAMENTALS as filed (Custom ML, docs/SCOPE_CUSTOM-ML_2026-10-07.md, queue items 1-3).

Same photograph as tools/extract_companyfacts.py (companyfacts.zip, its provenance JSON; never refetched), same symbol ->
CIK map, same cut (facts FILED on or after 2025-06-30 are not extracted). That tool keeps the three share-count concepts
for NETISS; this one keeps the balance-sheet, income and cash-flow concepts below, one row per (fact x filing):
  cik, symbols, concept, unit, val, start, end, accn, fy, fp, form, filed, frame
Nothing is deduplicated here: a consumer takes min(filed) per (cik, concept, start, end) so a value is known only from
the session after its FIRST filing; amendments and later re-filings never overwrite history. Written as parquet parts
(500 CIKs each) plus a manifest, so memory stays small.

    python tools/extract_fundamentals.py [--map CSV] [--out DIR]
"""
import argparse
import datetime
import json
import os
import sys
import zipfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_companyfacts as X                                       # noqa: E402  ZIP, MAP, CUT, sha

CONCEPTS = [("us-gaap", c) for c in (
    # balance sheet
    "Assets", "Liabilities", "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "AssetsCurrent", "LiabilitiesCurrent", "CashAndCashEquivalentsAtCarryingValue", "LongTermDebt",
    "LongTermDebtNoncurrent", "PropertyPlantAndEquipmentNet", "Goodwill", "IntangibleAssetsNetExcludingGoodwill",
    "InventoryNet", "AccountsReceivableNetCurrent", "RetainedEarningsAccumulatedDeficit",
    # income statement
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "CostOfRevenue",
    "CostOfGoodsAndServicesSold", "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss", "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense", "InterestExpense", "IncomeTaxExpenseBenefit", "EarningsPerShareBasic",
    "EarningsPerShareDiluted", "DepreciationDepletionAndAmortization",
    # cash flow
    "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsForRepurchaseOfCommonStock", "PaymentsOfDividends", "ProceedsFromIssuanceOfCommonStock")]
OUT = os.path.join(X.RAW, "fundamentals_asfiled")
COLS = ["cik", "symbols", "concept", "unit", "val", "start", "end", "accn", "fy", "fp", "form", "filed", "frame"]


def extract(map_csv, out, chunk=500):
    os.makedirs(out, exist_ok=True)
    M = pd.read_csv(map_csv, dtype=str, keep_default_na=False)
    M = M[M["cik"] != ""]
    syms = M.groupby("cik")["symbol"].apply(lambda x: ";".join(sorted(set(x)))).to_dict()
    ciks = sorted(syms)
    found, late, parts, per_concept = set(), 0, [], {}
    with zipfile.ZipFile(X.ZIP) as z:
        names = set(z.namelist())
        for p0 in range(0, len(ciks), chunk):
            rows = []
            for cik in ciks[p0:p0 + chunk]:
                fn = "CIK%s.json" % cik.zfill(10)
                if fn not in names:
                    continue
                d = json.loads(z.read(fn)); found.add(cik)
                facts = d.get("facts", {})
                for tax, con in CONCEPTS:
                    for unit, lst in facts.get(tax, {}).get(con, {}).get("units", {}).items():
                        for f in lst:
                            if str(f.get("filed", "")) >= X.CUT:
                                late += 1; continue
                            rows.append((cik, syms[cik], con, unit, f.get("val"), f.get("start"), f.get("end"),
                                         f.get("accn"), f.get("fy"), f.get("fp"), f.get("form"), f.get("filed"),
                                         f.get("frame")))
            F = pd.DataFrame(rows, columns=COLS)
            for c in ("cik", "symbols", "concept", "unit", "fp", "form"):
                F[c] = F[c].astype("category")
            F["val"] = pd.to_numeric(F["val"], errors="coerce")
            fn_out = os.path.join(out, "part-%03d.parquet" % (p0 // chunk))
            F.to_parquet(fn_out, index=False)
            parts.append(dict(file=os.path.basename(fn_out), rows=len(F), sha256=X.sha(fn_out)))
            for c, n in F.groupby("concept", observed=True).size().items():
                per_concept[c] = per_concept.get(c, 0) + int(n)
            print("part %d: %d CIKs done, %d rows" % (p0 // chunk, min(p0 + chunk, len(ciks)), len(F)), flush=True)
    man = dict(built_at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"), zip_sha256=X.sha(X.ZIP),
               map=map_csv, map_sha256=X.sha(map_csv), concepts=["%s:%s" % c for c in CONCEPTS],
               ciks_requested=len(ciks), ciks_found_in_zip=len(found), ciks_missing=sorted(set(ciks) - found)[:500],
               rows=sum(p["rows"] for p in parts), rows_cut_filed_on_or_after_2025_06_30=late, per_concept=per_concept,
               parts=parts)
    json.dump(man, open(os.path.join(out, "fundamentals_manifest.json"), "w"), indent=1)
    print("fundamentals extract: %d rows, %d of %d CIKs, %d facts cut -> %s" % (man["rows"], len(found), len(ciks), late, out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=X.MAP)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    extract(a.map, a.out)
