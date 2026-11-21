"""PC-side report over a pulled logs/ownbar_shadow.jsonl + cloud_signal/signals.csv.

  python tools/ownbar_shadow_report.py ownbar_shadow.jsonl signals.csv [--json]

Per real decision bar (signals.csv row with dec_bar_start), re-evaluate the decision's
logged comparison dec_rule (e.g. "close>upper", "low<=stop") against dec_level on the OWN
bar (stream 1m folded, read at close+1 s). Status per decision:
  same          comparison still true on the own bar
  flip          comparison false on the own bar -> own-bar decision would have differed
  time_rule     rule is time-based (session_last_bar): bar values cannot change it
  not_checkable no/unknown dec_rule, no level, or the rule is not true even on the logged
                dec bar (inconsistent row) - never guessed
  no_own_bar    no shadow row / own bar incomplete for that bar
The level is held fixed: vwap/band levels that themselves include the decision bar are NOT
recomputed (blind spot). Bars where NO decision fired are invisible here.
"""
import csv
import datetime as dt
import json
import re
import statistics
import sys

FIELDS = ("open", "high", "low", "close", "volume")
RULE_RE = re.compile(r"^(open|high|low|close)\s*(<=|>=|<|>)\s*([a-z_]+)$")
TIME_RULES = {"session_last_bar"}
OPS = {"<": lambda a, b: a < b, ">": lambda a, b: a > b,
       "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b}
LEVEL_COLS = {"upper": "dec_band_upper", "lower": "dec_band_lower", "vwap": "dec_vwap"}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def to_epoch(s):
    return int(dt.datetime.fromisoformat(s).timestamp())


def parse_rule(rule):
    m = RULE_RE.match((rule or "").strip())
    return m.groups() if m else None


def level_for(row, rhs):
    lv = _num(row.get("dec_level"))
    if lv is None and rhs in LEVEL_COLS:
        lv = _num(row.get(LEVEL_COLS[rhs]))
    return lv


def check_decision(row, own_bar):
    """-> (status, detail). own_bar = [o,h,l,c,v] or None."""
    rule = (row.get("dec_rule") or "").strip()
    if rule in TIME_RULES:
        return "time_rule", {}
    parsed = parse_rule(rule)
    if not parsed:
        return "not_checkable", {"why": "no/unknown rule " + repr(rule)}
    field, op, rhs = parsed
    lv = level_for(row, rhs)
    if lv is None:
        return "not_checkable", {"why": "no level"}
    real = _num(row.get("dec_" + field))
    if real is None or not OPS[op](real, lv):
        return "not_checkable", {"why": "rule not true on logged dec bar"}
    if own_bar is None:
        return "no_own_bar", {}
    own = own_bar[FIELDS.index(field)]
    d = {"field": field, "level": lv, "real": real, "own": own,
         "own_margin": round(own - lv, 6)}
    return ("same" if OPS[op](own, lv) else "flip"), d


def load_shadow(path):
    out = {}
    with open(path) as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                r = json.loads(ln)
                if "bar_start" in r:
                    out[int(r["bar_start"])] = r
    return out


def own_bar_of(rec):
    return ((rec or {}).get("own_1_0") or {}).get("bar")


def bar_stats(shadow):
    comp = [r for r in shadow.values() if own_bar_of(r) and r.get("rest_final")]
    ident = sum(1 for r in comp if own_bar_of(r) == r["rest_final"])
    cdiffs = [abs(own_bar_of(r)[3] - r["rest_final"][3]) for r in comp]
    saved = [r["seconds_to_final"] - 1.0 for r in comp if r.get("seconds_to_final") is not None]
    return {"bars_compared": len(comp),
            "pct_identical": round(100.0 * ident / len(comp), 2) if comp else None,
            "worst_close_diff": round(max(cdiffs), 6) if cdiffs else None,
            "seconds_saved_median": round(statistics.median(saved), 2) if saved else None,
            "seconds_saved_mean": round(statistics.mean(saved), 2) if saved else None}


def run(shadow, signal_rows):
    res = []
    for row in signal_rows:
        if not row.get("dec_bar_start"):
            continue
        try:
            start = to_epoch(row["dec_bar_start"])
        except ValueError:
            continue
        rec = shadow.get(start)
        if rec is None:
            continue  # outside the shadow's days
        status, det = check_decision(row, own_bar_of(rec))
        res.append({"emitted_at": row.get("emitted_at"), "leg": row.get("leg"),
                    "event": row.get("event"), "rule": row.get("dec_rule"),
                    "status": status, **det})
    counts = {}
    for r in res:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = bar_stats(shadow)
    summary.update(decisions_in_window=len(res),
                   decisions_checked=counts.get("same", 0) + counts.get("flip", 0),
                   flips=counts.get("flip", 0), status_counts=counts)
    return summary, res


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    shadow = load_shadow(argv[0])
    with open(argv[1], newline="") as fh:
        rows = list(csv.DictReader(fh))
    summary, res = run(shadow, rows)
    if "--json" in argv:
        print(json.dumps({"summary": summary, "decisions": res}, indent=1))
        return 0
    for k, v in summary.items():
        print(f"{k:24s} {v}")
    for r in res:
        if r["status"] in ("flip", "not_checkable"):
            print(r)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
