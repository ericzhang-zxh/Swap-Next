// SPDX-License-Identifier: GPL-2.0-only
/*
 * Swap-in latency in the style of the zswapin_perf cgroup selftest: fill an
 * anonymous region, push it out through memory.reclaim, then time the first
 * touch of every swapped page.  The first half is read sequentially, the
 * second half in a fixed pseudo-random order.  All data is verified.
 *
 * usage: swapin <size, e.g. 1G> <path to memory.reclaim>
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <stdbool.h>
#include <inttypes.h>
#include <time.h>
#include <unistd.h>

#define PAGEMAP_SWAPPED (1ULL << 62)

static long page;
static clockid_t timing_clock = CLOCK_MONOTONIC;
static bool compressed_mode;
static int compressed_type = -1;
#ifndef TRACE_ROOT
#define TRACE_ROOT "/sys/kernel/tracing"
#endif
#define TRACE_INSTANCE TRACE_ROOT "/instances/swap_next_timing"
#define TRACE_EVENT "swap_next_timing/decode_return"
static bool probe_installed, instance_created;
static uint64_t verified_decode_samples;

static int text_write(const char *path, const char *text, bool append)
{
	int fd = open(path, O_WRONLY | O_CLOEXEC | (append ? O_APPEND : O_TRUNC));
	size_t n = strlen(text);
	if (fd < 0)
		return -1;
	ssize_t wrote = write(fd, text, n);
	int saved = errno;
	close(fd);
	errno = saved;
	return wrote == (ssize_t)n ? 0 : -1;
}

static int text_read(const char *path, char *buf, size_t cap)
{
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	size_t used = 0;
	if (fd < 0)
		return -1;
	for (;;) {
		ssize_t n = read(fd, buf + used, cap - used - 1);
		if (n < 0) { close(fd); return -1; }
		if (!n) { buf[used] = 0; close(fd); return 0; }
		used += n;
		if (used == cap - 1) { close(fd); errno = EOVERFLOW; return -1; }
	}
}

static void probe_cleanup(void)
{
	if (instance_created) {
		text_write(TRACE_INSTANCE "/tracing_on", "0", false);
		text_write(TRACE_INSTANCE "/events/" TRACE_EVENT "/enable", "0", false);
		rmdir(TRACE_INSTANCE);
	}
	if (probe_installed)
		text_write(TRACE_ROOT "/kprobe_events", "-:" TRACE_EVENT "\n", true);
}

static int probe_setup(void)
{
	char marker[64], filter[64];
	if (geteuid() != 0 || text_read("/run/swap-next-guest", marker, sizeof(marker)) ||
	    strcmp(marker, "swap-next-guest-v1\n"))
		return -1;
	if (!access(TRACE_ROOT "/events/" TRACE_EVENT, F_OK))
		return -1;
	if (text_write(TRACE_ROOT "/kprobe_events",
		       "r64:" TRACE_EVENT " zswap_load ret=$retval:s64\n", true))
		return -1;
	probe_installed = true;
	atexit(probe_cleanup);
	if (mkdir(TRACE_INSTANCE, 0700))
		return -1;
	instance_created = true;
	snprintf(filter, sizeof(filter), "common_pid == %ld", (long)getpid());
	if (text_write(TRACE_INSTANCE "/tracing_on", "0", false) ||
	    text_write(TRACE_INSTANCE "/current_tracer", "nop", false) ||
	    text_write(TRACE_INSTANCE "/buffer_size_kb", "16", false) ||
	    text_write(TRACE_INSTANCE "/events/" TRACE_EVENT "/filter", filter, false) ||
	    text_write(TRACE_INSTANCE "/events/" TRACE_EVENT "/enable", "1", false) ||
	    text_write(TRACE_INSTANCE "/tracing_on", "1", false))
		return -1;
	puts("COMPRESSED_OBSERVER id=pid_kretprobe_zswap_load_v1 instrumented=1 clock=monotonic_raw maxactive=64");
	return 0;
}

static int target_ready(char *address)
{
	uint64_t pte;
	unsigned char resident;
	int fd = open("/proc/self/pagemap", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	ssize_t n = pread(fd, &pte, sizeof(pte), ((uintptr_t)address / page) * sizeof(pte));
	close(fd);
	if (n != sizeof(pte) || !(pte & PAGEMAP_SWAPPED) || (pte & (1ULL << 63)) ||
	    (int)(pte & 31) != compressed_type || mincore(address, page, &resident) ||
	    (resident & 1))
		return -1;
	return text_write(TRACE_INSTANCE "/trace", "\n", false);
}

struct trace_read_info {
	size_t bytes;
	int error;
	bool truncated;
	const char *stage;
};

struct trace_parse_info {
	unsigned long entries, written;
	int headers, records;
	bool attempted, scan_complete, bad_record, return_present;
	size_t bad_offset, bad_length;
	long return_value;
	const char *reason;
};

/* Match text_read's limit and rejection; retain partial bytes on an error. */
static int trace_read_file(const char *path, char *raw, size_t cap,
			   struct trace_read_info *info)
{
	int fd;

