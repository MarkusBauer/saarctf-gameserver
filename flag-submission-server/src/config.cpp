#include "config.h"
#include "yaml-cpp/yaml.h"
#include <cstdlib>
#include <fstream>
#include <iostream>

struct IpSpec {
    int a[4] = {0, 0, 0, 0};
    int b[4] = {0, 0, 0, 0};
    int c[4] = {0, 0, 0, 0};
    int size = 32; // in bits

    IpSpec() = default;

    explicit IpSpec(const YAML::Node &node) {
        if (!node.IsSequence() || node.size() < 4)
            throw std::runtime_error("Invalid IpSpec");
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
            (ip0 - c[0]) * a[0], (ip1 - c[1]) * a[1], (ip2 - c[2]) * a[2],
            (ip3 - c[3]) * a[3]
        };
        int smallest; // = max(interval starts)
        int largest; //  = min(interval ends)
        do {
            smallest = 0;
            largest = 0xffffff;
            for (int i = 0; i < size / 8; i++) {
                if (b[i] > 1) {
                    if (smallest < pos[i])
                        smallest = pos[i];
                    if (largest > pos[i] + a[i])
                        largest = pos[i] + a[i];
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
static std::unordered_map<std::string, std::string> envConfig;
unsigned char Config::hmac_secret_key[32];
std::string Config::flagPrefix = "SAAR";
int Config::nopTeamId;
int Config::flagRoundsValid;

// Network range: x1.x2.x3.x4/size  with  xi=(teamid/a1 %bi +ci)
static IpSpec team_range;
static IpSpec vpn_peers_range;

static void decodeHexSecret(const std::string &hex, unsigned char *output) {
    unsigned long len = hex.length();
    if (len != 64)
        throw std::runtime_error("hex secret invalid length");
    for (unsigned long i = 0; i < len; i += 2) {
        std::string byte = hex.substr(i, 2);
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
            Config::load(std::string(env) + "/config.yaml");
        } else {
            Config::load("../../config.yaml");
        }
    }
}

void Config::load(const std::string &filename) {
    std::cout << "Loading configuration file \"" << filename << "\" ..." << std::endl;
    std::fstream fin(filename, std::ios_base::in);
    if (!fin.is_open()) {
        std::cerr << "Could not open config file!" << std::endl;
        throw std::runtime_error("Cannot open config file");
    }
    config = YAML::LoadFile(filename);

    // Load flag secret + prefix
    if (config["flag_prefix"]) {
        Config::flagPrefix = config["flag_prefix"].as<std::string>();
    }
    if (config["secret_flags"]) {
        decodeHexSecret(config["secret_flags"].as<std::string>(), hmac_secret_key);
    }

    // Load scoring config
    nopTeamId = 0;
    flagRoundsValid = 10;
    if (config["scoring"] && config["scoring"].IsMap()) {
        const auto &scoring = config["scoring"];
        if (scoring["nop_team_id"] && !scoring["nop_team_id"].IsNull()) {
            nopTeamId = scoring["nop_team_id"].as<int>();
        }
        if (scoring["flags_rounds_valid"] &&
            !scoring["flags_rounds_valid"].IsNull()) {
            flagRoundsValid = scoring["flags_rounds_valid"].as<int>();
        }
    }

    // Network range
    team_range = IpSpec(config["network"]["team_range"]);
    vpn_peers_range = IpSpec(config["network"]["vpn_peer_ips"]);
}


static std::string config_env_keys[9] {
    "POSTGRES_SERVER", "POSTGRES_PORT", "POSTGRES_USERNAME", "POSTGRES_PASSWORD", "POSTGRES_DATABASE",
    "REDIS_HOST", "REDIS_PORT", "REDIS_DATABASE", "REDIS_PASSWORD"
};

void Config::loadFromEnv() {
    if (getenv("CONFIG_FLAG_PREFIX") != nullptr)
        flagPrefix = std::string(getenv("CONFIG_FLAG_PREFIX"));
    if (getenv("CONFIG_FLAG_ROUNDS_VALID") != nullptr)
        flagRoundsValid = std::stoi(getenv("CONFIG_FLAG_ROUNDS_VALID"));
    if (getenv("CONFIG_SECRET_FLAGS") != nullptr)
        decodeHexSecret(getenv("CONFIG_SECRET_FLAGS"), hmac_secret_key);
    if (getenv("CONFIG_NOP_TEAM_ID") != nullptr)
        nopTeamId = std::stoi(getenv("CONFIG_NOP_TEAM_ID"));

    for (const auto& key: config_env_keys) {
        if (getenv(key.c_str()))
            envConfig[key] = std::string(getenv(key.c_str()));
    }
}

inline std::string configGet(YAML::Node pg, const char *keyInConfigFile, const std::string &keyInEnv) {
    auto it1 = envConfig.find(keyInEnv);
    if (it1 != envConfig.end())
        return it1->second;
    auto it2 = pg[keyInConfigFile];
    if (it2)
        return it2.as<std::string>();
    return "";
}

const char *Config::getPostgresConnectionString() {
    if (!postgresConfigString) {
        auto pg = config["databases"]["postgres"];
        auto username = configGet(pg, "username", "POSTGRES_USERNAME");
        auto password = configGet(pg, "password", "POSTGRES_PASSWORD");
        std::string str = "postgresql://";
        if (!username.empty()) {
            str += username;
            if (!password.empty())
                str += ":" + password;
            str += "@";
        }
        str += configGet(pg, "server", "POSTGRES_SERVER");
        auto port = configGet(pg, "port", "POSTGRES_PORT");
        if (!port.empty()) {
            str += ":" + port;
        }
        str += "/" + configGet(pg, "database", "POSTGRES_DATABASE");
        postgresConfigString = (new std::string(str))->c_str();
    }
    return postgresConfigString;
}

std::string Config::getRedisHost() {
    auto it = envConfig.find("REDIS_HOST");
    if (it != envConfig.end())
        return it->second;
    return config["databases"]["redis"]["host"].as<std::string>();
}

int Config::getRedisPort() {
    auto it = envConfig.find("REDIS_PORT");
    if (it != envConfig.end())
        return std::stoi(it->second);
    return config["databases"]["redis"]["port"].as<int>();
}

int Config::getRedisDB() {
    auto it = envConfig.find("REDIS_DATABASE");
    if (it != envConfig.end())
        return std::stoi(it->second);
    return config["databases"]["redis"]["db"].as<int>();
}

std::string Config::getRedisPassword() {
    auto it = envConfig.find("REDIS_PASSWORD");
    if (it != envConfig.end())
        return it->second;

    auto redis = config["databases"]["redis"];
    auto it2 = redis["password"];
    if (it2)
        return it2.as<std::string>();
    return "";
}

uint16_t Config::getTeamIdFromIp(uint8_t ip0, uint8_t ip1, uint8_t ip2, uint8_t ip3) {
    auto v1 = team_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
    auto v2 = vpn_peers_range.getTeamIdFromIpSpec(ip0, ip1, ip2, ip3);
    // printf("%d %d\n", v1, v2);
    if (v2 > 0 && v2 < v1)
        return v2;
    return v1;
}
