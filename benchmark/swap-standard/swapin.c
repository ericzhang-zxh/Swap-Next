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

#define C2_CONTRACT "xswap-independent-v1"
#define C2_OBSERVER_ID "pid_kretprobe_frontend_v2"
#define C2_ANCHOR "5e84ca928deeacb4eee656806a003f27d1eca82f"
#define C2_TARGET_BYTES 134217728ULL
#define C2_ISOLATION "mlockall_current_future_target_munlock_v1"
#ifndef C2_CMDLINE_PATH
#define C2_CMDLINE_PATH "/proc/cmdline"
#endif
#ifndef C2_SMAPS_PATH
#define C2_SMAPS_PATH "/proc/self/smaps"
#endif
#ifndef C2_MEMINFO_PATH
#define C2_MEMINFO_PATH "/proc/meminfo"
#endif
#ifndef C2_FRONTEND_ROOT
#define C2_FRONTEND_ROOT "/sys/kernel/debug/xswap/frontend"
#endif
#ifndef C2_ZSWAP_PARAMETERS
#define C2_ZSWAP_PARAMETERS "/sys/module/zswap/parameters"
#endif
#ifndef C2_ZSWAP_DEBUG
#define C2_ZSWAP_DEBUG "/sys/kernel/debug/zswap"
#endif

static bool c2_mode;
static const char *c2_role, *c2_source, *c2_frontend, *c2_symbol;
static int c2_probe_readbacks(void);
static int c2_debug_number(const char *name, uint64_t *value);
static int c2_legacy_snapshot(const char *phase, uint64_t stored,
			      uint64_t pool, uint64_t raw);
static int c2_frontend_snapshot(const char *phase, uint64_t *stored,
				uint64_t *pool, uint64_t *raw);

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
	char marker[64], filter[64], registration[192];
	if (geteuid() != 0 || text_read("/run/swap-next-guest", marker, sizeof(marker)) ||
	    strcmp(marker, "swap-next-guest-v1\n"))
		return -1;
	if (!access(TRACE_ROOT "/events/" TRACE_EVENT, F_OK))
		return -1;
	snprintf(registration, sizeof(registration),
		 "r64:" TRACE_EVENT " %s ret=$retval:s64\n",
		 c2_mode ? c2_symbol : "zswap_load");
	if (text_write(TRACE_ROOT "/kprobe_events", registration, true))
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
	if (c2_mode) {
		if (c2_probe_readbacks())
			return -1;
		printf("COMPRESSED_OBSERVER id=" C2_OBSERVER_ID " instrumented=1 clock=monotonic_raw maxactive=64 contract=" C2_CONTRACT " role=%s source=%s frontend=%s symbol=%s buffer_kb=16 success_return=0\n",
		       c2_role, c2_source, c2_frontend, c2_symbol);
	} else {
		puts("COMPRESSED_OBSERVER id=pid_kretprobe_zswap_load_v1 instrumented=1 clock=monotonic_raw maxactive=64");
	}
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

	if (c2_mode)
		return c2_debug_number(name, value);
	snprintf(path, sizeof(path), C2_ZSWAP_DEBUG "/%s", name);
	return text_read(path, raw, sizeof(raw)) || sscanf(raw, "%" SCNu64 " %c", value, &tail) != 1 ? -1 : 0;
}

static int compression_snapshot(const char *phase, uint64_t *stored, uint64_t *pool, uint64_t *raw)
{
	if (c2_mode && !strcmp(c2_frontend, "independent"))
		return c2_frontend_snapshot(phase, stored, pool, raw);
	if (debug_number("stored_pages", stored) || debug_number("pool_total_size", pool) ||
	    debug_number("stored_incompressible_pages", raw))
		return -1;
	printf("COMPRESSED_STATE phase=%s stored_pages=%" PRIu64 " pool_bytes=%" PRIu64 " incompressible_pages=%" PRIu64 "\n",
	       phase, *stored, *pool, *raw);
	return c2_mode ? c2_legacy_snapshot(phase, *stored, *pool, *raw) : 0;
}



/* Revision 9 has its own strict input and readback contract. */
static int c2_u64(const char *text, uint64_t *value)
{
	uint64_t result = 0;

	if (!*text || (*text == '0' && text[1]))
		return -1;
	for (const char *p = text; *p; p++) {
		unsigned int digit = (unsigned char)*p - '0';

		if (digit > 9 || result > (UINT64_MAX - digit) / 10)
			return -1;
		result = result * 10 + digit;
	}
	*value = result;
	return 0;
}

static bool c2_identifier(const char *text)
{
	size_t n = strlen(text);

	if (!n || n > 64 || text[0] < 'a' || text[0] > 'z')
		return false;
	for (size_t i = 1; i < n; i++)
		if ((text[i] < 'a' || text[i] > 'z') &&
		    (text[i] < '0' || text[i] > '9') &&
		    text[i] != '_' && text[i] != '-')
			return false;
	return true;
}

