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
#include <time.h>
#include <unistd.h>

#define PAGEMAP_SWAPPED (1ULL << 62)

static long page;

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

	clock_gettime(CLOCK_MONOTONIC, &ts);
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
	unsigned char *map;
	volatile uint64_t sink = 0;
	char *buf, unit = '\0';
	int i;

	if (argc != 3 || sscanf(argv[1], "%zu%c", &bytes, &unit) < 1) {
		fprintf(stderr, "usage: swapin SIZE[K|M|G] MEMORY_RECLAIM\n");
		return 2;
	}
	if (unit == 'G')
		bytes <<= 30;
	else if (unit == 'M')
		bytes <<= 20;
	else if (unit == 'K')
		bytes <<= 10;

	page = sysconf(_SC_PAGESIZE);
	pages = bytes / page;
	if (pages < 2 || bytes % page)
		return 2;
	half = pages / 2;
	buf = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	map = calloc(pages, 1);
	lat_seq = calloc(half, sizeof(*lat_seq));
	lat_rand = calloc(pages - half, sizeof(*lat_rand));
	order = calloc(pages - half, sizeof(*order));
	if (buf == MAP_FAILED || !map || !lat_seq || !lat_rand || !order) {
		perror("alloc");
		return 1;
	}
	madvise(buf, bytes, MADV_NOHUGEPAGE);
	fill(buf, pages);

	/* Reclaim until at least 90% of the region is out, at most 16 tries. */
	for (i = 0; i < 16; i++) {
		reclaim(argv[2], bytes);
		if (swapped(buf, pages, map) * 10 >= pages * 9)
			break;
	}
	printf("SWAPIN_SWAPPED pages=%zu swapped=%zu reclaim_rounds=%d\n",
	       pages, swapped(buf, pages, map), i + 1);
	if (swapped(buf, pages, map) * 10 < pages * 9) {
		printf("SWAPIN_FAIL not_swapped\n");
		return 1;
	}

	for (size_t pg = 0; pg < half; pg++) {
		uint64_t t0, d;

		if (!map[pg])
			continue;
		t0 = now_ns();
		sink += *(volatile uint64_t *)(buf + pg * page);
		d = now_ns() - t0;
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
		t0 = now_ns();
		sink += *(volatile uint64_t *)(buf + pg * page);
		d = now_ns() - t0;
		lat_rand[n_rand++] = d;
		t_rand += d;
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
