#!/usr/bin/env python3
"""
tools/repair_10s_from_replay.py -- rebuild the 10-second order-flow holes from a Tick Replay sidecar.

WHY
---
The PC is switched off / put to sleep every night on purpose. While it is down nothing is captured,
and when NinjaTrader wakes it back-fills the missed 10-second bars from bar history: OHLCV is right
but there are NO ticks, so EdgeLogOHLCExport writes those bars as rt=3 ("live but no ticks") with
delta = buy = sell = 0. A zero there is UNKNOWN, not a quiet bar. The same hole exists as rt=0 rows
with no flow (a history pass with Tick Replay off), and as bars missing from the file altogether.

When the hosting chart is reloaded with TICK REPLAY on, the indicator (v2.1, staged in
C:\\EdgeLog\\_nt_staging\\EdgeLogOHLCExport.repair.cs) also writes a SIDECAR,
C:\\EdgeLog\\ohlc\\replay\\<ROOT>_10s_replay.csv: the same 11 columns, rt = 4 meaning "rebuilt from
tick replay", classified by the very same code as live bars. This tool merges that sidecar into the
live capture file C:\\EdgeLog\\ohlc\\<ROOT>_10s.csv.

MERGE RULES (per sidecar bar; `time` is the bar END in unix seconds, UTC)
------------------------------------------------------------------------
* The bar is in the master AND the master row is rt=3, or carries no flow (buy_vol + sell_vol = 0),
  AND the sidecar row has ticks (tick_count > 0 and buy_vol + sell_vol > 0)
      -> delta / buy_vol / sell_vol / tick_count come from the sidecar, rt becomes 4.
         OHLCV is replaced ONLY when the master volume is 0 (otherwise the master's bar stays).
* The bar is NOT in the master -> INSERTED in time order (rt 4; or rt 3 when the bar traded but the
  replay saw no tick, because that delta is unknown and must stay flagged INVALID downstream).
* A master row that already carries buy/sell is NEVER touched, whatever its rt (0, 1, 2 or 4).
* No row is ever deleted. A result with fewer rows than the input is refused (exit 2).
* A sidecar bar whose close is far from the master's close is skipped (wrong contract / time zone).

SAFETY
------
* Untouched rows stay byte-for-byte identical (the file is edited as bytes, not re-formatted).
* A dated backup of the file is written first (<ohlc>\\_backups\\<name>.pre-repair-YYYYMMDD-HHMMSS).
* Write = temp file in the same folder -> flush + fsync -> read back and count -> os.replace.
* CONCURRENCY. The indicator appends a row to the live file every 10 s (File.AppendAllText, which holds
  the file only for the instant of the write) and does not honour a lock file we could create - it is a
  compiled NinjaTrader DLL we do not touch. So the tool does optimistic concurrency instead:
    1. read the file, merge, write the temp file;
    2. just before the replace re-read the live file; if it only GREW (rows were appended meanwhile) the
       appended bytes are carried over to the merged result and the check repeats; if it changed in any
       other way the whole merge starts again from a fresh read;
    3. immediately before os.replace a hard link to the live file is taken (NTFS). os.replace unlinks the
       live NAME, but the hard link keeps the old data, and an append that landed in the last
       microseconds went to that old data. After the replace the link is compared with what we merged
       and any such row is re-inserted into the new file (in time order) by one more merge pass.
  os.replace fails with a sharing violation while another process holds the file open (the indicator
  mid-append, the 15-minute import task mid-read); the tool then waits and starts over.
* --dry-run reads everything, prints the full summary, writes NOTHING (no backup either).

USAGE
-----
  python tools/repair_10s_from_replay.py                  # NQ and ES from C:\\EdgeLog\\ohlc
  python tools/repair_10s_from_replay.py --dry-run
  python tools/repair_10s_from_replay.py --sym NQ --ohlc-dir D:\\copy --dry-run
  python tools/repair_10s_from_replay.py --master X.csv --sidecar Y.csv

Exit codes: 0 done (or nothing to do), 2 refused (a safety rule tripped), 3 bad / missing input.
Stdlib only.
"""
import argparse
import datetime as dt
import glob
import os
import sys
import time