static int c2_arguments(int argc, char **argv)
{
	char reclaim_path[4096], digits[32];
	size_t n;
	uint64_t size, type, multiplier = 1;

	if (argc != 11 || strcmp(argv[3], "compressed") ||
	    strcmp(argv[6], C2_CONTRACT) ||
	    strcmp(argv[9], C2_OBSERVER_ID) ||
	    strncmp(argv[5], "/sys/fs/cgroup/", 15) ||
	    snprintf(reclaim_path, sizeof(reclaim_path), "%s/memory.reclaim", argv[5])
		>= (int)sizeof(reclaim_path) || strcmp(reclaim_path, argv[2]) ||
	    c2_u64(argv[4], &type) || type > 31 || strlen(argv[8]) != 40)
		return -1;
	for (size_t i = 0; i < 40; i++)
		if ((argv[8][i] < '0' || argv[8][i] > '9') &&
		    (argv[8][i] < 'a' || argv[8][i] > 'f'))
			return -1;
	if (!strcmp(argv[7], "baseline")) {
		if (strcmp(argv[8], C2_ANCHOR) || strcmp(argv[10], "legacy"))
			return -1;
	} else if (!strcmp(argv[7], "candidate")) {
		if (!strcmp(argv[8], C2_ANCHOR) || strcmp(argv[10], "independent"))
			return -1;
	} else {
		return -1;
	}
	n = strlen(argv[1]);
	if (!n || n >= sizeof(digits))
		return -1;
	memcpy(digits, argv[1], n + 1);
	if (digits[n - 1] == 'K' || digits[n - 1] == 'M' || digits[n - 1] == 'G') {
		multiplier = digits[n - 1] == 'K' ? 1024 :
			     digits[n - 1] == 'M' ? 1048576 : 1073741824;
		digits[--n] = 0;
	}
	if (c2_u64(digits, &size) || size > UINT64_MAX / multiplier ||
	    size * multiplier != C2_TARGET_BYTES)
		return -1;
	c2_role = argv[7];
	c2_source = argv[8];
	c2_frontend = argv[10];
	c2_symbol = !strcmp(c2_role, "baseline") ? "zswap_load" : "xswap_load_folio";
	c2_mode = true;
	return 0;
}

static int c2_read(const char *path, char *raw, size_t cap, size_t *bytes)
{
	struct trace_read_info info;

	if (trace_read_file(path, raw, cap, &info) || !info.bytes ||
	    memchr(raw, 0, info.bytes) || raw[info.bytes - 1] != '\n')
		return -1;
	*bytes = info.bytes;
	return 0;
}

static int c2_debug_number(const char *name, uint64_t *value)
{
	char path[256], raw[128];
	size_t bytes;

	snprintf(path, sizeof(path), C2_ZSWAP_DEBUG "/%s", name);
	if (c2_read(path, raw, sizeof(raw), &bytes))
		return -1;
	raw[bytes - 1] = 0;
	return c2_u64(raw, value);
}

static int c2_cmdline_matches(char *raw)
{
	struct {
		const char *key, *value;
		unsigned int count;
	} expected[] = {
		{ "bench.protocol_revision", "9", 0 },
		{ "bench.contract_id", C2_CONTRACT, 0 },
		{ "bench.source_role", c2_role, 0 },
		{ "bench.source_commit", c2_source, 0 },
		{ "bench.frontend", c2_frontend, 0 },
		{ "bench.observer", C2_OBSERVER_ID, 0 },
		{ "bench.compression_target_bytes", "134217728", 0 },
		{ "bench.backend", "compressed", 0 },
		{ "bench.mode", "xswap", 0 },
		{ "bench.workload", "swapin", 0 },
	};
	char *save, *word;

	for (word = strtok_r(raw, " \t\n", &save); word;
	     word = strtok_r(NULL, " \t\n", &save)) {
		for (size_t i = 0; i < sizeof(expected) / sizeof(expected[0]); i++) {
			size_t n = strlen(expected[i].key);

			if (strncmp(word, expected[i].key, n) || word[n] != '=')
				continue;
			if (++expected[i].count != 1 || strcmp(word + n + 1, expected[i].value))
				return -1;
		}
	}
	for (size_t i = 0; i < sizeof(expected) / sizeof(expected[0]); i++)
		if (expected[i].count != 1)
			return -1;
	return 0;
}

static int c2_source_readback(void)
{
	char raw[16384];
	size_t bytes;

	return c2_read(C2_CMDLINE_PATH, raw, sizeof(raw), &bytes) ||
	       c2_cmdline_matches(raw) ? -1 : 0;
}

static int c2_next_line(const char **cursor, char *line, size_t cap)
{
	const char *end;
	size_t n;

	if (!**cursor)
		return 0;
	end = strchr(*cursor, '\n');
	if (!end || (n = end - *cursor) >= cap)
		return -1;
	memcpy(line, *cursor, n);
	line[n] = 0;
	*cursor = end + 1;
	return 1;
}

