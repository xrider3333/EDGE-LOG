# nt_config_reconcile.py -- is NinjaTrader running the config we THINK it is?
#
# WHY THIS EXISTS (2026-08-16). The paper book only means something if the strategy
# NinjaTrader is actually executing matches the strategy the engine is shadow-running.
# Until the bridge grew GET /strategy/params (v2.1) nothing outside NinjaTrader could SEE
# the live values, so a drift between the two was invisible by construction -- you would
# only find it by opening each strategy's dialog by hand and reading it off the screen.
#
# This compares, per leg:
#     api/paper.py's PAPER_LEGS[key]['params']   (what the engine shadow-runs)
# vs  GET /strategy/params?name=<NinjaScript>    (what NinjaTrader has loaded right now)
#
# It does NOT touch anything. Read-only on both sides.
#
# NAME MAPPING IS EXPLICIT AND HAND-MAINTAINED, on purpose. The NinjaScript property
# names (Lookback, BandMultLong, StopK) and the engine param names (lookback,
# band_mult_long, stop_k) are different vocabularies, and fuzzy-matching them would
# eventually pair two knobs that merely look alike. A missing mapping is reported as
# UNMAPPED rather than silently skipped -- during development a wrong guess ('act_r' for
# what is really 'act_R') produced a scary MISMATCH on a parameter that was in fact
# identical, which is exactly the kind of false alarm that teaches people to ignore the
# tool. If you add a knob to a strategy, add it here too.
#
# USAGE
#   python tools/nt_config_reconcile.py            # table, exit 1 if anything differs
#   python tools/nt_config_reconcile.py --json     # machine-readable
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = os.environ.get("EDGELOG_BRIDGE_URL", "http://127.0.0.1:8391")

# leg key -> the NinjaScript strategy instance name in NinjaTrader
# 2026-08-16: EdgeLogNOISE now runs the #231 crowned config WITH the live ML gate, so it
# reconciles against the NOISE_H_RF leg (identical base params to NOISE_225), not the old
# hand-built NOISE leg, which stays engine-only.
NT_NAME = {
    "NOISE_H_RF": "EdgeLogNOISE",
    # 2026-08-21: EdgeLogORBV2 was deleted from NinjaTrader on 08-17 and replaced by
    # EdgeLogORB230 (the run-#230 port that actually trades), so the mapping had been
    # reporting UNREADABLE against a ghost. Repointed + remapped to ORB230's own
    # property names, checked live via the bridge.
    "ORB":   "EdgeLogORB230",
    "ENGUQ": "EdgeLogENGUQ1m",
}

# leg key -> {NinjaScript property : engine param}. Case matters on the engine side --
# ENGU-Q really does use act_R and breakeven_R with a capital R.
PARAM_MAP = {
    "NOISE_H_RF": {"Lookback": "lookback", "BandMultLong": "band_mult_long",
                   "BandMultShort": "band_mult_short", "StopK": "stop_k"},
    "ORB":   {"OrBars": "or_bars", "StopFrac": "stop_frac",
              "BreakoutBuf": "breakout_buf", "PartialExitR": "partial_exit_R",
              "TrailBars": "trail_bars", "TargetR": "target_R",
              "AtrFilter": "atr_filter", "VpaceFilter": "vpace_filter",
              "SkipHolidays": "skip_holidays"},
    "ENGUQ": {"TlLen": "tl_len", "EmaLen": "ema_len", "BufAtr": "buf_atr",
              "MinBrk": "min_brk", "AtrLen": "atr_len", "VolMult": "vol_mult",
              "StopMult": "stop_mult", "ActR": "act_R", "TrailFrac": "trail_frac",
              "BreakevenR": "breakeven_R"},
}

# Knobs that exist on the NinjaScript side with no engine counterpart, by design.
# Listed so they show as INFO instead of UNMAPPED noise.
NT_ONLY = {"Qty", "UseStop",
           # the live ML-gate knobs (2026-08-16) -- NT-side plumbing for the bouncer
           # call, with no engine param counterpart by design
           "GateEnabled", "GateUrl", "GateTimeoutMs",
           # Short Veto knobs (2026-08-21): EdgeLogNOISE carries the crowned run-#241
           # filter DEFAULT OFF, while its reconcile target NOISE_H_RF runs the plain
           # #231 core (no daytype keys), so these stay NT-only here. The crowned
           # NOISE_SBS leg is engine-only (no NT instance yet); if EdgeLogNOISE is
           # ever flipped to SkipBotShort=true, repoint NT_NAME/PARAM_MAP at NOISE_SBS
           # and map these two properly.
           "SkipBotShort", "DaytypeLo",
           # LimitAtr (2026-08-21): the NinjaScript ENGUQ port carries limit-entry
           # support (written for the L50 research) while the #226 market-entry leg it
           # reconciles against has no such engine key. 0 on the strategy = disabled =
           # exactly that leg, so it is NT-only here; if an ENGUQ_L50 NT row ever goes
           # live, map it properly against that leg instead.
           "LimitAtr"}


