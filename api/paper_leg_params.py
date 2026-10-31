"""PAPER LEG PARAMS -- which numbered parameter SET of its run a paper leg trades, and which
MODEL VARIANT (owner 10-31: every paper row said '#382 . params: not recorded'; he wants
'NOISE #382.2 keel' - run 382, set 2, the KEEL overlay on).

THE SET NUMBER. Every paper run here is a validate run, and the one numbered list of parameter
sets its report shows the owner is the 1E table (COMPARE > the run's report, 'one row per
config') - the run doc's saved search grid (`points`), one row per configuration, sorted by
in-sample NET. Set N = the leg's cell is the N-th best configuration of that grid by in-sample
net (1 = the best). The walk-forward fold table is NOT a list of sets: a fold row is the cell
that fold re-tuned to, and one cell can own five folds (#382 owns folds 3 4 6 7 8).

Every matched leg is ALSO the run's validate CHAMPION (validate.champion == best_params), the
cell the report crowns; `matched_on` says so. `cell` is None where the leg's values sit in no
row of the saved grid: DIP #424 / #452 / #433 keep a grid thinned to 150 of their trials and
the champion is not among the kept rows; ENGU-Q #335 trades the R2 DEFAULTS, not the run's own
cell (LEG_SOURCE["ENGUQ_335"]["caveat"] says so in plain words). Those rows read 'set ?'.

THE MODEL VARIANT is read off the leg's own config, never typed by hand: a Webull leg's "keel"
block (api/cloud_signal.py CROWN_LEGS / SHADOW_LEGS) or an NT8 leg's "gate" block
(api/paper.py PAPER_LEGS). No block = 'raw'.

tools/check_paper_leg_params.py re-derives every number from the run docs and fails when a
leg's values no longer sit on the recorded set, and when index.html's inline copy
(PAPER_LEG_PARAMS) is stale. This module reads nothing and imports nothing of the engine, so
api/paper.py and api/cloud_signal.py can both import it.
"""
import json

_THIN = "the saved grid keeps 150 of the run's trials and the champion is not one of them"
_R2 = "trades the R2 defaults, not the run's own cell (LEG_SOURCE caveat)"
_FULL = ["champion", "grid_rank_by_is_net"]


def _c(run, cell, grid, why=None):
    d = {"run": run, "cell": cell, "grid": grid, "matched_on": list(_FULL if cell is not None else (["champion"] if why == _THIN else []))}
    if why:
        d["why"] = why
    return d


# leg key -> run, set number (None = not in the report's grid), grid size, how it was matched
CELLS = {
    # Webull (api/cloud_signal.py CROWN_LEGS + SHADOW_LEGS)
    "ORB_R6": _c(314, 22, 382),
    "NOISE_382": _c(382, 2, 24),
    "DIP_424": _c(424, None, 150, _THIN),
    "DIP_424K": _c(424, None, 150, _THIN),
    "DIP_424F": _c(424, None, 150, _THIN),
    "ENGUQ_335": _c(335, None, 527, _R2),
    "NOISE_422_PLAIN": _c(422, 2, 27),
    "NOISE_422_FIXED": _c(422, 2, 27),
    "NOISE_422_KEEL": _c(422, 2, 27),
    # NT8 (api/paper.py PAPER_LEGS)
    "ORB": _c(234, 1, 1),
    "ORB_H": _c(234, 1, 1),
    "ORB_257": _c(257, 1, 1),
    "ORB_239": _c(239, 1, 1),
    "ORB_R6_C15": _c(314, 22, 382),
    "ORB_R6_C15F": _c(314, 22, 382),
    "ORB_R6_C15FE": _c(314, 22, 382),
    "DIP_ES_452": _c(452, None, 150, _THIN),
    "DIP_NQ_433": _c(433, None, 150, _THIN),
    "ENGUQ_335_S1": _c(335, None, 527, _R2 + " plus a session window"),
    "ENGUQ_335_S2": _c(335, None, 527, _R2 + " plus a session window"),
    "ENGUQ_335_VC": _c(335, 4, 527),
    "ENGUQ_309": _c(309, 48, 150),
    "ENGUQ_309_K": _c(309, 48, 150),
    "ENGUQ_309_K9": _c(309, 48, 150),
    "ENGUQ_309_C15": _c(309, 48, 150),
    "ENGUQ_309_CD": _c(309, 48, 150),
    "ENGUQ_309_CDE": _c(309, 48, 150),
    "ENGUQ_309_CDE2": _c(309, 48, 150),
    "ENGUQ_ER_H": _c(265, 1, 1),
    "ENGUQ_L50": _c(249, 1, 1),
    "NOISE_304": _c(304, 99, 495),
    "NOISE_422": _c(422, 2, 27),
    "NOISE_H": _c(225, 11, 300),
    "NOISE_H_RF": _c(231, 11, 300),
    "TTM_299": _c(299, 6, 81),
    "TTM_299_T": _c(340, 6, 81),
    "TTM_299_SS": _c(353, 1, 9),
    "TTM_299_SSO": _c(368, 1, 9),
    "TTM_299_SSF2": _c(364, 1, 9),
    "TTM_299_SSL": _c(352, 1, 27),
    "TTM_299_SSOF2": _c(459, 1, 9),
    "TTM_299_SSOF2R": _c(369, 1, 9),
    "TTM_299_SSOF2R5": _c(428, 3, 9),
    "TTM_458_KEEL": _c(458, 3, 9),
}
for _k in ("NOISE_SBS_V90", "NOISE_SBS_V90_H", "NOISE_SBS_V90_T", "NOISE_SBS_V90_K", "NOISE_SBS_V90_K6",
           "NOISE_SBS_V90_K7", "NOISE_SBS_V90_K8", "NOISE_SBS_V90_K9", "NOISE_SBS_V90_K11",
           "NOISE_SBS_V90_K12", "NOISE_SBS_V90_C15", "NOISE_SBS_V90_C15G"):
    CELLS[_k] = _c(243, 1, 1)

