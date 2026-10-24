FROM ubuntu:latest
RUN apt-get update && apt-get upgrade -y && apt install -y make \
    gcc g++ \
    git ca-certificates \
    zlib1g-dev libglusterfs-dev \
    libgoogle-perftools-dev \
    libaio-dev \
    libcunit1-dev \
    libcurl4-openssl-dev \
    libfl-dev \
    libgnutls28-dev \
    libnuma-dev \
    libnfs-dev \
    valgrind \
    libisal-dev \
    libiscsi-dev \
    libnbd-dev \
    libpmem-dev \
    librbd-dev \
    libtcmalloc-minimal4 \
    libibverbs-dev \
    librdmacm-dev \
    pkg-config --no-install-recommends
   # nvidia-cuda-dev - optional, for GDS
WORKDIR /tmp/build
RUN git clone https://github.com/axboe/fio
WORKDIR /tmp/build/fio
RUN ./configure --enable-libiscsi --enable-libnbd && make && make install
COPY job.fio /etc/fio/job.fio
WORKDIR /data
CMD ["fio", "/etc/fio/job.fio"]

