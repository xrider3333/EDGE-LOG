# rename_strategies.py — ONE-TIME migration: standardize strategy filenames +
# STRATEGY_NAME display names to a consistent FAMILY M.m scheme, and update every
# reference (augur_config.json active_strategy + strat_nums, pine/<stem>.pine,
# _AUGUR_PARENT, _AUGUR_LINEAGE.parent_file). Backs everything up first; verifies
# every renamed .py still parses. Reversible: restore the backup dir.
import os, re, json, shutil, time, ast, sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDIR = os.path.join(ROOT, "augur_strategies")
PDIR = os.path.join(ROOT, "pine")
CFG  = os.path.join(ROOT, "augur_config.json")

# old_file_stem -> (new_file_stem, new_STRATEGY_NAME or None to keep existing)
RENAME = {
    "GROK_ENGU__I__V20":          ("ENGU_1_1_20",       "ENGU 1.1.20 (GROK)"),
    "ENGU_1_evo_v11":             ("ENGU_1_1_21",       "ENGU 1.1.21 · daily bias + flat-EOD (GROK)"),
    "ENGU_II":                    ("ENGU_1_2_1",        "ENGU 1.2.1 (GROK)"),
    "ENGU_3__CLAUDE_":            ("ENGU_1_3_1",        "ENGU 1.3.1 (CLAUDE)"),
    "tuned_0601_1331_72f8":       ("ENGU_1_3_2",        "ENGU 1.3.2 · AI-evolved (CLAUDE)"),
    "tuned_0602_0756_b468":       ("ENGU_1_3_3",        "ENGU 1.3.3 · gate 2-of-3 (CLAUDE)"),
    "ENGU_3_evo_v134":            ("ENGU_1_3_4",        "ENGU 1.3.4 · tight-consolidation (CLAUDE)"),
    "ENGU_3_evo_v135":            ("ENGU_1_3_5",        "ENGU 1.3.5 · daily bias + flat-EOD (CLAUDE)"),
    "OPENING_RANGE_BREAKOUT":     ("ORB_1_0",           "ORB 1.0 · open-momentum"),
    "OPENING_RANGE_BREAKOUT_V2":  ("ORB_2_0",           "ORB 2.0 · trail + ATR stop + vol filter"),
    "OPENING_RANGE_BREAKOUT_SIMPLE": ("ORB_SIMPLE_1_0", "ORB SIMPLE 1.0 · low-DOF deployable"),
    "Trend_Following_v1":         ("SUPERTREND_1_0",    "SUPERTREND 1.0 · trend-following (lighter)"),
    "Trend_Following_v2":         ("SUPERTREND_2_0",    "SUPERTREND 2.0 · strict (GROK)"),
    "OVERNIGHT_HOLD":             ("OVERNIGHT_HOLD_1_0","OVERNIGHT HOLD 1.0 · close→open risk-premium"),
    "RF_ML":                      ("RF_ML_1_0",         "RF ML 1.0 · random-forest direction"),
    "REVERT_1":                   ("REVERT_1_0",        None),
    "VWAP_FADE_1":                ("VWAP_FADE_1_0",     None),
    "VWAP_FADE_2":                ("VWAP_FADE_2_0",     None),
    # REVERT_1_1, REVERT_1_2 already consistent -> untouched
}
# in-file filename references to rewrite (old.py -> new.py), applied to ALL files
REF_REWRITE = {f"{o}.py": f"{n}.py" for o, (n, _) in RENAME.items()}


def set_strategy_name(txt, new_name):
    return re.sub(r'(?m)^STRATEGY_NAME\s*=\s*.+$',
                  f'STRATEGY_NAME = {new_name!r}', txt, count=1)


def main():
    stamp = time.strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(ROOT, "backups", f"strategy_rename_{stamp}")
    os.makedirs(bak, exist_ok=True)
    shutil.copytree(SDIR, os.path.join(bak, "augur_strategies"))
    shutil.copytree(PDIR, os.path.join(bak, "pine"))
    shutil.copy2(CFG, os.path.join(bak, "augur_config.json"))
    print(f"backup -> {bak}")

    # 1. rewrite + rename each strategy .py
    for old, (new, newname) in RENAME.items():
        op = os.path.join(SDIR, old + ".py")
        if not os.path.exists(op):
            print(f"  !! missing {old}.py — skipping"); continue
        txt = open(op, encoding="utf-8").read()
        if newname:
            txt = set_strategy_name(txt, newname)
        for a, b in REF_REWRITE.items():            # update parent_file / _AUGUR_PARENT refs
            txt = txt.replace(a, b)
        np_ = os.path.join(SDIR, new + ".py")
        open(np_, "w", encoding="utf-8").write(txt)
        if np_ != op:
            os.remove(op)
        print(f"  .py  {old}.py -> {new}.py" + (f'   NAME={newname!r}' if newname else ''))

    # 1b. fix refs inside the UNCHANGED files too (REVERT_1_1/1_2 reference nothing,
    #     but be safe — sweep all strategy files for old filename strings)
    for f in os.listdir(SDIR):
        if not f.endswith(".py"): continue
        p = os.path.join(SDIR, f)
        t = open(p, encoding="utf-8").read(); t2 = t
        for a, b in REF_REWRITE.items():
            t2 = t2.replace(a, b)
        if t2 != t:
            open(p, "w", encoding="utf-8").write(t2)
            print(f"  ref  updated filename refs inside {f}")

    # 2. rename matching pine files (pine/<stem>.pine)
    for old, (new, _) in RENAME.items():
        op = os.path.join(PDIR, old + ".pine")
        if os.path.exists(op):
            shutil.move(op, os.path.join(PDIR, new + ".pine"))
            print(f"  pine {old}.pine -> {new}.pine")

    # 3. augur_config.json: active_strategy + strat_nums keys
    cfg = json.load(open(CFG, encoding="utf-8"))
    act = cfg.get("active_strategy", "")
    for old, (new, _) in RENAME.items():
        if act.endswith(old + ".py"):
            cfg["active_strategy"] = act.replace(old + ".py", new + ".py")
            print(f"  cfg  active_strategy -> {new}.py")
    sn = cfg.get("strat_nums", {})
    newsn = {}
    for k, v in sn.items():
        stem = k[:-3] if k.endswith(".py") else k
        if stem in RENAME:
            newsn[RENAME[stem][0] + ".py"] = v
        else:
            newsn[k] = v
    cfg["strat_nums"] = newsn
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("  cfg  strat_nums keys rewritten (Library #s preserved)")

    # 4. verify every strategy file still parses
    bad = 0
    for f in sorted(os.listdir(SDIR)):
        if not f.endswith(".py"): continue
        try:
            ast.parse(open(os.path.join(SDIR, f), encoding="utf-8").read())
        except Exception as e:
            print(f"  XX PARSE FAIL {f}: {e}"); bad += 1
    print(f"\nverify: {bad} parse failures")
    print("Done." if not bad else "DONE WITH ERRORS — check backup.")


if __name__ == "__main__":
    main()
