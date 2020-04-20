#include <iostream>
#include <ev.h>
#include <unistd.h>
#include <ev++.h>
#include <hiredis/async.h>
#include "redis.h"
#include "hiredis/hiredis.h"
#include "hiredis/async.h"
#include "hiredis/adapters/libev.h"
#include "config.h"
#include "flagchecker.h"

#define CURRENT_STATE_KEY "timing:state"
#define CURRENT_ROUND_KEY "timing:currentRound"


using namespace std;


volatile int Redis::current_round = -1;
volatile int Redis::state = STOPPED;
static ev::timer reconnect_timer;


static void reconnect() {
	reconnect_timer.set(3);
	reconnect_timer.start();
}

static void setCurrentRound(const char *round) {
	int newRound = atoi(round);
	int oldRound = Redis::current_round;
	if (newRound != oldRound) {
		Redis::current_round = newRound;
		cout << "[Redis] Current round: " << Redis::current_round << endl;
		printFlagStatsForRound(oldRound);
	}
}

static void setCurrentState(const char *state_chars) {
	string state(state_chars);
	int new_state;
	if (state == "STOPPED") {
		new_state = STOPPED;
	} else if (state == "SUSPENDED") {
		new_state = SUSPENDED;
	} else if (state == "RUNNING") {
		new_state = RUNNING;
	} else {
		cerr << "[Redis] Invalid state: " << state_chars << endl;
		return;
	}

	if (new_state != Redis::state) {
		Redis::state = new_state;
		cout << "[Redis] CTF State: ";
		switch (Redis::state) {
			case STOPPED:
				cout << "Stopped" << endl;
				break;
			case SUSPENDED:
				cout << "Suspended" << endl;
				break;
			case RUNNING:
				cout << "Running" << endl;
				break;
			default:
				break;
		}
	}
}


static void onHandleMessage(redisAsyncContext *context, void *r, void *privdata) {
	if (r == nullptr) {
		cerr << "[Redis] Received invalid message." << endl;
		return;
	}
	auto reply = (redisReply *) r;

	if (reply->type == REDIS_REPLY_ARRAY) {
		if (string(reply->element[0]->str) == "message") {
			auto callback = (void (*)(const char *)) privdata;
			callback(reply->element[2]->str);
		}
	} else {
		cerr << "[Redis] Strange subscription message type: " << reply->type << endl;
	}
}


static void onGetKey(redisAsyncContext *context, void *r, void *privdata) {
	if (r == nullptr) {
		cerr << "[Redis] Could not retrieve key! " << context->errstr << endl;
		throw exception();
	}

	auto reply = (redisReply *) r;
	if (reply->type == REDIS_REPLY_ERROR) {
		cerr << "[Redis] Error: " << reply->str << " " << context->errstr << endl;
	} else if (reply->type == REDIS_REPLY_STRING) {
		auto callback = (void (*)(const char *)) privdata;
		callback(reply->str);
	} else if (reply->type == REDIS_REPLY_NIL) {
		cout << "[Redis] Key missing. Did the game already start?" << endl;
	} else {
		cout << "[Redis] Unexpected " << reply->type << endl;
	}
}


static void onDatabaseSelected(redisAsyncContext *context, void *r, void *privdata) {
	if (r == nullptr) {
		cerr << "[Redis] Could not select database! " << context->errstr << endl;
		throw exception();
	}

	auto reply = (redisReply *) r;
	if (reply->type == REDIS_REPLY_ERROR) {
		cerr << "[Redis] Error in select: " << reply->str << " " << context->errstr << endl;
		throw exception();
	}

	redisAsyncCommand(context, nullptr, nullptr, "CLIENT SETNAME submission_server");
	redisAsyncCommand(context, onGetKey, (void *) setCurrentState, "GET " CURRENT_STATE_KEY);
	redisAsyncCommand(context, onGetKey, (void *) setCurrentRound, "GET " CURRENT_ROUND_KEY);
	redisAsyncCommand(context, onHandleMessage, (void *) setCurrentState, "SUBSCRIBE " CURRENT_STATE_KEY);
	redisAsyncCommand(context, onHandleMessage, (void *) setCurrentRound, "SUBSCRIBE " CURRENT_ROUND_KEY);
}

static void onAuthenticated(redisAsyncContext *context, void *r, void *privdata) {
	if (r == nullptr && privdata == nullptr) {
		cerr << "[Redis] Could not authenticate! " << context->errstr << endl;
		throw exception();
	}
	if (r != nullptr) {
		auto reply = (redisReply *) r;
		if (reply->type == REDIS_REPLY_ERROR) {
			cerr << "[Redis] Error in auth: " << reply->str << " " << context->errstr << endl;
			throw exception();
		}
	}

	string db = to_string(Config::getRedisDB());
	if (redisAsyncCommand(context, onDatabaseSelected, nullptr, "SELECT %s", db.c_str()) != REDIS_OK) {
		cerr << "[Redis] Could not send USE command" << endl;
		throw exception();
	}
}

static void onConnect(redisAsyncContext *context, int status) {
	if (status != REDIS_OK) {
		cerr << "[Redis] Could not connect to database" << endl;
		reconnect();
	} else {
		// Authenticate iff a password is given
		if (Config::getRedisPassword().empty()) {
			onAuthenticated(context, nullptr, &Config::flagRoundsValid);
		} else {
			if (redisAsyncCommand(context, onAuthenticated, nullptr, "AUTH %s", Config::getRedisPassword().c_str()) != REDIS_OK) {
				cerr << "[Redis] Could not send authentication" << endl;
			}
		}
	}
}

static void onDisconnect(const redisAsyncContext *context, int status) {
	if (status == REDIS_OK) {
		cerr << "[Redis] Disconnected" << endl;
	} else {
		cerr << "[Redis] Disconnected: " << context->errstr << endl;
		reconnect();
	}
}

static void onReconnect(ev::timer &w, int revents) {
	cerr << "[Redis] Reconnecting...";

	// Create a new connection
	string host = Config::getRedisHost();
	redisAsyncContext *context = redisAsyncConnect(host.c_str(), Config::getRedisPort());
	if (context->err) {
		cerr << "  (failed) " << context->errstr << endl;
		reconnect();
		redisAsyncFree(context);
	} else {
		cerr << "  (ok)" << endl;
		redisLibevAttach(w.loop, context);
		auto e = (struct redisLibevEvents *) context->ev.data;
		ev_set_priority(&e->rev, EV_MAXPRI);
		ev_set_priority(&e->wev, EV_MAXPRI);
		redisAsyncSetDisconnectCallback(context, onDisconnect);
		redisAsyncSetConnectCallback(context, reinterpret_cast<void (*)(const redisAsyncContext *, int)>(onConnect));
	}
}

void Redis::connect(struct ev_loop *loop) {
	// Init reconnect timer
	reconnect_timer.set<onReconnect>();
	reconnect_timer.set(3);
	reconnect_timer.set(loop);

	// Initial connection
	string host = Config::getRedisHost();
	redisAsyncContext *context = redisAsyncConnect(host.c_str(), Config::getRedisPort());
	if (context->err) {
		cerr << "[Redis] Connection error: " << context->errstr << endl;
		throw exception();
	}

	redisLibevAttach(loop, context);
	auto e = (struct redisLibevEvents *) context->ev.data;
	ev_set_priority(&e->rev, EV_MAXPRI);
	ev_set_priority(&e->wev, EV_MAXPRI);
	redisAsyncSetDisconnectCallback(context, onDisconnect);
	redisAsyncSetConnectCallback(context, reinterpret_cast<void (*)(const redisAsyncContext *, int)>(onConnect));
}
