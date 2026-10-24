// SPDX-License-Identifier: GPL-2.0-only
/*
 * Swap slot lifetime churn: each round forks workers that fill anonymous
 * memory beyond their memcg limit, so it is swapped out and written back,
 * and then all exit together.  Every slot is freed at once while zswap
 * writeback may still hold copied entries, and on xswap the free tail is
 * unmapped behind them.  Even-numbered workers verify all their data
 * before exiting; the others exit without touching it again.  Rounds
 * repeat for a fixed time.
 *
 * usage: churn <bytes per worker, e.g. 512M> <workers> <seconds>
 */
#define _GNU_SOURCE
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static long page;

static uint64_t word(uint64_t salt, size_t pg, size_t i)
{
	uint64_t x = (salt + 1) * 0xd6e8feb86659fd93ULL +
		     (pg + 1) * 0x9e3779b97f4a7c15ULL + i * 0xbf58476d1ce4e5b9ULL;

	x ^= x >> 31;
	return x * 0x94d049bb133111ebULL;
}

static size_t parse_size(const char *s)
{
	char *end;
	size_t n = strtoull(s, &end, 10);

	switch (*end) {
	case 'G': n <<= 10; /* fall through */
	case 'M': n <<= 10; /* fall through */
	case 'K': n <<= 10; end++; break;
	}
	return *end ? 0 : n;
}

static double now(void)
{
	struct timespec ts;

	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec / 1e9;
}

static int worker(size_t bytes, uint64_t salt, int verify)
{
	size_t pages = bytes / page, words = page / sizeof(uint64_t);
	char *buf = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
			 MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);

	if (buf == MAP_FAILED)
		return 2;
	/* Half random, half zero: compressible, never same-filled. */
	for (size_t pg = 0; pg < pages; pg++) {
		uint64_t *p = (uint64_t *)(buf + pg * page);

		for (size_t i = 0; i < words; i++)
			p[i] = i < words / 2 ? word(salt, pg, i) : 0;
	}
	if (!verify)
		return 0;
	for (size_t pg = 0; pg < pages; pg++) {
		uint64_t *p = (uint64_t *)(buf + pg * page);

		for (size_t i = 0; i < words; i++) {
			if (p[i] != (i < words / 2 ? word(salt, pg, i) : 0)) {
				printf("CHURN_MISMATCH salt=%llu page=%zu word=%zu\n",
				       (unsigned long long)salt, pg, i);
				return 3;
			}
		}
	}
	return 0;
}

int main(int argc, char **argv)
{
	size_t bytes;
	int workers, seconds, rounds = 0, verified = 0;
	double start;

	page = sysconf(_SC_PAGESIZE);
	if (argc != 4 || !(bytes = parse_size(argv[1])) ||
	    (workers = atoi(argv[2])) < 1 || (seconds = atoi(argv[3])) < 1) {
		fprintf(stderr, "usage: churn <bytes> <workers> <seconds>\n");
		return 1;
	}
	setvbuf(stdout, NULL, _IOLBF, 0);
	start = now();
	while (now() - start < seconds) {
		for (int w = 0; w < workers; w++) {
			pid_t pid = fork();

			if (pid < 0) {
				printf("CHURN_FAIL fork round=%d\n", rounds);
				return 1;
			}
			if (!pid)
				_exit(worker(bytes, (uint64_t)rounds << 16 | w,
					     !(w % 2)));
		}
		for (int w = 0; w < workers; w++) {
			int status;

			if (wait(&status) < 0 || !WIFEXITED(status) ||
			    WEXITSTATUS(status)) {
				printf("CHURN_FAIL round=%d status=%d\n", rounds, status);
				return 1;
			}
		}
		verified += (workers + 1) / 2;
		rounds++;
		printf("CHURN_ROUND %d t=%.1f\n", rounds, now() - start);
	}
	printf("CHURN_PASS rounds=%d workers=%d bytes=%zu verified_workers=%d\n",
	       rounds, workers, bytes, verified);
	return 0;
}
