"""Q40 ADDENDUM 1 (bookq/RULE_family_luck_bar_ADD1.txt): DIP #434 under the frozen family luck-bar rule. Imports q40_luck_bar.py UNCHANGED (its
LF sha256 is checked) and replaces only RUNS and OUT.
    python q40b_dip434.py run"""
import hashlib
import os
import sys

BQ = r"C:\EdgeLog\_anatomy_cache\bookq"
sys.path.insert(0, BQ)
lf = lambda p: hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()
Q40_SHA = "ad8bd0206a5ed86cb7143e01ca287e2e0075469656ec652f4b09c1e28ab77786"         # q40_luck_bar.py with the 10-12 post-run fix (f7e7a44c)
ADD1 = os.path.join(BQ, "RULE_family_luck_bar_ADD1.txt")
ADD1_SHA = "d4351bf7c249acc94609578ffff49a5bdfa6abc17ab77294793e7c8c5404c6dd"

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "run":
        raise SystemExit(__doc__)
    got = (lf(os.path.join(BQ, "q40_luck_bar.py")), lf(ADD1))
    print(f"PINS: q40 LF {got[0]}; addendum LF {got[1]}; wrapper LF {lf(__file__)}", flush=True)
    if got != (Q40_SHA, ADD1_SHA):
        raise SystemExit("refused: a pinned input is not the frozen one (nothing computed)")
    import q40_luck_bar as Q
    Q.RUNS = [(434, "DIP", "board leader (roll-aware successor of #424)")]
    Q.OUT = os.path.join(r"C:\EdgeLog\_anatomy_cache\luckbar", "add1_dip434")
    os.makedirs(Q.OUT, exist_ok=True)
    Q.run()
