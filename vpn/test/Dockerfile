FROM debian:bullseye

RUN apt-get update && \
    apt-get install -y  \
    	openvpn htop nano sudo screen \
    	net-tools iptables bash-completion iputils-ping tcpdump netcat-openbsd \
    	python3 socat && \
    apt-get clean && \
    echo 'shell "/bin/bash"' > ~/.screenrc

CMD ["socat", "-T", "10", "tcp-l:12345,reuseaddr,fork", "exec:'/bin/cat'"]
