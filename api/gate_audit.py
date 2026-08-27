r"""Layer 4 — did the LIVE ML gate actually do its job today? A READER, and only that.

WHY THIS FILE EXISTS. On 2026-08-24 the gated NinjaScript was enabled on a chart, the
gate service was up, and the strategy simply never asked it anything. Nothing recorded
that. Three separate records existed and none of them could be joined to the others:

  C:\EdgeLog\gate_decisions.csv   what the NINJASCRIPT did — one row per entry-check
                                  opportunity, INCLUDING the branches where the gate is
                                  never consulted. That last part is the whole point.
  C:\EdgeLog\gate_live.log        what the SERVICE answered, in its own words.
  C:\EdgeLog\fills.csv            what the BROKER actually filled.

This module joins them and says whether the chain held. It answers the four questions the
2026-08-26 gate review could not answer after the fact:

  G1  was the gate even asked for this trade?          -> opportunities / asked / not_asked
  G2  was it scored on the RIGHT bar series?           -> bar_mismatch + a bar-minutes check
                                                          against each leg's own timeframe
  G3  did the size dial move anything?                 -> contracts_ordered_distinct
  --  did the ledger and the service agree?            -> agreement, per leg, per bar

IT NEVER DECIDES AND NEVER WRITES. No file is opened for anything but reading, no
Firestore document is touched, no state is carried between calls. It is wired into the
nightly report next to the reconcile and, like the reconcile, a failure here must cost
the report nothing: audit() never raises, and the caller wraps it anyway.

NEVER FABRICATE A NUMBER. Every figure that cannot be computed comes back None with its
reason recorded in the leg's `dashes` map, so the board can paint a dash that explains
itself on hover. A zero here would be a claim -- "the gate was asked nothing" reads very
differently from "we have no record of what the gate was asked" -- and this file exists
precisely because those two were once indistinguishable.

WHAT IT DOES NOT CHECK. G4 (the NinjaScript sizing its stop and its VWAP exit with the
literal Qty instead of Position.Quantity) leaves no fingerprint in these three files that
can be told apart from an ordinary partial fill, so it is not claimed here. It is a code
shape, checked by reading the .cs file.

DATING. A decision is filed under the ET date of the BAR it acted on, on both sides, so
the two sides join. Service lines that carry no bar stamp (a fail-open before scoring got
that far) are filed by the service's own wall clock converted to ET -- an approximation
that assumes the audit runs on the machine that wrote the log, which it does.
"""
import csv
import math
import os
import re
from collections import Counter
from datetime import datetime

DECISIONS_CSV = r"C:\EdgeLog\gate_decisions.csv"
GATE_LOG = r"C:\EdgeLog\gate_live.log"
FILLS_CSV = r"C:\EdgeLog\fills.csv"

# The ledger schema, in the contract's order. Checked rather than assumed: a NinjaScript
# that quietly reorders or renames a column would otherwise be read as a day of blanks.
LEDGER_COLUMNS = (
    "ts_utc", "strategy", "leg", "nt_bar_time", "state", "outcome", "http_status",
    "prob", "threshold", "take", "size", "bars", "bar_minutes", "q_intended",
    "q_ordered", "qty_base", "max_contracts", "latency_ms", "fallback", "reason",
)

OUTCOMES = ("ORDERED", "SKIPPED_BY_GATE", "FAIL_OPEN", "NOT_ASKED")

# Free text in the file, but a CLOSED vocabulary in the contract. Anything outside it is
# reported as schema drift rather than silently bucketed, because "not_asked: 14, reason
# unknown" is the exact shape of the failure this whole exercise is about.
REASONS = (
    "gate_disabled", "not_realtime", "not_warm", "vetoed_daytype", "vetoed_volskip",
    "in_position", "entry_cutoff", "no_signal_side", "http_error", "timeout",
    "parse_fail", "bar_mismatch",
    # 2026-08-26, from the review pass: a service fallback that is NOT a bar mismatch used to
    # write an empty reason, which is outside a closed vocabulary and vanished into an
    # unattributed fail_open count. "session_start" is the unconditional per-session
    # heartbeat -- its presence is what tells an empty day apart from a dead one. The
    # interlock_* pair records a request where the bar check did not actually run.
    "service_fallback", "session_start", "interlock_absent", "interlock_unparseable",
)

# The service logs prob to 3 decimals and size to 2, so agreement is judged at the
# precision the LOG can carry. Tighter than this would report rounding as a defect.
_PROB_TOL = 0.0011
_SIZE_TOL = 0.011

_MAX_EXAMPLES = 10          # keep the report doc well under the 1 MiB Firestore cap

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:                                    # pragma: no cover - zoneinfo missing
    _ET = None


# ── the service's own log ─────────────────────────────────────────────────────────
# 2026-08-26 20:14:02  decide NOISE_H_RF: prob=0.546 take=False size=0.00 (115ms, bar
#                      2026-08-26 15:55:00-04:00, 2573 bars @ 5m)
# 2026-08-26 20:11:21  decide ORB_H FAILED (fail-open): FileNotFoundError: ...
# The "N bars @ Nm" tail arrived with the bar-series fix; lines written before it end at
# the bar stamp, so that whole group is optional.
_DECIDE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+decide\s+(?P<leg>[A-Za-z0-9_]+)"
    r"(?P<tag>:|\s+FAIL-OPEN(?: \(BAR MISMATCH\))?:|\s+FAILED \(fail-open\):)\s*(?P<rest>.*)$")
_BODY_RE = re.compile(
    r"prob=(?P<prob>[-\d.]+)\s+take=(?P<take>\w+)\s+size=(?P<size>[-\d.]+)\s*"
    r"\((?P<ms>\d+)ms,\s*bar\s+(?P<bar>[^,)]+?)"
    r"(?:,\s*(?P<bars>\d+)\s+bars\s+@\s+(?P<step>\d+)m)?\)")


