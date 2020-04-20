#include "bpf-utils.h"
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>



#define SAARSEC_MAX_TTL 48


static inline int anonymize_frame(struct __sk_buff *skb, const __u64 ipoffset) {
	// Has IP packet?
	if (skb->data + ipoffset + sizeof(struct iphdr) > skb->data_end) {
		return TC_ACT_UNSPEC;
	}

	// Limit TTL
	struct iphdr *ip  = (void*) (skb->data + ipoffset);
	__u32 protocol = ip->protocol;
	if (ip->ttl > SAARSEC_MAX_TTL) {
		// Checksum can only be repaired given 2 bytes. Take old/new of ttl+protocol (2x 1byte)
		__u8 new_ttl = SAARSEC_MAX_TTL;
		__u16 old = *((__u16*) &ip->ttl);
		__u16 new = old;
		((__u8*) &new)[0] = SAARSEC_MAX_TTL;
		bpf_l3_csum_replace(skb, ipoffset + offsetof(struct iphdr, check), old, new, 2);
		// Store only 1 byte (ttl)
		bpf_skb_store_bytes(skb, ipoffset + offsetof(struct iphdr, ttl), &new_ttl, 1, 0);
	}
	
	return TC_ACT_UNSPEC;
}


SEC("anonymize_traffic")
int handle_egress(struct __sk_buff *skb) {
	__u32 offset = get_ip4_offset(skb);
	if (offset == NO_OFFSET)
		return TC_ACT_UNSPEC;
	else
		return anonymize_frame(skb, offset);
}


char __license[] SEC("license") = "GPL";
