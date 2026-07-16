FROM debian:trixie
LABEL maintainer="Chris Lee <chris.lee@redpanda.com>"
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}
ARG WORKLOAD_CLUSTER_SIZE
ENV WORKLOAD_CLUSTER_SIZE=${WORKLOAD_CLUSTER_SIZE}
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /usr/local/bin/uv
# venv on PATH for docker exec/CMD; ssh and sudo -i sessions reach it through
# the /usr/local/bin/python3 wrapper installed after uv sync below
ENV VIRTUAL_ENV=/opt/venv \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries
# single RUN so a failed `apt update` layer can never be cached separately
# from the installs; Error-Mode=any makes failed index fetches fatal instead
# of warnings
RUN apt update -y -o APT::Update::Error-Mode=any \
    && apt upgrade -y \
    && apt install -y curl wget iptables python3 gnuplot \
       iputils-ping vim tmux less ssh sudo \
    && apt install -y --no-install-recommends gcc git libssl-dev g++ make python3-dev
# create the ubuntu user (the harness ssh convention) unless the base ships one
RUN id -u ubuntu >/dev/null 2>&1 || adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /mnt/vectorized
RUN mkdir -p /home/ubuntu/.ssh
COPY id_ed25519 /home/ubuntu/.ssh/id_ed25519
RUN chown ubuntu:ubuntu -R /home/ubuntu/.ssh
COPY docker/control/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY docker/control/test.test.sh /mnt/vectorized/test.test.sh
COPY docker/control/test.suite.sh /mnt/vectorized/test.suite.sh
RUN cd /tmp && git clone --depth 1 --branch v1.9.0 https://github.com/edenhill/librdkafka.git && \
  cd librdkafka && \
  ./configure --prefix=/usr && make -j4 && make install && \
  cd ../ && rm -rf librdkafka
# confluent-kafka builds from source against the librdkafka installed above
COPY pyproject.toml uv.lock /mnt/vectorized/
# wrapper (not a symlink: CPython resolves symlinks past the venv) so login
# shells, sshd, and sudo secure_path all get the venv python
RUN cd /mnt/vectorized && uv sync --frozen && \
  printf '#!/bin/sh\nexec /opt/venv/bin/python3 "$@"\n' > /usr/local/bin/python3 && \
  chmod +x /usr/local/bin/python3
COPY --chown=ubuntu:ubuntu harness /mnt/vectorized/harness
COPY --chown=ubuntu:ubuntu suites /mnt/vectorized/suites
CMD /mnt/vectorized/entrypoint.sh
