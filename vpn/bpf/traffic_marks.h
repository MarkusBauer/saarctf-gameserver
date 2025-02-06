#include <stddef.h>
#include <linux/bpf.h>
#include <linux/ip.h>
#include <linux/in.h>
#include "bpf-utils.h"

/*
-------------------------------------------
|             32 bit                      |
-------------------------------------------
| 8 | 2  2    4 | 4        2   1  9       |
| - | -  DIR  - | service  tc  P  team-id |
-------------------------------------------

8bit            unused
2bit            unused
2bit  0x300000  direction (1=original, 2=reply)
4bit            unused
4bit  0xf000  service
2bit  0x0c00  traffic class
1bit  0x0200  processed (always 1)
9bit  0x01ff  team-id
 */

#define MASK_TEAM_ID 0x01ff        // 9 bits
#define MASK_PROCESSED_BIT 0x0200  // 1 bit
#define OFFSET_PROCESSED_BIT 9
#define MASK_TRAFFIC_CLASS 0x0c00  // 2 bits
#define OFFSET_TRAFFIC_CLASS 10
#define MASK_SERVICE 0xf000        // 4 bits
#define OFFSET_SERVICE 12
#define MASK_PER_PACKET 0x0300     // = TEAM_ID + PROCESSED_BIT
#define MASK_PER_CONNECTION 0xfc00 // = TRAFFIC_CLASS + SERVICE

#define TC_UNKNOWN 0x0
#define TC_GAMESERVER 0x1    // 0x0400/0x0c00
#define TC_TEAM_INTERNAL 0x2 // 0x0800/0x0c00
#define TC_TEAM_TEAM 0x3     // 0x0c00/0x0c00

#define IP_RANGE_UNKNOWN 0
#define IP_RANGE_GAMESERVER -1


struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__type(key, __u32);
	__type(value, __u32); // 16bit service, 16bit port
	__uint(max_entries, 20);
	__uint(map_flags, 0);
	__uint(pinning, LIBBPF_PIN_BY_NAME);
} service_ports_tcp SEC(".maps");

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__type(key, __u32);
	__type(value, __u32); // 16bit service, 16bit port
	__uint(max_entries, 20);
	__uint(map_flags, 0);
	__uint(pinning, LIBBPF_PIN_BY_NAME);
} service_ports_udp SEC(".maps");


static inline int get_service(int protocol, int port) {
	if (protocol == IPPROTO_TCP) {
		switch (port) {
			case 22:
				return 15;
			case 31337:
				return 14;
		}
		for (int i = 0; i < 20; i++) {
			int idx = i;
			__u32 *entry_ptr = bpf_map_lookup_elem(&service_ports_tcp, &idx);
			if (!entry_ptr) continue;
			__u32 entry = *entry_ptr;
			if ((entry & 0xffff) == port)
				return (entry >> 16) & 0xf;
			if (!entry)
				break;
		}
	} else if (protocol == IPPROTO_UDP) {
		for (int i = 0; i < 20; i++) {
			int idx = i;
			__u32 *entry_ptr = bpf_map_lookup_elem(&service_ports_udp, &idx);
			if (!entry_ptr) continue;
			__u32 entry = *entry_ptr;
			if ((entry & 0xffff) == port)
				return (entry >> 16) & 0xf;
			if (!entry)
				break;
		}
	}
	return 0;
}


/**
 * Return the team id that matches the given (BIG ENDIAN) IP address.
 * Returns IP_RANGE_GAMESERVER (=-1) for saarctf-internal IPs.
 * Returns IP_RANGE_UNKNOWN (=0) for other ips.
 * @param daddr
 * @return
 */
static inline int get_ip_range(__be32 daddr) {
	// 10.X.Y.Z
	if ((daddr & 0xff) != 10) return IP_RANGE_UNKNOWN;
	int x = (daddr >> 8) & 0xff;
	if (x >= 48) x -= 16;  // 10.48.Y.Z => 10.32.Y.Z
	if (x != 32 && x != 33) return IP_RANGE_UNKNOWN;
	int y = (daddr >> 16) & 0xff;
	if (y == 250) return IP_RANGE_GAMESERVER;
	if (y >= 1 && y <= 200)
		return (x - 32) * 200 + y;  // team ID
	return IP_RANGE_UNKNOWN;
}


static inline void mark_skb_basic(struct __sk_buff *skb, __u32 team_id) {
	skb->mark = (skb->mark & ~MASK_PER_PACKET) | (1 << OFFSET_PROCESSED_BIT) | team_id;
}

static inline void mark_skb_advanced(struct __sk_buff *skb, struct iphdr *ip, int port, __u32 team_id) {
	int tc = TC_UNKNOWN;
	int remote_team_id = get_ip_range(ip->daddr);
	if (remote_team_id == IP_RANGE_GAMESERVER) {
		tc = TC_GAMESERVER;
	} else if (remote_team_id == team_id) {
		tc = TC_TEAM_INTERNAL;
	} else if (remote_team_id != IP_RANGE_UNKNOWN) {
		tc = TC_TEAM_TEAM;
	}

	skb->mark = (skb->mark & ~MASK_PER_CONNECTION) | (tc << OFFSET_TRAFFIC_CLASS) | (get_service(ip->protocol, port) << OFFSET_SERVICE);
}

static inline void mark_skb_advanced_gameserver(struct __sk_buff *skb, struct iphdr *ip, int port) {
	// packet coming from a gameserver IP
	int tc = TC_UNKNOWN;
	if (get_ip_range(ip->daddr) > 0)
		tc = TC_GAMESERVER;

	skb->mark = (skb->mark & ~MASK_PER_CONNECTION) | (tc << OFFSET_TRAFFIC_CLASS) | (get_service(ip->protocol, port) << OFFSET_SERVICE);
}
