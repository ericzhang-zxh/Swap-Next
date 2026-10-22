// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/swap.h>
#include <sys/wait.h>
#include <unistd.h>

/* Frozen x86 guest ABI: 4 KiB pages and 256 slots per swap cluster. */
#define PAGE_BYTES 4096UL
#define WORDS_PER_PAGE (PAGE_BYTES / sizeof(uint64_t))
#define CLUSTER_SLOTS 256UL
#define FILLER_BYTES (1024UL * 1024 * 1024)
#define ANCHOR_BYTES (64UL * 1024 * 1024)
#define ANCHOR_MIN_SWAPPED 1000UL
#define ANCHOR_MIN_CLUSTER 512UL
#define ANCHOR_SALT UINT64_C(0x71ab934fe02d6805)
#define COW_MASK UINT64_C(0x123456)

static int xswap_type;
static char debugpath[128];
static const char * const fields[] = {
	"clusters_max", "clusters_mapped", "usage_pages", "tail_free",
	"grows", "shrinks", "clusters_nonempty", "clusters_free",
	"highest_nonempty_plus1", "highest_blocker_plus1", "cache_only_pages",
	"referenced_pages", "highest_cache_only_plus1",
	"highest_referenced_plus1", "cache_only_clusters"
};

struct placement {
	size_t swapped;
	uint64_t min_cluster;
	uint64_t max_cluster;
};

static void fail(const char *why)
{
	fprintf(stderr, "XSWAP_FAIL hole_probe %s\n", why);
	exit(EXIT_FAILURE);
}

static uint64_t pattern(size_t word, uint64_t salt)
{
	return (((word / WORDS_PER_PAGE) * 8 + word % 8) *
		UINT64_C(0x9e3779b97f4a7c15)) ^ salt;
}

static uint64_t *allocate(size_t bytes, uint64_t salt)
{
	uint64_t *data = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
			      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	size_t i;

	if (data == MAP_FAILED)
		fail("mmap");
	for (i = 0; i < bytes / sizeof(*data); i++)
		data[i] = pattern(i, salt);
	return data;
}

static void verify(const uint64_t *data, size_t bytes, uint64_t salt)
{
	const volatile uint64_t *words = data;
	size_t i;

	for (i = 0; i < bytes / sizeof(*data); i++)
		if (words[i] != pattern(i, salt))
			fail("data_mismatch");
}

static void metadata(const char *phase)
{
	uint64_t values[sizeof(fields) / sizeof(fields[0])] = { 0 };
	unsigned int seen = 0;
	char line[256], name[80], number[80], extra;
	FILE *stream = fopen(debugpath, "r");
	size_t i;

	if (!stream)
		fail("debugfs_open");
	while (fgets(line, sizeof(line), stream)) {
		char *end;
		unsigned long long value;

		if (sscanf(line, "%79s %79s %c", name, number, &extra) != 2 ||
		    number[0] < '0' || number[0] > '9')
			fail("debugfs_format");
		errno = 0;
		value = strtoull(number, &end, 10);
		if (errno || *end)
			fail("debugfs_value");
		for (i = 0; i < sizeof(fields) / sizeof(fields[0]); i++)
			if (!strcmp(name, fields[i]))
				break;
		if (i == sizeof(fields) / sizeof(fields[0]) || (seen & (1U << i)))
			fail("debugfs_field");
		seen |= 1U << i;
		values[i] = value;
	}
	if (ferror(stream) || fclose(stream))
		fail("debugfs_read");
	if (seen != (1U << (sizeof(fields) / sizeof(fields[0]))) - 1)
		fail("debugfs_missing_field");
	printf("META_BEGIN %s\n", phase);
	for (i = 0; i < sizeof(fields) / sizeof(fields[0]); i++)
		printf("%s %" PRIu64 "\n", fields[i], values[i]);
	puts("META_END");
}

static struct placement inspect(const uint64_t *data, size_t bytes,
				const char *label, int cycle)
{
	struct placement result = { .min_cluster = UINT64_MAX };
	int fd = open("/proc/self/pagemap", O_RDONLY);
	size_t page;

	if (fd < 0)
		fail("pagemap_open");
	for (page = 0; page < bytes / PAGE_BYTES; page++) {
		uint64_t pte, offset, cluster;
		off_t position = ((uintptr_t)data / PAGE_BYTES + page) * sizeof(pte);

		if (pread(fd, &pte, sizeof(pte), position) != sizeof(pte))
			fail("pagemap_read");
		if (!(pte & (UINT64_C(1) << 62))) {
			if (!(pte & (UINT64_C(1) << 63)))
				fail("missing_populated_page");
			continue;
		}
		if (pte & (UINT64_C(1) << 63))
			fail("present_and_swapped");
		if ((pte & 31) != (uint64_t)xswap_type)
			fail("wrong_swap_type");
		/* pagemap bits 5..54 encode the swap offset, not a PFN. */
		offset = (pte & ((UINT64_C(1) << 55) - 1)) >> 5;
		cluster = offset / CLUSTER_SLOTS;
		result.swapped++;
		if (cluster < result.min_cluster)
			result.min_cluster = cluster;
		if (cluster > result.max_cluster)
			result.max_cluster = cluster;
	}
	if (close(fd))
		fail("pagemap_close");
	printf("PLACEMENT %s cycle=%d swapped=%zu total=%zu min_cluster=%" PRIu64
	       " max_cluster=%" PRIu64 "\n", label, cycle, result.swapped,
	       bytes / PAGE_BYTES, result.swapped ? result.min_cluster : 0,
	       result.max_cluster);
	return result;
}

