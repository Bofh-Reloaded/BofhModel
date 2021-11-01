FROM ubuntu:focal AS builder
MAINTAINER neta <neta@logn.info>

ARG DEBIAN_FRONTEND=noninteractive

ENV BOOST_VERSION=1.77.0
ENV BOOST_VERSION_=1_77_0
ENV PYTHON_VERSION=3.8.11
ENV TOOLCHAIN_ROOT=/toolchain
ENV DEB_PACKAGES="build-essential git wget libffi-dev libbz2-dev libncurses-dev libsqlite3-dev libssl-dev uuid-dev zlib1g-dev libreadline-dev lzma-dev libgdbm-dev"
WORKDIR /src/

RUN apt-get -qq update && apt-get install -q -y software-properties-common
RUN add-apt-repository ppa:ubuntu-toolchain-r/test -y
RUN apt-get -qq update && apt-get install -qy ${DEB_PACKAGES}

RUN wget --max-redirect 3 https://boostorg.jfrog.io/artifactory/main/release/${BOOST_VERSION}/source/boost_${BOOST_VERSION_}.tar.gz
RUN mkdir -p ${TOOLCHAIN_ROOT} && tar zxf boost_${BOOST_VERSION_}.tar.gz -C ${TOOLCHAIN_ROOT} --strip-components=1

RUN wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz
RUN apt-get install -qy libffi-dev libbz2-dev libncurses-dev libsqlite3-dev libssl-dev uuid-dev zlib1g-dev libreadline-dev lzma-dev libgdbm-dev
RUN tar xvzf Python-${PYTHON_VERSION}.tgz && cd Python-${PYTHON_VERSION} && ./configure --prefix=${TOOLCHAIN_ROOT} --disable-shared --enable-static

RUN cd Python-${PYTHON_VERSION} && make -j4 && make install

RUN apt-get install -qy cmake g++

ENV PATH=${TOOLCHAIN_ROOT}/bin:${PATH}
WORKDIR /deploy
COPY CMakeLists.txt /deploy
COPY model /deploy/model
COPY test /deploy/test

RUN mkdir -p b && cd b && ls -l .. && cmake -DBOOST_ROOT=${TOOLCHAIN_ROOT} .. && make model
ENTRYPOINT /bin/bash
