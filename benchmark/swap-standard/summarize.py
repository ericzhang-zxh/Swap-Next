#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Summarize retained runs without dropping failures or inferring acceptance."""
import argparse
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=BASE / "runs")
    args = parser.parse_args()
    records = []
    for directory in sorted(args.runs.iterdir()):
        if not directory.is_dir():
            continue
        result = directory / "result.json"
        if not result.exists():
            records.append({"run": directory.name, "status": "incomplete", "performance_accepted": False})
            continue
        data = json.loads(result.read_text())
        records.append({"run": directory.name, "status": "pass" if data.get("integration_pass") else "fail",
                        "build": data.get("build"), "source_commit": data.get("source_commit"),
                        "kernel_sha256": data.get("image_sha256"),
                        "guest_image_sha256": data.get("guest_provenance", {}).get("image_sha256"),
                        "stop_reason": data.get("stop_reason"),
                        "interruption_reason": json.loads((directory / "interruption.json").read_text()).get("reason") if (directory / "interruption.json").exists() else None, "backend": data.get("backend"),
                        "workload": data.get("workload"), "wall_seconds": data.get("wall_seconds"),
                        "failed_gates": [name for name, passed in data.get("gates", {}).items() if passed is not True],
                        "metrics": data.get("metrics", {}), "serial_sha256": data.get("serial_sha256"),
                        "has_reanalysis": (directory / "reanalysis.json").exists(), "performance_accepted": False})
    print(json.dumps({"runs": records, "count": len(records), "calibrated": False,
                      "performance_accepted": False}, indent=2))


if __name__ == "__main__":
    main()