static void pageout(uint64_t *data, size_t bytes)
{
	if (madvise(data, bytes, MADV_PAGEOUT))
		fail("madvise_pageout");
	if (sleep(2))
		fail("pageout_wait_interrupted");
}

static void check_anchor(const uint64_t *anchor, const char *label, int cycle)
{
	struct placement placement = inspect(anchor, ANCHOR_BYTES, label, cycle);

	if (placement.swapped < ANCHOR_MIN_SWAPPED ||
	    placement.min_cluster < ANCHOR_MIN_CLUSTER)
		fail("high_live_anchor_prerequisite");
}

int main(int argc, char **argv)
{
	uint64_t *anchor = NULL;
	char *end, phase[80], value[16];
	long type;
	int cycle, status, destroy, len;
	pid_t child;
	struct placement placement;

	setvbuf(stdout, NULL, _IOLBF, 0);
	if (argc != 2 || !argv[1][0])
		fail("expected_xswap_type_argument");
	errno = 0;
	type = strtol(argv[1], &end, 10);
	if (errno || *end || type < 0 || type > 31)
		fail("invalid_xswap_type");
	if (sysconf(_SC_PAGESIZE) != PAGE_BYTES || sizeof(void *) != 8)
		fail("requires_64bit_4k_guest");
	xswap_type = type;
	snprintf(debugpath, sizeof(debugpath), "/sys/kernel/debug/xswap/type%d", xswap_type);
	metadata("before");
	for (cycle = 0; cycle < 3; cycle++) {
		uint64_t salt = UINT64_C(0xa5a5a5a5a5a5a5a5) ^ (uint64_t)cycle;
		uint64_t *filler;

		printf("HOLE_CYCLE_BEGIN %d\n", cycle);
		filler = allocate(FILLER_BYTES, salt);
		pageout(filler, FILLER_BYTES);
		placement = inspect(filler, FILLER_BYTES, "filler_swapout", cycle);
		if (placement.swapped < (FILLER_BYTES / PAGE_BYTES) * 3 / 4)
			fail("filler_75percent_swapout_prerequisite");
		snprintf(phase, sizeof(phase), "cycle%d_filler_swapped", cycle);
		metadata(phase);
		if (cycle == 0) {
			anchor = allocate(ANCHOR_BYTES, ANCHOR_SALT);
			pageout(anchor, ANCHOR_BYTES);
			check_anchor(anchor, "anchor_initial", cycle);
			metadata("anchor_high_placement");
		} else {
			check_anchor(anchor, "anchor_after_filler_swapout", cycle);
		}
		verify(filler, FILLER_BYTES, salt);
		printf("FILLER_DATA_PASS %d\n", cycle);
		if (munmap(filler, FILLER_BYTES))
			fail("filler_munmap");
		snprintf(phase, sizeof(phase), "cycle%d_after_unmap", cycle);
		metadata(phase);
		check_anchor(anchor, "anchor_after_unmap", cycle);
		if (sleep(2))
			fail("settle_interrupted");
		snprintf(phase, sizeof(phase), "cycle%d_after_settle", cycle);
		metadata(phase);
		check_anchor(anchor, "anchor_after_settle", cycle);
		printf("HOLE_CYCLE_PASS %d\n", cycle);
	}
	verify(anchor, ANCHOR_BYTES, ANCHOR_SALT);
	puts("ANCHOR_DATA_PASS");
	child = fork();
	if (child < 0)
		fail("cow_fork");
	if (!child) {
		size_t i;

		anchor[0] ^= COW_MASK;
		for (i = 0; i < ANCHOR_BYTES / sizeof(*anchor); i++)
			if (((volatile uint64_t *)anchor)[i] !=
			    (pattern(i, ANCHOR_SALT) ^ (i == 0 ? COW_MASK : 0)))
				_exit(1);
		_exit(0);
	}
	if (waitpid(child, &status, 0) != child || !WIFEXITED(status) || WEXITSTATUS(status))
		fail("cow_child");
	verify(anchor, ANCHOR_BYTES, ANCHOR_SALT);
	puts("COW_PASS");
	pageout(anchor, ANCHOR_BYTES);
	placement = inspect(anchor, ANCHOR_BYTES, "anchor_before_destroy", 3);
	if (!placement.swapped)
		fail("destroy_requires_live_xswap_ptes");
	printf("DESTROY_LIVE_XSWAP_PTES %zu\n", placement.swapped);
	destroy = open("/sys/kernel/mm/xswap/destroy", O_WRONLY);
	if (destroy < 0)
		fail("destroy_open");
	len = snprintf(value, sizeof(value), "%d\n", xswap_type);
	if (write(destroy, value, len) != len || close(destroy))
		fail("destroy_write");
	verify(anchor, ANCHOR_BYTES, ANCHOR_SALT);
	if (access(debugpath, F_OK) == 0 || errno != ENOENT)
		fail("destroy_debugfs_still_present");
	puts("DESTROY_LIVE_PASS");
	if (swapoff("/dev/vda"))
		fail("swapoff");
	verify(anchor, ANCHOR_BYTES, ANCHOR_SALT);
	puts("SWAPOFF_LIVE_PASS");
	if (munmap(anchor, ANCHOR_BYTES))
		fail("anchor_munmap");
	puts("KERNEL_WORKLOAD_PASS");
	return 0;
}