static int c2_registration(const char *raw)
{
	char line[4096], expected[192];
	const char *cursor = raw;
	int result, found = 0;

	snprintf(expected, sizeof(expected),
		 "r64:" TRACE_EVENT " %s ret=$retval:s64", c2_symbol);
	while ((result = c2_next_line(&cursor, line, sizeof(line))) > 0) {
		char *event = strstr(line, ":" TRACE_EVENT);

		if (!event)
			continue;
		/* Reject aliases, extra fields, wrong symbol and duplicate registration. */
		if (strcmp(line, expected) || ++found != 1)
			return -1;
	}
	return result || found != 1 ? -1 : 0;
}

static int c2_trace_options(const char *raw)
{
	const char *required[] = { "context-info", "nolatency-format", "nohex",
				  "nobin", "noraw", "noverbose" };
	char line[256];
	const char *cursor = raw;
	unsigned int seen = 0;
	int result;

	while ((result = c2_next_line(&cursor, line, sizeof(line))) > 0) {
		for (size_t i = 0; i < sizeof(required) / sizeof(required[0]); i++) {
			const char *opposite = !strncmp(required[i], "no", 2) ?
					       required[i] + 2 : "nocontext-info";

			if (!strcmp(line, opposite))
				return -1;
			if (strcmp(line, required[i]))
				continue;
			if (seen & (1U << i))
				return -1;
			seen |= 1U << i;
		}
	}
	return result || seen != (1U << 6) - 1 ? -1 : 0;
}

static int c2_event_format(const char *raw)
{
	char line[4096];
	const char *cursor = raw;
	int result, names = 0, returns = 0;

	while ((result = c2_next_line(&cursor, line, sizeof(line))) > 0) {
		char type[32], name[32];
		unsigned int offset, size, is_signed;
		int used = 0;

		if (!strncmp(line, "name:", 5)) {
			if (strcmp(line, "name: decode_return") || ++names != 1)
				return -1;
		}
		if (!strstr(line, " ret;"))
			continue;
		if (sscanf(line, " field:%31s %31[^;]; offset:%u; size:%u; signed:%u;%n",
			   type, name, &offset, &size, &is_signed, &used) != 5 ||
		    !used || line[used] || strcmp(type, "s64") || strcmp(name, "ret") ||
		    offset != 24 || size != 8 || is_signed != 1 || ++returns != 1)
			return -1;
	}
	return result || names != 1 || returns != 1 ? -1 : 0;
}

static int c2_probe_readbacks(void)
{
	const struct {
		const char *name, *path, *expected;
	} files[] = {
		{ "kprobe_events", TRACE_ROOT "/kprobe_events", NULL },
		{ "current_tracer", TRACE_INSTANCE "/current_tracer", "nop\n" },
		{ "buffer_size_kb", TRACE_INSTANCE "/buffer_size_kb", "16\n" },
		{ "event_filter", TRACE_INSTANCE "/events/" TRACE_EVENT "/filter", NULL },
		{ "event_enable", TRACE_INSTANCE "/events/" TRACE_EVENT "/enable", "1\n" },
		{ "tracing_on", TRACE_INSTANCE "/tracing_on", "1\n" },
		{ "event_format", TRACE_INSTANCE "/events/" TRACE_EVENT "/format", NULL },
		{ "trace_options", TRACE_INSTANCE "/trace_options", NULL },
	};
	char raw[65536], filter[64];
	size_t bytes;

	snprintf(filter, sizeof(filter), "common_pid == %ld\n", (long)getpid());
	for (size_t i = 0; i < sizeof(files) / sizeof(files[0]); i++) {
		if (c2_read(files[i].path, raw, sizeof(raw), &bytes) ||
		    (files[i].expected && strcmp(raw, files[i].expected)) ||
		    (i == 0 && c2_registration(raw)) ||
		    (i == 3 && strcmp(raw, filter)) ||
		    (i == 6 && c2_event_format(raw)) ||
		    (i == 7 && c2_trace_options(raw)))
			return -1;
		printf("COMPRESSED_PROBE_READBACK_BEGIN phase=setup name=%s bytes=%zu encoding=hex\n",
		       files[i].name, bytes);
		trace_hex(stdout, raw, bytes);
		printf("COMPRESSED_PROBE_READBACK_END name=%s\n", files[i].name);
	}
	return 0;
}

struct isolation_stats {
	uint64_t locked_mappings, locked_mapping_bytes, locked_resident_bytes;
	uint64_t target_mappings, target_unlocked_bytes;
	uint64_t special_mappings, inaccessible_mappings;
};

