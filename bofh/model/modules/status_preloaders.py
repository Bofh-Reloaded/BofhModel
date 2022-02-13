from concurrent.futures import ThreadPoolExecutor

from bofh.model.modules.constants import PREDICTION_LOG_TOPIC0_SYNC
from bofh.utils.misc import progress_printer, secs_to_human_repr
from bofh.utils.web3 import bsc_block_age_secs, Web3PoolExecutor


class EntitiesPreloader:

    def load(self):
        self.preload_exchanges()
        self.preload_tokens()
        start_token = self.graph.lookup_token(self.args.start_token_address)
        if not start_token:
            msg = "start_token not found: address %s is unknown or not of a token" % self.args.start_token_address
            self.log.error(msg)
            raise RuntimeError(msg)
        else:
            self.log.info("start_token is %s (%s)", start_token.symbol, start_token.address)
            self.graph.start_token = start_token
        self.preload_pools()
        self.graph.calculate_paths()
        self.preload_balances()
        self.log.info("  *********************************")
        self.log.info("  ***  GRAPH LOAD COMPLETE :-)  ***")
        self.log.info("  *********************************")

    def preload_exchanges(self):
        self.log.info("preloading exchanges...")
        ctr = 0
        with self.db as curs:
            for a in curs.list_exchanges():
                exc = self.graph.add_exchange(*a)
                assert exc is not None
                ctr += 1
        self.log.info("EXCHANGE set loaded, size is %r items", ctr)


    def preload_tokens(self):
        with self.db as curs:
            ctr = curs.count_tokens()
            print_progress = progress_printer(ctr, "preloading tokens {percent}% ({count} of {tot}"
                                                   " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                              , on_same_line=True)
            with print_progress:
                for args in curs.list_tokens():
                    tok = self.graph.add_token(*args)
                    if tok is None:
                        raise RuntimeError(
                            "integrity error: token address is already not of a token: id=%r, %r" % (id, args))
                    print_progress()
            self.log.info("TOKENS set loaded, size is %r items", print_progress.ctr)


    def preload_pools(self):
        with self.db as curs:
            ctr = curs.count_pools()
            print_progress = progress_printer(ctr, "preloading pools {percent}% ({count} of {tot}"
                                                   " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                              , on_same_line=True)
            with print_progress:

                for id, address, exchange_id, token0_id, token1_id in curs.list_pools():
                    print_progress()
                    # t0 = self.graph.lookup_token(token0_id)
                    # t1 = self.graph.lookup_token(token1_id)
                    # if not t0 or not t1:
                    #    if self.args.verbose:
                    #        self.log.warning("disabling pool %s due to missing or disabled affering token "
                    #                         "(token0=%r, token1=%r)", address, token0_id, token1_id)
                    #    continue
                    # exchange = self.graph.lookup_exchange(exchange_id)
                    # assert exchange is not None
                    # pool = self.graph.add_lp(id, address, exchange, t0, t1)
                    pool = self.graph.add_lp(id, address, exchange_id, token0_id, token1_id)
                    if pool is None:
                        if self.args.verbose:
                            self.log.warning("integrity error: pool address is already not of a pool: "
                                             "id=%r, %r", id, address)
                        continue
                    self.pools.add(pool)

            self.log.info("POOLS set loaded, size is %r items", print_progress.ctr)
            missing = print_progress.tot - print_progress.ctr
            if missing > 0:
                self.log.info("  \\__ %r over pool the total %r were not loaded due to "
                              "failed graph connectivity or other problems", missing, print_progress.tot)

    def preload_balances(self):
        if not self.preload_balances_from_db():
            self.download_reserves_snapshot_from_web3()
        if not self.args.do_not_update_reserves_from_chain:
            self.update_balances_from_web3()

    def preload_balances_from_db(self):
        with self.db as curs:
            latest_blocknr = curs.reserves_block_number
            current_blocknr = self.w3.eth.block_number
            age = current_blocknr-latest_blocknr
            if not latest_blocknr or age < 0:
                self.log.warning("unable to preload reserves from DB (latest block number not set in DB, or invalid)")
                return
            age_secs = bsc_block_age_secs(age)
            self.log.info("reserves DB snapshot is for block %u (%d blocks old), which is %s old"
                          , latest_blocknr
                          , age
                          , secs_to_human_repr(age_secs))
            if not self.args.force_reuse_reserves_snapshot:
                if age_secs > self.args.max_reserves_snapshot_age_secs:
                    self.log.warning("reserves DB snapshot is too old (older than --max_reserves_snapshot_age_secs=%r)"
                                     , self.args.max_reserves_snapshot_age_secs)
                    return
            else:
                self.log.warning(
                    "forcing reuse of existing reserves DB snapshot (as per --force_reuse_reserves_snapshot)")

            self.log.info("fetching LP reserves previously saved in db")
            nr = curs.execute("SELECT COUNT(1) FROM pool_reserves").get_int()
            with progress_printer(nr, "fetching pool reserves {percent}% ({count} of {tot}"
                                       " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                       , on_same_line=True) as print_progress:

                ok = 0
                disc = 0
                for poolid, reserve0, reserve1 in curs.execute("SELECT id, reserve0, reserve1 FROM pool_reserves").get_all():
                    pool = self.graph.lookup_lp(poolid)
                    print_progress()
                    if not pool:
                        if self.args.verbose:
                            self.log.debug("pool id not found: %r", poolid)
                        disc += 1
                        continue
                    pool.setReserves(reserve0, reserve1)
                    ok += 1
                self.log.info("%r records read, reserves loaded for %r pools, %r discarded"
                              , print_progress.ctr, ok, disc)
            return True

    def download_reserves_snapshot_from_web3(self):
        self.log.info("downloading a new reserves snapshot from Web3")
        print_progress = progress_printer(self.pools_ctr
                                          , "fetching pool reserves {percent}% ({count} of {tot}"
                                            " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                          , on_same_line=True)
        with Web3PoolExecutor(connection_uri=self.args.web3_rpc_url, max_workers=self.args.max_workers) as executor:
            self.log.info("concurrent reserves download via Web3:"
                     "\n\t- %r pool getReserve requests"
                     "\n\t- on Web3 servant at %s"
                     "\n\t- using %d workers"
                     "\n\t- each with a %d preload queue"
                      , self.pools_ctr
                      , self.args.web3_rpc_url
                      , self.args.max_workers
                      , self.args.chunk_size
                      )
            with self.db as curs:
                try:
                    currentBlockNr = self.w3.eth.block_number
                    def pool_addresses_iter():
                        for p in self.pools:
                            yield str(p.address)
                    for pool_addr, reserve0, reserve1, blockTimestampLast in executor.map(getReserves, pool_addresses_iter(), chunksize=self.args.chunk_size):
                        try:
                            if reserve0 is None or reserve1 is None:
                                continue
                            pair = self.graph.lookup_lp(pool_addr)
                            if not pair:
                                raise IndexError("unknown pool: %s" % pool_addr)
                            # reset pool reserves
                            pair.setReserves(reserve0, reserve1)
                            pool = self.graph.lookup_lp(pool_addr)
                            assert pool
                            curs.add_pool_reserve(pool.tag, reserve0, reserve1)
                            print_progress()
                        except:
                            self.log.exception("unable to query pool %s", pool_addr)
                        curs.reserves_block_number = currentBlockNr
                finally:
                    curs.reserves_block_number = currentBlockNr
            executor.shutdown(wait=True)

    def update_balances_from_web3(self, start_block=None):
        per_thread_queue_size = self.args.max_workers * 10
        current_block = self.w3.eth.block_number
        with self.db as curs:
            if start_block is None:
                start_block = curs.reserves_block_number
            latest_read = max(0, start_block-1)
            nr = current_block - latest_read
            if nr <= 0:
                return
            with progress_printer(nr, "rolling forward pool reserves {percent}% ({count} of {tot}"
                                      " eta={eta_secs:.0f}s at {rate:.0f} items/s) ..."
                                      , on_same_line=True) as print_progress:
                while True:
                    nr = current_block - latest_read
                    print_progress.tot = nr
                    if nr <= 0:
                        self.log.info("LP balances updated to current block (%u)", current_block)
                        break
                    target = min(latest_read+per_thread_queue_size, current_block+1)
                    with ThreadPoolExecutor(max_workers=self.args.max_workers) as executor:
                        for next_block in range(latest_read, target):
                            self.log.debug("loading reserves from block %r ... ", next_block)
                            if print_progress():
                                self.db.commit()
                            executor.submit(self.reserves_parse_blocknr, next_block)
                            latest_read = next_block
                        executor.shutdown()
                curs.reserves_block_number = latest_read

    def reserves_parse_blocknr(self, blocknr):
        block = self.w3.eth.get_block(blocknr)
        if not block:
            return
        txs = block.get("transactions")
        if not txs:
            return

        with self.db as curs:
            try:
                for txh in txs:
                    txr = self.w3.eth.get_transaction_receipt(txh)
                    if not txr:
                        continue
                    logs = txr.get("logs")
                    if not logs:
                        continue
                    for log in logs:
                        topics = log.get("topics")
                        address = log.get("address")
                        if address and topics and topics[0] == PREDICTION_LOG_TOPIC0_SYNC:
                            pool = self.graph.lookup_lp(address)
                            if not pool:
                                continue
                            self.update_pool_reserves_by_tx_sync_log(pool, log["data"], curs)
            except:
                self.db.rollback()
                raise



def getReserves(pool_address):
    """Invoke local execution of PoolContract.getReserves() on the EVM for the specified pool.
       Returns a tuple of (pool_address, reserve0, reserve1).

       This function is meant to be executed across an IPC multiprocess turk for massive parallelism.

       It reuses its web3 connection and assets to improve batch performance.

       It also avoids usage of the web3 framework which has shown flaky performances in the past. It does
       the dirty handling inline, and calls a remote RPC at the lowest possible level."""
    try:
        exe = getReserves.exe
        ioloop = getReserves.ioloop
        mid = getReserves.mid
    except AttributeError:
        exe = getReserves.exe = JSONRPCConnector.get_connection()
        ioloop = getReserves.ioloop = get_event_loop()
        mid = getReserves.mid = method_id("getReserves()")
    for i in range(4):  # make two attempts
        fut = exe.eth_call({"to": pool_address, "data": mid}, "latest")
        res = ioloop.run_until_complete(fut)
        # at this point "res" should be a long 0xhhhhh... byte hexstring.
        # it should be composed of 3 32-bytes big-endian values. In sequence:
        # - reserve0
        # - reserve1
        # - blockTimestampLast (mod 2**32) of the last block during which an interaction occured for the pair.
        try:
            reserve0, reserve1, blockTimestampLast = parse_data_parameters(res)
            return (pool_address
                    , reserve0
                    , reserve1
                    , blockTimestampLast
                    )
        except:
            pass
        print("invalid response (expected 96-byte hexstring):", res)
        return pool_address, None, None, None

