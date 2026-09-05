"""
Mine every Auto-Validate run's saved candidate population for the best EV R and R / YR.

House definitions (augur_engine/analytics.py + the web app, v73.460):
  EV R   = (1 - win_rate) * (PF - 1)            win_rate as a fraction; exact closed form
  R / YR = EV R * trades_per_year                trades / years of the SAME stretch

Reads users/{uid}/runs. For each run with a validate block and a window >= 3 years:
  - the crowned champion (best_* fields, optimize window),
  - every candidate in selection.candidates (+ robust), on its cal.wf block (the honest,
    walk-forward read) and its cal.pre block (pre-lockbox = in-sample+WF).
WF years: taken from the candidate's wf_rng when it is a date pair; otherwise the
optimize window years times the WF trade share (num_trades wf / num_trades pre) -
stated in the CSV column `wf_years_src` so nobody mistakes an estimate for a record.
Writes tools/r16_results/ryr_frontier.csv and prints the frontier tables.
"""
import os, sys, csv, json, datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate("serviceAccount.json"))
db = firestore.client()
u = db.collection("users").document("IO0K35JpLIcH9YK4C0pMNYUzZOM2")


def yrs(a, b):
    try:
        return (datetime.date.fromisoformat(str(b)[:10]) - datetime.date.fromisoformat(str(a)[:10])).days / 365.25
    except Exception:
        return None


def evr(win_pct, pf):
    w = win_pct / 100.0 if win_pct > 1 else win_pct
    return (1 - w) * (pf - 1)


def rng_years(rng):
    """wf_rng / is_rng may be a [from, to] date pair, a dict, or bar indices."""
    if isinstance(rng, dict):
        a = rng.get("from") or rng.get("start"); b = rng.get("to") or rng.get("end")
        y = yrs(a, b) if a and b else None
        return y, "dates"
    if isinstance(rng, (list, tuple)) and len(rng) == 2 and isinstance(rng[0], str):
        y = yrs(rng[0], rng[1])
        return y, "dates"
    return None, None


rows = []
printed_schema = False
for d in u.collection("runs").stream():
    r = d.to_dict() or {}
    v = r.get("validate") if isinstance(r.get("validate"), dict) else None
    if not v:
        continue
    win = (v.get("windows") or {}).get("optimize") or [r.get("date_from"), r.get("date_to")]
    oy = yrs(win[0], win[1]) if win and len(win) == 2 else yrs(r.get("date_from"), r.get("date_to"))
    if not oy or oy < 3:
        continue
    base = dict(run=r.get("id"), famKey=r.get("famKey"), strategy=str(r.get("strategy")),
                instrument=r.get("instrument"), timeframe=r.get("timeframe"), verdict=v.get("verdict"))
    pf = r.get("best_pf"); wr = r.get("best_win_rate"); n = r.get("best_trades")
    if pf and wr is not None and n and 0 < pf < 50:
        e = evr(wr, pf)
        rows.append(dict(base, source="champion", stretch="pre", n=n, years=round(oy, 2), pf=round(pf, 3),
                         win_pct=round(wr if wr > 1 else wr * 100, 1), evr=round(e, 3), ryr=round(e * n / oy, 1),
                         net=round(r.get("best_pnl_usd") or 0), dd=round(abs(r.get("best_dd_usd") or 0)),
                         wf_years_src="optimize window", params=json.dumps(r.get("best_params") or {})))
    sel = r.get("selection") or {}
    for src_name in ("candidates", "robust"):
        for c in (sel.get(src_name) or []):
            if not isinstance(c, dict):
                continue
            cal = c.get("cal") or {}
            pre = cal.get("pre") or {}
            if not printed_schema and c.get("wf_rng") is not None:
                print("schema peek: wf_rng =", json.dumps(c.get("wf_rng"))[:120], "| is_rng =", json.dumps(c.get("is_rng"))[:120])
                printed_schema = True
            for stretch in ("wf", "pre"):
                blk = cal.get(stretch) or {}
                n2 = blk.get("num_trades"); pf2 = blk.get("profit_factor"); wr2 = blk.get("win_rate")
                if not n2 or pf2 is None or wr2 is None or not (0 < pf2 < 50):
                    continue
                if stretch == "pre":
                    y, src = oy, "optimize window"
                else:
                    y, src = rng_years(c.get("wf_rng"))
                    if not y:
                        share = (n2 / pre["num_trades"]) if pre.get("num_trades") else None
                        y, src = ((oy * share) if share else None), "estimate: optimize yrs x WF trade share"
                if not y or y <= 0:
                    continue
                e = evr(wr2, pf2)
                rows.append(dict(base, source=src_name[:-1] if src_name.endswith("s") else src_name, stretch=stretch,
                                 n=n2, years=round(y, 2), pf=round(pf2, 3), win_pct=round(wr2 if wr2 > 1 else wr2 * 100, 1),
                                 evr=round(e, 3), ryr=round(e * n2 / y, 1), net=round(blk.get("total_pnl") or 0),
                                 dd=round(abs(blk.get("max_drawdown") or 0)), wf_years_src=src,
                                 params=json.dumps(c.get("params") or {})))

os.makedirs("tools/r16_results", exist_ok=True)
with open("tools/r16_results/ryr_frontier.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print(f"rows: {len(rows)}  -> tools/r16_results/ryr_frontier.csv\n")


def table(title, sel_rows, key, k=20):
    print(title)
    print(f"{'R/YR':>6} {'EVR':>5} {'run':>4} {'src':>9} {'str':>3} {'strategy':26} {'ins':3} {'tf':3} {'n':>5} {'yrs':>5} {'PF':>5} {'win%':>5} verdict")
    for x in sorted(sel_rows, key=lambda z: -z[key])[:k]:
        print(f"{x['ryr']:6.1f} {x['evr']:5.2f} {str(x['run']):>4} {x['source']:>9} {x['stretch']:>3} {x['strategy'][:26]:26} "
              f"{str(x['instrument'])[:3]:3} {str(x['timeframe'])[:3]:3} {x['n']:5} {x['years']:5.1f} {x['pf']:5.2f} {x['win_pct']:5.1f} {x['verdict']}")
    print()


wf = [x for x in rows if x["stretch"] == "wf" and x["n"] >= 100]
pre = [x for x in rows if x["stretch"] == "pre" and x["n"] >= 100]
table("TOP R / YR — WALK-FORWARD stretch (n>=100)", wf, "ryr")
table("TOP EV R — WALK-FORWARD stretch (n>=100)", wf, "evr", 15)
table("TOP R / YR — pre-lockbox stretch incl. champions (n>=100)", pre, "ryr")
table("TOP EV R — pre-lockbox stretch (n>=100)", pre, "evr", 15)
print("PER FAMILY: best WF R/YR candidate vs that run's champion (pre stretch)")
fams = {}
for x in wf:
    fams.setdefault(x["famKey"] or x["strategy"][:10], []).append(x)
for fam, xs in sorted(fams.items(), key=lambda kv: -max(z["ryr"] for z in kv[1])):
    b = max(xs, key=lambda z: z["ryr"])
    ch = [z for z in rows if z["run"] == b["run"] and z["source"] == "champion"]
    chs = f"champion pre R/YR {ch[0]['ryr']:.1f} EVR {ch[0]['evr']:.2f}" if ch else "champion n/a"
    print(f"  {str(fam):12} best WF R/YR {b['ryr']:6.1f} (EVR {b['evr']:.2f}, n {b['n']}, run #{b['run']}, {b['strategy'][:24]}) | {chs}")