struct isolation_vma {
	uint64_t start, end, offset, inode, size_kb, locked_kb, huge_kb, kernel_kb, mmu_kb;
	unsigned int major, minor;
	char perms[5], name[4096];
	bool present, lo, lf, nh, rd, wr, ex, sh;
	unsigned int flags_seen, size_seen, locked_seen, huge_seen, kernel_seen, mmu_seen;
	unsigned int field_count;
	char field_names[64][32];
};

/* The buffer exists before mlockall; no raw smaps read is inside t0/touch/t1. */
static char isolation_raw[262144];

static bool c2_special_mapping(const char *name)
{
	return !strcmp(name, "[vvar]") || !strcmp(name, "[vvar_vclock]") ||
	       !strcmp(name, "[vdso]") || !strcmp(name, "[vsyscall]");
}

static int c2_smaps_kb(const char *text, uint64_t *value)
{
	char number[32];
	size_t n = 0;

	while (*text == ' ' || *text == '\t')
		text++;
	while (*text >= '0' && *text <= '9') {
		if (n == sizeof(number) - 1)
			return -1;
		number[n++] = *text++;
	}
	number[n] = 0;
	while (*text == ' ' || *text == '\t')
		text++;
	return strcmp(text, "kB") || c2_u64(number, value) ? -1 : 0;
}

static int c2_smaps_flags(char *text, struct isolation_vma *vma)
{
	bool seen[26 * 26] = { 0 };
	char *save, *flag;

	if (++vma->flags_seen != 1)
		return -1;
	for (flag = strtok_r(text, " \t", &save); flag;
	     flag = strtok_r(NULL, " \t", &save)) {
		unsigned int index;

		if (strlen(flag) != 2 || flag[0] < 'a' || flag[0] > 'z' ||
		    flag[1] < 'a' || flag[1] > 'z')
			return -1;
		index = (flag[0] - 'a') * 26 + flag[1] - 'a';
		if (seen[index])
			return -1;
		seen[index] = true;
		if (!strcmp(flag, "lo")) vma->lo = true;
		if (!strcmp(flag, "lf")) vma->lf = true;
		if (!strcmp(flag, "nh")) vma->nh = true;
		if (!strcmp(flag, "rd")) vma->rd = true;
		if (!strcmp(flag, "wr")) vma->wr = true;
		if (!strcmp(flag, "ex")) vma->ex = true;
		if (!strcmp(flag, "sh")) vma->sh = true;
	}
	return 0;
}

static int c2_finish_vma(const struct isolation_vma *vma, uint64_t target,
			 uint64_t end, uint64_t *covered, struct isolation_stats *stats)
{
	uint64_t size = vma->end - vma->start;
	bool accessible = vma->rd || vma->wr || vma->ex;

	if (!vma->present)
		return 0;
	if (vma->flags_seen != 1 || vma->locked_seen != 1 ||
	    vma->size_seen != 1 || vma->size_kb != size / 1024 ||
	    vma->locked_kb > size / 1024 ||
	    (vma->perms[0] == 'r') != vma->rd || (vma->perms[1] == 'w') != vma->wr ||
	    (vma->perms[2] == 'x') != vma->ex || (vma->perms[3] == 's') != vma->sh)
		return -1;
	if (vma->start < end && vma->end > target) {
		if (vma->start != *covered || vma->end > end ||
		    strcmp(vma->perms, "rw-p") || vma->name[0] ||
		    vma->offset || vma->inode || vma->major || vma->minor ||
		    vma->lo || vma->lf || !vma->nh || vma->locked_kb ||
		    vma->huge_seen != 1 || vma->huge_kb ||
		    vma->kernel_seen != 1 || vma->kernel_kb != 4 ||
		    vma->mmu_seen != 1 || vma->mmu_kb != 4)
			return -1;
		stats->target_mappings++;
		stats->target_unlocked_bytes += size;
		*covered = vma->end;
	} else if (c2_special_mapping(vma->name)) {
		stats->special_mappings++;
	} else if (!accessible) {
		stats->inaccessible_mappings++;
	} else {
		if (vma->perms[3] != 'p' || !vma->lo || vma->lf)
			return -1;
		stats->locked_mappings++;
		stats->locked_mapping_bytes += size;
		stats->locked_resident_bytes += vma->locked_kb * 1024;
	}
	return 0;
}

static int c2_parse_smaps(const char *raw, uint64_t target, uint64_t bytes,
			 struct isolation_stats *stats)
{
	char line[8192];
	const char *cursor = raw;
	struct isolation_vma vma = { 0 };
	uint64_t end = target + bytes, covered = target, last_end = 0;
	int result;

