#include "bpf-utils.h"
#include "traffic_marks.h"
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>

// ATTACH THIS SCRIPT TO THE INTERFACES TOWARDS THE GAMESERVER



static inline void handle_packet(struct __sk_buff *skb, const __u64 packet_offset) {
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

	// TCP present?
	int is_tcp = 0;
	int is_syn = 0;
	int port = 0;
	if (ip->protocol == IPPROTO_TCP && skb->data + packet_offset + sizeof(struct iphdr) + sizeof(struct tcphdr) < skb->data_end) {
		struct tcphdr *tcp = (void *) (skb->data + packet_offset + sizeof(struct iphdr));
		is_tcp = 1;
		is_syn = tcp->syn;
		port = tcp->dest;
	} else if (ip->protocol == IPPROTO_UDP && skb->data + packet_offset + sizeof(struct iphdr) + sizeof(struct udphdr) < skb->data_end) {
		struct udphdr *udp = (void *) (skb->data + packet_offset + sizeof(struct iphdr));
		port = udp->dest;
	}

	// ... and add more bits that might go to conntrack later
	if (!is_tcp || is_syn) {
		mark_skb_advanced_gameserver(skb, ip, port);
	}
}


SEC("traffic_stats_gameserver_ingress")
int handle_ingress(struct __sk_buff *skb) {
	__u32 offset = get_ip4_offset(skb);
	if (offset != NO_OFFSET)
		handle_packet(skb, offset);
	return TC_ACT_UNSPEC;
}


char __license[] SEC("license") = "GPL";
