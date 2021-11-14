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

cd $SRC_ROOT \
	&& python3 setup.py develop \
	&& cd bofh.collector \
	&& python3 setup.py develop

echo $TOOLCHAIN_ROOT/lib >/etc/ld.so.conf.d/toolchian.conf && ldconfig
