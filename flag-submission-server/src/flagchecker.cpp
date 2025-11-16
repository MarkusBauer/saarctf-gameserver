#include <openssl/hmac.h>
#include <cstring>
#include <iostream>
#include <arpa/inet.h>
#include "flagchecker.h"
#include "database.h"
#include "config.h"
#include "libraries/base64.h"
#include "redis.h"
#include "statistics.h"
#include "string_pool.h"


// valid team ids: [1 .. max_team_id]
uint32_t max_team_id = 255;
// valid service ids: [1 .. max_service_id]
uint32_t max_service_id = 10;

FlagCache flag_cache;


/**
 * Might be called multiple times if services or teams are added.
 * Each invocation resets the cache.
 * @param _max_team_id
 * @param _max_service_id
 */
void initModelSizes(uint32_t _max_team_id, uint32_t _max_service_id) {
	max_team_id = _max_team_id;
	max_service_id = _max_service_id;
	flag_cache.resize(max_team_id, max_service_id);
	std::cout << "Handling at most " << max_team_id << " teams and " << max_service_id << " services." << std::endl;
}


static void print_flag(FlagFormat &flag) {
	printf("Flag: [team=%hu, service=%hu, round=%hu, payload=%hu]\n", flag.team_id, flag.service_id, flag.round, flag.payload);
}


/**
 * Parses an IP address and returns the team id it belongs to
 * @param addr
 * @return
 */
static inline uint16_t get_team_id_from_ip(struct sockaddr_in &addr) {
	// "wrong" byte order: 127.0.0.1 = 0x0100007f
	uint32_t ip = addr.sin_addr.s_addr;
	auto ip0 = (uint8_t) ((ip >> 0u) & 0xffu);
	auto ip1 = (uint8_t) ((ip >> 8u) & 0xffu);
	auto ip2 = (uint8_t) ((ip >> 16u) & 0xffu);
	auto ip3 = (uint8_t) ((ip >> 24u) & 0xffu);
	uint16_t team_id = Config::getTeamIdFromIp(ip0, ip1, ip2, ip3);
	return team_id ? team_id : (char) 1; // 127.0.0.1 is team "1"
}

static inline bool is_test_flag(const FlagFormat &flag);
static const char* answer_test_flag(const FlagFormat &flag, uint16_t submitting_team);


/**
 * Checks if a flag is valid or not
 * @param flag buffer containing the flag
 * @param len length in bytes
 * @param addr ip address of the submitter
 * @return a string constant that should be sent back
 */
const char *progress_flag(const char *flag, int len, struct sockaddr_in *addr, uint16_t *team_id_cache) {
	// rtrim
	while (len > 0 && flag[len - 1] <= ' ') len--;

	// flag present?
	if (len <= 0) return "";

	// check length
	if (len != FLAG_LENGTH_FULL) return "[ERR] Wrong length\n";

	// check format (SAAR{...})
	if (memcmp(flag, Config::flagPrefix.c_str(), Config::flagPrefix.size()) != 0 ||
		flag[Config::flagPrefix.size()] != '{' ||
		flag[FLAG_LENGTH_FULL - 1] != '}') {
		return "[ERR] Invalid flag (wrong format)\n";
	}

	// Base64 decode
	FlagFormat binary_flag;
	if (base64_decode((unsigned char *) &flag[5], FLAG_LENGTH_B64, (unsigned char *) &binary_flag) != sizeof binary_flag) {
		return "[ERR] Invalid flag (format)\n";
	}

	#ifdef CHECK_STATE
	if (Redis::state != RUNNING && !is_test_flag(binary_flag)) {
		return "[OFFLINE] CTF not running\n";
	}
	#endif

	// print_flag(binary_flag);

	// check submitting team (own team)
	uint16_t this_team;
	if (team_id_cache) {
		this_team = *team_id_cache;
		if (this_team == 0xffff) {
			*team_id_cache = this_team = get_team_id_from_ip(*addr);
		}
	} else {
		this_team = get_team_id_from_ip(*addr);
	}
	if (this_team > max_team_id || this_team == 0) {
		char buffer[32];
		inet_ntop(AF_INET, &addr, buffer, sizeof(buffer));
		printf("Got connection from invalid IP: %s\n", buffer);
		if (is_test_flag(binary_flag)) {
			this_team = 0xffff;
		} else {
			return "[ERR] Invalid source IP\n";
		}
	}

	if (!is_test_flag(binary_flag)) {
		// Check service
		if (binary_flag.service_id > max_service_id) {
			statistics::countFlag(this_team, statistics::FlagState::Invalid);
			return "[ERR] Invalid flag (service)\n";
		}

		// check team is valid
		if (binary_flag.team_id > max_team_id) {
			statistics::countFlag(this_team, statistics::FlagState::Invalid);
			return "[ERR] Invalid flag (team)\n";
		}
		// check NOP team / test runs (with round < 0)
		if (Config::nopTeamId && binary_flag.team_id == Config::nopTeamId) {
			statistics::countFlag(this_team, statistics::FlagState::Nop);
			return "[ERR] Can't submit flag from NOP team\n";
		}
		if (binary_flag.round > 0x7fff) {
			statistics::countFlag(this_team, statistics::FlagState::Invalid);
			return "[ERR] Invalid flag (issued for testing purposes)\n";
		}
		// Check
		if (this_team == binary_flag.team_id) {
			statistics::countFlag(this_team, statistics::FlagState::Own);
			return "[ERR] This is your own flag\n";
		}
		if (Config::nopTeamId && this_team == Config::nopTeamId) {
			return "[ERR] Can't submit flag as NOP team\n";
		}

		// check if flag is expired
		#ifdef CHECK_EXPIRED
		// <round issued> + <number of valid rounds> is the last round a flag is valid
		if (binary_flag.round + Config::flagRoundsValid < Redis::current_round) {
			statistics::countFlag(this_team, statistics::FlagState::Expired);
			return "[ERR] Expired\n";
		}
		#endif
	}

	// check MAC
#ifdef CHECK_MAC
	if (!verify_hmac(&binary_flag, &binary_flag.mac, binary_flag.mac)) {
		statistics::countFlag(this_team, statistics::FlagState::Invalid);
		return "[ERR] Invalid flag\n";
	}
#else
	volatile bool x = verify_hmac(&binary_flag, &binary_flag.mac, binary_flag.mac);
#endif

	if (is_test_flag(binary_flag)) {
		return answer_test_flag(binary_flag, this_team);
	}

	// Check if flag is a resubmit
#ifdef CHECK_CACHE
	if (!flag_cache.checkFlag(this_team, binary_flag.team_id, binary_flag.service_id, binary_flag.round,
							  binary_flag.payload)) {
		statistics::countFlag(this_team, statistics::FlagState::Old);
		return "[ERR] Already submitted\n";
	}
#endif

	int submit_result = submit_flag(this_team, binary_flag);
	if (submit_result < 0) {
		return "[ERR] Internal error (database)\n";
	} else if (submit_result == 0) {
#ifdef CHECK_CACHE
		flag_cache.cacheFailed();
#endif
		statistics::countFlag(this_team, statistics::FlagState::Old);
		return "[ERR] Already submitted\n";
	}

	statistics::countFlag(this_team, statistics::FlagState::New);
	return "[OK]\n";
}

