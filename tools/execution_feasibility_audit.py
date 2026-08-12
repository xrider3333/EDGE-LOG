"""PRE-CROWN GATE: can this exact config actually be TRADED, as backtested?

The question every crowning must now answer, per decision the engine makes:

    "Does every input exist at the moment of THIS fill?"

Two real leaks got past walk-forward, lockbox and cross-instrument transfer because
all of those re-run the same engine -- a look-ahead is invisible to them:
  * 2026-08-10  ML GATE scored trades using the entry bar's close on open-filled bars.
  * 2026-08-11  ORB touch-entry fills at the range edge INTRABAR but gates the trade on
                that bar's FINISHED volume. 91% of ORB #125's edge was that gap.

This tool encodes the 2026-08-11 audit of all 60 strategy files so a session can check
a config BEFORE crowning it. Verdicts:

  LEAK   the config uses information that does not exist at fill time -- results are
         not live-achievable. Do not crown. An honest alternative is suggested.
  MILD   an intrabar SEQUENCING assumption (e.g. trail raised with this bar's high,
         then tested against this bar's low). Not future information, but a modeling
         choice -- state it when reporting.
  CLEAN  every input exists when it is used.

Usage:
  python3.13.exe tools/execution_feasibility_audit.py --strategy ORB_3_0.py \
      --params "or_bars=1,vol_filter=1.25,close_confirm=False"
  python3.13.exe tools/execution_feasibility_audit.py --all       # whole library
"""
import argparse
import os
import sys

# ── the ORB family: verdict depends on PARAMS, not just the file ──────────────
# touch entry (close_confirm off / entry_mode 'touch') + a volume filter = the leak.
_ORB_TOUCH_FAMILY = {
    "ORB_2_0.py", "ORB_3_0.py", "ORB_3_1.py", "ORB_3_2.py", "ORB_3_3.py",
    "ORB_3_0_BE.py", "ORB_3_0_BEAV.py", "ORB_3_0_BET.py", "ORB_3_0_CC.py",
    "ORB_3_0_ENS.py", "ORB_3_0_ENSL.py", "ORB_3_0_LATE.py", "ORB_3_0_MM.py",
    "ORB_3_0_PYR.py", "ORB_3_0_RE.py", "ORB_3_1_125.py",
}

# same-bar trail/breakeven ordering — documented, not future information
_MILD = {
    "ENGUQ_1M_1_0.py", "ENGUQ_5M_1_0.py", "ENGUQ_15M_1_0.py", "ENGUQ_1M_ETH_1_0.py",
    "ENGUQ_1M_ENS_1_0.py", "ENGUQ_1M_CTX_1_0.py", "ENGUDQ_1M_1_0.py",
    "REVERT_1_0.py", "REVERT_1_1.py", "REVERT_1_2.py",
    "ENGU_1_3_1.py", "ENGU_1_3_2.py", "ENGU_1_3_3.py", "ENGU_1_3_4.py", "ENGU_1_3_5.py",
}

_MILD_NOTE = ("trailing stop / breakeven is raised using THIS bar's high and then tested "
              "against THIS bar's low in the same step (mirrored on shorts) - assumes the "
              "high printed first. Priced on ENGU-Q #149: the live-realistic lagged trail "
              "earns MORE (+$31k/16.1y), so the engine book is CONSERVATIVE there.")

_CLEAN_NOTE = {
    "NOISE_1_0.py": "signal at a bar's CLOSE, fill at the NEXT bar's OPEN - the honest convention.",
    "ORB_1_0.py": "touch entry, but no volume filter - nothing end-of-bar gates the fill.",
    "ORB_FADE_1_0.py": "trigger AND fill both at the bar's close.",
    "ORB_3_1_125C.py": "#125's knobs with the decision moved to the bar close - the live-legal twin.",
    "TTIBS_1_0.py": "daily bars; next-session-open or same-day-close fills.",
}


def _parse_params(s):
    out = {}
    for part in (s or "").split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        k, v = part.split("=", 1)
        k, v = k.strip(), v.strip()
        low = v.lower()
        if low in ("true", "false"):
            out[k] = (low == "true")
        else:
            try:
                out[k] = float(v) if "." in v else int(v)
            except ValueError:
                out[k] = v
    return out


def _strategy_defaults(name):
    """Read DEFAULT_PARAMS off the plugin so an omitted knob is judged at its real default."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, root)
        from augur_engine.strategies import load_strategy
        mod = load_strategy(name)
        dp = getattr(mod, "DEFAULT_PARAMS", {}) or {}
        return {k: (v or {}).get("default") for k, v in dp.items()}
    except Exception:
        return {}


def audit(name, params=None):
    """-> (verdict, reason, fix)"""
    name = os.path.basename(str(name))
    if not name.endswith(".py"):
        name += ".py"
    p = dict(_strategy_defaults(name))
    p.update(params or {})

    if name in _ORB_TOUCH_FAMILY:
        volf = float(p.get("vol_filter", 0) or 0)
        # ORB_3_0_CC exposes entry_mode instead of close_confirm
        mode = str(p.get("entry_mode", "") or "").lower()
        cc = bool(p.get("close_confirm", False)) or (mode and mode != "touch")
        if volf > 0 and not cc:
            return ("LEAK",
                    f"touch entry fills at the range edge INTRABAR, but vol_filter={volf:g} "
                    "reads the breakout bar's FINISHED volume - that number does not exist "
                    "at fill time.",
                    "crown ORB_3_1_125C.py (close-confirmed twin), or set close_confirm=True, "
                    "or vol_filter=0. Honest baselines are $44-69k/16.1y, NOT $494k.")
        if volf > 0 and cc:
            return ("CLEAN",
                    "the entry decision happens at the bar's CLOSE, where that bar's volume "
                    "is legitimately known.", "")
        return ("CLEAN", "no volume filter - nothing end-of-bar gates the fill.", "")

    if name in _MILD:
        return ("MILD", _MILD_NOTE, "state the assumption when reporting; no action required.")

    if name in _CLEAN_NOTE:
        return ("CLEAN", _CLEAN_NOTE[name], "")

    return ("UNAUDITED",
            "not covered by the 2026-08-11 sweep - audit it by hand before crowning.",
            "for every fill ask: does every input exist at the moment of THIS fill?")


_ICON = {"LEAK": "[X] LEAK ", "MILD": "[!] MILD ", "CLEAN": "[ok] CLEAN", "UNAUDITED": "[?] UNAUD"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default="")
    ap.add_argument("--params", default="")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()

    if a.all:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sdir = os.path.join(root, "augur_strategies")
        names = sorted(f for f in os.listdir(sdir) if f.endswith(".py"))
        buckets = {}
        for n in names:
            v, why, _ = audit(n)
            buckets.setdefault(v, []).append(n)
        for v in ("LEAK", "MILD", "CLEAN", "UNAUDITED"):
            items = buckets.get(v) or []
            print(f"\n{_ICON[v]}  ({len(items)})")
            for n in items:
                print(f"    {n}")
        print("\nNOTE: ORB-family verdicts above use each file's DEFAULT params. A specific "
              "config can flip - re-run with --strategy/--params before crowning.")
        return 0

    if not a.strategy:
        ap.print_help()
        return 2
    v, why, fix = audit(a.strategy, _parse_params(a.params))
    print()
    print(f"{_ICON[v]}   {a.strategy}   {a.params}")
    print(f"  why: {why}")
    if fix:
        print(f"  do : {fix}")
    print()
    return 1 if v == "LEAK" else 0


if __name__ == "__main__":
    raise SystemExit(main())
