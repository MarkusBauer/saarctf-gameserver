#include "bpf-utils.h"
#include "traffic_marks.h"
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>


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
We mark incoming traffic with "from team x" (see traffic_marks.h).
Incoming traffic is first counted in total, incoming team traffic is counted when it is sent to another team.
Outgoing traffic is counted as team traffic or game traffic, depending on the mark.
*/



/*
struct bpf_elf_map SEC("maps") counting_map = {
	.type        = BPF_MAP_TYPE_ARRAY,
	.id          = 1,
	.size_key    = sizeof(__u32),
	.size_value  = sizeof(struct stats_for_team),
	.max_elem    = (MAX_TEAM_COUNT+1),
	.flags       = 0,
	.pinning     = PIN_GLOBAL_NS
};
BPF_ANNOTATE_KV_PAIR(counting_map, __u32, struct stats_for_team);
*/

struct {
	__uint(type, BPF_MAP_TYPE_ARRAY);
	__type(key, __u32);
	__type(value, struct stats_for_team);
	__uint(max_entries, MAX_TEAM_COUNT + 1);
	__uint(map_flags, 0);
	__uint(pinning, LIBBPF_PIN_BY_NAME);
} counting_map SEC(".maps");


static void handle_packet(struct __sk_buff *skb, int is_ingress, const __u64 packet_offset) {
	// Has IP packet?
	if (skb->data + packet_offset + sizeof(struct iphdr) > skb->data_end) {
		return;
	}

	// Handle only IP packets
	if (packet_offset == sizeof(struct ethhdr)) {
		struct ethhdr *eth = (void *) (__u64) skb->data;
		if (eth->h_proto != __constant_htons(ETH_P_IP))
			return;
	}

	// Read data from IP packet
	struct iphdr *ip = (void *) (__u64) (skb->data + packet_offset);
	__u32 team_id = get_ip_range(is_ingress ? ip->saddr : ip->daddr);
	__u32 size = skb->len >= packet_offset ? skb->len - packet_offset : 0;
	int is_other_team = !is_ingress && ((skb->mark & MASK_PROCESSED_BIT) != 0);
	int is_self_forward = !is_ingress && (skb->mark & MASK_PROCESSED_BIT) && (team_id == (skb->mark & MASK_TEAM_ID));

	// TCP present?
	int is_tcp = 0;
	int is_syn = 0;
	int is_synack = 0;
	int port = 0;
	if (ip->protocol == IPPROTO_TCP && skb->data + packet_offset + sizeof(struct iphdr) + sizeof(struct tcphdr) < skb->data_end) {
		struct tcphdr *tcp = (void *) (skb->data + packet_offset + sizeof(struct iphdr));
		is_tcp = 1;
		is_syn = tcp->syn;
		is_synack = is_syn && tcp->ack;
		port = __constant_ntohs(tcp->dest);
	} else if (ip->protocol == IPPROTO_UDP && skb->data + packet_offset + sizeof(struct iphdr) + sizeof(struct udphdr) < skb->data_end) {
		struct udphdr *udp = (void *) (skb->data + packet_offset + sizeof(struct iphdr));
		port = __constant_ntohs(udp->dest);
	}

	// save results
	struct stats_for_team *stats = bpf_map_lookup_elem(&counting_map, &team_id);
	if (stats) {
		struct counters *counter = &stats->counters[is_self_forward ? 4 : 2 * is_ingress + is_other_team];
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
		mark_skb_basic(skb, team_id);
		// ... and add more bits that might go to conntrack later
		if (!is_tcp || is_syn) {
			mark_skb_advanced(skb, ip, port, team_id);
		}
	} else if (skb->mark & MASK_PROCESSED_BIT && !is_self_forward) {
		// On egress of a team-routed packet, count the traffic as "team routed" for that team
		__u32 other_team_id = skb->mark & MASK_TEAM_ID;
		struct stats_for_team *stats = bpf_map_lookup_elem(&counting_map, &other_team_id);
		if (stats) {
			struct counters *counter = &stats->counters[3];
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
