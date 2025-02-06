#include <iostream>
#include <ev++.h>
#include <unistd.h>
#include <fcntl.h>
#include <cstring>
#include <cstdlib>
#include <netinet/in.h>
#include <sys/socket.h>
#include <list>
#include <arpa/inet.h>
#include <atomic>
#include "flagchecker.h"
#include "workerpool.h"
#include "config.h"
#include "redis.h"
#include "database.h"
#include "statistics.h"
#include "periodic.h"


#define MAX_LINE_BYTES 80


using namespace std;

inline bool isLocalAddress(struct sockaddr_in &addr) {
	if (addr.sin_family == AF_INET) {
		return (addr.sin_addr.s_addr & 0xffu) == 127;
	} else {
		return false;
	}
}


/**
 * A write buffer for string constants
 */
class ConstBuffer {
public:
	const char *data;
	size_t len;
	size_t pos;

	ConstBuffer(const char *bytes, size_t nbytes) : data(bytes), len(nbytes), pos(0) {}

	virtual ~ConstBuffer() = default;

	const char *dpos() {
		return data + pos;
	}

	size_t nbytes() {
		return len - pos;
	}
};

/**
 * A write buffer for malloc-allocated strings
 */
class ConstOwningBuffer : public ConstBuffer {
public:
	ConstOwningBuffer(const char *bytes, size_t nbytes) : ConstBuffer(bytes, nbytes) {}

	~ConstOwningBuffer() override {
		free((void *) data);
	}
};


/**
 * A single incoming connection.
 * Each connection is tied to a fixed worker thread, whose event loop it uses.
 * This class reads data from the connection (until a \n occurs) and writes responses back.
 */
class Connection {
private:
	static std::atomic_int total_clients;

	// event listener that fires the callback if connection_fd is read to read/write
	ev::io io;
	ev::timer timer;
	int connection_fd;
	// address of the submitter
	struct sockaddr_in peer_address;
	// count lines received in this connection
	int line_count = 0;

	// read into line_buffer until "\n" occurs
	// no valid submission contains more than MAX_LINE_BYTES interesting characters, we drop everything in a line that's longer
	char line_buffer[MAX_LINE_BYTES + 2];
	int line_buffer_pos = 0;
	// if we read an EOF, set this to true
	bool read_closed = false;

	// Buffers that are pending write
	std::list<unique_ptr<ConstBuffer>> write_queue;
	// if we write to a broken pipe, set this to true
	bool write_closed = false;
	// set to true for activity, false during checks
	bool hasSeenActivity = true;

	uint16_t team_id = 0xffff; // 0xffff=unknown

	// Generic callback - delegates connection reads and writes
	void callback(ev::io &watcher, int revents) {
		if (EV_ERROR & revents) {
			perror("got invalid event");
			return;
		}

		// handle a read event
		if (revents & EV_READ) {
			read_cb(watcher);
		}

		// handle a write event
		if (revents & EV_WRITE) {
			write_cb(watcher);
		}

		// is this connection fully closed?
		if (read_closed && (write_closed || write_queue.empty())) {
			delete this;
		} else {
			// check if we can still read from / write to this connection (and listen for the matching events)
			int events = read_closed || (!write_closed && write_queue.size() > 32) ? 0 : ev::READ;
			events |= write_queue.empty() || write_closed ? 0 : ev::WRITE;
			io.set(events);
		}
	}

