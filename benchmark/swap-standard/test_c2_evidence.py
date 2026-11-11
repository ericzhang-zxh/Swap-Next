# SPDX-License-Identifier: GPL-2.0-only
"""Revision-9 synthetic protocol replay; no fixture is runtime evidence."""
import copy
import unittest

import configurations as catalog
import evidence
from test_evidence import thp

CANDIDATE = "c" * 40
TREE = "d" * 40


def binding(role="candidate", frontend="independent"):
    return {"contract_id": catalog.C2_CONTRACT, "source_role": role,
            "source_commit": catalog.C2_BASELINE if role == "baseline" else CANDIDATE,
            "source_tree": TREE, "frontend": frontend,
            "observer_id": catalog.C2_OBSERVER["id"],
            "observer_symbol": catalog.C2_OBSERVER["arms"][role]["symbol"]}


def case(case_id="c-independent"):
    ident, role, group = next(row for row in catalog.C2_CASES if row[0] == case_id)
    return dict(copy.deepcopy(catalog.C2_GROUPS[group]), id=ident, role=role, group=group)


def fields(prefix, values):
    return prefix + " " + " ".join(str(key) + "=" + str(value) for key, value in values.items())


def snapshot(generation=1, point="before", positive=True, test=0):
    value = dict.fromkeys(evidence.C2_SNAPSHOT_KEYS, 0)
    value.update(ram_pages=1048576, cap_pages=209715, allocator_chain_pages=4,
                 cap_headroom_pages=4, pool_create_ok=1)
    if point != "before" and positive:
        value.update(entry_allocs=8192, handle_allocs=8192, published=8192,
                     charge_calls=8192, charge_ok=8192, charged_total_bytes=524288,
                     peak_backing_pages=128, store_token_peak=1)
        if point == "effect":
            value.update(entries_live=8192, compressed_live=8192, handles_live=8192,
                         index_live=8192, lru_live=8192, stored_bytes=524288,
                         owner_refs=8192, charged_bytes=524288, pool_backing_pages=128)
        else:
            value.update(entry_frees=8192, handle_frees=8192, retired=8192,
                         uncharged_total_bytes=524288, uncharge_calls=8192,
                         compressed_loads=8192)
    if point == "reset":
        value["pool_destroy_returned"] = 1
    return dict(schema="1", type=1, generation=generation, pool=generation,
                snapshot=("before", "effect", "after", "reset").index(point) + 1,
                state="destroyed" if point == "reset" else "active", codec="lzo",
                driver="lzo_generic", test=test, **value)


def snapshot_lines(value):
    header = tuple("schema type generation pool snapshot state codec driver test".split())
    return [fields("XSWAP_FRONTEND_BEGIN", {key: value[key] for key in header}),
            *[key + " " + str(value[key]) for key in evidence.C2_SNAPSHOT_KEYS],
            fields("XSWAP_FRONTEND_END", {key: value[key] for key in
                    ("schema", "type", "generation", "snapshot")})]


def policy(phase, point, config="c2-independent"):
    absent = config.endswith("independent")
    reset = point == "reset"
    return fields("COMPRESS_POLICY", dict(phase=phase, point=point,
        zswap_present=0 if absent else 1, zswap_enabled="absent" if absent else 1,
        zswap_pool_percent="absent" if absent else 20, zswap_shrinker="absent" if absent else 0,
        zswap_codec="absent" if absent else "lzo", zswap_quota="absent" if absent or reset else "max",
        swap_quota="absent" if reset else "max", cgroup_inode=0 if reset else 11,
        parent_inode=10, cgroup_errno=2 if reset else 0,
        memory_current="absent" if reset else 33554432,
        memory_swap_current="absent" if reset else 0))


def swaps(phase, point, devices=None):
    if devices is None:
        devices = [] if point == "reset" else ["xswap1\tvirtual\t1048576\t32768\t32767"]
    return [fields("COMPRESS_SWAPS", dict(phase=phase, point=point)),
            "Filename\tType\tSize\tUsed\tPriority", *devices,
            fields("COMPRESS_SWAPS_END", dict(phase=phase, point=point))]


