FROM ubuntu:focal AS builder
MAINTAINER neta <neta@logn.info>

ARG DEBIAN_FRONTEND=noninteractive

ENV BOOST_VERSION=1.77.0
ENV BOOST_VERSION_=1_77_0
ENV PYTHON_VERSION=3.8.11
ENV CMAKE_VERSION=3.21.0
ENV TOOLCHAIN_ROOT=/toolchain
ENV BUILD_ROOT=/build
ENV BOOST_COMPONENTS=--with-python
ENV DEB_PACKAGES="build-essential git wget libffi-dev libbz2-dev libncurses-dev libsqlite3-dev libssl-dev uuid-dev zlib1g-dev libreadline-dev lzma-dev libgdbm-dev g++"
ENV PATH=${TOOLCHAIN_ROOT}/bin:${PATH}


RUN apt-get -qq update && apt-get install -q -y software-properties-common && \
    add-apt-repository ppa:ubuntu-toolchain-r/test -y && \
    apt-get -qq update && apt-get install -qy ${DEB_PACKAGES}

# Some crucial things are build out of sources because specific versions may
# not be available from the distro / because we want to be distro agnostic.

# Install CMake. Binary because it takes a LOOONG time to do otherwise
RUN mkdir -p ${TOOLCHAIN_ROOT} \
    && wget https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz -O - \
    | tar xvzf - --strip-components=1 -C ${TOOLCHAIN_ROOT}

# Install Python3
WORKDIR ${BUILD_ROOT}
RUN mkdir -p python \
    && wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz -O - \
    | tar xvzf - -C python
WORKDIR ${BUILD_ROOT}/python
RUN cd * && ./configure --prefix=${TOOLCHAIN_ROOT} --enable-static --disable-shared && make -j4 && make install

# Install Boost
WORKDIR ${BUILD_ROOT}
RUN mkdir -p boost \
    && wget https://boostorg.jfrog.io/artifactory/main/release/${BOOST_VERSION}/source/boost_${BOOST_VERSION_}.tar.gz -O - \
    | tar xvzf - -C boost
WORKDIR ${BUILD_ROOT}/boost
RUN cd */tools/build \
    && sh bootstrap.sh \
    && ./b2 install --prefix=${TOOLCHAIN_ROOT} \
    && cd ${BUILD_ROOT}/boost/* \
    && echo 'import toolset : using ; using python : : ${TOOLCHAIN_ROOT}/bin/python3 ;' >user-config.jam \
    && ./tools/build/b2 --user-config=user-config.jam install \
        variant=debug \
        link=shared \
        threading=multi \
        runtime-link=shared \
        --prefix=${TOOLCHAIN_ROOT} \
        --build-type=minimal \
        --layout=system \
        ${BOOST_COMPONENTS}


FROM ubuntu:focal AS final
MAINTAINER neta <neta@logn.info>

ENV TOOLCHAIN_ROOT=/toolchain
ENV SRC_ROOT=/src
ENV DEB_PACKAGES="build-essential bzip2 libncurses5 sqlite3 zlib1g libreadline5 lzma libgdbm6 g++ less inetutils-ping"
ENV PATH=${TOOLCHAIN_ROOT}/bin:${PATH}

COPY --from=builder ${TOOLCHAIN_ROOT} ${TOOLCHAIN_ROOT}
RUN apt-get -qq update && apt-get install -q -y software-properties-common && \
    add-apt-repository ppa:ubuntu-toolchain-r/test -y && \
    apt-get -qq update && apt-get install -qy ${DEB_PACKAGES}
RUN echo ${TOOLCHAIN_ROOT}/lib>/etc/ld.so.conf.d/toolchain.conf && ldconfig
RUN python3 -m pip install jupyterlab

WORKDIR ${SRC_ROOT}

# preload Python requirements ^^"
# It's unnecessary but avoids continuously rerunning this image step as I hack the sources
COPY requirements.txt ${SRC_ROOT}
COPY bofh.collector/requirements.txt ${SRC_ROOT}/requirements2.txt
RUN pip3 install -r requirements.txt \
    && pip3 install -r requirements2.txt

## Now add the rest of the sources 'n stuff
#COPY \
#    CMakeLists.txt \
#    docker-compose.yml \
#    setup.py \
#    ${SRC_ROOT}
#COPY bofh ${SRC_ROOT}/bofh
#COPY test ${SRC_ROOT}/test
#COPY support ${SRC_ROOT}/support
#COPY bofh.collector ${SRC_ROOT}/bofh.collector
#COPY src ${SRC_ROOT}/src



ENV BUILD_ROOT=/build
WORKDIR ${BUILD_ROOT}
EXPOSE 8888
#RUN bash ${SRC_ROOT}/support/launch_cmake.sh

ENTRYPOINT /bin/bash
#CMD  ["jupyter-lab", "--allow-root", "--ip", "0.0.0.0"]
CMD  ["sleep", "1000000"]

