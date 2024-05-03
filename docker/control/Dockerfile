FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}
ARG WORKLOAD_CLUSTER_SIZE
ENV WORKLOAD_CLUSTER_SIZE=${WORKLOAD_CLUSTER_SIZE}

RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries
RUN apt update -y --fix-missing 
RUN apt upgrade -y
RUN apt install -f -y
RUN apt install -y curl wget iptables python3-pip gnuplot --fix-missing
RUN apt install -y iputils-ping vim tmux less ssh sudo --fix-missing
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /mnt/vectorized
RUN mkdir -p /home/ubuntu/.ssh
COPY id_ed25519 /home/ubuntu/.ssh/id_ed25519
RUN chown ubuntu:ubuntu -R /home/ubuntu/.ssh
COPY docker/control/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY docker/control/test.test.sh /mnt/vectorized/test.test.sh
COPY docker/control/test.suite.sh /mnt/vectorized/test.suite.sh
RUN pip3 install 'sh==1.14.3'
RUN pip3 install flask
RUN pip3 install pyyaml
RUN apt-get update && apt-get install -y --no-install-recommends gcc git libssl-dev g++ make
RUN cd /tmp && git clone --depth 1 --branch v1.9.0 https://github.com/edenhill/librdkafka.git && \
  cd librdkafka && \
  ./configure --prefix=/usr && make -j4 && make install && \
  cd ../ && rm -rf librdkafka
RUN pip3 install 'confluent_kafka==1.9.2'
COPY --chown=ubuntu:ubuntu harness /mnt/vectorized/harness
COPY --chown=ubuntu:ubuntu suites /mnt/vectorized/suites
CMD /mnt/vectorized/entrypoint.sh