static EVP_MAC *mac = EVP_MAC_fetch(nullptr, "HMAC", nullptr);
static char sha256[7] = "SHA256";

bool verify_hmac(void *data_start, void *data_end, const char *hmac) {
	EVP_MAC_CTX *ctx = EVP_MAC_CTX_new(mac);
	OSSL_PARAM params[2];
	params[0] = OSSL_PARAM_construct_utf8_string("digest", sha256, 0);
	params[1] = OSSL_PARAM_construct_end();
	EVP_MAC_init(ctx, Config::hmac_secret_key, sizeof Config::hmac_secret_key, params);

	size_t length = ((char *) data_end) - ((char *) data_start);
	EVP_MAC_update(ctx, (unsigned char *) data_start, length);

	unsigned char buffer[32];
	size_t mdlen;
	EVP_MAC_final(ctx, buffer, &mdlen, sizeof buffer);
	EVP_MAC_CTX_free(ctx);

	return memcmp(hmac, buffer, sizeof FlagFormat::mac) == 0;
}


void create_hmac(void *data_start, void *data_end, char *hmac_out) {
	EVP_MAC_CTX *ctx = EVP_MAC_CTX_new(mac);
	OSSL_PARAM params[2];
	params[0] = OSSL_PARAM_construct_utf8_string("digest", sha256, 0);
	params[1] = OSSL_PARAM_construct_end();
	EVP_MAC_init(ctx, Config::hmac_secret_key, sizeof Config::hmac_secret_key, params);

	size_t length = ((char *) data_end) - ((char *) data_start);
	EVP_MAC_update(ctx, (unsigned char *) data_start, length);

	unsigned char buffer[32];
	size_t mdlen;
	EVP_MAC_final(ctx, buffer, &mdlen, sizeof buffer);
	EVP_MAC_CTX_free(ctx);

	memcpy(hmac_out, buffer, sizeof FlagFormat::mac);
}


static long flagsScoredLastRound = 0;
static long flagsResubmitLastRound = 0;

void printFlagStatsForRound(int round) {
	long flagsScored = flag_cache.getCacheMisses() - flag_cache.getCacheFails();
	long flagsResubmit = flag_cache.getCacheHits() + flag_cache.getCacheFails();
	long flagsScoredThisRound = flagsScored - flagsScoredLastRound;
	long flagsResubmitThisRound = flagsResubmit - flagsResubmitLastRound;

	if (round > 0) {
		// std::cout << "[Stats] In round " << round << ", " << flagsScoredThisRound << " flags were submitted (" << flagsResubmitThisRound << " resubmits)" << std::endl;
		printf("[Stats] In round %d, %'ld flags were submitted (%'ld resubmits)\n", round, flagsScoredThisRound,
			   flagsResubmitThisRound);
	}

	flagsScoredLastRound = flagsScored;
	flagsResubmitLastRound = flagsResubmit;
}

void printCacheStats() {
	flag_cache.printStats();
}


static StringPool dynamicAnswers;

static inline bool is_test_flag(const FlagFormat &flag) {
	return flag.service_id >= FLAG_SERVICE_CHECK_LIMIT;
}

static const char* answer_test_flag(const FlagFormat &flag, uint16_t submitting_team) {
	if (flag.service_id == FLAG_SERVICE_STATUSCHECK) {
		return dynamicAnswers.get(
			"[OK] Status check passed. submitter=%d max_team_id=%d max_service_id=%d online_status=%d tick=%d nop_team_id=%d\n",
			submitting_team, max_team_id, max_service_id, Redis::state, Redis::current_round, Config::nopTeamId
		);
	}
	if (flag.service_id == FLAG_SERVICE_TEAMCHECK) {
		return dynamicAnswers.get(
			"[OK] You are team %d\n",
			submitting_team, max_team_id, max_service_id, Redis::state, Redis::current_round, Config::nopTeamId
		);
	}
	return "[ERR] Invalid flag (service)\n";
}
