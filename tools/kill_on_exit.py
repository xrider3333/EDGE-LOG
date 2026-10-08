r"""Kill every process this one starts when it ends - however it ends (2026-10-07, MANAGER #69).

THE PROBLEM. A render probe runs headless Chrome with subprocess.run(..., timeout=...). If the probe's
own python is killed (a ship cancelled, a lane closed, the selftest parent timing out), nothing kills
Chrome: tools/webull_board_probe.py left a headless Chrome running from 11:39 on 2026-10-06 with its
python parent long gone. subprocess's timeout only kills the DIRECT child, never Chrome's renderers.

THE FIX. On Windows, put this process in a job object with KILL_ON_JOB_CLOSE. Every process started
after that (Chrome and all its children, a selftest's copies of the probe) joins the job. The job's only
handle lives in this process, so the kernel closes it when this process ends by any route - normal exit,
exception, taskkill /F, a killed parent - and that kills every process still in the job.

install() is safe to call more than once and anywhere: it does nothing off Windows and never raises (a
probe must run even where a job cannot be created). Returns True when the job is in place.
"""
import os

_JOB = None


def install():
    global _JOB
    if _JOB is not None:
        return True
    if os.name != 'nt':
        return False
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

        class BASIC(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class IOC(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('ReadOperationCount', 'WriteOperationCount',
                                                       'OtherOperationCount', 'ReadTransferCount',
                                                       'WriteTransferCount', 'OtherTransferCount')]

        class EXTENDED(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IOC),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return False
        info = EXTENDED()
        info.BasicLimitInformation.LimitFlags = 0x2000          # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):   # 9 = extended
            return False
        if not k32.AssignProcessToJobObject(job, k32.GetCurrentProcess()):
            return False
        _JOB = job                                              # the one handle: held for this process's life
        return True
    except Exception:
        return False