	*stats = (struct isolation_stats){ 0 };
	if (!target || target % 4096 || bytes != C2_TARGET_BYTES || end < target)
		return -1;
	while ((result = c2_next_line(&cursor, line, sizeof(line))) > 0) {
		unsigned long long start, finish, offset, inode;
		unsigned int major, minor;
		char perms[5], *name;
		int used = 0;

		if (sscanf(line, "%llx-%llx %4s %llx %x:%x %llu%n",
			   &start, &finish, perms, &offset, &major, &minor, &inode, &used) == 7) {
			if (c2_finish_vma(&vma, target, end, &covered, stats) ||
			    !used || start < last_end || start >= finish ||
			    start % 4096 || finish % 4096 || strlen(perms) != 4 ||
			    !strchr("r-", perms[0]) || !strchr("w-", perms[1]) ||
			    !strchr("x-", perms[2]) || !strchr("ps", perms[3]) ||
			    (line[used] && line[used] != ' ' && line[used] != '\t'))
				return -1;
			vma = (struct isolation_vma){
				.present = true, .start = start, .end = finish,
				.offset = offset, .inode = inode, .major = major, .minor = minor,
			};
			memcpy(vma.perms, perms, sizeof(perms));
			name = line + used;
			while (*name == ' ' || *name == '\t')
				name++;
			if (strlen(name) >= sizeof(vma.name))
				return -1;
			strcpy(vma.name, name);
			last_end = finish;
			continue;
		}
		if (!vma.present || !*line || !strchr(line, ':')) {
			return -1;
		} else {
			size_t key_length = strchr(line, ':') - line;

			if (!key_length || key_length >= sizeof(vma.field_names[0]) ||
			    vma.field_count == 64)
				return -1;
			for (size_t i = 0; i < key_length; i++)
				if ((line[i] < 'a' || line[i] > 'z') &&
				    (line[i] < 'A' || line[i] > 'Z') && line[i] != '_')
					return -1;
			for (unsigned int i = 0; i < vma.field_count; i++)
				if (strlen(vma.field_names[i]) == key_length &&
				    !strncmp(vma.field_names[i], line, key_length))
					return -1;
			memcpy(vma.field_names[vma.field_count], line, key_length);
			vma.field_names[vma.field_count++][key_length] = 0;
		}
		if (!strncmp(line, "VmFlags:", 8)) {
			if (c2_smaps_flags(line + 8, &vma))
				return -1;
		} else if (!strncmp(line, "Size:", 5)) {
			if (++vma.size_seen != 1 || c2_smaps_kb(line + 5, &vma.size_kb))
				return -1;
		} else if (!strncmp(line, "Locked:", 7)) {
			if (++vma.locked_seen != 1 || c2_smaps_kb(line + 7, &vma.locked_kb))
				return -1;
		} else if (!strncmp(line, "AnonHugePages:", 14)) {
			if (++vma.huge_seen != 1 || c2_smaps_kb(line + 14, &vma.huge_kb))
				return -1;
		} else if (!strncmp(line, "KernelPageSize:", 15)) {
			if (++vma.kernel_seen != 1 || c2_smaps_kb(line + 15, &vma.kernel_kb))
				return -1;
		} else if (!strncmp(line, "MMUPageSize:", 12)) {
			if (++vma.mmu_seen != 1 || c2_smaps_kb(line + 12, &vma.mmu_kb))
				return -1;
		}
	}
	if (result || c2_finish_vma(&vma, target, end, &covered, stats) ||
	    covered != end || stats->target_unlocked_bytes != bytes ||
	    !stats->target_mappings || !stats->locked_mappings ||
	    !stats->locked_mapping_bytes)
		return -1;
	return 0;
}

static int c2_isolation_snapshot(const char *phase, char *target, size_t bytes)
{
	struct isolation_stats stats;
	size_t raw_bytes;

	if (c2_read(C2_SMAPS_PATH, isolation_raw, sizeof(isolation_raw), &raw_bytes) ||
	    c2_parse_smaps(isolation_raw, (uintptr_t)target, bytes, &stats))
		return -1;
	printf("COMPRESSED_ISOLATION_BEGIN phase=%s strategy=" C2_ISOLATION " target_start=%" PRIuPTR " target_bytes=%zu bytes=%zu encoding=hex\n",
	       phase, (uintptr_t)target, bytes, raw_bytes);
	trace_hex(stdout, isolation_raw, raw_bytes);
	printf("COMPRESSED_ISOLATION_END phase=%s locked_mappings=%" PRIu64 " locked_mapping_bytes=%" PRIu64 " locked_resident_bytes=%" PRIu64 " target_mappings=%" PRIu64 " target_unlocked_bytes=%" PRIu64 " special_mappings=%" PRIu64 " inaccessible_mappings=%" PRIu64 "\n",
	       phase, stats.locked_mappings, stats.locked_mapping_bytes,
	       stats.locked_resident_bytes, stats.target_mappings, stats.target_unlocked_bytes,
	       stats.special_mappings, stats.inaccessible_mappings);
	return 0;
}

