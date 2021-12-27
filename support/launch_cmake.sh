#!/bin/bash

if test -z "$TOOLCHAIN_ROOT"
then
        echo "missing evvar: TOOLCHAIN_ROOT. Perhaps not running inside Docker?"
        exit 1
fi

if test -z "$SRC_ROOT"
then
        echo "missing evvar: SRC_ROOT. Perhaps not running inside Docker?"
        exit 1
fi

if test -z "$BUILD_ROOT"
then
        echo "missing evvar: BUILD_ROOT. Perhaps not running inside Docker?"
        exit 1
fi

# Look for actual boost directory

echo "**** build SOURCES at $SRC_ROOT "
echo "**** using TOOLCHAIN at $TOOLCHAIN_ROOT"
echo "**** in BUILD directory $BUILD_ROOT "

mkdir -p $BUILD_ROOT
cd $BUILD_ROOT \
    && cmake ${SRC_ROOT} \
        -DBOOST_ROOT=${TOOLCHAIN_ROOT} \
        -DPYTHON_ROOT=${TOOLCHAIN_ROOT} \
        -DCMAKE_INSTALL_PREFIX=${TOOLCHAIN_ROOT} \
        -DCMAKE_BUILD_TYPE=Debug \
        -DCMAKE_INSTALL_PREFIX=${TOOLCHAIN_ROOT}