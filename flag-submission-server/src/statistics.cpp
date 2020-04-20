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
	std::atomic_long counters[6];
};

static std::atomic_long connection_counter(0);
static CounterLine *flag_counters;
static int flag_counters_size;


void statistics::initStatisticSize(int max_teams) {
	flag_counters_size = max_teams + 1;
	flag_counters = (CounterLine *) malloc(flag_counters_size * sizeof(CounterLine));
	for (int i = 0; i <= max_teams; i++) {
		for (auto &counter : flag_counters[i].counters) {
			counter = 0;
		}
	}
}

void statistics::countFlag(uint16_t submittingTeam, statistics::FlagState state) {
	flag_counters[submittingTeam].counters[state]++;
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
	sprintf(buffer, "%d,%ld,%d,%ld\n", current_connection_count, std::atomic_exchange(&connection_counter, 0L), current, limit);
	return buffer;
}

std::vector<const char *> statistics::getFlagReport() {
	std::vector<const char *> result;
	long line[6];

	for (int team_id = 0; team_id < flag_counters_size; team_id++) {
		bool notzero = false;
		for (int j = 0; j < 6; j++) {
			long c = std::atomic_exchange(&flag_counters[team_id].counters[j], 0L);
			line[j] = c;
			if (c != 0) notzero = true;
		}
		if (notzero) {
			char *buffer = (char *) malloc(100);
			sprintf(buffer, "team%d,%ld,%ld,%ld,%ld,%ld,%ld\n", team_id, line[0], line[1], line[2], line[3], line[4], line[5]);
			result.push_back(buffer);
		}
	}

	return result;
}

const char *statistics::getCacheReport() {
	char *buffer = (char *) malloc(48);
	sprintf(buffer, "%ld,%ld,%ld\n", flag_cache.getCacheHits(), flag_cache.getCacheMisses(), flag_cache.getCacheFails());
	return buffer;
}