DEFAULT_OHLC_DIR = r"C:\EdgeLog\ohlc"
DEFAULT_SYMS = ("NQ", "ES")
PERIOD = "10s"
HEADER = "time,open,high,low,close,volume,delta,buy_vol,sell_vol,tick_count,rt"
NCOL = 11
RT_NO_TICKS = 3
RT_REPLAY = 4
DEFAULT_MAX_PRICE_DIFF_PCT = 0.05     # a replay bar's close may differ from the master's by this many percent
DEFAULT_MAX_INSERT = 60000            # ~7 sessions of 10 s bars; more than this is not a normal replay window
KEEP_BACKUPS = 7

# Test hooks (never set in production): called while the file is "between" two of our steps.
_hook_before_final_check = None       # after the temp file is written, before the re-read check
_hook_before_replace = None           # after the last check, right before os.replace


class Refused(Exception):
    """A safety rule tripped: nothing was written."""


class BadInput(Exception):
    """A missing or unreadable input file."""


# ---------------------------------------------------------------------------------------------
# time helpers
# ---------------------------------------------------------------------------------------------
def _et_str(t):
    """Unix seconds -> 'YYYY-MM-DD HH:MM:SS ET' (US Eastern, DST-aware)."""
    if t is None:
        return "-"
    try:
        from zoneinfo import ZoneInfo
        d = dt.datetime.fromtimestamp(int(t), ZoneInfo("America/New_York"))
    except Exception:                                   # no tzdata on this box -> pandas knows the zone
        import pandas as pd
        d = pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert("US/Eastern")
    return d.strftime("%Y-%m-%d %H:%M:%S") + " ET"


# ---------------------------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------------------------
def _parse(line):
    """bytes line (no terminator) -> dict of the numeric fields, or None when malformed."""
    f = line.strip().split(b",")
    if len(f) != NCOL:
        return None
    try:
        return {"t": int(f[0]), "o": float(f[1]), "h": float(f[2]), "l": float(f[3]), "c": float(f[4]),
                "v": float(f[5]), "delta": float(f[6]), "buy": float(f[7]), "sell": float(f[8]),
                "ticks": int(float(f[9])), "rt": int(float(f[10])), "f": f}
    except ValueError:
        return None


def _split_lines(raw):
    """bytes -> (header_line, [data lines without terminators], eol, ends_with_newline)."""
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    ends = raw.endswith(b"\n")
    lines = raw.split(b"\n")
    if ends:
        lines.pop()                                      # the empty piece after the final newline
    lines = [x[:-1] if x.endswith(b"\r") else x for x in lines]
    if not lines:
        return b"", [], eol, ends
    return lines[0], lines[1:], eol, ends


