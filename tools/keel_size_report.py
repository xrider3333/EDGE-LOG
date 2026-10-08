r"""tools/keel_size_report.py -- what KEEL sized each NOISE entry on one day, against what the
fixed rule alone would have sized it (MANAGER #76, owner GL 2.6 decision pending).

WHY. KEEL v12's 10-05 evening states read fast-trust (t_fast) -1.33 (NOISE_382) / -1.23
(NOISE_422_KEEL), below the -0.5 shade line for the first time. From 10-06 the SHADE branch
(size = clip(1 - 1.0 x score, 0.5, 1.5), against the model's own score) replaces the fixed tilts
alone on the live Webull NOISE leg. This report shows, per entry, the size actually used, which
branch decided it, and the size v12's fixed tilts alone give the same entry -- recomputed
offline with the engine's own functions on the box's own bar cache.

READ-ONLY. With --box it reads the box over ONE kind of call -- `ssh ... cat/grep/zcat` (the
same read-only key every tool uses); the bar caches, KEEL summaries and (with --rescore) the
KEEL state files are copied into a temp dir that is deleted afterwards. Nothing on the box or
under EDGELOG_HOME is ever written; no Firestore, no Webull.

WHAT IT READS for --date D:
  signals     cloud_signal/signals.csv (live) and cloud_signal/shadow/signals.csv (shadow):
              the day's ENTRY rows on NOISE legs with a KEEL block (NOISE_382, NOISE_422_KEEL,
              and NOISE_422_FIXED as a cross-check of the fixed rule).
  log         logs/cloud_signal.log* (rotated and .gz too): "KEEL ENTRY" lines -- written by
              the engine from the KEEL ENTRY EXTRAS deploy on (api/cloud_signal.py).
  state       cloud_signal/keel/<leg>_v12_summary.json: t_fast_now / trust_now / data_through.
              A summary whose data_through is BEFORE D is the state that sized D's entries
              (the nightly build runs ~18:30 ET); a later one has been rebuilt since, and its
              t_fast is not D's.
  bars        ohlc/QQQ_5m.csv (+ QQQ_5m_backfill.csv when present) and ohlc/QQQ_1d.csv.

WORKS BEFORE THE EXTRAS DEPLOY. Re-scoring is ON by default (--no-rescore turns it off): while
the state in effect on the day is still the one on disk, each entry is re-scored offline with
it (cloud_signal._keel_size_for_entry, the engine's own call) and the exact branch / t_fast /
trust / score are reported (marked "rescored"). Otherwise, on a day whose rows carry no
keel_branch column and whose log has no KEEL ENTRY lines, the branch is INFERRED (marked "?")
from the state summary in effect AND the sizes -- the shade branch also needs a non-zero model
score, so t_fast below the line alone does not mean it fired: below the line, KEEL's size
equal to the fixed rule's -> "fixed-only?" (score 0: shade gives clip(1 - k x z) x fixed,
which equals fixed only at z ~ 0), different -> "shade?", no fixed size to compare ->
"shade-line?" (not counted as fired); above the line, equal -> "fixed-only?", else "trust?". Every fixed-rule size is recomputed by replaying the leg's decision exactly as the
engine does (closed_arrays -> leg_decision_trades -> _keel_fixed_size_for_entry at the entry
bar); the bar cache may have been revised since the day, so a recomputed size can differ from
what the engine saw -- the logged one (keel_fixed_size, after the deploy) is the record.

WHEN TO RUN IT (review 10-05). Re-scoring needs the state that sized the day, and the box
rebuilds the KEEL state at ~18:30 ET. Run the day's report AFTER the session closes and BEFORE
~18:30 ET (for 10-06: `--date 2026-10-06 --box` between 16:00 and 18:30 ET); run later, the
pre-deploy rows show an inferred ("?") or "unknown" branch instead of the exact one.

Usage:
  python tools/keel_size_report.py --date 2026-10-06 --box           (the box, over ssh)
  python tools/keel_size_report.py --date 2026-10-06 --box --no-rescore   (skip the state pull)
  python tools/keel_size_report.py --date 2026-10-06 --home C:\EdgeLog_copy   (a local copy)
"""
import argparse
import csv
import datetime as _dt
import glob
import gzip
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HOST = "ubuntu@163.192.117.12"
SSH_KEY = os.path.expanduser(os.path.join("~", ".ssh", "edgelog_oracle"))
BOX_HOME = "/home/ubuntu/edgelog"
SSH_TIMEOUT_SEC = 120
SIZE_TOL = 0.01                       # the engine's KEEL_DIFF_TOL: sizes closer than this agree

