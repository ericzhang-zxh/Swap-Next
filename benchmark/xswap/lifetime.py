# SPDX-License-Identifier: GPL-2.0-only
import ctypes,os,signal
SUPERVISOR_PID=os.getpid()
def bind_child_to_parent():
    """Child-only preexec hook: kill this stage if its supervisor disappears."""
    parent=SUPERVISOR_PID
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.prctl(1,signal.SIGKILL,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),"PR_SET_PDEATHSIG")
    if os.getppid()!=parent:os.kill(os.getpid(),signal.SIGKILL)
