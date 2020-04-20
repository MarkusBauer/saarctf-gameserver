#ifndef LIBEV_SERVER_DATABASE_H
#define LIBEV_SERVER_DATABASE_H

#include <cstdint>

class FlagFormat;

/**
 * Submits a flag to the database
 * @param team submitting team
 * @param flag binary part of the flag
 * @return 1 if the flag was new and accepted, 0 if the flag was already present, negative values for error
 */
int submit_flag(uint16_t team, FlagFormat& flag);

int getMaxTeamId();
int getMaxServiceId();

#endif //LIBEV_SERVER_DATABASE_H
