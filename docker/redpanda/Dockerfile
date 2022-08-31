FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}
RUN apt update -y --fix-missing 
RUN apt upgrade -y
RUN apt install -f -y
RUN apt install -y wget iptables ssh sudo --fix-missing
RUN apt install -y iputils-ping vim tmux less --fix-missing
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /home/ubuntu/.ssh
COPY --chown=ubuntu:ubuntu id_ed25519.pub /home/ubuntu/.ssh/authorized_keys
RUN mkdir -p /mnt/vectorized
COPY --chown=ubuntu:ubuntu control /mnt/vectorized/control
RUN chown ubuntu:ubuntu -R /mnt/vectorized/control
COPY docker/redpanda/entrypoint.sh /mnt/vectorized/entrypoint.sh
CMD /mnt/vectorized/entrypoint.sh
