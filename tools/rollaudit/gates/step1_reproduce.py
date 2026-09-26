"""Step 1: reproduce the served artifact offline and confirm predictions match."""
import time
import numpy as np
import joblib

from common import leg_config, load_raw_arrays, get_trades, fit_artifact_model, ARTIFACT_DIR

for key in ("NOISE_H_RF", "ENGUQ_ER_H"):
    t0 = time.time()
    leg = leg_config(key)
    arrays, master = load_raw_arrays(leg)
    print(f"{key}: master={master['filename']} bars={len(arrays['index'])} "
          f"span={arrays['index'][0]} .. {arrays['index'][-1]}")
    trades, res = get_trades(leg, arrays)
    print(f"{key}: n_trades={len(trades)} (dt {time.time()-t0:.1f}s)")

    art = joblib.load(rf"{ARTIFACT_DIR}\{key}.pkl")
    print(f"{key}: served n_trades_trained={art['n_trades_trained']} "
          f"trained_through={art['trained_through']}")

    assert len(trades) == art["n_trades_trained"], "trade count mismatch vs served artifact"

    mdl, X, y, P, names = fit_artifact_model(leg, arrays, trades, seed=leg["gate"].get("seed", 42))
    my_proba = mdl.predict_proba(X)[:, 1]
    served_proba = art["pipe"].predict_proba(X)[:, 1]
    maxdiff = float(np.max(np.abs(my_proba - served_proba)))
    print(f"{key}: max prob diff vs served artifact = {maxdiff:.10f}  "
          f"(dt total {time.time()-t0:.1f}s)")
    print("-" * 70)