static int c2_isolate(char *target, size_t bytes)
{
	if (!target || (uintptr_t)target % 4096 || bytes != C2_TARGET_BYTES ||
	    (uintptr_t)target + bytes < (uintptr_t)target)
		return -1;
	if (mlockall(MCL_CURRENT | MCL_FUTURE)) {
		perror("observer mlockall");
		return -1;
	}
	if (munlock(target, bytes)) {
		perror("observer munlock");
		return -1;
	}
	printf("COMPRESSED_ISOLATION_SETUP mlockall=0 munlock=0 flags=current_future target_bytes=%zu\n",
	       bytes);
	return c2_isolation_snapshot("before_reclaim", target, bytes);
}

static int c2_ram_pages(uint64_t *pages)
{
	char raw[65536], line[4096];
	const char *cursor = raw;
	size_t bytes;
	uint64_t kb;
	int found = 0, result;

	if (c2_read(C2_MEMINFO_PATH, raw, sizeof(raw), &bytes))
		return -1;
	while ((result = c2_next_line(&cursor, line, sizeof(line))) > 0) {
		if (strncmp(line, "MemTotal:", 9))
			continue;
		if (++found != 1 || c2_smaps_kb(line + 9, &kb) || !kb || kb % 4)
			return -1;
		*pages = kb / 4;
	}
	return result || found != 1 ? -1 : 0;
}

static int c2_legacy_snapshot(const char *phase, uint64_t stored,
			      uint64_t pool, uint64_t raw)
{
	char codec[128], percent[128], shrinker[128];
	size_t bytes;
	uint64_t ram, limit, limit_hits, written, poor;
	static uint64_t initial_limit_hits, initial_written, initial_poor, initial_ram;
	static bool before;

	(void)stored;
	if (c2_read(C2_ZSWAP_PARAMETERS "/compressor", codec, sizeof(codec), &bytes) ||
	    c2_read(C2_ZSWAP_PARAMETERS "/max_pool_percent", percent, sizeof(percent), &bytes) ||
	    c2_read(C2_ZSWAP_PARAMETERS "/shrinker_enabled", shrinker, sizeof(shrinker), &bytes) ||
	    strcmp(codec, "lzo\n") || strcmp(percent, "20\n") || strcmp(shrinker, "N\n") ||
	    c2_ram_pages(&ram) || ram > UINT64_MAX / 20 ||
	    debug_number("pool_limit_hit", &limit_hits) ||
	    debug_number("written_back_pages", &written) ||
	    debug_number("reject_compress_poor", &poor))
		return -1;
	limit = ram * 20 / 100;
	if (!limit || limit > UINT64_MAX / 4096 || pool >= limit * 4096 || raw)
		return -1;
	if (!strcmp(phase, "before")) {
		if (before)
			return -1;
		before = true;
		initial_limit_hits = limit_hits;
		initial_written = written;
		initial_poor = poor;
		initial_ram = ram;
	} else if (!before || ram != initial_ram || limit_hits != initial_limit_hits ||
		   written != initial_written || poor != initial_poor) {
		return -1;
	}
	printf("COMPRESSED_LEGACY_CONFIG phase=%s codec=lzo max_pool_percent=20 ram_pages=%" PRIu64 " cap_pages=%" PRIu64 " shrinker_enabled=0\n",
	       phase, ram, limit);
	printf("COMPRESSED_LEGACY_LIMITS phase=%s pool_limit_hit=%" PRIu64 " written_back_pages=%" PRIu64 " reject_compress_poor=%" PRIu64 "\n",
	       phase, limit_hits, written, poor);
	return 0;
}

static const char *const frontend_keys[] = {
	"ram_pages", "cap_pages", "cap_updates", "cap_rejects", "bypasses",
	"incompressible_rejects", "raw_admitted",
	"entries_live", "compressed_live", "raw_live", "handles_live", "index_live",
	"lru_live", "stored_bytes", "owner_refs", "charged_bytes", "inflight",
	"store_token_active", "store_token_peak", "store_retries",
	"retained_folios_live", "retained_folio_gets", "retained_folio_puts",
	"pool_backing_pages", "peak_backing_pages", "allocator_chain_pages",
	"cap_headroom_pages", "entry_allocs", "entry_frees", "handle_allocs",
	"handle_frees", "published", "retired", "rollback_objects", "charge_calls",
	"charge_ok", "charge_fail", "charge_injected", "charged_total_bytes",
	"uncharge_calls", "uncharged_total_bytes", "compressed_loads", "raw_loads",
	"load_misses", "decode_errors", "backing_live", "backing_allocs",
	"backing_frees", "backing_charge_denials", "read_submitted", "write_submitted",
	"read_completed", "write_completed", "read_errors", "write_errors",
	"pool_create_ok", "pool_destroy_returned", "test_windows", "events_lost",
};

#define FRONTEND_FIELDS (sizeof(frontend_keys) / sizeof(frontend_keys[0]))

struct frontend_snapshot {
	unsigned int type;
	uint64_t generation, pool, sequence, value[FRONTEND_FIELDS];
	char driver[65];
};

