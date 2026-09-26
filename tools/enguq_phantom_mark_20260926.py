r"""tools/enguq_phantom_mark_20260926.py -- MARK (never delete) the two ENGU-Q ghost trades
named in WEBULL_GO_LIVE.md 3.7, once fully classified, verified and evidenced by two agents.

THE BUG (fixed in augur_strategies/ENGUQ_1M_ETH_R2_1_0.py / augur_engine/fastloop.py, this same
change): the shallow-limit entry's resting-limit fill scan clamps its window at the end of
available data (`jmax = min(i + _N_SCAN, n - 1)`) and treated a scan cut short by the data
running out exactly like a scan that genuinely found nothing -- so a live, incrementally-growing
read could book a trade a full backtest never takes. Two such phantom entries reached the live
ENGUQ_335 leg on the cloud box:

    trade_id                          entry_time (ET)          entry_px   shares
    ENGUQ_335-20260917T190700Z-L      2026-09-17T15:07:00-04:00  716.8592     139
    ENGUQ_335-20260923T180000Z-L      2026-09-23T14:00:00-04:00  741.1147     134

Evidence (box, read via read-only ssh/scp into a local scratch copy, never written):
  - cloud_signal/signals.csv: an ENTRY row for each, emitted at 2026-09-17T15:08:23.872853-04:00
    and 2026-09-23T14:01:26.996825-04:00.
  - cloud_signal/state.json: legs.ENGUQ_335.trades[trade_id] for both has exit_emitted=false and
    will never get a real EXIT -- the corrected engine's true trade list does not contain them,
    so nothing will ever recompute a matching exit for either.
  - qqq_exec/trades.csv: the book actually opened both (leg ENGUQ, entry_ts 2026-09-17 15:08:24
    @ 716.8692 and 2026-09-23 14:01:29 @ 741.1247) -- both real Webull paper orders, real fills.
    qqq_exec.log shows 'WARN entry_leg_busy ... 2026-09-23 14:01 ... not taken' for the REAL
    signal that the first phantom's still-open lot blocked.

WHAT THIS TOOL DOES, and NOTHING ELSE:
  1. cloud_signal/signals.csv: relabels each ghost's ENTRY row to VOID_ENTRY, exactly the
     convention tools/cloud_signal_repair_20260914.py uses -- the reason is KEPT and prefixed
     with a 'ghost: phantom limit entry, the backtest never takes it' note. Never deletes a row
     (api/qqq_exec.py consumes signals.csv by row count).
  2. cloud_signal/state.json: sets `"ghost": true` and a `"ghost_reason"` string on each trade
     record. `exit_emitted` is left exactly as it is (false, which is the true fact -- no exit
     was ever emitted) so nothing here is fabricated; the `ghost` marker is what tells a human,
     or any FUTURE tool in this family, that the record is a known, permanent void, not a
     position anything should keep waiting on.
     LIMITATION (finding 4, minor, left as documentation rather than code -- changing it would
     mean fabricating exit_emitted=True, which this tool's own "never fabricate" rule above
     forbids): `ghost` is a convention nothing in api/cloud_signal.py reads today. The only code
     that acts on a recorded trade is `_diff_leg`, which emits an EXIT for any trade with
     exit_emitted False once the engine's own trade list shows it closed. If either ghost's
     trade_id were ever re-derived (e.g. a rolling-window edge change) the engine could still
     try to emit an orphan EXIT for it. In practice this is harmless -- qqq_exec only closes a
     lot whose trade_id matches, and both lots were already flattened at 15:59 -- but the
     "engine never expects their EXIT" guarantee holds by convention, not by code. The engine's
     own convention for "never emit an exit" is the late/stale-skip shape instead
     (exit_emitted=True, exit_time None, skipped=<reason>); a future tool could adopt that shape
     for ghosts too, at the cost of no longer being able to say `exit_emitted` was never changed.
  3. qqq_exec/trades.csv: IF the file already has a `note` column, sets it to the same ghost
     note on the two matching rows (matched by leg=ENGUQ + entry_ts + entry side; the 2026-09-17
     row predates this ledger's trade_id column) and leaves every other row's note blank. IF it
     does NOT have a `note` column (true as of this writing), this tool does NOT add one and does
     NOT touch trades.csv at all -- api/qqq_exec.py's own `_append_csv` calls
     `_migrate_csv_header(path, TRADE_COLS)` before every append, and a header this tool adds that
     TRADE_COLS does not know about would be silently rewritten away (dropping both ghost notes)
     the next time qqq_exec closes any trade. Instead the two matching rows' identity (leg,
     entry_ts, entry_px) is recorded in corrections.log only, for a human or a future tool to
     apply once TRADE_COLS itself carries a `note` column (a lead/integration decision, out of
     this tool's scope). Either way, no P&L field (entry_px, exit_px, pnl, nq_pnl_points, ...) or
     any other existing column is ever touched, and no row is ever added, removed or reordered.

WHAT THIS TOOL DELIBERATELY DOES NOT DO. It does not close, resize or otherwise touch
qqq_exec's own OPEN-LOT state (api/qqq_exec.py's separate state.json) or send any broker order --
that book already executed real (paper) fills for both phantoms, and unwinding a live position is
an operational, human decision outside a marking tool's remit (and outside what this task allows:
never call Webull or any broker API). It also never adds a `note` column to trades.csv itself --
see item 3 above for why that is api/qqq_exec.py's call, not this tool's.

PRECONDITIONS (refuse, exit 2, write nothing) -- same shape as
tools/cloud_signal_repair_20260914.py:
  - all three files must exist;
  - both ghosts must match the evidence above EXACTLY in signals.csv and state.json (identity
    only in qqq_exec/trades.csv -- see item 3), or already be marked;
  - pre-mark backups without the repair marker, whose live files differ from those backups, mean
    an earlier apply half-finished -- stop for a human;
  - --apply additionally refuses outside its safe window: now (ET) must be a weekday after 16:05
    or before 09:25, or a weekend (api.qqq_exec._in_market_window's own 09:25-16:05 definition,
    inverted); the cloud_signal heartbeat must show the live writer stopped or idle; qqq_exec's
    own state.json must not have been written in the last cs.LIVE_WRITER_FRESH_SEC seconds (a
    concurrent write there is what finding 4 was about -- see api/qqq_exec.py's own 5s tick
    loop); and (when psutil is available) no process may have api.cloud_signal
    --loop/--once/--live-paths or cloud_signal_thread (the box's systemd form -- see
    deploy/cloud/edgelog-cloud-signal.service), or api.qqq_exec --serve/--once, on its command
    line.

WRITES (only under --apply, only once every precondition above holds): backs up signals.csv and
state.json first (<file>.pre-phantom-mark-20260926, once, via shutil.copy2; trades.csv too, ONLY
if it already has a `note` column and this run will therefore write it), writes state.json and
signals.csv (and trades.csv when applicable) each via a .tmp sibling + a retried os.replace
(Windows refuses to replace a file another process has open), and appends a plain-text record to
<home>/cloud_signal/corrections.log. Idempotent: once applied, a second run (dry or --apply)
prints "nothing to mark" and exits 0 without touching backups or the log again.

The home directory is --home, else $EDGELOG_HOME, else api.cloud_signal's own default
(C:\EdgeLog on Windows). qqq_exec's trades.csv is read from <home>/qqq_exec/trades.csv, matching
api/qqq_exec.py's own OUT_DIR default (EDGELOG_QQQ_EXEC_DIR is not consulted here -- see that
module's TRADES_CSV if a box ever sets it).

Usage:
    python tools/enguq_phantom_mark_20260926.py [--home DIR]            # dry run (default)
    python tools/enguq_phantom_mark_20260926.py [--home DIR] --apply    # write the changes

NEVER run this against the box (ssh access here is read-only: ls/head/tail/wc/grep/cat and scp
FROM the box). Test it only against local copies in a temp directory.
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


GHOST_LEG = "ENGUQ_335"            # cloud_signal's key
EXEC_LEG = "ENGUQ"                 # api/qqq_exec.py's ENGINE_LEG_MAP short key for it
GHOST_NOTE = "ghost: phantom limit entry, the backtest never takes it"
GHOST_REASON = (GHOST_NOTE + " (WEBULL_GO_LIVE.md 3.7; ENGUQ_1M_ETH_R2_1_0.py's fill-window "
               "truncation bug -- see augur_engine/fastloop.py's phantom_safe)")
MARKER_KEY = "20260926_enguq_phantom_mark"
BACKUP_SUFFIX = ".pre-phantom-mark-20260926"

# The two ghosts, exactly as the evidence in this file's docstring gives them.
GHOSTS = [
    dict(
        trade_id="ENGUQ_335-20260917T190700Z-L",
        entry_time="2026-09-17T15:07:00-04:00", side="long",
        entry_px=716.8592, shares=139,
        signals_emitted_at="2026-09-17T15:08:23.872853-04:00",
        exec_entry_ts="2026-09-17 15:08:24", exec_entry_px=716.8692,
    ),
    dict(
        trade_id="ENGUQ_335-20260923T180000Z-L",
        entry_time="2026-09-23T14:00:00-04:00", side="long",
        entry_px=741.1147, shares=134,
        signals_emitted_at="2026-09-23T14:01:26.996825-04:00",
        exec_entry_ts="2026-09-23 14:01:29", exec_entry_px=741.1247,
    ),
]


# ── small helpers (same convention as tools/cloud_signal_repair_20260914.py) ────────────────────
def _price_matches(actual, expected):
    a = str(actual if actual is not None else "").strip()
    e = str(expected if expected is not None else "").strip()
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


def _exec_trades_path(home):
    return os.path.join(home, "qqq_exec", "trades.csv")


def _read_csv(path):
    """(header, rows) via csv.DictReader (newline="" so CRLF round-trips unchanged); (None,
    None) if the file does not exist."""
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


def _write_csv(path, header, rows, log):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in header})
    return qp._replace_with_retry(tmp, path, log=log, what=f"[enguq-phantom-mark] {os.path.basename(path)}")


# ── classification: 'match' (still live/unmarked), 'marked' (already done), 'mismatch' ─────────
def _classify_signals_row(row, ghost):
    same_shape = (row.get("emitted_at") == ghost["signals_emitted_at"] and row.get("leg") == GHOST_LEG
                 and row.get("side", "") == ghost["side"] and row.get("ref_time", "") == ghost["entry_time"]
                 and _price_matches(row.get("ref_price", ""), ghost["entry_px"])
                 and row.get("trade_id", "") == ghost["trade_id"])
    if not same_shape:
        return "mismatch"
    if row.get("event") == "ENTRY":
        return "match"
    if row.get("event") == "VOID_ENTRY" and str(row.get("reason", "")).startswith(GHOST_REASON):
        return "marked"
    return "mismatch"


def _find_signals_row(rows, ghost):
    """Position is not assumed (unlike the repair tool's item 1 -- these rows are further
    back in a ledger that keeps growing): found by identity, among ENTRY or already-VOID_ENTRY
    rows for this leg/trade_id."""
    hits = [i for i, r in enumerate(rows) if r.get("leg") == GHOST_LEG
           and r.get("trade_id") == ghost["trade_id"]
           and r.get("event") in ("ENTRY", "VOID_ENTRY")]
    return hits


def _classify_state_trade(rec, ghost):
    if rec is None:
        return "missing"
    try:
        # Finding 6: a non-integer string (e.g. "139.0") raised ValueError here and crashed the
        # tool with a traceback instead of cleanly refusing -- any value that cannot be read as
        # a share count is not the evidence, so it classifies as a plain mismatch.
        shares_match = int(float(rec.get("shares") or 0)) == ghost["shares"]
    except (TypeError, ValueError):
        return "mismatch"
    same_shape = (rec.get("entry_time") == ghost["entry_time"] and rec.get("side") == ghost["side"]
                 and _price_matches(rec.get("entry_px"), ghost["entry_px"])
                 and shares_match)
    if not same_shape:
        return "mismatch"
    if rec.get("ghost") is True and str(rec.get("ghost_reason", "")).startswith(GHOST_NOTE):
        return "marked"
    if rec.get("ghost") in (None, False) and rec.get("exit_emitted") is False:
        return "match"
    return "mismatch"


def _classify_exec_row(row, ghost, has_note_col):
    """When trades.csv has no `note` column, this tool never writes it (see the module
    docstring, item 3 / finding 3) -- so identity is all there is to classify: "match" if it
    is the row the evidence names, "mismatch" otherwise. There is no "marked" state on this
    file in that case; the ghost's mark lives in signals.csv + state.json, and this row's
    identity is recorded in corrections.log instead."""
    same_shape = (row.get("leg") == EXEC_LEG and row.get("entry_ts") == ghost["exec_entry_ts"]
                 and row.get("side", "") == ghost["side"]
                 and _price_matches(row.get("entry_px", ""), ghost["exec_entry_px"]))
    if not same_shape:
        return "mismatch"
    if not has_note_col:
        return "match"
    note = str(row.get("note") or "")
    if note.startswith(GHOST_NOTE):
        return "marked"
    if note == "":
        return "match"
    return "mismatch"


def _find_exec_row(rows, ghost):
    return [i for i, r in enumerate(rows) if r.get("leg") == EXEC_LEG
           and r.get("entry_ts") == ghost["exec_entry_ts"]]


# ── printing ─────────────────────────────────────────────────────────────────────────────────
def _fmt_ghost_status(ghost, sig_cls, state_cls, exec_cls):
    return (f"  {ghost['trade_id']}: signals.csv={sig_cls} state.json={state_cls} "
           f"qqq_exec/trades.csv={exec_cls}")


def _append_corrections_log(paths, now_et, changes, has_note_col, log):
    log_path = os.path.join(paths["state_dir"], "corrections.log")
    exec_line = ("noted qqq_exec/trades.csv" if has_note_col else
                "qqq_exec/trades.csv left untouched (no note column -- identity recorded here)")
    lines = [f"\n=== {now_et.strftime('%F %T')} ET  tools/enguq_phantom_mark_20260926.py --apply  "
            f"(git {_git_sha()})\n",
            f"WEBULL_GO_LIVE.md 3.7: marked 2 ENGU-Q phantom limit entries as ghosts "
            f"(relabelled signals.csv, flagged state.json, {exec_line}). "
            f"No row deleted, no P&L field touched, no broker order sent.\n"]
    for trade_id, sig_change, exec_change in changes:
        lines.append(f"  {trade_id}:\n")
        lines.append(f"    signals.csv row: event {sig_change[0]!r} -> {sig_change[1]!r}\n")
        lines.append(f"    state.json: legs.{GHOST_LEG}.trades[{trade_id!r}].ghost = true\n")
        if has_note_col:
            lines.append(f"    qqq_exec/trades.csv row: note -> {exec_change!r}\n")
        else:
            lines.append(f"    qqq_exec/trades.csv row (NOT written, no note column): "
                         f"leg={exec_change['leg']!r} entry_ts={exec_change['entry_ts']!r} "
                         f"entry_px={exec_change['entry_px']!r} -- note pending a note column "
                         f"in api/qqq_exec.py's TRADE_COLS\n")
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
    """Finding 3: the box's systemd unit (deploy/cloud/edgelog-cloud-signal.service) runs
    `python -u -c 'from api.cloud_signal import cloud_signal_thread; cloud_signal_thread()'` --
    no --loop/--once/--live-paths flag on that command line at all, so the flag-only check below
    used to never see it (the heartbeat freshness check in _check_apply_window was the only
    guard against that form). Matching the bare function name too covers it directly."""
    if _psutil is None:
        return None
    hits = []
    for p in _psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "cloud_signal" in cmd and (
                "cloud_signal_thread" in cmd or
                any(f in cmd for f in ("--loop", "--once", "--live-paths"))):
            hits.append(f"pid {p.info.get('pid')}: {cmd}")
    return hits


def _running_qqq_exec_cmdlines():
    """Review finding 4 (minor): --apply used to check only that cloud_signal was idle, but
    edgelog-qqq-exec keeps running independently (its own 5s tick loop) and rewrites
    trades.csv on every close, header migration and trim -- a write landing between this
    tool's read and its os.replace would lose a ledger row. Same convention as
    _running_live_writer_cmdlines above (api/qqq_exec.py's own main(): the live service runs
    as `--serve` or a scheduled `--once`, per its argparse). Matching on the module name alone
    would also hit an unrelated pytest run of tests/test_qqq_exec_*.py or a plain syntax check
    of api/qqq_exec.py in a SIBLING worktree -- which happened during development of this very
    check -- so the flag is required, exactly like cloud_signal's own --loop/--once/--live-paths
    check just above."""
    if _psutil is None:
        return None
    hits = []
    for p in _psutil.process_iter(["pid", "cmdline"]):
        try:
            cmd = " ".join(p.info.get("cmdline") or [])
        except Exception:
            continue
        if "qqq_exec" in cmd and "cloud_signal" not in cmd and any(
                f in cmd for f in ("--serve", "--once")):
            hits.append(f"pid {p.info.get('pid')}: {cmd}")
    return hits


def _qqq_exec_state_age_sec(exec_path, now_et):
    """Age (seconds) of qqq_exec's OWN state.json, next to trades.csv under the same OUT_DIR
    (api/qqq_exec.py's STATE_PATH). None if it does not exist -- read the same way as a
    stopped/never-started writer, matching cs._live_writer_age_sec's own convention."""
    state_path = os.path.join(os.path.dirname(exec_path), "state.json")
    if not os.path.exists(state_path):
        return None
    try:
        mtime = _dt.datetime.fromtimestamp(os.path.getmtime(state_path), tz=_dt.timezone.utc)
        now_utc = now_et.astimezone(_dt.timezone.utc) if now_et.tzinfo else now_et.replace(
            tzinfo=_dt.timezone.utc)
        return (now_utc - mtime).total_seconds()
    except Exception:
        return None


def _check_apply_window(paths, exec_path, now_et, log):
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
        log("[warn] psutil unavailable -- skipped the cloud_signal running-process check; "
            "heartbeat freshness is the primary guard here.")
    elif hits:
        log("REFUSED: a live cloud_signal process is running:")
        for h in hits:
            log(f"  {h}")
        return False

    # edgelog-qqq-exec itself: finding 4. Its OWN state.json age is the heartbeat-equivalent
    # (it has no separate heartbeat file of its own), backed up by a process-cmdline check.
    qe_age = _qqq_exec_state_age_sec(exec_path, now_et)
    if qe_age is not None and qe_age < cs.LIVE_WRITER_FRESH_SEC:
        log(f"REFUSED: {os.path.join(os.path.dirname(exec_path), 'state.json')} is "
            f"{qe_age:.0f}s old -- edgelog-qqq-exec looks active. Stop it first "
            f"(it rewrites qqq_exec/trades.csv on every close, header migration and trim).")
        return False
    qe_hits = _running_qqq_exec_cmdlines()
    if qe_hits is None:
        log("[warn] psutil unavailable -- skipped the qqq_exec running-process check; stop "
            "edgelog-qqq-exec by hand before --apply (it rewrites qqq_exec/trades.csv).")
    elif qe_hits:
        log("REFUSED: a live qqq_exec process is running:")
        for h in qe_hits:
            log(f"  {h}")
        return False
    return True


def _check_half_applied(paths, exec_path, state, has_note_col, log):
    backups = [paths["signals_path"] + BACKUP_SUFFIX, paths["state_path"] + BACKUP_SUFFIX]
    live = [paths["signals_path"], paths["state_path"]]
    if has_note_col:
        # trades.csv is only ever backed up/written when it already has a note column (see
        # finding 3) -- with no note column this tool never touches it, so there is nothing
        # to compare here and an exec backup could never legitimately exist.
        backups.append(exec_path + BACKUP_SUFFIX)
        live.append(exec_path)
    marker = bool((state.get("repairs") or {}).get(MARKER_KEY))
    backups_exist = any(os.path.exists(b) for b in backups)
    if backups_exist and not marker:
        identical = all(os.path.exists(b) and os.path.exists(v) and filecmp.cmp(b, v, shallow=False)
                        for b, v in zip(backups, live))
        if not identical:
            log(f"REFUSED: one or more of {backups} already exist but no repair marker is set, "
                f"and the live files differ from those backups -- an earlier apply may have "
                f"half-finished. Compare them by hand before re-running.")
            return False
    return True


# ── the one entry point (importable for tests; main() below is the CLI) ────────────────────────
def run_mark(home, apply_=False, now=None, log=print):
    """Returns a process exit code: 0 (applied, or nothing to mark, or a clean dry run),
    1 (a write failed after preconditions passed -- earlier writes restored where possible),
    2 (refused: a precondition or a content mismatch -- nothing was ever written)."""
    paths = cs._paths(home=home)
    exec_path = _exec_trades_path(home)
    now_et = now or qe._now_et()

    sig_header, sig_rows = _read_csv(paths["signals_path"])
    if sig_rows is None:
        log(f"REFUSED: no signals.csv at {paths['signals_path']} -- nothing to check against the "
            f"evidence, so nothing to mark.")
        return 2
    state = cs._load_state(paths)
    exec_header, exec_rows = _read_csv(exec_path)
    if exec_rows is None:
        log(f"REFUSED: no trades.csv at {exec_path} -- nothing to check against the evidence, so "
            f"nothing to mark.")
        return 2
    # Finding 3: only write trades.csv (note included) when it ALREADY has a note column.
    # api/qqq_exec.py's own TRADE_COLS does not carry one as of this writing, and adding the
    # column here would be wiped by that module's own header migration on its next close.
    has_note_col = "note" in exec_header

    per_ghost = []   # (ghost, sig_idx or None, sig_cls, state_cls, exec_idx or None, exec_cls)
    for ghost in GHOSTS:
        sig_hits = _find_signals_row(sig_rows, ghost)
        sig_idx, sig_cls = (None, "missing") if not sig_hits else (
            sig_hits[0], _classify_signals_row(sig_rows[sig_hits[0]], ghost))
        if len(sig_hits) > 1:
            sig_cls = "mismatch"   # more than one row claims this trade id -- stop, do not guess

        rec = ((state.get("legs") or {}).get(GHOST_LEG, {}).get("trades") or {}).get(ghost["trade_id"])
        state_cls = _classify_state_trade(rec, ghost)

        exec_hits = _find_exec_row(exec_rows, ghost)
        exec_idx, exec_cls = (None, "missing") if not exec_hits else (
            exec_hits[0], _classify_exec_row(exec_rows[exec_hits[0]], ghost, has_note_col))
        if len(exec_hits) > 1:
            exec_cls = "mismatch"

        per_ghost.append((ghost, sig_idx, sig_cls, state_cls, exec_idx, exec_cls))

    log("evidence check:")
    for ghost, _si, sig_cls, state_cls, _ei, exec_cls in per_ghost:
        log(_fmt_ghost_status(ghost, sig_cls, state_cls, exec_cls))
    if not has_note_col:
        log("  note: qqq_exec/trades.csv has no 'note' column -- its rows are matched by "
            "identity only (see finding 3); this run will NOT write that file.")

    # exec_cls carries a real "marked" state only when a note column exists to hold it; with
    # no note column, "match" is as far as exec identity ever gets (this tool never writes
    # it), so done_all falls back to sig+state alone for that ghost.
    def _exec_pending_ok(exec_cls):
        return exec_cls == "match"

    def _exec_done_ok(exec_cls):
        return exec_cls == "marked" if has_note_col else exec_cls == "match"

    pending_all = all(sig_cls == "match" and state_cls == "match" and _exec_pending_ok(exec_cls)
                      for _g, _si, sig_cls, state_cls, _ei, exec_cls in per_ghost)
    done_all = all(sig_cls == "marked" and state_cls == "marked" and _exec_done_ok(exec_cls)
                  for _g, _si, sig_cls, state_cls, _ei, exec_cls in per_ghost)
    if not (pending_all or done_all):
        log("REFUSED: at least one ghost does not match the evidence in this file's docstring "
            "exactly (see the per-file status above) -- changing nothing.")
        return 2

    if not _check_half_applied(paths, exec_path, state, has_note_col, log):
        return 2

    if done_all:
        log("nothing to mark")
        return 0

    log("rows to relabel (signals.csv):")
    for ghost, sig_idx, _sc, _st, _ei, _ec in per_ghost:
        log(f"  row {sig_idx + 2} (data row {sig_idx + 1}): "  # +2: header + 1-index
            f"{sig_rows[sig_idx].get('event')} -> VOID_ENTRY  ({ghost['trade_id']})")
    log("state.json keys to touch:")
    for ghost, *_r in per_ghost:
        log(f"  legs.{GHOST_LEG}.trades[{ghost['trade_id']!r}].ghost = true")
    log(f"  repairs.{MARKER_KEY}  (add)")
    if has_note_col:
        log("qqq_exec/trades.csv rows to note:")
        for ghost, _si, _sc, _st, exec_idx, _ec in per_ghost:
            log(f"  row {exec_idx + 2} (data row {exec_idx + 1}): note -> {GHOST_REASON!r}  "
                f"({ghost['exec_entry_ts']})")
    else:
        log("qqq_exec/trades.csv: NOT writing (no note column) -- recording identity in "
            "corrections.log instead:")
        for ghost, _si, _sc, _st, exec_idx, _ec in per_ghost:
            log(f"  row {exec_idx + 2} (data row {exec_idx + 1}): leg={EXEC_LEG} "
                f"entry_ts={ghost['exec_entry_ts']!r} entry_px={ghost['exec_entry_px']!r}")

    if not apply_:
        log("DRY RUN -- no files changed. Re-run with --apply to write.")
        return 0

    if not _check_apply_window(paths, exec_path, now_et, log):
        return 2

    sig_bak = paths["signals_path"] + BACKUP_SUFFIX
    st_bak = paths["state_path"] + BACKUP_SUFFIX
    shutil.copy2(paths["signals_path"], sig_bak)
    shutil.copy2(paths["state_path"], st_bak)
    exec_bak = None
    if has_note_col:
        exec_bak = exec_path + BACKUP_SUFFIX
        shutil.copy2(exec_path, exec_bak)

    # 1) state.json -- never fabricate exit_emitted/exit_time/exit_px; only add the marker.
    new_state = json.loads(json.dumps(state, default=str))
    for ghost in GHOSTS:
        rec = new_state["legs"][GHOST_LEG]["trades"][ghost["trade_id"]]
        rec["ghost"] = True
        rec["ghost_reason"] = GHOST_REASON
    new_state.setdefault("repairs", {})[MARKER_KEY] = {
        "applied_at": now_et.isoformat(), "tool": "tools/enguq_phantom_mark_20260926.py",
        "git_sha": _git_sha(), "trade_ids": [g["trade_id"] for g in GHOSTS],
    }
    tmp_state = paths["state_path"] + ".tmp"
    with open(tmp_state, "w", encoding="utf-8") as f:
        json.dump(new_state, f, indent=2, default=str)
    if not qp._replace_with_retry(tmp_state, paths["state_path"], log=log,
                                  what="[enguq-phantom-mark] state.json"):
        log("REFUSED: could not replace state.json after retries -- nothing has changed.")
        return 1

    # 2) signals.csv -- relabel, reason kept and prefixed, nothing deleted.
    new_sig_rows = [dict(r) for r in sig_rows]
    sig_changes = []
    for ghost, sig_idx, *_r in per_ghost:
        before_event = new_sig_rows[sig_idx].get("event")
        before_reason = str(new_sig_rows[sig_idx].get("reason", ""))
        new_sig_rows[sig_idx]["event"] = "VOID_ENTRY"
        new_sig_rows[sig_idx]["reason"] = GHOST_REASON + (f"; {before_reason}" if before_reason else "")
        sig_changes.append((ghost["trade_id"], before_event, "VOID_ENTRY"))
    if not _write_csv(paths["signals_path"], sig_header, new_sig_rows, log):
        shutil.copy2(st_bak, paths["state_path"])
        log("REFUSED: could not replace signals.csv after retries -- state.json restored from "
            "backup, nothing has changed.")
        return 1

    # 3) qqq_exec/trades.csv -- ONLY when it already has a note column (finding 3). Never adds
    # one: api/qqq_exec.py's own header migration (TRADE_COLS) would wipe an unrecognised
    # column on the next trade it closes. With no note column, the two rows' identity is
    # recorded in corrections.log below instead, and this file is never opened for writing.
    exec_changes = []
    if has_note_col:
        new_exec_rows = [dict(r) for r in exec_rows]
        for ghost, _si, _sc, _st, exec_idx, _ec in per_ghost:
            new_exec_rows[exec_idx]["note"] = GHOST_REASON
            exec_changes.append(GHOST_REASON)
        if not _write_csv(exec_path, exec_header, new_exec_rows, log):
            shutil.copy2(st_bak, paths["state_path"])
            shutil.copy2(sig_bak, paths["signals_path"])
            log("REFUSED: could not replace qqq_exec/trades.csv after retries -- state.json and "
                "signals.csv restored from backup, nothing has changed.")
            return 1
    else:
        for ghost, _si, _sc, _st, exec_idx, _ec in per_ghost:
            exec_changes.append({"leg": EXEC_LEG, "entry_ts": ghost["exec_entry_ts"],
                                 "entry_px": ghost["exec_entry_px"]})

    changes = [(g["trade_id"], (sc[1], sc[2]), ec)
              for g, sc, ec in zip(GHOSTS, sig_changes, exec_changes)]
    _append_corrections_log(paths, now_et, changes, has_note_col, log)
    log(f"applied. backups: {sig_bak}, {st_bak}"
        f"{', ' + exec_bak if exec_bak else ''}; audit trail: "
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
    return run_mark(home=home, apply_=args.apply, log=print)


if __name__ == "__main__":
    sys.exit(main())
