#ifndef LIBEV_SERVER_WORKERPOOL_H
#define LIBEV_SERVER_WORKERPOOL_H


#include <ev++.h>
#include <vector>
#include <thread>
#include <queue>
#include <mutex>
#include <atomic>
#include <functional>


/**
 * A thread running an libev eventloop.
 * Use invoke() to push functions to the eventloop (that can register additional handlers)
 */
class Worker {
	friend class WorkerPool;
public:
	ev::dynamic_loop loop;
	std::thread thread;
	// this handler is triggered to terminate the thread
	ev::async break_handler;

	Worker();
	~Worker();

protected:
	ev::async invoke_handler;
	std::queue<std::function<void()>> invoke_queue;
	std::mutex invoke_lock;
	std::atomic_bool terminating{};

	void mainloop();
	void terminate_cb(ev::async& sig, int revents);
	void invoke_cb(ev::async&sig, int revents);

public:
	template<class K, void (K::*method)(Worker *w)>
	void invoke(K* object){
		std::lock_guard<std::mutex> lockGuard(this->invoke_lock);
		invoke_queue.push(std::bind(method, object, this));
		invoke_handler.send();
	};
};



/**
 * A collection of workers. getWorker() gives a random worker back.
 * Freeing the pool stops all contained workers.
 */
class WorkerPool{
	std::vector<std::shared_ptr<Worker>> workers;
	int next_worker = 0;

public:
	explicit WorkerPool(int threads);
	~WorkerPool();

	inline Worker& getWorker(){
		if (next_worker >= workers.size()) next_worker = 0;
		return *workers[next_worker++];
	}
};


#endif //LIBEV_SERVER_WORKERPOOL_H
