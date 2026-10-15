# SUPERSCALPER r1 - the AS-PORTED cell's lines beside the grid's (NOISE #123 ask): the same four lines at 0.706 and the
# +0.25-point stress line, on the 2024 development year. Display only - the selection is tools/superscalper_improve_r1.py's.
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import superscalper_improve_r1 as G

if __name__ == "__main__":
    G._init()
    vals = tuple(G.AS_PORTED[k] for k in G.KEYS)
    _v, g, dt = G._cell(vals)
    show = ("trades", "win_rate", "avg_win", "avg_loss", "net_pf", "net_pts")
    for lab, cost in (("AS-PORTED  0.706", G.COST), ("AS-PORTED +0.25 ", G.COST + G.STRESS)):
        s = G.stats(g, cost)
        print(lab, json.dumps({k: round(s[k], 4) if isinstance(s[k], float) else s[k] for k in show}))
