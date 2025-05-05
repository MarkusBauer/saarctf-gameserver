FROM debian:trixie AS base

# optional: use a local apt-cacher-ng to speed things up
# RUN IP=172.17.0.1 && echo "Acquire::http { Proxy \"http://$IP:3142\"; }" > /etc/apt/apt.conf.d/01proxy

# install runtime libraries + headers
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends libev-dev libhiredis-dev libpq-dev libssl-dev && \
    apt-get clean



FROM base AS build

# install a C++ compiler and toolchain
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends g++ cmake make git ca-certificates postgresql-server-dev-all && \
    apt-get clean

RUN mkdir /src && mkdir /build

ADD benchmark /src/benchmark
ADD cmake /src/cmake
ADD src /src/src
ADD tests /src/tests
ADD CMakeLists.txt /src/

RUN cd /build && \
    cmake -DCMAKE_BUILD_TYPE=Release -DPostgreSQL_ADDITIONAL_VERSIONS=17 /src && \
    make -j4 flag-submission-server



FROM base AS runtime

COPY --from=build /build/flag-submission-server /flag-submission-server

WORKDIR /
USER nobody
EXPOSE 31337
ENV SAARCTF_CONFIG=/config.yaml

CMD ["/flag-submission-server", "31337", "8"]
