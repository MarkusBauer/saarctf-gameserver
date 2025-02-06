#ifndef FLAG_SUBMISSION_SERVER_STATISTICS_H
#define FLAG_SUBMISSION_SERVER_STATISTICS_H

// echo -e 'statistics connections\nstatistics flags\nstatistics cache' | socat - tcp:localhost:31337

#include <vector>

# define MAX_TEAMS 2048

namespace statistics {

enum FlagState {
	New = 0,
	Old = 1,
	Expired = 2,
	Invalid = 3,
	Nop = 4,
	Own = 5
};

void initStatisticSize(int max_teams);

void countFlag(uint16_t submittingTeam, FlagState state);

void countConnection();

const char *getConnectionFDReport(int current_connection_count);

std::vector<const char *> getFlagReport();

const char *getCacheReport();

}

#endif //FLAG_SUBMISSION_SERVER_STATISTICS_H