	*info = (struct trace_read_info){ .stage = "open" };
	fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		info->error = errno;
		raw[0] = 0;
		return -1;
	}
	info->stage = "read";
	for (;;) {
		ssize_t n = read(fd, raw + info->bytes, cap - info->bytes - 1);

		if (n < 0) {
			info->error = errno;
			raw[info->bytes] = 0;
			close(fd);
			return -1;
		}
		if (!n) {
			raw[info->bytes] = 0;
			info->stage = "complete";
			close(fd);
			return 0;
		}
		info->bytes += n;
		if (info->bytes == cap - 1) {
			raw[info->bytes] = 0;
			info->stage = "limit";
			info->truncated = true;
			info->error = EOVERFLOW;
			close(fd);
			return -1;
		}
	}
}

static int parse_decode_trace(char *raw, struct trace_parse_info *info)
{
	char *line = raw;

	*info = (struct trace_parse_info){ .attempted = true, .reason = "ok" };
	while (*(line += strspn(line, "\n"))) {
		char *end = line + strcspn(line, "\n");
		char saved = *end;

		/* Restore each separator so a failure keeps the first read intact. */
		*end = 0;
		if (sscanf(line, "# entries-in-buffer/entries-written: %lu/%lu",
			   &info->entries, &info->written) == 2)
			info->headers++;
		if (line[0] != '#') {
			char *event = strstr(line, " decode_return: ");
			char *ret = event ? strstr(event, " ret=") : NULL;
			char tail;
			long value = 0;
			int fields = ret ? sscanf(ret, " ret=%ld %c", &value, &tail) : 0;

			if (!ret || fields != 1 || value != 0) {
				info->bad_record = true;
				info->bad_offset = line - raw;
				info->bad_length = end - line;
				info->return_present = fields >= 1;
				info->return_value = value;
				info->reason = !event ? "event_missing" :
					!ret ? "return_missing" : fields != 1 ?
					"return_format" : "return_nonzero";
				*end = saved;
				return -1;
			}
			info->records++;
		}
		*end = saved;
		line = end;
	}
	info->scan_complete = true;
	/* A missing entry, duplicate decode or ring-buffer loss is invalid. */
	if (info->headers != 1)
		info->reason = "header_count";
	else if (info->entries != 1)
		info->reason = "entry_count";
	else if (info->written != 1)
		info->reason = "written_count";
	else if (info->records != 1)
		info->reason = "record_count";
	return strcmp(info->reason, "ok") ? -1 : 0;
}

static void trace_hex(FILE *out, const char *raw, size_t bytes)
{
	for (size_t i = 0; i < bytes; i++) {
		fprintf(out, "%02x", (unsigned char)raw[i]);
		if ((i + 1) % 64 == 0)
			fputc('\n', out);
	}
	if (bytes % 64)
		fputc('\n', out);
}

static void trace_readback(FILE *out, const char *name, const char *path)
{
	char raw[4096];
	struct trace_read_info read_info;
	int result = trace_read_file(path, raw, sizeof(raw), &read_info);

	fprintf(out, "COMPRESSED_TRACE_READBACK_BEGIN phase=post_failure name=%s result=%d stage=%s errno=%d bytes=%zu truncated=%d encoding=hex\n",
		name, result, read_info.stage, read_info.error, read_info.bytes,
		read_info.truncated);
	trace_hex(out, raw, read_info.bytes);
	fprintf(out, "COMPRESSED_TRACE_READBACK_END name=%s\n", name);
}

