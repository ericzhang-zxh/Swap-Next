#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fill story.json "patches" with verbatim hunks of each stage's incremental diff.

Excerpts come from `git diff <parent> <child>` in the linux object store; every
excerpt line is checked against that diff. The full cumulative patch stays in
campaigns/<c>/patches/ and is cited as the pinned source.
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = Path(__file__).resolve().parents[1].name
STAGES = (
    ("M1", "xswap-fast-in-v1", "5e84ca928deeacb4eee656806a003f27d1eca82f",
     "5cde9eaa28a2cd79f640e8932c4572573ab2323a",
     "allocator-first sync swap-in and streak-gated readahead"),
    ("M2", "xswap-mthp-reassembly-v1", "5cde9eaa28a2cd79f640e8932c4572573ab2323a",
     "53e02e8615a30d927daf77e5f1f7a7182a1c6ec5",
     "zswap mTHP residency check and subpage zswap_load"),
    ("M3", "xswap-radix-hole-reclaim-v1", "53e02e8615a30d927daf77e5f1f7a7182a1c6ec5",
     "2c1ddb537fd926482ab4845bd7d5be116b4523ac",
     "two-level cluster_dir chunks and interior hole reclaim"),
)
MAX_LINES = 80


def hunks(diff):
    out, header, cur = [], [], None
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            header, cur = [], None
            continue
        if cur is None and (line.startswith("--- ") or line.startswith("+++ ")):
            header.append(line)
            continue
        if line.startswith("@@"):
            cur = {"file": list(header), "lines": [line]}
            out.append(cur)
        elif cur is not None and line[:1] in (" ", "+", "-", "\\"):
            cur["lines"].append(line)
    return out


def excerpt(parent, child):
    diff = subprocess.check_output(["git", "-C", str(ROOT / "linux"), "diff", parent, child], text=True)
    all_hunks = hunks(diff)
    ranked = sorted(range(len(all_hunks)),
                    key=lambda i: -sum(l.startswith("+") for l in all_hunks[i]["lines"]))
    chosen, used = [], 0
    for i in ranked:
        size = len(all_hunks[i]["lines"])
        if used + size > MAX_LINES and chosen:
            continue
        chosen.append(i)
        used += size
    text, last = [], None
    for i in sorted(chosen):
        h = all_hunks[i]
        if h["file"] != last:
            text += h["file"]
            last = h["file"]
        text += h["lines"]
    diff_lines = set(diff.splitlines())
    assert all(l in diff_lines for l in text), "excerpt line not in real diff"
    return "\n".join(text) + "\n"


def main():
    path = ROOT / "campaigns" / CAMPAIGN / "report/story.json"
    story = json.loads(path.read_text())
    story["patches_title"] = "Core kernel patches (M1 \u2192 M2 \u2192 M3)"
    story["patches_lead"] = ("Verbatim largest hunks of each stage's incremental git diff; "
                             "full cumulative patches are the pinned sources.")
    story["patches"] = [{
        "takeaway": f"{m} {child[:8]}: {what} (git diff {parent[:8]}..{child[:8]})",
        "source": f"campaigns/{CAMPAIGN}/patches/{cand}.patch",
        "patch": excerpt(parent, child)} for m, cand, parent, child, what in STAGES]
    path.write_text(json.dumps(story, indent=2) + "\n")


if __name__ == "__main__":
    main()
