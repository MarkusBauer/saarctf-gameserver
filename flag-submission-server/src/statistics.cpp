//
// Created by markus on 05.03.20.
//

#include <cstdlib>
#include <cstdio>
#include <atomic>
#include "statistics.h"
#include "flagchecker.h"
#include <sys/resource.h>
#include <dirent.h>

struct CounterLine {
	std::atomic_long counters[6] = {
			{0},
			{0},
			{0},
			{0},
			{0},
			{0}
	};
};

static std::atomic_long connection_counter(0);
static std::vector<CounterLine> flag_counters(MAX_TEAMS);


void statistics::countFlag(uint16_t submittingTeam, statistics::FlagState state) {
	if (submittingTeam < flag_counters.size())
		flag_counters.at(submittingTeam).counters[state]++;
}

void statistics::countConnection() {
	connection_counter++;
}

static int filecount(const char *dir) {
	DIR *dp;
	dp = opendir(dir);
	if (dp != nullptr) {
		int counter = 0;
		while (readdir(dp))
			counter++;
		closedir(dp);
		return counter - 2; // "." and ".."
	} else {
		perror("Couldn't open the directory");
		return -1;
	}
}

const char *statistics::getConnectionFDReport(int current_connection_count) {
	struct rlimit limits;
	if (getrlimit(RLIMIT_NOFILE, &limits))
		perror("getrlimit");
	auto limit = limits.rlim_max > 0 && (limits.rlim_max < limits.rlim_cur || limits.rlim_cur == 0) ? limits.rlim_max : limits.rlim_cur;
	auto current = filecount("/proc/self/fd/");

	char *buffer = (char *) malloc(56);
	snprintf(buffer, 56, "%d,%ld,%d,%ld\n", current_connection_count, std::atomic_exchange(&connection_counter, 0L), current, limit);
	return buffer;
}

std::vector<const char *> statistics::getFlagReport() {
	std::vector<const char *> result;
	long line[6];

	for (int team_id = 0; team_id < flag_counters.size(); team_id++) {
		bool notzero = false;
		for (int j = 0; j < 6; j++) {
			long c = std::atomic_exchange(&flag_counters[team_id].counters[j], 0L);
			line[j] = c;
			if (c != 0) notzero = true;
		}
		if (notzero) {
			char *buffer = (char *) malloc(128);
			snprintf(buffer, 128, "team%d,%ld,%ld,%ld,%ld,%ld,%ld\n", team_id, line[0], line[1], line[2], line[3], line[4], line[5]);
			result.push_back(buffer);
		}
	}

	return result;
}

const char *statistics::getCacheReport() {
	char *buffer = (char *) malloc(48);
	snprintf(buffer, 48, "%ld,%ld,%ld\n", flag_cache.getCacheHits(), flag_cache.getCacheMisses(), flag_cache.getCacheFails());
	return buffer;
}
