#include <sys/socket.h>
#include <sys/wait.h>
#include <netinet/in.h>
#include <cstdio>
#include <sys/types.h>
#include <unistd.h>
#include <cstring>
#include <netdb.h>
#include <iostream>
#include <fstream>
#include <iterator>
#include <algorithm>
#include <chrono>
#include <arpa/inet.h>

#include "../src/flagchecker.h"
#include "../src/libraries/base64.h"
#include "../src/config.h"

using namespace std;


// #define TEST_SUBMIT

#ifdef TEST_SUBMIT
const long FLAG_COUNT = 2;
#else
const long FLAG_COUNT = 20000;
#endif

/*
 *
 * Generates FLAG_COUNT (semi-valid) flags and fires them to localhost:31337.
 * No result checking is done, but total time and flags/second is calculated.
 * The generated flags have an invalid mac, disable mac checking if you want to benchmark Postgresql performance.
 *
 * USAGE: ./benchmark-newflags [# of connections]
 *
 * In total, FLAG_COUNT * #connections flags are sent.
 *
 */




static void print_flag(FlagFormat &flag) {
	printf("Flag: [team=%hu, service=%hu, round=%hu, payload=%hu]\n", flag.team_id, flag.service_id, flag.round, flag.payload);
}

int send_singlethread(int sockfd) {
	srand(time(NULL) + 31 * getpid());

	char tmp[4096];
	ssize_t rc;
	// char flag[64] = {'S', 'A', 'A', 'R', '{', '/', 'w', 'A', 'A', 'A', 'B', 'U', 'A', 'A', 'w', 'B', 'B', 'Q', 'k', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', 'Q', 'U', 'F', 'B', '}', '\n', '\0'};
	// int flagLen = FLAG_LENGTH_FULL + 1;

	char flag[FLAG_LENGTH_FULL + 2];
	flag[0] = 'S';
	flag[1] = 'A';
	flag[2] = 'A';
	flag[3] = 'R';
	flag[4] = '{';
	flag[FLAG_LENGTH_FULL - 1] = '}';
	flag[FLAG_LENGTH_FULL] = '\n';
	flag[FLAG_LENGTH_FULL + 1] = '\0';
	FlagFormat ff{};
	//ff.expires = static_cast<uint32_t>(time(0) + 3600 * 24 * 30);

	for (long i = 0; i < FLAG_COUNT; i++) {
		ff.payload = rand() & 0xffff;
		ff.team_id = (rand() % 10) + 2;
		ff.service_id = (rand() % 5) + 2;
		ff.round = rand() & 0x7fff;
		create_hmac(&ff, &ff.mac, ff.mac);
		base64_encode(reinterpret_cast<const unsigned char *>(&ff), sizeof(FlagFormat), &flag[5]);
		flag[FLAG_LENGTH_FULL - 1] = '}';
		flag[FLAG_LENGTH_FULL] = '\n';
		flag[FLAG_LENGTH_FULL + 1] = '\0';

#ifdef TEST_SUBMIT
		cout << "Flag: " << flag;
		print_flag(ff);
		FlagFormat ff2{};
		base64_decode(reinterpret_cast<const unsigned char *>(&flag[5]), FLAG_LENGTH_B64, (unsigned char *) &ff2);
		print_flag(ff2);
#endif

		// send flag
		size_t n = 0;
		do {
			ssize_t count = write(sockfd, flag + n, FLAG_LENGTH_FULL + 1 - n);
			if (count <= 0) {
				perror("Invalid count");
				return 2;
			}
			n += count;
		} while (n < FLAG_LENGTH_FULL + 1);

		// read some responses
		if (read(sockfd, tmp, sizeof tmp) < 0) {
			perror("read");
			return 3;
		}

#ifdef TEST_SUBMIT
		cout << "Resp: " << tmp << endl;
#endif
	}
	shutdown(sockfd, SHUT_WR);

	// read all responses
	while ((rc = read(sockfd, tmp, sizeof tmp)) > 0) {}
	if (rc < 0) perror("read_all");

	return 0;
}


int do_forks(int process_count) {
	cout << "Forking " << process_count << " times..." << endl;
	const int sleeptime = 100000;

	std::chrono::steady_clock::time_point begin = std::chrono::steady_clock::now();

	for (int i = 0; i < process_count; i++) {
		pid_t pid = fork();
		if (pid < 0) {
			perror("fork()");
			return 1;
		} else if (pid == 0) {
			// child - start working
			usleep(sleeptime);
			return -1;
		}
	}
	// Wait for childs
	int status;
	while (wait(&status) > 0) {}

	std::chrono::steady_clock::time_point end = std::chrono::steady_clock::now();
	auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - begin).count() - sleeptime;

	cout << "All child processes terminated" << endl;
	printf("Wrote %ld flags (by %d processes) in %.3f seconds\n", FLAG_COUNT * process_count, process_count, duration / 1000000.0);
	printf("= %.2f flags / second\n", FLAG_COUNT * process_count * 1000000.0 / duration);
	return 0;
}


int main(int argc, char *argv[]) {
	Config::load();
    Config::loadFromEnv();

#ifndef TEST_SUBMIT
	if (argc > 1) {
		int forkno = atoi(argv[1]);
		int r = do_forks(forkno);
		if (r >= 0) return r;
	}
#endif

	int sockfd = socket(AF_INET, SOCK_STREAM, 0);
	struct sockaddr_in serv_addr;
	memset(&serv_addr, 0, sizeof serv_addr);
	struct hostent *server = gethostbyname("localhost");
	bzero((char *) &serv_addr, sizeof(serv_addr));
	serv_addr.sin_family = AF_INET;
	bcopy((char *) server->h_addr, (char *) &serv_addr.sin_addr.s_addr, server->h_length);
	serv_addr.sin_port = htons(31337);

	// Set source address
	struct sockaddr_in localaddr;
	localaddr.sin_family = AF_INET;
	localaddr.sin_addr.s_addr = inet_addr("127.0.5.1");
	localaddr.sin_port = 0;  // Any local port will do
	bind(sockfd, (struct sockaddr *) &localaddr, sizeof(localaddr));

	if (connect(sockfd, (struct sockaddr *) &serv_addr, sizeof serv_addr) < 0) {
		perror("Connect");
		return 1;
	}
	cout << "Connected..." << endl;

	std::chrono::steady_clock::time_point begin = std::chrono::steady_clock::now();

	int r = send_singlethread(sockfd);
	if (r != 0) return r;

	std::chrono::steady_clock::time_point end = std::chrono::steady_clock::now();
	auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - begin).count();

	close(sockfd);
	cout << "All written." << endl;

	printf("Wrote %ld flags in %.3f seconds\n", FLAG_COUNT, duration / 1000000.0);
	printf("= %.2f flags / second\n", FLAG_COUNT * 1000000.0 / duration);

	return 0;
}

// Stubs
int submit_flag(uint16_t team, FlagFormat &flag) {
	return 0;
}

#include "../src/redis.h"

volatile int Redis::state = STOPPED;
volatile int Redis::current_round = 0;

