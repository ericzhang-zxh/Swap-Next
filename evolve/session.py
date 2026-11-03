#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Durable contributor actions around the existing controller and evaluator.

The active contributor supplies ideas, edits, review and explanation. This
module dispatches only framework-owned argv and derives progress from retained
artifacts. It never owns a second budget or treats an agent's "done" as evidence.
plan(snapshot) is pure; Session accepts injected snapshot/executor functions
for guest-free fixtures. The production CLI has no bypass switches.
"""
import argparse
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "control"))
import comparisons
import comparison_runtime
import calibration_cache
import correctness_proof
import delivery
import research
import reviews
import ownership

NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
OBJECT = re.compile(r"[0-9a-f]{40}")
TERMINAL_FAST = {"FAST_PASS", "REGRESSION", "NEEDS_REVIEW", "INCONCLUSIVE"}
FAILED = {"INCOMPLETE", "INTERRUPTED", "BLOCKED", "CORRECTNESS_FAIL", "CALIBRATION_NOISY"}
MEASUREMENT_COMMANDS = {"calibrate", "evaluate", "compare-calibrate", "compare"}
ALLOWED_TIERS = ["probe", "fast"]


class SessionError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise SessionError(message)


def name(value, what):
    need(isinstance(value, str) and NAME.fullmatch(value), "invalid " + what)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(), parse_constant=lambda value: _invalid(value))


def _invalid(value):
    raise SessionError("non-finite JSON: " + value)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    with tmp.open("w") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def action(stage, kind="agent", *, reason="", identity=None, expects=None, command=None, **parameters):
    result = {"stage": stage, "kind": kind, "reason": reason,
              "identity": identity or {}, "expects": expects or []}
    if command:
        result.update(command=command, parameters=parameters)
    return result


def _close_candidate(s, reason):
    candidate = s.get("candidate")
    if not candidate or candidate["record"].get("status") != "active":
        return None
    ident = candidate.get("identity", {})
    if not candidate.get("exported"):
        return action("export", "command", command="export", candidate=ident["candidate"],
                      identity=ident, reason=reason,
                      expects=["Retained exact candidate patch; STOP and exhausted budget remain unchanged."])
    return action("close_candidate", "command", command="close-candidate", candidate=ident["candidate"],
                  reason=reason, identity=ident, close_reason=reason,
                  expects=["Candidate controller record is closed; evidence remains."])


def _delivery_action(s):
    state = s.get("delivery", {})
    if state.get("error"):
        return action("delivery_blocked", "blocked", reason=state["error"],
                      expects=["Repair the cited report input without changing measured history."])
    if state.get("state") == "live_verified":
        return action("complete", "complete", reason="Explanatory report and exact deployment are verified.",
                      identity=state.get("publication", {}))
    if state.get("state") == "pending":
        if not state.get("story_valid"):
            return action("explain", reason=state.get("story_error", "Write the evidence-bound explanatory story."),
                          expects=["report/story.json validated against delivery.story_template(extract()).",
                                   "Verdict, context, system, subsystem, changes and next decision with source references."])
        return action("render", "command", command="render",
                      identity={"evidence_sha256": state.get("evidence_sha256")},
                      expects=["Renderer outputs and current report/delivery.json."])
    if state.get("state") == "generated":
        return action("visual_check", reason="Inspect the actual report in both themes and mobile/desktop.",
                      identity={"artifact_sha256": state["artifacts"]["explainer.html"]},
                      expects=["Hashed screenshots and delivery.record_visual_check evidence; no blanket done flag."])
    publication = s.get("publication")
    if publication:
        return action("verify_live", "command", command="verify-live", **publication,
                      identity=publication, expects=["Exact successful Pages deployment, live HTML hash and index entry."])
    return action("publish", reason="Publish the reviewed report under the standing repository rule, then supply commit and Pages run ID.",
                  identity={"artifact_sha256": state["artifacts"]["explainer.html"]},
                  expects=["Exact commit and Pages run ID; the next action independently verifies them."])


def _finish(s, reason):
    candidate = s.get("candidate")
    if (candidate and candidate.get("value_supported") and not candidate.get("value_ready")
            and s.get("mode") == "research" and not candidate.get("value_error")):
        return action("value", reason="Record practical value from the retained result before closing: " + reason,
                      identity=candidate["value_identity"],
                      expects=["session value records independently reconciled facts and review/comparison disposition."])
    close = _close_candidate(s, reason)
    if close:
        return close
    remaining = s.get("other_active", [])
    if remaining:
        return action("closeout_candidates", reason="Export and close retained comparison/other active candidates.",
                      identity={"candidates": remaining},
                      expects=["Every active candidate has an exported patch and a closed controller record."])
    if not s.get("opened"):
        return action("preparation_blocked", "blocked", reason=reason,
                      expects=["No experiment opened. Preserve preparation and correct the cited input."])
    return action("close_campaign", "command", command="close-campaign", close_reason=reason,
                  reason=reason, expects=["Campaign is closed and its machine claim released; report delivery follows."])


def _tier(s, tier, evaluate=False):
    candidate = s.get("candidate")
    status = s.get("calibration", {}).get(tier, {})
    needed = s.get("tier_cost", {}).get(tier, {}).get("evaluate" if evaluate else "calibrate", 0)
    pool = "probe" if tier == "probe" else "fast"
    if s.get("remaining", {}).get(pool, 0) < needed:
        return _finish(s, "Insufficient remaining " + pool + " budget for a complete " + tier + " tier.")
    if not evaluate:
        if status.get("failed"):
            return _finish(s, "Retained " + tier + " calibration is incomplete or noisy; no silent retry.")
        return action("calibrate_" + tier, "command", command="calibrate", tier=tier,
                      identity={"fingerprint": s.get("fingerprint"), "prior_calibration": status.get("id")},
                      expects=["Complete exact-fingerprint baseline calibration, with every attempt retained."])
    return action("evaluate_" + tier, "command", command="evaluate", tier=tier,
                  candidate=candidate["identity"]["candidate"], correctness=candidate["correctness"]["path"],
                  selection_reason=(candidate.get("selection") or {}).get("reason"),
                  identity={**candidate["identity"], "fingerprint": s.get("fingerprint"),
                            "calibration_id": status.get("id"),
                            "probe_id": (candidate.get("probe") or {}).get("id")},
                  expects=["Exact-tree " + tier + " evaluator report and retained reservations."])


def plan(s):
    """Return the next justified action from a validated snapshot; perform no I/O."""
    if s.get("running"):
        return action("running", "running", reason="An owned or matching experiment process is still active.",
                      identity={"processes": s["running"]})
    if s.get("closed"):
        return _delivery_action(s)
    if s.get("integrity_errors"):
        return action("integrity_blocked", "blocked", reason="; ".join(s["integrity_errors"]),
                      expects=["Reconcile exact pinned inputs and retained artifacts; do not reset budgets or retry measurements."])
    if s.get("preparation_missing"):
        return action("prepare", reason="; ".join(s["preparation_missing"]),
                      expects=["Prepared campaign policy/protocol, active line agenda, selected idea and registered machine.",
                               "Rerun start after preparation; baseline and measurements are never invented."])
    if s.get("mode") == "preparing":
        return action("freeze", "command", command="start",
                      line=s.get("line"), idea=s.get("idea_id"), machine=s.get("machine"),
                      expects=["Frozen research contract and exact protocol/policy hashes."])
    if s.get("mode") == "legacy":
        return _finish(s, "Legacy recovery preserves the original scientific contract and finishes closeout; fresh research needs a new campaign.")
    if s.get("stop_reason"):
        return _finish(s, s["stop_reason"])
    if s.get("stop"):
        return _finish(s, "STOP is set; experiment execution ended and authorized report delivery remains.")
    if s.get("deadline_exhausted"):
        return _finish(s, "Campaign deadline exhausted; retain all attempts and finish report delivery.")
    if s.get("budget_exhausted"):
        return _finish(s, "Campaign resource budget exhausted; no allocation is reset.")
    if not s.get("capability", {}).get("ready"):
        return action("capability_blocked", "blocked",
                      reason="; ".join(s.get("capability", {}).get("missing_capabilities", ["Capability preflight is incomplete."])),
                      expects=["Use an approved capable profile/protocol or close/report the precise coverage gap."])
    if not s.get("machine_matches", True):
        return action("machine_blocked", "blocked", reason="Campaign belongs to a different measurement machine.")
    if not s.get("opened"):
        if s.get("claim") not in (None, s["campaign"]):
            return action("machine_busy", "blocked", reason="Another campaign owns this measurement machine: " + s["claim"])
        return action("open", "command", command="open", line=s["line"], machine=s["machine"],
                      identity={"protocol_sha256": s["protocol_sha256"], "policy_sha256": s["policy_sha256"]},
                      expects=["Controller-created campaign record and one machine claim."])
    if s.get("claim") != s["campaign"]:
        if s.get("claim") is not None:
            return action("machine_busy", "blocked", reason="Another campaign holds the machine claim: " + s["claim"])
        return action("recover_claim", "command", command="recover",
                      expects=["Existing ownership recovered without modifying deadline, budgets, STOP or evidence."])
    if s.get("runtime_missing"):
        return action("prepare_runtime", reason="; ".join(s["runtime_missing"]),
                      expects=["Frozen baseline build and trusted guest images with matching manifests.",
                               "Use existing trusted build/setup paths and counted budget; do not change measurements."])
    if s.get("baseline_blockers"):
        return _finish(s, "Baseline review blocks dependent execution: " + json.dumps(s["baseline_blockers"]))
    candidate = s.get("candidate")
    if not candidate:
        if s.get("last_round_closed"):
            return action("next_idea", reason="Choose a supported next idea within the same frozen contract, or stop.",
                          identity=s.get("last_outcome", {}),
                          expects=["A new validated idea plus evidence-based rationale, or an explicit stop decision."])
        proposal = s.get("proposal")
        if proposal:
            return action("create_candidate", "command", command="new", **proposal,
                          identity={"brief_id": proposal["brief"], "idea": s.get("idea_id")},
                          expects=["Controller-created isolated worktree and candidate record."])
        brief = s.get("brief")
        if not brief:
            return action("brief", "command", command="brief",
                          identity={"fingerprint": s.get("fingerprint"), "idea": s.get("idea_id")},
                          expects=["Durable exact-parent proposal brief."])
        return action("propose", reason="Propose one falsifiable implementation using this durable brief.",
                      identity={"brief_id": brief["id"], "brief_sha256": brief["sha256"],
                                "allowed_parents": brief["allowed_parents"], "idea": s.get("idea_id")},
                      expects=["Candidate ID, exact allowed parent, hypothesis and counter or structural mechanism declaration."])
    ident = candidate["identity"]
    if candidate["record"].get("status") != "active":
        return action("next_idea", reason="Candidate execution is closed. Continue only with a supported next idea.",
                      identity=s.get("last_outcome", ident))
    if candidate.get("termination"):
        return _finish(s, candidate["termination"])
    if candidate.get("source_error") or candidate.get("dirty") or not candidate.get("changed"):
        return action("implement", reason=candidate.get("source_error") or "Implement and commit the bounded hypothesis in its isolated worktree.",
                      identity=ident, expects=["Clean committed source tree differing from the parent; controller records remain authoritative."])
    if candidate.get("static_status") != "SCOPE_PASS":
        if candidate.get("static_status") == "STATIC_REJECT":
            return action("repair_static", reason="Static checks rejected this exact source revision.",
                          identity=ident, expects=["A substantive committed repair or a reject/stop decision; no repeated check of unchanged code."])
        return action("check", "command", command="check", candidate=ident["candidate"],
                      identity=ident, expects=["Exact-commit scope/checkpatch result and exported patch."])
    if candidate.get("review_blockers") or not candidate.get("review_clear"):
        return action("review", reason="Resolve exact-tree correctness findings before runtime execution." if candidate.get("review_blockers") else
                      "Record an independent exact-tree review with hashed evidence.",
                      identity=ident, expects=["Structured review pass or explicit finding resolution; a prose close cannot clear a veto."])
    if not candidate.get("mechanism_ready", True):
        return action("mechanism", reason=candidate.get("mechanism_error", "Exact-tree mechanism evidence is missing."),
                      identity=ident, expects=["Validated candidates/<id>/mechanism.json bound to its declaration and review."])
    correctness = candidate.get("correctness", {})
    if not correctness.get("passed"):
        if correctness.get("failed") or correctness.get("attempted"):
            return _finish(s, "Retained correctness attempt is failed or incomplete: " + correctness.get("reason", "inspect raw evidence"))
        return action("correctness", reason="Run the frozen correctness route with the trusted runner and counted reservation.",
                      identity=ident, expects=["Validated exact-commit raw correctness result with serial/hash/build/reservation provenance.",
                                               "Retain failed or ambiguous attempts; no copied PASS summary."])
    probe = candidate.get("probe")
    if probe:
        if not probe.get("attested") or probe.get("status") != "PROBE_PASS":
            return _finish(s, "Probe ended as " + str(probe.get("status")) + "; retain the outcome and choose the next idea after closeout.")
    else:
        if not s.get("calibration", {}).get("probe", {}).get("ready"):
            return _tier(s, "probe")
        return _tier(s, "probe", evaluate=True)
    selection = candidate.get("selection")
    if not selection:
        return action("fast_selection", reason="Decide whether this exact probe pass justifies a latency screen.",
                      identity={**ident, "probe_id": probe["id"], "fingerprint": s.get("fingerprint")},
                      expects=["Explicit screen/reject decision with exact commit, tree, probe ID and reason."])
    if selection.get("disposition") != "screen":
        return _finish(s, "Probe was not selected for fast screening: " + selection["reason"])
    fast = candidate.get("fast")
    if not fast:
        if not s.get("calibration", {}).get("fast", {}).get("ready"):
            return _tier(s, "fast")
        return _tier(s, "fast", evaluate=True)
    if not fast.get("attested"):
        return _finish(s, "Fast evidence is missing or mismatched; no retry of the started tier.")
    if fast.get("status") in FAILED:
        return _finish(s, "Fast evaluation ended as " + fast["status"] + "; measurements remain incomplete.")
    comparison = candidate.get("comparisons", {})
    if fast.get("status") == "FAST_PASS" and comparison.get("required") and not comparison.get("settled"):
        if comparison.get("next"):
            item = comparison["next"]
            if item.get("required_guests", 0) > s.get("remaining", {}).get("fast", 0):
                return _finish(s, "Insufficient retained campaign budget for the required upstream comparison.")
            return action(item["command"], "command", command=item["command"], comparison=item["comparison"],
                          contrast=item["contrast"], tier="fast", identity=item["identity"],
                          expects=["Bound upstream contrast in the same campaign ledger; no cross-protocol score."])
        return action("prepare_comparisons", reason=comparison.get("reason", "Prepare compatible upstream arms and freeze their comparison plan."),
                      identity=ident, expects=["Canonical comparison contract, exact sources/builds and complete raw correctness routes.",
                                               "Use a bound incomparable/missing decision when coverage cannot be established."])
    if not candidate.get("value_ready"):
        if candidate.get("value_error"):
            return _finish(s, "Value evidence needs reconciliation: " + candidate["value_error"])
        if candidate.get("value_supported"):
            return action("value", reason="Explain whether measured benefit justifies semantic complexity and upstream alternatives.",
                          identity=candidate["value_identity"],
                          expects=["Structured, evidence-bound value.json; numerical facts are extracted by trusted code."])
        return _finish(s, "No supported complete latency value result; retain the actual outcome.")
    return _close_candidate(s, "Research disposition: " + candidate["value_disposition"]) or action(
        "next_idea", identity=s.get("last_outcome", ident))



def _module(path, module_name):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _process(pid):
    """Linux PID plus kernel start tick avoids treating PID reuse as ownership."""
    try:
        fields = (Path("/proc") / str(int(pid)) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "start_ticks": fields[19]}
    except (OSError, ValueError, IndexError):
        return None


def _same_process(identity):
    return bool(identity and _process(identity.get("pid")) == identity)


def _token_processes(token):
    found = []
    marker = ("SWAP_NEXT_ACTION_TOKEN=" + token).encode()
    for directory in Path("/proc").glob("[0-9]*"):
        try:
            if marker in (directory / "environ").read_bytes().split(b"\0"):
                ident = _process(directory.name)
                if ident:
                    found.append(ident)
        except OSError:
            continue
    return found


class Session:
    def __init__(self, campaign, root=ROOT, *, contributor=None, snapshotter=None, executor=None, clock=None):
        self.campaign = name(campaign, "campaign")
        self.contributor = ownership.contributor(contributor)
        self.root = Path(root).resolve()
        self.directory = self.root / "campaigns" / campaign
        need(not self.directory.is_symlink(), "campaign directory must not be a symlink")
        self.path = self.directory / "ledger/session.json"
        self.snapshotter = snapshotter
        self.executor = executor
        self.clock = clock or time.time
        self._observed = {}

    @contextmanager
    def lock(self):
        if ownership.owner(self.root, self.campaign) is not None:
            ownership.require(self.root, self.campaign, self.contributor)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (self.path.parent / ".session.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def state(self):
        ownership.require(self.root, self.campaign, self.contributor)
        need(self.path.is_file(), "Run session start or resume before requesting actions.")
        value = read(self.path)
        need(value.get("schema_version") == 1 and value.get("campaign") == self.campaign,
             "session identity/schema mismatch")
        need(value.get("contributor") == self.contributor, "session contributor differs from campaign ownership")
        need(value.get("allowed_tiers") == ALLOWED_TIERS, "session automatic tiers must remain probe and fast")
        return value

    def _store(self):
        module = _module(self.root / "evolve/control/campaign_store.py", "session_campaign_store")
        module.PROJECT, module.CAMPAIGNS = self.root, self.root / "campaigns"
        module.HOSTS, module.GLOBAL_STOP = module.CAMPAIGNS / "hosts.json", module.CAMPAIGNS / "STOP"
        return module

    def _data(self, relative, default=None):
        path = self.root / relative
        need(not Path(relative).is_absolute() and ".." not in Path(relative).parts,
             "session input must be repository-relative")
        need(path.resolve().is_relative_to(self.root), "session input escapes repository")
        self._observed[relative] = sha(path) if path.is_file() else None
        return read(path) if path.is_file() else copy.deepcopy(default)

    def _campaign_data(self, suffix, default=None):
        return self._data("campaigns/" + self.campaign + "/" + suffix, default)

    def _git(self, source, *args):
        result = subprocess.run(["git", "-C", str(source), *args], capture_output=True, text=True, timeout=30)
        need(result.returncode == 0, "source identity unavailable: " + result.stderr.strip()[:400])
        return result.stdout.strip()

    def _prepare(self, state):
        missing = []
        ppath, qpath = self.directory / "protocol.json", self.directory / "policy.json"
        for path in (ppath, qpath):
            if not path.is_file():
                missing.append(str(path.relative_to(self.root)) + " is missing")
        line_id, idea_id = state.get("line"), state.get("idea_id")
        if not line_id:
            try:
                selected = research.select_line(self.root, contributor=self.contributor).get("selected")
                if selected:
                    line_id, idea_id = selected["line"], idea_id or selected["idea"]
                else:
                    missing.append("No active executable line with a supported proposed idea is available")
            except (ValueError, OSError) as exc:
                missing.append("Line selection: " + str(exc))
        line, idea, profile = None, None, None
        if line_id:
            try:
                line = research.validate_line(read(self.root / "campaigns/lines" / (name(line_id, "line") + ".json")))
                need(line.get("contributor") == self.contributor,
                     "selected line belongs to another contributor or is unowned; prepare your own line")
                need(line["status"] == "active", "selected research line is not active")
                profile = research.load_profile(line["profile"], self.root)
                ideas = [item for item in line["ideas"] if item["status"] == "proposed"
                         and (not idea_id or item["id"] == idea_id)]
                need(ideas, "selected line has no matching proposed idea")
                ideas.sort(key=lambda item: (-item["priority"], item["id"]))
                idea = ideas[0]
                idea_id = idea["id"]
            except (ValueError, OSError) as exc:
                missing.append("Research preparation: " + str(exc))
        machine = state.get("machine")
        try:
            current = self._store().current_machine()
            machine = machine or current
            need(machine == current, "selected machine is not this registered worker")
        except (ValueError, OSError) as exc:
            missing.append("Machine preparation: " + str(exc))
        return {"missing": missing, "line": line, "idea": idea, "profile": profile,
                "line_id": line_id, "idea_id": idea_id, "machine": machine}

    def start(self, *, line=None, idea=None, machine=None):
        """Freeze prepared inputs or return a concrete preparation action. Never launches."""
        with self.lock():
            ownership.claim(self.root, self.campaign, self.contributor)
            if self.path.exists():
                state = self.state()
                if state["mode"] != "preparing":
                    return self._next_locked(state)
            else:
                state = {"schema_version": 1, "campaign": self.campaign, "mode": "preparing",
                         "contributor": self.contributor,
                         "created_unix": self.clock(), "allowed_tiers": list(ALLOWED_TIERS),
                         "line": line, "idea_id": idea, "machine": machine,
                         "pins": {}, "rounds": [], "decisions": [], "executions": [], "stop_reason": None}
            for key, value in (("line", line), ("idea_id", idea), ("machine", machine)):
                if value is not None:
                    name(value, key)
                    state[key] = value
            existing = read(self.directory / "campaign.json") if (self.directory / "campaign.json").exists() else None
            frozen_path = self.directory / "research.json"
            if existing:
                if frozen_path.exists():
                    need(read(frozen_path).get("line_contract", {}).get("contributor") == self.contributor,
                         "frozen research belongs to another contributor or is unowned")
                state.update(line=existing.get("line"), machine=existing.get("machine"))
                state["mode"] = "research" if frozen_path.exists() else "legacy"
                if frozen_path.exists():
                    frozen = read(frozen_path)
                    research.validate_contract(frozen["line_contract"], self.root)
                    state["idea_id"] = frozen["selected_idea"]["id"]
                    state["rounds"] = [{"idea": frozen["selected_idea"]}]
                self._pin(state, research_file=frozen_path.exists())
                records = [read(path) for path in self.directory.glob("candidates/*.json")]
                active = sorted((r for r in records if r.get("status") == "active"),
                                key=lambda row: (row.get("created_unix", 0), row["id"]))
                if state["rounds"] and len(active) == 1:
                    state["rounds"][-1]["candidate"] = active[0]["id"]
            else:
                prepared = self._prepare(state)
                state.update(line=prepared["line_id"], idea_id=prepared["idea_id"], machine=prepared["machine"])
                if not prepared["missing"]:
                    protocol, policy = read(self.directory / "protocol.json"), read(self.directory / "policy.json")
                    need(protocol.get("campaign") == self.campaign, "prepared protocol campaign mismatch")
                    need(protocol.get("baseline_commit") == prepared["line"]["baseline_commit"],
                         "prepared protocol baseline differs from selected line")
                    frozen = {"schema_version": 1,
                              "line_contract": research.line_contract(prepared["line"], prepared["profile"], self.root),
                              "selected_idea": prepared["idea"],
                              "upstream_refs": prepared["line"]["upstream_refs"],
                              "protocol_sha256": sha(self.directory / "protocol.json"),
                              "policy_sha256": sha(self.directory / "policy.json"),
                              "allowed_tiers": list(ALLOWED_TIERS)}
                    if frozen_path.exists():
                        need(read(frozen_path) == frozen, "prepared research contract already exists with different input")
                    else:
                        write(frozen_path, frozen)
                    state["mode"] = "research"
                    state["rounds"] = [{"idea": prepared["idea"]}]
                    self._pin(state, research_file=True)
            write(self.path, state)
            return self._next_locked(state)

    def _pin(self, state, *, research_file):
        names = ["owner.json", "policy.json", "protocol.json"] + (["research.json"] if research_file else [])
        state["pins"] = {key: sha(self.directory / key) for key in names if (self.directory / key).is_file()}

    def resume(self):
        """Restore a session, preserving scientific inputs and every budget/attempt."""
        if not self.path.exists():
            need((self.directory / "campaign.json").is_file(), "resume requires an existing campaign")
            return self.start()
        with self.lock():
            state = self.state()
            current = self._next_locked(state)
            if current["stage"] == "delivery_blocked" and not self._running(state):
                previous = next((item for item in reversed(state.get("executions", []))
                                 if item["command"] in {"render", "verify-live"}), None)
                if previous and not self._effect(previous, self.snapshot(state)):
                    state["delivery_retry_generation"] = state.get("delivery_retry_generation", 0) + 1
                    write(self.path, state)
                    return self._next_locked(state)
            return current

    def _running(self, state):
        found = []
        for item in state.get("executions", []):
            if item.get("status") not in {"starting", "running"}:
                continue
            processes = _token_processes(item["token"])
            if _same_process(item.get("process")):
                processes.append(item["process"])
            elif not processes and _same_process(item.get("launcher")):
                processes.append(item["launcher"])
            for proc in processes:
                if proc not in found:
                    found.append(proc)
        # Commands started outside this driver remain owned by the same campaign's
        # normal lock. Reading its lock neither starts nor stops another process.
        runtime_lock = self.root / "benchmark/kernel/.runtime.lock"
        if runtime_lock.is_file():
            with runtime_lock.open("r") as stream:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(stream, fcntl.LOCK_UN)
                except BlockingIOError:
                    found.append({"runtime_lock": "benchmark/kernel/.runtime.lock"})
        return found

    def _row(self, row):
        item = copy.deepcopy(row)
        reference = row.get("report", row.get("report_path",
                    "campaigns/" + self.campaign + "/runs/evaluations/" + str(row.get("id")) + "/report.json"))
        item["report_path"] = reference
        try:
            report = self._data(reference)
            item["attested"] = report == row
            if not item["attested"]:
                item["evidence_error"] = "retained report is missing or differs from its ledger row"
            elif row.get("measurement_reused") is True:
                protocol = self._campaign_data("protocol.json", {})
                if row.get("comparison"):
                    comparison_runtime.validate_alias(self.root, protocol, row)
                else:
                    need(row.get("action") == "calibrate", "unsupported native reused measurement")
                    calibration_cache.validate_alias(self.root, protocol, row)
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            item.update(attested=False, evidence_error=str(exc))
        return item

    def _runtime(self, protocol):
        missing = []
        build = protocol.get("baseline_build")
        if not isinstance(build, str) or not NAME.fullmatch(build):
            return ["Frozen baseline_build is missing or invalid"], None
        manifest = self._data("benchmark/kernel/builds/" + build + "/result.json")
        if not manifest:
            missing.append("Baseline build manifest is missing: " + build)
        elif (manifest.get("commit") != protocol.get("baseline_commit") or manifest.get("passed") is not True
              or manifest.get("instrument_sha256", "missing") is not None):
            missing.append("Baseline build manifest does not attest the frozen uninstrumented commit")
        for relative in ("benchmark/kernel/builds/" + build + "/output/arch/x86/boot/bzImage",
                         "benchmark/kernel/builds/" + build + "/output/.config",
                         "benchmark/swap-standard/bench.img", "benchmark/swap-standard/initramfs.cpio.gz"):
            if not (self.root / relative).is_file():
                missing.append("Runtime artifact is missing: " + relative)
        image = self._data("benchmark/swap-standard/image.json")
        if not image:
            missing.append("Trusted guest-image manifest is missing")
        for relative in ("evolve/.venv/bin/python",):
            if not (self.root / relative).is_file():
                missing.append("Required interpreter is missing: " + relative)
        fingerprint = None
        if not missing:
            try:
                workflow = _module(self.root / "evolve/standard_workflow.py", "session_standard_workflow")
                workflow.ROOT, workflow.BENCH = self.root, self.root / "benchmark/swap-standard"
                workflow.CAMPAIGN, workflow.PROTOCOL = self.directory, self.directory / "protocol.json"
                fingerprint = workflow.fingerprint(protocol)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                missing.append("Trusted evaluator fingerprint is unavailable: " + str(exc))
        return missing, fingerprint

    def snapshot(self, state=None):
        """Read artifacts and actual identities; do not initialize a workflow or budget."""
        state = state or self.state()
        if self.snapshotter:
            return self.snapshotter(copy.deepcopy(state))
        self._observed = {}
        s = {"campaign": self.campaign, "mode": state["mode"], "line": state.get("line"),
             "machine": state.get("machine"), "idea_id": state.get("idea_id"),
             "integrity_errors": [], "preparation_missing": [], "running": self._running(state),
             "stop_reason": state.get("stop_reason"), "publication": state.get("publication"),
             "delivery_retry_generation": state.get("delivery_retry_generation", 0)}
        for relative in ("evolve/session.py", "evolve/control/controller.py", "evolve/standard_workflow.py",
                         "evolve/research.py", "evolve/reviews.py", "evolve/population.py",
                         "evolve/comparisons.py", "evolve/delivery.py", "evolve/calibration_cache.py",
                         "evolve/reference_cache.py", "evolve/comparison_runtime.py"):
            self._observed[relative] = sha(self.root / relative) if (self.root / relative).is_file() else None
        record = self._campaign_data("campaign.json")
        s.update(opened=bool(record), closed=bool(record and record.get("status") == "closed"))
        for suffix, expected in state.get("pins", {}).items():
            path = self.directory / suffix
            if not path.is_file() or sha(path) != expected:
                s["integrity_errors"].append("Pinned " + suffix + " changed or disappeared")
        protocol, policy = self._campaign_data("protocol.json", {}), self._campaign_data("policy.json", {})
        s.update(protocol_sha256=self._observed.get("campaigns/" + self.campaign + "/protocol.json"),
                 policy_sha256=self._observed.get("campaigns/" + self.campaign + "/policy.json"))
        frozen = self._campaign_data("research.json", {})
        if state["mode"] == "preparing":
            prepared = self._prepare(state)
            s.update(preparation_missing=prepared["missing"], line=prepared["line_id"],
                     idea_id=prepared["idea_id"], machine=prepared["machine"])
        if record:
            s.update(line=record.get("line"), machine=record.get("machine"))
        try:
            store = self._store()
            current_machine = store.current_machine()
            s.update(claim=store.read_claim(), machine_matches=not s.get("machine") or s["machine"] == current_machine)
        except (ValueError, OSError) as exc:
            s.update(claim=None, machine_matches=False)
            s["preparation_missing"].append("Machine: " + str(exc))
        s["stop"] = (self.root / "campaigns/STOP").exists() or (self.directory / "STOP").exists()
        rows = self._campaign_data("ledger/ledger.json", [])
        need(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), "malformed evaluation ledger")
        need(len({row.get("id") for row in rows}) == len(rows), "duplicate evaluation ledger identity")
        s["rows"] = [self._row(row) for row in rows]
        budget = self._campaign_data("ledger/budget.json")
        tickets = list((self.directory / "ledger/guest-reservations").glob("*.json"))
        if budget is None:
            if tickets or any(row.get("execution_started") for row in rows):
                s["integrity_errors"].append("Budget ledger missing while counted execution evidence exists")
            budget = {"guests": 0, "probe_guests": 0, "builds": 0}
        counters = {key: budget.get(key, 0) for key in ("guests", "probe_guests", "builds")}
        if any(type(value) is not int or value < 0 for value in counters.values()):
            s["integrity_errors"].append("Malformed authoritative budget counters")
        counts = {"fast": 0, "probe": 0}
        for path in tickets:
            ticket = self._data(str(path.relative_to(self.root)))
            if ticket.get("pool") not in counts or ticket.get("campaign") != self.campaign:
                s["integrity_errors"].append("Malformed counted reservation: " + path.name)
            else:
                counts[ticket["pool"]] += 1
        if counters["guests"] < counts["fast"] or counters["probe_guests"] < counts["probe"]:
            s["integrity_errors"].append("Budget is lower than retained guest reservations")
        limits = protocol.get("budget", {})
        s["budget"] = budget
        s["remaining"] = {"fast": max(0, limits.get("guest_attempts", 0) - counters["guests"]),
                          "probe": max(0, limits.get("probe_guest_attempts", 0) - counters["probe_guests"]),
                          "builds": max(0, limits.get("build_attempts", 0) - counters["builds"])}
        created = budget.get("created")
        s["deadline_exhausted"] = bool(type(created) in (int, float) and self.clock() >
                                      created + limits.get("wall_seconds", 0))
        s["budget_exhausted"] = bool(s["opened"] and sum(s["remaining"][k] for k in ("fast", "probe")) == 0)
        if state["mode"] == "research":
            try:
                contract = research.validate_contract(frozen["line_contract"], self.root)
                need(frozen.get("protocol_sha256") == s["protocol_sha256"]
                     and frozen.get("policy_sha256") == s["policy_sha256"], "frozen research input hashes mismatch")
                profile = research.load_profile(contract["profile"], self.root)
                s["capability"] = research.capability_readout(profile, protocol, policy, self.root)
            except (ValueError, OSError, KeyError) as exc:
                s["capability"] = {"ready": False, "missing_capabilities": [str(exc)]}
        else:
            s["capability"] = {"ready": False, "missing_capabilities": ["Legacy closeout only"]}
        s["runtime_missing"], s["fingerprint"] = self._runtime(protocol) if not s["closed"] else ([], None)
        baseline = {"id": None, "candidate_commit": protocol.get("baseline_commit"),
                    "source_tree": protocol.get("baseline_tree")}
        s["baseline_blockers"] = reviews.blockers(self.root, self.campaign, baseline) if s["opened"] else []
        s["calibration"], s["tier_cost"] = {}, {}
        for tier in ALLOWED_TIERS:
            spec = protocol.get("tiers", {}).get(tier, {})
            mult = 1 if tier == "probe" else 2
            keys = ("calibration_runs", "candidate_runs") if tier == "probe" else ("calibration_pairs", "comparison_pairs")
            s["tier_cost"][tier] = {"calibrate": mult * len(spec.get("cases", [])) * spec.get(keys[0], 0),
                                    "evaluate": mult * len(spec.get("cases", [])) * spec.get(keys[1], 0)}
            attempts = [row for row in s["rows"] if row.get("action") == "calibrate"
                        and row.get("tier") == tier and not row.get("comparison")]
            current = [row for row in attempts if row.get("fingerprint") == s["fingerprint"]]
            cal = self._campaign_data("ledger/calibration-" + tier + ".json", {})
            row = current[-1] if current else {}
            fresh = bool(row and type(row.get("finished")) in (int, float) and
                         0 <= self.clock() - row["finished"] <= protocol.get("calibration_max_age_seconds", 0))
            ready = (row.get("status") == "CALIBRATED" and row.get("attested")
                     and row.get("analysis", {}).get("passed") is True and fresh
                     and cal.get("id") == row.get("id") and cal.get("fingerprint") == s["fingerprint"])
            s["calibration"][tier] = {"ready": bool(ready), "id": row.get("id"),
                                      "failed": bool(row and (row.get("status") != "CALIBRATED" or not row.get("attested")))}
        records = [self._data(str(path.relative_to(self.root))) for path in sorted(self.directory.glob("candidates/*.json"))]
        round_ = state["rounds"][-1] if state.get("rounds") else {}
        s["idea_id"] = round_.get("idea", {}).get("id", s["idea_id"])
        s["proposal"] = round_.get("proposal")
        selected = round_.get("candidate", (round_.get("proposal") or {}).get("candidate"))
        active = [item for item in records if item.get("status") == "active"]
        if selected:
            chosen = next((item for item in records if item.get("id") == selected), None)
        else:
            chosen = active[0] if state["mode"] == "legacy" and active else None
        s["other_active"] = [item["id"] for item in active if not chosen or item["id"] != chosen["id"]]
        s["candidate"] = self._candidate_snapshot(chosen, s, state, frozen, protocol) if chosen else None
        s["last_round_closed"] = bool(selected and chosen and chosen.get("status") == "closed")
        if s["candidate"]:
            c = s["candidate"]
            s["last_outcome"] = {**c["identity"], "evaluation_id": (c.get("fast") or c.get("probe") or {}).get("id"),
                                 "value_disposition": c.get("value_disposition")}
        s["brief"] = self._brief(protocol, s.get("fingerprint"), records) if not chosen and not s["closed"] else None
        if s["closed"]:
            if s["integrity_errors"]:
                s["delivery"] = {"error": "; ".join(s["integrity_errors"])}
            else:
                try:
                    status = delivery.status(self.root, self.campaign)
                    if status["state"] == "pending":
                        summary = delivery.extract(self.root, self.campaign)
                        status["evidence_sha256"] = summary["evidence_sha256"]
                        try:
                            story = self._campaign_data("report/story.json")
                            delivery.validate_story(story or {}, summary)
                            status["story_valid"] = True
                        except (ValueError, KeyError, TypeError) as exc:
                            status.update(story_valid=False, story_error=str(exc))
                    s["delivery"] = status
                except (ValueError, OSError, KeyError, TypeError) as exc:
                    s["delivery"] = {"error": str(exc)}
        s["input_hashes"] = copy.deepcopy(self._observed)
        return s



    def _decision(self, state, kind, identity):
        for item in reversed(state.get("decisions", [])):
            if item.get("kind") == kind and item.get("identity") == identity:
                return item["payload"]
        return None

    def _brief(self, protocol, fingerprint, records):
        path = self.directory / "archive/population.json"
        if not path.is_file() or not fingerprint:
            return None
        state = self._campaign_data("archive/population.json", {})
        for key, receipt in reversed(list(state.get("briefs", {}).items())):
            if receipt.get("consumed_by") is not None or receipt.get("fingerprint") != fingerprint:
                continue
            relative = "campaigns/" + self.campaign + "/" + receipt["file"]
            brief = self._data(relative)
            if not brief or self._observed[relative] != receipt.get("sha256"):
                continue
            try:
                from population import Population
                population = Population(self.directory, protocol, fingerprint)
                allowed = [parent for parent in receipt.get("allowed_parents", [])
                           if self._parent_valid(population, key, parent)]
                if allowed:
                    return {"id": key, "sha256": receipt["sha256"], "allowed_parents": allowed}
            except (ValueError, KeyError, OSError):
                continue
        return None

    @staticmethod
    def _parent_valid(population, brief, parent):
        try:
            population.validate_parent(brief, parent)
            return True
        except (ValueError, OSError, KeyError):
            return False

    def _correctness(self, record, identity, protocol):
        commit = identity.get("candidate_commit")
        found, invalid = [], []
        paths = sorted(self.directory.glob("runs/guests/*/result.json"))
        alias = self.directory / "candidates" / record["id"] / "correctness.json"
        if alias.exists():
            paths.insert(0, alias)
        seen = set()
        for path in paths:
            proof = self._data(str(path.relative_to(self.root)))
            if not isinstance(proof, dict) or proof.get("workload") != "correctness":
                continue
            if proof.get("candidate_commit", proof.get("source_commit")) != commit:
                continue
            key = proof.get("run_id") or str(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                verified = correctness_proof.validate(proof, protocol, self.root)
                need(verified["candidate_commit"] == commit, "correctness exact commit mismatch")
                found.append({"passed": True, "path": str(path.relative_to(self.root)), "run_id": key})
            except correctness_proof.CorrectnessFailure as exc:
                invalid.append({"passed": False, "failed": True, "attempted": True,
                                "path": str(path.relative_to(self.root)), "reason": str(exc)})
            except (ValueError, OSError) as exc:
                invalid.append({"passed": False, "attempted": True, "path": str(path.relative_to(self.root)),
                                "reason": str(exc)})
        if invalid:
            return invalid[-1]
        if len(found) > 1:
            return {"passed": False, "attempted": True, "reason": "Multiple correctness attempts need explicit reconciliation; no selective success."}
        if found:
            return found[0]
        for path in sorted(self.directory.glob("ledger/guest-reservations/*.json")):
            ticket = self._data(str(path.relative_to(self.root)))
            build = ticket.get("identity", {}).get("build")
            if ticket.get("identity", {}).get("workload") != "correctness" or not isinstance(build, str):
                continue
            manifest = self._data("benchmark/kernel/builds/" + build + "/result.json", {})
            if manifest.get("commit") == commit:
                return {"passed": False, "attempted": True,
                        "reason": "Counted correctness reservation has no validated result: " + path.stem}
        return {"passed": False}

    def _candidate_snapshot(self, record, s, state, frozen, protocol):
        ident = name(record["id"], "candidate")
        relative = "campaigns/" + self.campaign + "/candidates/" + ident
        static = self._data(relative + "/static.json", {})
        archived = self._campaign_data("archive/population.json", {}).get("entries", {}).get(ident, {})
        identity = {"candidate": ident, "candidate_commit": archived.get("candidate_commit", static.get("candidate_commit")),
                    "source_tree": archived.get("source_tree"),
                    "parent_commit": record.get("parent_commit", record.get("parent")),
                    "baseline_commit": protocol.get("baseline_commit")}
        candidate = {"record": record, "identity": identity, "source_error": None, "dirty": False,
                     "changed": False, "exported": (self.directory / "patches" / (ident + ".patch")).is_file()}
        worktree = self.root / record.get("worktree", "")
        try:
            need(record.get("worktree") and worktree.resolve().is_relative_to(self.root / "worktrees"),
                 "candidate worktree is outside controller-owned worktrees")
            identity.update(candidate_commit=self._git(worktree, "rev-parse", "HEAD"),
                            source_tree=self._git(worktree, "rev-parse", "HEAD^{tree}"),
                            parent_tree=self._git(self.root / "linux", "rev-parse", identity["parent_commit"] + "^{tree}"))
            candidate["dirty"] = bool(self._git(worktree, "status", "--porcelain", "--untracked-files=all"))
            candidate["changed"] = identity["source_tree"] != identity["parent_tree"]
        except (ValueError, OSError, TypeError) as exc:
            candidate["source_error"] = str(exc)
            try:
                if identity.get("candidate_commit"):
                    identity["source_tree"] = self._git(self.root / "linux", "rev-parse", identity["candidate_commit"] + "^{tree}")
                if identity.get("parent_commit"):
                    identity["parent_tree"] = self._git(self.root / "linux", "rev-parse", identity["parent_commit"] + "^{tree}")
            except (ValueError, OSError):
                pass
        candidate["static_status"] = static.get("status") if static.get("candidate_commit") == identity.get("candidate_commit") else None
        subject = dict(record, candidate_commit=identity.get("candidate_commit"), source_tree=identity.get("source_tree"))
        candidate["review_blockers"] = reviews.blockers(self.root, self.campaign, subject)
        try:
            dispositions = reviews.list_reviews(self.root, self.campaign)
        except (ValueError, OSError):
            dispositions = []
        exact_reviews = [item for item in dispositions if item.get("candidate_commit") == identity.get("candidate_commit")
                         and item.get("source_tree") == identity.get("source_tree")
                         and item.get("disposition") in {"pass", "resolve"}]
        candidate["review_clear"] = bool(exact_reviews and not candidate["review_blockers"])
        declaration = record.get("mechanism")
        candidate["mechanism_ready"] = True
        if isinstance(declaration, dict) and declaration.get("kind") == "reviewed_structure":
            proof = self._data(relative + "/mechanism.json", {})
            match = next((review for review in exact_reviews if review["id"] == proof.get("review_id")
                          and review["record_sha256"] == proof.get("review_record_sha256")), None)
            candidate["mechanism_ready"] = bool(
                "reviewed_structure" in protocol.get("mechanism_evidence_types", [])
                and proof.get("kind") == "reviewed_structure" and proof.get("schema_version") == 1
                and proof.get("candidate_commit") == identity.get("candidate_commit")
                and proof.get("source_tree") == identity.get("source_tree")
                and proof.get("protocol_sha256") == s["protocol_sha256"]
                and proof.get("claim") == declaration.get("claim")
                and proof.get("falsifier") == declaration.get("falsifier") and match
                and not candidate["review_blockers"])
            candidate["mechanism_error"] = "Structural proof, protocol capability or exact review binding is missing."
        candidate["correctness"] = self._correctness(record, identity, protocol) if identity.get("candidate_commit") else {"passed": False}
        ordinary = [row for row in s["rows"] if row.get("candidate") == ident and row.get("action") == "evaluate"
                    and not row.get("comparison") and row.get("candidate_commit") == identity.get("candidate_commit")]
        for tier in ALLOWED_TIERS:
            rows = [row for row in ordinary if row.get("tier") == tier]
            result = rows[-1] if rows else None
            if result and (result.get("candidate_tree") != identity.get("source_tree") or result.get("fingerprint") != s["fingerprint"]):
                result = dict(result, attested=False, evidence_error="current candidate/fingerprint differs from retained tier evidence")
            candidate[tier] = result
        probe = candidate.get("probe") or {}
        selection_identity = {**identity, "probe_id": probe.get("id"), "fingerprint": s.get("fingerprint")}
        candidate["selection"] = self._decision(state, "fast_selection", selection_identity)
        for decision in reversed(state.get("decisions", [])):
            if decision.get("kind") == "reject" and decision.get("identity", {}).get("candidate") == ident:
                candidate["termination"] = decision["payload"]["reason"]
                break
        candidate["comparisons"] = self._comparisons(candidate, s, state, frozen, protocol)
        fast = candidate.get("fast")
        candidate["value_ready"] = False
        if fast and fast.get("attested") and identity.get("parent_tree"):
            try:
                research.performance_from_report(fast)
                candidate["value_supported"] = True
                candidate["value_identity"] = {
                    "candidate_commit": identity["candidate_commit"], "candidate_tree": identity["source_tree"],
                    "parent_commit": identity["parent_commit"], "parent_tree": identity["parent_tree"],
                    "baseline_commit": identity["baseline_commit"], "protocol_sha256": s["protocol_sha256"],
                    "evaluation_id": fast["id"], "evaluation_report": fast["report_path"]}
                value = self._data(relative + "/value.json")
                if value:
                    self._validate_value(value, candidate, frozen)
                    candidate.update(value_ready=True, value_disposition=value["assessment"]["disposition"])
            except (ValueError, OSError, KeyError, TypeError) as exc:
                if (self.root / relative / "value.json").exists():
                    candidate["value_error"] = str(exc)
        return candidate

    def _comparisons(self, candidate, s, state, frozen, protocol):
        contract = frozen.get("line_contract", {})
        required = contract.get("value_policy", {}).get("requires_upstream_comparison", False)
        result = {"required": required, "settled": not required, "status": "not-applicable",
                  "reason": "Frozen line declares no relevant upstream comparison.", "evidence": []}
        refs = list(frozen.get("upstream_refs", []))
        round_ = state["rounds"][-1] if state.get("rounds") else {}
        refs += round_.get("idea", {}).get("upstream_refs", [])
        expected = {(item["source_url"], item["revision"], item["commit"], item["tree"]) for item in refs}
        skipped = self._decision(state, "skip_comparisons", candidate["identity"])
        if skipped:
            return dict(result, settled=True, status="missing", reason=skipped["reason"], evidence=skipped.get("evidence", []))
        plans, covered = [], set()
        for path in sorted(self.directory.glob("comparisons/*.json")):
            try:
                item = comparisons.load(self.root, self.campaign, path.stem, protocol)
                arm = item["arms"]["candidate"]
                if arm["commit"] != candidate["identity"].get("candidate_commit") or arm["tree"] != candidate["identity"].get("source_tree"):
                    continue
                need(item["tier"] == "fast", "Automatic comparison must use fast tier")
                upstream = item["arms"]["upstream"]
                source = upstream["source"]
                if upstream["compatibility"] == "compatible":
                    covered.add((source["url"], source["revision"], upstream["commit"], upstream["tree"]))
                else:
                    covered.update(ref for ref in expected if ref[:2] == (source["url"], source["revision"]))
                plans.append(item)
                self._observed[str(path.relative_to(self.root))] = sha(path)
            except (ValueError, OSError, KeyError) as exc:
                return dict(result, required=True, settled=False, status="missing", reason=str(exc))
        if not plans:
            return dict(result, status="missing", reason="Freeze a same-base upstream plan for this exact candidate.") if required else result
        if expected - covered:
            return dict(result, required=True, settled=False, status="missing",
                        reason="Frozen comparison plans do not cover every declared upstream alternative.")
        result.update(required=True, settled=True, status="complete", reason="All declared contrasts have bound retained evidence.")
        for item in plans:
            summary = comparisons.reconcile(item, protocol, s["rows"])
            reference = "campaigns/" + self.campaign + "/comparisons/" + item["id"] + ".json"
            result["evidence"].append(reference)
            for outcome in summary["outcomes"]:
                if outcome["status"] == "NOT_COMPARABLE":
                    result.update(status="incomparable", reason="A declared contrast has a recorded base/compatibility conflict.")
                    continue
                row = next((row for row in s["rows"] if row.get("id") == outcome.get("evaluation_id")), None)
                if outcome["status"] != "PENDING":
                    if row and row.get("attested") and outcome.get("analysis"):
                        result["evidence"].append(row["report_path"])
                    else:
                        result.update(status="missing", reason="Retained comparison is incomplete or its raw report is unavailable.")
                    continue
                result.update(settled=False, status="missing")
                try:
                    comparisons.validate_evidence(item, protocol, self.root, s["fingerprint"], s["machine"],
                                                  source_repo=self.root / "linux")
                    for role, arm in item["arms"].items():
                        if role == "baseline" or arm.get("compatibility") != "compatible":
                            continue
                        record = self._campaign_data("candidates/" + arm["candidate"] + ".json", {})
                        need(record and not reviews.blockers(self.root, self.campaign,
                             dict(record, candidate_commit=arm["commit"], source_tree=arm["tree"])),
                             "Comparison arm review is unresolved: " + role)
                    result["next"] = comparison_runtime.planning_step(self.root, protocol,
                        self._campaign_data("ledger/ledger.json", []), item, outcome["contrast"],
                        s["fingerprint"], now=self.clock())
                    return result
                except (ValueError, OSError, KeyError) as exc:
                    return dict(result, reason="Prepare comparison evidence: " + str(exc))
        return result

    def _validate_value(self, value, candidate, frozen):
        expected = candidate["value_identity"]
        decision = value["decision"]
        assessment = research.assess_value(decision, frozen["line_contract"], expected)
        need(assessment == value["assessment"], "stored value assessment differs from its bound decision")
        need(value["provenance"]["evaluation_sha256"] == sha(self.root / expected["evaluation_report"]),
             "value evaluation hash changed")
        for ref, expected_sha in value["provenance"]["evidence_sha256"].items():
            need(sha(delivery.at(self.root, ref)) == expected_sha, "value evidence hash changed: " + ref)
        if candidate["review_blockers"]:
            need(decision["review_status"] == "blocked", "new review veto dominates the historical value decision")
        upstream = candidate["comparisons"]
        need(decision["upstream_comparison"]["status"] == upstream["status"],
             "stored upstream decision differs from retained comparison evidence")



    def _argv(self, item):
        command, p = item["command"], item.get("parameters", {})
        python = str(self.root / "evolve/.venv/bin/python")
        control = [python, "evolve/control/controller.py", "--campaign", self.campaign]
        loop = [python, "evolve/loop.py", "swap-standard"]
        if command == "start":
            argv = [python, "evolve/session.py", "start", "--campaign", self.campaign]
            for key in ("line", "idea", "machine"):
                if p.get(key):
                    argv += ["--" + key, name(p[key], key)]
            return argv
        if command == "open":
            return control + ["open-campaign", "--line", name(p["line"], "line"), "--machine", name(p["machine"], "machine")]
        if command == "recover":
            return control + ["resume-campaign", "--reason", "Contributor session resumed existing ownership without resetting evidence or resources."]
        if command in {"check", "export"}:
            return control + [command, name(p["candidate"], "candidate")]
        if command in {"close-candidate", "close-campaign"}:
            reason = p["close_reason"]
            need(isinstance(reason, str) and reason.strip(), "closure reason is required")
            return control + (["close", name(p["candidate"], "candidate")] if command == "close-candidate" else ["close-campaign"]) + ["--reason", reason]
        if command == "brief":
            return loop + ["next", "--campaign", self.campaign]
        if command == "new":
            argv = control + ["new", name(p["candidate"], "candidate"), "--hypothesis", p["hypothesis"],
                              "--brief", p["brief"], "--parent", p["parent"]]
            if isinstance(p["mechanism"], dict):
                reference = p.get("mechanism_spec")
                need(reference, "structural proposal needs its retained mechanism declaration")
                delivery.at(self.root, reference)
                return argv + ["--mechanism-spec", reference]
            return argv + ["--mechanism", p["mechanism"]]
        if command in MEASUREMENT_COMMANDS:
            tier = p["tier"]
            need(tier in ALLOWED_TIERS and (command not in {"compare", "compare-calibrate"} or tier == "fast"),
                 "automatic execution stops at probe/fast")
            runtime_action = {"compare": "evaluate", "compare-calibrate": "calibrate"}.get(command, command)
            argv = loop + [runtime_action, "--campaign", self.campaign, "--tier", tier]
            if command == "evaluate":
                proof = p["correctness"]
                delivery.at(self.root, proof)
                argv += ["--candidate", name(p["candidate"], "candidate"), "--correctness", proof]
                if tier == "fast":
                    need(p.get("selection_reason"), "exact probe admission reason is required")
                    argv += ["--selection-reason", p["selection_reason"]]
            if command in {"compare", "compare-calibrate"}:
                argv += ["--comparison", name(p["comparison"], "comparison"), "--contrast", name(p["contrast"], "contrast")]
            return argv
        if command == "render":
            return [python, "evolve/delivery.py", "render", "--campaign", self.campaign]
        if command == "verify-live":
            need(OBJECT.fullmatch(p.get("commit", "")) and str(p.get("run_id", "")).isdigit(),
                 "exact publication commit and numeric run ID required")
            return [python, "evolve/delivery.py", "verify-live", "--campaign", self.campaign,
                    "--commit", p["commit"], "--run-id", str(p["run_id"])]
        raise SessionError("unregistered executable action")

    def _bound_action(self, item, s):
        item = copy.deepcopy(item)
        inputs = s.get("input_hashes", {})
        guard = {key: s.get(key) for key in ("opened", "closed", "claim", "stop", "budget", "fingerprint")}
        if item.get("command") in {"render", "verify-live"}:
            item["identity"]["delivery_retry_generation"] = s.get("delivery_retry_generation", 0)
        item["contributor"] = self.contributor
        item["input_hashes"] = inputs
        item["guard"] = guard
        item["id"] = "action-" + digest(item)[:24]
        if item["kind"] == "command":
            item["argv"] = self._argv(item)
            # Measurement identity survives unrelated input changes. A reserved
            # attempt cannot acquire a second launch through a new action hash.
            key = {"command": item["command"], "parameters": item.get("parameters"),
                   "identity": item["identity"]}
            item["operation_key"] = digest(key) if item["command"] in MEASUREMENT_COMMANDS else item["id"]
        return item

    def _effect(self, execution, s):
        command, p = execution["command"], execution.get("parameters", {})
        candidate = s.get("candidate") or {}
        if command == "start":
            return s.get("mode") != "preparing"
        if command == "open":
            return s.get("opened")
        if command == "recover":
            return s.get("claim") == self.campaign
        if command == "brief":
            return bool(s.get("brief") or candidate)
        if command == "new":
            return candidate.get("identity", {}).get("candidate") == p.get("candidate")
        if command == "check":
            return candidate.get("static_status") in {"SCOPE_PASS", "STATIC_REJECT"}
        if command == "export":
            return candidate.get("exported")
        if command == "close-candidate":
            path = self.directory / "candidates" / (p["candidate"] + ".json")
            return path.is_file() and read(path).get("status") == "closed"
        if command == "close-campaign":
            return s.get("closed")
        if command == "calibrate":
            cal = s.get("calibration", {}).get(p["tier"], {})
            return bool(cal.get("id") and cal["id"] != execution.get("identity", {}).get("prior_calibration"))
        if command == "evaluate":
            row = candidate.get(p["tier"]) or {}
            return bool(row.get("attested") and row.get("candidate_commit") == execution["identity"].get("candidate_commit"))
        if command in {"compare", "compare-calibrate"}:
            action_name = "evaluate" if command == "compare" else "calibrate"
            return any(row.get("action") == action_name and row.get("comparison", {}).get("contract_id") == p["comparison"]
                       and row.get("comparison", {}).get("contrast_id") == p["contrast"] and row.get("attested")
                       for row in s.get("rows", []))
        if command == "render":
            return s.get("delivery", {}).get("state") in {"generated", "visually_checked", "live_verified"}
        if command == "verify-live":
            return s.get("delivery", {}).get("state") == "live_verified"
        return False

    def _closeout(self, state):
        path = self.directory / "ledger/session-closeout.json"
        if path.exists():
            return
        actions = [{key: item.get(key) for key in ("action_id", "command", "identity", "status", "returncode", "log")}
                   for item in state.get("executions", []) if item["command"] not in {"render", "verify-live"}]
        close = next((item for item in reversed(state.get("executions", []))
                      if item["command"] == "close-campaign"), {})
        reason = state.get("stop_reason") or close.get("parameters", {}).get("close_reason")
        records = [read(p) for p in sorted(self.directory.glob("candidates/*.json"))]
        write(path, {"schema_version": 1, "campaign": self.campaign, "mode": state["mode"],
                     "reason": reason or "Recovered closed campaign; original candidate reasons and measurements are retained.",
                     "frozen_inputs": state.get("pins", {}), "decisions": state.get("decisions", []),
                     "actions": actions, "candidate_reasons": {r["id"]: r.get("reason") for r in records},
                     "performance_accepted": False, "auto_promote": False})

    def _next_locked(self, state):
        s = self.snapshot(state)
        changed = False
        if not s.get("running"):
            for execution in state.get("executions", []):
                if execution.get("status") not in {"starting", "running"}:
                    continue
                completed = self._effect(execution, s)
                execution.update(status="artifact_reconciled" if completed else "interrupted",
                                 reconciled_unix=self.clock())
                if not completed and execution["command"] not in {"render", "verify-live"}:
                    state["stop_reason"] = "Interrupted or ambiguous " + execution["command"] + "; retained attempts will not be launched again."
                changed = True
        if changed:
            write(self.path, state)
            s = self.snapshot(state)
        if s.get("closed") and not (self.directory / "ledger/session-closeout.json").exists():
            self._closeout(state)
            s = self.snapshot(state)
        item = self._bound_action(plan(s), s)
        if item["kind"] == "command":
            previous = next((x for x in state.get("executions", []) if x["operation_key"] == item["operation_key"]), None)
            if previous:
                if item["command"] in {"render", "verify-live"}:
                    item = self._bound_action(action("delivery_blocked", "blocked",
                        reason="The last delivery command did not produce verified artifacts. Inspect " + previous["log"] +
                               ". Fix inputs or wait for service recovery, then Resume to retry delivery without repeating measurements."), s)
                elif not s.get("running"):
                    state["stop_reason"] = "Prior " + item["command"] + " lacks its required output; no duplicate execution."
                    write(self.path, state)
                    s = self.snapshot(state)
                    item = self._bound_action(plan(s), s)
        state["current_action"] = item
        state["status"] = "complete" if item["kind"] == "complete" else ("blocked" if item["kind"] == "blocked" else "active")
        write(self.path, state)
        return item

    def next(self):
        with self.lock():
            return self._next_locked(self.state())

    def _spawned(self, token, process):
        with self.lock():
            state = self.state()
            item = next(x for x in state["executions"] if x["token"] == token)
            item.update(status="running", process=process)
            write(self.path, state)

    def _run(self, argv, log, token, on_spawn):
        env = os.environ.copy()
        env["SWAP_NEXT_CONTRIBUTOR"] = self.contributor
        env["SWAP_NEXT_ACTION_TOKEN"] = token
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        with log.open("wb") as output:
            proc = subprocess.Popen(argv, cwd=self.root, env=env, stdout=output, stderr=subprocess.STDOUT,
                                    start_new_session=True)
            on_spawn(_process(proc.pid) or {"pid": proc.pid, "start_ticks": "unknown"})
            return proc.wait()

    def execute(self, action_id):
        with self.lock():
            state = self.state()
            prior = next((item for item in state["executions"] if item["action_id"] == action_id), None)
            if prior:
                return {"executed": False, "reason": "Action already has a durable execution receipt.", "receipt": prior}
            current = self._next_locked(state)
            need(current["id"] == action_id, "stale action ID; inspect the current next action")
            need(current["kind"] == "command", "only generated mechanical actions can execute")
            need(not any(item["operation_key"] == current["operation_key"] for item in state["executions"]),
                 "this operation already has an execution receipt")
            argv = self._argv(current)
            token = uuid.uuid4().hex
            log = self.directory / "runs/session" / (current["id"] + "-" + token[:8] + ".log")
            log.parent.mkdir(parents=True, exist_ok=True)
            receipt = {"action_id": current["id"], "operation_key": current["operation_key"],
                       "command": current["command"], "parameters": current["parameters"],
                       "identity": current["identity"], "input_hashes": current["input_hashes"],
                       "token": token, "status": "starting", "started_unix": self.clock(),
                       "launcher": _process(os.getpid()), "process": None,
                       "log": str(log.relative_to(self.root)), "argv": argv}
            state["executions"].append(receipt)
            write(self.path, state)
        failure = None
        try:
            returncode = (self.executor or self._run)(argv, log, token,
                         lambda process: self._spawned(token, process))
        except BaseException as exc:
            failure, returncode = str(exc), None
        with self.lock():
            state = self.state()
            receipt = next(item for item in state["executions"] if item["token"] == token)
            receipt.update(status="completed" if returncode == 0 else "failed",
                           returncode=returncode, finished_unix=self.clock())
            if failure:
                receipt["error"] = failure
            if returncode != 0 and current["command"] not in {"render", "verify-live", "check"}:
                state["stop_reason"] = current["command"] + " failed; inspect " + receipt["log"] + ". Retain all started attempts."
            write(self.path, state)
            next_action = self._next_locked(state)
        return {"executed": True, "receipt": receipt, "next": next_action}

    def _decision_record(self, state, current, kind, payload):
        record = {"id": "decision-" + digest({"action": current["id"], "kind": kind, "payload": payload})[:24],
                  "action_id": current["id"], "kind": kind, "identity": current["identity"],
                  "input_hashes": current["input_hashes"], "payload": copy.deepcopy(payload)}
        prior = next((item for item in state["decisions"] if item["action_id"] == current["id"]), None)
        need(prior is None or prior == record, "this action already has a different decision")
        if prior is None:
            state["decisions"].append(record)
        return record

    def decide(self, action_id, payload):
        """Record research judgment, never a replacement for checks/measurements."""
        need(isinstance(payload, dict) and isinstance(payload.get("kind"), str), "structured decision kind is required")
        with self.lock():
            state = self.state()
            previous = next((item for item in state["decisions"] if item["action_id"] == action_id), None)
            if previous:
                need(previous["payload"] == payload, "decision action is already bound to different content")
                return self._next_locked(state)
            current = self._next_locked(state)
            need(current["id"] == action_id, "stale decision action ID")
            kind, stage = payload["kind"], current["stage"]
            if kind != "visual":
                need(isinstance(payload.get("reason"), str) and payload["reason"].strip(), "decision needs a concrete reason")
            snapshot = self.snapshot(state)
            if kind == "stop":
                need(not snapshot.get("closed"), "execution is already closed; finish delivery")
                state["stop_reason"] = payload["reason"]
            elif kind == "reject":
                need(snapshot.get("candidate") and snapshot["candidate"]["record"].get("status") == "active",
                     "reject needs an active exact candidate")
            elif kind == "propose":
                need(stage == "propose", "proposal decision is not the next action")
                name(payload.get("candidate"), "candidate")
                need(isinstance(payload.get("hypothesis"), str) and 10 <= len(payload["hypothesis"]) <= 2000,
                     "proposal needs a falsifiable hypothesis")
                parent = payload.get("parent")
                need(parent in current["identity"]["allowed_parents"], "proposal parent is not permitted by durable brief")
                mechanism = payload.get("mechanism")
                round_ = state["rounds"][-1]
                profile = research.load_profile(read(self.directory / "research.json")["line_contract"]["profile"], self.root)
                if isinstance(mechanism, dict):
                    need(mechanism.get("kind") == "reviewed_structure" and
                         all(isinstance(mechanism.get(key), str) and mechanism[key].strip() for key in ("claim", "falsifier")),
                         "invalid structural mechanism declaration")
                    need("reviewed_structure" in profile["mechanism_evidence"], "profile lacks structural mechanism capability")
                    need("reviewed_structure" in read(self.directory / "protocol.json").get("mechanism_evidence_types", []),
                         "frozen protocol lacks structural mechanism capability")
                else:
                    need(isinstance(mechanism, str) and len(mechanism.split(":")) == 3 and
                         mechanism.split(":")[-1] in {"up", "down"}, "counter mechanism must be CASE:KEY:up|down")
                proposal = {"candidate": payload["candidate"], "parent": parent, "hypothesis": payload["hypothesis"],
                            "brief": current["identity"]["brief_id"], "mechanism": mechanism}
                if isinstance(mechanism, dict):
                    path = self.directory / "ledger/session-inputs" / (current["id"] + "-mechanism.json")
                    write(path, mechanism)
                    proposal["mechanism_spec"] = str(path.relative_to(self.root))
                round_.update(proposal=proposal, candidate=payload["candidate"])
            elif kind == "fast_selection":
                need(stage == "fast_selection", "fast selection is not the next action")
                need(payload.get("disposition") in {"screen", "reject"}, "choose screen or reject")
                for key in ("candidate_commit", "source_tree", "probe_id"):
                    need(payload.get(key) == current["identity"].get(key), "fast selection identity mismatch: " + key)
            elif kind == "continue":
                need(stage == "next_idea", "finish the current candidate before choosing another idea")
                idea = research.validate_idea(payload.get("idea"))
                need(idea["status"] == "proposed", "next idea must be proposed")
                need(idea["id"] not in {item["idea"]["id"] for item in state["rounds"]}, "next idea needs a distinct identity")
                frozen = read(self.directory / "research.json")
                profile = research.load_profile(frozen["line_contract"]["profile"], self.root)
                need(set(idea["affected_paths"]) <= set(profile["allowed_modify"]), "next idea widens the approved profile")
                need(idea["mechanism_evidence_type"] in profile["mechanism_evidence"], "next idea lacks mechanism capability")
                need(not idea["upstream_refs"] or frozen["line_contract"]["value_policy"]["requires_upstream_comparison"],
                     "new upstream requirement needs a new frozen research contract")
                need(idea["estimated_cost"]["guest_attempts"] <= sum(snapshot["remaining"][k] for k in ("fast", "probe"))
                     and idea["estimated_cost"]["build_attempts"] <= snapshot["remaining"]["builds"],
                     "next idea exceeds the existing remaining campaign budget")
                evidence = payload.get("evidence")
                need(isinstance(evidence, list) and evidence, "continuation requires retained evidence references")
                for ref in evidence:
                    delivery.at(self.root, ref)
                state["rounds"].append({"idea": idea})
                state["idea_id"] = idea["id"]
            elif kind == "skip_comparisons":
                need(stage == "prepare_comparisons", "comparison disposition is not the next action")
                for ref in payload.get("evidence", []):
                    delivery.at(self.root, ref)
            elif kind == "visual":
                need(stage == "visual_check", "visual verification is not the next action")
                delivery.record_visual_check(self.root, self.campaign, payload.get("evidence", {}))
            elif kind == "publication":
                need(stage == "publish" or (stage == "delivery_blocked" and snapshot.get("closed")
                     and snapshot.get("delivery", {}).get("state") == "visually_checked"
                     and not snapshot.get("running")), "publication is not the next action")
                need(OBJECT.fullmatch(payload.get("commit", "")) and str(payload.get("run_id", "")).isdigit(),
                     "exact publication commit and Pages run ID are required")
                state["publication"] = {"commit": payload["commit"], "run_id": str(payload["run_id"])}
            else:
                raise SessionError("unsupported decision; done/pass booleans cannot advance artifact stages")
            self._decision_record(state, current, kind, payload)
            write(self.path, state)
            return self._next_locked(state)

    def value(self, candidate, decision):
        """Rebuild expected identity, performance, vetoes and comparisons before writing."""
        name(candidate, "candidate")
        with self.lock():
            state = self.state()
            s = self.snapshot(state)
            c = s.get("candidate")
            need(c and c["identity"]["candidate"] == candidate and c.get("value_supported"),
                 "candidate has no exact attested evaluation supporting a value decision")
            need(state["mode"] == "research", "legacy recovery cannot invent practical-value thresholds")
            frozen = read(self.directory / "research.json")
            expected = c["value_identity"]
            decision = copy.deepcopy(decision)
            need(decision.get("identity") == expected, "authored value identity differs from independently reconciled evidence")
            measured = research.performance_from_report(read(self.root / expected["evaluation_report"]))
            for key, value in measured.items():
                need(decision.get(key) == value, "authored " + key + " differs from trusted evaluation")
            review_status = "blocked" if c["review_blockers"] else ("clear" if c["review_clear"] else "pending")
            need(decision.get("review_status") == review_status, "authored review status differs from exact-tree dispositions")
            upstream = c["comparisons"]
            submitted = decision.get("upstream_comparison", {})
            need(submitted.get("status") == upstream["status"], "authored upstream status differs from bound contrasts")
            if upstream["status"] == "complete":
                need(set(upstream["evidence"]) <= set(submitted.get("evidence", [])), "value omits required upstream contrast evidence")
            result = research.record_value(self.directory, candidate, decision, frozen["line_contract"], expected, self.root)
            self._next_locked(state)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "resume", "next", "execute", "decide", "value"])
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--contributor", help="stable caller identity; defaults to SWAP_NEXT_CONTRIBUTOR")
    parser.add_argument("--line")
    parser.add_argument("--idea")
    parser.add_argument("--machine")
    parser.add_argument("--action")
    parser.add_argument("--decision", type=Path)
    parser.add_argument("--candidate")
    args = parser.parse_args(argv)
    try:
        session = Session(args.campaign, contributor=args.contributor)
        if args.command == "start":
            result = session.start(line=args.line, idea=args.idea, machine=args.machine)
        elif args.command == "resume":
            result = session.resume()
        elif args.command == "next":
            result = session.next()
        elif args.command == "execute":
            need(args.action, "execute requires --action")
            result = session.execute(args.action)
        elif args.command == "decide":
            need(args.action and args.decision, "decide requires --action and --decision")
            result = session.decide(args.action, read(args.decision))
        else:
            need(args.candidate and args.decision, "value requires --candidate and --decision")
            result = session.value(args.candidate, read(args.decision))
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "auto_promote": False}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
