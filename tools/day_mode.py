"""RUNNER DAY MODE (OWNER 11-04, MANAGER #177): fewer runners claim work in the owner's day.

Between day_start and day_end (MST, America/Phoenix, no DST) only runner slots
1..day_runners claim NEW jobs; the others finish what they hold and then wait. Slot 1 = the
PRIMARY runner, slot N+1 = worker EDGELOG_WORKER=N. Outside the window every runner claims.

The schedule is a JSON file read on every claim attempt (mtime-cached), so flipping it needs no
restart:  C:\\EdgeLog\\runner_schedule.json  (env EDGELOG_RUNNER_SCHEDULE overrides)
    {"enabled": true, "day_start": "07:00", "day_end": "16:00", "day_runners": 2}
A missing or broken file = the defaults above (owner's pick). enabled=false = never hold.
A job already in progress (resumed orphan) is never held. Fail-open: any error = no hold.

CLI:  python tools/day_mode.py status | on | off | set --runners N [--start HH:MM --end HH:MM]
"""
import datetime as _dt
import json
import os
import sys

try:
    from zoneinfo import ZoneInfo
    MST = ZoneInfo("America/Phoenix")
except Exception:
    MST = _dt.timezone(_dt.timedelta(hours=-7), "MST")

DEFAULTS = {"enabled": True, "day_start": "07:00", "day_end": "16:00", "day_runners": 2}
_cache = {"mtime": None, "cfg": dict(DEFAULTS)}


def path():
    return os.environ.get("EDGELOG_RUNNER_SCHEDULE", r"C:\EdgeLog\runner_schedule.json")


def load():
    p = path()
    try:
        mt = os.path.getmtime(p)
    except OSError:
        return dict(DEFAULTS)
    if mt != _cache["mtime"]:
        cfg = dict(DEFAULTS)
        try:
            with open(p, encoding="utf-8") as fh:
                body = json.load(fh)
            if isinstance(body, dict):
                cfg.update({k: body[k] for k in DEFAULTS if k in body})
        except Exception:
            pass
        _cache.update(mtime=mt, cfg=cfg)
    return dict(_cache["cfg"])


def _hm(s):
    h, m = str(s).split(":")
    return int(h) * 60 + int(m)


def slot(worker_env=None):
    w = os.environ.get("EDGELOG_WORKER") if worker_env is None else worker_env
    try:
        return int(w) + 1 if w else 1
    except ValueError:
        return 1


def in_day(now=None, cfg=None):
    cfg = cfg or load()
    now = (now or _dt.datetime.now(MST)).astimezone(MST)
    t = now.hour * 60 + now.minute
    return _hm(cfg["day_start"]) <= t < _hm(cfg["day_end"])


def hold(now=None, worker_env=None, cfg=None):
    """True = this runner must not claim a NEW job right now."""
    try:
        cfg = cfg or load()
        if not cfg.get("enabled", True):
            return False
        return in_day(now, cfg) and slot(worker_env) > int(cfg["day_runners"])
    except Exception:
        return False


def _write(cfg):
    p = path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv) or ["status"]
    cfg = load()
    if a[0] == "on":
        cfg["enabled"] = True; _write(cfg)
    elif a[0] == "off":
        cfg["enabled"] = False; _write(cfg)
    elif a[0] == "set":
        for flag, key in (("--runners", "day_runners"), ("--start", "day_start"), ("--end", "day_end")):
            if flag in a:
                v = a[a.index(flag) + 1]
                cfg[key] = int(v) if key == "day_runners" else v
        _write(cfg)
    print("day mode %s: %s-%s MST, %s runner(s) claim; now %s (%s)" % (
        "ON" if cfg["enabled"] else "OFF", cfg["day_start"], cfg["day_end"], cfg["day_runners"],
        _dt.datetime.now(MST).strftime("%H:%M"), "DAY" if in_day(cfg=cfg) else "night"))


if __name__ == "__main__":
    main()
