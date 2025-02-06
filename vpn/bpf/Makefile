CFLAGS=-O2 -I/usr/include/x86_64-linux-gnu
ifeq ($(CC),)
	CC=cc
endif

# find the newest clang compiler
ifeq ($(CC),cc)
	ifneq ($(shell clang --version 2>/dev/null),)
		CC := clang
	else ifneq ($(shell clang-21 --version 2>/dev/null),)
		CC := clang-21
	else ifneq ($(shell clang-20 --version 2>/dev/null),)
		CC := clang-20
	else ifneq ($(shell clang-19 --version 2>/dev/null),)
		CC := clang-19
	else ifneq ($(shell clang-18 --version 2>/dev/null),)
		CC := clang-18
	else ifneq ($(shell clang-17 --version 2>/dev/null),)
		CC := clang-17
	else ifneq ($(shell clang-16 --version 2>/dev/null),)
		CC := clang-16
	else ifneq ($(shell clang-15 --version 2>/dev/null),)
		CC := clang-15
	else ifneq ($(shell clang-14 --version 2>/dev/null),)
		CC := clang-14
	else ifneq ($(shell clang-13 --version 2>/dev/null),)
		CC := clang-13
	else ifneq ($(shell clang-12 --version 2>/dev/null),)
		CC := clang-12
	else ifneq ($(shell clang-11 --version 2>/dev/null),)
		CC := clang-11
	endif
endif

all:
	@echo "Using ${CC} as compiler ..."
	${CC} -target bpf -c ${CFLAGS} anonymize_traffic.c -o anonymize_traffic.o
	${CC} -target bpf -c ${CFLAGS} -g traffic_stats.c -o traffic_stats.o
	${CC} -target bpf -c ${CFLAGS} -g traffic_stats_gameserver.c -o traffic_stats_gameserver.o

vmlinux.h:
	@bpftool btf dump file /sys/kernel/btf/vmlinux format c > vmlinux.h
