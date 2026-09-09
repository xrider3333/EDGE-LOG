r"""Measure whether FREE market data is fresh enough to drive a 1-minute strategy loop.

WHY THIS EXISTS. The owner killed the browser-clicking QQQ paper build with "1-2 min
delay? that would never work". That objection was about clicking a web paper account,
but it left an unanswered question underneath it that the whole cloud plan rests on:
is FREE data (yfinance) actually fast enough to run the crowned strategies on QQQ
without a paid feed? Webull's OpenAPI answers 403 MARKET_DATA_NOT_SUBSCRIBED for both
stock and futures quotes, so until a subscription is bought, free data is the only
data. This tool measures the answer instead of assuming it.

WHAT IT SAMPLES, every 20 s during regular hours:
  - the newest yfinance QQQ 1-minute bar and its age
  - the yfinance last price and how long the call took
  - for comparison, the age of the NinjaTrader 10-second NQ feed already on this box

READ THE AGE CAREFULLY. A bar stamped 10:12 covers 10:12-10:13, so it CLOSES at 10:13.
yfinance hands back the bar that is still FORMING, which makes the measured age
NEGATIVE (it is ahead of that bar's close). The number that matters to a strategy is
the age of the newest CLOSED bar, which is one whole minute later -- `--summarise`
does that conversion so the raw column and the verdict can never drift apart. It also
means a live consumer must DROP the last row yfinance returns; it is incomplete.

VERDICT RULE, pre-registered before the first run: free data is usable for a
1-minute loop if the 90th-percentile CLOSED-bar age stays at or under 90 s. A 1m bar
closing at :00 must be readable well before the next one closes at +60 s, with margin
for a slow call.

FIRST RESULT (2026-09-09, regular hours): median 38 s, p90 58 s, call latency 0.41 s
median / 1.16 s max, 0 errors -> PASS. Yahoo's NQ=F futures quote is ~10 minutes
delayed and stays unusable for signals; this verdict covers QQQ shares only.

Run:  python tools/qqq_feed_latency_probe.py              # collect (25 min default)
      PROBE_MINUTES=5 python tools/qqq_feed_latency_probe.py
      python tools/qqq_feed_latency_probe.py --summarise  # verdict from the CSV
"""
import csv
import datetime as dt
import os
import statistics
import sys
import time
import zoneinfo

NY = zoneinfo.ZoneInfo("America/New_York")
OUT = os.environ.get("PROBE_OUT", r"C:\EdgeLog\qqq_exec\yf_latency_probe.csv")
NQ10S = r"C:\EdgeLog\ohlc\NQ_10s.csv"
COLS = ["ts_et", "yf_last_bar_et", "yf_bar_age_s", "yf_fast_last",
        "yf_call_s", "nq10s_age_s", "nq10s_close"]
VERDICT_P90_SEC = 90


def collect(minutes=None):
    """Append samples to OUT for `minutes`. Safe to re-run; never overwrites."""
    import yfinance as yf

    minutes = float(minutes if minutes is not None
                    else os.environ.get("PROBE_MINUTES", "25"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    new = not os.path.exists(OUT)
    rows = 0
    with open(OUT, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(COLS)
        end = time.time() + minutes * 60
        while time.time() < end:
            now = dt.datetime.now(NY)
            t0 = time.time()
            last_bar, age, px = "", "", ""
            try:
                df = yf.Ticker("QQQ").history(period="1d", interval="1m", prepost=False)
                if len(df):
                    lb = df.index[-1].tz_convert(NY)
                    last_bar = lb.strftime("%H:%M:%S")
                    # the stamp is the bar's OPEN, so it closes a minute later
                    age = round((now - (lb + dt.timedelta(minutes=1))).total_seconds())
                px = float(yf.Ticker("QQQ").fast_info.last_price)
            except Exception as exc:               # a network/API wobble IS the data
                last_bar = "ERR %s" % type(exc).__name__
            call_s = round(time.time() - t0, 2)

            nq_age, nq_close = "", ""
            try:
                with open(NQ10S, "rb") as f:       # tail-read: the file is 25+ MB
                    f.seek(0, os.SEEK_END)
                    f.seek(max(0, f.tell() - 400))
                    tail = f.read().decode("utf-8", "replace")
                parts = tail.strip().splitlines()[-1].split(",")
                nq_age = round(time.time() - float(parts[0]))
                nq_close = parts[4]
            except Exception:
                pass

            w.writerow([now.strftime("%H:%M:%S"), last_bar, age, px,
                        call_s, nq_age, nq_close])
            fh.flush()
            rows += 1
            time.sleep(20)
    print("probe done: %d samples -> %s" % (rows, OUT))


def summarise(path=OUT):
    """Print the verdict from a probe CSV. Lives beside collect() so the measurement
    and the rule that judges it can never drift apart. Returns True/False/None."""
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    ages = [int(r["yf_bar_age_s"]) for r in rows if r["yf_bar_age_s"] not in ("", "None")]
    calls = [float(r["yf_call_s"]) for r in rows if r["yf_call_s"]]
    errs = [r for r in rows if str(r["yf_last_bar_et"]).startswith("ERR")]
    if not ages:
        print("no usable samples in", path)
        return None
    ordered = sorted(ages)
    # +60: a negative age means the bar is still forming, so the newest CLOSED bar is a
    # whole minute older than the stamp measured here (see module docstring).
    closed_median = statistics.median(ages) + 60
    closed_p90 = ordered[int(0.9 * (len(ordered) - 1))] + 60
    print("samples=%d errors=%d" % (len(rows), len(errs)))
    print("newest CLOSED 1m bar age: median %.0fs  p90 %.0fs" % (closed_median, closed_p90))
    print("call latency: median %.2fs  max %.2fs" % (statistics.median(calls), max(calls)))
    nq = [int(r["nq10s_age_s"]) for r in rows if r["nq10s_age_s"] not in ("", "None")]
    if nq:
        print("NT 10s NQ feed age: median %.0fs (past ~180s the shadow adapter refuses "
              "to mark a lot at all)" % statistics.median(nq))
    ok = closed_p90 <= VERDICT_P90_SEC
    print("VERDICT: %s (rule: p90 <= %ds to drive a 1-minute loop)"
          % ("USABLE" if ok else "TOO SLOW", VERDICT_P90_SEC))
    return ok


if __name__ == "__main__":
    if "--summarise" in sys.argv:
        summarise()
    else:
        collect()
