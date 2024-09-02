CC=clang-15
CFLAGS=-O2 -I/usr/include/x86_64-linux-gnu

all:
	${CC} -target bpf -c ${CFLAGS} anonymize_traffic.c -o anonymize_traffic.o
	${CC} -target bpf -c ${CFLAGS} -g traffic_stats.c -o traffic_stats.o
