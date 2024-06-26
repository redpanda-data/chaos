FROM ubuntu:20.04
LABEL maintainer="Denis Rystsov <denis@vectorized.io>"
ARG DEBIAN_FRONTEND=noninteractive
ARG USER_ID
ARG REDPANDA_CLUSTER_SIZE
ENV REDPANDA_CLUSTER_SIZE=${REDPANDA_CLUSTER_SIZE}

RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries
RUN apt update -y --fix-missing 
RUN apt upgrade -y
RUN apt install -f -y
RUN apt install -y wget iptables ssh python3-pip sudo --fix-missing
RUN apt install -y iputils-ping vim tmux less openjdk-11-jdk maven --fix-missing
RUN adduser --disabled-password --gecos "" ubuntu
RUN usermod -aG sudo -u $USER_ID ubuntu
RUN echo "ubuntu ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers
RUN mkdir -p /mnt/vectorized
RUN mkdir -p /home/ubuntu/.ssh
COPY --chown=ubuntu:ubuntu id_ed25519.pub /home/ubuntu/.ssh/authorized_keys
COPY docker/client/entrypoint.sh /mnt/vectorized/entrypoint.sh
COPY --chown=ubuntu:ubuntu control /mnt/vectorized/control
RUN chown ubuntu:ubuntu -R /mnt/vectorized/control
RUN pip3 install 'sh==1.14.3'
RUN pip3 install flask
RUN apt-get update && apt-get install -y --no-install-recommends gcc git libssl-dev g++ make
RUN cd /tmp && git clone --depth 1 --branch v1.9.0 https://github.com/edenhill/librdkafka.git && \
  cd librdkafka && \
  ./configure --prefix=/usr && make -j4 && make install && \
  cd ../ && rm -rf librdkafka
RUN pip3 install 'confluent_kafka==1.9.2'
RUN mkdir -p /mnt/vectorized/workloads
COPY workloads /mnt/vectorized/workloads
RUN cd /mnt/vectorized/workloads/uber && \
    mvn clean dependency:copy-dependencies package
RUN chown ubuntu:ubuntu -R /mnt/vectorized/workloads
CMD /mnt/vectorized/entrypoint.sh
