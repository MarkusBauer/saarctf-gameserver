#ifndef FLAG_SUBMISSION_SERVER_REDIS_H
#define FLAG_SUBMISSION_SERVER_REDIS_H


const int STOPPED = 1;
const int SUSPENDED = 2;
const int RUNNING = 3;


class Redis {
public:
	static volatile int current_round;
	static volatile int state;

	static void connect(struct ev_loop *loop);
};


#endif //FLAG_SUBMISSION_SERVER_REDIS_H
