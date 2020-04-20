#ifndef LIBEV_SERVER_FLAGCACHE_H
#define LIBEV_SERVER_FLAGCACHE_H

#include <cstdint>
#include <atomic>


class FlagCache {
private:
	uint32_t team_count;
	uint32_t service_count;
	uint32_t round_buckets;
	uint32_t payload_buckets;
	std::atomic_uint *cache = nullptr;

	std::atomic_long cache_hits;
	std::atomic_long cache_misses;
	std::atomic_long cache_fails;

public:
	FlagCache();

	FlagCache(uint32_t team_count, uint32_t service_count);

	~FlagCache();

	void resize(uint32_t team_count, uint32_t service_count);

	void printStats();

	/**
	 *
	 * @param submitting_team
	 * @param team_id
	 * @param expires
	 * @return true is possibly new, false if it was already present there (definitely not new)
	 */
	bool checkFlag(uint16_t submitting_team, uint16_t team_id, uint16_t service_id, uint16_t round, uint16_t payload);

	/**
	 * call this if an already existing entry was not found in the cache before
	 */
	void cacheFailed();

	/**
	 * @return number of flags that were cached
	 */
	long getCacheHits() {
		return cache_hits;
	}

	/**
	 * @return number of flags that were not in cache
	 */
	long getCacheMisses() {
		return cache_misses;
	}

	/**
	 * @return number of flags that were not in cache, but have been already submitted
	 */
	long getCacheFails() {
		return cache_fails;
	}
};

#endif //LIBEV_SERVER_FLAGCACHE_H
