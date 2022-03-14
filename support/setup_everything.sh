#!/bin/bash

TOOLCHAIN_ROOT=$(dirname $(dirname $(which python3)))
SRC_ROOT=$(dirname $( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd ) )
BUILD_ROOT=$(realpath .)
if test "$SRC_ROOT" = "$BUILD_ROOT"
then
  BUILD_ROOT=$BUILD_ROOT/build
  mkdir -p $BUILD_ROOT
fi

export TOOLCHAIN_ROOT
export SRC_ROOT
export BUILD_ROOT

cd $BUILD_ROOT
bash "$SRC_ROOT/support/launch_cmake.sh" && \
  make && \
  make install && \
  ldconfig && \
  cd "$SRC_ROOT/bofh.utils" && python3 setup.py develop && \
  cd "$SRC_ROOT/bofh.contract" && python3 setup.py develop && \
  cd "$SRC_ROOT" && python3 setup.py develop

