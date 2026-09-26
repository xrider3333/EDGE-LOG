"""Merge worker JSON outputs and print the comparison numbers used in REPORT.txt."""
import json
import glob


def load_all(paths):
    out = {}
    for p in paths:
        with open(p) as f:
            d = json.load(f)
        out.update(d)
    return out


def flip_share(raw_c, corr_c):
    raw_map = dict(zip(raw_c["entry_bars"], raw_c["keep"]))
    corr_map = dict(zip(corr_c["entry_bars"], corr_c["keep"]))
    common = sorted(set(raw_map) & set(corr_map))
    flips = sum(1 for e in common if raw_map[e] != corr_map[e])
    return flips, len(common)


def fmt_block(b):
    return (f"n={b['n']} net=${b['net_usd']:.0f} dd=${b['max_dd_usd']:.0f} "
            f"roc%/yr={b['roc_pct_yr']:.2f}" if b.get('roc_pct_yr') is not None else
            f"n={b['n']} net=${b['net_usd']:.0f} dd=${b['max_dd_usd']:.0f} roc%/yr=n/a") + \
           (f" sortino={b['sortino']:.2f}" if b.get('sortino') is not None else " sortino=n/a")


def report_leg(name, d):
    print(f"\n===== {name} =====")
    raw = d["raw"]; corr = d["corrected"]
    print(f"raw:       taken {raw['n_taken']}/{raw['n_total']} skipped {raw['n_skipped']}")
    print(f"  WF   {fmt_block(raw['wf'])}")
    print(f"  LB   {fmt_block(raw['lb'])}")
    print(f"  FULL {fmt_block(raw['full'])}")
    print(f"corrected: taken {corr['n_taken']}/{corr['n_total']} skipped {corr['n_skipped']} "
          f"(masked {corr.get('masked_n')} 2026-splice trades, "
          f"{corr.get('stitch_nonzero')} stitch-corrected, sum|stitch|={corr.get('stitch_abs_sum'):.2f}pt)")
    print(f"  WF   {fmt_block(corr['wf'])}")
    print(f"  LB   {fmt_block(corr['lb'])}")
    print(f"  FULL {fmt_block(corr['full'])}")
    flips, common = flip_share(raw, corr)
    print(f"flip share raw vs corrected: {flips}/{common} = {flips/common*100:.2f}%")

    seed_keys = sorted([k for k in d if k.startswith("seed")], key=lambda k: int(k[4:]))
    nets = [d[k]["full"]["net_usd"] for k in seed_keys]
    dds = [d[k]["full"]["max_dd_usd"] for k in seed_keys]
    takens = [d[k]["n_taken"] for k in seed_keys]
    print(f"seed spread over {len(seed_keys)} seeds {seed_keys}:")
    print(f"  net$  min={min(nets):.0f} max={max(nets):.0f} spread={max(nets)-min(nets):.0f} raw={raw['full']['net_usd']:.0f}")
    print(f"  dd$   min={min(dds):.0f} max={max(dds):.0f} spread={max(dds)-min(dds):.0f} raw={raw['full']['max_dd_usd']:.0f}")
    print(f"  taken min={min(takens)} max={max(takens)} raw_taken={raw['n_taken']}")
    corr_net = corr["full"]["net_usd"]; raw_net = raw["full"]["net_usd"]
    move = abs(corr_net - raw_net)
    spread = max(nets) - min(nets)
    print(f"roll-correction move in net$ = {move:.0f}; seed spread in net$ = {spread:.0f}; "
          f"{'EXCEEDS' if move > spread else 'within'} seed spread")
    return dict(raw=raw, corr=corr, flips=flips, common=common, nets=nets, dds=dds,
                move=move, spread=spread, seed_keys=seed_keys)


if __name__ == "__main__":
    noise = load_all(sorted(glob.glob("noise_*.json")))
    report_leg("NOISE_H_RF", noise)
    try:
        enguq = load_all(sorted(glob.glob("enguq_*.json")))
        report_leg("ENGUQ_ER_H", enguq)
    except FileNotFoundError:
        print("\nENGUQ_ER_H not ready yet")