KEEL_LOG_RE = re.compile(r"\[cloud-signal\] KEEL ENTRY (.*)$")
_KV_RE = re.compile(r"(\w+)=(\S+)")


# -- where things are (a home laid out like the box's ~/edgelog) -------------------------------
def home_files(home):
    cs_dir = os.path.join(home, "cloud_signal")
    return {
        "live_signals": os.path.join(cs_dir, "signals.csv"),
        "shadow_signals": os.path.join(cs_dir, "shadow", "signals.csv"),
        "keel_dir": os.path.join(cs_dir, "keel"),
        "logs_dir": os.path.join(home, "logs"),
        "ohlc_dir": os.path.join(home, "ohlc"),
    }


def keel_legs():
    """{leg: (cfg, "live"/"shadow")} for every NOISE leg with a KEEL block, from the engine's
    own leg tables (so the report can never name a leg the engine does not run)."""
    from api import cloud_signal as cs
    out = {}
    for table, kind in ((cs.CROWN_LEGS, "live"), (cs.SHADOW_LEGS, "shadow")):
        for k, cfg in table.items():
            if k.startswith("NOISE") and cfg.get("keel"):
                out[k] = (cfg, kind)
    return out


# -- box pull (read-only ssh) -------------------------------------------------------------------
def _ssh_cmd(remote):
    exe = shutil.which("ssh") or "ssh"
    return [exe, "-i", SSH_KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=20", HOST, remote]


def _ssh_run(remote, run_cmd=None, binary=False):
    run_cmd = run_cmd or subprocess.run
    kw = {"capture_output": True, "timeout": SSH_TIMEOUT_SEC, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    r = run_cmd(_ssh_cmd(remote), **kw)
    out = r.stdout or b""
    if not binary and isinstance(out, bytes):
        out = out.decode("utf-8", "replace")
    return r.returncode, out


def pull_from_box(date, dest, rescore=False, run_cmd=None, log=print):
    """Copy what the report reads into `dest`, laid out like the box home. Read-only on the
    box: cat / grep / zcat / test only. Returns the list of what could not be read."""
    missing = []
    f = home_files(dest)
    for d in (os.path.dirname(f["live_signals"]), os.path.dirname(f["shadow_signals"]),
              f["keel_dir"], f["logs_dir"], f["ohlc_dir"]):
        os.makedirs(d, exist_ok=True)

    def _cat(remote_rel, local, optional=False, binary=True):
        q = shlex.quote(f"{BOX_HOME}/{remote_rel}")
        rc, out = _ssh_run(f"test -f {q} && cat {q}", run_cmd, binary=binary)
        if rc != 0:
            if not optional:
                missing.append(remote_rel)
            return False
        with open(local, "wb") as fh:
            fh.write(out if isinstance(out, bytes) else out.encode("utf-8"))
        return True

    # the day's signal rows (header + lines naming the date) -- the ledgers are long
    for rel, local in (("cloud_signal/signals.csv", f["live_signals"]),
                       ("cloud_signal/shadow/signals.csv", f["shadow_signals"])):
        q = shlex.quote(f"{BOX_HOME}/{rel}")
        rc, out = _ssh_run(f"test -f {q} && {{ head -1 {q}; grep -F {shlex.quote(date)} {q}; "
                           f"true; }}", run_cmd, binary=True)
        if rc != 0:
            missing.append(rel)
            continue
        with open(local, "wb") as fh:
            fh.write(out)
    # KEEL ENTRY lines from every cloud_signal log, rotated ones too
    logs = shlex.quote(f"{BOX_HOME}/logs")
    rc, out = _ssh_run(
        f"cd {logs} && {{ grep -h 'KEEL ENTRY' cloud_signal.log cloud_signal.log.1 "
        f"2>/dev/null; for g in cloud_signal.log.*.gz; do [ -f \"$g\" ] && zcat \"$g\" | "
        f"grep -h 'KEEL ENTRY'; done; true; }}", run_cmd, binary=True)
    if rc == 0:
        with open(os.path.join(f["logs_dir"], "cloud_signal.log"), "wb") as fh:
            fh.write(out)
    else:
        missing.append("logs/cloud_signal.log*")
    from api import cloud_signal as cs
    for leg, (cfg, _kind) in keel_legs().items():
        if cs.keel_mode(cfg.get("keel")) != cs.KEEL_MODE_LEARNED:
            continue                              # a fixed-mode leg has no state
        _cat(f"cloud_signal/keel/{leg}_v12_summary.json",
             os.path.join(f["keel_dir"], f"{leg}_v12_summary.json"), optional=True)
        if rescore:
            _cat(f"cloud_signal/keel/{leg}_v12_state.joblib",
                 os.path.join(f["keel_dir"], f"{leg}_v12_state.joblib"), optional=True)
    _cat("ohlc/QQQ_5m.csv", os.path.join(f["ohlc_dir"], "QQQ_5m.csv"))
    _cat("ohlc/QQQ_1d.csv", os.path.join(f["ohlc_dir"], "QQQ_1d.csv"), optional=True)
    _cat("ohlc/QQQ_5m_backfill.csv", os.path.join(f["ohlc_dir"], "QQQ_5m_backfill.csv"),
         optional=True)
    return missing


# -- readers ------------------------------------------------------------------------------------
def read_entries(path, date, legs):
    """The day's ENTRY rows on `legs`, as dicts (a missing file is [])."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return []
    out = []
    for r in rows:
        if r.get("event") != "ENTRY" or r.get("leg") not in legs:
            continue
        if str(r.get("ref_time") or "")[:10] != date:
            continue
        out.append(r)
    return out


def read_log_entries(logs_dir, date):
    """{(leg, entry time): {key: value}} from every "KEEL ENTRY" line in the cloud_signal
    logs under `logs_dir` (plain and .gz), for entries on `date`. The last line wins."""
    out = {}
    files = sorted(glob.glob(os.path.join(logs_dir, "cloud_signal.log*")))
    for p in files:
        try:
            if p.endswith(".gz"):
                with gzip.open(p, "rt", encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            else:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
        except OSError:
            continue
        for ln in text.splitlines():
            m = KEEL_LOG_RE.search(ln)
            if not m:
                continue
            kv = dict(_KV_RE.findall(m.group(1)))
            if str(kv.get("time") or "")[:10] != date:
                continue
            out[(kv.get("leg"), kv.get("time"))] = kv
    return out


def read_summary(keel_dir, leg):
    p = os.path.join(keel_dir, f"{leg}_v12_summary.json")
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def summary_in_effect(summary, date):
    """True when this summary's state is the one that sized `date`'s entries: its data ends
    BEFORE `date` (the nightly build after `date`'s close has not replaced it yet)."""
    dt = (summary or {}).get("data_through") or (summary or {}).get("last_nq_session")
    return bool(dt) and str(dt) < date


def _f(v):
    try:
        x = float(v)
        return x if x == x else None
    except (TypeError, ValueError):
        return None


# -- offline recompute (the engine's own functions) ---------------------------------------------
def recompute_entry(cs, leg, cfg, epoch_df, entry_time, side, paths, keel_cfg=None):
    """Replay the leg's decision for ONE entry exactly as the engine makes it and return
    {"fixed", "entry_bar", "how", and -- with `keel_cfg` -- "keel_size", "diag"}; None when
    the entry cannot be re-found in the bars (a revised bar, or a cache that no longer
    reaches the day)."""
    import pandas as pd
    quiet = lambda *a, **k: None  # noqa: E731
    T = pd.Timestamp(entry_time)
    if T.tzinfo is None:
        T = T.tz_localize(cs.TZ)
    grace = pd.Timedelta(seconds=cs.CLOSE_GRACE_SECONDS + 1)
    bar = pd.Timedelta(seconds=cs.TIMEFRAME_SECONDS["5m"])
    # decided at the close of the bar BEFORE the entry bar (decide_at_close), else at the
    # close of the entry bar itself
    for now in (T + grace, T + bar + grace):
        now_dt = now.to_pydatetime()
        arrays = cs.closed_arrays(epoch_df, now_dt, "5m", cs.leg_warmup_sessions(cfg))
        if arrays is None:
            continue
        trades, diff_arrays = cs.leg_decision_trades(cfg, arrays, leg, "5m", now_dt, paths,
                                                     False, log=quiet)
        for t in trades:
            if t.get("side") != side or t.get("entry_bar") is None:
                continue
            try:
                same = pd.Timestamp(t["entry_time"]) == T
            except (TypeError, ValueError):
                same = False
            if not same:
                continue
            fixed, fdiag = cs._keel_fixed_size_for_entry({"version": "v12", "mode": "fixed"},
                                                          diff_arrays, t["entry_bar"], log=quiet)
            out = {"fixed": float(fixed) if isinstance(fdiag, dict) else None,
                   "entry_bar": int(t["entry_bar"]),
                   "how": "probe" if t.get("probe_entry") else "closed bar"}
            if keel_cfg:
                ks, diag = cs._keel_size_for_entry(keel_cfg, diff_arrays, t["entry_bar"],
                                                   t["entry_time"], log=quiet)
                out["keel_size"], out["diag"] = ks, diag
            return out
    return None


# -- the report ---------------------------------------------------------------------------------
def build_report(home, date, rescore=False, recompute=True, log=print):
    """Rows (one per NOISE KEEL entry on `date`) + the plain-words verdict, from a home laid
    out like the box's ~/edgelog."""
    from api import cloud_signal as cs
    from augur_engine import ml_keel as K
    f = home_files(home)
    legs = keel_legs()
    shade_t = K.CFG["v12"]["shade"]["t"]
    entries = (read_entries(f["live_signals"], date, legs)
               + read_entries(f["shadow_signals"], date, legs))
    logged = read_log_entries(f["logs_dir"], date)
    summaries = {leg: read_summary(f["keel_dir"], leg) for leg, (cfg, _k) in legs.items()
                 if cs.keel_mode(cfg.get("keel")) == cs.KEEL_MODE_LEARNED}
    paths = cs._paths(home=home)
    epoch_df = None
    if recompute and entries:
        try:
            epoch_df = cs.historical_bars("5m", paths)
        except Exception as e:
            log(f"[keel-report] bar cache unreadable ({type(e).__name__}: {e}) -- no recompute")
    rows = []
    for r in sorted(entries, key=lambda r: (r.get("ref_time") or "", r.get("leg") or "")):
        leg = r["leg"]
        cfg, kind = legs[leg]
        mode = cs.keel_mode(cfg.get("keel"))
        when = r.get("ref_time") or ""
        lg = logged.get((leg, when)) or {}
        row = {"leg": leg, "kind": kind, "mode": mode, "time": when, "side": r.get("side"),
               "trade_id": r.get("trade_id") or "",
               "keel_size": _f(r.get("keel_size")), "size": _f(r.get("size")),
               "branch": "", "t_fast": None, "trust": None, "score": None, "src": "-",
               "fixed_logged": _f(r.get("keel_fixed_size")) if r.get("keel_fixed_size") not in
               (None, "") else _f(lg.get("fixed_size")),
               "fixed_recomputed": None, "how": "", "note": ""}
        if mode == cs.KEEL_MODE_FIXED:
            row["branch"], row["src"] = "fixed-leg", "rule"
            if row["fixed_logged"] is None:     # its used size IS the fixed rule's size
                row["fixed_logged"] = row["keel_size"]
        elif r.get("keel_branch"):
            row.update(branch=r["keel_branch"], t_fast=_f(r.get("keel_t_fast")),
                       trust=_f(r.get("keel_trust")), score=_f(r.get("keel_score")), src="row")
        elif lg.get("branch") and lg.get("branch") != "-":
            row.update(branch=lg["branch"], t_fast=_f(lg.get("t_fast")),
                       trust=_f(lg.get("trust")), score=_f(lg.get("score")), src="log")
        summ = summaries.get(leg)
        keel_cfg = None
        if (rescore and mode == cs.KEEL_MODE_LEARNED and not row["branch"]
                and summary_in_effect(summ, date)):
            sp = os.path.join(f["keel_dir"], f"{leg}_v12_state.joblib")
            if os.path.exists(sp):
                keel_cfg = {"version": "v12", "state_path": sp,
                            "summary_path": os.path.join(f["keel_dir"], f"{leg}_v12_summary.json")}
        if epoch_df is not None and len(epoch_df):
            try:
                rc = recompute_entry(cs, leg, cfg, epoch_df, when, r.get("side"), paths,
                                     keel_cfg=keel_cfg)
            except Exception as e:
                rc = None
                row["note"] = f"recompute failed: {type(e).__name__}: {e}"
            if rc:
                row["fixed_recomputed"], row["how"] = rc["fixed"], rc["how"]
                if keel_cfg and "diag" in rc:
                    diag = rc["diag"]
                    state, _s = cs._load_keel_state(keel_cfg["state_path"],
                                                    keel_cfg["summary_path"], log=lambda *_: None)
                    rule = (state or {}).get("cfg") or K.CFG["v12"]
                    row.update(branch=K.keel_branch(diag, rule) + " (rescored)", src="rescore")
                    if isinstance(diag, dict):
                        row.update(t_fast=_f(diag.get("t_fast")), trust=_f(diag.get("trust")),
                                   score=_f(diag.get("z")))
                    rks = _f(rc.get("keel_size"))
                    if rks is not None and row["keel_size"] is not None \
                            and abs(rks - row["keel_size"]) > SIZE_TOL:
                        row["note"] = (f"rescored size {rks:.3f} != used {row['keel_size']:.3f} "
                                       f"(bars revised since?)")
            elif not row["note"]:
                row["note"] = "entry not re-found in the bar cache (bars revised?)"
        if not row["branch"] and mode == cs.KEEL_MODE_LEARNED:
            fixed = row["fixed_logged"] if row["fixed_logged"] is not None else row["fixed_recomputed"]
            tf_now = _f((summ or {}).get("t_fast_now"))
            if summary_in_effect(summ, date) and tf_now is not None:
                row["t_fast"], row["trust"], row["src"] = tf_now, _f(summ.get("trust_now")), "state"
                known = fixed is not None and row["keel_size"] is not None
                same = known and abs(fixed - row["keel_size"]) <= SIZE_TOL
                if tf_now < shade_t:
                    # below the line, the shade branch still needs z != 0 -- it gives
                    # clip(1 - k z) x fixed, equal to the fixed size only at z ~ 0. So decide
                    # by the sizes; with none to compare, do not call it fired.
                    row["branch"] = ("fixed-only?" if same else "shade?") if known \
                        else "shade-line?"
                elif known:
                    row["branch"] = "fixed-only?" if same else "trust?"
                else:
                    row["branch"] = "?"
            else:
                row["branch"] = "unknown"
                if summ and not row["note"]:
                    row["note"] = (f"state rebuilt since (data_through "
                                   f"{summ.get('data_through')}) -- run with the day's state, "
                                   f"or after the extras deploy")
        rows.append(row)
    return rows, summaries, verdict(rows, date)


def _sizes(xs):
    return "/".join("?" if x is None else f"{x:g}" for x in xs)


def verdict(rows, date):
    """The one plain-words line: how often the shade branch fired, and what KEEL sized where
    the fixed rule would have sized something else."""
    learned = [r for r in rows if r["mode"] == "learned"]
    if not learned:
        return f"{date}: no KEEL-sized NOISE entries."

    def _fixed(r):
        return r["fixed_logged"] if r["fixed_logged"] is not None else r["fixed_recomputed"]

    def _part(rs):
        n_shade = sum(1 for r in rs if str(r["branch"]).startswith("shade")
                      and not str(r["branch"]).startswith("shade-line"))
        guessed = any(str(r["branch"]).endswith("?") for r in rs)
        unknown = sum(1 for r in rs if str(r["branch"]) in ("unknown", "?", ""))
        undecided = sum(1 for r in rs if str(r["branch"]).startswith("shade-line"))
        return n_shade, guessed, unknown, undecided

    live = [r for r in learned if r["kind"] == "live"]
    shadow = [r for r in learned if r["kind"] != "live"]
    main = live or shadow
    n_shade, guessed, unknown, undecided = _part(main)
    leg = main[0]["leg"]
    differ = [r for r in main if r["keel_size"] is not None and _fixed(r) is not None
              and abs(r["keel_size"] - _fixed(r)) > SIZE_TOL]
    text = (f"{date} {leg}: shade branch fired on {n_shade} of {len(main)} entries"
            + (" (inferred from the KEEL state)" if guessed else "")
            + (f", branch not known on {unknown} (no log line and the state was rebuilt since)"
               if unknown else "")
            + (f", {undecided} below the shade line with no fixed size to tell shade from "
               f"fixed-only" if undecided else "") + "; ")
    if differ:
        text += (f"KEEL sized {_sizes([r['keel_size'] for r in differ])} where the fixed rule "
                 f"would size {_sizes([_fixed(r) for r in differ])}")
    else:
        text += "KEEL sized every entry the same as the fixed rule would"
    if live and shadow:
        s_shade, _g, _u, _d = _part(shadow)
        text += f" (shadow {shadow[0]['leg']}: shade on {s_shade} of {len(shadow)})"
    return text + "."


def _cell(v, nd=3):
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def format_report(rows, summaries, verdict_line, date):
    out = io.StringIO()
    out.write(f"KEEL SIZE REPORT {date}\n")
    for leg, s in sorted(summaries.items()):
        if not s:
            out.write(f"  state {leg}: no summary\n")
            continue
        out.write(f"  state {leg}: data_through {s.get('data_through')}, built "
                  f"{s.get('built_at')}, t_fast_now {_cell(_f(s.get('t_fast_now')))}, "
                  f"trust_now {_cell(_f(s.get('trust_now')))}"
                  f" -- {'in effect on ' + date if summary_in_effect(s, date) else 'rebuilt since ' + date}\n")
    head = (f"{'leg':<16}{'time':<7}{'side':<7}{'used':>7}  {'branch':<20}{'t_fast':>8}"
            f"{'trust':>8}{'score':>8}{'fixed':>8}{'fixed*':>8}  {'src':<8}note")
    out.write(head + "\n" + "-" * len(head) + "\n")
    for r in rows:
        t = r["time"][11:16] if len(r["time"]) >= 16 else r["time"]
        out.write(f"{r['leg']:<16}{t:<7}{str(r['side'] or ''):<7}{_cell(r['keel_size']):>7}  "
                  f"{str(r['branch'] or '-'):<20}{_cell(r['t_fast'], 2):>8}"
                  f"{_cell(r['trust'], 2):>8}{_cell(r['score'], 2):>8}"
                  f"{_cell(r['fixed_logged']):>8}{_cell(r['fixed_recomputed']):>8}  "
                  f"{r['src']:<8}{r['note']}\n")
    if not rows:
        out.write("(no NOISE KEEL entries on this day)\n")
    out.write("used = keel_size on the signal row (the KEEL multiplier the order got); fixed = "
              "the fixed rule's size as logged (blank before the extras deploy); fixed* = "
              "recomputed offline from the bar cache; branch '?' = inferred from the state "
              "summary in effect and the sizes ('shade-line?' = below the shade line, no "
              "fixed size to compare).\n")
    out.write("VERDICT: " + verdict_line + "\n")
    return out.getvalue()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", required=True, help="the session day, YYYY-MM-DD")
    ap.add_argument("--box", action="store_true", help="read the box over read-only ssh")
    ap.add_argument("--home", default=None,
                    help="a local home laid out like the box's ~/edgelog (default EDGELOG_HOME)")
    ap.add_argument("--rescore", dest="rescore", action="store_true", default=True,
                    help="re-score entries offline with the KEEL state in effect, when still "
                         "on disk (the default)")
    ap.add_argument("--no-rescore", dest="rescore", action="store_false",
                    help="skip the re-score (and, with --box, the state pull)")
    ap.add_argument("--no-recompute", action="store_true", help="skip the offline fixed-size recompute")
    a = ap.parse_args(argv)
    try:
        _dt.date.fromisoformat(a.date)
    except ValueError:
        print("--date must be YYYY-MM-DD", file=sys.stderr)
        return 2
    tmp = None
    try:
        if a.box:
            tmp = tempfile.mkdtemp(prefix="keel_report_")
            missing = pull_from_box(a.date, tmp, rescore=a.rescore)
            for m in missing:
                print(f"[keel-report] could not read {m} on the box", file=sys.stderr)
            home = tmp
        else:
            from api import cloud_signal as cs
            home = a.home or cs.edgelog_home()
        rows, summaries, line = build_report(home, a.date, rescore=a.rescore,
                                             recompute=not a.no_recompute)
        print(format_report(rows, summaries, line, a.date), end="")
        return 0
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
