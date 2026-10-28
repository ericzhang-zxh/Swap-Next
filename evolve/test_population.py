# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free integration with the pinned OpenEvolve database and prompt sampler."""
import copy
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("population", Path(__file__).with_name("population.py"))
pop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pop)

BASE, ANCHOR = "a" * 40, "0" * 40
METRIC = "swapin-disk.swapin_seq.mean_ns"
PATCH = "diff --git a/mm/swap_state.c b/mm/swap_state.c\n--- a/mm/swap_state.c\n+++ b/mm/swap_state.c\n@@ -1 +1 @@\n-old\n+new\n"


def row(name="one", *, ident=None, score=1, status="FAST_PASS", tier="fast", fp="fp-one"):
    return {"id": ident or name + "-fast", "action": "evaluate", "tier": tier,
            "candidate": name, "candidate_commit": {"one": "1", "two": "2", "three": "3"}.get(name, "4") * 40,
            "baseline_commit": BASE, "fingerprint": fp, "status": status, "finished": 10,
            "correctness": {"candidate_commit": {"one": "1", "two": "2", "three": "3"}.get(name, "4") * 40,
                            "gates": {"data_roundtrip": True}},
            "probe_signals": {"swapin-disk": {"swap_ra_hit": 100}},
            "analysis": {"status": status, "combined_score": score, "primary": [METRIC],
                         "metrics": {METRIC: {"guard_pass": True, "noise_relative": .25},
                                     "swapin-disk.swapin_seq.p99_ns": {"guard_pass": False, "advisory": True,
                                                                     "noise_relative": .4}}}}


def candidate(name="one", **extra):
    return dict({"id": name, "parent": BASE, "hypothesis": "Useful bounded swap hypothesis",
                 "mechanism": "swapin-disk:swapin_vmstat_delta.swap_ra_hit:up"}, **extra)


class PopulationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.campaign = self.root / "campaigns/demo"
        self.campaign.mkdir(parents=True)
        self.protocol = {"campaign": "demo", "baseline_commit": BASE, "line_anchor_commit": ANCHOR,
                         "max_candidates": 3, "max_probe_candidates": 10}
        self.fp = "fp-one"
        (self.campaign / "campaign.json").write_text(json.dumps({"status": "open"}))
        self.population = pop.Population(self.campaign, self.protocol, self.fp)
        self.no_network = patch.object(socket.socket, "connect", side_effect=AssertionError("no network in population"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def add(self, name="one", score=1, **record):
        data = row(name, score=score)
        entry = self.population.record(data, candidate(name, **record), PATCH + "+" + name + "\n",
                                       {"one": "b", "two": "c", "three": "d"}[name] * 40)
        return data, entry

    def files(self):
        return {str(path.relative_to(self.campaign)): path.read_bytes()
                for path in self.campaign.rglob("*") if path.is_file()}

    def test_neutral_screen_is_exploratory_but_cannot_advance(self):
        data, entry = self.add(score=1 / 1.2)
        self.assertTrue(entry["parent_eligible"])
        self.assertFalse(entry["advancement"]["eligible"])
        self.assertEqual(entry["line_anchor_commit"], ANCHOR)
        self.assertFalse(entry["performance_accepted"])
        self.assertTrue(entry["screen_only"])
        self.assertEqual(entry["tier"], "fast")
        from openevolve.config import DatabaseConfig
        from openevolve.database import ProgramDatabase
        db = ProgramDatabase(DatabaseConfig(in_memory=True, num_islands=1))
        db.load(str(self.population.archive / "database"))
        self.assertEqual(set(db.programs), {"one"})
        self.assertEqual(db.programs["one"].metadata["source_tree"], "b" * 40)
        self.assertEqual(db.programs["one"].metadata["analysis"], data["analysis"])
        self.assertEqual(db.programs["one"].code, entry["patch"])
        self.assertEqual(self.population.eligible_parents()["one"]["candidate_commit"], "1" * 40)

    def test_advancement_is_strict_and_uses_all_scored_guards(self):
        strong = row(score=1.3)
        evidence = pop.advancement_evidence(strong)
        self.assertTrue(evidence["eligible"])
        self.assertEqual(evidence["threshold"], 1.25)
        self.assertFalse(pop.advancement_evidence(row(score=1.25))["eligible"])
        strong["analysis"]["metrics"][METRIC]["guard_pass"] = False
        self.assertFalse(pop.advancement_evidence(strong)["eligible"])
        strong = row(score=2)
        del strong["analysis"]["metrics"][METRIC]["noise_relative"]
        self.assertFalse(pop.advancement_evidence(strong)["eligible"])
        self.assertFalse(pop.advancement_evidence(row(score=2, tier="probe", status="PROBE_PASS"))["eligible"])

    def test_probe_reject_and_incomplete_never_admit(self):
        for status, tier in (("PROBE_PASS", "probe"), ("PROBE_REJECT", "probe"),
                             ("REGRESSION", "fast"), ("INCOMPLETE", "fast")):
            with self.subTest(status=status):
                self.assertIsNone(self.population.record(row(status=status, tier=tier), candidate(), PATCH, "b" * 40))
        self.assertFalse(self.population.path.exists())
        self.assertFalse((self.population.archive / "database").exists())

    def test_failed_correctness_and_contradictory_guards_cannot_admit(self):
        bad = row()
        bad["correctness"]["gates"]["data_roundtrip"] = False
        with self.assertRaisesRegex(ValueError, "correctness"):
            self.population.record(bad, candidate(), PATCH, "b" * 40)
        bad = row()
        bad["analysis"]["metrics"][METRIC]["guard_pass"] = False
        with self.assertRaisesRegex(ValueError, "guards"):
            self.population.record(bad, candidate(), PATCH, "b" * 40)
        self.assertFalse(self.population.path.exists())

    def test_slow_failure_updates_identity_and_preserves_fast_evidence(self):
        data, original = self.add()
        later = row(ident="one-slow", tier="slow", status="REGRESSION")
        later["analysis"]["metrics"][METRIC]["guard_pass"] = False
        result = self.population.record(later, candidate(), original["patch"], original["source_tree"])
        self.assertEqual(result["id"], "one")
        self.assertEqual([item["id"] for item in result["evidence"]], ["one-fast", "one-slow"])
        self.assertEqual(result["evidence"][0]["analysis"], data["analysis"])
        self.assertFalse(result["parent_eligible"])
        self.assertIn("slow_regression", result["invalidation_reasons"])
        from openevolve.config import DatabaseConfig
        from openevolve.database import ProgramDatabase
        db = ProgramDatabase(DatabaseConfig(in_memory=True, num_islands=1))
        db.load(str(self.population.archive / "database"))
        self.assertEqual(db.programs, {})
        self.assertEqual(self.population.eligible_parents(), {})

    def test_correctness_failure_invalidates_even_older_fingerprint(self):
        _, original = self.add()
        bad = row(ident="one-correctness", tier="probe", status="INCOMPLETE", fp="older")
        bad["correctness"]["gates"]["data_roundtrip"] = False
        changed = self.population.record(bad, candidate(), original["patch"], original["source_tree"])
        self.assertIn("correctness_failure", changed["invalidation_reasons"])
        self.assertEqual(len(changed["evidence"]), 2)

    def test_record_is_idempotent_and_evidence_cannot_be_rewritten(self):
        data, original = self.add()
        before = self.files()
        self.population.record(data, candidate(), original["patch"], original["source_tree"])
        self.assertEqual(before, self.files())
        changed = copy.deepcopy(data)
        changed["analysis"]["combined_score"] = 2
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.population.record(changed, candidate(), original["patch"], original["source_tree"])
        self.assertEqual(before, self.files())

    def test_stale_scores_are_filtered_and_preview_is_read_only(self):
        self.add()
        before = self.files()
        newer = pop.Population(self.campaign, self.protocol, "fp-two")
        self.assertEqual(newer.eligible_parents(), {})
        preview = newer.next_brief([], "line history", {"probe": 9, "fast": 70}, persist=False)
        self.assertEqual(preview["parent"]["kind"], "baseline")
        self.assertEqual(preview["allowed_parents"], [BASE])
        self.assertIn("no root-relative measurement", preview["anchor_comparison"])
        self.assertEqual(before, self.files())
        with self.assertRaisesRegex(ValueError, "stale"):
            newer.record(row(), candidate(), PATCH, "e" * 40)

    def test_closed_preview_and_constructor_write_no_files(self):
        (self.campaign / "campaign.json").write_text(json.dumps({"status": "closed"}))
        before = self.files()
        closed = pop.Population(self.campaign, self.protocol, self.fp)
        brief = closed.next_brief([], "line", {}, persist=False)
        self.assertFalse(brief["persisted"])
        self.assertEqual(before, self.files())
        with self.assertRaisesRegex(ValueError, "closed"):
            closed.next_brief([], "line", {})
        self.assertEqual(before, self.files())

    def test_sampling_progress_and_bound_parent_are_durable(self):
        self.add("one")
        self.add("two")
        self.add("three")
        from openevolve.prompt.sampler import PromptSampler
        build = PromptSampler.build_prompt
        with patch.object(PromptSampler, "build_prompt", autospec=True, side_effect=build) as rendered:
            first = self.population.next_brief([], "line history", {"probe": 20, "fast": 50})
        self.assertEqual(rendered.call_count, 1)
        self.assertEqual(len(first["inspirations"]), 2)
        restarted = pop.Population(self.campaign, self.protocol, self.fp)
        preview = restarted.next_brief([], "line history", {}, persist=False)
        second = restarted.next_brief([], "line history", {})
        self.assertEqual(second["sequence"], 2)
        self.assertNotEqual(first["sample_seed"], second["sample_seed"])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(preview["sample_seed"], second["sample_seed"])
        self.assertEqual(preview["parent"]["id"], second["parent"]["id"])
        self.assertEqual(first["allowed_parents"], [BASE, first["parent"]["candidate_commit"]])
        self.assertIn("line history", first["prompt"]["user"])
        self.assertIn("calibrated noise", first["prompt"]["user"])
        self.assertIn(PATCH, first["parent"]["patch"])
        restarted.validate_parent(first["id"], BASE)
        restarted.validate_parent(first["id"], first["parent"]["candidate_commit"])
        other = next(commit for commit in ("1" * 40, "2" * 40, "3" * 40) if commit not in first["allowed_parents"])
        with self.assertRaisesRegex(ValueError, "sampled exact"):
            restarted.validate_parent(first["id"], other)
        receipt = restarted.consume_brief(first["id"], BASE, "child")
        self.assertEqual(receipt["consumed_by"], "child")
        self.assertEqual(restarted.consume_brief(first["id"], BASE, "child"), receipt)
        with self.assertRaisesRegex(ValueError, "consumed"):
            restarted.consume_brief(first["id"], BASE, "other-child")
        with self.assertRaisesRegex(ValueError, "stale"):
            pop.Population(self.campaign, self.protocol, "fp-two").validate_parent(first["id"], BASE)

    def test_receipt_detects_modified_brief_or_invalidated_parent(self):
        _, entry = self.add()
        brief = self.population.next_brief([], "", {})
        later = row(ident="one-fail", tier="slow", status="REGRESSION")
        self.population.record(later, candidate(), entry["patch"], entry["source_tree"])
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            self.population.validate_parent(brief["id"], "1" * 40)
        self.population.validate_parent(brief["id"], BASE)
        path = self.population.archive / "briefs" / (brief["id"] + ".json")
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "bytes changed"):
            self.population.validate_parent(brief["id"], BASE)

    def test_child_keeps_cumulative_patch_and_parent_diagnostics(self):
        _, parent = self.add()
        data = row("two", score=1.2)
        data["probe_signals"]["swapin-disk"]["swap_ra_hit"] = 110
        entry = self.population.record(data, candidate("two", parent_candidate="one", parent_commit="1" * 40),
                                       PATCH + "+child\n", "c" * 40)
        self.assertEqual(entry["generation"], 2)
        self.assertEqual(entry["parent_candidate"], "one")
        self.assertEqual(entry["parent_commit"], "1" * 40)
        self.assertEqual(entry["baseline_commit"], BASE)
        self.assertEqual(entry["parent_delta"]["probe_signals"]["swapin-disk.swap_ra_hit"], 10)
        self.assertAlmostEqual(entry["parent_delta"]["combined_score"], .2)
        self.assertIn("not a paired parent control", entry["parent_delta"]["interpretation"])

    def test_equivalent_source_tree_does_not_create_new_identity(self):
        self.add()
        with self.assertRaisesRegex(ValueError, "already archived"):
            self.population.record(row("two"), candidate("two"), PATCH + "+two\n", "b" * 40)

    def test_brief_retains_relevant_older_rejection(self):
        self.add()
        older = {"id": "old", "candidate": "rejected", "status": "PROBE_REJECT", "tier": "probe",
                 "reason": "mechanism did not engage", "controller_check": {"files": ["mm/swap_state.c"]}}
        ledger = [older] + [{"id": f"new-{i}", "status": "FAST_PASS", "candidate": "other"} for i in range(3)]
        brief = self.population.next_brief(ledger, "historical line", {"probe_guests": 12}, persist=False)
        self.assertEqual([item["id"] for item in brief["last_outcomes"]], ["new-0", "new-1", "new-2"])
        self.assertEqual(brief["older_relevant_failures"][0]["id"], "old")
        self.assertEqual(brief["inspirations"][0]["kind"], "negative_inspiration")
        self.assertFalse(brief["inspirations"][0]["parent_eligible"])
        self.assertIn("mechanism did not engage", brief["prompt"]["user"])
        self.assertEqual(brief["remaining"], {"probe_guests": 12})


    def test_campaign_metadata_owns_anchor_without_editing_protocol(self):
        (self.campaign / "campaign.json").write_text(json.dumps({"status": "open", "line_anchor_commit": "9" * 40}))
        protocol_before = copy.deepcopy(self.protocol)
        population = pop.Population(self.campaign, self.protocol, self.fp)
        self.assertEqual(population.anchor, "9" * 40)
        self.assertEqual(self.protocol, protocol_before)

    def test_idempotent_replay_recovers_a_missing_database(self):
        data, entry = self.add()
        import shutil
        shutil.rmtree(self.population.archive / "database")
        before = self.population.path.read_bytes()
        self.population.record(data, candidate(), entry["patch"], entry["source_tree"])
        self.assertTrue((self.population.archive / "database/metadata.json").exists())
        self.assertEqual(before, self.population.path.read_bytes())

    def test_required_correctness_and_tree_receipt_are_bound(self):
        protocol = dict(self.protocol, required_correctness_gates=["fork_cow"])
        population = pop.Population(self.campaign, protocol, self.fp)
        with self.assertRaisesRegex(ValueError, "required correctness"):
            population.record(row(), candidate(), PATCH, "b" * 40)
        _, entry = self.add()
        brief = self.population.next_brief([], "", {})
        receipt = self.population.validate_parent(brief["id"], "1" * 40)
        self.assertEqual(receipt["parent_bindings"]["1" * 40]["source_tree"], "b" * 40)
        self.population.consume_brief(brief["id"], BASE, "child")
        with self.assertRaisesRegex(ValueError, "chosen parent"):
            self.population.consume_brief(brief["id"], "1" * 40, "child")
        state = self.population._state()
        state["entries"]["one"]["source_tree"] = "f" * 40
        pop._atomic(self.population.path, state)
        with self.assertRaisesRegex(ValueError, "source tree changed"):
            self.population.validate_parent(brief["id"], "1" * 40)


    def test_baseline_prompt_has_no_invented_fitness(self):
        from openevolve.prompt.sampler import PromptSampler
        build = PromptSampler.build_prompt
        with patch.object(PromptSampler, "build_prompt", autospec=True, side_effect=build) as rendered:
            brief = self.population.next_brief([], "", {}, persist=False)
        self.assertEqual(rendered.call_args.kwargs["program_metrics"], {})
        self.assertEqual(brief["parent"]["analysis"], {})
        self.assertNotIn("combined_score", brief["prompt"]["user"])


    def test_malformed_fast_fitness_never_publishes_an_eligible_entry(self):
        variants = []
        missing = row(); del missing["analysis"]["combined_score"]; variants.append(missing)
        for value in (None, 0, -1, float("inf"), float("nan")):
            variants.append(row(score=value))
        contradictory = row(); contradictory["analysis"]["status"] = "REGRESSION"; variants.append(contradictory)
        wrong_tier = row(); wrong_tier["analysis"]["tier"] = "probe"; variants.append(wrong_tier)
        for primary in ([], ["missing"], [METRIC, METRIC]):
            malformed = row(); malformed["analysis"]["primary"] = primary; variants.append(malformed)
        missing_noise = row(); del missing_noise["analysis"]["metrics"][METRIC]["noise_relative"]; variants.append(missing_noise)
        advisory = row(); advisory["analysis"]["metrics"][METRIC]["advisory"] = True; variants.append(advisory)
        for data in variants:
            with self.subTest(analysis=data["analysis"]):
                with self.assertRaisesRegex(ValueError, "FAST_PASS analysis"):
                    self.population.record(data, candidate(), PATCH, "b" * 40)
                self.assertEqual(self.population.eligible_parents(), {})
                self.assertFalse(self.population.path.exists())
                self.assertFalse(pop.advancement_evidence(data)["eligible"])

    def test_invalid_persisted_fitness_is_filtered_read_only(self):
        self.add()
        state = self.population._state()
        del state["entries"]["one"]["analysis"]["combined_score"]
        pop._atomic(self.population.path, state)
        before = self.files()
        self.assertEqual(self.population.eligible_parents(), {})
        brief = self.population.next_brief([], "", {}, persist=False)
        self.assertEqual(brief["parent"]["kind"], "baseline")
        self.assertEqual(before, self.files())

    def test_real_probe_sample_lists_produce_labeled_parent_deltas(self):
        signals = {"swapin-disk": {"swapin_vmstat_delta.swap_ra_hit": [100]},
                   "metadata-brd": {"metadata_delta_bytes_per_capacity_slot": [.2]}}
        parent = row(); parent["probe_signals"] = copy.deepcopy(signals)
        self.population.record(parent, candidate(), PATCH + "+parent\n", "b" * 40)
        child = row("two", score=1.2)
        child["probe_signals"] = {"swapin-disk": {"swapin_vmstat_delta.swap_ra_hit": [110]},
                                  "metadata-brd": {"metadata_delta_bytes_per_capacity_slot": [.201]}}
        entry = self.population.record(child, candidate("two", parent_candidate="one", parent_commit="1" * 40),
                                       PATCH + "+child\n", "c" * 40)
        self.assertEqual(entry["probe_signals"], child["probe_signals"])
        self.assertEqual(self.population.eligible_parents()["one"]["probe_signals"], signals)
        self.assertIn("median of retained samples", entry["parent_delta"]["signal_summary"])
        deltas = entry["parent_delta"]["probe_signals"]
        self.assertEqual(deltas["swapin-disk.swapin_vmstat_delta.swap_ra_hit"], 10)
        self.assertAlmostEqual(deltas["metadata-brd.metadata_delta_bytes_per_capacity_slot"], .001)
        self.assertEqual(pop._flatten({"counter": [100, 2, 1]})["counter"], 2)


if __name__ == "__main__":
    unittest.main()
