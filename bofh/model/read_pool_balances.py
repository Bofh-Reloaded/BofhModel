"""
#### DEPRECATED ####
#### DO NOT USE ####

Superseded by bofh.collector, at https://github.com/Bofh-Reloaded/BofhCollector
"""
raise RuntimeError(__doc__)

## TODO: remove file


import json
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Thread

from web3 import Web3
from web3.middleware import geth_poa_middleware
from generic_contract import contract_abi


poolsDB = {}




def load_pools_lite(address, w3):
    poolsDB[p] = {}
    contract = None
    address = Web3.toChecksumAddress(address.lower())
    poolsDB[p][address] = {}
    if not contract:
        contract = w3.eth.contract(address=address, abi=contract_abi())
    else:
        # reuse the contract. no point in making objects up
        contract.address = address
    # print("LP: {0} {1}".format(contract.functions.symbol().call(), contract.address))
    reserves = contract.functions.getReserves().call()
    print(address, reserves)




def load_pools(p, pools, w3):
    poolsDB[p] = {}
    for pool in pools['wrapped'][p]['pools']:
        print(pool['address'])
        address = Web3.toChecksumAddress(pool['address'].lower())
        poolsDB[p][address] = {}
        contract = w3.eth.contract(address=address, abi=contract_abi())
        # print("LP: {0} {1}".format(contract.functions.symbol().call(), contract.address))
        token0 = w3.eth.contract(
            address=Web3.toChecksumAddress(
                contract.functions.token0().call().lower()
            ),
            abi=contract_abi())
        # print(" - Token0: {0}".format(token0.functions.symbol().call(), token0.address))
        token1 = w3.eth.contract(
            address=Web3.toChecksumAddress(
                contract.functions.token1().call().lower()
            ),
            abi=contract_abi())
        # print(" - Token1: {0}".format(token1.functions.symbol().call(), token1.address))
        reserves = contract.functions.getReserves().call()
        reserve0 = w3.fromWei(reserves[0], 'ether')
        reserve1 = w3.fromWei(reserves[1], 'ether')
        block_time_stamp = reserves[2]
        poolsDB[p][address]["token0"] = {
            "address": token0.address.lower(),
            "symbol": token0.functions.symbol().call(),
            "reserve": reserve0
        }
        poolsDB[p][address]["token1"] = {
            "address": token1.address.lower(),
            "symbol": token1.functions.symbol().call(),
            "reserve": reserve1
        }

        # print(' - Reserves: reserve0: {0} {1}, reserve1: {2} {3}, blockTimeStamp: {2}'.format(
        #    reserve0,
        #    token0.functions.symbol().call(),
        #    reserve1,
        #    token1.functions.symbol().call(),
        #    block_time_stamp)
        # )
        # r_reserve0 = token0.functions.balanceOf(contract.address).call()
        # r_reserve1 = token1.functions.balanceOf(contract.address).call()
        # print("Token: {0} with address {1}, has balance (using balanceOf) of: {2}".format(
        #    token0.functions.symbol().call(),
        #    token0.address,
        #    w3.fromWei(r_reserve0, 'ether')
        # ))
        # print("Token: {0} with address {1}, has balance (using balanceOf) of: {2}".format(
        #    token1.functions.symbol().call(),
        #    token1.address,
        #    w3.fromWei(r_reserve1, 'ether')
        # ))



def executor(queue):
    with ThreadPoolExecutor() as executor:
        print(1111)
        executor.map(load_pools_lite, iter(queue.get, None))

def load(w3):
    queue = Queue(maxsize=100)
    th = Thread(target=lambda: executor(queue))
    th.start()

    #executor = ThreadPoolExecutor(max_workers=6)
    #t = time.process_time()
    import gzip
    with gzip.open('../../test/bsc_pools.data.gz') as pool_data:
        data = json.loads(pool_data.read())
    for k, v in data.items():
        for ex_name, exchange in v.items():
            for pool in exchange["pools"]:
                queue.put(pool["address"])


if __name__ == "__main__":
    ht = Web3(Web3.HTTPProvider("http://localhost:8545"))
    ht.middleware_onion.inject(geth_poa_middleware, layer=0)
    (ht_load, ht_exec, ht_total) = load(ht)
    ws = Web3(Web3.WebsocketProvider("http://localhost:8546"))
    ws.middleware_onion.inject(geth_poa_middleware, layer=0)
    (ws_load, ws_exec, ws_total) = load(ws)

    print(f"HTTP      Load time {ht_load:.2} exec {ht_exec:.2} loaded {ht_total}")
    print(f"Websocket Load time {ws_load:.2} exec {ws_exec:.2} loaded {ws_total}")