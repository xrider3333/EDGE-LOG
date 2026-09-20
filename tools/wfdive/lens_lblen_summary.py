"""Compact reader over _wfdive_data/lens_lblen.json -- prints the headline table
for the crowns + a rollup across all OK runs. Read-only, no backtests, no lock."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_wfdive_data")
PATH = os.path.join(DATA_DIR, "lens_lblen.json")


def main():
    d = json.load(open(PATH, encoding="utf-8"))
    print(f"generated_at={d['generated_at']} n_selected={d['n_selected']} "
          f"n_ok={d['n_ok']} n_dropped={d['n_dropped']} "
          f"n_resamples={d['n_resamples']} lengths={d['lockbox_lengths_months']}")
    print()
    print("DROPPED:")
    for r in d["dropped"]:
        print(f"  #{r.get('id')}: {r.get('drop_reason')}")
    print()
    print(f"{'id':>4} {'crown':>5} {'strategy':<28} {'inst/tf':<10} "
          f"{'wfsplit':<11} {'honest_tr':>9} {'L12_real':>8} {'L12_noEdge':>10} "
          f"{'L24_real':>8} {'L24_noEdge':>10} {'cross_m':>7} {'coldshare12':>11} "
          f"{'coldshare24':>11} {'spearman_rho':>12}")
    for r in d["runs"]:
        pt = r.get("power_table") or {}
        l12 = pt.get("12") or {}
        l24 = pt.get("24") or {}
        cs = r.get("cold_start_share") or {}
        rt = r.get("recency_pf_trend") or {}
        print(f"{r['id']:>4} {str(r.get('crown')):>5} {r.get('strategy','')[:28]:<28} "
              f"{(r.get('instrument','')+'/'+r.get('timeframe','')):<10} "
              f"{str((r.get('wf_split') or {}).get('date')):<11} "
              f"{str((r.get('honest_edge') or {}).get('trades')):>9} "
              f"{str(round((l12.get('real_edge') or {}).get('p_verdict_pass', float('nan')), 2)):>8} "
              f"{str(round((l12.get('no_edge_control') or {}).get('p_verdict_pass', float('nan')), 2)):>10} "
              f"{str(round((l24.get('real_edge') or {}).get('p_verdict_pass', float('nan')), 2)):>8} "
              f"{str(round((l24.get('no_edge_control') or {}).get('p_verdict_pass', float('nan')), 2)):>10} "
              f"{str(r.get('power_crossing_months')):>7} "
              f"{str((cs.get('12mo') or {}).get('share_lost')):>11} "
              f"{str((cs.get('24mo') or {}).get('share_lost')):>11} "
              f"{str(rt.get('spearman_rho')):>12}")


if __name__ == "__main__":
    main()