static void trace_failure_dump(FILE *out, const char *order, size_t target,
			       const char *raw, int read_result,
			       const struct trace_read_info *read_info,
			       const struct trace_parse_info *parse_info)
{
	static bool emitted;
	const struct {
		const char *name, *path;
	} readbacks[] = {
		{ "tracing_on", TRACE_INSTANCE "/tracing_on" },
		{ "current_tracer", TRACE_INSTANCE "/current_tracer" },
		{ "trace_options", TRACE_INSTANCE "/trace_options" },
		{ "event_enable", TRACE_INSTANCE "/events/" TRACE_EVENT "/enable" },
		{ "event_filter", TRACE_INSTANCE "/events/" TRACE_EVENT "/filter" },
		{ "event_format", TRACE_INSTANCE "/events/" TRACE_EVENT "/format" },
		{ "kprobe_events", TRACE_ROOT "/kprobe_events" },
		{ "kprobe_profile", TRACE_ROOT "/kprobe_profile" },
	};
	long cpus;
	int disabled, disable_error;

	if (emitted)
		return;
	emitted = true;
	errno = 0;
	disabled = text_write(TRACE_INSTANCE "/tracing_on", "0", false);
	disable_error = disabled ? errno : 0;
	fprintf(out, "COMPRESSED_TRACE_DIAGNOSTIC schema=1 order=%s target_index=%zu read_result=%d read_stage=%s read_errno=%d bytes=%zu truncated=%d parse_attempted=%d parse_reason=%s scan_complete=%d headers=%d entries=%lu written=%lu records=%d bad_record=%d bad_offset=%zu bad_length=%zu return_present=%d return_value=%ld disable_result=%d disable_errno=%d\n",
		order, target, read_result, read_info->stage, read_info->error,
		read_info->bytes, read_info->truncated, parse_info->attempted,
		parse_info->reason, parse_info->scan_complete, parse_info->headers,
		parse_info->entries, parse_info->written, parse_info->records,
		parse_info->bad_record,
		parse_info->bad_offset, parse_info->bad_length,
		parse_info->return_present, parse_info->return_value, disabled,
		disable_error);
	fprintf(out, "COMPRESSED_TRACE_FIRST_READ_BEGIN bytes=%zu encoding=hex\n",
		read_info->bytes);
	trace_hex(out, raw, read_info->bytes);
	fputs("COMPRESSED_TRACE_FIRST_READ_END\n", out);
	for (size_t i = 0; i < sizeof(readbacks) / sizeof(readbacks[0]); i++)
		trace_readback(out, readbacks[i].name, readbacks[i].path);

	/* Bound post-failure output even with an unexpected CPU enumeration. */
	cpus = sysconf(_SC_NPROCESSORS_CONF);
	fprintf(out, "COMPRESSED_TRACE_CPUS phase=post_failure configured=%ld limit=64 truncated=%d\n",
		cpus, cpus < 1 || cpus > 64);
	for (long cpu = 0; cpu < cpus && cpu < 64; cpu++) {
		char name[48], path[256];

		snprintf(name, sizeof(name), "cpu%ld_stats", cpu);
		snprintf(path, sizeof(path), TRACE_INSTANCE "/per_cpu/cpu%ld/stats", cpu);
		trace_readback(out, name, path);
	}
}

static int decode_observed(const char *order, size_t target)
{
	char raw[32768];
	struct trace_read_info read_info;
	struct trace_parse_info parse_info = { .reason = "not_run" };
	int result = trace_read_file(TRACE_INSTANCE "/trace", raw, sizeof(raw), &read_info);

	if (result || parse_decode_trace(raw, &parse_info)) {
		trace_failure_dump(stdout, order, target, raw, result, &read_info,
				   &parse_info);
		return -1;
	}
	verified_decode_samples++;
	return 0;
}

