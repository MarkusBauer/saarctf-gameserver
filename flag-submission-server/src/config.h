#ifndef FLAG_SUBMISSION_SERVER_CONFIG_H
#define FLAG_SUBMISSION_SERVER_CONFIG_H


#include <string>

class Config {
public:
	static void load();
	static void load(const std::string filename);

	static const char *getPostgresConnectionString();

	static std::string getRedisHost();

	static int getRedisPort();

	static int getRedisDB();

	static std::string getRedisPassword();

	static unsigned char hmac_secret_key[32];

	static int flagRoundsValid;

	static int nopTeamId;

	static uint16_t getTeamIdFromIp(uint8_t ip0, uint8_t ip1, uint8_t ip2, uint8_t ip3);
};

#endif //FLAG_SUBMISSION_SERVER_CONFIG_H
