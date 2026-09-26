"""WHAT THE CONTRACT-ROLL GUARD WOULD STOP, AND WHAT IT WOULD STOP BY MISTAKE.

`augur_engine/roll_guard.py` refuses to append a bar that spans a contract switch. A
guard like that is only worth having if two things are true, and both have to be checked
against the real masters rather than argued about:

  1. It CATCHES the splices we know are there - 2026-06-15 03:30 ET (NQ) and 05:30 (ES)
     on the 24-hour masters, and 2026-09-14 11:30 ET on every Yahoo-fed master.
  2. It does not stop the refresh often for nothing. Every hit is a paused append and a
     human look, so the false-alarm RATE is the running cost of the guard.

This tool runs the guard over a master's whole history and prints every bar it would
have refused, with the two ratios that say how close the call was: body against the
expected contract carry, and body against its own ten-sigma floor. The known splices are
marked. Everything else is a false alarm, and on sixteen years of NQ/ES data they are
all Federal Reserve 14:00 ET decisions or 08:30 ET inflation prints that happened to
land inside expiry week.

    python tools/roll_guard_scan.py                  # the six NQ/ES 1m and 5m masters
    python tools/roll_guard_scan.py --masters NOADJ_NQ_5m_ETH.csv
    python tools/roll_guard_scan.py --out docs/ROLL_GUARD_SCAN.md

Read-only: it never writes a master and never touches the registry.
"""
import argparse
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from augur_engine import roll_guard  # noqa: E402

UPLOADS = os.path.join(ROOT, "augur_uploads")

DEFAULT_MASTERS = ["NOADJ_NQ_1m_RTH.csv", "NOADJ_ES_1m_RTH.csv",
                   "NOADJ_NQ_5m_RTH.csv", "NOADJ_ES_5m_RTH.csv",
                   "NOADJ_NQ_5m_ETH.csv", "NOADJ_ES_5m_ETH.csv"]

# The in-bar splices ROLL_AUDIT.md section 2.7 establishes, by ET date. The June pair is
# only inside a bar on the 24-hour masters; on the RTH masters that switch falls cleanly
# between the 06-12 close and the 06-15 open, which is an ordinary non-adjusted gap.
KNOWN = {"eth": ["2026-06-15", "2026-09-14"], "rth": ["2026-09-14"]}


def known_for(filename):
    return KNOWN["eth"] if "_ETH" in filename.upper() else KNOWN["rth"]


def scan(filename, uploads=UPLOADS):
    path = os.path.join(uploads, filename)
    if not os.path.exists(path):
        return None, "file not found"
    d = pd.read_csv(path)
    for col in ("time", "open", "close"):
        if col not in d.columns:
            return None, "no %s column" % col
    hits = roll_guard.suspect_bars(d["time"].values, d["open"].values, d["close"].values,
                                   volumes=d.get("volume"))
    for h in hits:
        h["et"] = str(pd.to_datetime(h["time"], unit="s", utc=True)
                      .tz_convert("US/Eastern").strftime("%Y-%m-%d %H:%M"))
    return dict(filename=filename, bars=len(d), hits=hits), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--masters", default=",".join(DEFAULT_MASTERS))
    ap.add_argument("--uploads", default=UPLOADS, help="read masters from here instead")
    ap.add_argument("--out", default="", help="also write a markdown table here")
    a = ap.parse_args()

    lines = ["# What the contract-roll guard would refuse (tools/roll_guard_scan.py)", "",
             "Every bar `augur_engine/roll_guard.py` would refuse to append, over each",
             "master's whole history. Bars marked KNOWN are the in-bar contract splices",
             "ROLL_AUDIT.md section 2.7 establishes; every other row is a false alarm the",
             "guard would cost us - a paused append and one look by a human.", ""]
    missed_any = False
    for fn in [x.strip() for x in a.masters.split(",") if x.strip()]:
        res, err = scan(fn, a.uploads)
        if res is None:
            lines.append("**%s** - skipped (%s)" % (fn, err))
            print("%-22s SKIPPED (%s)" % (fn, err))
            continue
        want = known_for(fn)
        got = [h["et_date"] for h in res["hits"]]
        missed = [w for w in want if w not in got]
        missed_any = missed_any or bool(missed)
        head = ("**%s** - %s bars, %d would be refused, %d of them known splices%s"
                % (fn, format(res["bars"], ","), len(res["hits"]),
                   len([g for g in got if g in want]),
                   "" if not missed else "  **MISSED %s**" % ", ".join(missed)))
        lines += ["", head, "",
                  "| Bar (ET) | Body | Carry prior | Body / carry | Body / 10-sigma floor | |",
                  "|---|---|---|---|---|---|"]
        print("%-22s %10s bars  %2d refused  known splices caught: %s"
              % (fn, format(res["bars"], ","), len(res["hits"]), not missed))
        for h in res["hits"]:
            ratio_c = h["body"] / h["carry_prior"] if h["carry_prior"] else float("nan")
            ratio_s = h["body"] / h["sd_floor"] if h.get("sd_floor") else float("nan")
            tag = "KNOWN SPLICE" if h["et_date"] in want else ""
            lines.append("| %s | %.2f | %.0f | %.2f | %.2f | %s |"
                         % (h["et"], h["body"], h["carry_prior"], ratio_c, ratio_s, tag))
            print("      %s  body %9.2f  body/carry %.2f  body/floor %.2f  %s"
                  % (h["et"], h["body"], ratio_c, ratio_s, tag))
    lines += ["", "**Every known splice is caught.**" if not missed_any
              else "**A KNOWN SPLICE WAS MISSED - the guard is not safe to rely on.**"]
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("\nwrote", a.out)
    return 1 if missed_any else 0


if __name__ == "__main__":
    sys.exit(main())
