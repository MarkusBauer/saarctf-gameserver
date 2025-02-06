#include "periodic.h"
#include "database.h"
#include "flagchecker.h"
#include <cstdint>
#include <iostream>

void PeriodicMaintenance::checkDatabase(ev::timer &w, int revents) {
	uint32_t current_max_teams = std::max(max_team_id, (uint32_t) getMaxTeamId() + 1);
	uint32_t current_max_services = std::max(max_service_id, (uint32_t) getMaxServiceId());
	if (current_max_teams > max_team_id || current_max_services > max_service_id) {
		std::cout << "[Teams] Number of teams/services changed" << std::endl;
		initModelSizes(current_max_teams, current_max_services);
	}
}

void PeriodicMaintenance::connect(struct ev_loop *loop) {
	timer.set<checkDatabase>();
	timer.set(60.0, 60.0);
	timer.set(loop);
	timer.start();
}