static uint64_t c2_value(const struct frontend_snapshot *snapshot, const char *key)
{
	for (size_t i = 0; i < FRONTEND_FIELDS; i++)
		if (!strcmp(frontend_keys[i], key))
			return snapshot->value[i];
	/* Callers name only members of the fixed contract above. */
	abort();
}

static int c2_parse_frontend(const char *raw, struct frontend_snapshot *snapshot)
{
	const char *cursor = raw;
	char line[512], canonical[512], state[32], codec[32];
	bool seen[FRONTEND_FIELDS] = { 0 };
	unsigned int test;
	int used = 0, result;

	*snapshot = (struct frontend_snapshot){ 0 };
	if (c2_next_line(&cursor, line, sizeof(line)) != 1 ||
	    sscanf(line, "XSWAP_FRONTEND_BEGIN schema=1 type=%u generation=%" SCNu64 " pool=%" SCNu64 " snapshot=%" SCNu64 " state=%31s codec=%31s driver=%64s test=%u%n",
		   &snapshot->type, &snapshot->generation, &snapshot->pool, &snapshot->sequence,
		   state, codec, snapshot->driver, &test, &used) != 8 ||
	    !used || line[used] || snapshot->type != (unsigned int)compressed_type ||
	    !snapshot->generation || snapshot->pool != snapshot->generation ||
	    !snapshot->sequence || strcmp(state, "active") || strcmp(codec, "lzo") ||
	    !c2_identifier(snapshot->driver) || test)
		return -1;
	snprintf(canonical, sizeof(canonical),
		 "XSWAP_FRONTEND_BEGIN schema=1 type=%u generation=%" PRIu64 " pool=%" PRIu64 " snapshot=%" PRIu64 " state=active codec=lzo driver=%s test=0",
		 snapshot->type, snapshot->generation, snapshot->pool,
		 snapshot->sequence, snapshot->driver);
	if (strcmp(line, canonical))
		return -1;
	for (size_t n = 0; n < FRONTEND_FIELDS; n++) {
		char key[64], number[32], tail;
		uint64_t value;
		size_t i;

		if (c2_next_line(&cursor, line, sizeof(line)) != 1 ||
		    sscanf(line, "%63s %31s%c", key, number, &tail) != 2 ||
		    c2_u64(number, &value))
			return -1;
		snprintf(canonical, sizeof(canonical), "%s %" PRIu64, key, value);
		if (strcmp(line, canonical))
			return -1;
		for (i = 0; i < FRONTEND_FIELDS; i++)
			if (!strcmp(key, frontend_keys[i]))
				break;
		if (i != n || seen[i])
			return -1;
		seen[i] = true;
		snapshot->value[i] = value;
	}
	snprintf(canonical, sizeof(canonical),
		 "XSWAP_FRONTEND_END schema=1 type=%u generation=%" PRIu64 " snapshot=%" PRIu64,
		 snapshot->type, snapshot->generation, snapshot->sequence);
	result = c2_next_line(&cursor, line, sizeof(line));
	return result != 1 || strcmp(line, canonical) || *cursor ? -1 : 0;
}

static int c2_frontend_valid(const struct frontend_snapshot *snapshot)
{
	const char *const zero[] = {
		"raw_live", "raw_admitted", "raw_loads", "cap_updates", "cap_rejects",
		"bypasses", "incompressible_rejects", "inflight", "store_token_active",
		"retained_folios_live", "backing_live", "backing_allocs", "backing_frees",
		"backing_charge_denials", "read_submitted", "write_submitted",
		"read_completed", "write_completed", "read_errors", "write_errors",
		"decode_errors", "load_misses", "pool_destroy_returned", "test_windows",
		"events_lost",
	};
	uint64_t entries = c2_value(snapshot, "compressed_live");
	uint64_t stored = c2_value(snapshot, "stored_bytes");
	uint64_t cap = c2_value(snapshot, "cap_pages");
	uint64_t ram = c2_value(snapshot, "ram_pages");
	uint64_t observed_ram;

	if (c2_ram_pages(&observed_ram) || ram != observed_ram || ram > UINT64_MAX / 20 ||
	    !cap || cap > UINT64_MAX / 4096 || cap != ram * 20 / 100 ||
	    c2_value(snapshot, "pool_backing_pages") >= cap ||
	    c2_value(snapshot, "pool_create_ok") != 1 ||
	    c2_value(snapshot, "store_token_peak") > 1 ||
	    entries != c2_value(snapshot, "entries_live") ||
	    entries != c2_value(snapshot, "handles_live") ||
	    entries != c2_value(snapshot, "index_live") ||
	    entries != c2_value(snapshot, "lru_live") ||
	    entries > UINT64_MAX / 4096 ||
	    (entries ? stored < entries || stored >= entries * 4096 : stored != 0))
		return -1;
	for (size_t i = 0; i < sizeof(zero) / sizeof(zero[0]); i++)
		if (c2_value(snapshot, zero[i]))
			return -1;
	const char *const balances[][3] = {
		{ "entry_allocs", "entry_frees", "entries_live" },
		{ "handle_allocs", "handle_frees", "handles_live" },
		{ "published", "retired", "entries_live" },
		{ "charged_total_bytes", "uncharged_total_bytes", "charged_bytes" },
		{ "retained_folio_gets", "retained_folio_puts", "retained_folios_live" },
		{ "charge_calls", "charge_ok", "charge_fail" },
	};
	for (size_t i = 0; i < sizeof(balances) / sizeof(balances[0]); i++) {
		uint64_t total = c2_value(snapshot, balances[i][0]);
		uint64_t released = c2_value(snapshot, balances[i][1]);

		if (released > total || total - released != c2_value(snapshot, balances[i][2]))
			return -1;
	}
	uint64_t headroom = c2_value(snapshot, "cap_headroom_pages");
	uint64_t chain = c2_value(snapshot, "allocator_chain_pages");

	if (!chain || headroom < chain || headroom > UINT64_MAX - cap ||
	    c2_value(snapshot, "pool_backing_pages") > cap + headroom ||
	    c2_value(snapshot, "peak_backing_pages") < c2_value(snapshot, "pool_backing_pages"))
		return -1;
	return 0;
}

