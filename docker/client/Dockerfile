FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG REDPANDA_DEB
RUN apt-get update -y
RUN apt-get install -y wget iptables ssh python3-pip sudo
RUN apt-get install -y iputils-ping vim tmux less openjdk-11-jdk maven
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /mnt/vectorized
RUN mkdir -p /home/ubuntu/.ssh
COPY id_ed25519.pub /home/ubuntu/.ssh/authorized_keys
COPY docker/client/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY control /mnt/vectorized/control
RUN chown ubuntu:ubuntu -R /mnt/vectorized/control
COPY $REDPANDA_DEB /mnt/vectorized/$REDPANDA_DEB
RUN dpkg --force-confold -i /mnt/vectorized/$REDPANDA_DEB
RUN systemctl disable redpanda
RUN systemctl disable wasm_engine
RUN pip3 install sh
RUN pip3 install flask
RUN pip3 install confluent_kafka
RUN mkdir -p /mnt/vectorized/workloads
COPY workloads/writing /mnt/vectorized/workloads/writing
RUN cd /mnt/vectorized/workloads/writing/kafka-clients && \
    mvn clean dependency:copy-dependencies package
RUN cd /mnt/vectorized/workloads/writing/list-offsets && \
    mvn clean dependency:copy-dependencies package
RUN chown ubuntu:ubuntu -R /mnt/vectorized/workloads/writing
CMD /mnt/vectorized/entrypoint.sh