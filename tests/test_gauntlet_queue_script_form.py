import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_script_form_imports_job_host():
    # `python tools/gauntlet_queue.py --help` must not die on `from tools.job_host`.
    r = subprocess.run([sys.executable, os.path.join(REPO, "tools", "gauntlet_queue.py"), "--help"],
                       cwd=os.path.join(REPO, "tools"), capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "--on-desktop" in r.stdout
