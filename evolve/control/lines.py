#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render campaign and line indexes from recorded identities and outcomes."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

try:
    from . import campaign_store as store
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import campaign_store as store

PROJECT = Path(__file__).resolve().parents[2]


@contextmanager
def project_store(project):
    old = store.PROJECT, store.CAMPAIGNS, store.HOSTS
    store.PROJECT = project
    store.CAMPAIGNS = project / "campaigns"
    store.HOSTS = store.CAMPAIGNS / "hosts.json"
    try:
        yield
    finally:
        store.PROJECT, store.CAMPAIGNS, store.HOSTS = old


def cell(value):
    return str(value if value is not None else "—").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def baseline(project, record):
    directory = project / "campaigns" / record["campaign"]
    protocol = directory / "protocol.json"
    if not protocol.exists() and record.get("protocol_ref"):
        protocol = (project / record["protocol_ref"]).resolve()
        if not protocol.is_relative_to(project):
            raise store.CampaignError(f"protocol_ref escapes project: {record['campaign']}")
    if protocol.exists():
        value = json.loads(protocol.read_text()).get("baseline_commit")
        if value:
            return value
    policy = directory / "policy.json"
    return json.loads(policy.read_text()).get("seed_ref") if policy.exists() else None


def report(directory):
    for name in ("REPORT.md", "README.md"):
        if (directory / "report" / name).is_file():
            return "report/" + name
    return None


def void_rows(project, campaign):
    """Void receipts from the campaign ledger. Missing ledger means none."""
    path = Path(project) / "campaigns" / campaign / "ledger" / "ledger.json"
    if not path.is_file():
        return []
    try:
        rows = json.loads(path.read_text())
    except ValueError as exc:
        raise store.CampaignError(f"unreadable ledger for {campaign}: {exc}") from exc
    if not isinstance(rows, list):
        raise store.CampaignError(f"ledger for {campaign} is not a list")
    found = []
    for row in rows:
        if not isinstance(row, dict) or row.get("action") != "void-calibration":
            continue
        for key in ("id", "attempt_id", "tier", "reason", "guests"):
            if key not in row:
                raise store.CampaignError(f"void receipt {row.get('id')!r} missing {key}")
        guests = row["guests"]
        named = isinstance(guests, list) and all(isinstance(guest, dict) and isinstance(guest.get("id"), str) and guest["id"] for guest in guests)
        if not named:
            raise store.CampaignError(f"void receipt {row.get('id')!r} guests must name an id")
        found.append(row)
    return found


def _void_section(rows):
    lines = ["Voided calibration attempts:", "",
             "| Attempt | Tier | Receipt | Guests | Reason |",
             "| --- | --- | --- | --- | --- |"]
    for row in rows:
        guests = ", ".join(f"{guest.get('id')} {guest.get('status')}" for guest in row["guests"]) or None
        fields = [row["attempt_id"], row["tier"], row["id"], guests, row["reason"]]
        lines.append("| " + " | ".join(cell(value) for value in fields) + " |")
    return lines


def render(project=None):
    """Return relative output filenames and complete contents; write nothing."""
    project = Path(project or PROJECT).resolve()
    root = project / "campaigns"
    with project_store(project):
        records = [store.load(path.parent.name) for path in sorted(root.glob("*/campaign.json"))]
        records.sort(key=lambda r: (r["opened"], r["campaign"]))
        baselines = {r["campaign"]: baseline(project, r) for r in records}
        candidates = {r["campaign"]: store.candidates(r["campaign"]) for r in records}
    line_names = sorted({r["line"] for r in records})
    index = ["# Campaigns", "", "Generated from campaign identities, protocols and candidate outcomes.", ""]
    if line_names:
        index += ["Lines: " + " · ".join(f"[{line}](lines/{line}.md)" for line in line_names), ""]
    index += ["| Campaign | Status | Line | Machine | Opened | Closed | Baseline |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for record in records:
        name = record["campaign"]
        target = report(root / name) or "campaign.json"
        fields = [f"[{name}]({name}/{target})", record["status"], f"[{record['line']}](lines/{record['line']}.md)",
                  record["machine"], record["opened"], record["closed"], baselines[name]]
        index.append("| " + " | ".join(cell(v) for v in fields) + " |")
    outputs = {"campaigns/README.md": "\n".join(index) + "\n"}
    for line in line_names:
        history = [r for r in records if r["line"] == line]
        anchors = {r["line_anchor_commit"] for r in history if r.get("line_anchor_commit")}
        if len(anchors) > 1:
            raise store.CampaignError(f"conflicting anchors on line {line}")
        anchor = next(iter(anchors), None)
        text = [f"# {line} line", "", "Campaigns in opening order, with their recorded baselines and outcomes.", ""]
        if anchor:
            text += [f"Fixed line anchor: `{anchor}`. This is an identity, not an inferred root-relative performance result.", ""]
        for record in history:
            name = record["campaign"]
            text += [f"## {name}", "", f"Status: {record['status']}; machine: {record['machine']}; opened: {record['opened']}; closed: {record['closed'] or '—'}.", "",
                     f"Baseline: `{baselines[name] or 'unknown'}`.", ""]
            origin = record["baseline_from"]
            if origin:
                evidence = origin["evidence"]
                source = origin["campaign"]
                text += [f"Baseline origin: [{source}/{origin['candidate']}](../{source}/candidates/{origin['candidate']}.json), commit `{origin['commit']}`.", ""]
                if evidence["kind"] == "fast_pass":
                    text += [f"Origin evidence: [fast-pass ledger](../{source}/ledger/ledger.json), row `{evidence['ledger_row']}`.", ""]
                else:
                    path = Path(evidence["report"])
                    if path.parts and path.parts[0] == "campaigns":
                        target = "../" + str(Path(*path.parts[1:]))
                    else:
                        target = "../../" + str(path)
                    text += [f"Origin evidence: [correctness review]({target}).", ""]
            else:
                text += ["Baseline origin: upstream or imported reference.", ""]
            target = report(root / name)
            if target:
                text += [f"[Campaign report](../{name}/{target})", ""]
            text += ["| Candidate | Status | Reason |", "| --- | --- | --- |"]
            for cid, candidate in sorted(candidates[name].items()):
                fields = [f"[{cid}](../{name}/candidates/{cid}.json)", candidate.get("status", "unknown"), candidate.get("reason", "—")]
                text.append("| " + " | ".join(cell(v) for v in fields) + " |")
            voids = void_rows(project, name)
            if voids:
                text += ["", *_void_section(voids)]
            text += [""]
        latest = history[-1]
        text += [f"Current baseline: {baselines[latest['campaign']] or 'unknown'} ({latest['campaign']})"]
        outputs[f"campaigns/lines/{line}.md"] = "\n".join(text) + "\n"
    return outputs


def generate(project=None):
    """Regenerate indexes atomically; unchanged files retain their timestamps."""
    project = Path(project or PROJECT).resolve()
    outputs = render(project)  # Validate every input before changing any index.
    for relative, content in sorted(outputs.items()):
        path = project / relative
        data = content.encode("utf-8")
        if path.exists() and path.read_bytes() == data:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    return outputs


if __name__ == "__main__":
    for name in generate():
        print(name)
