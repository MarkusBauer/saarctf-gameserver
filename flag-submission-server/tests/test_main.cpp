#define CATCH_CONFIG_MAIN

#include <thread>
#include <chrono>
#include "catch1.hpp"
#include "../src/config.h"

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
	cerr << "Time for " << cnt << " conversions: " << dt.count() << " µs" << endl;
	cerr << " => " << dt.count() * 1.0 / cnt << " µs/conversion (single-threaded)" << endl;
	cerr << " => " << std::fixed << std::setprecision(1) << cnt * 1000000.0 / dt.count() << " conversions/sec (single-threaded)" << endl;
}
