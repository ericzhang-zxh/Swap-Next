# SPDX-License-Identifier: GPL-2.0-only
"""Revision-9 observer fixtures. No guest, kernel, or real mlock syscall runs."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parent
ANCHOR = "5e84ca928deeacb4eee656806a003f27d1eca82f"
CANDIDATE = "1234567890abcdef1234567890abcdef12345678"
TARGET = 134217728
START = 0x200000
KEYS = (
    "ram_pages cap_pages cap_updates cap_rejects bypasses incompressible_rejects raw_admitted "
    "entries_live compressed_live raw_live handles_live index_live lru_live stored_bytes owner_refs "
    "charged_bytes inflight store_token_active store_token_peak store_retries retained_folios_live "
    "retained_folio_gets retained_folio_puts pool_backing_pages peak_backing_pages allocator_chain_pages "
    "cap_headroom_pages entry_allocs entry_frees handle_allocs handle_frees published retired rollback_objects "
    "charge_calls charge_ok charge_fail charge_injected charged_total_bytes uncharge_calls uncharged_total_bytes "
    "compressed_loads raw_loads load_misses decode_errors backing_live backing_allocs backing_frees "
    "backing_charge_denials read_submitted write_submitted read_completed write_completed read_errors write_errors "
    "pool_create_ok pool_destroy_returned test_windows events_lost"
).split()


def smap(start, end, perms="rw-p", name="", locked=True, *, nh=False, huge=0):
    flags = [x for enabled, x in ((perms[0] == "r", "rd"), (perms[1] == "w", "wr"),
                                  (perms[2] == "x", "ex"), (perms[3] == "s", "sh"),
                                  (locked, "lo"), (nh, "nh")) if enabled]
    return (f"{start:016x}-{end:016x} {perms} 00000000 00:00 0" + (f" {name}" if name else "") + "\n"
            f"Size: {(end-start)//1024:8d} kB\nKernelPageSize:        4 kB\nMMUPageSize:        4 kB\n"
            f"AnonHugePages: {huge:8d} kB\nLocked: {((end-start)//1024 if locked else 0):8d} kB\n"
            "VmFlags: " + " ".join(flags) + " \n")


def smaps():
    return (smap(0x100000, 0x101000, "r-xp", "/bin/swapin")
            + smap(0x110000, 0x120000, name="[heap]")
            + smap(START, START + TARGET, locked=False, nh=True)
            + smap(0x9000000, 0x9001000, "---p", locked=False)
            + smap(0x9100000, 0x9101000, "r--p", "[vvar]", False)
            + smap(0x9200000, 0x9201000, "r-xp", "[vdso]", False))


def frontend(phase, **changes):
    values = dict.fromkeys(KEYS, 0)
    values.update(ram_pages=1048576, cap_pages=209715, allocator_chain_pages=4, cap_headroom_pages=4, pool_create_ok=1)
    seq = {"before": 1, "stored": 2, "after": 3}[phase]
    if phase != "before":
        values.update(store_token_peak=1, entry_allocs=32768, handle_allocs=32768,
                      published=32768, charge_calls=32768, charge_ok=32768,
                      charged_total_bytes=65536000, peak_backing_pages=18000)
    if phase == "stored":
        values.update(entries_live=32768, compressed_live=32768, handles_live=32768,
                      index_live=32768, lru_live=32768, stored_bytes=65536000,
                      owner_refs=32768, charged_bytes=65536000, pool_backing_pages=18000)
    if phase == "after":
        values.update(entry_frees=32768, handle_frees=32768, retired=32768,
                      uncharge_calls=32768, uncharged_total_bytes=65536000,
                      compressed_loads=32768)
    values.update(changes)
    return (f"XSWAP_FRONTEND_BEGIN schema=1 type=1 generation=7 pool=7 snapshot={seq} "
            "state=active codec=lzo driver=lzo-generic test=0\n"
            + "".join(f"{key} {values[key]}\n" for key in KEYS)
            + f"XSWAP_FRONTEND_END schema=1 type=1 generation=7 snapshot={seq}\n")


def cmdline(role="baseline"):
    source, frontend_name = (ANCHOR, "legacy") if role == "baseline" else (CANDIDATE, "independent")
    return (f"root=/dev/vda bench.protocol_revision=9 bench.contract_id=xswap-independent-v1 "
            f"bench.source_role={role} bench.source_commit={source} bench.frontend={frontend_name} "
            "bench.observer=pid_kretprobe_frontend_v2 bench.compression_target_bytes=134217728 "
            "bench.backend=compressed bench.mode=xswap bench.workload=swapin\n")


class C2TimingObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="swap-next-c2-observer-")
        cls.root = Path(cls.temp.name)
        cls.binary = cls.root / "observer-fixture"
        cls.trace = cls.root / "tracing"
        cls.instance = cls.trace / "instances/swap_next_timing"
        cls.event = cls.instance / "events/swap_next_timing/decode_return"
        cls.event.mkdir(parents=True)
        cls.front = cls.root / "frontend"
        cls.front.mkdir()
        cls.params = cls.root / "parameters"
        cls.params.mkdir()
        cls.debug = cls.root / "zswap"
        cls.debug.mkdir()
        definitions = {
            "TRACE_ROOT": str(cls.trace),
            "C2_SMAPS_PATH": str(cls.root / "smaps"),
            "C2_MEMINFO_PATH": str(cls.root / "meminfo"),
            "C2_CMDLINE_PATH": str(cls.root / "cmdline"),
            "C2_FRONTEND_ROOT": str(cls.front),
            "C2_ZSWAP_PARAMETERS": str(cls.params),
            "C2_ZSWAP_DEBUG": str(cls.debug),
        }
        wrapper = "".join(f"#define {name} {json.dumps(value)}\n" for name, value in definitions.items())
        wrapper += "#define mlockall fixture_mlockall\n#define munlock fixture_munlock\n"
        wrapper += "#define main swapin_guest_main\n#include " + json.dumps(str(BASE / "swapin.c")) + "\n#undef main\n"
        wrapper += r"""
