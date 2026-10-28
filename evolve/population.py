# SPDX-License-Identifier: GPL-2.0-only
"""Screened population, durable proposal receipts and baseline advancement evidence.

The caller supplies trusted evaluator rows and cumulative patches. This module runs
no evaluator or model. ``archive/population.json`` owns evidence and sampling
sequence; ``archive/database`` is a rebuildable OpenEvolve view of eligible parents.
Only FAST_PASS admits a new candidate. A later failure preserves its history and
removes it from the parent pool. Neutral screens may reproduce; advancement has a
separate, stricter rule in :func:`advancement_evidence`.

Controller integration is stdlib-only: ``eligible_parents()``, ``validate_parent``
and ``consume_brief`` do not import OpenEvolve. Validate a durable brief before
creating a candidate, then consume it with that candidate's ID. Consumption is
idempotent for crash recovery and refuses reuse by a different candidate.
"""
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import tempfile

NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
OBJECT = re.compile(r"[0-9a-f]{40}")
FAILURES = {"PROBE_REJECT", "REGRESSION", "STATIC_REJECT", "CORRECTNESS_FAIL", "INCOMPLETE", "BLOCKED"}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _fast(row):
    return (row.get("action") == "evaluate" and row.get("tier") == "fast"
            and row.get("status") == "FAST_PASS")


def _guards(analysis):
    metrics = analysis.get("metrics")
    return (isinstance(metrics, dict) and bool(metrics)
            and all(isinstance(v, dict) and (v.get("advisory") is True or v.get("guard_pass") is True)
                    for v in metrics.values()))


def advancement_evidence(row):
    """Return an auditable advancement decision; never changes a baseline.

    ``analysis.metrics[primary].noise_relative`` is the calibrated envelope
    already emitted by swap-standard analysis. Every scored guard must pass and
    the normalized combined score must exceed ``1 + max(primary envelopes)``.
    This comparison is against the campaign baseline, not an unmeasured anchor.
    """
    analysis = row.get("analysis") or {}
    result = {"eligible": False, "reason": "requires a fast evaluation pass",
              "evidence_id": row.get("id"), "candidate_commit": row.get("candidate_commit"),
              "fingerprint": row.get("fingerprint"), "score": analysis.get("combined_score")}
    if not _fast(row):
        return result
    if not _guards(analysis):
        return dict(result, reason="a scored guard failed or is missing")
    primary = analysis.get("primary")
    if not isinstance(primary, list) or not primary:
        return dict(result, reason="primary calibrated noise is missing")
    noise = []
    for name in primary:
        metric = analysis["metrics"].get(name, {})
        value = metric.get("noise_relative")
        if metric.get("advisory") or not _finite(value) or value < 0:
            return dict(result, reason="primary calibrated noise is missing or invalid")
        noise.append(value)
    score = analysis.get("combined_score")
    if not _finite(score) or score <= 0:
        return dict(result, reason="normalized combined score is missing or invalid")
    threshold = 1 + max(noise)
    eligible = score > threshold
    return dict(result, eligible=eligible, primary=list(primary), noise_relative=max(noise),
                threshold=threshold,
                reason="improvement exceeds calibrated noise" if eligible else
                       "screen is exploratory; improvement does not exceed calibrated noise")


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("." + path.name + ".tmp")
    with tmp.open("w") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _paths(patch):
    return sorted(set(re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)))


def _flatten(value, prefix=""):
    out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            out.update(_flatten(item, prefix + "." + str(key) if prefix else str(key)))
    elif _finite(value):
        out[prefix] = value
    return out


class _StableSet(set):
    """Give the pinned sampler stable iteration across Python hash seeds."""
    def __iter__(self):
        return iter(sorted(super().__iter__()))