static int probe_misses(uint64_t *hits, uint64_t *misses)
{
	char raw[65536], *line, *save, name[128];
	unsigned long h, m;
	int count = 0;
	if (text_read(TRACE_ROOT "/kprobe_profile", raw, sizeof(raw)))
		return -1;
	for (line = strtok_r(raw, "\n", &save); line; line = strtok_r(NULL, "\n", &save))
		if (sscanf(line, "%127s %lu %lu", name, &h, &m) == 3 && !strcmp(name, "decode_return")) {
			*hits = h; *misses = m; count++;
		}
	return count == 1 ? 0 : -1;
}

static int compressed_topology(const char *phase)
{
	FILE *f = fopen("/proc/swaps", "r");
	char line[512], name[128], kind[64], expected[64];
	unsigned long size, used;
	int priority, count = 0;
	if (!f)
		return -1;
	snprintf(expected, sizeof(expected), "xswap%d", compressed_type);
	while (fgets(line, sizeof(line), f)) {
		if (sscanf(line, "%127s %63s %lu %lu %d", name, kind, &size, &used, &priority) != 5)
			continue;
		if (strcmp(name, expected)) { fclose(f); return -1; }
		count++;
	}
	int error = ferror(f);
	fclose(f);
	if (error || count != 1)
		return -1;
	printf("COMPRESSED_TOPOLOGY phase=%s devices=1 physical=0 type=%d\n", phase, compressed_type);
	return 0;
}

static int debug_number(const char *name, uint64_t *value)
{
	char path[256], raw[128], tail;
	snprintf(path, sizeof(path), "/sys/kernel/debug/zswap/%s", name);
	return text_read(path, raw, sizeof(raw)) || sscanf(raw, "%" SCNu64 " %c", value, &tail) != 1 ? -1 : 0;
}

static int compression_snapshot(const char *phase, uint64_t *stored, uint64_t *pool, uint64_t *raw)
{
	if (debug_number("stored_pages", stored) || debug_number("pool_total_size", pool) ||
	    debug_number("stored_incompressible_pages", raw))
		return -1;
	printf("COMPRESSED_STATE phase=%s stored_pages=%" PRIu64 " pool_bytes=%" PRIu64 " incompressible_pages=%" PRIu64 "\n",
	       phase, *stored, *pool, *raw);
	return 0;
}


static uint64_t word(size_t pg, size_t i)
{
	uint64_t x = (pg + 1) * 0x9e3779b97f4a7c15ULL + i * 0xbf58476d1ce4e5b9ULL;

	x ^= x >> 31;
	return x * 0x94d049bb133111ebULL;
}

static void fill(char *buf, size_t pages)
{
	size_t words = page / sizeof(uint64_t);

	/* Half random, half zero: compressible, never same-filled. */
	for (size_t pg = 0; pg < pages; pg++) {
		uint64_t *p = (uint64_t *)(buf + pg * page);

		for (size_t i = 0; i < words; i++)
			p[i] = i < words / 2 ? word(pg, i) : 0;
	}
}

static size_t verify(char *buf, size_t pages)
{
	size_t words = page / sizeof(uint64_t), bad = 0;

	for (size_t pg = 0; pg < pages; pg++) {
		uint64_t *p = (uint64_t *)(buf + pg * page);

		for (size_t i = 0; i < words; i++)
			if (p[i] != (i < words / 2 ? word(pg, i) : 0)) {
				bad++;
				break;
			}
	}
	return bad;
}

static size_t swapped(char *buf, size_t pages, unsigned char *map)
{
	int fd = open("/proc/self/pagemap", O_RDONLY);
	size_t n = 0;

	if (fd < 0) {
		perror("pagemap");
		exit(1);
	}
	for (size_t pg = 0; pg < pages; pg++) {
		uint64_t e;
		off_t off = ((uintptr_t)buf / page + pg) * sizeof(e);

		if (pread(fd, &e, sizeof(e), off) != sizeof(e)) {
			perror("pread pagemap");
			exit(1);
		}
		map[pg] = !!(e & PAGEMAP_SWAPPED);
		n += map[pg];
	}
	close(fd);
	return n;
}

