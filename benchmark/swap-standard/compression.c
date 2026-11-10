// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <sched.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdbool.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <ctype.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <getopt.h>
#include <signal.h>

#ifndef MADV_COLLAPSE
#define MADV_COLLAPSE 25
#endif

#define PAGE_BYTES 4096UL
#define HUGE_BYTES (2UL * 1024 * 1024)
#define DEFAULT_BYTES (32UL * 1024 * 1024)
#define MAX_BYTES (128UL * 1024 * 1024)
#define ZDBG "/sys/kernel/debug/zswap/"
#define ZPARAM "/sys/module/zswap/parameters/"
#define KUNIT_RESULTS "/sys/kernel/debug/kunit/page_compress/results"
#define GUEST_MARKER "/run/swap-next-guest"

enum result { PASS = 0, FAIL = 1, INCOMPLETE = 77 };

struct region {
	uint64_t *data;
	size_t bytes;
	unsigned int generation;
};

struct counters {
	uint64_t stored, pool_bytes, incompressible;
	uint64_t zswpin, zswpout, pswpin, pswpout;
	uint64_t cg_zswap, cg_zswapped;
	bool has_cg;
};

struct residency {
	size_t pages, swapped, nonresident;
	int type;
};

struct context {
	const char *mode, *test, *reclaim, *cgroup, *swap_device, *alternate;
	size_t bytes;
	int type;
	enum result result;
	const char *reason;
	char leaf[PATH_MAX];
	bool leaf_created, in_leaf, leaf_offlined;
	bool codec_touched, cpu_touched, affinity_saved;
	char original_codec[128], cpu_path[PATH_MAX];
	cpu_set_t original_affinity;
	struct region regions[2];
	unsigned char *resident;
	struct counters before;
	bool before_valid;
	uint64_t verified_words;
};

static const char *result_name(enum result r)
{
	return r == PASS ? "PASS" : r == FAIL ? "FAIL" : "INCOMPLETE";
}

static int problem(struct context *c, enum result r, const char *why)
{
	if (c->result == PASS || (r == FAIL && c->result != FAIL)) {
		c->result = r;
		c->reason = why;
	}
	return -1;
}

static void obs(struct context *c, const char *phase, const char *key,
		uint64_t value)
{
	printf("COMPRESS_OBS case=%s phase=%s key=%s value=%" PRIu64 "\n",
	       c->test, phase, key, value);
}

static int read_text(const char *path, char *buf, size_t size)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	ssize_t n;

	if (fd < 0)
		return -1;
	n = read(fd, buf, size - 1);
	int saved = errno;
	close(fd);
	if (n < 0) {
		errno = saved;
		return -1;
	}
	if ((size_t)n == size - 1) {
		errno = EOVERFLOW;
		return -1;
	}
	buf[n] = 0;
	while (n && isspace((unsigned char)buf[n - 1]))
		buf[--n] = 0;
	return 0;
}

static int write_text(const char *path, const char *value)
{
	int fd = open(path, O_WRONLY | O_CLOEXEC);
	ssize_t n;
	size_t len = strlen(value);

	if (fd < 0)
		return -1;
	n = write(fd, value, len);
	int saved = errno;
	close(fd);
	if (n != (ssize_t)len) {
		errno = n < 0 ? saved : EIO;
		return -1;
	}
	return 0;
}

static int read_number(const char *path, uint64_t *value)
{
	char buf[128], *end;
	unsigned long long n;

	if (read_text(path, buf, sizeof(buf)))
		return -1;
	if (!isdigit((unsigned char)buf[0])) {
		errno = EINVAL;
		return -1;
	}
	errno = 0;
	n = strtoull(buf, &end, 10);
	if (errno || *end) {
		errno = EINVAL;
		return -1;
	}
	*value = n;
	return 0;
}

static int stat_number(const char *path, const char *key, uint64_t *value)
{
	FILE *f = fopen(path, "r");
	char line[512], name[128];
	unsigned long long n;
	int found = 0;

	if (!f)
		return -1;
	while (fgets(line, sizeof(line), f)) {
		if (sscanf(line, "%127s %llu", name, &n) == 2 &&
		    !strcmp(name, key)) {
			*value = n;
			found++;
		}
	}
	int bad = ferror(f);
	fclose(f);
	if (bad || found != 1) {
		errno = bad ? EIO : ENOENT;
		return -1;
	}
	return 0;
}

static int cg_number(struct context *c, const char *key, uint64_t *value)
{
	char path[PATH_MAX];

	if (snprintf(path, sizeof(path), "%s/memory.stat", c->leaf) >=
	    (int)sizeof(path))
		return -1;
	return stat_number(path, key, value);
}

static int snapshot(struct context *c, const char *phase, struct counters *s)
{
	memset(s, 0, sizeof(*s));
	if (read_number(ZDBG "stored_pages", &s->stored) ||
	    read_number(ZDBG "pool_total_size", &s->pool_bytes) ||
	    read_number(ZDBG "stored_incompressible_pages", &s->incompressible) ||
	    stat_number("/proc/vmstat", "zswpin", &s->zswpin) ||
	    stat_number("/proc/vmstat", "zswpout", &s->zswpout) ||
	    stat_number("/proc/vmstat", "pswpin", &s->pswpin) ||
	    stat_number("/proc/vmstat", "pswpout", &s->pswpout))
		return problem(c, INCOMPLETE, "compression_observer_missing");
	if (c->leaf_created) {
		if (cg_number(c, "zswap", &s->cg_zswap) ||
		    cg_number(c, "zswapped", &s->cg_zswapped))
			return problem(c, INCOMPLETE, "memcg_observer_missing");
		s->has_cg = true;
	}
	if (!phase)
		return 0;
	obs(c, phase, "stored_pages", s->stored);
	obs(c, phase, "pool_bytes", s->pool_bytes);
	obs(c, phase, "incompressible_pages", s->incompressible);
	obs(c, phase, "zswpin", s->zswpin);
	obs(c, phase, "zswpout", s->zswpout);
	obs(c, phase, "pswpin", s->pswpin);
	obs(c, phase, "pswpout", s->pswpout);
	obs(c, phase, "memcg_present", s->has_cg);
	if (s->has_cg) {
		obs(c, phase, "memcg_zswap_bytes", s->cg_zswap);
		obs(c, phase, "memcg_zswapped_bytes", s->cg_zswapped);
	}
	return 0;
}

