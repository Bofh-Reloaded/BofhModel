#!/bin/bash

SRC_ROOT=$(dirname $( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd ) )
CONTRACTS=${SRC_ROOT}/bofh.contract/contracts/

remixd -s ${CONTRACTS} --remix-ide https://remix.ethereum.org
