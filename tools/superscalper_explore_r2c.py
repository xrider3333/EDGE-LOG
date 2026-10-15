# SUPERSCALPER r2c (prereg docs/PREREG_tv_superscalper_r2c_rth_hours_2026-10-15.md): the RTH hours H1 09:30-10:29 / H2 10:30-14:59 /
# H3 15:00-15:59 (signal bar, New York) of the file-default run on NQ 2023 and 2024, at 0.706 and at +1 tick (0.956). Descriptive only.
# Reuses r2's harness (sha-checked); parity gate = r2b's 2023 total. OUR PORT, development data only.
#   python tools/superscalper_explore_r2c.py
import hashlib, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHARED = r"C:\Users\xride\OneDrive\Desktop\EDGE-LOG"
PREREG = os.path.join(HERE, "..", "docs", "PREREG_tv_superscalper_r2c_rth_hours_2026-10-15.md")
PREREG_LF_SHA = "7f3caabe69667bd49b621dae747d5a1ff3032b54a9a6e963560460682cbd2d5c"
R2 = os.path.join(SHARED, "tools", "superscalper_explore_r2.py")
R2_LF_SHA = "26a2f9aab8f83ee3b058f4d9492e906d4f5484643eb4122be6f87eff29ecf9ab"
PORTS = [os.path.join(SHARED, "augur_strategies", "MISC_SUPERSCALPER_1_0.py"),
         r"C:\Users\xride\AppData\Local\EdgeLog-worktrees\superscalp\augur_strategies\MISC_SUPERSCALPER_1_0.py"]
PORT_LF_SHA = "b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1"
OUT = r"C:\EdgeLog\_research_cache\tv_scalp\superscalper\explore_r2c.json"
HOURS = (("H1 09:30-10:29", 570, 630), ("H2 10:30-14:59", 630, 900), ("H3 15:00-15:59", 900, 960))
COSTS = (("0.706", 0.706), ("+1 tick 0.956", 0.956))


def lf_sha(p):
    return hashlib.sha256(open(p, "rb").read().replace(b"\r\n", b"\n")).hexdigest()


def hour_of(m):
    for name, a, b in HOURS:
        if a <= m < b:
            return name
    return None


def main():
    got = lf_sha(PREREG)
    print("prereg LF sha256", got, "OK" if got == PREREG_LF_SHA else "MISMATCH", flush=True)
    if got != PREREG_LF_SHA:
        sys.exit("refused: prereg is not the pinned one")
    if lf_sha(R2) != R2_LF_SHA:
        sys.exit("refused: r2 harness is not %s" % R2_LF_SHA)
    port = next((p for p in PORTS if os.path.exists(p) and lf_sha(p) == PORT_LF_SHA), None)
    if port is None:
        sys.exit("refused: no port with LF sha %s" % PORT_LF_SHA)
    sys.path.insert(0, os.path.dirname(R2))
    import superscalper_explore_r2 as X
    print("r2 harness OK; port", port, "OK; harness LF sha256", lf_sha(os.path.abspath(__file__)), flush=True)
    R = X.Runner(port)
    out = {}
    for yname, yr in (("2023", X.Y23), ("2024", X.Y24)):
        d, days = R.trades("NQ", yr, dict(close_rule="any"))
        if yname == "2023":
            tot = round(float((d["pnl"] - 0.706).sum()), 1)
            print("PARITY GATE: 2023 'any' %d trades, %.1f net pt (r2b: 2311 / 2005.9)" % (len(d), tot), flush=True)
            if len(d) != 2311 or abs(tot - 2005.9) > 0.05:
                sys.exit("refused: parity gate failed - this port is not the r2b port at defaults")
        d["hour"] = d["sig_min"].map(hour_of)
        out[yname] = {}
        print("\nNQ %s" % yname, flush=True)
        for cname, cost in COSTS:
            X.COST["NQ"] = cost
            rows = {"RTH all": X.Runner.read(R, "NQ", d[d["hour"].notna()], days, "%s RTH all @ %s" % (yname, cname))}
            for h in [x[0] for x in HOURS]:
                rows[h] = X.Runner.read(R, "NQ", d[d["hour"] == h], days, "%s %s @ %s" % (yname, h, cname))
            out[yname][cname] = rows
        X.COST["NQ"] = 0.706
    carry = [h for h in [x[0] for x in HOURS]
             if all((out[y]["0.706"][h]["net_pf"] or 0) >= 1.10 and out[y]["0.706"][h]["trades"] >= 100 for y in ("2023", "2024"))]
    tick = {y: {h: bool((out[y]["+1 tick 0.956"][h]["net_pf"] or 0) > 1.0) for h in ["RTH all"] + [x[0] for x in HOURS]}
            for y in ("2023", "2024")}
    out["carries_both_years"] = carry
    out["survives_plus_1_tick"] = tick
    print("\nAn hour that carries it in BOTH years (PF >= 1.10, >= 100 trades each):", carry or "none", flush=True)
    print("Survives +1 tick (net PF > 1.00 at 0.956):", json.dumps(tick), flush=True)
    json.dump(out, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
