#ifndef FLAG_SUBMISSION_SERVER_PERIODIC_H
#define FLAG_SUBMISSION_SERVER_PERIODIC_H

#include <ev++.h>

class PeriodicMaintenance {
	ev::timer timer;

	static void checkDatabase(ev::timer &w, int revents);

public:
	void connect(struct ev_loop *loop);
};

#endif //FLAG_SUBMISSION_SERVER_PERIODIC_H
