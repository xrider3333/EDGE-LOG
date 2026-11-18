"""Contract specs and default round-trip cost for the CME roots added 2026-11-18 (ZN / RTY / YM).

cost_pts = one tick of slippage + all-in fees, per round trip, in POINTS (what run_backtest's cost_pts takes).
Fees use the ES house figure: ES cost 0.363 pts = 1 tick (0.25 = $12.50) + $5.65 fees, so $5.65 / mult here.
Specs checked against the CME contract pages: RTY $50 x index, tick 0.10 ($5.00); YM $5 x index, tick 1.0 ($5.00);
ZN $1,000 per point, tick 1/2 of 1/32 = 1/64 ($15.625).
NQ / ES are deliberately NOT here - their costs live with their legs (api/paper.py) and must not move.
"""
FEES_RT_USD = 5.65

SPECS = {
    "RTY": {"mult": 50.0, "tick": 0.10},
    "YM": {"mult": 5.0, "tick": 1.0},
    "ZN": {"mult": 1000.0, "tick": 1.0 / 64},
}
for _s in SPECS.values():
    _s["tick_usd"] = _s["mult"] * _s["tick"]
    _s["cost_pts"] = round(_s["tick"] + FEES_RT_USD / _s["mult"], 6)


def default_cost_pts(instrument):
    """1 tick + fees per round trip in points, or None for a root this table does not hold."""
    s = SPECS.get(str(instrument or "").upper())
    return s["cost_pts"] if s else None
