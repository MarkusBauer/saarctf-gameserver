#ifndef LIBEV_SERVER_FLAGCHECKER_H
#define LIBEV_SERVER_FLAGCHECKER_H


#include <cstdint>
#include <netinet/in.h>
#include "flagcache.h"


// Enable/disable checking steps (for benchmark)
#define CHECK_MAC
#define CHECK_EXPIRED
#define CHECK_CACHE
#define CHECK_STATE


// FORMAT: SAAR{QUFBQUFBQUFCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkFB}

// Binary flag format (after b64 decode): 39 bytes
// = 56 bytes base64
// = 62 bytes including SAAR{}
// Truncated format: 24bytes => 32chars => 38chars total
struct __attribute__((__packed__)) FlagFormat {
	uint16_t round;
	uint16_t team_id;
	uint16_t service_id;
	uint16_t payload;
	char mac[16]; // out of 32
};

#define FLAG_LENGTH_B64 32
#define FLAG_LENGTH_FULL 38
#define FLAG_SERVICE_CHECK_LIMIT 0xfffe
#define FLAG_SERVICE_TEAMCHECK 0xfffe
#define FLAG_SERVICE_STATUSCHECK 0xffff


/*
 * If you want to change the flag format:
 * - Change the struct above
 * - Ensure mac is the last field
 * - Change the length constants
 */


// valid team ids: [1 .. max_team_id]
extern uint32_t max_team_id;
// valid service ids: [1 .. max_service_id]
extern uint32_t max_service_id;


void initModelSizes(uint32_t _max_team_id, uint32_t _max_service_id);

const char *progress_flag(const char *flag, int len, struct sockaddr_in *addr, uint16_t *team_id_cache);

bool verify_hmac(void *data_start, void *data_end, const char *hmac);

void create_hmac(void *data_start, void *data_end, char *hmac_out);

void printFlagStatsForRound(int round);

void printCacheStats();

extern FlagCache flag_cache;

#endif //LIBEV_SERVER_FLAGCHECKER_H