def read_sidecar(path):
    """Sidecar -> ({time: parsed row}, malformed-row count). Later rows win on a repeated time."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise BadInput(f"cannot read sidecar {path}: {e}")
    head, rows, _eol, _ends = _split_lines(raw)
    if head.decode("utf-8", "replace").strip().lstrip("\ufeff") != HEADER:
        raise BadInput(f"sidecar {path}: unexpected header {head[:80]!r}")
    out, bad = {}, 0
    for ln in rows:
        if not ln.strip():
            continue
        p = _parse(ln)
        if p is None:
            bad += 1
            continue
        out[p["t"]] = p
    return out, bad


# ---------------------------------------------------------------------------------------------
# the merge (pure: bytes in, bytes out)
# ---------------------------------------------------------------------------------------------
def _fmt(x):
    """Number back to text the way the indicator formats it ('0.###' style: no trailing zeros)."""
    if float(x) == int(x):
        return str(int(x))
    return ("%.3f" % x).rstrip("0").rstrip(".")


def _needs_flow(p):
    return p["rt"] == RT_NO_TICKS or (p["buy"] + p["sell"]) == 0


def _has_ticks(p):
    return p["ticks"] > 0 and (p["buy"] + p["sell"]) > 0


def merge_bytes(raw, sidecar, max_price_diff_pct=DEFAULT_MAX_PRICE_DIFF_PCT, max_insert=DEFAULT_MAX_INSERT,
                extra_lines=None):
    """Merge `sidecar` ({time: row}) into the master bytes `raw`. Returns (new_bytes, stats).

    `extra_lines` ({time: exact line bytes}) are master rows to re-insert if (and only if) their time is
    absent - the heal pass for a row an indicator append lost to a replace race.
    """
    head, rows, eol, ends = _split_lines(raw)
    if not head:
        raise BadInput("master file is empty (no header)")
    if head.decode("utf-8", "replace").strip().lstrip("\ufeff") != HEADER:
        raise BadInput(f"master: unexpected header {head[:80]!r}")

    parsed = [(_parse(ln) if ln.strip() else None) for ln in rows]
    times = [p["t"] for p in parsed if p is not None]
    if any(b < a for a, b in zip(times, times[1:])):
        raise Refused("master is not sorted by time - fix it first (inserting into it would be a guess)")
    present = set(times)

    st = {"master_rows": sum(1 for ln in rows if ln.strip()), "sidecar_bars": len(sidecar),
          "repaired": 0, "inserted": 0, "inserted_unknown_flow": 0, "skip_no_ticks": 0,
          "skip_price": 0, "skip_has_flow": 0, "repaired_times": [], "inserted_times": [],
          "vol_sum": 0.0, "flow_sum": 0.0, "reach": min(sidecar) if sidecar else None,
          "sidecar_last": max(sidecar) if sidecar else None, "healed": 0}

    out = [None] * len(rows)
    for i, (ln, p) in enumerate(zip(rows, parsed)):
        out[i] = ln
        if p is None:
            continue
        s = sidecar.get(p["t"])
        if s is None:
            continue
        if not _needs_flow(p):
            st["skip_has_flow"] += 1
            continue
        if not _has_ticks(s):
            st["skip_no_ticks"] += 1
            continue
        ref = max(abs(p["c"]), 1.0)
        if abs(p["c"] - s["c"]) > ref * max_price_diff_pct / 100.0:
            st["skip_price"] += 1
            continue
        f = list(p["f"])
        if p["v"] == 0:                                     # master bar had no volume: take the replayed bar whole
            f[1:6] = s["f"][1:6]
            vol = s["v"]
        else:
            vol = p["v"]
        f[6] = s["f"][6]
        f[7] = s["f"][7]
        f[8] = s["f"][8]
        f[9] = s["f"][9]
        f[10] = str(RT_REPLAY).encode()
        out[i] = b",".join(f)
        st["repaired"] += 1
        st["repaired_times"].append(p["t"])
        st["vol_sum"] += vol
        st["flow_sum"] += s["buy"] + s["sell"]

    # bars the master does not have
    new_rows = []
    for t in sorted(sidecar):
        if t in present:
            continue
        s = sidecar[t]
        if _has_ticks(s) or s["v"] == 0:
            rt = RT_REPLAY
        else:
            rt = RT_NO_TICKS                                  # it traded, the replay saw no tick: unknown, keep it flagged
            st["inserted_unknown_flow"] += 1
        f = list(s["f"])
        f[10] = str(rt).encode()
        new_rows.append((t, b",".join(f)))
        st["inserted_times"].append(t)
    if extra_lines:
        for t, ln in extra_lines.items():
            if t not in present and t not in sidecar:
                new_rows.append((t, ln))
                st["healed"] += 1
        new_rows.sort(key=lambda x: x[0])
    st["inserted"] = len(st["inserted_times"])
    if st["inserted"] > max_insert:
        raise Refused(f"{st['inserted']:,} bars would be inserted (limit {max_insert:,}) - not a normal replay window; "
                      f"raise --max-insert only if you mean it")

    merged = []
    j = 0
    for ln, p in zip(out, parsed):
        if p is not None:
            while j < len(new_rows) and new_rows[j][0] < p["t"]:
                merged.append(new_rows[j][1])
                j += 1
        merged.append(ln)
    merged.extend(x[1] for x in new_rows[j:])

    if sum(1 for ln in merged if ln.strip()) < st["master_rows"]:
        raise Refused("internal check: the merged file has fewer rows than the input - refusing to write")
    new = eol.join([head] + merged) + (eol if ends else b"")    # a missing final newline stays missing
    return new, st


# ---------------------------------------------------------------------------------------------
# the atomic, race-aware file update
# ---------------------------------------------------------------------------------------------
def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _count_rows(b):
    _h, rows, _e, _n = _split_lines(b)
    return sum(1 for ln in rows if ln.strip())


def _write_tmp(tmp, data):
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    if _count_rows(_read(tmp)) != _count_rows(data):         # read back and count
        raise Refused("temp file did not read back with the same row count - nothing replaced")


def _backup(path, raw, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = os.path.join(backup_dir, os.path.basename(path) + ".pre-repair-" + stamp)
    n = 1
    while os.path.exists(bak):
        n += 1
        bak = os.path.join(backup_dir, os.path.basename(path) + ".pre-repair-" + stamp + f"-{n}")
    with open(bak, "wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    old = sorted(glob.glob(os.path.join(backup_dir, os.path.basename(path) + ".pre-repair-*")))
    for stale in old[:-KEEP_BACKUPS]:
        try:
            os.remove(stale)
        except OSError:
            pass
    return bak


def _extra_tail_ok(raw, cur):
    """True when `cur` is `raw` plus whole appended lines only."""
    return len(cur) > len(raw) and cur.startswith(raw) and cur.endswith(b"\n") and (
        raw == b"" or raw.endswith(b"\n"))


def update_file(path, sidecar, backup_dir=None, dry_run=False, max_price_diff_pct=DEFAULT_MAX_PRICE_DIFF_PCT,
                max_insert=DEFAULT_MAX_INSERT, max_attempts=8, sleep=time.sleep):
    """Merge the sidecar into `path`. Returns the stats dict (plus 'backup' and 'wrote')."""
    backup_dir = backup_dir or os.path.join(os.path.dirname(os.path.abspath(path)), "_backups")
    tmp = path + ".repair.tmp"
    bak = None
    for attempt in range(max_attempts):
        raw = _read(path)
        merged, st = merge_bytes(raw, sidecar, max_price_diff_pct, max_insert)
        st["wrote"] = False
        st["backup"] = None
        if dry_run or merged == raw:
            return st
        try:
            _write_tmp(tmp, merged)
            if _hook_before_final_check:
                _hook_before_final_check(path)
            # carry over rows the indicator appended while we were merging
            restart = False
            for _ in range(6):
                cur = _read(path)
                if cur == raw:
                    break
                if _extra_tail_ok(raw, cur):
                    merged = merged + cur[len(raw):]
                    raw = cur
                    _write_tmp(tmp, merged)
                    continue
                restart = True
                break
            else:
                restart = True
            if restart:
                sleep(0.2)
                continue
            if _count_rows(merged) < _count_rows(raw):
                raise Refused("result would have fewer rows than the input - nothing written")
            if bak is None:
                bak = _backup(path, raw, backup_dir)
            link = path + ".premerge"
            try:
                if os.path.exists(link):
                    os.remove(link)
                os.link(path, link)
            except OSError:
                link = None                                    # no hard links here: the carry-over loop still applies
            if _hook_before_replace:
                _hook_before_replace(path)
            try:
                os.replace(tmp, path)
            except PermissionError:
                if link:
                    _rm(link)
                sleep(0.5)
                continue
            st["wrote"] = True
            st["backup"] = bak
            if link:
                lost = _read(link)
                _rm(link)
                if len(lost) > len(raw) and lost.startswith(raw):
                    # an append landed on the old file after our last check: put those rows back
                    tail = lost[len(raw):]
                    lines = {}
                    for ln in tail.split(b"\n"):
                        ln = ln.rstrip(b"\r")
                        p = _parse(ln) if ln.strip() else None
                        if p:
                            lines[p["t"]] = ln
                    if lines:
                        # one more merge pass over the NEW file inserts them (insert-only, in time order)
                        st["healed"] = len(lines)
                        st["healed_ok"] = _heal(path, lines, max_attempts, sleep)
            return st
        finally:
            if os.path.exists(tmp):
                _rm(tmp)
    raise Refused(f"could not replace {path} after {max_attempts} attempts (file kept changing / locked) - nothing written")


def _heal(path, lines, max_attempts, sleep):
    """Insert exact master rows (time-ordered, only if absent) that a replace race lost. Returns True when done."""
    tmp = path + ".repair.tmp"
    for _ in range(max_attempts):
        raw = _read(path)
        merged, st = merge_bytes(raw, {}, extra_lines=lines)
        if merged == raw:
            return True
        _write_tmp(tmp, merged)
        cur = _read(path)
        if cur != raw:
            if _extra_tail_ok(raw, cur):
                merged = merged + cur[len(raw):]
                _write_tmp(tmp, merged)
            else:
                sleep(0.2)
                continue
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            sleep(0.5)
        finally:
            if os.path.exists(tmp):
                _rm(tmp)
    return False


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------
# reporting + CLI
# ---------------------------------------------------------------------------------------------
def summarize(sym, st, side_bad, dry_run, sidecar_path):
    L = []
    pre = "DRY RUN  " if dry_run else ""
    L.append(f"{pre}{sym}: master {st['master_rows']:,} rows | sidecar {st['sidecar_bars']:,} bars"
             + (f" ({side_bad} malformed skipped)" if side_bad else ""))
    L.append(f"  reach (oldest sidecar bar): {_et_str(st['reach'])}   newest: {_et_str(st['sidecar_last'])}")
    L.append(f"  bars repaired: {st['repaired']:,}"
             + (f"   earliest {_et_str(min(st['repaired_times']))}   latest {_et_str(max(st['repaired_times']))}"
                if st["repaired_times"] else ""))
    L.append(f"  bars inserted: {st['inserted']:,}"
             + (f" ({st['inserted_unknown_flow']:,} kept as rt=3: traded, replay saw no tick)"
                if st["inserted_unknown_flow"] else "")
             + (f"   earliest {_et_str(min(st['inserted_times']))}   latest {_et_str(max(st['inserted_times']))}"
                if st["inserted_times"] else ""))
    L.append(f"  left alone: {st['skip_has_flow']:,} already carry buy/sell, {st['skip_no_ticks']:,} replay bars had no ticks, "
             f"{st['skip_price']:,} price mismatch")
    if st["repaired"] and st["vol_sum"]:
        L.append(f"  repaired flow / volume: {st['flow_sum'] / st['vol_sum']:.2f} (1.00 = every contract classified)")
    if st.get("healed"):
        L.append(f"  healed: {st['healed']} row(s) an indicator append lost to the replace race were put back")
    if dry_run:
        L.append("  nothing written (dry run)")
    elif st.get("wrote"):
        L.append(f"  written. backup: {st['backup']}")
    else:
        L.append("  nothing to change - file untouched")
    return "\n".join(L)


def run_one(sym, master, sidecar_path, dry_run, backup_dir, max_pct, max_insert, out=print):
    if not os.path.exists(master):
        raise BadInput(f"master not found: {master}")
    if not os.path.exists(sidecar_path):
        raise BadInput(f"sidecar not found: {sidecar_path} - reload the chart with Tick Replay on first")
    side, bad = read_sidecar(sidecar_path)
    age_h = (time.time() - os.path.getmtime(sidecar_path)) / 3600.0
    if age_h > 36:
        out(f"  note: {sym} sidecar is {age_h:.0f} h old (merging is idempotent, but it is not from today's load)")
    st = update_file(master, side, backup_dir, dry_run, max_pct, max_insert)
    out(summarize(sym, st, bad, dry_run, sidecar_path))
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description="Merge a Tick Replay sidecar into the 10s capture files.")
    ap.add_argument("--sym", action="append", help="NQ / ES (repeatable; default both)")
    ap.add_argument("--ohlc-dir", default=DEFAULT_OHLC_DIR, help="folder holding <SYM>_10s.csv")
    ap.add_argument("--replay-dir", help="folder holding <SYM>_10s_replay.csv (default <ohlc-dir>\\replay)")
    ap.add_argument("--master", help="explicit master file (with --sidecar; overrides --sym)")
    ap.add_argument("--sidecar", help="explicit sidecar file")
    ap.add_argument("--backup-dir", help="default <ohlc-dir>\\_backups")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing (not even a backup)")
    ap.add_argument("--max-price-diff-pct", type=float, default=DEFAULT_MAX_PRICE_DIFF_PCT)
    ap.add_argument("--max-insert", type=int, default=DEFAULT_MAX_INSERT)
    a = ap.parse_args(argv)

    jobs = []
    if a.master or a.sidecar:
        if not (a.master and a.sidecar):
            print("--master and --sidecar go together", file=sys.stderr)
            return 3
        jobs.append((os.path.basename(a.master), a.master, a.sidecar))
    else:
        replay = a.replay_dir or os.path.join(a.ohlc_dir, "replay")
        for sym in (a.sym or DEFAULT_SYMS):
            sym = sym.upper()
            jobs.append((sym, os.path.join(a.ohlc_dir, f"{sym}_{PERIOD}.csv"),
                         os.path.join(replay, f"{sym}_{PERIOD}_replay.csv")))
    rc = 0
    for sym, master, side in jobs:
        try:
            run_one(sym, master, side, a.dry_run, a.backup_dir or os.path.join(os.path.dirname(os.path.abspath(master)), "_backups"),
                    a.max_price_diff_pct, a.max_insert)
        except Refused as e:
            print(f"{sym}: REFUSED - {e}", file=sys.stderr)
            rc = max(rc, 2)
        except BadInput as e:
            print(f"{sym}: {e}", file=sys.stderr)
            rc = max(rc, 3)
    return rc


if __name__ == "__main__":
    sys.exit(main())
