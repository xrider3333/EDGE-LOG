"""paper_review_routine.py - the whole daily PAPER EOD review behind ONE script.

WHY: the review session runs unattended on a schedule. Every separate command it types
needs its own standing permission, and a single one it lacks leaves the run sitting on
an approval prompt nobody is there to click - that is exactly how the scheduled task
"edgelog-paper-eod-review" stalled ~5 seconds into nearly every run since late August
(its first Bash command waited on a permission prompt, the run still read "succeeded",
so no daily verdict was written for weeks). Same fix as commit de75e3f applied to the
trade-scores routine: ONE script, three subcommands, ONE inbox file the session writes.

  python tools/paper_review_routine.py start [--date YYYY-MM-DD]
      find the oldest unreviewed paper day (or MISSING REPORT, or NOTHING TO REVIEW),
      gather every fact a reviewer needs, read-only, into
      tools/data/paper_review_inbox/facts.json (+ a human-readable facts.md).
  python tools/paper_review_routine.py finish [--dry-run]
      read tools/data/paper_review_inbox/verdict.json (written by the model), validate
      it, merge-write the verdict into Firestore users/<uid>/paper_reports/<date>.
  python tools/paper_review_routine.py abort
      throw the run away (inbox files are kept under _aborted/ for a look).

  start --selftest        one fixture day, no Firestore read - proves the permissions.
  finish --dry-run        validate + print what would be written, no Firestore write.
  (a selftest run is ALWAYS a dry finish, regardless of --dry-run)

No git, no shipping in here - this routine only reads local files/Firestore and writes
ONE Firestore doc (merge, never overwriting fields it did not set). The inbox lives in
tools/data/paper_review_inbox/ (gitignored).

DATE SELECTION (documented here since the task left the exact policy to this script):
look at the last LOOKBACK_DAYS US trading days up to and including "today" (ET). Walk
them OLDEST -> NEWEST. The first day whose report doc EXISTS and whose status is not
'reviewed' is the review target - oldest first, so a run of missed days catches up one
day at a time (one day per `start` call; run it again to pick up the next one). If none
of those days has an unreviewed-but-present report, but one of them has NO report doc at
all, that is surfaced as MISSING REPORT for the OLDEST such gap - a missing report is a
runner failure and should never be silently skipped in favour of a later day. Otherwise:
NOTHING TO REVIEW. `--date` forces a specific date and skips the scan (still refuses a
non-trading day, and still reports MISSING REPORT if that date's doc does not exist).
"""
import os
import io
import re
import sys
import json
import shutil
import argparse
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
sys.path.insert(0, ROOT)
from api import market_calendar as MC  # noqa: E402

UID = "IO0K35JpLIcH9YK4C0pMNYUzZOM2"
INBOX = os.path.join(ROOT, "tools", "data", "paper_review_inbox")
PAPER_START = "2026-08-11"          # api/paper.py PAPER_START - nothing exists before this
LOOKBACK_DAYS = 5
FILES = ("facts.json", "facts.md", "verdict.json", "state.json")

# Paths the unattended session's own facts come from. Module-level so tests can
# monkeypatch them onto tmp files instead of the real (382 MB+) machine logs.
RUNNER_LOG = r"C:\EdgeLog\runner.log"
NT_RECOVER_LOG = r"C:\EdgeLog\nt_recover.log"
GATE_LIVE_LOG = r"C:\EdgeLog\gate_live.log"


def say(*a):
    print(*a, flush=True)


def et_now():
    from zoneinfo import ZoneInfo
    return dt.datetime.now(ZoneInfo("America/New_York"))


def inbox(f):
    return os.path.join(INBOX, f)


def load(fp):
    with io.open(fp, encoding="utf-8") as f:
        return json.load(f)


