r"""tools/cloud_signal_repair_20260914.py -- void two known-bad row groups in api/cloud_signal.py's
live signal ledger, in place, never deleting a row (api/qqq_exec.py consumes signals.csv by row
count -- see _consume_engine_signals -- so removing rows would hide the next real signals from it).

STATUS: apply only after the owner has said "apply the ledger repair" in chat
(WEBULL_PAPER_TODO.md items 1 and 4). Dry run by default; changes nothing until --apply.

ITEM 1 (docs/CLOUD_SIGNAL_REPAIR_20260914.md). At 00:55 ET on 2026-09-14 a background session's
`python -m api.cloud_signal --replay 2026-09-03` wrote into the LIVE ledger instead of a scratch
copy (fixed on main since, commit cff0006): four fake NOISE_304 rows (a SEED, two Sept-3 buys, one
Sept-3 sell) plus the live engine's own EXIT of the still-open fake trade at 09:31 ET. That is
signals.csv data rows 8-12 (header not counted), and state.json's legs.NOISE_304 exists only
because of it. Voids rows 8-12 (event -> VOID_*, reason gets a prefix, every other byte untouched)
and deletes legs.NOISE_304 so the engine re-learns NOISE_304 silently at the next session open --
exactly what it would have done on 2026-09-14 without the replay.

ITEM 4 (WEBULL_PAPER_TODO.md #4). A second signal-engine process ran on the cloud box from ~02:09
to ~14:33 UTC on 2026-09-21 (its own healthcheck restarted a runner that should have stayed off).
It wrote one duplicate NOISE_304 ENTRY: the same trade (long, ref 09:40 ET @ 729.81, trade id
NOISE_304-20260921T134000Z-L) signalled twice, ~0.65s apart. api/qqq_exec.py's own
entry_duplicate guard already ignored the second one (see qqq_exec.log), so voiding it changes no
executed trade -- only the record. Before touching anything, this tool repeats section 4's own
check ("confirm the duplicate row is the only damage"): it scans signals.csv and state.json for
NOISE_304/ENGUQ_335/ORB_R6 across the double-writer window (2026-09-21 00:37-14:33 UTC) for any
OTHER duplicate or lost-state record, and refuses if it finds one, exactly like a row mismatch.

PRECONDITIONS (refuse, exit 2, write nothing):
  - the two target rows/groups must match what is documented above EXACTLY (or already be voided);
  - legs.NOISE_304 must exist with no repair marker (or be already gone with the marker set);
  - item 4's "only damage" scan must come back clean before an item-4 apply;
  - a NOISE_304 record with exit_emitted=false refuses the item-1 apply unless qqq_exec's own
    shadow book shows no open NOISE lot (a real trade may still be live on the leg);
  - pre-repair-20260914 backups without either repair marker, whose live files differ from those
    backups, mean an earlier apply half-finished -- stop for a human;
  - --apply additionally refuses outside its safe window: now (ET) must be a weekday after 16:05
    or before 09:25, or a weekend (api.qqq_exec._in_market_window's own 09:25-16:05 definition,
    inverted), the heartbeat must show the live writer stopped or idle, and (when psutil is
    available) no process may have api.cloud_signal --loop/--once/--live-paths on its command line.

WRITES (only under --apply, only once all of the above holds): backs up both files first
(<file>.pre-repair-20260914, once, via shutil.copy2), writes state.json then signals.csv each via
a .tmp sibling + a retried os.replace (5 tries, 200ms apart -- Windows refuses to replace a file
another process has open), restores state.json from its backup if the signals.csv replace then
fails, and appends a plain-text record to <home>/cloud_signal/corrections.log. Idempotent: once
applied, a second run (dry or --apply) prints "nothing to repair" and exits 0 without touching
backups or the log again.

The home directory is --home, else $EDGELOG_HOME, else api.cloud_signal's own default
(C:\EdgeLog on Windows). Never guess a different EDGELOG_HOME than the rest of this codebase uses.

Usage:
    python tools/cloud_signal_repair_20260914.py [--home DIR]            # dry run (default)
    python tools/cloud_signal_repair_20260914.py [--home DIR] --apply    # write the changes
"""
import argparse
import csv
import datetime as _dt
import filecmp
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api import cloud_signal as cs           # noqa: E402
from api import qqq_exec as qe               # noqa: E402
import tools.qqq_paper as qp                 # noqa: E402

