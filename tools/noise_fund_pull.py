# -*- coding: utf-8 -*-
"""NOISE scope (docs/SCOPE_NOISE_2026-10-05.md) - the fund bar pull and its data gates, by REUSING the TRANSFER r2 code
(tools/rocfrontier/r8_transfer_etf.py: its `pull` and `gates`, unchanged) with this scope's symbol list and its own output
folder. MANAGER runs `pull` through the Alpaca wrapper (the owner's keys; nothing here creates an account or a key).

  python tools/noise_fund_pull.py commands   print the exact loader commands `pull` will run (no network)
  python tools/noise_fund_pull.py pull       5Min + 30Min RTH split-adjusted masters 2016-01-04 .. 2026-06-30 through the
                                             shared loader, then raw AND split-adjusted daily bars into the research cache
                                             (C:\\EdgeLog\\alpaca_cache\\etf_daily\\<SYM>_1Day_{split,raw}.csv); provenance
                                             (loader sha256, repo HEAD, time) and every registered file's sha256 ->
                                             C:\\EdgeLog\\_anatomy_cache\\noise_funds_r1\\pull.json; stops if any NQ / ES master
                                             lookup changes
  python tools/noise_fund_pull.py gates      TRANSFER r2's data gates per symbol (missing 5m bars <= 1%, 5m-summed days vs
                                             Alpaca's daily bars within a cent / 0.10% on 10 random sessions, a bar on
                                             2016-06-30, volume present) -> gates.json in the same folder
"""
import os
import sys

OUT = os.environ.setdefault("EDGELOG_ROCFRONTIER_R8", r"C:\EdgeLog\_anatomy_cache\noise_funds_r1")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "rocfrontier"))
import r8_transfer_etf as R8                                           # noqa: E402

SYMBOLS = ("SPY", "QQQ", "TLT", "XLE", "XLF", "XLU", "XLV", "XLP", "XLI", "XLY", "XLB", "XLK", "SMH", "VIXY")
R8.FUNDS = {s: ("NOISE",) for s in SYMBOLS}                            # gates() runs its TTM-only checks only for TTM cells


def main(argv):
    if not argv or argv[0] not in ("commands", "pull", "gates"):
        print(__doc__)
        return
    os.makedirs(OUT, exist_ok=True)
    if argv[0] == "commands":
        for c in R8.pull_commands():
            print(" ".join(c))
        print("then daily bars (split + raw) for %d symbols -> %s" % (len(SYMBOLS), os.path.join(R8.CACHE, "etf_daily")))
        print("output folder: %s" % OUT)
    elif argv[0] == "pull":
        R8.pull()
    else:
        R8.gates()


if __name__ == "__main__":
    main(sys.argv[1:])