def independent_phase(name, generation, spec=None):
    spec = spec or case()
    positive = name != "zero_control"
    lines = [fields("COMPRESS_BEGIN", dict(schema=2, contract=catalog.C2_CONTRACT,
        role=spec["role"], source=CANDIDATE, case=spec["id"], phase=name, frontend="independent",
        type=1, generation=generation, token=generation))]
    for point in ("before", "effect", "after", "reset"):
        lines += [policy(name, point, spec["config_id"]), *swaps(name, point),
                  fields("COMPRESS_SNAPSHOT", dict(phase=name, point=point)),
                  *snapshot_lines(snapshot(generation, point, positive)),
                  fields("COMPRESS_SNAPSHOT_END", dict(phase=name, point=point))]
        if point == "effect":
            lines += [fields("COMPRESS_RESIDENCY", dict(phase=name, frontend="independent",
                pattern="nonzero" if positive else "zero", pattern_generation=1,
                pages=8192, swapped=8192, nonresident=8192, type=1, key_first=1, key_last=8192))]
        if point == "after":
            lines += [fields("COMPRESS_DATA", dict(phase=name, checked_words=4194304,
                corrupt_words=0, completed_faults=8192, child_signal=0))]
    lines += [fields("COMPRESS_RESET", dict(schema=2, case=spec["id"], phase=name, status="PASS")),
              fields("COMPRESS_END", dict(schema=2, case=spec["id"], phase=name, status="PASS"))]
    return "\n".join(lines) + "\n"


def group_log():
    spec = case()
    body = "COMPRESSION_GROUP_BEGIN independent-roundtrip\n"
    body += independent_phase("independent_roundtrip", 1) + independent_phase("zero_control", 2)
    return body + "COMPRESSION_GROUP_END independent-roundtrip\n", spec


def basic_log(spec, arm=None):
    arm = arm or binding(spec["role"], spec["frontend"])
    args = dict(image_sha="abc", backend=spec["backend"], mode=spec["mode"], workload=spec["workload"],
                protocol_revision=9, config_id=spec["config_id"], topology_id=spec["topology_id"],
                contract_id=arm["contract_id"], source_role=arm["source_role"],
                source_commit=arm["source_commit"], frontend=arm["frontend"], observer=arm["observer_id"],
                correctness_case=spec["id"], correctness_group=spec["group"],
                compression_cases=",".join(spec["subcases"]))
    return ("BENCH_BOOT\nCMDLINE_BEGIN\n" + " ".join("bench." + key + "=" + str(value)
            for key, value in args.items()) + "\nCMDLINE_END\n" + thp() +
            "ONLINE_NODES flat\nGUEST_TOPOLOGY single\n" +
            "KERNEL_LOG_BEGIN\nLinux test fixture\nKERNEL_LOG_END\nBENCH_WORKLOAD_PASS\nBENCH_PASS\n")


def event(name, seq, op=1, kind="store", **updates):
    values = dict.fromkeys(evidence.C2_EVENT_KEYS, 0)
    values.update(schema=1, seq=seq, token=1, type=1, generation=1, op=op, kind=kind,
                  event=name, stage="none", key=10, count=1)
    values.update(updates)
    return values


def event_lines(events):
    envelope = dict(schema=1, first=events[0]["seq"], last=events[-1]["seq"], lost=0)
    return [fields("XSWAP_EVENTS_BEGIN", envelope),
            *[fields("XSWAP_EVENT", value) for value in events],
            fields("XSWAP_EVENTS_END", envelope)]