static bool compressed_targets_evicted(char *buf, size_t pages, const unsigned char *map,
				       unsigned char *resident)
{
	size_t seq = 0, random = 0, half = pages / 2;
	if (mincore(buf, pages * page, resident))
		return false;
	for (size_t pg = 0; pg < pages; pg++) {
		if (!map[pg])
			continue;
		if (resident[pg] & 1)
			return false;
		if (pg < half) seq++;
		else random++;
	}
	return seq * 10 >= half * 9 && random * 10 >= (pages - half) * 9;
}

static int reclaim(const char *path, size_t bytes)
{
	int fd = open(path, O_WRONLY);
	char s[32];
	int ret;

	if (fd < 0) {
		perror("memory.reclaim");
		exit(1);
	}
	snprintf(s, sizeof(s), "%zu", bytes);
	ret = write(fd, s, strlen(s));
	close(fd);
	return ret < 0 ? -errno : 0;
}

static uint64_t now_ns(void)
{
	struct timespec ts;

	clock_gettime(timing_clock, &ts);
	return ts.tv_sec * 1000000000ULL + ts.tv_nsec;
}

static int cmp(const void *a, const void *b)
{
	uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;

	return x < y ? -1 : x > y;
}

static void report(const char *name, uint64_t *lat, size_t n, uint64_t total)
{
	double mean;

	if (!n) {
		printf("%s samples=0\n", name);
		return;
	}
	mean = (double)total / n;
	qsort(lat, n, sizeof(*lat), cmp);
	printf("%s samples=%zu mean_ns=%.0f p50_ns=%lu p90_ns=%lu p99_ns=%lu p999_ns=%lu max_ns=%lu total_ms=%.3f\n",
	       name, n, mean, lat[n / 2], lat[n * 9 / 10], lat[n * 99 / 100],
	       lat[n * 999 / 1000], lat[n - 1], total / 1e6);
}