static int topology(struct context *c, const char *phase)
{
	FILE *f = fopen("/proc/swaps", "r");
	char line[1024], name[PATH_MAX], kind[64], expected[64];
	unsigned long size, used;
	int prio, devices = 0, virtuals = 0, physical = 0, matched = 0;
	int intended_priority = INT_MIN;

	if (!f)
		return problem(c, INCOMPLETE, "swap_topology_unreadable");
	snprintf(expected, sizeof(expected), "xswap%d", c->type);
	while (fgets(line, sizeof(line), f)) {
		if (sscanf(line, "%4095s %63s %lu %lu %d",
			   name, kind, &size, &used, &prio) != 5)
			continue;
		devices++;
		if (!strncmp(name, "xswap", 5)) {
			virtuals++;
			if (!strcmp(name, expected)) {
				matched++;
				intended_priority = prio;
			}
		} else {
			physical++;
			if (c->swap_device && !strcmp(name, c->swap_device)) {
				matched++;
				intended_priority = prio;
			}
		}
	}
	int bad = ferror(f);
	fclose(f);
	if (bad)
		return problem(c, FAIL, "swap_topology_read_error");
	obs(c, phase, "swap_devices", devices);
	obs(c, phase, "virtual_devices", virtuals);
	obs(c, phase, "physical_devices", physical);
	obs(c, phase, "no_backing", physical == 0);
	obs(c, phase, "intended_device_matches", matched);
	if (!strcmp(c->mode, "xswap")) {
		if (devices != 1 || virtuals != 1 || physical || matched != 1)
			return problem(c, FAIL, "xswap_not_exclusive_no_backing");
		if (intended_priority != 32767)
			return problem(c, FAIL, "xswap_priority_not_restorable");
		obs(c, phase, "xswap_priority", intended_priority);
	} else if (devices != 1 || virtuals || physical != 1 || matched != 1) {
		return problem(c, FAIL, "legacy_backing_topology_mismatch");
	}
	return 0;
}

static int runtime_config(struct context *c)
{
	char enabled[16], shrinker[16], codec[128];

	if (read_text(ZPARAM "enabled", enabled, sizeof(enabled)) ||
	    read_text(ZPARAM "shrinker_enabled", shrinker, sizeof(shrinker)) ||
	    read_text(ZPARAM "compressor", codec, sizeof(codec)))
		return problem(c, INCOMPLETE, "runtime_config_unavailable");
	bool on = !strcmp(enabled, "Y") || !strcmp(enabled, "1");
	bool off = !strcmp(enabled, "N") || !strcmp(enabled, "0");
	bool shrink_on = !strcmp(shrinker, "Y") || !strcmp(shrinker, "1");
	bool shrink_off = !strcmp(shrinker, "N") || !strcmp(shrinker, "0");
	if ((!on && !off) || (!shrink_on && !shrink_off))
		return problem(c, FAIL, "runtime_config_invalid");
	for (size_t i = 0; codec[i]; i++)
		if (!isalnum((unsigned char)codec[i]) && codec[i] != '-' &&
		    codec[i] != '_')
			return problem(c, FAIL, "codec_name_not_a_token");
	obs(c, "configuration", "zswap_enabled", on);
	obs(c, "configuration", "shrinker_enabled", shrink_on);
	printf("COMPRESS_CONFIG case=%s codec=%s\n", c->test, codec);
	if (!on)
		return problem(c, INCOMPLETE, "zswap_disabled_for_c1");
	return 0;
}

static int move_self(const char *dir)
{
	char path[PATH_MAX], pid[32];

	if (snprintf(path, sizeof(path), "%s/cgroup.procs", dir) >=
	    (int)sizeof(path)) {
		errno = ENAMETOOLONG;
		return -1;
	}
	snprintf(pid, sizeof(pid), "%ld\n", (long)getpid());
	return write_text(path, pid);
}

static int fixture_create(struct context *c)
{
	char path[PATH_MAX], current[PATH_MAX], expected[PATH_MAX];
	FILE *f;
	bool match = false;

	f = fopen("/proc/self/cgroup", "r");
	if (!f)
		return problem(c, INCOMPLETE, "current_cgroup_unreadable");
	while (fgets(current, sizeof(current), f)) {
		size_t len = strlen(current);
		while (len && isspace((unsigned char)current[len - 1]))
			current[--len] = 0;
		if (strncmp(current, "0::", 3))
			continue;
		if (snprintf(expected, sizeof(expected), "/sys/fs/cgroup%s",
			     current + 3) >= (int)sizeof(expected))
			continue;
		if (!strcmp(expected, c->cgroup))
			match = true;
	}
	fclose(f);
	if (!match)
		return problem(c, FAIL, "caller_cgroup_mismatch");
	snprintf(c->leaf, sizeof(c->leaf), "/sys/fs/cgroup/swap-next-comp-%ld",
		 (long)getpid());
	if (mkdir(c->leaf, 0755))
		return problem(c, INCOMPLETE, "test_memcg_create_failed");
	c->leaf_created = true;
	if (snprintf(path, sizeof(path), "%s/memory.reclaim", c->leaf) >=
	    (int)sizeof(path) || access(path, W_OK))
		return problem(c, INCOMPLETE, "test_memcg_controller_missing");
	if (move_self(c->leaf))
		return problem(c, INCOMPLETE, "test_memcg_join_failed");
	c->in_leaf = true;
	obs(c, "fixture", "isolated_memcg", 1);
	return 0;
}

static uint64_t word_pattern(size_t page, size_t word, unsigned int generation)
{
	uint64_t stamp = UINT64_C(0xa5c31f7200000001) ^
			 ((uint64_t)generation << 40) ^ (page << 8);

	if (word == 0)
		return stamp;
	if (word == 1)
		return ~stamp;
	return UINT64_C(0x636f6d7072657373) ^
	       ((uint64_t)generation * UINT64_C(0x0101010101010101));
}