# the Webull board's family keys -> the leg whose set it shows
WB_FAMILY_LEG = {"ORB": "ORB_R6", "NOISE": "NOISE_382", "DIP": "DIP_424", "ENGUQ": "ENGUQ_335"}

# an NT8 gate block's mode -> the word on the row
_GATE_WORD = {"keel": "keel", "keel_frozen": "keel", "hybrid": "hybrid", "tilt": "tilt", "comp": "comp"}
# a Webull keel block's mode (api/cloud_signal.py KEEL_MODE_*) -> the word on the row
_KEEL_WORD = {"fixed": "fixed", "const": "raw"}

GRID_LIST = "the run report's 1E table, one row per config, sorted by in-sample net"


def variant_of(cfg):
    """The model-variant word of a leg config: 'keel' (a learned KEEL state), 'fixed' (KEEL's
    fixed tilts), 'raw' (no model; a constant size counts as raw), or an NT8 gate's own word
    (keel / hybrid / tilt / comp)."""
    cfg = cfg or {}
    k = cfg.get("keel")
    if isinstance(k, dict):
        mode = str(k.get("mode") or "").lower()
        return _KEEL_WORD.get(mode, "keel")
    g = cfg.get("gate")
    if isinstance(g, dict):
        mode = str(g.get("mode") or "").lower()
        return _GATE_WORD.get(mode, mode or "raw")
    return "raw"


def cell_of(leg_key):
    """The recorded set of a leg key, or None for a leg this module has never matched."""
    return CELLS.get(leg_key)


def set_label(leg_key, run=None):
    """'#382.2' when the set is known, '#382 set ?' when the run is known and the set is not."""
    c = CELLS.get(leg_key) or {}
    r = c.get("run") if c.get("run") is not None else run
    if r is None:
        return ""
    return ("#%s.%s" % (r, c["cell"])) if c.get("cell") is not None else ("#%s set ?" % r)


def params_cell_of(leg_key):
    """The set number stamped on a trade: int, or None when the set is not in the report."""
    return (CELLS.get(leg_key) or {}).get("cell")


def stamp(rec, leg_key, cfg=None):
    """Add params_cell + model_variant to a trade / signal record (in place; returns it)."""
    rec["params_cell"] = params_cell_of(leg_key)
    rec["model_variant"] = variant_of(cfg)
    return rec


def inline_js(cfgs=None):
    """The JS constant index.html carries (PAPER_LEG_PARAMS): leg -> {run, cell, grid, variant}.
    variant is read from the cfg dicts handed in (the check script passes the live ones)."""
    out = {}
    for k, c in sorted(CELLS.items()):
        out[k] = {"run": c["run"], "cell": c["cell"], "grid": c["grid"], "variant": variant_of((cfgs or {}).get(k))}
    return "const PAPER_LEG_PARAMS=" + json.dumps(out, separators=(",", ":"), sort_keys=True) + ";"