def dump(fp, obj):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with io.open(fp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def shelve(tag):
    """Move this run's inbox files aside (never deleted) so the next run starts clean."""
    present = [f for f in FILES if os.path.exists(inbox(f))]
    if not present:
        return None
    dest = os.path.join(INBOX, "_" + tag, et_now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for f in present:
        shutil.move(inbox(f), os.path.join(dest, f))
    return dest


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore
    cred_path = os.path.join(ROOT, "serviceAccount.json")
    if not os.path.exists(cred_path):
        cred_path = os.path.join(SHARED, "serviceAccount.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred_path))
    return firestore.client()


# ── trading-day helpers ──────────────────────────────────────────────────────────────
def _last_n_sessions(ref_date, n):
    """Last n US trading sessions up to and including ref_date, oldest first."""
    start = ref_date - dt.timedelta(days=n * 3 + 10)   # generous pad for holidays/weekends
    days = MC.sessions_between(start, ref_date)
    return days[-n:] if len(days) > n else days


def _iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


# ── log tailing (runner.log is 380+ MB and growing - never load it whole) ────────────
def _tail_lines(path, max_bytes=4_000_000):
    if not os.path.exists(path):
        return []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(size - max_bytes)
            f.readline()   # drop the partial first line
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def _full_grep(path, needles, max_matches=300):
    """Line-by-line scan (never loads the file into memory at once) - used only when a
    full diagnosis is actually needed (MISSING REPORT), since runner.log is 380+ MB."""
    if not os.path.exists(path):
        return []
    out = []
    needles = [n.lower() for n in needles]
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                low = line.lower()
                if any(n in low for n in needles):
                    out.append(line.rstrip("\n"))
                    if len(out) >= max_matches:
                        break
    except OSError:
        return out
    return out


def _grep_lines(lines, needles):
    needles = [n.lower() for n in needles]
    return [l for l in lines if any(n in l.lower() for n in needles)]


# ── Firestore reads (kept lean - Spark free tier, 50k reads/day) ─────────────────────
def _get_report(db, date_str):
    ref = (db.collection("users").document(UID).collection("paper_reports")
           .document(date_str))
    snap = ref.get()
    return snap.to_dict() if snap.exists else None


def _cumulative(db, date_str):
    """Sum leg/blend/book pnl_usd across every paper_reports doc from PAPER_START to
    date_str inclusive. One .get() per trading day in range (a few dozen by now) -
    cheap, and avoids relying on a document-id range query needing a composite index."""
    days = [d for d in MC.sessions_between(PAPER_START, date_str)
            if d.isoformat() <= date_str]
    per_leg, blend_total, book_total, n_days = {}, 0.0, 0.0, 0
    for d in days:
        rep = _get_report(db, d.isoformat())
        if not rep:
            continue
        n_days += 1
        for k, blk in (rep.get("legs") or {}).items():
            try:
                per_leg[k] = per_leg.get(k, 0.0) + float(blk.get("pnl_usd") or 0.0)
            except (TypeError, ValueError):
                pass
        try:
            blend_total += float((rep.get("blend") or {}).get("pnl_usd") or 0.0)
        except (TypeError, ValueError):
            pass
        try:
            book_total += float((rep.get("book") or {}).get("pnl_usd") or 0.0)
        except (TypeError, ValueError):
            pass
    return {"since": PAPER_START, "through": date_str, "n_report_days": n_days,
            "per_leg_pnl_usd": per_leg, "blend_pnl_usd": round(blend_total, 2),
            "book_pnl_usd": round(book_total, 2)}


def _trades_for_date(db, date_str):
    try:
        docs = (db.collection("users").document(UID).collection("paper_trades")
                .where("run_date", "==", date_str).stream())
    except Exception as e:
        return [], f"paper_trades query failed: {type(e).__name__}: {e}"
    out = []
    roll_flagged = []
    for d in docs:
        t = d.to_dict() or {}
        t["_id"] = d.id
        if t.get("roll_artifact") or "roll_artifact" in (t.get("flags") or []):
            roll_flagged.append(d.id)
        out.append(t)
    return out, roll_flagged


def _webull_doc(db):
    try:
        ref = (db.collection("users").document(UID).collection("meta")
               .document("qqq_exec"))
        snap = ref.get()
        return (snap.to_dict() if snap.exists else None), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _webull_trades_on_date(doc, date_str):
    """trades_all rows whose entry OR exit falls on date_str. meta/qqq_exec is a LIVE
    snapshot (one doc, continuously overwritten) - not a per-day history - so this is a
    best-effort filter of whatever the current snapshot still remembers (trades_all is
    capped, newest first read from the CSV directly), not a guaranteed historical record
    for a day several sessions back."""
    if not doc:
        return []
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    out = []
    for r in (doc.get("trades_all") or []):
        for key in ("entry_ts", "exit_ts"):
            ts = r.get(key)
            if ts:
                try:
                    d = dt.datetime.fromtimestamp(float(ts), et).date().isoformat()
                except (TypeError, ValueError, OSError):
                    continue
                if d == date_str:
                    out.append(r)
                    break
    return out


# ── start ─────────────────────────────────────────────────────────────────────────────
def _selftest_facts():
    """One fixture day, entirely fabricated, no Firestore - proves the ALLOWED ACTIONS
    commands run cleanly without touching real data (mirrors score_routine.py's
    start --selftest)."""
    date_str = "2026-08-11"
    return {
        "date": date_str, "selftest": True,
        "generated_at": et_now().isoformat(timespec="seconds"),
        "nt_book": {
            "report_status": "runner_done",
            "legs": {"ORB": {"n_signals": 1, "pnl_usd": 120.0, "n_since_start": 1,
                              "bars_appended": 3, "data_fresh_thru": "2026-08-11 16:00",
                              "warnings": []},
                      "ENGUQ_309": {"n_signals": 0, "pnl_usd": 0.0, "n_since_start": 0,
                                    "bars_appended": 2, "data_fresh_thru": "2026-08-11 16:00",
                                    "warnings": ["SELFTEST fixture leg"]}},
            "blend": {"pnl_usd": 120.0}, "book": {"pnl_usd": 120.0},
            "cumulative": {"since": date_str, "through": date_str, "n_report_days": 1,
                           "per_leg_pnl_usd": {"ORB": 120.0, "ENGUQ_309": 0.0},
                           "blend_pnl_usd": 120.0, "book_pnl_usd": 120.0},
            "trades_today": [{"_id": "pt_ORB_SELFTEST", "leg": "ORB", "pnl_usd": 120.0}],
            "roll_artifact_trade_ids": [],
            "reconcile": {"ok": True, "note": "SELFTEST fixture"},
            "gate_live": {"ok": True, "note": "SELFTEST fixture"},
        },
        "webull_book": {"available": False,
                        "note": "SELFTEST fixture - the real Webull book did not exist yet "
                                "on 2026-08-11 (it started 2026-09-20)."},
        "diagnostics": {"runner_log_lines": [], "nt_recover_lines": [], "gate_live_lines": []},
    }


def _gather_facts(db, date_str):
    rep = _get_report(db, date_str)
    if rep is None:
        return None  # caller handles MISSING REPORT
    trades, roll_or_err = _trades_for_date(db, date_str)
    roll_flagged = roll_or_err if isinstance(roll_or_err, list) else []
    cum = _cumulative(db, date_str)
    wb_doc, wb_err = _webull_doc(db)
    today_et = et_now().date().isoformat()
    webull_book = {"available": wb_doc is not None, "error": wb_err,
                   "is_live_snapshot_for": today_et,
                   "snapshot_is_point_in_time": (date_str == today_et)}
    if wb_doc is not None:
        webull_book.update({
            "cum_pnl_by_leg": wb_doc.get("cum_pnl"),
            "today_block": wb_doc.get("today") if date_str == today_et else None,
            "trades_on_date": _webull_trades_on_date(wb_doc, date_str),
            "rails": wb_doc.get("rails"), "keel": wb_doc.get("keel"),
            "health": wb_doc.get("health"), "readiness": wb_doc.get("readiness"),
            "feed_stale": wb_doc.get("feed_stale"), "breaker_tripped": wb_doc.get("breaker_tripped"),
            "broker": wb_doc.get("broker"), "parity": wb_doc.get("parity"),
            "broker_parity": wb_doc.get("broker_parity"),
            "book_only_summary": wb_doc.get("book_only_summary"),
            "lease": wb_doc.get("lease"),
        })
        if date_str != today_et:
            webull_book["note"] = ("rails/keel/health/readiness/broker/parity are the CURRENT "
                                    "live snapshot, not point-in-time for this date - only "
                                    "cum_pnl_by_leg and trades_on_date are date-specific "
                                    "(best-effort, from the capped trades_all history).")
    else:
        webull_book["note"] = "users/<uid>/meta/qqq_exec doc not found or unreadable."

    tail = _tail_lines(RUNNER_LOG)
    nt_lines = _grep_lines(_tail_lines(NT_RECOVER_LOG, max_bytes=8_000_000), [date_str])
    gate_lines = _grep_lines(_tail_lines(GATE_LIVE_LOG, max_bytes=8_000_000), [date_str])
    runner_lines = _grep_lines(tail, [date_str + ": ", date_str + " GATE"])

    facts = {
        "date": date_str, "selftest": False,
        "generated_at": et_now().isoformat(timespec="seconds"),
        "nt_book": {
            "report_status": rep.get("status"),
            "legs": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                     for k, v in (rep.get("legs") or {}).items()},
            "blend": rep.get("blend"), "book": rep.get("book"), "live": rep.get("live"),
            "cumulative": cum,
            "trades_today": [{kk: vv for kk, vv in t.items()} for t in trades],
            "roll_artifact_trade_ids": roll_flagged,
            "reconcile": rep.get("reconcile"), "gate_live": rep.get("gate_live"),
        },
        "webull_book": webull_book,
        "diagnostics": {
            "runner_log_lines": runner_lines[-100:],
            "nt_recover_lines": nt_lines[-100:],
            "gate_live_lines": gate_lines[-100:],
        },
    }
    return facts


def _facts_md(facts):
    d = facts["date"]
    nt = facts["nt_book"]
    lines = [f"# Paper review facts - {d}" + (" (SELFTEST)" if facts.get("selftest") else ""),
             "", f"Report status: {nt.get('report_status')}", ""]
    lines.append("## NT8 legs (today)")
    for k, v in sorted((nt.get("legs") or {}).items()):
        warn = f"  WARN: {v['warnings']}" if v.get("warnings") else ""
        lines.append(f"- {k}: n_signals={v.get('n_signals')} pnl_usd={v.get('pnl_usd')} "
                     f"fresh_thru={v.get('data_fresh_thru')}{warn}")
    blend = (nt.get("blend") or {}).get("pnl_usd")
    book = (nt.get("book") or {}).get("pnl_usd")
    lines += ["", f"Blend today: ${blend}", f"Book today: ${book}"]
    cum = nt.get("cumulative") or {}
    lines += ["", f"Cumulative since {cum.get('since')} through {cum.get('through')} "
                  f"({cum.get('n_report_days')} report days):",
              f"  blend cumulative: ${cum.get('blend_pnl_usd')}",
              f"  book cumulative: ${cum.get('book_pnl_usd')}"]
    if nt.get("roll_artifact_trade_ids"):
        lines.append(f"ROLL ARTIFACT flagged trades: {nt['roll_artifact_trade_ids']}")
    lines.append("")
    lines.append("## Webull paper book")
    wb = facts["webull_book"]
    if wb.get("available"):
        lines.append(f"cum_pnl_by_leg: {wb.get('cum_pnl_by_leg')}")
        lines.append(f"trades on date: {len(wb.get('trades_on_date') or [])}")
        if wb.get("note"):
            lines.append(f"NOTE: {wb['note']}")
    else:
        lines.append(f"NOT AVAILABLE: {wb.get('note') or wb.get('error')}")
    diag = facts["diagnostics"]
    lines += ["", "## Diagnostics",
              f"runner.log lines matched: {len(diag['runner_log_lines'])}",
              f"nt_recover.log lines matched: {len(diag['nt_recover_lines'])}",
              f"gate_live.log lines matched: {len(diag['gate_live_lines'])}"]
    return "\n".join(lines) + "\n"


def cmd_start(a):
    os.makedirs(INBOX, exist_ok=True)
    old = shelve("stale")
    if old:
        say("an earlier unfinished run was moved aside: " + old)

    if a.selftest:
        facts = _selftest_facts()
        dump(inbox("facts.json"), facts)
        with io.open(inbox("facts.md"), "w", encoding="utf-8") as f:
            f.write(_facts_md(facts))
        dump(inbox("state.json"), {"date": facts["date"], "selftest": True,
                                   "started": et_now().isoformat(timespec="seconds")})
        say(f"SELFTEST: one fixture day ({facts['date']}) - nothing is published")
        say(f"RESULT: REVIEW {facts['date']}")
        return

    db = _db()
    today = et_now().date()

    if a.date:
        date_str = a.date
        d = dt.date.fromisoformat(date_str)
        if not MC.is_session(d):
            say(f"RESULT: NOTHING TO REVIEW ({date_str} is not a US trading day)")
            return
        rep = _get_report(db, date_str)
        if rep is None:
            diag = _full_grep(RUNNER_LOG, [date_str])
            dump(inbox("facts.json"), {"date": date_str, "missing_report": True,
                                       "runner_log_matches": diag[-300:]})
            say(f"RESULT: MISSING REPORT {date_str}")
            for l in diag[-30:]:
                say("  " + l)
            return
        facts = _gather_facts(db, date_str)
    else:
        window = _last_n_sessions(today, LOOKBACK_DAYS)
        target = None
        missing = None
        # Oldest -> newest, stop at the FIRST day that is not already reviewed. A
        # missing report several days back must never be skipped past in favour of a
        # later day that happens to have one - it is a runner failure, and reviewing
        # the newer day first would bury it.
        for d in window:
            date_str = d.isoformat()
            rep = _get_report(db, date_str)
            if rep is None:
                missing = date_str
                break
            if rep.get("status") != "reviewed":
                target = date_str
                break
        if target is None:
            if missing is not None:
                diag = _full_grep(RUNNER_LOG, [missing])
                dump(inbox("facts.json"), {"date": missing, "missing_report": True,
                                           "runner_log_matches": diag[-300:]})
                say(f"RESULT: MISSING REPORT {missing}")
                for l in diag[-30:]:
                    say("  " + l)
                return
            say("RESULT: NOTHING TO REVIEW")
            return
        date_str = target
        facts = _gather_facts(db, date_str)

    if facts is None:
        say(f"RESULT: MISSING REPORT {date_str}")
        return

    dump(inbox("facts.json"), facts)
    with io.open(inbox("facts.md"), "w", encoding="utf-8") as f:
        f.write(_facts_md(facts))
    dump(inbox("state.json"), {"date": date_str, "selftest": False,
                               "started": et_now().isoformat(timespec="seconds")})
    say(f"RESULT: REVIEW {date_str} - read tools/data/paper_review_inbox/facts.json "
        f"(and facts.md), write tools/data/paper_review_inbox/verdict.json, then run: "
        f"python tools/paper_review_routine.py finish")


# ── finish ────────────────────────────────────────────────────────────────────────────
def _word_count(s):
    return len(re.findall(r"\S+", s or ""))


def _clean_text(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _validate_verdict(v, date_str, fix):
    if not isinstance(v, dict):
        fix.append("verdict.json must be a JSON object")
        return
    if v.get("date") != date_str:
        fix.append(f"date must be exactly {date_str!r} (the day facts.json was built for), "
                   f"got {v.get('date')!r}")
    verdict = v.get("verdict")
    if not isinstance(verdict, str) or not verdict.strip():
        fix.append("verdict must be a non-empty plain-English string")
    elif _word_count(verdict) > 120:
        fix.append(f"verdict must be <=120 words, got {_word_count(verdict)}")
    nt_book = v.get("nt_book")
    if not isinstance(nt_book, dict) or not nt_book:
        fix.append("nt_book must be a non-empty object (short per-leg summary strings)")
    else:
        for k, vv in nt_book.items():
            if not isinstance(vv, str) or len(vv.strip()) < 3:
                fix.append(f"nt_book[{k!r}] must be a short descriptive string")
    wb = v.get("webull_book")
    if not isinstance(wb, dict):
        fix.append("webull_book must be an object with orders, trades, realized_pnl, "
                   "rail_trips, feed_stale_minutes, verdict")
    else:
        for f in ("orders", "trades", "rail_trips"):
            if wb.get(f) is not None and not isinstance(wb.get(f), int):
                fix.append(f"webull_book.{f} must be a whole number or null")
        for f in ("realized_pnl", "feed_stale_minutes"):
            if wb.get(f) is not None and not isinstance(wb.get(f), (int, float)):
                fix.append(f"webull_book.{f} must be a number or null")
        if "verdict" not in wb or not isinstance(wb.get("verdict"), str) or not wb["verdict"].strip():
            fix.append("webull_book.verdict must be a non-empty string")
    oa = v.get("owner_actions")
    if not isinstance(oa, list) or not all(isinstance(x, str) for x in oa):
        fix.append("owner_actions must be a JSON list of strings (can be empty)")


def cmd_finish(a):
    if not os.path.exists(inbox("state.json")):
        raise SystemExit("no review run in progress - run: python tools/paper_review_routine.py start")
    st = load(inbox("state.json"))
    date_str = st["date"]
    dry = bool(a.dry_run or st.get("selftest"))

    if not os.path.exists(inbox("verdict.json")):
        raise SystemExit("FIX: write tools/data/paper_review_inbox/verdict.json first "
                         "(see tools/data/PAPER_REVIEW_ROUTINE.md for the format)")
    try:
        verdict = load(inbox("verdict.json"))
    except ValueError as e:
        raise SystemExit(f"FIX: verdict.json is not valid JSON: {e}")

    fix = []
    _validate_verdict(verdict, date_str, fix)
    if fix:
        for f in fix:
            say("FIX: " + f)
        raise SystemExit("verdict.json needs the fixes above - edit it, then run finish again")

    update = {
        "status": "reviewed",
        "verdict": _clean_text(verdict["verdict"]),
        "nt_book_review": {k: _clean_text(v) for k, v in verdict["nt_book"].items()},
        "webull_book_review": verdict["webull_book"],
        "owner_actions": [_clean_text(x) for x in verdict["owner_actions"]],
    }

    if dry:
        say(json.dumps(update, indent=1, ensure_ascii=False))
        where = shelve("dryrun")
        say(f"RESULT: DRY RUN OK - {date_str} verdict validated and would be merged "
            f"(inbox kept in {where})")
        return

    db = _db()
    from firebase_admin import firestore
    payload = dict(update)
    payload["reviewedAt"] = firestore.SERVER_TIMESTAMP
    (db.collection("users").document(UID).collection("paper_reports").document(date_str)
     .set(payload, merge=True))
    shelve("done")
    say(f"RESULT: WRITTEN {date_str}")


def cmd_abort(a):
    where = shelve("aborted")
    say(f"RESULT: ABORTED{' - inbox files kept in ' + where if where else ' - nothing was in progress'}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="EDGE LOG daily PAPER review routine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--date")
    s.add_argument("--selftest", action="store_true")
    f = sub.add_parser("finish")
    f.add_argument("--dry-run", action="store_true")
    sub.add_parser("abort")
    a = ap.parse_args()
    {"start": cmd_start, "finish": cmd_finish, "abort": cmd_abort}[a.cmd](a)


if __name__ == "__main__":
    main()
