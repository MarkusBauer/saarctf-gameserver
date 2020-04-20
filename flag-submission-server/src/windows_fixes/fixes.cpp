
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/tcp.h>
#include "hook.hpp"

real_function(setsockopt, int(int, int, int, const void*, socklen_t));

int hook_setsockopt(int sockfd, int level, int optname, const void *optval, socklen_t optlen) {
	if (optname == TCP_NODELAY)
		return 0;
	return real(setsockopt)(sockfd, level, optname, optval, optlen);
}
install_hook(setsockopt, hook_setsockopt);