static int region_create(struct context *c, int slot, unsigned int generation,
			 bool huge)
{
	struct region *r = &c->regions[slot];
	size_t bytes = c->bytes;

	r->bytes = bytes;
	r->generation = generation;
	if (huge) {
		void *raw = mmap(NULL, bytes + HUGE_BYTES, PROT_READ | PROT_WRITE,
				 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		uintptr_t aligned;
		size_t prefix, suffix;

		if (raw == MAP_FAILED)
			return problem(c, FAIL, "mapping_allocation_failed");
		aligned = ((uintptr_t)raw + HUGE_BYTES - 1) & ~(HUGE_BYTES - 1);
		prefix = aligned - (uintptr_t)raw;
		suffix = bytes + HUGE_BYTES - prefix - bytes;
		if (prefix && munmap(raw, prefix))
			return problem(c, FAIL, "mapping_alignment_failed");
		if (suffix && munmap((void *)(aligned + bytes), suffix))
			return problem(c, FAIL, "mapping_alignment_failed");
		r->data = (uint64_t *)aligned;
		if (madvise(r->data, bytes, MADV_HUGEPAGE))
			return problem(c, INCOMPLETE, "hugepage_advice_unsupported");
	} else {
		r->data = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
			       MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		if (r->data == MAP_FAILED) {
			r->data = NULL;
			return problem(c, FAIL, "mapping_allocation_failed");
		}
		if (madvise(r->data, bytes, MADV_NOHUGEPAGE) && errno != EINVAL)
			return problem(c, FAIL, "basepage_advice_failed");
	}
	for (size_t p = 0; p < bytes / PAGE_BYTES; p++)
		for (size_t w = 0; w < PAGE_BYTES / sizeof(uint64_t); w++)
			r->data[p * (PAGE_BYTES / sizeof(uint64_t)) + w] =
				word_pattern(p, w, generation);
	obs(c, slot ? "mapping_b" : "mapping_a", "nonzero_pages", bytes / PAGE_BYTES);
	return 0;
}

static int inspect_residency(struct context *c, struct region *r,
			     struct residency *s)
{
	int fd = open("/proc/self/pagemap", O_RDONLY | O_CLOEXEC);

	if (fd < 0)
		return problem(c, INCOMPLETE, "pagemap_unavailable");
	memset(s, 0, sizeof(*s));
	s->pages = r->bytes / PAGE_BYTES;
	s->type = -1;
	if (mincore(r->data, r->bytes, c->resident)) {
		close(fd);
		return problem(c, INCOMPLETE, "mincore_unavailable");
	}
	for (size_t page = 0; page < s->pages; page++) {
		uint64_t pte;
		off_t pos = ((uintptr_t)r->data / PAGE_BYTES + page) * sizeof(pte);

		if (pread(fd, &pte, sizeof(pte), pos) != sizeof(pte)) {
			close(fd);
			return problem(c, FAIL, "pagemap_short_read");
		}
		if (!(pte & (UINT64_C(1) << 62)) ||
		    (pte & (UINT64_C(1) << 63)))
			continue;
		int type = pte & 31;
		if (s->type == -1)
			s->type = type;
		if (type != s->type || (c->type >= 0 && type != c->type)) {
			close(fd);
			return problem(c, FAIL, "unexpected_swap_type");
		}
		s->swapped++;
		if (!(c->resident[page] & 1))
			s->nonresident++;
	}
	close(fd);
	return 0;
}

static void emit_residency(struct context *c, const char *phase,
			   const struct residency *s)
{
	obs(c, phase, "target_pages", s->pages);
	obs(c, phase, "swapped_pages", s->swapped);
	obs(c, phase, "absent_swapcache_pages", s->nonresident);
	if (s->type >= 0)
		obs(c, phase, "target_type", s->type);
}

static int reclaim_once(struct context *c, struct region *r)
{
	char path[PATH_MAX], amount[64];

	if (madvise(r->data, r->bytes, MADV_PAGEOUT))
		return problem(c, INCOMPLETE, "pageout_unavailable");
	if (snprintf(path, sizeof(path), "%s/memory.reclaim", c->leaf) >=
	    (int)sizeof(path))
		return problem(c, FAIL, "reclaim_path_too_long");
	snprintf(amount, sizeof(amount), "%zu\n", r->bytes);
	if (write_text(path, amount) && errno != EAGAIN)
		return problem(c, FAIL, "explicit_reclaim_failed");
	return 0;
}

static int store_region(struct context *c, int slot, const char *phase)
{
	struct region *r = &c->regions[slot];
	struct residency s;
	size_t minimum = r->bytes / PAGE_BYTES * 9 / 10;

	for (int attempt = 0; attempt < 40; attempt++) {
		if (reclaim_once(c, r))
			return -1;
		usleep(100000);
		if (inspect_residency(c, r, &s))
			return -1;
		if (s.nonresident >= minimum) {
			emit_residency(c, phase, &s);
			return 0;
		}
	}
	emit_residency(c, phase, &s);
	return problem(c, INCOMPLETE, "target_compressed_residency_unobserved");
}

static int verify_region(struct context *c, struct region *r)
{
	volatile uint64_t *p = r->data;

	for (size_t page = 0; page < r->bytes / PAGE_BYTES; page++)
		for (size_t word = 0; word < PAGE_BYTES / sizeof(uint64_t); word++)
			if (p[page * (PAGE_BYTES / sizeof(uint64_t)) + word] !=
			    word_pattern(page, word, r->generation))
				return problem(c, FAIL, "data_mismatch");
	c->verified_words += r->bytes / sizeof(uint64_t);
	return 0;
}

static int stored_evidence(struct context *c, const char *phase)
{
	struct counters s;
	bool observed = false;

	/* memcg rstat is buffered. Wait for an observed state, never infer it. */
	for (int retry = 0; retry < 40; retry++) {
		if (snapshot(c, NULL, &s))
			return -1;
		if (s.incompressible != c->before.incompressible)
			return problem(c, FAIL, "raw_storage_instead_of_compression");
		if (s.pswpout != c->before.pswpout)
			return problem(c, FAIL, "unexpected_physical_write");
		if (s.stored > c->before.stored && s.zswpout > c->before.zswpout &&
		    s.cg_zswap && s.cg_zswapped) {
			observed = true;
			break;
		}
		usleep(100000);
	}
	if (snapshot(c, phase, &s))
		return -1;
	if (s.incompressible != c->before.incompressible)
		return problem(c, FAIL, "raw_storage_instead_of_compression");
	if (s.pswpout != c->before.pswpout)
		return problem(c, FAIL, "unexpected_physical_write");
	if (!observed || s.stored <= c->before.stored ||
	    s.zswpout <= c->before.zswpout || !s.cg_zswap || !s.cg_zswapped)
		return problem(c, INCOMPLETE, "compressed_store_or_charge_unobserved");
	return 0;
}

static int decoded_evidence(struct context *c)
{
	struct counters s;
	bool observed = false;

	/* These are aggregate phase observations, not per-page decode events. */
	for (int retry = 0; retry < 40; retry++) {
		if (snapshot(c, NULL, &s))
			return -1;
		if (s.pswpout != c->before.pswpout || s.pswpin != c->before.pswpin)
			return problem(c, FAIL, "unexpected_physical_io");
		if (s.zswpin > c->before.zswpin) {
			observed = true;
			break;
		}
		usleep(100000);
	}
	if (snapshot(c, "decoded", &s))
		return -1;
	obs(c, "decoded", "verified_words", c->verified_words);
	if (s.pswpout != c->before.pswpout || s.pswpin != c->before.pswpin)
		return problem(c, FAIL, "unexpected_physical_io");
	if (!observed || s.zswpin <= c->before.zswpin)
		return problem(c, INCOMPLETE, "decoder_traffic_unobserved");
	return 0;
}

static int case_roundtrip(struct context *c)
{
	if (region_create(c, 0, 1, false) || store_region(c, 0, "stored_a") ||
	    stored_evidence(c, "stored") || verify_region(c, &c->regions[0]))
		return -1;
	return decoded_evidence(c);
}

static int codec_read(struct context *c)
{
	if (read_text(ZPARAM "compressor", c->original_codec,
		      sizeof(c->original_codec)))
		return problem(c, INCOMPLETE, "codec_control_missing");
	return 0;
}

static int case_codec_switch(struct context *c)
{
	const char *alternate = c->alternate;
	char after[128];
	struct residency old;

	if (codec_read(c) || region_create(c, 0, 2, false) ||
	    store_region(c, 0, "stored_old") || stored_evidence(c, "old_pool"))
		return -1;
	if (!alternate)
		alternate = !strcmp(c->original_codec, "lz4") ? "lzo" : "lz4";
	if (!strcmp(alternate, c->original_codec))
		return problem(c, INCOMPLETE, "alternate_codec_not_distinct");
	c->codec_touched = true;
	if (write_text(ZPARAM "compressor", alternate))
		return problem(c, INCOMPLETE, "alternate_codec_unavailable");
	if (read_text(ZPARAM "compressor", after, sizeof(after)) ||
	    strcmp(after, alternate))
		return problem(c, FAIL, "codec_change_readback_failed");
	obs(c, "case", "codec_switched", 1);
	if (region_create(c, 1, 3, false) || store_region(c, 1, "stored_new") ||
	    inspect_residency(c, &c->regions[0], &old))
		return -1;
	emit_residency(c, "old_after_switch", &old);
	if (old.nonresident < old.pages * 9 / 10)
		return problem(c, INCOMPLETE, "old_objects_not_retained");
	if (stored_evidence(c, "stored") ||
	    verify_region(c, &c->regions[0]) || verify_region(c, &c->regions[1]))
		return -1;
	obs(c, "case", "old_and_new_data_verified", 1);
	return decoded_evidence(c);
}

static int case_invalid_codec(struct context *c)
{
	char after[128];
	int saved;

	if (codec_read(c))
		return -1;
	c->codec_touched = true;
	errno = 0;
	if (!write_text(ZPARAM "compressor", "swap_next_invalid_codec_7d83"))
		return problem(c, FAIL, "invalid_codec_accepted");
	saved = errno;
	obs(c, "case", "invalid_codec_errno", saved);
	if (saved != EINVAL && saved != ENOENT)
		return problem(c, INCOMPLETE, "invalid_codec_rejection_not_semantic");
	if (read_text(ZPARAM "compressor", after, sizeof(after)) ||
	    strcmp(after, c->original_codec))
		return problem(c, FAIL, "invalid_codec_changed_configuration");
	obs(c, "case", "codec_unchanged", 1);
	return case_roundtrip(c);
}

static int case_concurrent_fault(struct context *c)
{
	int gate[2], spawned = 0, status, failed = 0;
	pid_t kids[8] = {0};
	struct region targets;
	struct residency target_state;

	if (region_create(c, 0, 4, false) || store_region(c, 0, "stored_a") ||
	    stored_evidence(c, "stored"))
		return -1;
	targets = c->regions[0];
	targets.bytes = 32 * PAGE_BYTES;
	if (inspect_residency(c, &targets, &target_state))
		return -1;
	obs(c, "case", "concurrent_target_pages", target_state.pages);
	obs(c, "case", "concurrent_absent_swapcache_pages", target_state.nonresident);
	if (target_state.nonresident != target_state.pages)
		return problem(c, INCOMPLETE, "concurrent_targets_not_compressed");
	if (pipe(gate))
		return problem(c, FAIL, "worker_pipe_failed");
	for (int worker = 0; worker < 8; worker++) {
		pid_t pid = fork();
		if (pid < 0) {
			failed = 1;
			break;
		}
		if (!pid) {
			char token;
			close(gate[1]);
			if (read(gate[0], &token, 1) != 1)
				_exit(2);
			for (size_t page = 0; page < 32; page++)
				for (size_t word = 0; word < PAGE_BYTES / 8; word++)
					if (c->regions[0].data[page * (PAGE_BYTES / 8) + word] !=
					    word_pattern(page, word, 4))
						_exit(3);
			size_t off = (size_t)worker * (PAGE_BYTES / 8);
			c->regions[0].data[off] ^= UINT64_C(0x1234);
			if (c->regions[0].data[off] !=
			    (word_pattern(worker, 0, 4) ^ UINT64_C(0x1234)))
				_exit(4);
			_exit(0);
		}
		kids[spawned++] = pid;
	}
	close(gate[0]);
	for (int i = 0; i < spawned; i++) {
		if (write(gate[1], "x", 1) != 1)
			failed = 1;
	}
	close(gate[1]);
	for (int i = 0; i < spawned; i++) {
		if (waitpid(kids[i], &status, 0) != kids[i] ||
		    !WIFEXITED(status) || WEXITSTATUS(status))
			failed = 1;
	}
	obs(c, "case", "workers", spawned);
	if (failed || spawned != 8)
		return problem(c, FAIL, "concurrent_worker_failed");
	if (verify_region(c, &c->regions[0]))
		return -1;
	obs(c, "case", "cow_parent_verified", 1);
	return decoded_evidence(c);
}

static int case_memcg_offline(struct context *c)
{
	struct counters s;

	if (region_create(c, 0, 5, false) || store_region(c, 0, "stored_a") ||
	    stored_evidence(c, "stored") || snapshot(c, NULL, &s))
		return -1;
	obs(c, "case", "offline_live_compressed_bytes", s.cg_zswap);
	if (move_self(c->cgroup))
		return problem(c, FAIL, "memcg_leave_failed");
	c->in_leaf = false;
	if (rmdir(c->leaf))
		return problem(c, FAIL, "live_memcg_offline_failed");
	c->leaf_created = false;
	c->leaf_offlined = true;
	obs(c, "case", "live_memcg_removed", 1);
	if (verify_region(c, &c->regions[0]))
		return -1;
	return decoded_evidence(c);
}

static int case_memcg_limits(struct context *c)
{
	char path[PATH_MAX];
	struct counters s;
	struct residency residency;

	if (snprintf(path, sizeof(path), "%s/memory.zswap.max", c->leaf) >=
	    (int)sizeof(path))
		return problem(c, FAIL, "quota_path_too_long");
	if (write_text(path, "0\n"))
		return problem(c, INCOMPLETE, "zswap_quota_control_missing");
	uint64_t quota;
	if (read_number(path, &quota) || quota)
		return problem(c, FAIL, "zero_quota_readback_failed");
	obs(c, "case", "zswap_quota_bytes", quota);
	if (region_create(c, 0, 6, false))
		return -1;
	for (int i = 0; i < 4; i++) {
		if (reclaim_once(c, &c->regions[0]))
			return -1;
		usleep(100000);
		if (snapshot(c, NULL, &s))
			return -1;
		if (s.cg_zswap || s.cg_zswapped ||
		    s.zswpout != c->before.zswpout || s.stored != c->before.stored)
			return problem(c, FAIL, "zero_quota_admission_violation");
	}
	obs(c, "case", "quota_pageout_attempts", 4);
	if (inspect_residency(c, &c->regions[0], &residency))
		return -1;
	emit_residency(c, "quota", &residency);
	if (snapshot(c, "quota", &s))
		return -1;
	if (s.cg_zswap || s.cg_zswapped ||
	    s.zswpout != c->before.zswpout || s.stored != c->before.stored)
		return problem(c, FAIL, "zero_quota_admission_violation");
	if (!strcmp(c->mode, "xswap") &&
	    (s.pswpout != c->before.pswpout || residency.swapped))
		return problem(c, FAIL, "zero_quota_no_backing_violation");
	if (verify_region(c, &c->regions[0]))
		return -1;
	obs(c, "decoded", "verified_words", c->verified_words);
	obs(c, "case", "quota_data_verified", 1);
	return snapshot(c, "decoded", &s);
}

static int case_live_destroy(struct context *c)
{
	char value[32], path[PATH_MAX];
	struct residency r;
	int fd[2], status;
	pid_t child;

	if (strcmp(c->mode, "xswap"))
		return problem(c, INCOMPLETE, "live_destroy_requires_xswap");
	if (region_create(c, 0, 7, false) || store_region(c, 0, "stored_a") ||
	    stored_evidence(c, "stored") ||
	    inspect_residency(c, &c->regions[0], &r))
		return -1;
	obs(c, "case", "destroy_live_swapped_pages", r.swapped);
	if (pipe(fd))
		return problem(c, FAIL, "destroy_worker_pipe_failed");
	child = fork();
	if (child < 0) {
		close(fd[0]);
		close(fd[1]);
		return problem(c, FAIL, "destroy_worker_fork_failed");
	}
	if (!child) {
		char token;
		close(fd[1]);
		if (read(fd[0], &token, 1) != 1)
			_exit(2);
		for (size_t page = 0; page < c->bytes / PAGE_BYTES; page++)
			if (c->regions[0].data[page * (PAGE_BYTES / 8)] !=
			    word_pattern(page, 0, 7))
				_exit(3);
		_exit(0);
	}
	close(fd[0]);
	int release_ok = write(fd[1], "x", 1) == 1;
	close(fd[1]);
	snprintf(value, sizeof(value), "%d\n", c->type);
	int destroy_ok = !write_text("/sys/kernel/mm/xswap/destroy", value);
	int child_ok = waitpid(child, &status, 0) == child &&
		       WIFEXITED(status) && !WEXITSTATUS(status);
	if (!release_ok || !destroy_ok || !child_ok)
		return problem(c, FAIL, "live_destroy_or_reader_failed");
	snprintf(path, sizeof(path), "/sys/kernel/debug/xswap/type%d", c->type);
	if (!access(path, F_OK))
		return problem(c, FAIL, "destroyed_device_still_present");
	obs(c, "case", "destroy_observed", 1);
	if (verify_region(c, &c->regions[0]))
		return -1;
	obs(c, "case", "concurrent_destroy_reader_verified", 1);
	if (write_text("/sys/kernel/mm/xswap/create", "32767\n") ||
	    access(path, F_OK))
		return problem(c, FAIL, "destroyed_device_restore_failed");
	obs(c, "case", "original_type_recreated", 1);
	return decoded_evidence(c);
}

static int case_guest_hotplug(struct context *c)
{
	cpu_set_t selected;
	char online[16];
	int target = -1, keeper = -1;

	if (sched_getaffinity(0, sizeof(c->original_affinity), &c->original_affinity))
		return problem(c, INCOMPLETE, "cpu_affinity_unavailable");
	c->affinity_saved = true;
	for (int cpu = 0; cpu < CPU_SETSIZE; cpu++) {
		if (!CPU_ISSET(cpu, &c->original_affinity))
			continue;
		if (keeper == -1)
			keeper = cpu;
		if (!cpu)
			continue;
		snprintf(c->cpu_path, sizeof(c->cpu_path),
			 "/sys/devices/system/cpu/cpu%d/online", cpu);
		if (!read_text(c->cpu_path, online, sizeof(online)) &&
		    !strcmp(online, "1") && !access(c->cpu_path, W_OK)) {
			target = cpu;
			break;
		}
	}
	if (target < 0 || keeper < 0 || target == keeper)
		return problem(c, INCOMPLETE, "guest_hotplug_cpu_unavailable");
	CPU_ZERO(&selected);
	CPU_SET(target, &selected);
	if (sched_setaffinity(0, sizeof(selected), &selected) || sched_getcpu() != target)
		return problem(c, FAIL, "target_cpu_binding_failed");
	obs(c, "case", "target_cpu", target);
	if (region_create(c, 0, 8, false) || store_region(c, 0, "stored_old"))
		return -1;
	CPU_ZERO(&selected);
	CPU_SET(keeper, &selected);
	if (sched_setaffinity(0, sizeof(selected), &selected))
		return problem(c, FAIL, "keeper_cpu_binding_failed");
	c->cpu_touched = true;
	if (write_text(c->cpu_path, "0\n"))
		return problem(c, INCOMPLETE, "guest_cpu_offline_rejected");
	if (read_text(c->cpu_path, online, sizeof(online)) || strcmp(online, "0"))
		return problem(c, FAIL, "guest_cpu_offline_not_observed");
	obs(c, "case", "cpu_offline_observed", 1);
	if (write_text(c->cpu_path, "1\n") ||
	    read_text(c->cpu_path, online, sizeof(online)) || strcmp(online, "1"))
		return problem(c, FAIL, "guest_cpu_online_failed");
	obs(c, "case", "cpu_online_observed", 1);
	CPU_ZERO(&selected);
	CPU_SET(target, &selected);
	if (sched_setaffinity(0, sizeof(selected), &selected) || sched_getcpu() != target)
		return problem(c, FAIL, "reonline_cpu_binding_failed");
	if (region_create(c, 1, 9, false) || store_region(c, 1, "stored_new") ||
	    stored_evidence(c, "stored") ||
	    verify_region(c, &c->regions[0]) || verify_region(c, &c->regions[1]))
		return -1;
	return decoded_evidence(c);
}

static int huge_bytes(struct region *r, uint64_t *bytes)
{
	FILE *f = fopen("/proc/self/smaps", "r");
	char line[512];
	unsigned long start, end, kb;
	bool selected = false, found = false;

	*bytes = 0;
	if (!f)
		return -1;
	while (fgets(line, sizeof(line), f)) {
		if (sscanf(line, "%lx-%lx", &start, &end) == 2) {
			selected = start == (uintptr_t)r->data &&
				   end == (uintptr_t)r->data + r->bytes;
			continue;
		}
		if (selected && sscanf(line, "AnonHugePages: %lu kB", &kb) == 1) {
			*bytes = kb * 1024UL;
			found = true;
		}
	}
	fclose(f);
	return found ? 0 : -1;
}

static int case_large_folio(struct context *c)
{
	const char *counter = "/sys/kernel/mm/transparent_hugepage/"
			      "hugepages-2048kB/stats/zswpout";
	uint64_t huge, before, after;

	if (region_create(c, 0, 10, true))
		return -1;
	if (madvise(c->regions[0].data, c->bytes, MADV_COLLAPSE))
		return problem(c, INCOMPLETE, "large_folio_collapse_unavailable");
	if (huge_bytes(&c->regions[0], &huge) || huge != c->bytes)
		return problem(c, INCOMPLETE, "actual_large_folio_input_unobserved");
	obs(c, "case", "huge_input_bytes", huge);
	if (read_number(counter, &before))
		return problem(c, INCOMPLETE, "order_specific_store_observer_missing");
	obs(c, "case", "large_zswpout_before", before);
	if (store_region(c, 0, "stored_a") || stored_evidence(c, "stored"))
		return -1;
	if (read_number(counter, &after))
		return problem(c, INCOMPLETE, "order_specific_store_observer_missing");
	obs(c, "case", "large_zswpout_after", after);
	if (verify_region(c, &c->regions[0]) || decoded_evidence(c))
		return -1;
	if (after <= before)
		return problem(c, INCOMPLETE, "large_folio_split_before_store");
	return 0;
}

/*
 * This observer authenticates the result shape, not the implementation of a
 * KUnit test. The trusted manifest must bind reviewed test source and this raw
 * KTAP to the exact boot/config. The three names are a frozen C1 contract.
 */
static const char *unit_names[] = {
	"page_compress_alloc_rollback",
	"page_compress_partial_cleanup",
	"page_compress_numa_placement",
};

struct unit_result {
	unsigned int observed, failed, skipped;
	bool names[3];
	const char *reason;
};

static int parse_unit(char *raw, struct unit_result *u)
{
	char *save = NULL, *line;
	enum {
		OUTER_VERSION, OUTER_PLAN, INNER_VERSION, SUITE_NAME, INNER_PLAN,
		TEST_RESULTS, FINISHED
	} state = OUTER_VERSION;

	memset(u, 0, sizeof(*u));
	u->reason = "ktap_envelope_invalid";
	for (line = strtok_r(raw, "\n", &save); line;
	     line = strtok_r(NULL, "\n", &save)) {
		while (isspace((unsigned char)*line))
			line++;
		if (!*line)
			continue;
		if (strcasestr(line, "# skip") || strcasestr(line, "# todo")) {
			u->skipped++;
			u->reason = "ktap_skipped_or_todo";
			return -1;
		}
		if (state == OUTER_VERSION || state == INNER_VERSION) {
			if (strcmp(line, "KTAP version 1"))
				return -1;
			state++;
			continue;
		}
		if (state == OUTER_PLAN) {
			if (strcmp(line, "1..1"))
				return -1;
			state++;
			continue;
		}
		if (state == SUITE_NAME) {
			if (strcmp(line, "# Subtest: page_compress"))
				return -1;
			state++;
			continue;
		}
		if (state == INNER_PLAN) {
			if (strcmp(line, "1..3"))
				return -1;
			state++;
			continue;
		}
		if (state == FINISHED)
			return -1;
		if (*line == '#')
			continue;
		if (!strncmp(line, "not ok ", 7)) {
			u->failed++;
			u->reason = "ktap_failed_test";
			return -1;
		}
		if (strncmp(line, "ok ", 3))
			return -1;
		unsigned int number;
		char name[128], extra[128], trailing[2];
		int n = sscanf(line, "ok %u %127s %127s %1s",
			       &number, name, extra, trailing);
		if (n < 2)
			return -1;
		if (!strcmp(name, "-")) {
			if (n != 3)
				return -1;
			strcpy(name, extra);
		} else if (n != 2) {
			return -1;
		}
		if (!strcmp(name, "page_compress")) {
			if (number != 1 || u->observed != 3)
				return -1;
			state = FINISHED;
			continue;
		}
		if (u->observed >= 3 || number != u->observed + 1 ||
		    strcmp(name, unit_names[u->observed])) {
			u->reason = "ktap_unknown_duplicate_or_reordered_test";
			return -1;
		}
		u->names[u->observed] = true;
		u->observed++;
	}
	if (state != FINISHED || u->observed != 3)
		return -1;
	u->reason = "ok";
	return 0;
}

static int case_library_unit(struct context *c)
{
	FILE *f = fopen(KUNIT_RESULTS, "r");
	char *raw = NULL, *copy = NULL;
	struct unit_result u;
	const size_t limit = 256 * 1024;
	size_t n;
	int ret = -1;

	if (!f)
		return problem(c, INCOMPLETE, "kunit_suite_results_missing");
	raw = malloc(limit + 1);
	if (!raw) {
		fclose(f);
		return problem(c, FAIL, "ktap_buffer_allocation_failed");
	}
	n = fread(raw, 1, limit, f);
	int bad = ferror(f), more = fgetc(f);
	fclose(f);
	if (bad || more != EOF) {
		problem(c, FAIL, "ktap_read_error_or_oversize");
		goto out;
	}
	raw[n] = 0;
	if (memchr(raw, 0, n)) {
		problem(c, FAIL, "ktap_embedded_nul");
		goto out;
	}
	puts("COMPRESS_KTAP_BEGIN suite=page_compress");
	fwrite(raw, 1, n, stdout);
	if (n && raw[n - 1] != '\n')
		putchar('\n');
	puts("COMPRESS_KTAP_END suite=page_compress");
	copy = strdup(raw);
	if (!copy) {
		problem(c, FAIL, "ktap_buffer_allocation_failed");
		goto out;
	}
	int parsed = parse_unit(copy, &u);
	obs(c, "case", "kunit_expected", 3);
	obs(c, "case", "kunit_observed", u.observed);
	obs(c, "case", "kunit_failed", u.failed);
	obs(c, "case", "kunit_skipped", u.skipped);
	for (size_t i = 0; i < 3; i++)
		obs(c, "case", unit_names[i], u.names[i]);
	if (parsed)
		problem(c, FAIL, u.reason);
	else
		ret = 0;
out:
	free(copy);
	free(raw);
	return ret;
}

static int cleanup(struct context *c)
{
	char value[128];
	bool reset = true;

	if (c->cpu_touched) {
		if (write_text(c->cpu_path, "1\n") ||
		    read_text(c->cpu_path, value, sizeof(value)) || strcmp(value, "1"))
			reset = false;
		else
			obs(c, "reset", "cpu_restored", 1);
	}
	if (c->affinity_saved &&
	    sched_setaffinity(0, sizeof(c->original_affinity), &c->original_affinity))
		reset = false;
	for (size_t i = 0; i < 2; i++) {
		if (c->regions[i].data) {
			if (munmap(c->regions[i].data, c->regions[i].bytes))
				reset = false;
			c->regions[i].data = NULL;
		}
	}
	if (c->codec_touched) {
		if (write_text(ZPARAM "compressor", c->original_codec) ||
		    read_text(ZPARAM "compressor", value, sizeof(value)) ||
		    strcmp(value, c->original_codec))
			reset = false;
		else
			obs(c, "reset", "codec_restored", 1);
	}
	if (c->before_valid) {
		struct counters s;
		bool drained = false;
		for (int retry = 0; retry < 40; retry++) {
			if (snapshot(c, NULL, &s))
				break;
			if (s.stored == c->before.stored &&
			    s.pool_bytes <= c->before.pool_bytes &&
			    (!s.has_cg || (!s.cg_zswap && !s.cg_zswapped))) {
				drained = true;
				break;
			}
			usleep(100000);
		}
		if (snapshot(c, "cleanup", &s) || !drained)
			reset = false;
		obs(c, "reset", "objects_and_charges_drained", drained);
	}
	if (c->in_leaf) {
		if (move_self(c->cgroup))
			reset = false;
		else
			c->in_leaf = false;
	}
	if (c->leaf_created) {
		if (rmdir(c->leaf))
			reset = false;
		else
			c->leaf_created = false;
	}
	if (!c->leaf_created)
		obs(c, "reset", "temporary_memcg_removed", 1);
	if (topology(c, "reset"))
		reset = false;
	if (!reset)
		problem(c, FAIL, "case_reset_failed");
	printf("COMPRESS_RESET case=%s status=%s\n",
	       c->test, reset ? "PASS" : "FAIL");
	return reset ? 0 : -1;
}

static bool guest_marker_present(void)
{
	static const char expected[] = "swap-next-guest-v1\n";
	char marker[sizeof(expected) + 1];
	int fd = open(GUEST_MARKER, O_RDONLY | O_CLOEXEC);
	ssize_t n;

	if (fd < 0)
		return false;
	n = read(fd, marker, sizeof(marker));
	close(fd);
	return n == (ssize_t)sizeof(expected) - 1 &&
	       !memcmp(marker, expected, sizeof(expected) - 1);
}

static bool known_case(const char *name)
{
	const char *cases[] = {
		"roundtrip", "codec_switch", "invalid_codec", "concurrent_fault",
		"live_destroy", "memcg_balance", "memcg_offline", "memcg_limits",
		"guest_hotplug", "large_folio", "allocation_failure",
		"numa_locality", "partial_failure", "init_failure", "library_unit",
	};

	for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
		if (!strcmp(name, cases[i]))
			return true;
	return false;
}

static void usage(FILE *out)
{
	fputs("compression --mode xswap|plain --case ID --cgroup PATH "
	      "--reclaim PATH --type N [--bytes N] [--swap-device PATH] "
	      "[--alternate-codec NAME]\n"
	      "Guest only: requires /run/swap-next-guest marker. One case per run.\n"
	      "Cases: roundtrip codec_switch invalid_codec concurrent_fault "
	      "live_destroy memcg_balance memcg_offline memcg_limits "
	      "guest_hotplug large_folio library_unit\n"
	      "Explicitly incomplete observers: allocation_failure numa_locality "
	      "partial_failure init_failure\n"
	      "Exit 0=observed PASS, 1=FAIL, 77=INCOMPLETE, 64=bad arguments.\n"
	      "--selftest only exercises pure pattern/KTAP logic; it is not guest proof.\n",
	      out);
}

static int selftest(void)
{
	for (unsigned int generation = 1; generation <= 10; generation++)
		for (size_t page = 0; page < MAX_BYTES / PAGE_BYTES; page++)
			for (size_t word = 0; word < 3; word++)
				if (!word_pattern(page, word, generation))
					return 1;
	const char *valid =
		"KTAP version 1\n1..1\n"
		"    KTAP version 1\n    # Subtest: page_compress\n    1..3\n"
		"    ok 1 page_compress_alloc_rollback\n"
		"    ok 2 page_compress_partial_cleanup\n"
		"    ok 3 page_compress_numa_placement\n"
		"ok 1 page_compress\n";
	char *copy = strdup(valid);
	struct unit_result u;
	if (!copy || parse_unit(copy, &u)) {
		free(copy);
		return 1;
	}
	free(copy);
	const char *invalid[] = {
		"KTAP version 1\n# Subtest: page_compress\n1..3\nok 1 page_compress\n",
		"KTAP version 1\n# Subtest: page_compress\n1..3\nnot ok 1 page_compress_alloc_rollback\n",
		"KTAP version 1\n# Subtest: page_compress\n1..3\nok 1 page_compress_alloc_rollback # SKIP missing\n",
		"KTAP version 1\n# Subtest: page_compress\n1..3\nok 1 unrelated_test\n",
		"KTAP version 1\n# Subtest: page_compress\n1..3\nok 1 page_compress_alloc_rollback\nok 1 page_compress_alloc_rollback\n",
	};
	for (size_t i = 0; i < sizeof(invalid) / sizeof(invalid[0]); i++) {
		copy = strdup(invalid[i]);
		if (!copy)
			return 1;
		int ret = parse_unit(copy, &u);
		free(copy);
		if (!ret)
			return 1;
	}
	puts("COMPRESS_SELFTEST_PASS pattern_nonzero=1 ktap_negative_fixtures=5");
	return 0;
}

int main(int argc, char **argv)
{
	struct context c = { .bytes = DEFAULT_BYTES, .type = -1,
			     .result = PASS, .reason = "ok" };
	const struct option options[] = {
		{ "mode", required_argument, NULL, 'm' },
		{ "case", required_argument, NULL, 'c' },
		{ "bytes", required_argument, NULL, 'b' },
		{ "reclaim", required_argument, NULL, 'r' },
		{ "cgroup", required_argument, NULL, 'g' },
		{ "type", required_argument, NULL, 't' },
		{ "swap-device", required_argument, NULL, 'd' },
		{ "alternate-codec", required_argument, NULL, 'a' },
		{ "selftest", no_argument, NULL, 's' },
		{ "help", no_argument, NULL, 'h' },
		{ NULL, 0, NULL, 0 },
	};
	bool run_selftest = false;
	int ch;

	setvbuf(stdout, NULL, _IONBF, 0);
	while ((ch = getopt_long(argc, argv, "", options, NULL)) != -1) {
		char *end;
		unsigned long long n;
		switch (ch) {
		case 'm': c.mode = optarg; break;
		case 'c': c.test = optarg; break;
		case 'r': c.reclaim = optarg; break;
		case 'g': c.cgroup = optarg; break;
		case 'd': c.swap_device = optarg; break;
		case 'a': c.alternate = optarg; break;
		case 'b':
			errno = 0;
			n = strtoull(optarg, &end, 10);
			if (errno || !*optarg || *end || n < HUGE_BYTES ||
			    n > MAX_BYTES || n % HUGE_BYTES)
				return 64;
			c.bytes = n;
			break;
		case 't':
			errno = 0;
			n = strtoull(optarg, &end, 10);
			if (errno || !*optarg || *end || n > 31)
				return 64;
			c.type = n;
			break;
		case 's': run_selftest = true; break;
		case 'h': usage(stdout); return 0;
		default: usage(stderr); return 64;
		}
	}
	if (optind != argc)
		return 64;
	if (run_selftest)
		return selftest();
	if (!c.mode || !c.test || !c.cgroup || !c.reclaim ||
	    (strcmp(c.mode, "xswap") && strcmp(c.mode, "plain")) ||
	    !known_case(c.test) ||
	    (strcmp(c.mode, "plain") && c.type < 0) ||
	    (!strcmp(c.mode, "plain") && !c.swap_device) ||
	    strncmp(c.cgroup, "/sys/fs/cgroup/", 15) ||
	    strstr(c.cgroup, ".."))
		return 64;
	char expected_reclaim[PATH_MAX];
	snprintf(expected_reclaim, sizeof(expected_reclaim), "%s/memory.reclaim", c.cgroup);
	if (strcmp(expected_reclaim, c.reclaim))
		return 64;
	printf("COMPRESS_BEGIN schema=1 mode=%s case=%s bytes=%zu\n",
	       c.mode, c.test, c.bytes);
	if (!guest_marker_present()) {
		problem(&c, INCOMPLETE, "guest_marker_missing");
		goto untouched;
	}
	if (geteuid() || sysconf(_SC_PAGESIZE) != PAGE_BYTES) {
		problem(&c, INCOMPLETE, "root_or_page_size_unsupported");
		goto untouched;
	}
	if (topology(&c, "before"))
		goto untouched;
	signal(SIGPIPE, SIG_IGN);
	if (!strcmp(c.test, "allocation_failure") ||
	    !strcmp(c.test, "partial_failure") ||
	    !strcmp(c.test, "init_failure") ||
	    !strcmp(c.test, "numa_locality")) {
		obs(&c, "case", "targeted_observer_available", 0);
		problem(&c, INCOMPLETE, "targeted_library_observer_required");
		goto untouched;
	}
	if (!strcmp(c.test, "library_unit")) {
		case_library_unit(&c);
		goto untouched;
	}
	if (runtime_config(&c))
		goto untouched;
	c.resident = calloc(c.bytes / PAGE_BYTES, 1);
	if (!c.resident) {
		problem(&c, FAIL, "observer_allocation_failed");
		goto untouched;
	}
	if (fixture_create(&c) || snapshot(&c, "before", &c.before))
		goto done;
	c.before_valid = true;
	if (c.before.cg_zswap || c.before.cg_zswapped) {
		problem(&c, FAIL, "new_memcg_not_empty");
		goto done;
	}
	if (!strcmp(c.test, "roundtrip") || !strcmp(c.test, "memcg_balance"))
		case_roundtrip(&c);
	else if (!strcmp(c.test, "codec_switch"))
		case_codec_switch(&c);
	else if (!strcmp(c.test, "invalid_codec"))
		case_invalid_codec(&c);
	else if (!strcmp(c.test, "concurrent_fault"))
		case_concurrent_fault(&c);
	else if (!strcmp(c.test, "memcg_offline"))
		case_memcg_offline(&c);
	else if (!strcmp(c.test, "memcg_limits"))
		case_memcg_limits(&c);
	else if (!strcmp(c.test, "live_destroy"))
		case_live_destroy(&c);
	else if (!strcmp(c.test, "guest_hotplug"))
		case_guest_hotplug(&c);
	else if (!strcmp(c.test, "large_folio"))
		case_large_folio(&c);
done:
	cleanup(&c);
	free(c.resident);
	goto finish;
untouched:
	printf("COMPRESS_RESET case=%s status=PASS untouched=1\n", c.test);
finish:
	printf("COMPRESS_CASE case=%s status=%s reason=%s\n",
	       c.test, result_name(c.result), c.reason);
	printf("COMPRESS_END schema=1 status=%s cases=1\n", result_name(c.result));
	return c.result;
}
