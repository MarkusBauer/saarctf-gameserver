#include "bpf-utils.h"
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>



#define MAX_TEAM_COUNT 512



struct counters {
	__u64 packets;
	__u64 bytes;
	__u64 syns;
	__u64 syn_acks;
};

// ingress = up
// egress = down
struct stats_for_team {
	// struct counters egress_with_game;
	// struct counters egress_with_teams;
	// struct counters ingress_with_total;
	// struct counters ingress_with_teams;
	// struct counters forward_self;
	struct counters counters[5];
};


/*
We mark incoming traffic with "from team x" (mark 0x1???? with ????=team id).
Incoming traffic is first counted in total, incoming team traffic is counted when it is sent to another team.
Outgoing traffic is counted as team traffic or game traffic, depending on the mark.
*/



struct bpf_elf_map SEC("maps") counting_map = {
	.type        = BPF_MAP_TYPE_ARRAY,
	.id          = 1,
	.size_key    = sizeof(__u32),
	.size_value  = sizeof(struct stats_for_team),
	.max_elem    = (MAX_TEAM_COUNT+1),
	.flags       = 0,
	.pinning     = PIN_GLOBAL_NS
};




static inline void handle_packet(struct __sk_buff *skb, int is_ingress, const __u64 packet_offset) {
	// Has IP packet?
	if (skb->data + packet_offset + sizeof(struct iphdr) > skb->data_end) {
		return;
	}

	// Handle only IP packets
	if (packet_offset == sizeof(struct ethhdr)) {
		struct ethhdr *eth = (void*) (__u64) skb->data;
		if (eth->h_proto != __constant_htons(ETH_P_IP))
			return;
	}

	// Read data from IP packet
	__u32 team_id;
	__asm__("%0 = 0xdeadbeef" : "=r"(team_id)); // patched later with team id
	struct iphdr *ip  = (void*) (__u64) (skb->data + packet_offset);
	__u32 size = skb->len >= packet_offset ? skb->len - packet_offset : 0;
	int is_other_team = !is_ingress && ((skb->mark & 0x1ffff) != 0);
	int is_self_forward = !is_ingress && (skb->mark & 0x1ffff) && (team_id == (skb->mark & 0xffff));
	
	// TCP present?
	int is_syn = 0;
	int is_synack = 0;
	if (ip->protocol == IPPROTO_TCP && skb->data + packet_offset + sizeof(struct iphdr) + sizeof(struct tcphdr) < skb->data_end) {
		struct tcphdr *tcp = (void*) (skb->data + packet_offset + sizeof(struct iphdr));
		is_syn = tcp->syn;
		is_synack = is_syn && tcp->ack;
	}

	// save results
	struct stats_for_team *stats = bpf_map_lookup_elem(&counting_map, &team_id);
	if (stats) {
		struct counters* counter = &stats->counters[is_self_forward ? 4 : 2*is_ingress + is_other_team];
		__sync_fetch_and_add(&counter->packets, 1);
		__sync_fetch_and_add(&counter->bytes, size);
		if (is_syn) {
			if (is_synack) {
				__sync_fetch_and_add(&counter->syn_acks, 1);
			} else {
				__sync_fetch_and_add(&counter->syns, 1);
			}
		}
	}

	if (is_ingress) {
		// On ingress, mark packages as "from team X"
		skb->mark = (skb->mark & 0xfffe0000) | 1<<16 | team_id;
	} else if (skb->mark & 0x1ffff && !is_self_forward) {
		// On egress of a team-routed packet, count the traffic as "team routed" for that team
		__u32 other_team_id = skb->mark & 0xffff;
		struct stats_for_team *stats = bpf_map_lookup_elem(&counting_map, &other_team_id);
		if (stats) {
			struct counters* counter = &stats->counters[3];
			__sync_fetch_and_add(&counter->packets, 1);
			__sync_fetch_and_add(&counter->bytes, size);
			if (is_syn) {
				if (is_synack) {
					__sync_fetch_and_add(&counter->syn_acks, 1);
				} else {
					__sync_fetch_and_add(&counter->syns, 1);
				}
			}
		}
	}
}


SEC("traffic_stats_ingress")
int handle_ingress(struct __sk_buff *skb) {
	__u32 offset = get_ip4_offset(skb);
	if (offset != NO_OFFSET)
		handle_packet(skb, 1, offset);
	return TC_ACT_UNSPEC;
}


SEC("traffic_stats_egress")
int handle_egress(struct __sk_buff *skb) {
	__u32 offset = get_ip4_offset(skb);
	if (offset != NO_OFFSET)
		handle_packet(skb, 0, offset);
	return TC_ACT_UNSPEC;
}



char __license[] SEC("license") = "GPL";