class C2IndependentEvidenceTests(unittest.TestCase):
    def parse(self, body=None, spec=None, arm=None):
        default, default_spec = group_log()
        body = default if body is None else body
        spec = spec or default_spec
        return evidence.parse(basic_log(spec, arm) + body, "abc", spec["backend"], spec["mode"],
            spec["workload"], 9, config_id=spec["config_id"], correctness_case=spec["id"],
            topology_id=spec["topology_id"], expected_case=spec, source_binding=arm or binding())

    def rejected(self, body, reason=None):
        try:
            parsed = self.parse(body)
        except ValueError as exc:
            if reason:
                self.assertIn(reason, str(exc))
        else:
            self.assertFalse(all(parsed["gates"].values()), parsed)
            if reason:
                errors = " ".join(row.get("evidence_error", "") for row in parsed["correctness_subcases"].values())
                self.assertIn(reason, errors)

    def test_positive_independent_and_zero_do_not_require_legacy_vmstat(self):
        result = self.parse()
        self.assertTrue(all(result["gates"].values()), result)
        self.assertEqual(result["metrics"]["c2_activity"],
            dict(independent_loads=8192, physical_reads=0, physical_writes=0, legacy_loads=0, legacy_stores=0))
        self.assertIsNone(result["metrics"]["vmstat_delta"])

    def test_missing_duplicate_reordered_phase_rejected(self):
        body, spec = group_log()
        for bad in (body.replace(independent_phase("zero_control", 2), ""),
                    body.replace("COMPRESSION_GROUP_END", independent_phase("zero_control", 3) + "COMPRESSION_GROUP_END"),
                    body.replace(independent_phase("independent_roundtrip", 1) + independent_phase("zero_control", 2),
                                 independent_phase("zero_control", 2) + independent_phase("independent_roundtrip", 1))):
            with self.subTest():
                self.rejected(bad)

    def test_wrong_source_or_role_rejected(self):
        body, spec = group_log()
        self.rejected(body.replace("source=" + CANDIDATE, "source=" + "e" * 40, 1))
        self.rejected(body.replace("role=candidate", "role=baseline", 1))
        for key, value in (("source_role", "baseline"), ("source_commit", catalog.C2_BASELINE),
                           ("observer_symbol", "zswap_load"), ("observer_id", "pid_kretprobe")):
            arm = binding()
            arm[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.parse(arm=arm)

    def test_fake_raw_zero_cache_physical_traffic_rejected(self):
        body, _ = group_log()
        for before, after, reason in (
            ("raw_admitted 0", "raw_admitted 1", "raw admission"),
            ("pattern=nonzero", "pattern=zero", "positive compressed target"),
            ("nonresident=8192", "nonresident=1", "positive compressed target"),
            ("compressed_loads 8192", "compressed_loads 0", "decoder proof"),
            ("write_submitted 0", "write_submitted 1", "counter"),
        ):
            with self.subTest(reason=reason):
                # Changing only the first before counter causes a decreasing lifetime.
                self.rejected(body.replace(before, after, 1), reason)

    def test_zero_requires_real_residency_full_data_and_no_compression(self):
        body, _ = group_log()
        zero_phase = independent_phase("zero_control", 2)
        for before, after in (("nonresident=8192", "nonresident=0"),
                              ("checked_words=4194304", "checked_words=512"),
                              ("completed_faults=8192", "completed_faults=0")):
            with self.subTest(before=before):
                self.rejected(body.replace(zero_phase, zero_phase.replace(before, after, 1)), "zero control")

    def test_unknown_duplicate_missing_snapshot_field_rejected(self):
        value = snapshot()
        lines = snapshot_lines(value)
        for bad in (lines[:-1], lines[:2] + lines[1:],
                    [line.replace("ram_pages ", "unknown_pages ") for line in lines]):
            with self.subTest(), self.assertRaises(ValueError):
                evidence.c2_snapshot(bad)

    def test_terminal_leaks_and_wrong_charge_arithmetic_rejected(self):
        for key in ("owner_refs", "charged_bytes", "backing_live", "retained_folios_live",
                    "store_token_active", "events_lost"):
            value = snapshot(point="reset")
            value[key] = 1
            with self.subTest(key=key), self.assertRaises(ValueError):
                evidence.c2_snapshot(snapshot_lines(value))

    def test_cross_phase_generation_reuse_fails(self):
        body, _ = group_log()
        second = independent_phase("zero_control", 2)
        self.rejected(body.replace(second, second.replace("generation=2", "generation=1")
                                   .replace("pool=2", "pool=1")), "generation reused")

    def test_snapshot_sequence_and_type_substitution_fail(self):
        body, _ = group_log()
        self.rejected(body.replace("snapshot=2", "snapshot=1"), "sequence")
        self.rejected(body.replace("type=1 generation=1 pool=1 snapshot=2",
                                   "type=2 generation=1 pool=1 snapshot=2"))

    def test_reset_and_policy_restore_are_observed(self):
        body, _ = group_log()
        self.rejected(body.replace("COMPRESS_RESET schema=2 case=c-independent phase=zero_control status=PASS",
                                   "COMPRESS_RESET schema=2 case=c-independent phase=zero_control status=INCOMPLETE"))
        self.rejected(body.replace("point=reset zswap_present=0", "point=reset zswap_present=1", 1))
        self.rejected(body.replace("point=reset\nFilename\tType\tSize\tUsed\tPriority\n",
            "point=reset\nFilename\tType\tSize\tUsed\tPriority\nxswap1 virtual 1048576 0 32767\n", 1),
            "empty swap reset")

    def test_warning_fails_despite_complete_phase_proof(self):
        body, spec = group_log()
        text = basic_log(spec).replace("Linux test fixture", "Linux test fixture\nWARNING: test") + body
        parsed = evidence.parse(text, "abc", "compressed", "xswap", "compression", 9,
            config_id=spec["config_id"], correctness_case=spec["id"], topology_id="single",
            expected_case=spec, source_binding=binding())
        self.assertTrue(parsed["gates"]["compression_evidence"])
        self.assertFalse(parsed["gates"]["no_new_kernel_warnings"])

    def test_duplicate_outer_identity_blocks_and_stray_topology_fail(self):
        body, spec = group_log()
        text = basic_log(spec) + body
        for extra in ("CMDLINE_BEGIN\nbench.source_role=baseline\nCMDLINE_END\n",
                      "GUEST_TOPOLOGY other\n"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                evidence.c2_source_identity(text + extra, "compressed", "xswap", "compression",
                    spec["config_id"], spec["id"], "single", spec, binding())

    def test_source_cmdline_duplicate_fails(self):
        body, spec = group_log()
        text = basic_log(spec).replace("CMDLINE_END", "bench.source_role=candidate\nCMDLINE_END") + body
        with self.assertRaises(ValueError):
            evidence.c2_source_identity(text, "compressed", "xswap", "compression",
                spec["config_id"], spec["id"], "single", spec, binding())


class C2RawAdapterTests(unittest.TestCase):
    def test_actual_intersecting_operation_journal(self):
        values = [event("op_begin", 1), event("charge_call", 2, flags=32),
                  event("op_begin", 3, op=2, kind="load"),
                  event("overlap", 4, op=2, kind="load", peer=1),
                  event("op_end", 5, op=2, kind="load"), event("op_end", 6)]
        self.assertEqual(len(evidence.c2_events(event_lines(values), 1)), 6)
        for change in (dict(peer=3), dict(key=20), dict(generation=2)):
            bad = copy.deepcopy(values)
            bad[3].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                evidence.c2_events(event_lines(bad), 1)

    def test_injection_is_not_core_charge_or_completion(self):
        for name, flags in (("charge_call", 16), ("bio_complete", 0)):
            values = [event("op_begin", 1), event(name, 2, flags=flags), event("op_end", 3)]
            with self.subTest(name=name), self.assertRaises(ValueError):
                evidence.c2_events(event_lines(values), 1)

    def test_journal_loss_gap_duplicate_and_unfinished_rejected(self):
        values = [event("op_begin", 1), event("op_end", 2)]
        lines = event_lines(values)
        variants = [[line.replace("lost=0", "lost=1") for line in lines],
                    [line.replace("seq=2", "seq=3") for line in lines],
                    event_lines([event("op_begin", 1), event("op_begin", 2)]),
                    event_lines([event("op_begin", 1), event("publish", 2)])]
        for bad in variants:
            with self.subTest(), self.assertRaises(ValueError):
                evidence.c2_events(bad, 1)

    def test_actual_policy_absence_and_cpu_ranges(self):
        self.assertEqual(evidence.c2_policy(policy("test", "before"))["zswap_present"], 0)
        for bad in (policy("test", "before").replace("zswap_enabled=absent", "zswap_enabled=0"),
                    policy("test", "reset").replace("memory_current=absent", "memory_current=0")):
            with self.assertRaises(ValueError):
                evidence.c2_policy(bad)
        self.assertEqual(evidence.c2_cpu_list("0-1,3"), {0, 1, 3})
        for bad in ("00-1", "0-2,2-3", "0-4", "2-1", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evidence.c2_cpu_list(bad)

    def test_controls_are_exact_bounded_actual_acknowledgements(self):
        line = ("XSWAP_CONTROL schema=1 command=hold type=1 generation=1 token=1 status=ok "
                "point=load_after_lookup key=next count=1 timeout_ms=1000")
        self.assertEqual(evidence.c2_control(line)["timeout_ms"], 1000)
        for bad in (line.replace("timeout_ms=1000", "timeout_ms=0"),
                    line.replace("status=ok", "status=FAIL"), line + " invented=1",
                    line.replace("point=load_after_lookup", "point=user_sleep")):
            with self.subTest(), self.assertRaises(ValueError):
                evidence.c2_control(bad)



def smaps_fixture():
    return ("100000-101000 r-xp 00000000 08:01 1 /bin/swapin\n"
            "Size: 4 kB\nLocked: 4 kB\nVmFlags: rd ex mr mw me lo\n"
            "20000000-28000000 rw-p 00000000 00:00 0\n"
            "Size: 131072 kB\nLocked: 0 kB\nAnonHugePages: 0 kB\n"
            "KernelPageSize: 4 kB\nMMUPageSize: 4 kB\nVmFlags: rd wr mr mw me ac nh\n"
            "30000000-30001000 ---p 00000000 00:00 0\n"
            "Size: 4 kB\nLocked: 0 kB\nVmFlags: mr mw me\n"
            "40000000-40001000 r-xp 00000000 00:00 0 [vdso]\n"
            "Size: 4 kB\nLocked: 0 kB\nVmFlags: rd ex mr mw me\n")


def isolation_log(raw=None):
    raw = smaps_fixture() if raw is None else raw
    derived = dict(locked_mappings=1, locked_mapping_bytes=4096, locked_resident_bytes=4096,
                   target_mappings=1, target_unlocked_bytes=134217728,
                   special_mappings=1, inaccessible_mappings=1)
    lines = ["COMPRESSED_ISOLATION_SETUP mlockall=0 munlock=0 flags=current_future target_bytes=134217728"]
    for phase in ("before_reclaim", "after_measurement"):
        lines += [fields("COMPRESSED_ISOLATION_BEGIN", dict(phase=phase,
            strategy=evidence.C2_ISOLATION_STRATEGY, target_start=536870912,
            target_bytes=134217728, bytes=len(raw.encode()), encoding="hex"))]
        encoded = raw.encode().hex()
        lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
        lines += [fields("COMPRESSED_ISOLATION_END", dict(phase=phase, **derived))]
    return "\n".join(lines) + "\n"


class C2IsolationTests(unittest.TestCase):
    def test_actual_locked_observer_and_exact_unlocked_target(self):
        result = evidence.c2_isolation_evidence(isolation_log())
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["target_unlocked_bytes"], 134217728)

    def test_success_syscalls_and_fabricated_aggregates_do_not_prove_isolation(self):
        for before, after in (("target_unlocked_bytes=134217728", "target_unlocked_bytes=134217727"),
                              ("locked_mappings=1", "locked_mappings=2"),
                              ("mlockall=0", "mlockall=-1")):
            with self.subTest(before=before), self.assertRaises(ValueError):
                evidence.c2_isolation_evidence(isolation_log().replace(before, after))

    def test_target_gap_huge_or_locked_page_fails(self):
        for before, after in (("20000000-28000000", "20001000-28000000"),
                              ("AnonHugePages: 0", "AnonHugePages: 2048"),
                              ("MMUPageSize: 4", "MMUPageSize: 2048"),
                              ("me ac nh", "me ac lo nh"),
                              ("me ac nh", "me ac lf nh"),
                              ("me ac nh", "me ac")):
            with self.subTest(before=before), self.assertRaises(ValueError):
                evidence.c2_isolation_evidence(isolation_log(smaps_fixture().replace(before, after)))

    def test_accessible_unlocked_shared_or_fabricated_special_observer_fails(self):
        for before, after in (("me lo", "me"), ("me lo", "me lo lf"), ("r-xp", "r-xs"),
                              ("[vdso]", "[invented]"), ("[vdso]", "[vdso] fake")):
            with self.subTest(before=before), self.assertRaises(ValueError):
                evidence.c2_isolation_evidence(isolation_log(smaps_fixture().replace(before, after)))

    def test_raw_truncation_duplicate_vma_fields_and_phase_reorder_fail(self):
        raw = smaps_fixture().replace("Locked: 4 kB", "Locked: 4 kB\nLocked: 4 kB")
        with self.assertRaises(ValueError):
            evidence.c2_isolation_evidence(isolation_log(raw))
        text = isolation_log()
        size = len(smaps_fixture().encode())
        for bad in (text.replace("bytes=" + str(size), "bytes=" + str(size + 1)),
                    text.replace("phase=after_measurement", "phase=before_reclaim"),
                    text[:text.index("COMPRESSED_ISOLATION_BEGIN phase=after_measurement")]):
            self.assertNotEqual(bad, text)
            with self.subTest(), self.assertRaises(ValueError):
                evidence.c2_isolation_evidence(bad)


def timing_probe_log(arm):
    data = {
        "kprobe_events": "r64:swap_next_timing/decode_return " + arm["observer_symbol"] + " ret=$retval:s64\n",
        "current_tracer": "nop\n", "buffer_size_kb": "16\n", "event_filter": "common_pid == 123\n",
        "event_enable": "1\n", "tracing_on": "1\n",
        "event_format": "name: decode_return\nID: 123\nformat:\n\tfield:s64 ret;\toffset:24;\tsize:8;\tsigned:1;\n",
        "trace_options": "context-info\nnolatency-format\nnohex\nnobin\nnoraw\nnoverbose\n",
    }
    lines = []
    for name, raw in data.items():
        lines += [fields("COMPRESSED_PROBE_READBACK_BEGIN", dict(phase="setup", name=name, bytes=len(raw), encoding="hex"))]
        encoded = raw.encode().hex()
        lines += [encoded[i:i + 128] for i in range(0, len(encoded), 128)]
        lines += ["COMPRESSED_PROBE_READBACK_END name=" + name]
    return "\n".join(lines) + "\n"


def c2_timing_log(role="candidate"):
    from test_compression_evidence import basic_log as c1_basic_log
    arm = binding(role, "independent" if role == "candidate" else "legacy")
    text = c1_basic_log("compressed", "xswap", "swapin").replace("bench.protocol_revision=8", "bench.protocol_revision=9")
    identity = ("bench.contract_id=" + arm["contract_id"] + " bench.source_role=" + role +
                " bench.source_commit=" + arm["source_commit"] + " bench.frontend=" + arm["frontend"] +
                " bench.observer=" + arm["observer_id"])
    text = text.replace("\nCMDLINE_END", " " + identity + "\nCMDLINE_END")
    if role == "candidate":
        text = text.replace("zswpin 32768", "zswpin 0").replace("zswpout 32768", "zswpout 0")
    text += timing_probe_log(arm)
    text += fields("COMPRESSED_OBSERVER", dict(id=arm["observer_id"], instrumented=1, clock="monotonic_raw",
        maxactive=64, contract=arm["contract_id"], role=role, source=arm["source_commit"],
        frontend=arm["frontend"], symbol=arm["observer_symbol"], buffer_kb=16, success_return=0)) + "\n"
    text += "COMPRESSED_TOPOLOGY phase=before devices=1 physical=0 type=1\n"
    iso = isolation_log()
    split = iso.index("COMPRESSED_ISOLATION_BEGIN phase=after_measurement")
    for point in ("before", "stored", "after"):
        actual = snapshot(1, {"before": "before", "stored": "effect", "after": "after"}[point])
        for key in ("entries_live", "compressed_live", "handles_live", "index_live", "lru_live",
                    "stored_bytes", "owner_refs", "charged_bytes", "pool_backing_pages", "entry_allocs",
                    "entry_frees", "handle_allocs", "handle_frees", "published", "retired", "charge_calls",
                    "charge_ok", "charged_total_bytes", "uncharged_total_bytes", "uncharge_calls",
                    "peak_backing_pages", "compressed_loads"):
            actual[key] *= 4
        if role == "candidate":
            text += "COMPRESSED_FRONTEND_BEGIN phase=" + point + "\n"
            text += "\n".join(snapshot_lines(actual)) + "\n"
            text += "COMPRESSED_FRONTEND_END phase=" + point + "\n"
        text += fields("COMPRESSED_STATE", dict(phase=point, stored_pages=actual["compressed_live"],
                    pool_bytes=actual["pool_backing_pages"] * 4096, incompressible_pages=0)) + "\n"
        if role == "baseline":
            text += fields("COMPRESSED_LEGACY_CONFIG", dict(phase=point, codec="lzo", max_pool_percent=20,
                ram_pages=1048576, cap_pages=209715, shrinker_enabled=0)) + "\n"
            text += fields("COMPRESSED_LEGACY_LIMITS", dict(phase=point, pool_limit_hit=0,
                written_back_pages=0, reject_compress_poor=0)) + "\n"
        if point == "before":
            text += iso[:split] + "SWAPIN_SWAPPED pages=32768 swapped=32768 reclaim_rounds=1\n"
    text += "COMPRESSED_TOPOLOGY phase=after devices=1 physical=0 type=1\n" + iso[split:]
    text += ("COMPRESSED_SAMPLES seq=16384 rand=16384 target_checks=32768 decoded=32768 trace_lost=0 probe_missed=0 probe_hits=32768\n"
             "SWAPIN_SEQ samples=16384 mean_ns=100 p99_ns=200\n"
             "SWAPIN_RAND samples=16384 mean_ns=110 p99_ns=220\nSWAPIN_DATA_PASS\n")
    return text, arm


class C2MatchedTimingTests(unittest.TestCase):
    def parse(self, text, arm):
        return evidence.parse(text, "abc", "compressed", "xswap", "swapin", 9, config_id="c1-common",
                              topology_id="single", source_binding=arm)

    def rejected(self, text, arm):
        try:
            parsed = self.parse(text, arm)
        except ValueError:
            return
        self.assertFalse(all(parsed["gates"].values()), parsed)

    def test_both_matched_arms_have_actual_route_and_isolation_proof(self):
        for role in ("baseline", "candidate"):
            text, arm = c2_timing_log(role)
            with self.subTest(role=role):
                parsed = self.parse(text, arm)
                self.assertTrue(all(parsed["gates"].values()), parsed)
                self.assertEqual(parsed["metrics"]["compressed_probe"]["symbol"], arm["observer_symbol"])

    def test_missing_or_wrong_source_registration_fails(self):
        text, arm = c2_timing_log()
        for bad in (text.replace("symbol=xswap_load_folio", "symbol=zswap_load"),
                    text.replace("COMPRESSED_PROBE_READBACK_BEGIN phase=setup name=kprobe_events",
                                 "COMPRESSED_PROBE_READBACK_BEGIN phase=setup name=wrong"),
                    text.replace("buffer_kb=16", "buffer_kb=32")):
            with self.subTest():
                self.rejected(bad, arm)
        wrong = timing_probe_log(dict(arm, observer_symbol="zswap_load"))
        self.rejected(text.replace(timing_probe_log(arm), wrong), arm)

    def test_candidate_legacy_counter_or_fake_normalized_state_fails(self):
        text, arm = c2_timing_log()
        for before, after in (("phase=stored stored_pages=32768", "phase=stored stored_pages=32767"),
                              ("compressed_loads 32768", "compressed_loads 1"),
                              ("cap_rejects 0", "cap_rejects 1"),
                              ("test=0", "test=1"),
                              ("read_submitted 0", "read_submitted 1")):
            with self.subTest(before=before):
                self.rejected(text.replace(before, after, 1), arm)

    def test_legacy_cap_writeback_or_incompressible_fallback_fails(self):
        text, arm = c2_timing_log("baseline")
        for before, after in (("phase=stored pool_limit_hit=0", "phase=stored pool_limit_hit=1"),
                              ("max_pool_percent=20", "max_pool_percent=30"),
                              ("shrinker_enabled=0", "shrinker_enabled=1"),
                              ("incompressible_pages=0", "incompressible_pages=1")):
            with self.subTest(before=before):
                self.rejected(text.replace(before, after, 1), arm)

    def test_exact_decode_counts_and_no_loss_required(self):
        text, arm = c2_timing_log()
        for before, after in (("decoded=32768", "decoded=32767"), ("probe_missed=0", "probe_missed=1"),
                              ("trace_lost=0", "trace_lost=1"), ("rand=16384", "rand=1"),
                              ("pages=32768 swapped=32768", "pages=32768 swapped=1")):
            with self.subTest(before=before):
                self.rejected(text.replace(before, after, 1), arm)

    def test_actual_isolation_proof_cannot_be_omitted_or_moved_after_reclaim(self):
        text, arm = c2_timing_log()
        self.rejected(text.replace("COMPRESSED_ISOLATION_SETUP", "IGNORED_ISOLATION_SETUP"), arm)
        marker = "SWAPIN_SWAPPED pages=32768 swapped=32768 reclaim_rounds=1\n"
        moved = marker + text.replace(marker, "")
        self.rejected(moved, arm)


class C2PhaseReadbackTests(unittest.TestCase):
    def record(self, name="independent_roundtrip"):
        text, spec = group_log()
        _, records = evidence.c2_compression_evidence(text, spec, binding())
        result = copy.deepcopy(records["independent_roundtrip"])
        result["phase"] = result["identity"]["phase"] = name
        return result

    def test_cpu_hotplug_requires_actual_offline_online_and_live_interval(self):
        record = self.record("live_cpu_hotplug")
        record["cpu"] = {point: {"target": 2, "online": online} for point, online in
                          (("before", "0-3"), ("offline", "0-1,3"), ("online", "0-3"), ("reset", "0-3"))}
        record["positions"].update({"snapshot:effect": 10, "cpu:offline": 20,
                                     "cpu:online": 30, "snapshot:after": 40})
        evidence.c2_phase_readbacks(record)
        for mutation in ("no_offline", "wrong_target", "after_drain"):
            bad = copy.deepcopy(record)
            if mutation == "no_offline":
                bad["cpu"]["offline"]["online"] = "0-3"
            elif mutation == "wrong_target":
                bad["cpu"]["online"]["target"] = 1
            else:
                bad["positions"]["cpu:offline"] = 50
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evidence.c2_phase_readbacks(bad)

    def test_legacy_actual_overlap_requires_live_distinct_operations_and_hold(self):
        keys = ("schema", "token", "epoch", "type", "pool", "owner", "first", "last", "lost")
        header = dict(zip(keys, (1, 1, 77, 2, 4, 11, 1, 8, 0)))
        rows = []
        for sequence, (op, kind, event, stage, peer) in enumerate((
            (1, "pool_release", "op_begin", "pool_release_enter", 0),
            (1, "pool_release", "hold_enter", "pool_release_enter", 0),
            (2, "memcg_offline", "op_begin", "memcg_offline_enter", 0),
            (2, "memcg_offline", "overlap", "memcg_offline_enter", 1),
            (1, "pool_release", "hold_release", "pool_release_enter", 0),
            (2, "memcg_offline", "op_end", "memcg_offline_returned", 0),
            (1, "pool_release", "op_end", "pool_release_returned", 0),
        ), 1):
            rows.append(dict(schema=1, seq=sequence, token=1, epoch=77, type=2, op=op,
                kind=kind, event=event, stage=stage, pool=4, owner=11, peer=peer, result=0))
        header["last"] = len(rows)
        def encoded(values):
            return [fields("XSWAP_LEGACY_EVENTS_BEGIN", header),
                    *[fields("XSWAP_LEGACY_EVENT", value) for value in values],
                    fields("XSWAP_LEGACY_EVENTS_END", header)]
        self.assertEqual(len(evidence.c2_legacy_events(encoded(rows), 1)["events"]), 7)
        for mutation in ("peer", "epoch", "timeout", "hold", "return"):
            bad = copy.deepcopy(rows)
            if mutation == "peer":
                bad[3]["peer"] = 3
            elif mutation == "epoch":
                bad[3]["epoch"] = 78
            elif mutation == "timeout":
                bad[4]["result"] = -110
            elif mutation == "hold":
                bad[1]["event"] = "overlap"
            else:
                bad[-1]["stage"] = "pool_release_enter"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                evidence.c2_legacy_events(encoded(bad), 1)

    def test_wrong_allocator_node_and_absent_hook_do_not_pass_named_phases(self):
        for phase in ("independent_node0", "entry_refusal", "live_destroy", "fault_cow_invalidate"):
            record = self.record(phase)
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                evidence.c2_phase_semantics(record)

    def test_terminal_ack_must_follow_copied_terminal_snapshot(self):
        record = self.record()
        record["test_config"] = True
        for snapshots in record["snapshots"].values():
            for snapshot in snapshots:
                snapshot["test"] = 1
        reset = record["positions"]["snapshot:reset"]
        record["controls"] = [dict(command="ack", generation=1, _position=reset + 1)]
        evidence.c2_phase_semantics(record)
        for position in (0, reset):
            bad = copy.deepcopy(record)
            bad["controls"][0]["_position"] = position
            with self.subTest(position=position), self.assertRaises(ValueError):
                evidence.c2_phase_semantics(bad)
        record["controls"].append(copy.deepcopy(record["controls"][0]))
        with self.assertRaises(ValueError):
            evidence.c2_phase_semantics(record)

if __name__ == "__main__":
    unittest.main()