def _num(s, cast=float):
    """A blank cell is UNKNOWN, not zero — the one rule this whole file rests on."""
    s = ("" if s is None else str(s)).strip()
    if s == "" or s.lower() in ("nan", "none", "null", "-", "n/a"):
        return None
    try:
        return cast(float(s)) if cast is int else cast(s)
    except (TypeError, ValueError):
        return None


def _flag(s):
    """A CSV boolean. Unrecognised text is None so a typo never reads as False."""
    s = ("" if s is None else str(s)).strip().lower()
    if s in ("true", "1", "yes", "y", "t"):
        return True
    if s in ("false", "0", "no", "n", "f"):
        return False
    return None


def _mean(vals, nd=3):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), nd) if vals else None


def _pct(vals, q):
    """Nearest-rank percentile. A live day is a handful of decisions, and an interpolated
    percentile on five samples invents a precision the sample cannot carry."""
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = max(1, math.ceil(q * len(vals)))
    return vals[min(k, len(vals)) - 1]


def _to_et(dt):
    if _ET is None or dt is None:
        return dt
    if dt.tzinfo is None:
        dt = dt.astimezone()          # naive = this machine's clock
    return dt.astimezone(_ET)


def _bar_key(s):
    """An ISO-8601 bar stamp normalised to 'YYYY-MM-DD HH:MM:SS' in ET.

    This is the join key between the ledger and the service log, so both sides must land
    on the same string for the same bar no matter which offset each of them wrote. A
    stamp with no offset is taken as ET (the chart's own clock) rather than guessed at.
    """
    s = ("" if s is None else str(s)).strip()
    if not s:
        return None
    txt = s.replace("T", " ")
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    if dt.tzinfo is None and _ET is not None:
        dt = dt.replace(tzinfo=_ET)
    dt = _to_et(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _bar_date(key):
    return key.split(" ")[0] if key else None


# ── inputs ────────────────────────────────────────────────────────────────────────
def read_ledger(path, date_et):
    """The NinjaScript's decision ledger for one ET date. Returns (rows, meta).

    meta.found is False when the file does not exist — which is not an error, it is the
    state the whole system was in until the ledger shipped, and the audit has to say so
    in words rather than return a page of zeros.
    """
    meta = {"path": path, "found": False, "rows_total": 0, "rows_today": 0,
            "note": None, "header_ok": None, "missing_columns": [], "extra_columns": []}
    if not os.path.exists(path):
        meta["note"] = ("gate_decisions.csv does not exist: the NinjaScript has never "
                        "written a decision row, so no gate answer can be tied to a fill")
        return [], meta
    meta["found"] = True
    rows = []
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.DictReader(f)
            head = [(h or "").strip() for h in (rdr.fieldnames or [])]
            meta["missing_columns"] = [c for c in LEDGER_COLUMNS if c not in head]
            meta["extra_columns"] = [c for c in head if c not in LEDGER_COLUMNS]
            meta["header_ok"] = (head == list(LEDGER_COLUMNS))
            for raw in rdr:
                meta["rows_total"] += 1
                row = {(k or "").strip(): (v or "").strip()
                       for k, v in raw.items() if k is not None}
                bar = _bar_key(row.get("nt_bar_time"))
                # Bar date first so both sides of the join agree on which day a
                # 22:00 ET overnight decision belongs to; ts_utc is the fallback.
                day = _bar_date(bar) or _bar_date(_bar_key(row.get("ts_utc")))
                if day != date_et:
                    continue
                row["_bar"] = bar
                rows.append(row)
        meta["rows_today"] = len(rows)
    except Exception as e:
        meta["note"] = f"unreadable: {type(e).__name__}: {e}"
        return [], meta
    if meta["header_ok"] is False:
        meta["note"] = ("header does not match the contract"
                        + (f"; missing {meta['missing_columns']}" if meta["missing_columns"] else "")
                        + (f"; extra {meta['extra_columns']}" if meta["extra_columns"] else ""))
    return rows, meta


def read_service_log(path, date_et):
    """The service's own decide lines for one ET date. Returns (entries, meta)."""
    meta = {"path": path, "found": False, "entries": 0, "undated_by_bar": 0, "note": None}
    if not os.path.exists(path):
        meta["note"] = "gate_live.log does not exist: the gate service has never run here"
        return [], meta
    meta["found"] = True
    out = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = _DECIDE_RE.match(line.rstrip("\n"))
                if not m:
                    continue
                tag, rest = m.group("tag"), m.group("rest")
                try:
                    clock = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                e = {"leg": m.group("leg"), "clock": clock, "bar": None,
                     "prob": None, "take": None, "size": None, "ms": None,
                     "bars": None, "bar_minutes": None,
                     "fail_open": tag != ":", "error": None}
                if tag == ":":
                    b = _BODY_RE.search(rest)
                    if b:
                        e["prob"] = _num(b.group("prob"))
                        e["take"] = _flag(b.group("take"))
                        e["size"] = _num(b.group("size"))
                        e["ms"] = _num(b.group("ms"), int)
                        e["bar"] = _bar_key(b.group("bar"))
                        e["bars"] = _num(b.group("bars"), int)
                        e["bar_minutes"] = _num(b.group("step"), int)
                    else:
                        # A decide line we cannot read is worth counting, never guessing.
                        e["error"] = "unparsed decide line"
                else:
                    e["error"] = rest.strip() or "fail-open, no reason logged"
                day = (_bar_date(e["bar"]) if e["bar"]
                       else _to_et(clock).strftime("%Y-%m-%d"))
                if day != date_et:
                    continue
                if not e["bar"]:
                    meta["undated_by_bar"] += 1
                out.append(e)
        meta["entries"] = len(out)
    except Exception as ex:
        meta["note"] = f"unreadable: {type(ex).__name__}: {ex}"
        return [], meta
    return out, meta


def read_fills(path, date_et, account=None):
    """The broker's own entries for one ET date, per leg. Returns (by_leg, meta).

    Attribution is INFERRED from the fill's SignalName through the same map the Layer 3
    reconcile uses, and a signal that could belong to two gated legs is left unattributed
    rather than assigned. A wrong attribution here would look exactly like a result.
    """
    meta = {"path": path, "found": os.path.exists(path), "n_trades": 0,
            "unattributed": 0, "note": None,
            "attribution": "inferred from SignalName (paper_reconcile.SIGNAL_PREFIX)"}
    by_leg = {}
    if not meta["found"]:
        meta["note"] = "fills.csv does not exist"
        return by_leg, meta
    try:
        from . import nt_sync
        from . import paper_reconcile
        if account is None:
            from .paper import PAPER_LIVE_ACCOUNT
            account = PAPER_LIVE_ACCOUNT
        fills = [f for f in nt_sync.parse_fills(path) if f.get("account") == account]
        trades = [t for t in nt_sync.build_trades(fills) if t.get("date") == date_et]
    except Exception as e:
        meta["note"] = f"could not read fills: {type(e).__name__}: {e}"
        return by_leg, meta
    meta["n_trades"] = len(trades)
    meta["account"] = account
    gated = set(gated_legs())
    for t in trades:
        key = paper_reconcile.leg_from_signal(t.get("signal"))
        leg = None
        if key in gated:
            leg = key
        elif key:
            # The reconcile's map names shadow legs ("ENGUQ_ER", "ORB"); the gate serves
            # their gated variants ("ENGUQ_ER_H", "ORB_H"). Accept the extension only when
            # exactly one gated leg could be meant.
            cands = [g for g in gated if g.startswith(key + "_")]
            leg = cands[0] if len(cands) == 1 else None
        if leg is None:
            meta["unattributed"] += 1
            continue
        by_leg.setdefault(leg, []).append(
            {"entry_et": t.get("entryTime"), "contracts": t.get("size"),
             "side": t.get("type"), "signal": t.get("signal")})
    return by_leg, meta


def gated_legs():
    """{leg key: expected bar minutes} for the legs the service serves.

    Empty when api.paper cannot be imported (the CLI on a machine without the engine),
    which costs the audit its "this leg was gated and recorded nothing" line and nothing
    else — every other figure is derived from the three files.
    """
    try:
        from .paper import PAPER_LEGS
    except Exception:
        try:
            from api.paper import PAPER_LEGS       # running as a script, not a package
        except Exception:
            return {}
    out = {}
    for leg in PAPER_LEGS:
        if not leg.get("gate"):
            continue
        m = re.match(r"(\d+)", str(leg.get("timeframe") or ""))
        out[str(leg.get("key"))] = int(m.group(1)) if m else None
    return out


# ── the join ──────────────────────────────────────────────────────────────────────
def _agreement(rows, entries):
    """Ledger row vs the service's own log line, for the same leg on the same bar.

    They are two independent recordings of one event. A disagreement means something
    BETWEEN them changed the answer, which is the strongest signal this audit can produce
    — stronger than any count, because it needs no assumption about what should have
    happened.
    """
    svc = {}
    for e in entries:
        if e["bar"] and e["prob"] is not None:
            svc.setdefault(e["bar"], []).append(e)
    for lst in svc.values():
        lst.sort(key=lambda e: e["clock"])

    out = {"compared": 0, "agree": 0, "disagree": 0,
           "ledger_without_service_line": 0, "service_without_ledger_row": 0,
           "mismatches": []}
    used = Counter()
    for r in rows:
        if r.get("outcome") not in ("ORDERED", "SKIPPED_BY_GATE"):
            continue                      # only rows where the gate actually answered
        bar = r.get("_bar")
        cands = svc.get(bar) or []
        i = used[bar]
        if not bar or i >= len(cands):
            out["ledger_without_service_line"] += 1
            continue
        used[bar] += 1
        e = cands[i]
        out["compared"] += 1
        lp, ls, lt = _num(r.get("prob")), _num(r.get("size")), _flag(r.get("take"))
        bad = []
        if lp is None:
            bad.append("ledger carried no prob")
        elif abs(lp - e["prob"]) > _PROB_TOL:
            bad.append(f"prob {lp:.4f} vs service {e['prob']:.3f}")
        if ls is not None and e["size"] is not None and abs(ls - e["size"]) > _SIZE_TOL:
            bad.append(f"size {ls:.3f} vs service {e['size']:.2f}")
        if lt is not None and e["take"] is not None and lt != e["take"]:
            bad.append(f"take {lt} vs service {e['take']}")
        if bad:
            out["disagree"] += 1
            if len(out["mismatches"]) < _MAX_EXAMPLES:
                out["mismatches"].append({"bar": bar, "why": "; ".join(bad)})
        else:
            out["agree"] += 1
    out["service_without_ledger_row"] = sum(
        max(0, len(v) - used[k]) for k, v in svc.items())
    return out


def _leg_block(leg, rows, entries, fills, shadow, expect_minutes,
               have_ledger, have_log, have_fills):
    """One leg's row on the board. `dashes` explains every None it hands back."""
    d = {}                                            # field -> why it is a dash
    blk = {"leg": leg}

    def put(name, value, why):
        blk[name] = value
        if value is None:
            d[name] = why

    no_ledger = "no ledger for this day — gate_decisions.csv is missing or empty"
    by_outcome = Counter(r.get("outcome") or "(blank)" for r in rows)
    ordered = [r for r in rows if r.get("outcome") == "ORDERED"]
    asked = [r for r in rows if r.get("outcome") in ("ORDERED", "SKIPPED_BY_GATE", "FAIL_OPEN")]

    put("opportunities", len(rows) if have_ledger else None, no_ledger)
    put("asked", len(asked) if have_ledger else None, no_ledger)
    put("ordered", len(ordered) if have_ledger else None, no_ledger)
    put("skipped_by_gate", by_outcome.get("SKIPPED_BY_GATE") if have_ledger else None,
        no_ledger)
    put("fail_open", by_outcome.get("FAIL_OPEN") if have_ledger else None, no_ledger)
    put("not_asked", by_outcome.get("NOT_ASKED") if have_ledger else None, no_ledger)
    if have_ledger:
        for k in ("skipped_by_gate", "fail_open", "not_asked"):
            blk[k] = blk[k] or 0
            d.pop(k, None)

    reasons = Counter((r.get("reason") or "(blank)")
                      for r in rows if r.get("outcome") == "NOT_ASKED")
    blk["not_asked_by_reason"] = dict(reasons) if have_ledger else None
    if not have_ledger:
        d["not_asked_by_reason"] = no_ledger
    blk["unknown_reasons"] = sorted(
        k for k in reasons if k not in REASONS and k != "(blank)")
    blk["unknown_outcomes"] = sorted(
        k for k in by_outcome if k not in OUTCOMES and k != "(blank)")

    put("bar_mismatch",
        sum(1 for r in rows if (r.get("reason") or "") == "bar_mismatch")
        if have_ledger else None, no_ledger)
    put("parse_fail",
        sum(1 for r in rows if (r.get("reason") or "") == "parse_fail")
        if have_ledger else None, no_ledger)
    # A blank status is UNKNOWN and not counted; a zero is a connection that never
    # answered and very much is. Folding the two together would hide the second.
    put("http_errors",
        sum(1 for r in rows
            if _num(r.get("http_status"), int) not in (None, 200)) if have_ledger else None,
        no_ledger)
    put("served_fallback",
        sum(1 for r in rows if _flag(r.get("fallback")) is True) if have_ledger else None,
        no_ledger)

    # THE SIZE DIAL, both ends of it. `size_intended_mean` is the multiplier the model
    # asked for; `size_ordered_mean` is the multiplier the order actually expressed
    # (q_ordered / qty_base). The two drifting apart IS defect G3.
    put("size_intended_mean", _mean([_num(r.get("size")) for r in ordered]),
        "no ORDERED row carried a size" if have_ledger else no_ledger)
    achieved = []
    for r in ordered:
        q, base = _num(r.get("q_ordered")), _num(r.get("qty_base"))
        if q is not None and base:
            achieved.append(q / base)
    put("size_ordered_mean", _mean(achieved),
        "no ORDERED row carried both q_ordered and qty_base" if have_ledger else no_ledger)

    q_ord = sorted({int(v) for v in (_num(r.get("q_ordered"), int) for r in ordered)
                    if v is not None})
    put("contracts_ordered_distinct", q_ord or None,
        "no ORDERED row carried q_ordered" if have_ledger else no_ledger)
    blk["contracts_ordered_n"] = len(q_ord) or None
    if not q_ord:
        d["contracts_ordered_n"] = d.get("contracts_ordered_distinct")
    q_int = sorted({int(v) for v in (_num(r.get("q_intended"), int) for r in ordered)
                    if v is not None})
    put("contracts_intended_distinct", q_int or None,
        "no ORDERED row carried q_intended" if have_ledger else no_ledger)
    put("clamped",
        sum(1 for r in ordered
            if None not in (_num(r.get("q_intended"), int), _num(r.get("q_ordered"), int))
            and _num(r.get("q_intended"), int) != _num(r.get("q_ordered"), int))
        if have_ledger else None, no_ledger)
    over = [r for r in ordered
            if _num(r.get("max_contracts"), int) is not None
            and (_num(r.get("q_ordered"), int) or 0) > _num(r.get("max_contracts"), int)]
    put("over_max_contracts", len(over) if have_ledger else None, no_ledger)

    lat = [_num(r.get("latency_ms"), int) for r in rows]
    put("latency_p50", _pct(lat, 0.50),
        "no ledger row carried latency_ms" if have_ledger else no_ledger)
    put("latency_p99", _pct(lat, 0.99),
        "no ledger row carried latency_ms" if have_ledger else no_ledger)

    states = Counter((r.get("state") or "(blank)") for r in rows)
    blk["states"] = dict(states) if have_ledger else None
    blk["ordered_not_realtime"] = (
        sum(1 for r in ordered
            if (r.get("state") or "").strip().lower() not in ("realtime", "", "(blank)"))
        if have_ledger else None)

    # ── the service's side of the same day ────────────────────────────────────────
    no_log = "gate_live.log is missing or unreadable"
    scored = [e for e in entries if e["prob"] is not None]
    svc = {
        "decide_lines": len(entries) if have_log else None,
        "scored": len(scored) if have_log else None,
        "fail_open": sum(1 for e in entries if e["fail_open"]) if have_log else None,
        "take_true": sum(1 for e in scored if e["take"]) if have_log else None,
        "prob_mean": _mean([e["prob"] for e in scored], 4),
        "size_mean": _mean([e["size"] for e in scored]),
        "latency_p50": _pct([e["ms"] for e in scored], 0.50),
        "latency_p99": _pct([e["ms"] for e in scored], 0.99),
        "bar_minutes_seen": sorted({e["bar_minutes"] for e in scored
                                    if e["bar_minutes"] is not None}) or None,
        "expected_bar_minutes": expect_minutes,
        "last_bar": (max(e["bar"] for e in scored if e["bar"])
                     if any(e["bar"] for e in scored) else None),
        "errors": sorted({e["error"] for e in entries if e["error"]})[:_MAX_EXAMPLES],
    }
    if not have_log:
        d["service"] = no_log
    # G2's fingerprint: a 5-minute leg scored on 1-minute bars. The bar cache is fixed,
    # but the check stays — it is the cheapest possible tripwire on a repeat.
    wrong = ([m for m in (svc["bar_minutes_seen"] or []) if m != expect_minutes]
             if expect_minutes else [])
    svc["wrong_series_minutes"] = wrong or None
    blk["service"] = svc

    blk["agreement"] = _agreement(rows, entries) if (have_ledger and have_log) else None
    if blk["agreement"] is None:
        d["agreement"] = (no_ledger if not have_ledger else no_log)

    # ── broker + shadow, both for cross-checking, neither authoritative ───────────
    if have_fills:
        blk["fills"] = {
            "entries": len(fills),
            "contracts_distinct": sorted({f["contracts"] for f in fills
                                          if f.get("contracts") is not None}) or None,
        }
    else:
        blk["fills"] = None
        d["fills"] = "fills.csv is missing or could not be read"
    blk["shadow"] = shadow
    if shadow is None:
        d["shadow"] = ("no paper report handed in — run inside the nightly report to "
                       "compare the live gate with the shadow engine")

    blk["dashes"] = d
    blk["complaints"] = _leg_complaints(blk, leg, have_ledger, have_log)
    return blk


def _leg_complaints(blk, leg, have_ledger, have_log):
    """Concrete, in the owner's terms. One line per thing that is actually wrong."""
    out = []
    svc, sh = blk["service"], blk["shadow"]

    if have_ledger and blk.get("opportunities") == 0 and have_log and svc["scored"]:
        out.append(f"{leg}: the service scored {svc['scored']} decision(s) today but the "
                   f"NinjaScript logged no entry-check opportunity — the ledger and the "
                   f"service are not looking at the same strategy")
    if sh and (sh.get("n_signals") or 0) > 0 and have_ledger and blk.get("opportunities") == 0:
        out.append(f"{leg}: the shadow engine found {sh['n_signals']} entry/entries today "
                   f"and the NinjaScript recorded no opportunity at all — the strategy was "
                   f"not on a chart, or it never reached its entry check")
    if blk.get("not_asked"):
        top = sorted((blk.get("not_asked_by_reason") or {}).items(),
                     key=lambda kv: -kv[1])
        why = ", ".join(f"{k} x{v}" for k, v in top[:4])
        if any(k in ("gate_disabled", "http_error", "timeout", "parse_fail")
               for k, _ in top):
            out.append(f"{leg}: {blk['not_asked']} opportunity/ies never reached the gate "
                       f"({why})")
    if blk.get("bar_mismatch"):
        out.append(f"{leg}: {blk['bar_mismatch']} decision(s) hit the bar interlock — the "
                   f"NinjaScript and the service were on different bars")
    if blk.get("parse_fail"):
        out.append(f"{leg}: {blk['parse_fail']} reply could not be parsed; those fell open "
                   f"by design, but a parser that cannot read its own service is a bug")
    if blk.get("http_errors"):
        out.append(f"{leg}: {blk['http_errors']} call(s) came back non-200")
    if blk.get("over_max_contracts"):
        out.append(f"{leg}: {blk['over_max_contracts']} order(s) exceeded the "
                   f"max_contracts the service served — the clamp is not being applied")
    if blk.get("ordered_not_realtime"):
        out.append(f"{leg}: {blk['ordered_not_realtime']} order(s) were placed while the "
                   f"strategy was not in Realtime state")

    # G3, stated as the number that shows it.
    dist, n_ord = blk.get("contracts_ordered_distinct"), blk.get("ordered") or 0
    if dist and len(dist) == 1 and n_ord >= 3:
        line = (f"{leg}: all {n_ord} accepted trades ordered exactly {dist[0]} "
                f"contract(s)")
        si = blk.get("size_intended_mean")
        if si is not None:
            line += f" while the model asked for a mean size of {si}"
        out.append(line + " — the size dial is dead (G3)")

    ag = blk.get("agreement") or {}
    if ag.get("disagree"):
        ex = "; ".join(f"{m['bar']} {m['why']}" for m in ag["mismatches"][:3])
        out.append(f"{leg}: {ag['disagree']} decision(s) where the ledger and the service "
                   f"disagree about their own answer ({ex})")
    if ag.get("ledger_without_service_line"):
        out.append(f"{leg}: {ag['ledger_without_service_line']} ledger row(s) claim the "
                   f"gate answered, but gate_live.log has no matching line for that bar")
    if svc.get("wrong_series_minutes"):
        out.append(f"{leg}: scored on {svc['wrong_series_minutes']}-minute bars when the "
                   f"leg trades {svc['expected_bar_minutes']}m — wrong bar series (G2)")
    if have_log and svc.get("fail_open"):
        # Two errors, each whole enough to search the log for. A sentence cut mid-word
        # sends the reader back to the log anyway, so it may as well end cleanly.
        errs = "; ".join(e[:120] for e in (svc.get("errors") or [])[:2])
        out.append(f"{leg}: the service fell open {svc['fail_open']} time(s) today"
                   + (f" ({errs})" if errs else ""))

    f = blk.get("fills")
    if f and blk.get("ordered") is not None and f["entries"] != blk["ordered"]:
        out.append(f"{leg}: the ledger recorded {blk['ordered']} order(s) and the broker "
                   f"filled {f['entries']} entry/entries (attribution is inferred)")
    return out


def _shadow_for(leg, report):
    """What the shadow engine's own gate did for this leg today — free, it is already in
    the report dict the caller is assembling. None when no report was handed in."""
    if not report:
        return None
    blk = (report.get("legs") or {}).get(leg)
    if not isinstance(blk, dict):
        return None
    g = blk.get("gate") or {}
    return {"n_signals": blk.get("n_signals"),
            "gate_n_in": g.get("n_in"), "gate_n_kept": g.get("n_kept"),
            "gate_n_skipped": g.get("n_skipped"), "gate_avg_size": g.get("avg_size"),
            "gate_ok": g.get("ok")}


# ── the audit ─────────────────────────────────────────────────────────────────────
def audit(date_et, *, decisions_path=None, log_path=None, fills_path=None,
          report=None, account=None):
    """Join the NinjaScript's ledger, the service's log and the broker's fills for one
    ET date and say whether the live gate did its job. Never raises, never writes.

    date_et : "YYYY-MM-DD", the session date in New York — the date both sides file a
              decision under, so an overnight ENGU-Q bar lands on the day it traded.
    report  : the paper report being assembled, read ONLY for the shadow comparison.
    """
    try:
        return _audit(date_et, decisions_path, log_path, fills_path, report, account)
    except Exception as e:                              # pragma: no cover - belt and braces
        return {"ok": None, "date": date_et,
                "error": f"{type(e).__name__}: {e}",
                "verdict": "the gate audit itself failed; the rest of the report stands"}


def _audit(date_et, decisions_path, log_path, fills_path, report, account):
    dpath = decisions_path or DECISIONS_CSV
    lpath = log_path or GATE_LOG
    fpath = fills_path or FILLS_CSV

    rows, dmeta = read_ledger(dpath, date_et)
    entries, lmeta = read_service_log(lpath, date_et)
    fills, fmeta = read_fills(fpath, date_et, account)
    expect = gated_legs()

    have_ledger = dmeta["found"] and dmeta.get("note") is None
    have_log = lmeta["found"] and lmeta.get("note") is None
    have_fills = fmeta["found"] and fmeta.get("note") is None

    rows_by = {}
    for r in rows:
        rows_by.setdefault(r.get("leg") or "(blank)", []).append(r)
    ents_by = {}
    for e in entries:
        ents_by.setdefault(e["leg"], []).append(e)

    # Every leg any source mentions, plus every leg that is CONFIGURED to be gated — the
    # second half is what turns "we saw nothing" into "this leg should have been asked".
    legs = sorted(set(rows_by) | set(ents_by) | set(fills) | set(expect))

    out = {
        "date": date_et,
        "dated_by": ("the ET date of the bar each decision acted on; service lines with "
                     "no bar stamp fall back to the service's own clock"),
        "sources": {"decisions_csv": dmeta, "gate_live_log": lmeta, "fills_csv": fmeta,
                    "shadow": {"available": bool(report),
                               "note": None if report else
                               "no paper report handed in"}},
        "legs": {}, "complaints": [], "dashes": {},
    }

    for leg in legs:
        out["legs"][leg] = _leg_block(
            leg, rows_by.get(leg, []), ents_by.get(leg, []), fills.get(leg, []),
            _shadow_for(leg, report), expect.get(leg),
            have_ledger, have_log, have_fills)

    complaints = []
    if not dmeta["found"]:
        complaints.append(
            "no decision ledger: C:\\EdgeLog\\gate_decisions.csv does not exist, so not "
            "one gate answer today can be tied to a fill (G1). The NinjaScript that "
            "writes it is not deployed.")
    elif dmeta.get("note"):
        complaints.append(f"decision ledger unusable: {dmeta['note']}")
    elif dmeta["rows_today"] == 0:
        complaints.append(
            f"the decision ledger exists but recorded nothing on {date_et} — either no "
            f"strategy reached an entry check, or none of them is writing rows")
    if dmeta.get("header_ok") is False:
        complaints.append(f"decision ledger header drift: {dmeta.get('note')}")
    if not lmeta["found"] or lmeta.get("note"):
        complaints.append(f"service log unusable: {lmeta.get('note')}")
    if fmeta.get("note"):
        complaints.append(f"fills unusable: {fmeta['note']}")
    if fmeta.get("unattributed"):
        complaints.append(f"{fmeta['unattributed']} broker trade(s) could not be "
                          f"attributed to a gated leg by SignalName")
    for leg in legs:
        complaints.extend(out["legs"][leg]["complaints"])
        u = out["legs"][leg]["unknown_reasons"] + out["legs"][leg]["unknown_outcomes"]
        if u:
            complaints.append(f"{leg}: ledger vocabulary the contract does not define: "
                              f"{', '.join(u)}")

    tot = {k: 0 for k in ("opportunities", "asked", "ordered", "skipped_by_gate",
                          "fail_open", "not_asked", "bar_mismatch", "parse_fail")}
    for leg in legs:
        for k in tot:
            v = out["legs"][leg].get(k)
            if isinstance(v, int):
                tot[k] += v
    out["totals"] = tot if have_ledger else None
    if not have_ledger:
        out["dashes"]["totals"] = "no readable ledger for this day"

    # The three defects these files can actually speak to. None = no evidence either way,
    # which is itself the finding when the ledger is missing.
    dist_dead = [lg for lg in legs
                 if len(out["legs"][lg].get("contracts_ordered_distinct") or []) == 1
                 and (out["legs"][lg].get("ordered") or 0) >= 3]
    wrong_series = [lg for lg in legs
                    if (out["legs"][lg]["service"].get("wrong_series_minutes"))]
    out["defects"] = {
        "G1_unjoinable": {
            "seen": (True if not have_ledger else
                     bool(any(out["legs"][lg].get("ordered")
                              and out["legs"][lg].get("contracts_ordered_distinct") is None
                              for lg in legs))),
            "note": ("no ledger, so a decision cannot be joined to a fill" if not have_ledger
                     else "the ledger exists and carries the order size"),
        },
        "G2_wrong_bar_series": {
            "seen": (bool(wrong_series) if have_log else None),
            "note": (f"legs scored off their own series: {', '.join(wrong_series)}"
                     if wrong_series else
                     ("every scored decision used the leg's own bar size" if have_log
                      else "gate_live.log unreadable")),
        },
        "G3_size_dial_dead": {
            "seen": (bool(dist_dead) if have_ledger else None),
            "note": (f"one distinct order size across the day: {', '.join(dist_dead)}"
                     if dist_dead else
                     ("order sizes varied, or too few orders to tell" if have_ledger
                      else "no ledger to measure order sizes from")),
        },
    }

    out["complaints"] = complaints
    out["ok"] = (None if not have_ledger else not complaints)
    out["verdict"] = _verdict(out, have_ledger, have_log, date_et)
    return out


def _verdict(out, have_ledger, have_log, date_et):
    if not have_ledger:
        n = sum(1 for lg, b in out["legs"].items()
                if (b["service"].get("scored") or 0) > 0)
        tail = (f"; the service logged decisions for {n} leg(s), but with nothing on the "
                f"NinjaScript's side they cannot be tied to a trade" if n else
                "; the service logged no decisions either")
        return ("NO LEDGER — the gate cannot be audited for " + date_et +
                " (gate_decisions.csv does not exist)" + tail)
    t = out["totals"] or {}
    if not t.get("opportunities"):
        return (f"NOTHING RECORDED — the ledger holds no entry-check opportunity on "
                f"{date_et}")
    line = (f"{t['opportunities']} opportunity/ies: {t['asked']} asked, "
            f"{t['ordered']} ordered, {t['skipped_by_gate']} skipped by the gate, "
            f"{t['not_asked']} never asked, {t['fail_open']} fail-open")
    if not have_log:
        line += " (service log unreadable, so nothing could be cross-checked)"
    n = len(out["complaints"])
    return line + (" — CLEAN" if not n else f" — {n} complaint(s)")


# ── self-test / CLI ───────────────────────────────────────────────────────────────
def _fmt(v):
    if v is None:
        return "—"
    if isinstance(v, list):
        return ", ".join(str(x) for x in v) or "—"
    if isinstance(v, dict):
        return ", ".join(f"{k}={v[k]}" for k in sorted(v)) or "—"
    return str(v)


def _print(a):
    print(f"DATE     {a.get('date')}")
    print(f"OK       {a.get('ok')}")
    print(f"VERDICT  {a.get('verdict')}")
    if a.get("error"):
        print(f"ERROR    {a['error']}")
        return
    print("SOURCES")
    for k, s in (a.get("sources") or {}).items():
        bits = [f"found={s.get('found', s.get('available'))}"]
        for extra in ("rows_today", "entries", "n_trades", "unattributed"):
            if s.get(extra) is not None:
                bits.append(f"{extra}={s[extra]}")
        if s.get("note"):
            bits.append(f"note={s['note']}")
        print(f"  {k:16s} {'  '.join(bits)}")
    print("DEFECTS")
    for k, v in (a.get("defects") or {}).items():
        print(f"  {k:22s} seen={_fmt(v['seen']):5s} {v['note']}")
    print(f"TOTALS   {_fmt(a.get('totals'))}")
    print("LEGS")
    for leg, b in (a.get("legs") or {}).items():
        print(f"  {leg}")
        print(f"    opp={_fmt(b['opportunities'])} asked={_fmt(b['asked'])} "
              f"ordered={_fmt(b['ordered'])} skipped={_fmt(b['skipped_by_gate'])} "
              f"not_asked={_fmt(b['not_asked'])} fail_open={_fmt(b['fail_open'])}")
        print(f"    reasons={_fmt(b['not_asked_by_reason'])} "
              f"bar_mismatch={_fmt(b['bar_mismatch'])} parse_fail={_fmt(b['parse_fail'])}")
        print(f"    size_intended={_fmt(b['size_intended_mean'])} "
              f"size_ordered={_fmt(b['size_ordered_mean'])} "
              f"contracts_distinct=[{_fmt(b['contracts_ordered_distinct'])}]")
        print(f"    latency p50={_fmt(b['latency_p50'])} p99={_fmt(b['latency_p99'])}")
        s = b["service"]
        print(f"    service: scored={_fmt(s['scored'])} take={_fmt(s['take_true'])} "
              f"prob_mean={_fmt(s['prob_mean'])} size_mean={_fmt(s['size_mean'])} "
              f"p50={_fmt(s['latency_p50'])}ms bars@{_fmt(s['bar_minutes_seen'])}m "
              f"(expect {_fmt(s['expected_bar_minutes'])}m)")
        print(f"    agreement: {_fmt(b['agreement'])}")
        # Dashes are grouped by their REASON, not listed one per field. Twenty repeats of
        # the same sentence is how a legible report turns into wallpaper.
        groups = {}
        for k, why in sorted(b["dashes"].items()):
            groups.setdefault(why, []).append(k)
        for why, ks in groups.items():
            what = f"{len(ks)} fields" if len(ks) > 3 else ", ".join(ks)
            print(f"    - {what}: {why}")
    print("COMPLAINTS")
    for c in a.get("complaints") or ["(none)"]:
        print(f"  * {c}")


def _selftest():
    """Prove the join works before trusting it on a day that matters.

    Writes a synthetic ledger and log into a TEMP directory — never C:\\EdgeLog, which
    this module only ever reads — and checks that the audit finds the three things it
    exists to find: a dead size dial, a ledger/service disagreement, and an opportunity
    that never reached the gate.
    """
    import tempfile
    day = "2026-08-24"
    tmp = tempfile.mkdtemp(prefix="gate_audit_selftest_")
    dec = os.path.join(tmp, "gate_decisions.csv")
    log = os.path.join(tmp, "gate_live.log")

    def row(bar, outcome, prob, size, qi, qo, reason="", lat=60, mx=40):
        return ",".join([
            f"{day}T{bar}:30Z", "EdgeLogNOISE", "NOISE_H_RF",
            f"{day}T{bar}:00-04:00", "Realtime", outcome,
            "200" if outcome != "NOT_ASKED" else "",
            prob, "0.5", "true" if outcome == "ORDERED" else "false", size,
            "2573", "5", qi, qo, "3", str(mx),
            str(lat) if outcome != "NOT_ASKED" else "", "false", reason])

    with open(dec, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(LEDGER_COLUMNS) + "\n")
        # three accepted trades, three different model sizes, one identical order size
        f.write(row("10:00", "ORDERED", "0.612", "3.52", "11", "9") + "\n")
        f.write(row("10:05", "ORDERED", "0.640", "3.68", "11", "9") + "\n")
        f.write(row("10:10", "ORDERED", "0.655", "3.75", "11", "9") + "\n")
        # one the gate refused, and one it was never asked about
        f.write(row("10:15", "SKIPPED_BY_GATE", "0.410", "0.00", "", "") + "\n")
        f.write(row("10:20", "NOT_ASKED", "", "", "", "", "gate_disabled", lat=0) + "\n")

    with open(log, "w", encoding="utf-8") as f:
        # The service clock is the machine's, not the chart's — deliberately unrelated to
        # the bar stamps, because the join must never quietly fall back to matching on it.
        for clock, bar, p, tk, s in (("14:01:12", "10:00", "0.612", "True", "3.52"),
                                     ("14:06:12", "10:05", "0.640", "True", "3.68"),
                                     ("14:11:12", "10:10", "0.900", "True", "3.75"),
                                     ("14:16:00", "10:15", "0.410", "False", "0.00")):
            # 10:10 carries a prob the ledger does not: the disagreement under test.
            f.write(f"{day} {clock}  decide NOISE_H_RF: prob={p} take={tk} size={s} "
                    f"(61ms, bar {day} {bar}:00-04:00, 2573 bars @ 5m)\n")

    a = audit(day, decisions_path=dec, log_path=log,
              fills_path=os.path.join(tmp, "nope.csv"))
    b = a["legs"]["NOISE_H_RF"]
    checks = [
        ("5 opportunities counted", b["opportunities"] == 5),
        ("4 asked", b["asked"] == 4),
        ("3 ordered", b["ordered"] == 3),
        ("1 skipped by the gate", b["skipped_by_gate"] == 1),
        ("1 not asked, reason gate_disabled",
         b["not_asked"] == 1 and b["not_asked_by_reason"] == {"gate_disabled": 1}),
        ("size dial reported dead (one distinct order size)",
         b["contracts_ordered_distinct"] == [9]),
        ("intended size mean is the model's, not the order's",
         b["size_intended_mean"] == 3.65 and b["size_ordered_mean"] == 3.0),
        ("clamp counted (11 asked -> 9 ordered, x3)", b["clamped"] == 3),
        ("latency p50 present", b["latency_p50"] == 60),
        ("ledger/service disagreement surfaced",
         (b["agreement"] or {}).get("disagree") == 1),
        ("3 of 4 answers agree", (b["agreement"] or {}).get("agree") == 3),
        ("G3 flagged", a["defects"]["G3_size_dial_dead"]["seen"] is True),
        ("missing fills degrade to a dash with a reason",
         b["fills"] is None and "fills" in b["dashes"]),
    ]
    # and the whole point: a missing ledger must not read as a quiet, healthy day
    m = audit(day, decisions_path=os.path.join(tmp, "gone.csv"), log_path=log,
              fills_path=os.path.join(tmp, "nope.csv"))
    checks += [
        ("missing ledger -> ok is None, not False", m["ok"] is None),
        ("missing ledger -> every count is a dash, never 0",
         m["legs"]["NOISE_H_RF"]["opportunities"] is None and m["totals"] is None),
        ("missing ledger -> G1 called out", m["defects"]["G1_unjoinable"]["seen"] is True),
        ("missing ledger -> verdict says so", m["verdict"].startswith("NO LEDGER")),
    ]
    # The shadow hand-off, exercised the way the nightly report calls it: a leg the
    # engine signalled and the NinjaScript never even looked at. This is the 2026-08-24
    # shape, and it is the one line the board must never fail to print.
    rep = {"legs": {"NOISE_H_RF": {"n_signals": 4,
                                   "gate": {"n_in": 6, "n_kept": 4, "n_skipped": 2,
                                            "avg_size": 3.61, "ok": True}},
                    "ORB_H": {"n_signals": 2, "gate": {"n_in": 2, "n_kept": 2,
                                                       "avg_size": 1.2, "ok": True}}}}
    s = audit(day, decisions_path=dec, log_path=log,
              fills_path=os.path.join(tmp, "nope.csv"), report=rep)
    checks += [
        ("shadow numbers ride alongside the live ones",
         s["legs"]["NOISE_H_RF"]["shadow"]["gate_n_kept"] == 4),
        ("a leg the engine signalled and the ledger never saw is called out",
         any("recorded no opportunity at all" in c for c in s["complaints"])),
    ]

    bad = [name for name, okk in checks if not okk]
    for name, okk in checks:
        print(f"  [{'PASS' if okk else 'FAIL'}] {name}")
    print(f"selftest: {len(checks) - len(bad)}/{len(checks)} passed  (fixtures in {tmp})")
    return not bad


def main(argv=None):
    import argparse
    import json
    import sys
    try:
        # The Windows console defaults to cp1252 and would render every em dash in this
        # report as a question mark — which, in a file whose whole subject is dashes, is
        # a needlessly confusing way to be right.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Audit one day of live ML gate decisions.")
    p.add_argument("--date", help="session date in New York, YYYY-MM-DD (default: today)")
    p.add_argument("--decisions", default=None, help=f"override {DECISIONS_CSV}")
    p.add_argument("--log", default=None, help=f"override {GATE_LOG}")
    p.add_argument("--fills", default=None, help=f"override {FILLS_CSV}")
    p.add_argument("--json", action="store_true", help="raw dict instead of the summary")
    p.add_argument("--selftest", action="store_true",
                   help="run the synthetic join check (writes only to a temp dir)")
    a = p.parse_args(argv)
    if a.selftest:
        return 0 if _selftest() else 1
    day = a.date or (datetime.now(_ET) if _ET else datetime.now()).strftime("%Y-%m-%d")
    res = audit(day, decisions_path=a.decisions, log_path=a.log, fills_path=a.fills)
    if a.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        _print(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