int main(int argc, char **argv)
{
	size_t bytes, pages, half, n_seq = 0, n_rand = 0, *order;
	uint64_t *lat_seq, *lat_rand, t_seq = 0, t_rand = 0;
	unsigned char *map, *resident = NULL;
	volatile uint64_t sink = 0;
	char *buf, unit = '\0';
	int i;
	uint64_t before_stored = 0, before_pool = 0, before_raw = 0;
	uint64_t stored = 0, pool = 0, raw = 0;

	if ((argc != 3 && argc != 6) || sscanf(argv[1], "%zu%c", &bytes, &unit) < 1) {
		fprintf(stderr, "usage: swapin SIZE[K|M|G] MEMORY_RECLAIM [compressed TYPE CGROUP]\n");
		return 2;
	}
	if (argc == 6) {
		char *end;
		long type = strtol(argv[4], &end, 10);
		if (strcmp(argv[3], "compressed") || *end || type < 0 || type > 31 ||
		    strncmp(argv[5], "/sys/fs/cgroup/", 15))
			return 2;
		compressed_mode = true;
		compressed_type = type;
		timing_clock = CLOCK_MONOTONIC_RAW;
		if (probe_setup() || compressed_topology("before") ||
		    compression_snapshot("before", &before_stored, &before_pool, &before_raw)) {
			puts("SWAPIN_FAIL compressed_observer_setup");
			return 1;
		}
	}
	if (unit == 'G')
		bytes <<= 30;
	else if (unit == 'M')
		bytes <<= 20;
	else if (unit == 'K')
		bytes <<= 10;

	page = sysconf(_SC_PAGESIZE);
	pages = bytes / page;
	if (pages < 2 || bytes % page || (compressed_mode && page != 4096))
		return 2;
	half = pages / 2;
	buf = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	map = calloc(pages, 1);
	if (compressed_mode)
		resident = calloc(pages, 1);
	lat_seq = calloc(half, sizeof(*lat_seq));
	lat_rand = calloc(pages - half, sizeof(*lat_rand));
	order = calloc(pages - half, sizeof(*order));
	if (buf == MAP_FAILED || !map || !lat_seq || !lat_rand || !order || (compressed_mode && !resident)) {
		perror("alloc");
		return 1;
	}
	madvise(buf, bytes, MADV_NOHUGEPAGE);
	fill(buf, pages);

	/* Reclaim until at least 90% of the region is out, at most 16 tries. */
	for (i = 0; i < 16; i++) {
		reclaim(argv[2], bytes);
		if (swapped(buf, pages, map) * 10 >= pages * 9 &&
		    (!compressed_mode || compressed_targets_evicted(buf, pages, map, resident)))
			break;
	}
	printf("SWAPIN_SWAPPED pages=%zu swapped=%zu reclaim_rounds=%d\n",
	       pages, swapped(buf, pages, map), compressed_mode && i == 16 ? 16 : i + 1);
	if (swapped(buf, pages, map) * 10 < pages * 9 ||
	    (compressed_mode && !compressed_targets_evicted(buf, pages, map, resident))) {
		printf("SWAPIN_FAIL not_swapped\n");
		return 1;
	}

	if (compressed_mode) {
		size_t seq_targets = 0, rand_targets = 0;
		for (size_t pg = 0; pg < pages; pg++) {
			if (pg < half) seq_targets += map[pg];
			else rand_targets += map[pg];
		}
		if (bytes != 134217728 || seq_targets * 10 < half * 9 ||
		    rand_targets * 10 < (pages - half) * 9) {
			puts("SWAPIN_FAIL compressed_order_coverage");
			return 1;
		}
	}
	if (compressed_mode &&
	    (compression_snapshot("stored", &stored, &pool, &raw) ||
	     stored < before_stored + swapped(buf, pages, map) || pool <= before_pool || raw != before_raw)) {
		puts("SWAPIN_FAIL compressed_storage");
		return 1;
	}

	for (size_t pg = 0; pg < half; pg++) {
		uint64_t t0, d;

		if (!map[pg])
			continue;
		if (compressed_mode && target_ready(buf + pg * page)) {
			puts("SWAPIN_FAIL compressed_target_not_evicted");
			return 1;
		}
		t0 = now_ns();
		sink += *(volatile uint64_t *)(buf + pg * page);
		d = now_ns() - t0;
		if (compressed_mode && decode_observed("seq", pg)) {
			puts("SWAPIN_FAIL compressed_decode_unproven");
			return 1;
		}
		lat_seq[n_seq++] = d;
		t_seq += d;
	}

	/* Fixed Fisher-Yates shuffle so every run uses the same order. */
	for (size_t k = 0; k < pages - half; k++)
		order[k] = half + k;
	for (size_t k = pages - half - 1; k > 0; k--) {
		size_t j = word(k, 7) % (k + 1), tmp = order[k];

		order[k] = order[j];
		order[j] = tmp;
	}
	for (size_t k = 0; k < pages - half; k++) {
		size_t pg = order[k];
		uint64_t t0, d;

		if (!map[pg])
			continue;
		if (compressed_mode && target_ready(buf + pg * page)) {
			puts("SWAPIN_FAIL compressed_target_not_evicted");
			return 1;
		}
		t0 = now_ns();
		sink += *(volatile uint64_t *)(buf + pg * page);
		d = now_ns() - t0;
		if (compressed_mode && decode_observed("rand", pg)) {
			puts("SWAPIN_FAIL compressed_decode_unproven");
			return 1;
		}
		lat_rand[n_rand++] = d;
		t_rand += d;
	}

	if (compressed_mode) {
		uint64_t hits = 0, misses = 0;
		if (text_write(TRACE_INSTANCE "/events/" TRACE_EVENT "/enable", "0", false) ||
		    probe_misses(&hits, &misses) || misses || hits < verified_decode_samples ||
		    verified_decode_samples != n_seq + n_rand || compressed_topology("after")) {
			puts("SWAPIN_FAIL compressed_observer_loss");
			return 1;
		}
		printf("COMPRESSED_SAMPLES seq=%zu rand=%zu target_checks=%" PRIu64 " decoded=%" PRIu64 " trace_lost=0 probe_missed=%" PRIu64 " probe_hits=%" PRIu64 "\n",
		       n_seq, n_rand, verified_decode_samples, verified_decode_samples, misses, hits);
	}

	report("SWAPIN_SEQ", lat_seq, n_seq, t_seq);
	report("SWAPIN_RAND", lat_rand, n_rand, t_rand);
	if (verify(buf, pages)) {
		printf("SWAPIN_FAIL data\n");
		return 1;
	}
	printf("SWAPIN_DATA_PASS\n");
	(void)sink;
	return 0;
}
