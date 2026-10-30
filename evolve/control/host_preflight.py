#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host RAM check used before a swap-standard guest is reserved or launched.

The numbers are the ones in benchmark/swap-standard/run.py. MemAvailable is
read from /proc/meminfo in KiB. A TCG guest needs guest_mib + 1024 MiB. A KVM
guest needs 10240 MiB. Available memory equal to that threshold is enough;
only a strictly smaller value refuses. This module is not a measurement input.
The workflow and runner call it, and those call sites are what the calibration
fingerprint hashes.
"""
import importlib.util
import os
from pathlib import Path
import re
import sys

MEMINFO = Path("/proc/meminfo")
DISK_MESSAGE = "need 24 GiB free disk"
_RUN = None


def mem_available_kib(text=None):
    raw = MEMINFO.read_text() if text is None else text
    match = re.search(r"MemAvailable:\s+(\d+)", raw)
    if not match:
        raise OSError("MemAvailable missing from host meminfo")
    return int(match.group(1))


def need_kib(tcg, guest_mib):
    return (int(guest_mib) + 1024) * 1024 if tcg else 10 * 1024**2


def refusal_for(available_kib, tcg, guest_mib):
    """Return run.py's host-RAM message, or None when available_kib is enough."""
    if isinstance(available_kib, bool) or not isinstance(available_kib, int):
        raise TypeError("available memory")
    need = need_kib(tcg, guest_mib)
    if available_kib < need:
        return f"need {need // 1024} MiB available host RAM"
    return None


def _guest_shape(env):
    """guest_shape from run.py. A script launch puts its directory on sys.path;
    loading the file directly does not, so evidence and validity would not import."""
    global _RUN
    if _RUN is None:
        path = Path(__file__).resolve().parents[2] / "benchmark/swap-standard/run.py"
        bench = str(path.parent)
        name = "swap_standard_host_preflight_run"
        added = bench not in sys.path
        if added:
            sys.path.insert(0, bench)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
        finally:
            if added and bench in sys.path:
                sys.path.remove(bench)
        _RUN = module
    return _RUN.guest_shape(env)


def refusal(env=None):
    """Refusal for the environment run.py will see, or None when RAM is sufficient."""
    try:
        tcg, guest_mib, _, _ = _guest_shape(os.environ if env is None else env)
        return refusal_for(mem_available_kib(), tcg, guest_mib)
    except (OSError, ValueError, TypeError) as exc:
        text = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return "host RAM preflight failed: " + text
