#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Validate recorded settings against authoritative suite source; no runtime work."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent

def validate(base=BASE):
    manifest = json.loads((base / "settings.json").read_text())
    errors = []
    for name, expected in manifest["source_sha256"].items():
        path = base / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append("settings source drift: " + name)
    for suite, expected in manifest["protocol_snapshots"].items():
        if json.loads((base / suite / "protocol.json").read_text()) != expected:
            errors.append("protocol snapshot drift: " + suite)
    return errors

if __name__ == "__main__":
    errors = validate()
    if errors:
        raise SystemExit("\n".join(errors))
    print("Recorded benchmark settings match source fingerprints; no runtime validation implied.")
