FROM ubuntu:18.04

ARG USERNAME=vscode
# On Linux, replace with your actual UID, GID if not the default 1000
ARG USER_UID=1000
ARG USER_GID=$USER_UID

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

# Install programs needed for developing
RUN true \
    && apt-get update \
    && apt-get -y install \
    curl \
    git \
    python3-mypy \
    ssh \
    sudo \
    vim \
    # Clean up
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/* \
    && true

# Create the user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && mkdir -p /home/$USERNAME/.vscode-server /home/$USERNAME/.vscode-server-insiders \
    && chown ${USER_UID}:${USER_GID} /home/$USERNAME/.vscode-server* \
    # [Optional] Add sudo support
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME
ENV PATH /home/vscode/.local/bin:$PATH

# Install dependencies for this project
RUN true \
    && apt-get update \
    && curl -sL https://deb.nodesource.com/setup_12.x | bash\
    && apt-get -y install --no-install-recommends \
    clang-7 \
    cmake \
    g++ \
    libev-dev \
    libhiredis-dev \
    libpq-dev \
    libssl-dev \
    nodejs \
    postgresql-client-10 \
    postgresql-server-dev-all \
    python2.7 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    # Clean up
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/* \
    && true

# Set the default user
USER $USERNAME
ENV FLASK_APP controlserver/app.py