def _norm(v):
    """Compare 1.0 to '1' as equal, and 'Both' to 'both' as equal, without making
    genuinely different values look the same. Bools are handled FIRST: Python's
    float(True) is 1.0 while NinjaTrader reports the string 'True', so without this
    a genuinely matching boolean knob printed engine=True / NT=True and still read
    MISMATCH (found 2026-08-21 on ORB's skip_holidays)."""
    if isinstance(v, bool):
        return str(v).lower()
    s = str(v).strip().lower()
    if s in ("true", "false"):
        return s
    try:
        return round(float(v), 6)
    except (TypeError, ValueError):
        return s


def fetch_live(nt_name):
    url = "%s/strategy/params?name=%s" % (BASE.rstrip("/"), nt_name)
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        try:
            return None, json.loads(e.read().decode("utf-8")).get("error", "HTTP %d" % e.code)
        except Exception:
            return None, "HTTP %d" % e.code
    except Exception as e:
        return None, "%s: %s" % (type(e).__name__, e)


def main():
    ap = argparse.ArgumentParser(description="Compare engine leg params vs NinjaTrader's live params.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    from api.paper import PAPER_LEGS
    legs = {l["key"]: l for l in PAPER_LEGS}

    rows, problems = [], []
    for key, nt_name in NT_NAME.items():
        live, err = fetch_live(nt_name)
        if err:
            problems.append("%s: could not read %s (%s)" % (key, nt_name, err))
            rows.append({"leg": key, "param": "-", "engine": "-", "nt": "-", "status": "UNREADABLE"})
            continue
        live_vals = {p["name"]: p["value"] for p in live.get("params", [])}
        eng = legs.get(key, {}).get("params", {}) or {}
        mapping = PARAM_MAP.get(key, {})

        for nt_prop, eng_key in mapping.items():
            if nt_prop not in live_vals:
                rows.append({"leg": key, "param": eng_key, "engine": eng.get(eng_key, "-"),
                             "nt": "(not on strategy)", "status": "UNMAPPED"})
                problems.append("%s: %s is mapped but NinjaTrader has no such property" % (key, nt_prop))
                continue
            ev, nv = eng.get(eng_key, "(absent)"), live_vals[nt_prop]
            if eng_key not in eng:
                rows.append({"leg": key, "param": eng_key, "engine": "(absent)", "nt": nv, "status": "UNMAPPED"})
                problems.append("%s: engine has no param named %r (check PARAM_MAP spelling)" % (key, eng_key))
                continue
            same = _norm(ev) == _norm(nv)
            rows.append({"leg": key, "param": eng_key, "engine": ev, "nt": nv,
                         "status": "OK" if same else "MISMATCH"})
            if not same:
                problems.append("%s: %s engine=%s but NinjaTrader=%s" % (key, eng_key, ev, nv))

        for extra in sorted(set(live_vals) - set(mapping) - NT_ONLY):
            rows.append({"leg": key, "param": extra, "engine": "(no counterpart)",
                         "nt": live_vals[extra], "status": "UNMAPPED"})
            problems.append("%s: NinjaTrader property %r has no entry in PARAM_MAP" % (key, extra))

    if args.json:
        print(json.dumps({"rows": rows, "problems": problems, "ok": not problems}, indent=2))
    else:
        w = {c: max(len(c), max([len(str(r[c])) for r in rows] or [0])) for c in
             ("leg", "param", "engine", "nt", "status")}
        print("  ".join(c.upper().ljust(w[c]) for c in ("leg", "param", "engine", "nt", "status")))
        print("-" * (sum(w.values()) + 8))
        last = None
        for r in rows:
            if last and r["leg"] != last:
                print()
            print("  ".join(str(r[c]).ljust(w[c]) for c in ("leg", "param", "engine", "nt", "status")))
            last = r["leg"]
        print()
        if problems:
            print("PROBLEMS (%d):" % len(problems))
            for p in problems:
                print("  - " + p)
        else:
            print("All mapped parameters agree: the engine and NinjaTrader are running the same config.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
