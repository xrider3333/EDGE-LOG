"""HOST PIN helper for queue scripts (owner 11-20 "send backtest to desktop", MANAGER GO).

Every lane queue script builds its own job dict; this is the one shared way to pin it:

    from tools.job_host import add_host_args, apply_host
    add_host_args(ap)                 # adds --on-desktop and --host TAG
    job = apply_host(build_job(a), a) # sets job["host"] = "desktop" when asked

The runner (api/runner.py host_pin_verdict) lets only a runner with EDGELOG_HOST_TAG equal to
job["host"] claim it; after 6 h with no live runner of that tag any runner takes it and the
owner gets one phone line. No flag = no host field = exactly today's behaviour.
"""
DESKTOP = "desktop"


def add_host_args(ap):
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--on-desktop", action="store_true",
                   help="run on the desktop workers (job host='desktop'); falls back after 6 h")
    g.add_argument("--host", default=None, help="pin to the runners with this EDGELOG_HOST_TAG")
    return ap


def host_from_args(a):
    if getattr(a, "on_desktop", False):
        return DESKTOP
    h = (getattr(a, "host", None) or "").strip().lower()
    return h or None


def apply_host(job, a=None, host=None):
    """Return `job` with job['host'] set from `host` or the parsed args; unchanged when neither."""
    h = (host or "").strip().lower() or (host_from_args(a) if a is not None else None)
    if h:
        job["host"] = h
    return job
