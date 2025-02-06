#include <fstream>
#include <iostream>
#include "config.h"
#include "yaml-cpp/yaml.h"

using namespace std;

struct IpSpec {
	int a[4] = {0, 0, 0, 0};
	int b[4] = {0, 0, 0, 0};
	int c[4] = {0, 0, 0, 0};
	int size = 32; // in bits

	IpSpec() = default;

	explicit IpSpec(const YAML::Node &node) {
		if (!node.IsSequence() || node.size() < 4)
			throw runtime_error("Invalid IpSpec");
		for (int i = 0; i < 4; i++) {
			if (node[i].IsSequence()) {
				a[i] = node[i][0].as<int>();
				b[i] = node[i][1].as<int>();
				c[i] = node[i][2].as<int>();
			} else {
				a[i] = 1;
				b[i] = 1;
				c[i] = node[i].as<int>();
			}
		}
		size = node.size() > 4 ? node[4].as<int>() : 32;
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

static YAML::Node config;
static const char *postgresConfigString = nullptr;
unsigned char Config::hmac_secret_key[32];
int Config::nopTeamId;
int Config::flagRoundsValid;

// Network range: x1.x2.x3.x4/size  with  xi=(teamid/a1 %bi +ci)
static IpSpec team_range;
static IpSpec vpn_peers_range;


static void decodeHexSecret(const string &hex, unsigned char *output) {
	unsigned long len = hex.length();
	if (len != 64)
		throw runtime_error("hex secret invalid length");
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

void Config::load(const std::string &filename) {
	cout << "Loading configuration file \"" << filename << "\" ..." << endl;
	fstream fin(filename, ios_base::in);
	if (!fin.is_open()) {
		cerr << "Could not open config file!" << endl;
		throw runtime_error("Cannot open config file");
	}
	config = YAML::LoadFile(filename);

	// Load flag secret
	decodeHexSecret(config["secret_flags"].as<std::string>(), Config::hmac_secret_key);

	// Load scoring config
	nopTeamId = 0;
	flagRoundsValid = 10;
	if (config["scoring"] && config["scoring"].IsMap()) {
		const auto &scoring = config["scoring"];
		if (scoring["nop_team_id"] && !scoring["nop_team_id"].IsNull()) {
			nopTeamId = scoring["nop_team_id"].as<int>();
		}
		if (scoring["flags_rounds_valid"] && !scoring["flags_rounds_valid"].IsNull()) {
			flagRoundsValid = scoring["flags_rounds_valid"].as<int>();
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
		if (pg["username"] && !pg["username"].as<string>().empty()) {
			str += pg["username"].as<string>();
			if (pg["password"] && !pg["password"].as<string>().empty())
				str += ":" + pg["password"].as<string>();
			str += "@";
		}
		str += pg["server"].as<string>();
		if (pg["port"]) {
			str += ":" + to_string(pg["port"].as<int>());
		}
		str += "/" + pg["database"].as<string>();
		postgresConfigString = (new string(str))->c_str();
	}
	return postgresConfigString;
}

string Config::getRedisHost() {
	return config["databases"]["redis"]["host"].as<string>();
}

int Config::getRedisPort() {
	return config["databases"]["redis"]["port"].as<int>();
}

int Config::getRedisDB() {
	return config["databases"]["redis"]["db"].as<int>();
}

string Config::getRedisPassword() {
	auto redis = config["databases"]["redis"];
	auto it = redis["password"];
	if (it)
		return it.as<string>();
	return "";
}


uint16_t Config::getTeamIdFromIp(uint8_t ip0, uint8_t ip1, uint8_t ip2, uint8_t ip3) {
	auto v1 = team_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
	auto v2 = vpn_peers_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
	// printf("%d %d\n", v1, v2);
	if (v2 > 0 && v2 < v1) return v2;
	return v1;
}
