#include <iostream>
#include "workerpool.h"


void Worker::mainloop() {
	break_handler.set<Worker, &Worker::terminate_cb>(this);
	break_handler.start();
	invoke_handler.set<Worker, &Worker::invoke_cb>(this);
	invoke_handler.start();

	loop.run(0);
	if (!terminating) {
		std::cerr << "Worker died" << std::endl;
	}
}

void Worker::terminate_cb(ev::async &sig, int revents) {
	terminating = true;
	loop.break_loop();
}

Worker::Worker() : break_handler(loop), invoke_handler(loop), terminating(false) {
	// start thread after everything is initialized
	thread = std::thread(&Worker::mainloop, this);
}

Worker::~Worker() {
	// Worker can only be free if worker thread is not running anymore
	break_handler.send();
	thread.join();
}

void Worker::invoke_cb(ev::async &sig, int revents) {
	// invoke has been called from somewhere, process invoke queue
	std::lock_guard<std::mutex> lockGuard(this->invoke_lock);
	while (!invoke_queue.empty()) {
		invoke_queue.front()();
		invoke_queue.pop();
	}
}


WorkerPool::WorkerPool(int threads) {
	for (int i = 0; i < threads; i++) {
		workers.push_back(std::make_shared<Worker>());
	}
}

WorkerPool::~WorkerPool() {
	for (auto &worker: workers) {
		worker->break_handler.send();
	}
}
