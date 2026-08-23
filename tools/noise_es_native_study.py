"""
NOISE ES-NATIVE study — 2026-08-22.

THE QUESTION: does the NOISE mechanism carry an ES edge when its parameters are
allowed to fit ES? This is NOT a transfer test (transfer = NQ-tuned params on ES,
nothing refitted; banked best PF 1.126). A re-tuned result must never be quoted
as a transfer result. Full pre-registration in NOISE.md ("2026-08-22 — ES-native
study"), written and committed BEFORE the grid ran.

Data:    ES 5m RTH no-adjust master (NOADJ_ES_5m_RTH.csv, db_noadj_rth),
         coverage 2010-06-07 -> 2026-08-21. Costs = the campaign's ES-probe
         convention: 0.533 pts/round-trip, multiplier 50 ($26.65/trade), 1 lot.
Windows: SELECTION 2010-06-07 -> 2025-02-10 (mirrors the NQ spent-lockbox
         boundary). HOLDOUT 2025-02-11 -> 2026-08-21 — genuinely unspent,
         read EXACTLY ONCE at the end via --holdout, never ranked on.

Usage:
  python tools/noise_es_native_study.py --parity     # reproduction gate only
  python tools/noise_es_native_study.py --stage1     # 625-cell core grid (filters OFF)
  python tools/noise_es_native_study.py --stage2     # filter overlays (needs stage1 json)
  python tools/noise_es_native_study.py --holdout    # THE single holdout read (guarded)

Set AUGUR_DATA_ROOT to point augur_engine at a checkout that holds
optimizer_history.db + augur_uploads (research convenience; default = this repo).
Results JSONs land next to this file as noise_es_native_stage*.json.
"""
import os, sys, json, time, itertools, argparse

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
EDGELOG_ROOT = os.path.dirname(TOOLS_DIR)
for p in (EDGELOG_ROOT, TOOLS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import augur_engine.data as _data                                  # noqa: E402
_DROOT = os.environ.get("AUGUR_DATA_ROOT")
if _DROOT:
    _data.DB_PATH = os.path.join(_DROOT, "optimizer_history.db")
    _data.UPLOADS = os.path.join(_DROOT, "augur_uploads")

from noise_variant_research import run_variant, metrics, CHAMPION  # noqa: E402

FEE, MULT = 0.533, 50.0            # ES-probe convention: 0.533 pts, $50/pt
SEL_FROM, SEL_TO = "2010-06-07", "2025-02-10"
HOLD_FROM, HOLD_TO = "2025-02-11", "2026-08-21"

# Pre-registered grid (NOISE.md 2026-08-22 section)
G_LOOKBACK = [28, 36, 44, 52, 64]
G_BML = [0.5, 0.75, 1.0, 1.25, 1.5]
G_BMS = [0.75, 1.0, 1.25, 1.5, 1.75]
G_STOPK = [1.25, 1.5, 1.75, 2.0, 2.5]
FILTERS = [  # stage-2 overlays: (label, extra params)
    ("sbs",        dict(daytype_mode="skip_bot_short", daytype_lo=0.20)),
    ("vs90",       dict(rv_mode="skip_hi", rv_pct=90.0)),
    ("vs98",       dict(rv_mode="skip_hi", rv_pct=98.0)),
    ("sbs+vs90",   dict(daytype_mode="skip_bot_short", daytype_lo=0.20, rv_mode="skip_hi", rv_pct=90.0)),
    ("sbs+vs98",   dict(daytype_mode="skip_bot_short", daytype_lo=0.20, rv_mode="skip_hi", rv_pct=98.0)),
]

STAGE1_JSON = os.path.join(TOOLS_DIR, "noise_es_native_stage1.json")
STAGE2_JSON = os.path.join(TOOLS_DIR, "noise_es_native_stage2.json")
HOLDOUT_FLAG = os.path.join(TOOLS_DIR, "noise_es_native_holdout_READ.json")

_ARR = {}


def load_es(date_from=None, date_to=SEL_TO):
    key = (date_from, date_to)
    if key not in _ARR:
        m = _data.find_master("ES", "5m", "rth", "db_noadj_rth")
        if m is None:
            raise SystemExit("NO MASTER for ES/5m/rth/db_noadj_rth")
        _ARR[key] = _data.load_master_arrays(m, date_from=date_from, date_to=date_to)
    return _ARR[key]


def run_cfg(params, date_from=None, date_to=SEL_TO):
    arr = load_es(date_from, date_to)
    tr = run_variant(arr["open"], arr["high"], arr["low"], arr["close"],
                     arr.get("volume"), arr["day_id"], **params)
    m = metrics(tr, arr["index"], cost_pts=FEE, mult=MULT)
    if m is None:
        return None
    # extra legs the pre-registered bar needs: per-trade nets + concentration
    net_per_trade = [(t[2] - FEE) * MULT for t in tr]
    top10 = sum(sorted(net_per_trade, reverse=True)[:10])
    m["net_ex_top10"] = m["net"] - top10
    yrs = m["pyear"]
    m["years_pos"] = sum(1 for v in yrs.values() if v > 0)
    m["years_neg"] = sum(1 for v in yrs.values() if v <= 0)
    m["pyear"] = {int(k): round(v, 0) for k, v in yrs.items()}
    return m


def core(lb, bml, bms, sk):
    return dict(lookback=lb, band_mult_long=bml, band_mult_short=bms,
                exit_mode="vwap", side="Both", window="all_day",
                stop_mode="bandwidth", stop_k=sk)


def fmt(label, m):
    if m is None:
        return "%-34s NO TRADES" % label
    return ("%-34s n=%-5d net=$%-10s PF=%.3f DD=$%-9s MAR=%-5.2f "
            "yrs+%d/-%d 2010-17=$%-8s exTop10=$%s" % (
        label, m["n"], format(m["net"], ",.0f"), m["pf"],
        format(abs(m["dd"]), ",.0f"), m["mar"], m["years_pos"], m["years_neg"],
        format(m["era_2010_17"], ",.0f"), format(m["net_ex_top10"], ",.0f")))


def parity():
    """Reproduction gate: banked ES-transfer numbers (NOISE.md), selection window."""
    ok = True
    for label, params, en, epts, epf in [
        ("#231 champion (transfer)", dict(CHAMPION), 5312, 645.0, 1.036),
        ("SBS (transfer)", dict(CHAMPION, daytype_mode="skip_bot_short"), 4900, 1424.4, 1.093),
    ]:
        m = run_cfg(params)
        pts = m["net"] / MULT
        good = (m["n"] == en and abs(pts - epts) < 0.5 and abs(m["pf"] - epf) < 0.005)
        print("%s -> n=%d pts=%.1f PF=%.3f  %s" % (label, m["n"], pts, m["pf"],
              "PASS" if good else "FAIL (exp n=%d pts=%.1f PF=%.3f)" % (en, epts, epf)))
        ok = ok and good
    print("PARITY GATE: %s" % ("PASS" if ok else "FAIL"))
    return ok


def keyof(lb, bml, bms, sk):
    return "%d/%.2f/%.2f/%.2f" % (lb, bml, bms, sk)


def stage1():
    if not parity():
        raise SystemExit("parity FAIL — stop")
    cells = list(itertools.product(G_LOOKBACK, G_BML, G_BMS, G_STOPK))
    print("\nSTAGE 1 — %d core cells, filters OFF, selection window %s -> %s" %
          (len(cells), SEL_FROM, SEL_TO))
    out = {}
    t0 = time.time()
    for i, (lb, bml, bms, sk) in enumerate(cells):
        m = run_cfg(core(lb, bml, bms, sk))
        if m is not None:
            m.pop("pyear", None)
            out[keyof(lb, bml, bms, sk)] = m
        if (i + 1) % 50 == 0:
            print("  %d/%d (%.0fs)" % (i + 1, len(cells), time.time() - t0))
    with open(STAGE1_JSON, "w") as f:
        json.dump(out, f)
    rank = sorted(out.items(), key=lambda kv: kv[1]["pf"], reverse=True)
    print("\nTop 20 by selection-window PF:")
    for k, m in rank[:20]:
        print("  %-22s n=%-5d net=$%-10s PF=%.3f MAR=%.2f yrs+%d/-%d 2010-17=$%s" % (
            k, m["n"], format(m["net"], ",.0f"), m["pf"], m["mar"],
            m["years_pos"], m["years_neg"], format(m["era_2010_17"], ",.0f")))
    n12 = sum(1 for _, m in rank if m["pf"] >= 1.2)
    n115 = sum(1 for _, m in rank if m["pf"] >= 1.15)
    n10 = sum(1 for _, m in rank if m["pf"] >= 1.0)
    print("\ncells PF>=1.2: %d   PF>=1.15: %d   PF>=1.0: %d   of %d" %
          (n12, n115, n10, len(out)))
    print("NQ-champion cell: %s" % fmt("44/0.75/1.50/1.75", out.get(keyof(44, 0.75, 1.5, 1.75))))
    return out


def neighbours(lb, bml, bms, sk):
    out = []
    for ax, grid, val in (("lb", G_LOOKBACK, lb), ("bml", G_BML, bml),
                          ("bms", G_BMS, bms), ("sk", G_STOPK, sk)):
        i = grid.index(val)
        for j in (i - 1, i + 1):
            if 0 <= j < len(grid):
                d = dict(lb=lb, bml=bml, bms=bms, sk=sk); d[ax] = grid[j]
                out.append((d["lb"], d["bml"], d["bms"], d["sk"]))
    return out


def stage2():
    with open(STAGE1_JSON) as f:
        s1 = json.load(f)
    best_key = max(s1, key=lambda k: s1[k]["pf"])
    lb, bml, bms, sk = best_key.split("/")
    best_cell = (int(lb), float(bml), float(bms), float(sk))
    cores = [("NQ-core", (44, 0.75, 1.5, 1.75)), ("bestS1", best_cell)]
    for nb in neighbours(*best_cell):
        cores.append(("bestS1-nb", nb))
    print("STAGE 2 — filter overlays on %d cores x %d filter combos" %
          (len(cores), len(FILTERS)))
    out = {}
    for tag, (clb, cbml, cbms, csk) in cores:
        base = core(clb, cbml, cbms, csk)
        ck = keyof(clb, cbml, cbms, csk)
        m0 = s1.get(ck) or run_cfg(base)
        print("\n%s core %s  ->  %s" % (tag, ck, fmt("filters OFF", m0)))
        out.setdefault(ck, {})["off"] = m0
        for fl, fp in FILTERS:
            m = run_cfg(dict(base, **fp))
            print("  %s" % fmt(fl, m))
            m.pop("pyear", None)
            out[ck][fl] = m
    with open(STAGE2_JSON, "w") as f:
        json.dump(out, f)
    return out


def holdout(params, label, core_params=None):
    """THE single pre-registered holdout read (winner, plus optionally the same
    config's filter-off core for attribution — both in this ONE read event, as
    the pre-registration allows). Refuses to run twice."""
    if os.path.exists(HOLDOUT_FLAG):
        raise SystemExit("HOLDOUT ALREADY READ (%s exists) — it is spent. Refusing." % HOLDOUT_FLAG)
    rec = {"window": [HOLD_FROM, HOLD_TO], "reads": []}
    out = []
    for lab, p in [(label, params)] + ([("filter-off core", core_params)] if core_params else []):
        m = run_cfg(p, date_from=HOLD_FROM, date_to=HOLD_TO)
        print("HOLDOUT %s (%s -> %s)" % (fmt(lab, m), HOLD_FROM, HOLD_TO))
        rec["reads"].append({"label": lab, "params": dict(p),
                             "result": {k: v for k, v in (m or {}).items() if k != "pyear"},
                             "pyear": (m or {}).get("pyear")})
        out.append(m)
    with open(HOLDOUT_FLAG, "w") as f:
        json.dump(rec, f, indent=1)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--parity", action="store_true")
    ap.add_argument("--stage1", action="store_true")
    ap.add_argument("--stage2", action="store_true")
    ap.add_argument("--holdout", action="store_true",
                    help="single guarded holdout read of the declared winner")
    ap.add_argument("--params", help="JSON params for --holdout")
    a = ap.parse_args()
    if a.parity:
        sys.exit(0 if parity() else 1)
    if a.stage1:
        stage1()
    if a.stage2:
        stage2()
    if a.holdout:
        if not a.params:
            raise SystemExit("--holdout needs --params '<json>'")
        holdout(json.loads(a.params), "declared-winner")
    if not (a.parity or a.stage1 or a.stage2 or a.holdout):
        stage1(); stage2()
