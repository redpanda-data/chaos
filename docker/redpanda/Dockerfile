FROM debian:trixie
LABEL maintainer="Chris Lee <chris.lee@redpanda.com>"
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}

RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries
# single RUN so a failed `apt update` layer can never be cached separately
# from the installs; Error-Mode=any makes failed index fetches fatal instead
# of warnings
RUN apt update -y -o APT::Update::Error-Mode=any \
    && apt upgrade -y \
    && apt install -y wget iptables ssh sudo iputils-ping vim tmux less python3
# create the ubuntu user (the harness ssh convention) unless the base ships one
RUN id -u ubuntu >/dev/null 2>&1 || adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /home/ubuntu/.ssh
COPY --chown=ubuntu:ubuntu id_ed25519.pub /home/ubuntu/.ssh/authorized_keys
RUN mkdir -p /mnt/vectorized
COPY --chown=ubuntu:ubuntu control /mnt/vectorized/control
RUN chown ubuntu:ubuntu -R /mnt/vectorized/control
COPY docker/redpanda/entrypoint.sh /mnt/vectorized/entrypoint.sh
CMD /mnt/vectorized/entrypoint.sh