static int lock_fail, unlock_fail, lock_calls, unlock_calls, lock_flags;
static const void *unlock_address;
static size_t unlock_size;
int fixture_mlockall(int flags)
{
    lock_calls++;
    lock_flags = flags;
    errno = lock_fail ? ENOMEM : 0;
    return lock_fail ? -1 : 0;
}
int fixture_munlock(const void *address, size_t bytes)
{
    unlock_calls++;
    unlock_address = address;
    unlock_size = bytes;
    errno = unlock_fail ? EINVAL : 0;
    return unlock_fail ? -1 : 0;
}
static void select_role(const char *role)
{
    c2_mode = true;
    c2_role = role;
    c2_source = !strcmp(role, "baseline") ? C2_ANCHOR :
        "1234567890abcdef1234567890abcdef12345678";
    c2_frontend = !strcmp(role, "baseline") ? "legacy" : "independent";
    c2_symbol = !strcmp(role, "baseline") ? "zswap_load" : "xswap_load_folio";
    compressed_type = 1;
    page = 4096;
}
int main(int argc, char **argv)
{
    static char raw[262144];
    size_t n;
    int result;
    if (argc < 2)
        return 90;
    select_role(argc > 2 && !strcmp(argv[2], "candidate") ? "candidate" : "baseline");
    if (!strcmp(argv[1], "args"))
        return c2_arguments(argc - 1, argv + 1) ? 1 : 0;
    if (!strcmp(argv[1], "isolate")) {
        lock_fail = argc > 2 && !strcmp(argv[2], "lock_fail");
        unlock_fail = argc > 2 && !strcmp(argv[2], "unlock_fail");
        result = c2_isolate((char *)(uintptr_t)0x200000, C2_TARGET_BYTES);
        printf("FIXTURE result=%d lock_calls=%d flags=%d unlock_calls=%d target=%" PRIuPTR " bytes=%zu\n",
               result, lock_calls, lock_flags, unlock_calls,
               (uintptr_t)unlock_address, unlock_size);
        return result ? 1 : 0;
    }
    if (!strcmp(argv[1], "isolation_after"))
        return c2_isolation_snapshot("after_measurement", (char *)(uintptr_t)0x200000,
                                     C2_TARGET_BYTES) ? 1 : 0;
    if (!strcmp(argv[1], "source"))
        return c2_source_readback() ? 1 : 0;
    if (!strcmp(argv[1], "probe")) {
        char filter[64];
        snprintf(filter, sizeof(filter), "common_pid == %ld\n",
                 argc > 2 && !strcmp(argv[2], "bad_pid") ? 0L : (long)getpid());
        if (text_write(TRACE_INSTANCE "/events/" TRACE_EVENT "/filter", filter, false))
            return 91;
        return c2_probe_readbacks() ? 1 : 0;
    }
    if (!strcmp(argv[1], "snapshots")) {
        const char *phases[] = { "before", "stored", "after" };
        uint64_t stored, pool, incompressible;
        select_role("candidate");
        verified_decode_samples = 32768;
        if (argc != 5)
            return 92;
        for (int i = 0; i < 3; i++) {
            if (c2_read(argv[i + 2], raw, sizeof(raw), &n) ||
                text_write(C2_FRONTEND_ROOT "/type1", raw, false) ||
                c2_frontend_snapshot(phases[i], &stored, &pool, &incompressible))
                return 1;
        }
        return 0;
    }
    if (!strcmp(argv[1], "counter_read")) {
        char path[256];
        uint64_t value;

        if (argc != 3)
            return 96;
        snprintf(path, sizeof(path), C2_ZSWAP_DEBUG "/%s", argv[2]);
        if (c2_read(path, raw, sizeof(raw), &n))
            return 2;
        printf("FIXTURE_COUNTER_READ_OK bytes=%zu\n", n);
        if (debug_number(argv[2], &value))
            return 1;
        printf("FIXTURE_COUNTER_VALUE value=%" PRIu64 "\n", value);
        return 0;
    }
    if (!strcmp(argv[1], "legacy")) {
        if (c2_legacy_snapshot("before", 0, 0, 0))
            return 1;
        if (argc > 2 && !strcmp(argv[2], "limit") &&
            text_write(C2_ZSWAP_DEBUG "/pool_limit_hit", "1\n", false))
            return 93;
        if (c2_legacy_snapshot("stored", 32768,
                               argc > 2 && !strcmp(argv[2], "cap") ? 209715ULL*4096 : 73728000,
                               argc > 2 && !strcmp(argv[2], "raw") ? 1 : 0))
            return 1;
        return c2_legacy_snapshot("after", 0, 0, 0) ? 1 : 0;
    }
    n = fread(raw, 1, sizeof(raw) - 1, stdin);
    if (ferror(stdin) || n == sizeof(raw) - 1 || memchr(raw, 0, n))
        return 94;
    raw[n] = 0;
    if (!strcmp(argv[1], "smaps")) {
        struct isolation_stats stats;
        result = c2_parse_smaps(raw, 0x200000, C2_TARGET_BYTES, &stats);
        if (!result)
            printf("%" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 " %" PRIu64 "\n",
                   stats.locked_mappings, stats.locked_mapping_bytes,
                   stats.locked_resident_bytes, stats.target_mappings,
                   stats.target_unlocked_bytes, stats.special_mappings,
                   stats.inaccessible_mappings);
        return result ? 1 : 0;
    }
    if (!strcmp(argv[1], "registration"))
        return c2_registration(raw) ? 1 : 0;
    if (!strcmp(argv[1], "format"))
        return c2_event_format(raw) ? 1 : 0;
    if (!strcmp(argv[1], "options"))
        return c2_trace_options(raw) ? 1 : 0;
    if (!strcmp(argv[1], "cmdline"))
        return c2_cmdline_matches(raw) ? 1 : 0;
    if (!strcmp(argv[1], "frontend") || !strcmp(argv[1], "frontend_valid")) {
        struct frontend_snapshot snapshot;
        result = c2_parse_frontend(raw, &snapshot);
        if (!result && !strcmp(argv[1], "frontend_valid"))
            result = c2_frontend_valid(&snapshot);
        return result ? 1 : 0;
    }
    return 95;
}
"""
        cls.wrapper = cls.root / "observer-fixture.c"
        cls.wrapper.write_text(wrapper)
        subprocess.run(["gcc", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(cls.wrapper), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        (self.root / "smaps").write_text(smaps())
        (self.root / "meminfo").write_text("MemTotal:       4194304 kB\nMemFree:        500000 kB\n")
        (self.root / "cmdline").write_text(cmdline())
        for name, text in {"compressor": "lzo\n", "max_pool_percent": "20\n", "shrinker_enabled": "N\n"}.items():
            (self.params / name).write_text(text)
        for name in ("pool_limit_hit", "written_back_pages", "reject_compress_poor"):
            (self.debug / name).write_text("0\n")
        (self.front / "type1").write_text(frontend("before"))
        (self.trace / "kprobe_events").write_text("r64:swap_next_timing/decode_return zswap_load ret=$retval:s64\n")
        (self.instance / "current_tracer").write_text("nop\n")
        (self.instance / "buffer_size_kb").write_text("16\n")
        (self.instance / "tracing_on").write_text("1\n")
        (self.event / "filter").write_text("none\n")
        (self.event / "enable").write_text("1\n")
        (self.event / "format").write_text(self.format())
        (self.instance / "trace_options").write_text(self.options())

    @staticmethod
    def format():
        return ("name: decode_return\nID: 101\nformat:\n"
                "\tfield:unsigned short common_type;\toffset:0;\tsize:2;\tsigned:0;\n"
                "\tfield:s64 ret;\toffset:24;\tsize:8;\tsigned:1;\n\n"
                'print fmt: "(%lx <- %lx) ret=%Ld", REC->__probe_func, REC->__probe_ret_ip, REC->ret\n')

    @staticmethod
    def options():
        return "context-info\nnolatency-format\nnohex\nnobin\nnoraw\nnoverbose\nannotate\n"

    def run_case(self, mode, raw=None, *args):
        return subprocess.run([str(self.binary), mode, *args], input=raw, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def assertPass(self, mode, raw=None, *args):
        result = self.run_case(mode, raw, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def assertFail(self, mode, raw=None, *args):
        result = self.run_case(mode, raw, *args)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    @staticmethod
    def args(role="baseline"):
        return ["134217728", "/sys/fs/cgroup/bench/memory.reclaim", "compressed", "1",
                "/sys/fs/cgroup/bench", "xswap-independent-v1", role,
                ANCHOR if role == "baseline" else CANDIDATE,
                "pid_kretprobe_frontend_v2", "legacy" if role == "baseline" else "independent"]

    def test_fixture_never_links_real_pinning_syscalls(self):
        symbols = subprocess.run(["nm", "-u", str(self.binary)], text=True,
                                 stdout=subprocess.PIPE, check=True).stdout
        self.assertNotIn(" mlockall", symbols)
        self.assertNotIn(" munlock", symbols)

    def test_both_source_roles_and_target_size_forms(self):
        for role in ("baseline", "candidate"):
            for size in ("134217728", "128M", "131072K"):
                with self.subTest(role=role, size=size):
                    args = self.args(role)
                    args[0] = size
                    self.assertPass("args", None, *args)

    def test_arguments_fail_closed(self):
        base = self.args()
        mutations = [(0, "128Mgarbage"), (0, "0134217728"), (0, "256M"),
                     (0, "18446744073709551616"), (2, "plain"), (3, "+1"),
                     (3, "01"), (3, "32"), (4, "/tmp/bench"), (5, "wrong"),
                     (6, "candidate"), (6, "unknown"), (7, CANDIDATE),
                     (7, ANCHOR[:-1]), (7, ANCHOR.upper()), (8, "pid_kretprobe_zswap_load_v1"),
                     (9, "independent")]
        for index, value in mutations:
            with self.subTest(index=index, value=value):
                args = base.copy()
                args[index] = value
                self.assertFail("args", None, *args)
        self.assertFail("args", None, *base[:-1])
        self.assertFail("args", None, *base, "extra")
        candidate = self.args("candidate")
        candidate[7] = ANCHOR
        self.assertFail("args", None, *candidate)

    def test_cmdline_source_binding(self):
        self.assertPass("cmdline", cmdline())
        self.assertPass("cmdline", cmdline("candidate"), "candidate")
        self.assertPass("source")
        for old, new in (("revision=9", "revision=8"), (ANCHOR, CANDIDATE),
                         ("frontend=legacy", "frontend=independent"),
                         ("backend=compressed", "backend=disk"),
                         ("bytes=134217728", "bytes=1")):
            with self.subTest(old=old):
                self.assertFail("cmdline", cmdline().replace(old, new))
        for key in ("protocol_revision", "contract_id", "source_role", "source_commit", "frontend",
                    "observer", "compression_target_bytes", "backend", "mode", "workload"):
            token = next(x for x in cmdline().split() if x.startswith("bench." + key + "="))
            with self.subTest(key=key):
                self.assertFail("cmdline", " ".join(x for x in cmdline().split() if x != token) + "\n")
                self.assertFail("cmdline", cmdline().rstrip() + " " + token + "\n")

    def test_registration_requires_exact_matched_symbol(self):
        raw = "r64:swap_next_timing/decode_return zswap_load ret=$retval:s64\n"
        self.assertPass("registration", raw)
        self.assertPass("registration", raw.replace("zswap_load", "xswap_load_folio"), "candidate")
        for bad in (raw.replace("r64:", "r32:"), raw.replace("zswap_load", "xswap_load_folio"),
                    raw.replace("zswap_load", "zswap_load+4"), raw.replace(":s64", ":u64"),
                    raw + raw, raw.rstrip() + " extra=1\n", "", raw.rstrip()):
            with self.subTest(raw=bad):
                self.assertFail("registration", bad)

    def test_format_and_options_require_signed_ret_and_supported_printer(self):
        self.assertPass("format", self.format())
        self.assertPass("options", self.options())
        for bad in (self.format().replace("s64 ret", "u64 ret"),
                    self.format().replace("size:8", "size:4"),
                    self.format().replace("offset:24", "offset:16"),
                    self.format().replace("signed:1", "signed:0"),
                    self.format() + "\tfield:s64 ret;\toffset:24;\tsize:8;\tsigned:1;\n",
                    self.format().replace("name: decode_return", "name: other")):
            self.assertFail("format", bad)
        for key in ("context-info", "nolatency-format", "nohex", "nobin", "noraw", "noverbose"):
            with self.subTest(key=key):
                self.assertFail("options", self.options().replace(key + "\n", ""))
                self.assertFail("options", self.options() + key + "\n")
                opposite = key[2:] if key.startswith("no") else "nocontext-info"
                self.assertFail("options", self.options().replace(key, opposite))

    def test_all_probe_readbacks_retain_exact_bytes(self):
        output = self.assertPass("probe")
        for name, path in (("kprobe_events", self.trace / "kprobe_events"),
                           ("current_tracer", self.instance / "current_tracer"),
                           ("buffer_size_kb", self.instance / "buffer_size_kb"),
                           ("event_filter", self.event / "filter"),
                           ("event_enable", self.event / "enable"),
                           ("tracing_on", self.instance / "tracing_on"),
                           ("event_format", self.event / "format"),
                           ("trace_options", self.instance / "trace_options")):
            with self.subTest(name=name):
                begin = f"COMPRESSED_PROBE_READBACK_BEGIN phase=setup name={name} bytes={path.stat().st_size} encoding=hex\n"
                raw = output.split(begin, 1)[1].split(f"COMPRESSED_PROBE_READBACK_END name={name}\n", 1)[0]
                self.assertEqual(bytes.fromhex(raw), path.read_bytes())

    def test_probe_readback_mismatch_and_missing_reject(self):
        self.assertFail("probe", None, "bad_pid")
        for path, text in ((self.instance / "buffer_size_kb", "32\n"),
                           (self.instance / "current_tracer", "function\n"),
                           (self.event / "enable", "0\n"), (self.instance / "tracing_on", "0\n")):
            saved = path.read_text()
            with self.subTest(path=path.name):
                path.write_text(text)
                self.assertFail("probe")
                path.write_text(saved)
        (self.event / "format").unlink()
        self.assertFail("probe")

    def test_smaps_exact_coverage_and_replayed_totals(self):
        output = self.assertPass("smaps", smaps())
        self.assertEqual(output.strip(), f"2 69632 69632 1 {TARGET} 2 1")

    def test_split_unlocked_target_is_complete(self):
        whole = smap(START, START + TARGET, locked=False, nh=True)
        split = smap(START, START + TARGET//2, locked=False, nh=True)
        split += smap(START + TARGET//2, START + TARGET, locked=False, nh=True)
        output = self.assertPass("smaps", smaps().replace(whole, split))
        self.assertIn(f"2 {TARGET} 2 1", output)

    def test_target_and_observer_lock_failures_reject(self):
        whole = smap(START, START + TARGET, locked=False, nh=True)
        variants = [
            smaps().replace(whole, smap(START, START + TARGET, locked=True, nh=True)),
            smaps().replace(whole, smap(START + 4096, START + TARGET, locked=False, nh=True)),
            smaps().replace(whole, smap(START, START + TARGET - 4096, locked=False, nh=True)),
            smaps().replace(whole, smap(START - 4096, START + TARGET, locked=False, nh=True)),
            smaps().replace(whole, smap(START, START + TARGET, locked=False)),
            smaps().replace(whole, smap(START, START + TARGET, locked=False, nh=True, huge=2048)),
            smaps().replace(whole, whole.replace("KernelPageSize:        4", "KernelPageSize:       64")),
            smaps().replace(whole, whole.replace("MMUPageSize:        4", "MMUPageSize:       64")),
            smaps().replace(whole, smap(START, START + TARGET, "rw-s", locked=False, nh=True)),
            smaps().replace(whole, smap(START, START + TARGET, name="[anon:target]", locked=False, nh=True)),
            smaps().replace(whole, whole.replace("00:00 0", "08:01 0")),
            smaps().replace(whole, whole.replace("00:00 0", "00:00 1")),
            smaps().replace(whole, whole.replace("rw-p 00000000", "rw-p 00001000")),
            smaps().replace(whole, whole.replace("Size:   131072", "Size:   131071")),
            smaps().replace("rd ex lo ", "rd ex "),
            smaps().replace("/bin/swapin", "[unknown]").replace("rd ex lo ", "rd ex "),
            smaps().replace("[vvar]", "[unknown]"),
            smaps().replace("rd wr lo ", "rd wr lo lf "),
        ]
        for raw in variants:
            with self.subTest(raw=raw):
                self.assertFail("smaps", raw)

    def test_smaps_duplicate_malformed_and_truncated_records_reject(self):
        raw = smaps()
        for bad in (raw.replace("VmFlags: rd ex lo ", "VmFlags: rd ex lo lo "),
                    raw.replace("VmFlags: rd ex lo \n", "VmFlags: rd ex lo \nVmFlags: rd ex lo \n"),
                    raw.replace("Locked:        4 kB\n", "Locked:        4 kB\nLocked:        4 kB\n"),
                    raw.replace("VmFlags: rd ex lo ", "VmFlags: rd ex ?? "),
                    raw.replace("Locked:        4 kB", "Locked:       +4 kB"),
                    raw.replace("r-xp 00000000", "rw-p 00000000", 1),
                    raw.rstrip(), "garbage\n" + raw, raw.replace("Locked:", "NoLocked:", 1),
                    raw.replace("0000000000100000-0000000000101000", "0000000000101000-0000000000100000")):
            with self.subTest(raw=bad):
                self.assertFail("smaps", bad)

    def test_accessible_shared_mapping_is_not_an_observer_exemption(self):
        ordinary = smap(0x100000, 0x101000, "r-xp", "/bin/swapin")
        shared = smap(0x100000, 0x101000, "r-xs", "/bin/swapin")
        self.assertFail("smaps", smaps().replace(ordinary, shared))

    def test_named_kernel_special_mappings_are_the_only_exemptions(self):
        for name in ("[vvar]", "[vvar_vclock]", "[vdso]", "[vsyscall]"):
            with self.subTest(name=name):
                self.assertPass("smaps", smaps().replace("[vvar]", name))
        for name in ("[vvar-extra]", "[anon:[vvar]]", "[stack]", "[heap]"):
            with self.subTest(name=name):
                self.assertFail("smaps", smaps().replace("[vvar]", name))

    def test_isolation_success_records_real_fixture_readback(self):
        output = self.assertPass("isolate")
        self.assertIn("FIXTURE result=0 lock_calls=1 flags=3 unlock_calls=1 target=2097152 bytes=134217728", output)
        self.assertIn("COMPRESSED_ISOLATION_SETUP mlockall=0 munlock=0 flags=current_future target_bytes=134217728", output)
        begin = (f"COMPRESSED_ISOLATION_BEGIN phase=before_reclaim strategy=mlockall_current_future_target_munlock_v1 "
                 f"target_start={START} target_bytes={TARGET} bytes={len(smaps())} encoding=hex\n")
        payload = output.split(begin, 1)[1].split("COMPRESSED_ISOLATION_END", 1)[0]
        self.assertEqual(bytes.fromhex(payload).decode(), smaps())
        after = self.assertPass("isolation_after")
        self.assertIn("phase=after_measurement", after)

    def test_injected_syscall_failures_do_not_claim_isolation(self):
        lock_output = self.assertFail("isolate", None, "lock_fail")
        self.assertIn("lock_calls=1 flags=3 unlock_calls=0", lock_output)
        self.assertNotIn("COMPRESSED_ISOLATION_SETUP", lock_output)
        unlock_output = self.assertFail("isolate", None, "unlock_fail")
        self.assertIn("unlock_calls=1 target=2097152 bytes=134217728", unlock_output)
        self.assertNotIn("COMPRESSED_ISOLATION_SETUP", unlock_output)

    def test_successful_syscalls_cannot_hide_locked_target_or_unlocked_observer(self):
        original = smaps()
        target = smap(START, START + TARGET, locked=False, nh=True)
        for bad in (original.replace(target, smap(START, START + TARGET, locked=True, nh=True)),
                    original.replace("rd ex lo ", "rd ex ")):
            (self.root / "smaps").write_text(bad)
            output = self.assertFail("isolate")
            self.assertIn("lock_calls=1 flags=3 unlock_calls=1", output)
            self.assertNotIn("COMPRESSED_ISOLATION_BEGIN", output)

    def test_after_snapshot_revalidates_and_bounded_read_rejects(self):
        for bad in (smaps().replace("rd ex lo ", "rd ex "),
                    smaps().rstrip(), smaps() + "\0\n", "x" * 262143 + "\n"):
            (self.root / "smaps").write_text(bad)
            self.assertFail("isolation_after")
        (self.root / "smaps").unlink()
        self.assertFail("isolation_after")

    def test_frontend_grammar_and_generation_are_strict(self):
        self.assertPass("frontend", frontend("stored"))
        raw = frontend("stored")
        for bad in (raw.replace("generation=7", "generation=8", 1),
                    raw.replace("pool=7", "pool=8"), raw.replace("type=1", "type=2"),
                    raw.replace("snapshot=2", "snapshot=0"),
                    raw.replace("state=active", "state=destroyed"),
                    raw.replace("codec=lzo", "codec=lz4"), raw.replace("test=0", "test=1"),
                    raw.replace("driver=lzo-generic", "driver=1bad"), raw.replace("type=1", "type=01"),
                    raw.replace("ram_pages 1048576", "ram_pages +1048576"),
                    raw.replace("ram_pages 1048576", "ram_pages 01048576"),
                    raw.replace("ram_pages 1048576", "ram_pages 18446744073709551616"),
                    raw.replace("raw_live 0\n", ""), raw.replace("raw_live 0", "unknown 0"),
                    raw.replace("raw_live 0", "raw_admitted 0"),
                    raw.replace("ram_pages 1048576\ncap_pages 209715", "cap_pages 209715\nram_pages 1048576"),
                    raw + "trailer\n", raw.rstrip()):
            with self.subTest(raw=bad):
                self.assertFail("frontend", bad)

    def test_frontend_admission_nonbinding_no_raw_and_no_fallback(self):
        self.assertPass("frontend_valid", frontend("stored"))
        mutations = {"raw_live": 1, "raw_admitted": 1, "raw_loads": 1, "cap_updates": 1,
                     "cap_rejects": 1, "bypasses": 1, "incompressible_rejects": 1,
                     "inflight": 1, "store_token_active": 1, "store_token_peak": 2,
                     "retained_folios_live": 1, "backing_live": 1, "backing_allocs": 1,
                     "read_submitted": 1, "write_completed": 1, "decode_errors": 1,
                     "load_misses": 1, "events_lost": 1, "test_windows": 1,
                     "pool_create_ok": 0, "pool_destroy_returned": 1, "cap_pages": 0,
                     "pool_backing_pages": 209715, "ram_pages": 1048575,
                     "entries_live": 32767, "index_live": 0, "handles_live": 0,
                     "stored_bytes": 32768 * 4096, "entry_frees": 1, "handle_frees": 1,
                     "retired": 1, "charge_calls": 1, "charged_bytes": 1,
                     "retained_folio_puts": 1, "allocator_chain_pages": 0,
                     "cap_headroom_pages": 0, "peak_backing_pages": 17999}
        for key, value in mutations.items():
            with self.subTest(key=key):
                self.assertFail("frontend_valid", frontend("stored", **{key: value}))

    def snapshot_run(self, raws):
        paths = []
        for phase, raw in zip(("before", "stored", "after"), raws):
            path = self.root / (phase + ".snapshot")
            path.write_text(raw)
            paths.append(str(path))
        return self.run_case("snapshots", None, *paths)

    def test_snapshot_phases_retain_raw_and_match_normalized_state(self):
        raws = [frontend(phase) for phase in ("before", "stored", "after")]
        result = self.snapshot_run(raws)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for phase, raw in zip(("before", "stored", "after"), raws):
            self.assertIn(f"COMPRESSED_FRONTEND_BEGIN phase={phase}\n{raw}COMPRESSED_FRONTEND_END phase={phase}", result.stdout)
        self.assertIn("COMPRESSED_STATE phase=stored stored_pages=32768 pool_bytes=73728000 incompressible_pages=0", result.stdout)

    def test_snapshot_cross_phase_generation_sequence_and_decoder_proof(self):
        good = [frontend(phase) for phase in ("before", "stored", "after")]
        variants = [
            [good[0], good[1].replace("generation=7", "generation=8").replace("pool=7", "pool=8"), good[2]],
            [good[0], good[1].replace("snapshot=2", "snapshot=1"), good[2]],
            [good[0], good[1].replace("driver=lzo-generic", "driver=other"), good[2]],
            [good[0], good[1], frontend("after", compressed_loads=32767)],
            [frontend("before", entries_live=1, compressed_live=1, handles_live=1,
                      index_live=1, lru_live=1, stored_bytes=100), good[1], good[2]],
        ]
        for raws in variants:
            with self.subTest(raws=raws):
                self.assertNotEqual(self.snapshot_run(raws).returncode, 0)

    def test_legacy_actual_codec_cap_and_nonbinding_limit_readbacks(self):
        output = self.assertPass("legacy")
        self.assertIn("codec=lzo max_pool_percent=20 ram_pages=1048576 cap_pages=209715 shrinker_enabled=0", output)
        for mode in ("limit", "cap", "raw"):
            with self.subTest(mode=mode):
                self.setUp()
                self.assertFail("legacy", None, mode)
        for name, bad in (("compressor", "lz4\n"), ("max_pool_percent", "21\n"),
                          ("shrinker_enabled", "Y\n")):
            self.setUp()
            (self.params / name).write_text(bad)
            self.assertFail("legacy")

    def test_legacy_counters_require_canonical_unsigned_decimal(self):
        for name in ("pool_limit_hit", "written_back_pages", "reject_compress_poor"):
            for value in (0, (1 << 64) - 1):
                with self.subTest(name=name, control=value):
                    self.setUp()
                    raw = f"{value}\n"
                    (self.debug / name).write_text(raw)
                    output = self.assertPass("counter_read", None, name)
                    self.assertEqual(output, f"FIXTURE_COUNTER_READ_OK bytes={len(raw)}\n"
                                             f"FIXTURE_COUNTER_VALUE value={value}\n")
            for raw in ("-1\n", "+0\n", "00\n", "18446744073709551616\n", "0 extra\n"):
                with self.subTest(name=name, raw=raw):
                    self.setUp()
                    (self.debug / name).write_text(raw)
                    result = self.run_case("counter_read", None, name)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(result.stdout, f"FIXTURE_COUNTER_READ_OK bytes={len(raw)}\n")
                    self.assertFail("legacy")

    def test_memory_readback_missing_duplicate_or_noncanonical_rejects(self):
        for raw in ("MemTotal: 4194304 kB\nMemTotal: 4194304 kB\n",
                    "MemTotal: +4194304 kB\n", "MemTotal: 4194303 kB\n", "MemFree: 1 kB\n"):
            (self.root / "meminfo").write_text(raw)
            self.assertFail("legacy")


if __name__ == "__main__":
    unittest.main()
