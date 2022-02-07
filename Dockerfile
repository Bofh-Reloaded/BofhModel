FROM ubuntu:focal AS builder
MAINTAINER neta <neta@logn.info>

ARG DEBIAN_FRONTEND=noninteractive

ENV BOOST_VERSION=1.77.0
ENV BOOST_VERSION_=1_77_0
ENV PYTHON_VERSION=3.8.11
ENV CMAKE_VERSION=3.21.0
ENV TOOLCHAIN_ROOT=/toolchain
ENV BUILD_ROOT=/build
ENV PATH=${TOOLCHAIN_ROOT}/bin:${PATH}
ENV SRC_ROOT=/src

COPY . ${SRC_ROOT}
RUN bash ${SRC_ROOT}/support/build_toolchain.sh
RUN bash ${SRC_ROOT}/support/setup_everything.sh
WORKDIR /status
COPY support/sqliterc /root/.sqliterc


ENTRYPOINT /bin/bash
#CMD  ["jupyter-lab", "--allow-root", "--ip", "0.0.0.0"]
CMD  ["sleep", "1000000"]

