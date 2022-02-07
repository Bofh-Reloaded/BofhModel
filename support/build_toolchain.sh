#!/bin/bash

export BOOST_VERSION=${BOOST_VERSION-1.77.0}
export BOOST_VERSION_=$(echo $BOOST_VERSION | tr . _)
export PYTHON_VERSION=${PYTHON_VERSION-3.8.11}
export CMAKE_VERSION=${CMAKE_VERSION-3.21.0}
export TOOLCHAIN_ROOT=${TOOLCHAIN_ROOT-/toolchain}
export BUILD_ROOT=${BUILD_ROOT-~/build}
export BOOST_COMPONENTS=--with-python
export DEB_PACKAGES="build-essential git wget libffi-dev libbz2-dev libncurses-dev libsqlite3-dev libssl-dev uuid-dev zlib1g-dev libreadline-dev lzma-dev libgdbm-dev g++ gdb less inetutils-ping vim sqlite3"
export PATH=${TOOLCHAIN_ROOT}/bin:${PATH}
export SRC_ROOT=${SRC_ROOT-.}


# Exit on any error
set -euxo pipefail

mkdir -p ${TOOLCHAIN_ROOT} ${BUILD_ROOT}

# Install ${DEB_PACKAGES}
apt-get -qq update
apt-get install -q -y software-properties-common
add-apt-repository ppa:ubuntu-toolchain-r/test -y
apt-get -qq update
apt-get install -qy ${DEB_PACKAGES}

# Some crucial things are build out of sources because specific versions may
# not be available from the distro / because we want to be distro agnostic.

# Install CMake. Binary because it takes a LOOONG time to do otherwise
wget https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz -O - \
    | tar xvzf - --strip-components=1 -C ${TOOLCHAIN_ROOT}

# Install Python3
cd ${BUILD_ROOT}
mkdir -p python
 wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz -O - \
    | tar xvzf - -C python
cd ${BUILD_ROOT}/python/*
./configure --prefix=${TOOLCHAIN_ROOT} --enable-static --disable-shared
make -j4
make install
${TOOLCHAIN_ROOT}/bin/python3 -m pip install --upgrade pip

# Install Boost
cd ${BUILD_ROOT}
mkdir -p boost
wget https://boostorg.jfrog.io/artifactory/main/release/${BOOST_VERSION}/source/boost_${BOOST_VERSION_}.tar.gz -O - \
    | tar xvzf - -C boost
cd ${BUILD_ROOT}/boost/*/tools/build
sh bootstrap.sh
./b2 install --prefix=${TOOLCHAIN_ROOT}
cd ${BUILD_ROOT}/boost/*
echo 'import toolset : using ; using python : : ${TOOLCHAIN_ROOT}/bin/python3 ;' >user-config.jam
./tools/build/b2 --user-config=user-config.jam install \
        variant=debug \
        link=shared \
        threading=multi \
        runtime-link=shared \
        --prefix=${TOOLCHAIN_ROOT} \
        --build-type=minimal \
        --layout=system \
        ${BOOST_COMPONENTS}

echo ${TOOLCHAIN_ROOT}/lib>/etc/ld.so.conf.d/toolchain.conf
ldconfig

# preload Python requirements ^^"
# It's unnecessary but avoids continuously rerunning this image step as I hack the sources
python3 -m pip install jupyterlab
pip3 install -r ${SRC_ROOT}/requirements.txt
pip3 install -r ${SRC_ROOT}/bofh.utils/requirements.txt