static int c2_frontend_snapshot(const char *phase, uint64_t *stored,
				uint64_t *pool, uint64_t *raw)
{
	char path[256], snapshot_raw[16384];
	struct frontend_snapshot current;
	static struct frontend_snapshot previous, stored_snapshot;
	static bool before, have_stored;
	size_t bytes;

	snprintf(path, sizeof(path), C2_FRONTEND_ROOT "/type%d", compressed_type);
	if (c2_read(path, snapshot_raw, sizeof(snapshot_raw), &bytes) ||
	    c2_parse_frontend(snapshot_raw, &current) || c2_frontend_valid(&current))
		return -1;
	if (!strcmp(phase, "before")) {
		if (before || c2_value(&current, "entries_live") ||
		    c2_value(&current, "pool_backing_pages"))
			return -1;
		before = true;
	} else {
		if (!before || current.generation != previous.generation ||
		    current.pool != previous.pool || current.sequence <= previous.sequence ||
		    strcmp(current.driver, previous.driver) ||
		    c2_value(&current, "cap_pages") != c2_value(&previous, "cap_pages"))
			return -1;
	}
	if (!strcmp(phase, "stored")) {
		if (have_stored)
			return -1;
		have_stored = true;
		stored_snapshot = current;
	} else if (!strcmp(phase, "after")) {
		uint64_t loads = c2_value(&current, "compressed_loads");

		if (!have_stored || loads < c2_value(&stored_snapshot, "compressed_loads") ||
		    loads - c2_value(&stored_snapshot, "compressed_loads") < verified_decode_samples)
			return -1;
	} else if (strcmp(phase, "before")) {
		return -1;
	}
	previous = current;
	*stored = c2_value(&current, "compressed_live");
	*pool = c2_value(&current, "pool_backing_pages") * 4096;
	*raw = c2_value(&current, "raw_live");
	printf("COMPRESSED_FRONTEND_BEGIN phase=%s\n", phase);
	fwrite(snapshot_raw, 1, bytes, stdout);
	printf("COMPRESSED_FRONTEND_END phase=%s\n", phase);
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

	if ((argc != 3 && argc != 6 && argc != 11) ||
	    (argc == 11 && c2_arguments(argc, argv)) ||
	    sscanf(argv[1], "%zu%c", &bytes, &unit) < 1) {
		fprintf(stderr, "usage: swapin SIZE[K|M|G] MEMORY_RECLAIM [compressed TYPE CGROUP]\n");
		return 2;
	}
	if (argc == 6 || argc == 11) {
		char *end;
		long type = strtol(argv[4], &end, 10);
		if (strcmp(argv[3], "compressed") || *end || type < 0 || type > 31 ||
		    strncmp(argv[5], "/sys/fs/cgroup/", 15))
			return 2;
		compressed_mode = true;
		compressed_type = type;
		timing_clock = CLOCK_MONOTONIC_RAW;
		if ((c2_mode && c2_source_readback()) || probe_setup() ||
		    compressed_topology("before") ||
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
	if (madvise(buf, bytes, MADV_NOHUGEPAGE) && c2_mode) {
		puts("SWAPIN_FAIL compressed_target_order");
		return 1;
	}
	fill(buf, pages);
	if (c2_mode && c2_isolate(buf, bytes)) {
		puts("SWAPIN_FAIL compressed_observer_isolation");
		return 1;
	}

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
		if (c2_mode &&
		    (compression_snapshot("after", &stored, &pool, &raw) ||
		     c2_isolation_snapshot("after_measurement", buf, bytes))) {
			puts("SWAPIN_FAIL compressed_final_proof");
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
