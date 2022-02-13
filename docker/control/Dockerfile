FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG REDPANDA_DEB
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}
ARG WORKLOAD_CLUSTER_SIZE
ENV WORKLOAD_CLUSTER_SIZE=${WORKLOAD_CLUSTER_SIZE}
RUN apt-get update -y
RUN apt-get install -y curl wget iptables python3-pip gnuplot
RUN apt-get install -y iputils-ping vim tmux less ssh sudo
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /mnt/vectorized
RUN mkdir -p /home/ubuntu/.ssh
COPY id_ed25519 /home/ubuntu/.ssh/id_ed25519
RUN chown ubuntu:ubuntu -R /home/ubuntu/.ssh
COPY $REDPANDA_DEB /mnt/vectorized/$REDPANDA_DEB
RUN dpkg --force-confold -i /mnt/vectorized/$REDPANDA_DEB
RUN systemctl disable redpanda
RUN systemctl disable wasm_engine
COPY docker/control/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY docker/control/test.test.sh /mnt/vectorized/test.test.sh
COPY docker/control/test.suite.sh /mnt/vectorized/test.suite.sh
RUN pip3 install sh
RUN pip3 install flask
RUN pip3 install pyyaml
RUN pip3 install confluent_kafka
COPY --chown=ubuntu:ubuntu harness /mnt/vectorized/harness
COPY --chown=ubuntu:ubuntu suites /mnt/vectorized/suites
CMD /mnt/vectorized/entrypoint.sh
