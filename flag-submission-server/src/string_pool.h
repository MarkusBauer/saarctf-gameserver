#ifndef FLAG_SUBMISSION_SERVER_STRING_POOL_H
#define FLAG_SUBMISSION_SERVER_STRING_POOL_H
#include <string>
#include <unordered_map>


/**
 * A deduplicating string pool.
 * Threat return values as string constants that never change nor invalidate.
 */
class StringPool {
	std::unordered_map<std::string, const char *> cache;  // waste of memory, but ok for now
public:
	const char *get(const char *tmpl, ...);
};

#endif //FLAG_SUBMISSION_SERVER_STRING_POOL_H
