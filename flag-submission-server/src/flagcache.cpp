#include <cstddef>
#include <iostream>
#include <string.h>
#include <iomanip>
#include "flagcache.h"

// there are at most 20 flags valid at a given point in time per (service,team,payload). Collision is accceptable, but expensive.
#define FLAGCACHE_DEFAULT_BUCKETS 25
// number of flags that can be distinguished per round. Collision here is acceptable, but expensive.
#define FLAGCACHE_DEFAULT_PAYLOAD_BUCKETS 5


FlagCache::FlagCache() : team_count(0), service_count(0), round_buckets(FLAGCACHE_DEFAULT_BUCKETS + 1),
						 payload_buckets(FLAGCACHE_DEFAULT_PAYLOAD_BUCKETS), cache_hits(0), cache_misses(0), cache_fails(0) {
}

FlagCache::FlagCache(uint32_t team_count, uint32_t service_count) : FlagCache() {
	resize(team_count, service_count);
}

void FlagCache::resize(uint32_t team_count, uint32_t service_count) {
	this->team_count = team_count;
	this->service_count = service_count;
	size_t cache_size = team_count * team_count * service_count * round_buckets * payload_buckets;
	size_t memory_size = cache_size * sizeof(std::atomic_uint);
	std::cout << "Cache memory: " << (memory_size >> 20) << " MB" << std::endl;
	cache = new std::atomic_uint[cache_size];
	bzero(cache, memory_size);
}

FlagCache::~FlagCache() {
	if (cache) {
		printStats();
		delete[] cache;
	}
}

// true = flag is possibly new, false = definitive not new
bool FlagCache::checkFlag(uint16_t submitting_team, uint16_t team_id, uint16_t service_id, uint16_t round,
						  uint16_t payload) {
	// ids are [1..count], we need them [0..count-1]
	submitting_team--;
	team_id--;
	service_id--;
	// check if id in bounds - unsigned comparison ensures -1 is invalid
	if (submitting_team >= team_count || team_id >= team_count || service_id >= service_count)
		return true;

	// index order: cache[submitting_team][service_id][team_id][expires_bucket]
	int round_bucket = round % round_buckets;
	size_t index = submitting_team;
	index = index * service_count + service_id;
	index = index * team_count + team_id;
	index = index * round_buckets + round_bucket;
	index = index * payload_buckets + (payload % payload_buckets);

	// Must be unique. Idea: no collision in the last 16 bits of expires, because that would mean one flag is 18h old.
	unsigned int cache_key = round | payload << 16;

	bool is_new = cache[index].exchange(cache_key) != cache_key;
	(is_new ? cache_misses : cache_hits)++;
	return is_new;
}

void FlagCache::cacheFailed() {
	cache_fails++;
}

void FlagCache::printStats() {
	if (!cache)
		return;
	std::cout << "=== Flag Cache Statistics ===" << std::endl;
	auto t = std::time(nullptr);
	auto tm = *std::localtime(&t);
	std::cout << "At " << std::put_time(&tm, "%d.%m.%Y %H:%M:%S") << std::endl;
	std::cout << cache_hits << " cache hits" << std::endl;
	std::cout << cache_misses << " cache misses" << std::endl;
	std::cout << cache_fails << " cache fails" << std::endl;

	long all_flags = cache_hits + cache_misses + cache_fails;
	if (all_flags > 0) {
		printf("Resubmits: %.1f%%\n", (cache_hits + cache_fails) * 100.0 / all_flags);
	}
	if (cache_hits + cache_fails > 0) {
		printf("Cached resubmits: %.1f%%\n", cache_hits * 100.0 / (cache_hits + cache_fails));
	}
	std::cout << "=============================" << std::endl;
}
