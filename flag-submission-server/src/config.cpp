#include <fstream>
#include <iostream>
#include "nlohmann/json.hpp"
#include "config.h"

using namespace std;
using namespace nlohmann;

struct IpSpec {
	int a[4] = {0, 0, 0, 0};
	int b[4] = {0, 0, 0, 0};
	int c[4] = {0, 0, 0, 0};
	int size = 32; // in bits

	IpSpec() = default;

	explicit IpSpec(const json &json) {
		for (int i = 0; i < 4; i++) {
			if (json[i].is_number()) {
				a[i] = 1;
				b[i] = 1;
				c[i] = json[i].get<int>();
			} else {
				a[i] = json[i][0].get<int>();
				b[i] = json[i][1].get<int>();
				c[i] = json[i][2].get<int>();
			}
		}
		size = json.size() > 4 ? json[4].get<int>() : 32;
	}

	uint16_t getTeamIdFromIpSpec(uint8_t ip0, uint8_t ip1, uint8_t ip2, uint8_t ip3) {
		/*
		 *     id/ai%bi + ci = di
		 * <=> id/ai%bi = di - ci
		 * <=> id/ai = di-ci + ki*bi
		 * <=> id >= (di-ci + ki*bi)*ai  &&  id < (di-ci + ki*bi)*(a1+1)
		 * --> Intervals: offset (d-c)*a, size a, interval a*b
		 */
		int pos[4] = {
				(ip0 - c[0]) * a[0],
				(ip1 - c[1]) * a[1],
				(ip2 - c[2]) * a[2],
				(ip3 - c[3]) * a[3]
		};
		int smallest; // = max(interval starts)
		int largest; //  = min(interval ends)
		do {
			smallest = 0;
			largest = 0xffffff;
			for (int i = 0; i < size / 8; i++) {
				if (b[i] > 1) {
					if (smallest < pos[i]) smallest = pos[i];
					if (largest > pos[i] + a[i]) largest = pos[i] + a[i];
				}
			}
			if (smallest < largest) {
				return (uint16_t) smallest;
			} else {
				for (int i = 0; i < size / 8; i++) {
					if (b[i] > 1) {
						while (pos[i] + a[i] <= smallest) {
							pos[i] += a[i] * b[i];
						}
					}
				}
			}
		} while (smallest < 0xffff);
		return 0;
	}
};

static json config;
static const char *postgresConfigString = nullptr;
unsigned char Config::hmac_secret_key[32];
int Config::nopTeamId;
int Config::flagRoundsValid;

// Network range: x1.x2.x3.x4/size  with  xi=(teamid/a1 %bi +ci)
static IpSpec team_range;
static IpSpec vpn_peers_range;


static void decodeHexSecret(const string &hex, unsigned char *output) {
	unsigned long len = hex.length();
	assert(len == 64);
	for (unsigned long i = 0; i < len; i += 2) {
		string byte = hex.substr(i, 2);
		*output = (unsigned char) (int) strtol(byte.c_str(), nullptr, 16);
		output++;
	}
}


void Config::load() {
	auto env = getenv("SAARCTF_CONFIG");
	if (env) {
		Config::load(env);
	} else {
		env = getenv("SAARCTF_CONFIG_DIR");
		if (env) {
			Config::load(std::string(env) + "/config.json");
		} else {
			Config::load("../../config.json");
		}
	}
}

void Config::load(const std::string filename) {
	cout << "Loading configuration file \"" << filename << "\" ..." << endl;
	fstream fin(filename, ios_base::in);
	if (!fin.is_open()) {
		cerr << "Could not open config file!" << endl;
		throw exception();
	}
	fin >> config;

	// Load flag secret
	decodeHexSecret(config["secret_flags"], Config::hmac_secret_key);

	// Load legacy nop team/flags_round_valid
	if (config.find("nop_team_id") != config.end() && !config["nop_team_id"].is_null()) {
		nopTeamId = config["nop_team_id"].get<int>();
	} else {
		nopTeamId = 0;
	}
	if (config.find("flags_rounds_valid") != config.end() && !config["flags_rounds_valid"].is_null()) {
		flagRoundsValid = config["flags_rounds_valid"].get<int>();
	} else {
		flagRoundsValid = 10;
	}

	// Load scoring config
	if (config.find("scoring") != config.end() && config["scoring"].is_object()) {
		const auto scoring = config["scoring"];
		if (scoring.find("nop_team_id") != scoring.end() && !scoring["nop_team_id"].is_null()) {
			nopTeamId = scoring["nop_team_id"].get<int>();
		}
		if (scoring.find("flags_rounds_valid") != scoring.end() && !scoring["flags_rounds_valid"].is_null()) {
			flagRoundsValid = scoring["flags_rounds_valid"].get<int>();
		}
	}

	// Network range
	team_range = IpSpec(config["network"]["team_range"]);
	vpn_peers_range = IpSpec(config["network"]["vpn_peer_ips"]);
}


const char *Config::getPostgresConnectionString() {
	if (!postgresConfigString) {
		auto pg = config["databases"]["postgres"];
		string str = "postgresql://";
		if (pg.find("username") != pg.end() && !pg["username"].get<string>().empty()) {
			str += pg["username"].get<string>();
			if (pg.find("password") != pg.end() && !pg["password"].get<string>().empty())
				str += ":" + pg["password"].get<string>();
			str += "@";
		}
		str += pg["server"];
		if (pg.find("port") != pg.end()) {
			str += ":" + to_string(pg["port"].get<int>());
		}
		str += "/" + pg["database"].get<string>();
		postgresConfigString = (new string(str))->c_str();
	}
	return postgresConfigString;
}

string Config::getRedisHost() {
	return config["databases"]["redis"]["host"].get<string>();
}

int Config::getRedisPort() {
	return config["databases"]["redis"]["port"].get<int>();
}

int Config::getRedisDB() {
	return config["databases"]["redis"]["db"].get<int>();
}

string Config::getRedisPassword() {
	auto redis = config["databases"]["redis"];
	auto it = redis.find("password");
	if (it != redis.end())
		return it->get<string>();
	return "";
}


uint16_t Config::getTeamIdFromIp(uint8_t ip0, uint8_t ip1, uint8_t ip2, uint8_t ip3) {
	auto v1 = team_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
	auto v2 = vpn_peers_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
	// printf("%d %d\n", v1, v2);
	if (v2 > 0 && v2 < v1) return v2;
	return v1;
}
