#include "string_pool.h"

#include <cstdio>
#include <cstdlib>
#include <cstdarg>


const char *StringPool::get(const char *tmpl, ...) {
	char *buffer = (char *) malloc(256);
	va_list args;
	va_start(args, tmpl);
	vsnprintf(buffer, 256, tmpl, args);
	va_end(args);

	auto it = cache.insert({std::string(buffer), buffer});
	if (it.second) {
		// inserted to cache
		return buffer;
	} else {
		// already in cache, return cached memory
		free(buffer);
		return it.first->second;
	}
}