	// Receive message from client socket
	void read_cb(ev::io &watcher) {
		char buffer[256];

		ssize_t nread = recv(watcher.fd, buffer, sizeof(buffer), 0);

		if (nread < 0) {
			perror("read error");
			read_closed = true;
			return;
		}

		if (nread == 0) {
			read_closed = true;
		} else {
			// fill line_buffer until we get a \n
			for (int i = 0; i < nread; i++) {
				if (buffer[i] == '\n') {
					// submit line, and add response to write queue
					line_buffer[line_buffer_pos] = '\0';
					if (isLocalAddress(peer_address)) {
						// Print statistics
						if (strcmp(line_buffer, "statistics connections") == 0) {
							const char *response = statistics::getConnectionFDReport(total_clients);
							write_queue.emplace_back(new ConstOwningBuffer(response, strlen(response)));
						} else if (strcmp(line_buffer, "statistics flags") == 0) {
							for (const char *response : statistics::getFlagReport()) {
								write_queue.emplace_back(new ConstOwningBuffer(response, strlen(response)));
							}
						} else if (strcmp(line_buffer, "statistics cache") == 0) {
							const char *response = statistics::getCacheReport();
							write_queue.emplace_back(new ConstOwningBuffer(response, strlen(response)));
						} else {
							// Submit flag
							const char *response = progress_flag(line_buffer, line_buffer_pos, &peer_address, &team_id);
							write_queue.emplace_back(new ConstBuffer(response, strlen(response)));
						}
					} else {
						const char *response = progress_flag(line_buffer, line_buffer_pos, &peer_address, &team_id);
						write_queue.emplace_back(new ConstBuffer(response, strlen(response)));
					}
					line_count++;
					line_buffer_pos = 0;
				} else if (line_buffer_pos < MAX_LINE_BYTES) {
					// fill line buffer
					line_buffer[line_buffer_pos++] = buffer[i];
				} else {
					// silently drop characters - that's not going to be a valid flag anyway
				}
			}
		}
	}

	// Socket is writable
	void write_cb(ev::io &watcher) {
		// anything to write?
		if (write_queue.empty()) return;

		ConstBuffer *buffer = write_queue.front().get();

		ssize_t written = write(watcher.fd, buffer->dpos(), buffer->nbytes());
		if (written < 0) {
			perror("write error");
			write_queue.clear();
			write_closed = true;
			return;
		}
		buffer->pos += written;

		// buffer written completely?
		if (buffer->nbytes() == 0) {
			write_queue.pop_front();
		}
	}

	void check() {
		if (hasSeenActivity) {
			hasSeenActivity = false;
		} else {
			printf("Due to inactivity: ");
			delete this;
		}
	}

	void init_cb(Worker *worker) {
		// register this connection's event listener in the workers event loop
		io.loop = worker->loop;
		io.priority = 0;
		io.set<Connection, &Connection::callback>(this);
		io.start(connection_fd, ev::READ);
		timer.loop = worker->loop;
		timer.priority = 1;
		timer.set<Connection, &Connection::check>(this);
		timer.start(30, 30);
	}

	~Connection() {
		// Stop and free watcher, close the connection's socket
		io.stop();
		timer.stop();
		close(connection_fd);

		char buffer[20];
		inet_ntop(AF_INET, &(peer_address.sin_addr), buffer, sizeof(buffer));
		printf("Connection closed with %s (got %d lines)\n", buffer, line_count);

		printf("%d client(s) connected.\n", --total_clients);
	}

public:
	Connection(int connection_fd, struct sockaddr_in &peer_address, Worker &worker)
			: connection_fd(connection_fd), peer_address(peer_address), io(worker.loop) {
		// non-blocking IO of course
		fcntl(connection_fd, F_SETFL, fcntl(connection_fd, F_GETFL, 0) | O_NONBLOCK);

		char buffer[20];
		inet_ntop(AF_INET, &(peer_address.sin_addr), buffer, sizeof(buffer));
		printf("New connection from %s\n", buffer);
		total_clients++;
		statistics::countConnection();

		// assign this connection a worker
		worker.invoke<Connection, &Connection::init_cb>(this);
	}
};


/**
 * Accepts incoming connections and creates Connection instances.
 * Handles signals.
 */
class SubmissionServer {
private:
	ev::io io; //IO on server socket (=new connection)
	ev::sig sio1; //SIGINT
	ev::sig sio2; //SIGTERM
	ev::timer stats; // Stats printer
	int server_socket;
	WorkerPool workers;

public:

