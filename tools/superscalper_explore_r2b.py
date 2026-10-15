# SUPERSCALPER r2b (prereg docs/PREREG_tv_superscalper_r2b_session_2026-10-15.md): the outside-RTH / RTH split of the file-default
# run on NQ 2023 (decomposition, close_rule 'any', tagged at the signal bar). Reuses r2's harness (sha-checked) for the runner and
# readers. Refuses on a prereg / r2-harness / port sha mismatch. OUR PORT, development data only.
#   python tools/superscalper_explore_r2b.py
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r2b_session_2026-10-15.md")
PREREG_LF_SHA = "1166c03ee78d608c878256ce0e10f777323cdbf9732da690629dfe9c61a7a7ae"
R2_CANDIDATES = [os.path.join(HERE, "superscalper_explore_r2.py"),
                 r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\superscalper_explore_r2.py",
                 r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\tv-ssexplore\tools\superscalper_explore_r2.py"]
R2_LF_SHA = "26a2f9aab8f83ee3b058f4d9492e906d4f5484643eb4122be6f87eff29ecf9ab"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2b.json"


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH", flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    r2 = next((p for p in R2_CANDIDATES if os.path.exists(p) and lf_sha(p) == R2_LF_SHA), None)
    if r2 is None:
        sys.exit("refused: r2 harness with LF sha %s not found" % R2_LF_SHA)
    sys.path.insert(0, os.path.dirname(r2))
    import superscalper_explore_r2 as X
    port = next((p for p in X.PORT_CANDIDATES if os.path.exists(p) and X.lf_sha(p) == X.PORT_LF_SHA), None)
    if port is None:
        sys.exit("refused: no port file with LF sha %s" % X.PORT_LF_SHA)
    print("r2 harness", r2, "OK; port", port, "OK; harness LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)
    R = X.Runner(port)
    d, days = R.trades("NQ", X.Y23, dict(close_rule="any"))
    d["win"] = d["sig_min"].map(X.window_of)
    rth = d["win"] != "W4 outside RTH"
    out = {"all": R.read("NQ", d, days, "NQ 2023 all ('any')"),
           "rth": R.read("NQ", d[rth], days, "NQ 2023 RTH 09:30-15:59 (W1+W2+W3)"),
           "outside_rth": R.read("NQ", d[~rth], days, "NQ 2023 outside RTH (W4)")}
    for name in [w[0] for w in X.WINDOWS]:
        out[name] = R.read("NQ", d[d["win"] == name], days, "NQ 2023 " + name + " (information)")
    o, r = out["outside_rth"]["net_pf"] or 0, out["rth"]["net_pf"] or 0
    out["verdict"] = "OVERNIGHT CARRIES 2023 TOO" if (o >= 1.0 and o > r) else "it does not"
    print("\nVERDICT:", out["verdict"], flush=True)
    json.dump(out, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
