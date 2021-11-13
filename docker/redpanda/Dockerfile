FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG REDPANDA_DEB
ARG USER_ID
RUN apt-get update -y
RUN apt-get install -y wget iptables ssh sudo
RUN apt-get install -y iputils-ping vim tmux less
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /home/ubuntu/.ssh
COPY id_ed25519.pub /home/ubuntu/.ssh/authorized_keys
RUN mkdir -p /mnt/vectorized
COPY control /mnt/vectorized/control
RUN chown ubuntu:ubuntu -R /mnt/vectorized/control
COPY docker/redpanda/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY $REDPANDA_DEB /mnt/vectorized/$REDPANDA_DEB
RUN dpkg --force-confold -i /mnt/vectorized/$REDPANDA_DEB
RUN systemctl disable redpanda
RUN systemctl disable wasm_engine
CMD /mnt/vectorized/entrypoint.sh