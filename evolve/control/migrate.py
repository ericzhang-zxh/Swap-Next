#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Move historical campaigns without changing frozen scientific inputs.

A complete, preflighted journal is saved before the first git move. Repeating
apply after interruption resumes that journal; after completion it is a no-op.
The separate links action changes only Markdown/HTML link targets. After another
worker pulls the tracked move, import-state copies only its own ignored historical
state. It records a private per-machine receipt under Git metadata. Stop local
legacy runners first; different existing evidence must be reconciled explicitly.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit, urlunsplit

try:
    from . import campaign_store as store
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import campaign_store as store


class MigrationError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(tmp, path)


class Migration:
    def __init__(self, project=None):
        self.project = Path(project or Path(__file__).resolve().parents[2]).resolve()
        self.campaigns = self.project / "campaigns"
        self.done = self.campaigns / "MOVED.json"
        self.pending = self.campaigns / ".migration-pending.json"
        self.seed = self.campaigns / "migration-seed.json"

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.project, text=True).strip()

    @contextmanager
    def store_root(self):
        old = store.PROJECT, store.CAMPAIGNS, store.HOSTS
        store.PROJECT, store.CAMPAIGNS, store.HOSTS = self.project, self.campaigns, self.campaigns / "hosts.json"
        try:
            yield
        finally:
            store.PROJECT, store.CAMPAIGNS, store.HOSTS = old

    def clean_paths(self, data):
        """Normalize newly imported state; historical tracked files stay exact."""
        text = data.decode("utf-8")
        text = text.replace(str(self.project) + "/", "")
        # Runtime artifacts also mention sibling scratch checkouts. Preserve
        # their location relative to this checkout rather than a host username.
        prefixes = [r"/home/[A-Za-z0-9_./+@-]+"]
        if self.project.parent != Path("/"):
            prefixes.append(re.escape(str(self.project.parent)) + r"/[A-Za-z0-9_./+@-]+")
        for pattern in prefixes:
            text = re.sub(pattern, lambda m: os.path.relpath(m[0], self.project), text)
        return text.encode("utf-8")

    def destination(self, name, seeds):
        parts = Path(name).parts
        if name.startswith("evolve/control/campaigns/"):
            c = parts[3]
            if c not in seeds:
                raise MigrationError(f"campaign missing from seed: {c}")
            return str(Path("campaigns", c, *parts[4:]))
        if name.startswith("benchmark/swap-standard/protocol") and name.endswith(".json"):
            c = json.loads((self.project / name).read_text())["campaign"]
            if c not in seeds:
                raise MigrationError(f"protocol campaign missing from seed: {c}")
            return f"campaigns/{c}/protocol.json"
        if name.startswith("results/"):
            c = parts[1]
            if c in ("swap-standard-evolve-2026-10-22", "swap-standard-integration-2026-10-22"):
                return str(Path("campaigns/swap-standard-2026-10-22/report", *parts[1:]))
            if c in seeds:
                return str(Path("campaigns", c, "report", *parts[2:]))
            if c == "pilot-summary.json":
                return str(Path("campaigns/_unassigned/report", *parts[1:]))
            raise MigrationError(f"report campaign missing from seed: {c}")
        if name.startswith("patches/"):
            c = parts[1]
            if c in seeds:
                return str(Path("campaigns", c, "patches", *parts[2:]))
            return str(Path("campaigns/_unassigned/patches", *parts[1:]))
        if name.startswith("benchmark/swap-standard/confirmations/") and parts[-1] == "ledger.json":
            c = parts[3]
            if c not in seeds:
                raise MigrationError(f"confirmation missing from seed: {c}")
            return f"campaigns/{c}/ledger/confirmation.json"
        return None

    def content(self, entry):
        source = self.project / entry["from"]
        data = source.read_bytes()
        if entry.get("candidate_id") is not None:
            obj = json.loads(data)[entry["candidate_id"]]
            data = (json.dumps(obj, indent=2) + "\n").encode()
        if entry["how"] == "copy-rewritten":
            data = self.clean_paths(data)
        return data

    def plan(self):
        if self.done.exists():
            return json.loads(self.done.read_text())
        if self.pending.exists():
            return json.loads(self.pending.read_text())
        seeds = json.loads(self.seed.read_text())["campaigns"]
        tracked = self.git("ls-files", "-z").split("\0")
        tracked = [x for x in tracked if x]
        moves = []
        def add(source, target, how, note, **extra):
            source = str(source)
            op = {"from": source, "to": target, "how": how, "note": note, **extra}
            path = self.project / source
            if path.is_file():
                op["sha256"] = digest(path.read_bytes())
            if how in ("copy", "copy-rewritten"):
                op["output_sha256"] = digest(self.content(op))
            moves.append(op)
        legacy_paths = []
        for name in sorted(tracked):
            target = self.destination(name, seeds)
            if target is not None:
                add(name, target, "git-mv", "Tracked bytes are preserved exactly.")
                if b"/home/" in (self.project / name).read_bytes():
                    legacy_paths.append({"from": name, "to": target, "note": "Existing host paths retained to preserve historical bytes; normalize only in a separate evidence-aware commit."})
        destinations = {x["to"]: x for x in moves}
        policy_root = self.project / "evolve/control/campaigns"
        for path in sorted(policy_root.glob("*/*")):
            relative = str(path.relative_to(self.project))
            if path.is_file() and relative not in tracked:
                c = path.parent.name
                if c not in seeds:
                    raise MigrationError(f"untracked campaign missing from seed: {c}")
                add(relative, f"campaigns/{c}/{path.name}", "copy-rewritten", "Untracked controller policy imported; host paths normalized.")
        for directory in sorted((self.project / "evolve/swap-standard").glob("state-*")):
            c = "swap-standard-2026-10-22" if directory.name == "state-layout-v1" else directory.name.removeprefix("state-")
            if c not in seeds:
                raise MigrationError(f"ledger campaign missing from seed: {c}")
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.name in (".lock",) or path.name.endswith(".tmp"):
                    continue
                relative = str(path.relative_to(directory))
                target = f"campaigns/{c}/ledger/" + ("tasks/" if path.name.startswith("task-") and path.suffix == ".json" else "") + relative
                data = path.read_bytes()
                how = "copy-rewritten" if self.clean_paths(data) != data else "copy"
                add(str(path.relative_to(self.project)), target, how, "Runtime ledger imported; absolute host paths normalized when present.")
        for directory in sorted((self.project / "evolve/control/state").glob("*")):
            if not directory.is_dir() or directory.name not in seeds:
                continue
            c = directory.name
            registry = directory / "candidates.json"
            records = json.loads(registry.read_text()) if registry.exists() else {}
            for cid in sorted(records):
                store._name(cid, "candidate")
                if records[cid].get("id") != cid:
                    raise MigrationError(f"candidate id differs from registry key: {c}/{cid}")
                add(str(registry.relative_to(self.project)), f"campaigns/{c}/candidates/{cid}.json", "copy-rewritten", "Candidate registry split into per-candidate records; paths normalized.", candidate_id=cid)
                for path in sorted((directory / cid).rglob("*")):
                    if not path.is_file() or path.name == ".lock" or path.name.endswith(".tmp"):
                        continue
                    if path.name == "candidate.patch":
                        target = f"campaigns/{c}/patches/{cid}.patch"
                        export = destinations.get(target)
                        exported = self.project / export["from"] if export else self.project / target
                        if not exported.is_file() or exported.read_bytes() != path.read_bytes():
                            raise MigrationError(f"candidate patch differs from exported patch: {c}/{cid}")
                        add(str(path.relative_to(self.project)), str(path.relative_to(self.project)), "left-in-place", f"Verified byte-identical to {target}; exported patch is moved separately.")
                        continue
                    target = f"campaigns/{c}/candidates/{cid}/" + str(path.relative_to(directory / cid))
                    add(str(path.relative_to(self.project)), target, "copy-rewritten", "Candidate artifact imported; host paths normalized.")
            events = directory / "events.jsonl"
            if events.exists():
                add(str(events.relative_to(self.project)), f"campaigns/{c}/ledger/events.jsonl", "copy-rewritten", "Controller events imported; host paths normalized.")
            stop = directory / "STOP"
            if stop.exists():
                add(str(stop.relative_to(self.project)), f"campaigns/{c}/STOP", "copy", "Campaign STOP retained; remains gitignored.", ignored=True)
            imported = {x["from"] for x in moves}
            for path in sorted(directory.iterdir()):
                relative = str(path.relative_to(self.project))
                if relative in imported or path.name in records or path.name == ".lock":
                    continue
                add(relative, relative, "left-in-place", "Historical raw controller evidence remains at its original location.")
        patterns = ["benchmark/xswap/protocol.json", "benchmark/xswap-p123/protocol.json", "benchmark/xswap-structure/protocol.json", "benchmark/xswap-hole-probe/protocol.json", "benchmark/kernel/protocol.json", "evolve/xswap/state-layout-v1", "evolve/kernel/state-layout-v1", "evolve/xswap-structure/state-layout-v1", "benchmark/xswap-structure/state-*", "benchmark/swap-standard/runs", "benchmark/swap-standard/evaluations"]
        for pattern in patterns:
            for path in sorted(self.project.glob(pattern)):
                name = str(path.relative_to(self.project))
                add(name, name, "left-in-place", "Shared older-suite protocol or raw runtime evidence retains its original path.")
        records = {}
        for c, seed in sorted(seeds.items()):
            protocol = next((self.project / x["from"] for x in moves if x["to"] == f"campaigns/{c}/protocol.json"), None)
            ref = seed.get("protocol_ref")
            if protocol is None and ref:
                protocol = self.project / ref
            p = json.loads(protocol.read_text()) if protocol and protocol.is_file() else {}
            budget = p.get("budget", {})
            times = []
            def timestamps(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ("time_unix", "started", "finished", "created", "created_unix", "completed_unix") and isinstance(v, (float, int)) and 946684800 < v < 4102444800:
                            times.append(v)
                        elif isinstance(v, (list, dict)):
                            timestamps(v)
                elif isinstance(obj, list):
                    for item in obj:
                        timestamps(item)
            for op in moves:
                if op["to"].startswith(f"campaigns/{c}/ledger/") and op["from"].endswith((".json", ".jsonl")):
                    data = (self.project / op["from"]).read_text()
                    try:
                        if op["from"].endswith(".jsonl"):
                            for line in data.splitlines():
                                if line.strip(): timestamps(json.loads(line))
                        else: timestamps(json.loads(data))
                    except ValueError as e:
                        raise MigrationError(f"invalid ledger {op['from']}: {e}") from e
            fallback = re.search(r"\d{4}-\d{2}-\d{2}|\d{8}", c)
            date = fallback[0] if fallback else "2026-10-27"
            if len(date) == 8: date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
            first = datetime.fromtimestamp(min(times), timezone.utc).date().isoformat() if times else date
            last = datetime.fromtimestamp(max(times), timezone.utc).date().isoformat() if times else date
            records[c] = {"campaign": c, "status": seed["status"], "line": seed["line"], "baseline_from": seed.get("baseline_from"), "machine": seed["machine"], "opened": first, "closed": last if seed["status"] == "closed" else None, "budget": {"guest_attempts": budget.get("guest_attempts", 0), "wall_seconds": budget.get("wall_seconds", 0), "probe_guest_attempts": 0, "approved_over_cap": None}}
            if ref:
                records[c].update(protocol_ref=ref, protocol_sha256=digest((self.project / ref).read_bytes()))
            with self.store_root():
                store._check(c, records[c])
        sources = [x["from"] for x in moves if x["how"] == "git-mv"]
        dirty = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *sources], cwd=self.project)
        if dirty.returncode:
            raise MigrationError("tracked migration sources have uncommitted changes; commit or reconcile them before pinning evidence")
        result = {"pre_migration_commit": self.git("rev-parse", "HEAD"), "moves": moves, "campaigns": records, "legacy_absolute_paths": legacy_paths}
        self.preflight(result)
        return result

    def preflight(self, plan):
        targets = set()
        for op in plan["moves"]:
            if op["how"] == "left-in-place":
                continue
            source, target = self.project / op["from"], self.project / op["to"]
            if target.resolve().is_relative_to(self.campaigns.resolve()) is False:
                raise MigrationError(f"destination escapes campaigns: {op['to']}")
            if op["to"] in targets:
                raise MigrationError(f"duplicate destination: {op['to']}")
            targets.add(op["to"])
            if source.exists():
                if not source.is_file() or digest(source.read_bytes()) != op["sha256"]:
                    raise MigrationError(f"source changed since migration was planned: {op['from']}")
                if target.exists():
                    expected = op.get("output_sha256", op["sha256"])
                    copied = op["how"] in ("copy", "copy-rewritten")
                    if (not self.pending.exists() and not copied) or digest(target.read_bytes()) != expected:
                        raise MigrationError(f"destination already exists: {op['to']}")
            elif op["how"] != "git-mv" or not target.is_file() or digest(target.read_bytes()) != op["sha256"]:
                raise MigrationError(f"missing source and verified destination: {op['from']}")
        for c, record in plan["campaigns"].items():
            target = self.campaigns / c / "campaign.json"
            if target.exists() and (not self.pending.exists() or json.loads(target.read_text()) != record):
                raise MigrationError(f"campaign destination already exists: {c}/campaign.json")

    def move(self, entry):
        source, target = self.project / entry["from"], self.project / entry["to"]
        if not source.exists():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", "--", entry["from"], entry["to"])

    def apply(self):
        if self.done.exists():
            print("already migrated")
            return
        plan = self.plan()
        self.preflight(plan)
        if not self.pending.exists():
            dump(self.pending, plan)
        for op in plan["moves"]:
            if op["how"] == "git-mv":
                self.move(op)
        with self.store_root():
            for op in plan["moves"]:
                if op["how"] in ("copy", "copy-rewritten"):
                    target = self.project / op["to"]
                    if op.get("candidate_id"):
                        record = json.loads(self.content(op))
                        store.write_candidate(Path(op["to"]).parts[1], record)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(self.content(op))
                    if not op.get("ignored"):
                        self.git("add", "-f", "--", op["to"])
            for c, record in plan["campaigns"].items():
                store.write(c, record)
                self.git("add", "--", f"campaigns/{c}/campaign.json")
        for root in ("evolve/control/campaigns", "results", "patches"):
            base = self.project / root
            if base.exists():
                for path in sorted(base.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                    if path.is_dir() and not any(path.iterdir()): path.rmdir()
        for root in ("results", "patches"):
            path = self.project / root / "README.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("Moved to campaigns/<campaign>/ on 2026-10-27; see campaigns/MOVED.json.\n")
            self.git("add", "--", f"{root}/README.md")
        dump(self.done, plan)
        self.pending.unlink()
        self.git("add", "--", "campaigns/MOVED.json")
        print(f"migrated {len(plan['campaigns'])} campaigns; {len(plan['moves'])} source records")

    def state_paths(self, machine):
        """Private, per-machine receipt and journal; neither travels through git."""
        store._name(machine, "machine")
        common = Path(self.git("rev-parse", "--git-common-dir"))
        if not common.is_absolute(): common = self.project / common
        private = common.resolve() / "swap-next-migration"
        return private / f"{machine}.json", private / f"{machine}.pending.json"

    @staticmethod
    def check_state_identity(value, campaign, source):
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            if isinstance(row, dict) and row.get("campaign", campaign) != campaign:
                raise MigrationError(f"campaign identity mismatch in {source}")

    def local_state_moves(self, machine):
        """Plan local imports without replacing any different migrated evidence."""
        moves = []
        identities = {}
        def owner(campaign):
            if campaign not in identities:
                with self.store_root(): record = store.load(campaign)
                if record["machine"] != machine:
                    raise MigrationError(f"local campaign {campaign} belongs to machine {record['machine']}, not {machine}")
                identities[campaign] = record
        def add(path, target, candidate_id=None, exact=False, ignored=False):
            if path.is_symlink() or not path.resolve().is_relative_to(self.project):
                raise MigrationError(f"local state source escapes checkout: {path.name}")
            relative = str(path.relative_to(self.project))
            op = {"from": relative, "to": target, "how": "copy" if exact else "copy-rewritten",
                  "note": "Machine-local historical state imported after tracked layout migration.",
                  "sha256": digest(path.read_bytes())}
            if candidate_id is not None: op["candidate_id"] = candidate_id
            if ignored: op["ignored"] = True
            if path.suffix in (".json", ".jsonl"):
                data = path.read_text()
                values = [json.loads(line) for line in data.splitlines() if line.strip()] if path.suffix == ".jsonl" else [json.loads(data)]
                for value in values:
                    if candidate_id is not None: value = value[candidate_id]
                    self.check_state_identity(value, Path(target).parts[1], relative)
            op["output_sha256"] = digest(self.content(op))
            existing = self.project / target
            if existing.is_file() and digest(existing.read_bytes()) != op["output_sha256"]:
                op["retained_sha256"] = digest(existing.read_bytes())
            moves.append(op)
        for directory in sorted((self.project / "evolve/swap-standard").glob("state-*")):
            files = [p for p in sorted(directory.rglob("*")) if p.is_file() and p.name != ".lock" and not p.name.endswith(".tmp")]
            if not files: continue
            campaign = "swap-standard-2026-10-22" if directory.name == "state-layout-v1" else directory.name.removeprefix("state-")
            owner(campaign)
            for path in files:
                task = "tasks/" if path.name.startswith("task-") and path.suffix == ".json" else ""
                target = f"campaigns/{campaign}/ledger/" + task + str(path.relative_to(directory))
                add(path, target)
        for directory in sorted((self.project / "evolve/control/state").glob("*")):
            if not directory.is_dir(): continue
            registry = directory / "candidates.json"
            events, stop = directory / "events.jsonl", directory / "STOP"
            if not any(p.exists() for p in (registry, events, stop)): continue
            campaign = directory.name
            owner(campaign)
            records = json.loads(registry.read_text()) if registry.exists() else {}
            if not isinstance(records, dict): raise MigrationError(f"candidate registry is not an object: {campaign}")
            for cid, record in sorted(records.items()):
                store._name(cid, "candidate")
                if not isinstance(record, dict) or record.get("id") != cid:
                    raise MigrationError(f"candidate id differs from registry key: {campaign}/{cid}")
                add(registry, f"campaigns/{campaign}/candidates/{cid}.json", candidate_id=cid)
                for path in sorted((directory / cid).rglob("*")):
                    if not path.is_file() or path.name == ".lock" or path.name.endswith(".tmp"): continue
                    if path.name == "candidate.patch":
                        exported = self.project / "patches" / campaign / f"{cid}.patch"
                        if exported.exists() and exported.read_bytes() != path.read_bytes():
                            raise MigrationError(f"local candidate patch conflicts with legacy export: {campaign}/{cid}")
                        add(path, f"campaigns/{campaign}/patches/{cid}.patch", exact=True)
                    else:
                        add(path, f"campaigns/{campaign}/candidates/{cid}/" + str(path.relative_to(directory / cid)))
            if events.exists(): add(events, f"campaigns/{campaign}/ledger/events.jsonl")
            if stop.exists(): add(stop, f"campaigns/{campaign}/STOP", exact=True, ignored=True)
        self.preflight_state(moves, machine)
        return moves

    def state_equivalent(self, op, data):
        expected = self.content(op)
        return (data if op["how"] == "copy" else self.clean_paths(data)) == expected

    def preflight_state(self, moves, machine):
        targets = set()
        for op in moves:
            target = self.project / op["to"]
            source = self.project / op["from"]
            if not target.resolve().is_relative_to(self.campaigns.resolve()):
                raise MigrationError(f"state destination escapes campaigns: {op['to']}")
            if op["to"] in targets: raise MigrationError(f"duplicate state destination: {op['to']}")
            targets.add(op["to"])
            with self.store_root(): record = store.load(Path(op["to"]).parts[1])
            if record["machine"] != machine: raise MigrationError(f"state destination belongs to another machine: {op['to']}")
            if digest(source.read_bytes()) != op["sha256"]:
                raise MigrationError(f"local state source changed during import: {op['from']}")
            if target.exists() and (not target.is_file() or not self.state_equivalent(op, target.read_bytes())):
                raise MigrationError(f"local state conflicts with migrated destination: {op['to']}; reconcile evidence before importing")

    def import_state_file(self, op):
        """Write a missing artifact atomically; equivalent existing bytes stay put."""
        source, target = self.project / op["from"], self.project / op["to"]
        if digest(source.read_bytes()) != op["sha256"]:
            raise MigrationError(f"local state source changed during import: {op['from']}")
        data = self.content(op)
        if target.exists():
            if not self.state_equivalent(op, target.read_bytes()):
                raise MigrationError(f"local state destination changed during import: {op['to']}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".migration-tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        # Recovery may encounter bytes copied just before the prior process
        # died at git-add. Stage equivalent files as well as newly copied ones.
        if not op.get("ignored"): self.git("add", "-f", "--", op["to"])

    def import_state(self):
        """Import this worker's ignored state even after MOVED arrives via git."""
        if not self.done.exists(): raise MigrationError("apply tracked layout migration before import-state")
        manifest = json.loads(self.done.read_text())
        with self.store_root(): machine = store.current_machine()
        receipt_path, journal = self.state_paths(machine)
        if journal.exists():
            job = json.loads(journal.read_text())
            if job.get("machine") != machine or job.get("pre_migration_commit") != manifest["pre_migration_commit"]:
                raise MigrationError("state import journal has mismatched machine or layout identity")
            moves = job["sources"]
            self.preflight_state(moves, machine)
        else:
            moves = self.local_state_moves(machine)
            job = {"machine": machine, "pre_migration_commit": manifest["pre_migration_commit"], "sources": moves}
            if receipt_path.exists() and json.loads(receipt_path.read_text()) == job:
                print("already imported local state")
                return
            # No receipt or journal is written until all local source identities
            # and every destination have passed conflict checks.
            dump(journal, job)
        new = [op for op in moves if not (self.project / op["to"]).exists()]
        for op in moves: self.import_state_file(op)
        # Keep provenance for new tracked imports alongside the immutable layout
        # mapping. The receipt/journal remain private Git metadata per machine.
        imported = {"machine": machine, "sources": [op for op in moves if not op.get("ignored")]}
        imports = manifest.get("state_imports", [])
        if imported["sources"] and imported not in imports:
            imports.append(imported)
            manifest["state_imports"] = imports
            dump(self.done, manifest)
            self.git("add", "--", "campaigns/MOVED.json")
        dump(receipt_path, job)
        journal.unlink()
        print(f"imported {len(new)} machine-local state files for {machine}")

    def links(self):
        if not self.done.exists():
            raise MigrationError("apply migration before rewriting links")
        manifest = json.loads(self.done.read_text())
        mapping = {x["from"]: x["to"] for x in manifest["moves"] if x["how"] == "git-mv"}
        changed = set(manifest.get("rewritten_links", []))
        writes = []
        for old, new in mapping.items():
            path = self.project / new
            if "/report/" not in new or path.suffix.lower() not in (".md", ".html"):
                continue
            text = path.read_bytes().decode("utf-8")
            def target(value):
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
                    return value
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(old), unquote(parsed.path)))
                destination = mapping.get(resolved)
                if destination is None:
                    # Directory links move when all their descendants share the
                    # same translated directory. Unmoved evidence still needs
                    # a different relative path from the new report location.
                    descendants = set()
                    prefix = resolved.rstrip("/") + "/"
                    for source, dest in mapping.items():
                        if source.startswith(prefix):
                            suffix = source[len(prefix):]
                            if dest.endswith("/" + suffix):
                                descendants.add(dest[:-len(suffix)].rstrip("/"))
                    destination = next(iter(descendants)) if len(descendants) == 1 else resolved
                relative = posixpath.relpath(destination, posixpath.dirname(new))
                if parsed.path.endswith("/"):
                    relative += "/"
                return urlunsplit(("", "", relative, parsed.query, parsed.fragment))
            # Recompute from the pre-migration bytes each time: a relative link
            # may resolve to a different old file after the first rewrite.
            original = subprocess.check_output(["git", "show", f"{manifest['pre_migration_commit']}:{old}"], cwd=self.project).decode()
            updated = re.sub(r"(\]\(<?)([^\s)>]+)(>?[^)]*\))", lambda m: m[1] + target(m[2]) + m[3], original)
            updated = re.sub(r'''((?:href|src)\s*=\s*["'])([^"']+)(["'])''', lambda m: m[1] + target(m[2]) + m[3], updated, flags=re.I)
            # Never overwrite later prose edits. The idempotent output is
            # accepted, but any unrelated current change requires review.
            if text not in (original, updated):
                raise MigrationError(f"report changed beyond migration links: {new}")
            if updated != original:
                changed.add(new)
            if updated != text:
                writes.append((path, updated))
        for path, updated in writes:
            path.write_bytes(updated.encode("utf-8"))
        ordered = sorted(changed)
        if ordered != manifest.get("rewritten_links", []):
            manifest["rewritten_links"] = ordered
            dump(self.done, manifest)
        print(f"rewritten link targets in {len(ordered)} reports")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "links", "import-state"))
    args = parser.parse_args(argv)
    tool = Migration()
    try:
        if args.action == "plan":
            print(json.dumps(tool.plan(), indent=2))
        elif args.action == "apply":
            tool.apply()
        elif args.action == "import-state":
            tool.import_state()
        else:
            tool.links()
    except (MigrationError, store.CampaignError, OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"migration refused: {error}\n")


if __name__ == "__main__":
    main()