	/**
	 * Socket has a new connection - accept it
	 * @param watcher
	 * @param revents
	 */
	void io_accept(ev::io &watcher, int revents) {
		if (EV_ERROR & revents) {
			perror("got invalid event");
			return;
		}

		struct sockaddr_in client_addr;
		socklen_t client_len = sizeof(client_addr);

		int client_sd = accept(watcher.fd, (struct sockaddr *) &client_addr, &client_len);

		if (client_sd < 0) {
			perror("accept error");
			return;
		}

		// create the new connection - Connection's constructor adds it to a watcher thread
		Connection *client = new Connection(client_sd, client_addr, workers.getWorker());
	}

	static void signal_cb(ev::sig &signal, int revents) {
		cerr << "Terminating..." << endl;
		signal.loop.break_loop();
	}

	static void stats_cb(ev::timer &timer, int revents) {
		printCacheStats();
	}

	explicit SubmissionServer(int port, int threads = 1) : workers(threads) {
		printf("Listening on port %d\n", port);
		printf("Using %d worker threads\n", threads);

		struct sockaddr_in addr;

		// open non-blocking TCP socket
		server_socket = socket(PF_INET, SOCK_STREAM, 0);
		int one = 1;
		if (setsockopt(server_socket, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(int)) < 0)
			perror("setsockopt(SO_REUSEADDR) failed");

		addr.sin_family = AF_INET;
		addr.sin_port = htons((unsigned short) port);
		addr.sin_addr.s_addr = INADDR_ANY;

		if (bind(server_socket, (struct sockaddr *) &addr, sizeof(addr)) != 0) {
			perror("bind");
			exit(1);
		}

		fcntl(server_socket, F_SETFL, fcntl(server_socket, F_GETFL, 0) | O_NONBLOCK);

		listen(server_socket, 5);

		// we wait for some events: new connection, SIGINT signal, SIGTERM signal
		io.set<SubmissionServer, &SubmissionServer::io_accept>(this);
		io.start(server_socket, ev::READ);

		sio1.set<&SubmissionServer::signal_cb>();
		sio1.start(SIGINT);
		sio2.set<&SubmissionServer::signal_cb>();
		sio2.start(SIGTERM);

		stats.set<&SubmissionServer::stats_cb>();
		stats.start(600, 600);
	}

	virtual ~SubmissionServer() {
		shutdown(server_socket, SHUT_RDWR);
		close(server_socket);
	}
};

std::atomic_int Connection::total_clients(0);

int main(int argc, char **argv) {
	// USAGE: ./<binary> [<port>] [<threads>]
	int port = 31337;
	int threads = 1;

	if (argc > 1)
		port = std::stoi(argv[1]);
	if (argc > 2)
		threads = std::stoi(argv[2]);

	// Load configuration
	Config::load();

	// Check config
#ifndef CHECK_EXPIRED
	cerr << "[WARNING] Submission server does not check for expired flags" << endl;
#endif
#ifndef CHECK_MAC
	cerr << "[WARNING] Submission server does not check for valid MAC" << endl;
#endif
#ifndef CHECK_STATE
	cerr << "[WARNING] Submission server does not check if the game is running" << endl;
#endif

	// Load table sizes from DB
	uint32_t max_teams = (uint32_t) max(25, getMaxTeamId() + 2);
	uint32_t max_services = (uint32_t) max(6, getMaxServiceId() + 1);
	initModelSizes(max_teams, max_services);

	// we don't need a signal for broken pipes, we can handle that ourselves
	signal(SIGPIPE, SIG_IGN);
	// unbuffer stdout
	std::cout.setf(std::ios::unitbuf);
	setbuf(stdout, nullptr);
	// main thread event loop (for connection / signal handling)
	ev::default_loop loop;
	Redis::connect(loop.raw_loop);
	SubmissionServer echo(port, threads);
	PeriodicMaintenance maintenance;
	maintenance.connect(loop);
	loop.run(0);

	return 0;
}