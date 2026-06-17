"""One-off backfill of the 2026-06-08 WF run into augur_research/."""
import json, os

RESEARCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "augur_research")
os.makedirs(RESEARCH, exist_ok=True)

data = {
  "meta": {
    "run_date": "2026-06-08",
    "script": "wf_vwap.py",
    "n_trials": 200,
    "n_folds": 6,
    "init_frac": 0.40,
    "elapsed_s": 2816,
    "note": "Backfilled from console output — no equity curves (predates return_trades capture)"
  },
  "runs": [
    {
      "label": "VWAP_FADE_1 [ES]", "strategy": "VWAP_FADE_1", "instrument": "ES", "mult": 50,
      "total_held": 5, "total_folds": 6, "total_oos_usd": 3751,
      "folds": [
        {"fold":1,"yr_label":"2016-18","is_pf":3.76,"is_t":17,"oos_pf":2.40,"oos_t":10,"oos_usd":672,"held":True,"champ":{},"trades":[]},
        {"fold":2,"yr_label":"2018-20","is_pf":2.90,"is_t":23,"oos_pf":1.38,"oos_t":6,"oos_usd":324,"held":True,"champ":{},"trades":[]},
        {"fold":3,"yr_label":"2020-21","is_pf":2.01,"is_t":41,"oos_pf":1.11,"oos_t":16,"oos_usd":192,"held":True,"champ":{},"trades":[]},
        {"fold":4,"yr_label":"2021-23","is_pf":1.51,"is_t":71,"oos_pf":1.83,"oos_t":16,"oos_usd":3611,"held":True,"champ":{},"trades":[]},
        {"fold":5,"yr_label":"2023-24","is_pf":2.18,"is_t":49,"oos_pf":1.39,"oos_t":5,"oos_usd":376,"held":True,"champ":{},"trades":[]},
        {"fold":6,"yr_label":"2024-26","is_pf":1.99,"is_t":99,"oos_pf":0.77,"oos_t":9,"oos_usd":-1424,"held":False,"champ":{},"trades":[]},
      ],
      "per_year": {"2016":[-168,3],"2017":[181,4],"2018":[1046,4],"2019":[-63,5],"2020":[-938,5],"2021":[2580,15],"2022":[2160,12],"2023":[188,1],"2024":[189,4],"2025":[-1611,8],"2026":[188,1]}
    },
    {
      "label": "VWAP_FADE_2 [ES]", "strategy": "VWAP_FADE_2", "instrument": "ES", "mult": 50,
      "total_held": 3, "total_folds": 6, "total_oos_usd": 714,
      "folds": [
        {"fold":1,"yr_label":"2016-18","is_pf":2.85,"is_t":37,"oos_pf":2.03,"oos_t":17,"oos_usd":850,"held":True,"champ":{},"trades":[]},
        {"fold":2,"yr_label":"2018-20","is_pf":2.89,"is_t":27,"oos_pf":1.18,"oos_t":13,"oos_usd":263,"held":True,"champ":{},"trades":[]},
        {"fold":3,"yr_label":"2020-21","is_pf":2.82,"is_t":16,"oos_pf":0.85,"oos_t":5,"oos_usd":-87,"held":False,"champ":{},"trades":[]},
        {"fold":4,"yr_label":"2021-23","is_pf":2.13,"is_t":63,"oos_pf":0.58,"oos_t":9,"oos_usd":-1013,"held":False,"champ":{},"trades":[]},
        {"fold":5,"yr_label":"2023-24","is_pf":1.85,"is_t":170,"oos_pf":1.36,"oos_t":20,"oos_usd":863,"held":True,"champ":{},"trades":[]},
        {"fold":6,"yr_label":"2024-26","is_pf":2.09,"is_t":130,"oos_pf":0.98,"oos_t":11,"oos_usd":-162,"held":False,"champ":{},"trades":[]},
      ],
      "per_year": {"2016":[-127,1],"2017":[-62,11],"2018":[1552,8],"2019":[-250,10],"2020":[-358,2],"2021":[-36,4],"2022":[-412,6],"2023":[-63,5],"2024":[633,17],"2025":[312,9],"2026":[-474,2]}
    },
    {
      "label": "VWAP_FADE_1 [NQ]", "strategy": "VWAP_FADE_1", "instrument": "NQ", "mult": 20,
      "total_held": 6, "total_folds": 6, "total_oos_usd": 10391,
      "folds": [
        {"fold":1,"yr_label":"2016-18","is_pf":1.75,"is_t":61,"oos_pf":1.15,"oos_t":14,"oos_usd":245,"held":True,"champ":{},"trades":[]},
        {"fold":2,"yr_label":"2018-20","is_pf":1.70,"is_t":44,"oos_pf":1.46,"oos_t":15,"oos_usd":985,"held":True,"champ":{},"trades":[]},
        {"fold":3,"yr_label":"2020-21","is_pf":1.60,"is_t":35,"oos_pf":1.23,"oos_t":7,"oos_usd":677,"held":True,"champ":{},"trades":[]},
        {"fold":4,"yr_label":"2021-23","is_pf":1.64,"is_t":41,"oos_pf":1.83,"oos_t":6,"oos_usd":2641,"held":True,"champ":{},"trades":[]},
        {"fold":5,"yr_label":"2023-24","is_pf":1.71,"is_t":47,"oos_pf":1.57,"oos_t":8,"oos_usd":1425,"held":True,"champ":{},"trades":[]},
        {"fold":6,"yr_label":"2024-26","is_pf":2.03,"is_t":89,"oos_pf":2.69,"oos_t":6,"oos_usd":4418,"held":True,"champ":{},"trades":[]},
      ],
      "per_year": {"2016":[652,2],"2017":[-258,8],"2018":[1571,6],"2019":[-670,11],"2020":[-1076,5],"2021":[3703,6],"2022":[626,4],"2023":[-870,3],"2024":[261,7],"2025":[7035,3],"2026":[-583,1]}
    },
    {
      "label": "VWAP_FADE_2 [NQ]", "strategy": "VWAP_FADE_2", "instrument": "NQ", "mult": 20,
      "total_held": 3, "total_folds": 6, "total_oos_usd": 6261,
      "folds": [
        {"fold":1,"yr_label":"2016-18","is_pf":2.04,"is_t":13,"oos_pf":1.24,"oos_t":5,"oos_usd":67,"held":True,"champ":{},"trades":[]},
        {"fold":2,"yr_label":"2018-20","is_pf":2.90,"is_t":16,"oos_pf":0.00,"oos_t":2,"oos_usd":-590,"held":False,"champ":{},"trades":[]},
        {"fold":3,"yr_label":"2020-21","is_pf":1.85,"is_t":22,"oos_pf":0.45,"oos_t":4,"oos_usd":-617,"held":False,"champ":{},"trades":[]},
        {"fold":4,"yr_label":"2021-23","is_pf":2.13,"is_t":53,"oos_pf":1.00,"oos_t":12,"oos_usd":-6,"held":False,"champ":{},"trades":[]},
        {"fold":5,"yr_label":"2023-24","is_pf":1.36,"is_t":65,"oos_pf":9.99,"oos_t":8,"oos_usd":3973,"held":True,"champ":{},"trades":[]},
        {"fold":6,"yr_label":"2024-26","is_pf":1.79,"is_t":83,"oos_pf":1.68,"oos_t":9,"oos_usd":3434,"held":True,"champ":{},"trades":[]},
      ],
      "per_year": {"2016":[183,1],"2017":[-18,3],"2018":[-99,1],"2019":[-590,2],"2020":[-407,3],"2021":[1734,3],"2022":[1464,8],"2023":[-1709,6],"2024":[-775,7],"2025":[6573,4],"2026":[-96,2]}
    },
  ]
}

out = os.path.join(RESEARCH, "wf_vwap_20260608.json")
with open(out, "w") as f:
    json.dump(data, f, indent=2)
print("Written:", out)
