"""Which strategies the recover watchdog is HOLDING BACK for a person, for the NT8 board's 'NEEDS YOU' banner.

WHY (2026-10-09). On 10-08 a feed flap made NinjaTrader switch NOISE and ENGU-Q off with a NOISE MNQ short
still open. From then on nt_recover.ps1 refused every restart ('STOP: the account is holding a position
while strategies are down') -- correctly, a strategy starting flat would leave that short unmanaged -- but
the only place that said so was C:\\EdgeLog\\nt_recover.log. The board showed '0 / 0 live' and nobody knew a
decision was waiting. This module turns the watchdog's last word into one list that rides in
meta/nt_bridge as "held_back":

  [{strategy, instrument, side, qty, avg, stop, since, reason}]   -- [] when nothing is held

Two sources, both required to agree:
  * the log: the most recent verdict line wins. 'STOP: ...' / 'HELD BACK for a person: ...' hold;
    'healthy: ...', 'RECOVERED: ...', 'PARTIAL' for the started ones, or ENGU-Q adopting its own trade clear.
  * the bridge's live positions: a held item is dropped as soon as the account is flat on its contract,
    so a hand flatten clears the banner on the next publish instead of the next watchdog pass. When the
    bridge is down (night mode, NinjaTrader closed) the log alone decides.
Pure functions + one reader; never raises (the publisher must never fail on this).
"""
import json
import os
import re
from datetime import datetime

LOG = os.path.join(os.environ.get("EDGELOG_HOME") or r"C:\EdgeLog", "nt_recover.log")
TAIL_BYTES = 400_000                 # about two days of passes; the file itself is many MB

# Mirrors $stratRoot in nt_recover.ps1: the contract root each strategy trades.
STRAT_ROOT = {"EdgeLogNOISE": "MNQ", "EdgeLogENGUQ1m": "NQ"}
SHORT_NAME = {"EdgeLogNOISE": "NOISE", "EdgeLogENGUQ1m": "ENGU-Q"}

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})  (.*)$")
_HOLD = ("STOP: the account is holding a position", "HELD BACK for a person:")
_CLEAR = ("healthy:", "RECOVERED:", "the account holds ENGU-Q's own saved trade")


def _root(instrument):
    return (str(instrument or "").split(" ")[0] or "?").upper()


def _iso(stamp):
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").astimezone().isoformat(timespec="seconds")
    except ValueError:
        return stamp


def last_verdict(lines):
    """-> (kind, first_stamp, positions, held_names) from the log lines, newest verdict wins.
    kind: 'hold' | 'clear' | None. first_stamp is when the current unbroken run of holds began."""
    kind, first, positions, names = None, None, [], []
    for i, raw in enumerate(lines):
        m = _TS.match(raw.rstrip("\r\n"))
        if not m:
            continue
        stamp, msg = m.groups()
        if msg.startswith(_HOLD):
            pos = []
            for nxt in lines[i + 1:i + 4]:                       # the position JSON is logged on the next line
                n = _TS.match(nxt.rstrip("\r\n"))
                body = (n.group(2) if n else nxt).strip()
                if body.startswith("{"):
                    try:
                        pos = list(json.loads(body).get("positions") or [])
                    except ValueError:
                        pos = []
                    break
            if msg.startswith("HELD BACK"):
                held = msg.split(":", 1)[1].split(" - ", 1)[0]
                nm = [s.strip() for s in held.split(",") if s.strip()]
            else:
                nm = list(STRAT_ROOT)                             # STOP holds every strategy
            if kind != "hold":
                first = stamp
            kind, positions, names = "hold", pos, nm
        elif msg.startswith(_CLEAR):
            kind, first, positions, names = "clear", None, [], []
    return kind, first, positions, names


def build(lines, live_positions=None, orders=None):
    """Pure. live_positions: the bridge's list, or None when the bridge is down (then the log decides)."""
    kind, first, positions, names = last_verdict(lines)
    if kind != "hold":
        return []
    live_roots = None if live_positions is None else {_root(p.get("instrument")) for p in live_positions}
    out = []
    for p in positions:
        root = _root(p.get("instrument"))
        if live_roots is not None and root not in live_roots:
            continue                                              # flat on that contract now: nothing to decide
        mine = [s for s in names if STRAT_ROOT.get(s) == root] or (names if root not in STRAT_ROOT.values() else [])
        side = str(p.get("side") or "").upper()
        stop = None
        for o in orders or []:
            if _root(o.get("instrument")) == root and "stop" in str(o.get("type") or "").lower() and o.get("stop"):
                stop = o.get("stop")
                break
        who = ", ".join(SHORT_NAME.get(s, s) for s in mine) or "every strategy"
        qty = p.get("qty")
        out.append({
            "strategy": who,
            "instrument": root,
            "side": side,
            "qty": qty,
            "avg": p.get("avg_price"),
            "stop": stop,
            "since": _iso(first) if first else None,
            "reason": (f"{who} is off: the account holds a {side.lower()} of {qty} {root} that no strategy is managing"
                       f" - flatten it, or turn {who} on knowing it will not manage this trade."),
        })
    return out


def read_tail(path=LOG, n=TAIL_BYTES):
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - n))
            return f.read().decode("utf-8", errors="replace").splitlines()[1:]   # first line may be cut
    except OSError:
        return []


def state(live_positions=None, orders=None):
    """Never raises: [] on any failure."""
    try:
        return build(read_tail(), live_positions, orders)
    except Exception:
        return []