class Population:
    def __init__(self, campaign_dir, protocol, fingerprint):
        self.directory = Path(campaign_dir)
        self.protocol = copy.deepcopy(protocol)
        self.fingerprint = str(fingerprint)
        self.campaign = protocol["campaign"]
        self.baseline = protocol["baseline_commit"]
        if not NAME.fullmatch(self.campaign) or self.directory.name != self.campaign:
            raise ValueError("campaign directory identity mismatch")
        if not OBJECT.fullmatch(self.baseline) or not self.fingerprint:
            raise ValueError("baseline commit and fingerprint are required")
        record_path = self.directory / "campaign.json"
        self.campaign_record = json.loads(record_path.read_text()) if record_path.exists() else {}
        anchor = self.campaign_record.get("line_anchor_commit", protocol.get("line_anchor_commit", self.baseline))
        if not isinstance(anchor, str) or not OBJECT.fullmatch(anchor):
            raise ValueError("line anchor must be an exact commit")
        self.anchor = anchor
        self.archive = self.directory / "archive"
        self.path = self.archive / "population.json"
        self._state()  # Validate existing identity without creating any files.

    def _state(self):
        if not self.path.exists():
            return {"schema_version": 1, "campaign": self.campaign,
                    "baseline_commit": self.baseline, "line_anchor_commit": self.anchor,
                    "entries": {}, "sample_sequence": 0, "briefs": {}}
        state = json.loads(self.path.read_text())
        if (state.get("schema_version") != 1 or state.get("campaign") != self.campaign
                or state.get("baseline_commit") != self.baseline
                or state.get("line_anchor_commit") != self.anchor):
            raise ValueError("population identity differs from campaign baseline or line anchor")
        return state

    def _writable(self):
        path = self.directory / "campaign.json"
        if path.exists() and json.loads(path.read_text()).get("status") == "closed":
            raise ValueError("closed campaign population is read-only")

    @contextmanager
    def _lock(self):
        self._writable()
        runtime = self.directory / "runs"
        runtime.mkdir(parents=True, exist_ok=True)
        with (runtime / "population.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            self._writable()
            yield

    def _view(self, entry):
        entry = copy.deepcopy(entry)
        reasons = [item["reason"] for item in entry.get("invalidations", [])]
        if entry.get("fingerprint") != self.fingerprint:
            reasons.append("stale_fingerprint")
        if entry.get("baseline_commit") != self.baseline:
            reasons.append("baseline_mismatch")
        entry["parent_eligible"] = not reasons
        entry["invalidation_reasons"] = sorted(set(reasons))
        return entry

    def eligible_parents(self):
        """Exact-current-fingerprint exploratory entries, keyed by candidate ID."""
        return {name: view for name, item in self._state()["entries"].items()
                if (view := self._view(item))["parent_eligible"]}

    def _database(self, entries, seed=42):
        # Lazy imports keep controller-side receipt checks independent of the venv.
        from openevolve.config import DatabaseConfig
        from openevolve.database import Program, ProgramDatabase
        size = max(10, self.protocol.get("max_probe_candidates", 0), len(entries))
        db = ProgramDatabase(DatabaseConfig(in_memory=True, population_size=size,
                                            archive_size=size, num_islands=1, random_seed=seed,
                                            log_prompts=False, embedding_model=None,
                                            similarity_threshold=0))
        for name, entry in sorted(entries.items()):
            db.add(Program(id=name, code=entry["patch"], language="diff",
                           parent_id=entry.get("parent_candidate"), generation=entry["generation"],
                           timestamp=entry.get("timestamp", 0),
                           changes_description=entry.get("hypothesis", ""),
                           metrics={"combined_score": entry["analysis"]["combined_score"]},
                           metadata=copy.deepcopy(entry)))
        db.islands = [_StableSet(island) for island in db.islands]
        db.archive = _StableSet(db.archive)
        return db

    def _save_database(self, state):
        eligible = {name: view for name, item in state["entries"].items()
                    if (view := self._view(item))["parent_eligible"]}
        rng = random.getstate()
        try:
            db = self._database(eligible)
            runtime = self.directory / "runs"
            with tempfile.TemporaryDirectory(prefix="population-", dir=runtime) as temporary:
                staged, old = Path(temporary) / "database", Path(temporary) / "old"
                db.save(str(staged), iteration=len(state["briefs"]))
                _atomic(staged / "population-source.json", {"state_sha256": _digest(state),
                                                           "fingerprint": self.fingerprint})
                target = self.archive / "database"
                if target.is_symlink():
                    raise ValueError("population database must not be a symlink")
                if target.exists():
                    target.rename(old)
                try:
                    staged.rename(target)
                except BaseException:
                    if old.exists():
                        old.rename(target)
                    raise
        finally:
            random.setstate(rng)

    def _evidence(self, row):
        ident = row.get("id")
        if not isinstance(ident, str) or not re.fullmatch(r"[a-zA-Z0-9-]{1,96}", ident):
            raise ValueError("evaluation row needs a safe immutable ID")
        report = row.get("report", row.get("report_path",
                         f"campaigns/{self.campaign}/runs/evaluations/{ident}/report.json"))
        if not isinstance(report, str) or Path(report).is_absolute() or ".." in Path(report).parts:
            raise ValueError("report path must be repository-relative")
        keys = ("id", "action", "tier", "status", "candidate", "candidate_commit", "fingerprint",
                "started", "finished", "reason", "analysis", "calibration_id", "probe_id",
                "probe_signals", "probe_analysis", "probe", "controller_check")
        evidence = {key: copy.deepcopy(row[key]) for key in keys if key in row}
        proof = row.get("correctness")
        if isinstance(proof, dict):
            evidence["correctness"] = {key: copy.deepcopy(proof[key]) for key in
                ("candidate_commit", "source_commit", "gates", "integration_pass", "mode", "backend", "config_sha256")
                if key in proof}
        evidence.update(report=report, row_sha256=_digest(row))
        return evidence

    def record(self, row, candidate_record, patch, tree_id):
        """Admit a fast screen or append later evidence to its stable candidate entry.

        A non-pass for a never-admitted candidate stays in the caller's ledger and
        returns None. Reusing a row ID with different bytes is an integrity error.
        Fast evidence must match this fingerprint; known correctness/slow failures
        may invalidate an existing entry even when their fingerprint is older.
        """
        name = candidate_record.get("id")
        commit = row.get("candidate_commit")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError("candidate ID is required")
        if not isinstance(commit, str) or not OBJECT.fullmatch(commit):
            raise ValueError("exact candidate commit is required")
        if not isinstance(tree_id, str) or not OBJECT.fullmatch(tree_id):
            raise ValueError("exact source tree is required")
        if row.get("candidate") != name:
            raise ValueError("evaluation candidate identity mismatch")
        if row.get("baseline_commit", self.baseline) != self.baseline:
            raise ValueError("evaluation baseline mismatch")
        if not isinstance(patch, str) or not patch.strip():
            raise ValueError("cumulative candidate patch is required")
        evidence = self._evidence(row)
        with self._lock():
            state = self._state()
            entry = state["entries"].get(name)
            if any(other != name and any(item["id"] == evidence["id"] for item in saved["evidence"])
                   for other, saved in state["entries"].items()):
                raise ValueError("immutable evaluation ID is already bound to another candidate")
            if entry is None and not _fast(row):
                return None
            if _fast(row):
                if row.get("fingerprint") != self.fingerprint:
                    raise ValueError("fast screen has a stale fingerprint")
                if not _guards(row.get("analysis") or {}):
                    raise ValueError("FAST_PASS has failing or missing scored guards")
                proof = row.get("correctness") or {}
                if proof and proof.get("candidate_commit", proof.get("source_commit")) != commit:
                    raise ValueError("FAST_PASS correctness commit mismatch")
                if any(proof.get("gates", {}).get(gate) is not True
                       for gate in self.protocol.get("required_correctness_gates", [])):
                    raise ValueError("FAST_PASS required correctness gate is missing")
            if entry:
                if entry["candidate_commit"] != commit or entry["source_tree"] != tree_id or entry["patch"] != patch:
                    raise ValueError("archived candidate source identity changed")
                old = next((item for item in entry["evidence"] if item["id"] == evidence["id"]), None)
                if old:
                    if old != evidence:
                        raise ValueError("immutable evaluation ID was reused with changed evidence")
                    source = self.archive / "database/population-source.json"
                    expected = {"state_sha256": _digest(state), "fingerprint": self.fingerprint}
                    if not source.is_file() or json.loads(source.read_text()) != expected:
                        self._save_database(state)
                    return self._view(entry)
            else:
                if any(item["source_tree"] == tree_id for item in state["entries"].values()):
                    raise ValueError("source tree is already archived under another candidate")
                parent_name = candidate_record.get("parent_candidate")
                parent = state["entries"].get(parent_name, {})
                parent_commit = candidate_record.get("parent_commit", candidate_record.get("parent", self.baseline))
                if parent_name and (not parent or parent_commit != parent["candidate_commit"]):
                    raise ValueError("candidate parent identity is absent from this population")
                if not parent_name and parent_commit != self.baseline:
                    raise ValueError("baseline child has an unexpected parent commit")
                generation = candidate_record.get("generation", parent.get("generation", 0) + 1)
                if not isinstance(generation, int) or isinstance(generation, bool) or generation != parent.get("generation", 0) + 1:
                    raise ValueError("candidate generation must follow its recorded parent")
                entry = {"id": name, "candidate_commit": commit, "source_tree": tree_id,
                         "baseline_commit": self.baseline, "line_anchor_commit": self.anchor,
                         "parent_candidate": parent_name,
                         "parent_commit": parent_commit,
                         "generation": generation, "patch": patch, "changed_paths": _paths(patch),
                         "hypothesis": candidate_record.get("hypothesis", ""),
                         "mechanism": candidate_record.get("mechanism"), "evidence": [], "invalidations": [],
                         "timestamp": row.get("finished", row.get("started", 0))}
            entry["evidence"].append(evidence)
            proof = evidence.get("correctness", {})
            bad_correctness = (proof.get("integration_pass") is False or
                               any(value is False for value in proof.get("gates", {}).values()) or
                               row.get("status") == "CORRECTNESS_FAIL")
            reason = None
            if bad_correctness:
                reason = "correctness_failure"
            elif row.get("tier") == "slow" and (row.get("status") == "REGRESSION" or
                    any(v.get("guard_pass") is False and not v.get("advisory")
                        for v in (row.get("analysis", {}).get("metrics") or {}).values())):
                reason = "slow_regression"
            elif row.get("status") in ("PROBE_REJECT", "REGRESSION"):
                reason = "probe_rejected" if row.get("tier") == "probe" else "fast_regression"
            if _fast(row) and bad_correctness:
                raise ValueError("FAST_PASS correctness evidence failed")
            if reason:
                entry["invalidations"].append({"evidence_id": row["id"], "reason": reason})
            if _fast(row):
                entry.update(fingerprint=self.fingerprint, analysis=copy.deepcopy(row["analysis"]),
                             probe_signals=copy.deepcopy(row.get("probe_signals", row.get("probe", row.get("probe_analysis", {})))),
                             report=evidence["report"], fast_evidence_id=row["id"],
                             advancement=advancement_evidence(row))
            if _fast(row):
                parent = state["entries"].get(entry.get("parent_candidate"))
                comparable = parent and parent.get("fingerprint") == self.fingerprint
                before = _flatten(parent.get("probe_signals", {})) if comparable else {}
                after = _flatten(entry["probe_signals"])
                entry["parent_delta"] = {
                    "comparable": bool(comparable),
                    "probe_signals": {key: after[key] - before[key] for key in sorted(before.keys() & after.keys())},
                    "combined_score": (entry["analysis"]["combined_score"] - parent["analysis"]["combined_score"])
                                      if comparable else None,
                    "interpretation": "diagnostic difference of separate baseline comparisons, not a paired parent control"}
            entry["latest_status"] = row["status"]
            entry["tier"] = "fast"
            entry["screen_only"] = True
            entry["performance_accepted"] = False
            state["entries"][name] = entry
            # State is authoritative; a killed database refresh is safely rebuilt next time.
            self.archive.mkdir(parents=True, exist_ok=True)
            _atomic(self.path, state)
            self._save_database(state)
            return self._view(entry)

    def _summary(self, row):
        keys = ("id", "candidate", "candidate_commit", "tier", "status", "reason", "mechanism", "analysis", "changed_paths")
        result = {key: copy.deepcopy(row[key]) for key in keys if key in row}
        if not result.get("changed_paths"):
            check = row.get("controller_check", {})
            result["changed_paths"] = check.get("changed_paths", check.get("files", []))
        return result

    def _baseline_parent(self):
        return {"id": None, "candidate_commit": self.baseline, "source_tree": None,
                "baseline_commit": self.baseline, "line_anchor_commit": self.anchor,
                "patch": "", "generation": 0, "mechanism": None, "probe_signals": {},
                "analysis": {}, "report": None, "parent_eligible": True, "kind": "baseline"}

    def _brief(self, state, ledger, line_history, remaining, persist):
        from openevolve.config import PromptConfig
        from openevolve.prompt.sampler import PromptSampler
        sequence = state["sample_sequence"] + 1
        entries = {name: view for name, item in state["entries"].items()
                   if (view := self._view(item))["parent_eligible"]}
        binding = {"campaign": self.campaign, "baseline_commit": self.baseline,
                   "line_anchor_commit": self.anchor, "fingerprint": self.fingerprint,
                   "sequence": sequence, "eligible": {name: item["candidate_commit"] for name, item in sorted(entries.items())}}
        seed = int(_digest(binding)[:16], 16)
        rng = random.getstate()
        try:
            db = self._database(entries, seed)
            if entries:
                sampled, inspired = db.sample(num_inspirations=2)
                parent = dict(entries[sampled.id], kind="exploratory_parent")
                inspirations = [dict(entries[item.id], kind="exploratory_inspiration") for item in inspired]
            else:
                parent, inspirations = self._baseline_parent(), []
        finally:
            random.setstate(rng)
        paths = set(parent.get("changed_paths", []))
        mechanism = parent.get("mechanism")
        older = []
        for row in ledger[:-3]:
            item = self._summary(row)
            if row.get("status") in FAILURES and row.get("candidate") and (
                    not parent["id"] or (mechanism and row.get("mechanism") == mechanism)
                    or paths.intersection(item.get("changed_paths", []))):
                older.append(item)
        negative = [self._summary(row) for row in ledger if row.get("status") in FAILURES and row.get("candidate")]
        for item in reversed(negative):
            if len(inspirations) >= 2:
                break
            inspirations.append(dict(item, kind="negative_inspiration", parent_eligible=False))
        allowed = list(dict.fromkeys([self.baseline, parent["candidate_commit"]]))
        ident = f"brief-{sequence:06d}-" + _digest(binding)[:12]
        brief = {"schema_version": 1, "id": ident, **binding, "sample_seed": seed,
                 "persisted": persist, "parent": parent, "allowed_parents": allowed,
                 "parent_bindings": {self.baseline: {"candidate": None, "source_tree": self.protocol.get("baseline_tree")},
                                     **({parent["candidate_commit"]: {"candidate": parent["id"], "source_tree": parent["source_tree"]}}
                                        if parent["id"] else {})},
                 "inspirations": inspirations, "last_outcomes": [self._summary(row) for row in ledger[-3:]],
                 "older_relevant_failures": older, "line_history": line_history,
                 "remaining": copy.deepcopy(remaining),
                 "anchor_comparison": "measured campaign baseline" if self.baseline == self.anchor else
                                      "anchor identity retained; no root-relative measurement is claimed"}
        template = Path(__file__).with_name("templates")
        sampler = PromptSampler(PromptConfig(template_dir=str(template), use_template_stochasticity=False,
                                             system_message="You propose Linux swap experiments within the frozen campaign contract."))
        brief["prompt"] = sampler.build_prompt(current_program=parent["patch"],
            program_metrics=({"combined_score": parent["analysis"]["combined_score"]}
                             if "combined_score" in parent.get("analysis", {}) else {}),
            language="diff", evolution_round=sequence, template_key="swap_next",
            binding=_json({key: brief[key] for key in ("id", "campaign", "fingerprint", "baseline_commit", "line_anchor_commit", "allowed_parents")}),
            parent_evidence=_json(parent), inspiration_evidence=_json(inspirations),
            outcomes=_json(brief["last_outcomes"]), older_failures=_json(older),
            line_history=line_history, remaining=_json(remaining))
        return brief

    def next_brief(self, ledger, line_history, remaining, persist=True):
        """Render a pinned-library brief; previews (including closed campaigns) write nothing."""
        if not persist:
            return self._brief(self._state(), ledger, line_history, remaining, False)
        with self._lock():
            state = self._state()
            brief = self._brief(state, ledger, line_history, remaining, True)
            path = self.archive / "briefs" / (brief["id"] + ".json")
            _atomic(path, brief)
            state["sample_sequence"] = brief["sequence"]
            state["briefs"][brief["id"]] = {"fingerprint": self.fingerprint,
                "baseline_commit": self.baseline, "allowed_parents": brief["allowed_parents"],
                "parent_bindings": brief["parent_bindings"],
                "sample_seed": brief["sample_seed"], "sequence": brief["sequence"],
                "file": str(path.relative_to(self.directory)),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "consumed_by": None}
            _atomic(self.path, state)
            self._save_database(state)
            return brief

    def validate_parent(self, brief_id, parent_commit):
        """Read-only validation of the durable sampled-parent authorization receipt."""
        state = self._state()
        receipt = state["briefs"].get(brief_id)
        if receipt is None:
            raise ValueError("unknown or unpersisted proposal brief")
        if receipt["fingerprint"] != self.fingerprint or receipt["baseline_commit"] != self.baseline:
            raise ValueError("proposal brief has a stale fingerprint or baseline")
        path = self.directory / receipt["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]:
            raise ValueError("proposal brief bytes changed")
        if parent_commit not in receipt["allowed_parents"]:
            raise ValueError("parent must be the campaign baseline or the sampled exact commit")
        if parent_commit != self.baseline:
            binding = receipt["parent_bindings"][parent_commit]
            entry = self.eligible_parents().get(binding["candidate"])
            if not entry or entry["candidate_commit"] != parent_commit:
                raise ValueError("sampled parent is no longer eligible")
            if entry["source_tree"] != binding["source_tree"]:
                raise ValueError("sampled parent source tree changed")
        return copy.deepcopy(receipt)

    def consume_brief(self, brief_id, parent_commit, candidate_id):
        """Bind a validated proposal receipt to one candidate, idempotently."""
        if not isinstance(candidate_id, str) or not NAME.fullmatch(candidate_id):
            raise ValueError("candidate ID is required")
        with self._lock():
            receipt = self.validate_parent(brief_id, parent_commit)
            if receipt["consumed_by"] not in (None, candidate_id):
                raise ValueError("proposal brief is already consumed by another candidate")
            if receipt["consumed_by"] == candidate_id:
                if receipt.get("chosen_parent") != parent_commit:
                    raise ValueError("consumed proposal has a different chosen parent")
                return receipt
            state = self._state()
            receipt.update(consumed_by=candidate_id, chosen_parent=parent_commit)
            state["briefs"][brief_id] = receipt
            _atomic(self.path, state)
            return receipt
