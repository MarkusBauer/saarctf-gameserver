#define CATCH_CONFIG_MAIN

#include <thread>
#include <iostream>
#include <chrono>
#include <catch2/catch_test_macros.hpp>
#include <iomanip>
#include "../src/config.h"
#include "../src/flagchecker.h"
#include "../src/libraries/base64.h"

using namespace std;


TEST_CASE("force_the_linker_to_do_its_fucking_job") {
	thread t1;
	t1.joinable();
	printf("%p\n", pthread_create);
}


TEST_CASE("IP to Team ID conversion") {
	auto ts = std::chrono::steady_clock::now();

	Config::load("../tests/testconfig.json");
	for (int team_id = 1; team_id <= 10000; team_id++) {
		for (int last_byte = 0; last_byte < 256; last_byte++) {
			auto result = Config::getTeamIdFromIp(127, team_id / 200, team_id % 200, last_byte);
			if (result != team_id) {
				fprintf(stderr, "Expected team %d but got result %d for IP %d.%d.%d.%d",
						team_id, result, 127, team_id / 200, team_id % 200, last_byte);
			}
			REQUIRE(result == team_id);
		}
	}

	for (int team_id = 1; team_id <= 10000; team_id++) {
		for (int last_byte = 0; last_byte < 256; last_byte++) {
			auto result = Config::getTeamIdFromIp(127, 52 + team_id / 200, team_id % 200, last_byte);
			if (result != team_id) {
				fprintf(stderr, "Expected team %d but got result %d for IP %d.%d.%d.%d",
						team_id, result, 127, 52 + team_id / 200, team_id % 200, last_byte);
			}
			REQUIRE(result == team_id);
		}
	}

	auto dt = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - ts);
	auto cnt = 20000 * 256;
	std::cerr << "Time for " << cnt << " conversions: " << dt.count() << " µs" << endl;
	std::cerr << " => " << dt.count() * 1.0 / cnt << " µs/conversion (single-threaded)" << endl;
	std::cerr << " => " << std::fixed << std::setprecision(1) << cnt * 1000000.0 / dt.count() << " conversions/sec (single-threaded)" << endl;
}


TEST_CASE("Check Flag Parser") {
	for (int i = 0; i < sizeof Config::hmac_secret_key; i++)
		Config::hmac_secret_key[i] = 'a';

	SECTION("A simple Flag") {
		const char *flag = "SAAR{OQUHAAwAAAAlt3tF4y_TgZlNX2Yi4hw9}";  // service 12 team 7 tick 1337 payload 0
		FlagFormat binary_flag;
		auto decodeSize = base64_decode((unsigned char *) &flag[5], FLAG_LENGTH_B64, (unsigned char *) &binary_flag);
		REQUIRE(decodeSize == sizeof binary_flag);
		REQUIRE(binary_flag.service_id == 12);
		REQUIRE(binary_flag.team_id == 7);
		REQUIRE(binary_flag.round == 1337);
		REQUIRE(binary_flag.payload == 0);
		REQUIRE(verify_hmac(&binary_flag, &binary_flag.mac, binary_flag.mac));
	}

	SECTION("Negative Numbers / Potential Overflows") {
		const char *flag = "SAAR{x_qtrZWVEQBoxEDkuVt8YreJb7pBW_JH}";  // service 0x9595 team 0xadad tick -1337 payload 17
		FlagFormat binary_flag;
		auto decodeSize = base64_decode((unsigned char *) &flag[5], FLAG_LENGTH_B64, (unsigned char *) &binary_flag);
		REQUIRE(decodeSize == sizeof binary_flag);
		REQUIRE(binary_flag.service_id == 0x9595);
		REQUIRE(binary_flag.team_id == 0xadad);
		REQUIRE(binary_flag.round == (uint16_t) -1337);
		REQUIRE(binary_flag.payload == 17);
		REQUIRE(verify_hmac(&binary_flag, &binary_flag.mac, binary_flag.mac));
	}

	SECTION("Invalid Flag") {
		const char *flag = "SAAR{x_qtrZWVEQBoxEDkuVt8YreJb7pBW_XX}";  // service 0x9595 team 0xadad tick -1337 payload 17
		FlagFormat binary_flag;
		auto decodeSize = base64_decode((unsigned char *) &flag[5], FLAG_LENGTH_B64, (unsigned char *) &binary_flag);
		REQUIRE(decodeSize == sizeof binary_flag);
		REQUIRE(binary_flag.service_id == 0x9595);
		REQUIRE(binary_flag.team_id == 0xadad);
		REQUIRE(binary_flag.round == (uint16_t) -1337);
		REQUIRE(binary_flag.payload == 17);
		REQUIRE(!verify_hmac(&binary_flag, &binary_flag.mac, binary_flag.mac));
	}
}


TEST_CASE("Parse (legacy) Configs") {
	SECTION("testconfig.json") {
		Config::load("../tests/testconfig.json");
		REQUIRE(Config::nopTeamId == 1);
		REQUIRE(Config::flagRoundsValid == 10);
	}

	SECTION("testconfig2.json") {
		Config::load("../tests/testconfig2.json");
		REQUIRE(Config::nopTeamId == 2);
		REQUIRE(Config::flagRoundsValid == 20);
	}

	SECTION("testconfig3.json") {
		Config::load("../tests/testconfig3.json");
		REQUIRE(Config::nopTeamId == 2);
		REQUIRE(Config::flagRoundsValid == 20);
	}
}
