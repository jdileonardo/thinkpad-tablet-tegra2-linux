FROM ubuntu:20.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    bison flex libssl-dev device-tree-compiler libusb-1.0-0-dev \
    libcrypto++-dev pkg-config autoconf automake libtool python3 \
    python-is-python3 python2 python2-dev python3-dev python3-distutils swig \
    bc xz-utils cpio ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends libc6-dev-armhf-cross \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /work
