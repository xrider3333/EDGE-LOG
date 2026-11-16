from api import qqq_exec as qe


def test_dip_retired_in_code_even_without_config(tmp_path, monkeypatch):
    assert qe.RETIRED_LEGS.get("DIP") == "2026-11-16"
    cfg = qe.load_config(path=str(tmp_path / "missing.json"), log=lambda *a: None)         if "path" in qe.load_config.__code__.co_varnames else qe.load_config(log=lambda *a: None)
    dips = [x for x in qe.LEGS if qe.leg_family(x) == "DIP"]
    assert dips and all(cfg["shares"].get(x, 0) == 0 for x in dips)
