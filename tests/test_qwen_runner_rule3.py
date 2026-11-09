"""Runner rule 3 (owner GO 11-09): model 2 by day, the 35b only idle 15+ min or at night, dropped on activity."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import qwen_runner as R


def test_pick_model():
    assert R.pick_model(lambda: 5, lambda: False) == R.MODEL_DAY          # owner active by day
    assert R.pick_model(lambda: 16 * 60, lambda: False) == R.MODEL       # idle 15+ min
    assert R.pick_model(lambda: 120, lambda: True) == R.MODEL            # night, not active
    assert R.pick_model(lambda: 10, lambda: True) == R.MODEL_DAY         # night but owner active
    assert R.pick_model(lambda: None, lambda: True) == R.MODEL_DAY       # unknown idle = day model


def test_own_model_prefixes():
    ps = lambda: {"models": [{"name": R.MODEL_DAY}]}
    assert R.other_model_loaded(ps, own=("5.",))[0] is True
    assert R.other_model_loaded(ps, own=("2.", "5."))[0] is False


class _Fake(R._Rule3):
    def __init__(self):
        self.model = R.MODEL
        self.calls, self.unloads = [], 0

    def _unload_big(self):
        self.unloads += 1


def test_day_switch_unloads_big(monkeypatch):
    monkeypatch.setattr(R, "pick_model", lambda *a: R.MODEL_DAY)
    f = _Fake()
    assert f._guarded(lambda m: m) == R.MODEL_DAY and f.unloads == 1


def test_owner_returns_mid_turn(monkeypatch):
    monkeypatch.setattr(R, "pick_model", lambda *a: R.MODEL)
    monkeypatch.setattr(R, "WATCH_POLL_S", 0.01)
    monkeypatch.setattr(R, "owner_active", lambda *a: True)
    import time
    f = _Fake()

    def call(m):
        f.calls.append(m)
        if m == R.MODEL:
            time.sleep(0.2)
            raise RuntimeError("aborted by unload")
        return "ok"
    assert f._guarded(call) == "ok"
    assert f.calls == [R.MODEL, R.MODEL_DAY] and f.unloads >= 1
