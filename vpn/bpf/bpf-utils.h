#ifndef BPF_UTILS_H
#define BPF_UTILS_H

#include <stddef.h>
#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/in.h>
#include <linux/if_ether.h>

#define SEC(NAME) __attribute__((section(NAME), used))


// BPF helper functions
static int (*bpf_skb_store_bytes)(void *ctx, int off, void *from, int len, int flags) = (void *) BPF_FUNC_skb_store_bytes;
static int (*bpf_l3_csum_replace)(void *ctx, int off, int from, int to, int flags) = (void *) BPF_FUNC_l3_csum_replace;
static int (*bpf_l4_csum_replace)(void *ctx, int off, int from, int to, int flags) = (void *) BPF_FUNC_l4_csum_replace;
static void *(*bpf_map_lookup_elem)(void *map, const void *key) = (void *) BPF_FUNC_map_lookup_elem;
static void *(*bpf_map_update_elem)(void *map, const void *key, const void* value, int flags) = (void *) BPF_FUNC_map_update_elem;



// How to define a map for tc
struct bpf_elf_map {
	__u32 type;
	__u32 size_key;
	__u32 size_value;
	__u32 max_elem;
	__u32 flags;
	__u32 id;
	__u32 pinning;
	__u32 inner_id;
	__u32 inner_idx;
};

// Object pinning settings
#define PIN_NONE       0
#define PIN_OBJECT_NS  1
#define PIN_GLOBAL_NS  2


static inline __u16 nstohs(__be16 ns) {
	return (ns >> 8)|(ns << 8);
}

static inline __u32 nstoh(__be32 ns) {
	return (ns >> 24) | ((ns >> 8)&0xff00) | ((ns << 8)&0xff0000) | (ns << 24);
}


// IP4 => eth or raw ip4
// ETH => eth with ip4 or eth without ip4 or different

#define NO_OFFSET 0xffffffff

static inline __u32 get_ip4_offset(struct __sk_buff *skb) {
	// Detect ethernet frame + IP4
	if (skb->data + sizeof(struct ethhdr)+1 >= skb->data_end) return NO_OFFSET;
	struct ethhdr* eth = (void*) (__u64) skb->data;
	if (eth->h_proto == __constant_htons(ETH_P_IP)) return sizeof(struct ethhdr);

	// detect raw ip4
	if (skb->protocol == __constant_htons(ETH_P_IP)) {
		// IP4 set, IP4 without eth given
		__u8 ip1 = *((__u8*)(__u64) skb->data);
		if (((ip1 & 0xf0) == 0x40) && ((ip1 & 0x0f) >= 5)) return 0;
	}

	// unknown packaging
	return NO_OFFSET;
}


#endif