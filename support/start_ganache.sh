#!/bin/bash

PUBKEY=0x70F923DCe69C58e2E558E7f0a1F72D115450b933
PRIVKEY=0x6235b6a680b48559c9f36ca625cb1377b27c1250dace6c93aecacba492978a27
INITIAL_BALANCE=100000000000000000000

ganache-cli \
	--fork.url http://127.0.0.1:8545 \
	--server.ws -p 18545 \
	--wallet.accounts=${PRIVKEY},${INITIAL_BALANCE} \
        --wallet.unlockedAccounts=${PUBKEY}