try:
    import psutil as _psutil                 # same optional-dependency convention as api/runner.py
except Exception:                            # pragma: no cover - degrade to heartbeat-only checks
    _psutil = None


# ── item 1: the 2026-09-14 replay contamination (docs/CLOUD_SIGNAL_REPAIR_20260914.md) ──────────
ITEM1_LEG = "NOISE_304"
ITEM1_PREFIX_SEED_ENTRY = ("void 20260914: written into the live ledger by CLI --replay "
                          "2026-09-03 at 00:55 ET; ")
ITEM1_PREFIX_ROW12 = "void 20260914: live EXIT of the replay's 2026-09-03 11:00 trade; "
ITEM1_MARKER_KEY = "20260914_replay_contamination"

# Data row number (1-indexed, header not counted) -> exact expected shape. Rows are found by
# POSITION, not by scanning: nothing has ever deleted a row from this ledger, so the five bad
# rows written on 2026-09-14 are still physically rows 8-12 no matter how much has been appended
# since. Position is then cross-checked against content below -- belt and suspenders.
ITEM1_ROWS = [
    dict(row=8, event="SEED", side="", ref_time="", ref_price="",
        emitted_at="2026-09-14T00:55:21.008295-04:00",
        new_event="VOID_SEED", prefix=ITEM1_PREFIX_SEED_ENTRY),
    dict(row=9, event="ENTRY", side="long", ref_time="2026-09-03T09:40:00-04:00", ref_price="712.78",
        emitted_at="2026-09-14T00:55:22.286878-04:00",
        new_event="VOID_ENTRY", prefix=ITEM1_PREFIX_SEED_ENTRY),
    dict(row=10, event="EXIT", side="long", ref_time="2026-09-03T10:05:00-04:00", ref_price="711.275",
        emitted_at="2026-09-14T00:55:23.555021-04:00",
        new_event="VOID_EXIT", prefix=ITEM1_PREFIX_SEED_ENTRY),
    dict(row=11, event="ENTRY", side="long", ref_time="2026-09-03T11:00:00-04:00", ref_price="713.5699",
        emitted_at="2026-09-14T00:55:25.724420-04:00",
        new_event="VOID_ENTRY", prefix=ITEM1_PREFIX_SEED_ENTRY),
    dict(row=12, event="EXIT", side="long", ref_time="2026-09-03T15:55:00-04:00", ref_price="717.61",
        emitted_at="2026-09-14T09:31:00.324783-04:00",
        new_event="VOID_EXIT", prefix=ITEM1_PREFIX_ROW12),
]

# ── item 4: the 2026-09-21 duplicate NOISE_304 ENTRY (WEBULL_PAPER_TODO.md #4) ───────────────────
ITEM4_LEG = "NOISE_304"
ITEM4_EVENT = "ENTRY"
ITEM4_SIDE = "long"
ITEM4_REF_TIME = "2026-09-21T09:40:00-04:00"
ITEM4_REF_PRICE = "729.81"
ITEM4_TRADE_ID = "NOISE_304-20260921T134000Z-L"
ITEM4_PREFIX = ("void 20260921: duplicate signal from the cloud box's second signal-engine "
               "process (2026-09-21 00:37-14:33 UTC); api/qqq_exec.py's own entry_duplicate "
               "guard had already ignored it; ")
ITEM4_MARKER_KEY = "20260921_duplicate_entry"

# The double-writer window itself (WEBULL_PAPER_TODO.md #4), in ET (this ledger's own emitted_at
# timezone) so it can be compared against emitted_at strings with no conversion at read time.
ITEM4_WINDOW_START_ET = "2026-09-20T20:37:00-04:00"    # 2026-09-21 00:37 UTC
ITEM4_WINDOW_END_ET = "2026-09-21T10:33:00-04:00"      # 2026-09-21 14:33 UTC
ITEM4_WINDOW_LEGS = ("NOISE_304", "ENGUQ_335", "ORB_R6")

BACKUP_SUFFIX = ".pre-repair-20260914"   # named for the tool, shared by both items' one apply run


# ── small helpers ─────────────────────────────────────────────────────────────────────────────
def _price_matches(actual, expected):
    a, e = str(actual if actual is not None else "").strip(), str(expected if expected is not None else "").strip()
    if a == "" or e == "":
        return a == e
    try:
        return abs(float(a) - float(e)) <= 1e-6
    except ValueError:
        return a == e


def _git_sha():
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _read_ledger(signals_path):
    """(header, rows) read via csv.DictReader (newline="" so CRLF round-trips unchanged);
    (None, None) if the file does not exist."""
    if not os.path.exists(signals_path):
        return None, None
    with open(signals_path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


def _read_qqq_exec_state(home):
    """The Webull paper shadow book's OWN state.json (a different process's store, same home
    root -- see docs/CLOUD_SIGNAL_REPAIR_20260914.md's qqq_exec evidence section). Read-only,
    never written by this tool. {} if it does not exist -- a missing shadow state has no open
    lot on any leg, which is the conservative reading precondition 3 needs."""
    path = os.path.join(home, "qqq_exec", "state.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


# ── item 1: locate + classify rows 8-12 ──────────────────────────────────────────────────────
def _classify_row1(row, expect):
    """'match' (still the original contamination), 'voided' (already repaired), or 'mismatch'."""
    same_shape = (row.get("emitted_at") == expect["emitted_at"] and row.get("leg") == ITEM1_LEG
                 and row.get("side", "") == expect["side"] and row.get("ref_time", "") == expect["ref_time"]
                 and _price_matches(row.get("ref_price", ""), expect["ref_price"]))
    if not same_shape:
        return "mismatch"
    if row.get("event") == expect["event"]:
        return "match"
    if row.get("event") == expect["new_event"] and str(row.get("reason", "")).startswith(expect["prefix"]):
        return "voided"
    return "mismatch"


def _check_item1_rows(rows):
    results = []
    for expect in ITEM1_ROWS:
        idx = expect["row"] - 1
        row = rows[idx] if 0 <= idx < len(rows) else None
        cls = "missing" if row is None else _classify_row1(row, expect)
        results.append((expect, row, cls))
    classes = {c for _, _, c in results}
    if classes == {"match"}:
        return "pending", results
    if classes == {"voided"}:
        return "done", results
    return "mismatch", results


def _check_item1_state(state):
    legs = state.get("legs") or {}
    marker = bool((state.get("repairs") or {}).get(ITEM1_MARKER_KEY))
    has_leg = ITEM1_LEG in legs
    if has_leg and not marker:
        swallowed = [(tid, rec) for tid, rec in (legs[ITEM1_LEG].get("trades") or {}).items()
                    if not rec.get("exit_emitted", True)]
        return "pending", legs[ITEM1_LEG], swallowed
    if (not has_leg) and marker:
        return "done", None, []
    return "mismatch", legs.get(ITEM1_LEG), []


# ── item 4: locate the duplicate pair anywhere in the file, and confirm it is the only damage ──
def _is_item4_target(row):
    return (row.get("leg") == ITEM4_LEG and row.get("event") in (ITEM4_EVENT, "VOID_ENTRY")
           and row.get("side", "") == ITEM4_SIDE and row.get("ref_time", "") == ITEM4_REF_TIME
           and row.get("trade_id", "") == ITEM4_TRADE_ID
           and _price_matches(row.get("ref_price", ""), ITEM4_REF_PRICE))


def _check_item4_rows(rows):
    idxs = [i for i, r in enumerate(rows) if _is_item4_target(r)]
    pending = [i for i in idxs if rows[i].get("event") == ITEM4_EVENT]
    voided = [i for i in idxs if rows[i].get("event") == "VOID_ENTRY"
             and str(rows[i].get("reason", "")).startswith(ITEM4_PREFIX)]
    if len(idxs) == 2 and len(pending) == 2 and len(voided) == 0:
        i1, i2 = pending
        dup_idx, keep_idx = (i1, i2) if rows[i1]["emitted_at"] > rows[i2]["emitted_at"] else (i2, i1)
        return "pending", dup_idx, keep_idx, idxs
    if len(idxs) == 2 and len(pending) == 1 and len(voided) == 1:
        return "done", None, None, idxs
    return "mismatch", None, None, idxs


def _within_item4_window(emitted_at):
    try:
        t = _dt.datetime.fromisoformat(str(emitted_at))
    except Exception:
        return False
    start = _dt.datetime.fromisoformat(ITEM4_WINDOW_START_ET)
    end = _dt.datetime.fromisoformat(ITEM4_WINDOW_END_ET)
    return start <= t <= end


def _confirm_item4_only_damage(rows, state):
    """WEBULL_PAPER_TODO.md #4 step 1, "confirm the duplicate row is the only damage": every
    ENTRY/EXIT row for the three crown legs inside the double-writer window, grouped by identity
    -- any group seen more than once is a duplicate; and every one of those legs' state.json
    trade records whose entry sits in the window but was never exited. Returns (ok, report) --
    ok is True only when there is exactly the one known duplicate and nothing else. Never writes;
    called on every run (dry or apply) so the finding is always printed."""
    windowed = [r for r in rows if r.get("leg") in ITEM4_WINDOW_LEGS
               and str(r.get("event", "")).upper() in ("ENTRY", "EXIT")
               and _within_item4_window(r.get("emitted_at", ""))]
    groups = {}
    for r in windowed:
        key = (r.get("leg"), r.get("event"), r.get("side", ""), r.get("ref_time", ""),
              r.get("ref_price", ""), r.get("trade_id", ""))
        groups.setdefault(key, []).append(r)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}

    open_in_window = []
    for leg in ITEM4_WINDOW_LEGS:
        trades = ((state.get("legs") or {}).get(leg) or {}).get("trades") or {}
        for tid, rec in trades.items():
            et_ = rec.get("entry_time")
            if et_ and _within_item4_window(str(et_)) and not rec.get("exit_emitted", True):
                open_in_window.append((leg, tid, rec))

    def _is_expected(key):
        leg, event, side, ref_time, ref_price, trade_id = key
        return (leg, event, side, ref_time, trade_id) == (ITEM4_LEG, ITEM4_EVENT, ITEM4_SIDE,
                                                          ITEM4_REF_TIME, ITEM4_TRADE_ID) \
            and _price_matches(ref_price, ITEM4_REF_PRICE)

    ok = (len(dup_groups) == 1 and _is_expected(next(iter(dup_groups)))
         and not open_in_window)
    return ok, {"windowed_count": len(windowed), "dup_groups": dup_groups,
               "open_in_window": open_in_window}


# ── printing (dry run and pre-apply echo share this -- "short and plain") ──────────────────────
def _fmt_row1_line(row_num, row, expect=None):
    arrow = f"{row['event']} -> {expect['new_event']}" if expect else row.get("event", "")
    return (f"  row {row_num:<3} {row.get('emitted_at', '')}  {arrow:<20} "
           f"leg={row.get('leg', ''):<10} side={row.get('side') or '-':<5} "
           f"price={row.get('ref_price') or '-'}")


def _print_item4_confirmation(report, ok, required, log):
    """`required` is False once item 4 is already applied (its one duplicate is now VOID_*, so
    the window scan naturally sees no duplicate any more) -- the verdict line then says so
    instead of printing a misleading "NOT confirmed" next to a run that changed nothing."""
    log(f"item 4 check: {report['windowed_count']} ENTRY/EXIT row(s) for "
        f"{'/'.join(ITEM4_WINDOW_LEGS)} between {ITEM4_WINDOW_START_ET} and {ITEM4_WINDOW_END_ET}")
    if not report["dup_groups"]:
        log("item 4 check: no duplicate rows found in that window")
    for key, group in report["dup_groups"].items():
        leg, event, side, ref_time, ref_price, trade_id = key
        log(f"item 4 check: x{len(group)} duplicate -- {leg} {event} {side} ref_time={ref_time} "
            f"ref_price={ref_price} trade_id={trade_id}")
    for leg, tid, rec in report["open_in_window"]:
        log(f"item 4 check: legs.{leg} trade {tid} has exit_emitted=false inside the window: {rec}")
    if not required:
        log("item 4 check: already applied earlier -- this scan is informational only")
    elif ok:
        log("item 4 check: confirmed -- the duplicate row is the only damage")
    else:
        log("item 4 check: NOT confirmed -- see above")


def _append_corrections_log(paths, now_et, row_changes, removed_leg, did1, did4, log):
    log_path = os.path.join(paths["state_dir"], "corrections.log")
    lines = [f"\n=== {now_et.strftime('%F %T')} ET  tools/cloud_signal_repair_20260914.py --apply  "
            f"(git {_git_sha()})\n"]
    if did1:
        lines.append("item 1 (docs/CLOUD_SIGNAL_REPAIR_20260914.md): voided the 2026-09-14 "
                     "replay-contamination rows 8-12 and removed legs.NOISE_304.\n")
    if did4:
        lines.append("item 4 (WEBULL_PAPER_TODO.md #4): voided the 2026-09-21 duplicate "
                     f"NOISE_304 ENTRY row (trade_id {ITEM4_TRADE_ID}).\n")
    for rownum, before, after in row_changes:
        lines.append(f"  row {rownum}: event {before.get('event')} -> {after.get('event')}, "
                     f"reason {before.get('reason')!r} -> {after.get('reason')!r}\n")
    if removed_leg is not None:
        lines.append(f"  removed legs.{ITEM1_LEG}: {json.dumps(removed_leg, default=str)}\n")
    if did1:
        lines.append("  legs.ORB_R6 / legs.ENGUQ_335: left unchanged (see "
                     "docs/CLOUD_SIGNAL_REPAIR_20260914.md for the inert-record inference).\n")
    os.makedirs(paths["state_dir"], exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.writelines(lines)


# ── apply-time preconditions (never checked/enforced for a dry run) ────────────────────────────
def _read_heartbeat(paths):
    if not os.path.exists(paths["heartbeat_path"]):
        return None
    try:
        with open(paths["heartbeat_path"], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _running_live_writer_cmdlines():
    """None when psutil is unavailable (unknown -- heartbeat freshness is the primary guard,
    see the module docstring); else the cmdline of every process that looks like
    `python -m api.cloud_signal --loop|--once|--live-paths`."""
    if _psutil is None:
        return None
    hits = []
    for p in _psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "cloud_signal" in cmd and any(f in cmd for f in ("--loop", "--once", "--live-paths")):
            hits.append(f"pid {p.info.get('pid')}: {cmd}")
    return hits


def _check_apply_window(paths, now_et, log):
    naive = now_et.replace(tzinfo=None) if now_et.tzinfo else now_et
    if qe._in_market_window(naive):
        log("REFUSED: now is inside the 09:25-16:05 ET weekday window -- apply on a weekend, "
            "or a weekday after 16:05 or before 09:25 ET.")
        return False
    age = cs._live_writer_age_sec(paths)
    hb = _read_heartbeat(paths) or {}
    note = str(hb.get("note", ""))
    stopped = (age is None) or (age >= cs.LIVE_WRITER_FRESH_SEC)
    idle = (age is not None and age < cs.LIVE_WRITER_FRESH_SEC and note == "outside session hours")
    if not (stopped or idle):
        log(f"REFUSED: {paths['heartbeat_path']} is {age:.0f}s old with note={note!r} -- a live "
            f"writer looks active. Stop it first.")
        return False
    hits = _running_live_writer_cmdlines()
    if hits is None:
        log("[warn] psutil unavailable -- skipped the running-process check; heartbeat freshness "
            "is the primary guard here.")
    elif hits:
        log("REFUSED: a live cloud_signal process is running:")
        for h in hits:
            log(f"  {h}")
        return False
    return True


def _check_half_applied(paths, state, log):
    sig_bak = paths["signals_path"] + BACKUP_SUFFIX
    st_bak = paths["state_path"] + BACKUP_SUFFIX
    backups_exist = os.path.exists(sig_bak) or os.path.exists(st_bak)
    any_marker = bool((state.get("repairs") or {}).get(ITEM1_MARKER_KEY)) \
        or bool((state.get("repairs") or {}).get(ITEM4_MARKER_KEY))
    if backups_exist and not any_marker:
        identical = (os.path.exists(sig_bak) and os.path.exists(st_bak)
                    and filecmp.cmp(sig_bak, paths["signals_path"], shallow=False)
                    and filecmp.cmp(st_bak, paths["state_path"], shallow=False))
        if not identical:
            log(f"REFUSED: {sig_bak} / {st_bak} already exist but no repair marker is set, and "
                f"the live files differ from those backups -- an earlier apply may have "
                f"half-finished. Compare them by hand before re-running.")
            return False
    return True


# ── the one entry point (importable for tests; main() below is the CLI) ────────────────────────
def run_repair(home, apply_=False, now=None, log=print):
    """Returns a process exit code: 0 (applied, or nothing to repair, or a clean dry run),
    1 (a write failed after preconditions passed -- files restored where possible), 2 (refused:
    a precondition or a content mismatch -- nothing was ever written)."""
    paths = cs._paths(home=home)
    now_et = now or qe._now_et()

    header, rows = _read_ledger(paths["signals_path"])
    if rows is None:
        log(f"REFUSED: no signals.csv at {paths['signals_path']} -- nothing to check against the "
            f"spec, so nothing to repair.")
        return 2
    state = cs._load_state(paths)

    status1, results1 = _check_item1_rows(rows)
    status1_state, leg_state, swallowed = _check_item1_state(state)
    status4, dup_idx, keep_idx, matches4 = _check_item4_rows(rows)

    item1_marker = bool((state.get("repairs") or {}).get(ITEM1_MARKER_KEY))
    item4_marker = bool((state.get("repairs") or {}).get(ITEM4_MARKER_KEY))
    item1_pending = (status1 == "pending" and status1_state == "pending" and not item1_marker)
    item1_done = (status1 == "done" and status1_state == "done" and item1_marker)
    item4_pending = (status4 == "pending" and not item4_marker)
    item4_done = (status4 == "done" and item4_marker)

    ok4dmg, report4 = _confirm_item4_only_damage(rows, state)
    _print_item4_confirmation(report4, ok4dmg, required=(status4 == "pending"), log=log)

    if not (item1_pending or item1_done):
        log("REFUSED: item 1 (2026-09-14 replay rows) does not match "
            "docs/CLOUD_SIGNAL_REPAIR_20260914.md exactly -- printing what was found, changing "
            "nothing:")
        for expect, row, cls in results1:
            if row is None:
                log(f"  row {expect['row']}: MISSING (file has fewer than {expect['row']} data row(s))")
            else:
                log(_fmt_row1_line(expect["row"], row) + f"  [{cls}]")
        log(f"  legs.NOISE_304 present={ITEM1_LEG in (state.get('legs') or {})} "
            f"marker_present={item1_marker}")
        return 2

    if not (item4_pending or item4_done):
        log("REFUSED: item 4 (2026-09-21 duplicate NOISE entry) does not match "
            "WEBULL_PAPER_TODO.md section 4 exactly -- changing nothing.")
        return 2

    if item4_pending and not ok4dmg:
        log("REFUSED: item 4's 'confirm the duplicate is the only damage' check did not come "
            "back clean (see above) -- changing nothing.")
        return 2

    if item1_pending and swallowed:
        log(f"legs.NOISE_304 has {len(swallowed)} record(s) with exit_emitted=false:")
        for tid, rec in swallowed:
            log(f"  {tid}: {rec}")
        qexec_state = _read_qqq_exec_state(home)
        if "NOISE" in ((qexec_state or {}).get("legs") or {}):
            log("REFUSED: qqq_exec's shadow book still has an open NOISE lot -- a real trade may "
                "still be live on this leg. Stop and look before voiding legs.NOISE_304.")
            return 2

    if not _check_half_applied(paths, state, log):
        return 2

    if item1_done and item4_done:
        log("nothing to repair")
        return 0

    log("rows to relabel:")
    if not item1_done:
        for expect, row, cls in results1:
            log(_fmt_row1_line(expect["row"], row, expect))
    if not item4_done:
        r = rows[dup_idx]
        log(_fmt_row1_line(dup_idx + 1, r) + f"  -> VOID_ENTRY  (duplicate; kept row {keep_idx + 1})")

    log("state keys to touch:")
    if not item1_done:
        log(f"  legs.{ITEM1_LEG}  (remove)")
        log(f"  repairs.{ITEM1_MARKER_KEY}  (add)")
    if not item4_done:
        log(f"  repairs.{ITEM4_MARKER_KEY}  (add)")

    if not apply_:
        log("DRY RUN -- no files changed. Re-run with --apply to write.")
        return 0

    if not _check_apply_window(paths, now_et, log):
        return 2

    sig_bak = paths["signals_path"] + BACKUP_SUFFIX
    st_bak = paths["state_path"] + BACKUP_SUFFIX
    shutil.copy2(paths["signals_path"], sig_bak)
    shutil.copy2(paths["state_path"], st_bak)

    removed_leg = None
    new_state = json.loads(json.dumps(state, default=str))
    if not item1_done:
        removed_leg = (new_state.get("legs") or {}).pop(ITEM1_LEG, None)
        new_state.setdefault("repairs", {})[ITEM1_MARKER_KEY] = {
            "applied_at": now_et.isoformat(), "tool": "tools/cloud_signal_repair_20260914.py",
            "git_sha": _git_sha(),
        }
    if not item4_done:
        new_state.setdefault("repairs", {})[ITEM4_MARKER_KEY] = {
            "applied_at": now_et.isoformat(), "tool": "tools/cloud_signal_repair_20260914.py",
            "git_sha": _git_sha(), "voided_row": dup_idx + 1, "kept_row": keep_idx + 1,
            "trade_id": ITEM4_TRADE_ID,
        }

    tmp_state = paths["state_path"] + ".tmp"
    with open(tmp_state, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, default=str)
    if not qp._replace_with_retry(tmp_state, paths["state_path"], log=log,
                                  what="[cloud-signal-repair] state.json", retries=5, sleep=0.2):
        log("REFUSED: could not replace state.json after retries -- nothing has changed.")
        return 1

    new_rows = [dict(r) for r in rows]
    row_changes = []
    if not item1_done:
        for expect, row, cls in results1:
            if cls != "match":
                continue
            i = expect["row"] - 1
            before = dict(new_rows[i])
            new_rows[i]["event"] = expect["new_event"]
            new_rows[i]["reason"] = expect["prefix"] + str(before.get("reason", ""))
            row_changes.append((expect["row"], before, dict(new_rows[i])))
    if not item4_done:
        before = dict(new_rows[dup_idx])
        new_rows[dup_idx]["event"] = "VOID_ENTRY"
        new_rows[dup_idx]["reason"] = ITEM4_PREFIX + str(before.get("reason", ""))
        row_changes.append((dup_idx + 1, before, dict(new_rows[dup_idx])))

    tmp_sig = paths["signals_path"] + ".tmp"
    with open(tmp_sig, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in new_rows:
            w.writerow({k: r.get(k, "") for k in header})
    if not qp._replace_with_retry(tmp_sig, paths["signals_path"], log=log,
                                  what="[cloud-signal-repair] signals.csv", retries=5, sleep=0.2):
        shutil.copy2(st_bak, paths["state_path"])
        log("REFUSED: could not replace signals.csv after retries -- state.json restored from "
            "backup, nothing has changed.")
        return 1

    _append_corrections_log(paths, now_et, row_changes, removed_leg, not item1_done, not item4_done, log)
    log(f"applied. backups: {sig_bak}, {st_bak}; audit trail: "
        f"{os.path.join(paths['state_dir'], 'corrections.log')}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=None,
                    help="EDGELOG_HOME override (default: $EDGELOG_HOME, else api.cloud_signal's "
                         "own default)")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args(argv)
    home = args.home or cs.edgelog_home()
    return run_repair(home=home, apply_=args.apply, log=print)


if __name__ == "__main__":
    sys.exit(main())
