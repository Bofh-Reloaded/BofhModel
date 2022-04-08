from asyncio import sleep
from threading import Thread, Event
from jsonrpc_base import TransportError
from jsonrpc_websocket import Server

from bofh.model.modules.constants import PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP
from bofh.model.modules.loggers import Loggers
from bofh.utils.misc import checkpointer
from bofh.utils.web3 import parse_data_parameters

log = Loggers.constant_prediction


class ConstantPrediction:
    def start(self):
        self._constant_prediction_terminated = Event()
        self.search_opportunities_by_prediction_thread()
        self.pools_vs_txhashes = {}

    def stop(self):
        try:
            self._constant_prediction_terminated.set()
        except AttributeError:
            pass

    def join(self):
        th = getattr(self, "_search_opportunities_by_prediction_thread", None)
        if th:
            th.join()

    def search_opportunities_by_prediction_thread(self, constraint=None):
        self._search_opportunities_by_prediction_thread = Thread(
            target=lambda: self.ioloop.run_until_complete(self.prediction_polling_task(constraint))
            , daemon=True)
        self._search_opportunities_by_prediction_thread.start()

    def pack_payload_from_attack_plan(self, attack_plan, initialAmount=None, expectedAmount=None):
        path = attack_plan.path
        pools = []
        feesPPM = []
        for i in range(path.size()):
            swap = path.get(i)
            pools.append(str(swap.pool.address))
            feesPPM.append(swap.pool.feesPPM())
        if not initialAmount:
            initialAmount = int(str(attack_plan.initial_balance()))
        if expectedAmount is None:
            expectedAmount = int(str(attack_plan.final_balance()))
        if not expectedAmount:
            expectedAmount = 0
        return self.pack_args_payload(pools, feesPPM, initialAmount, expectedAmount)

    async def prediction_polling_task(self, constraint=None):
        # await self.polling_started.wait()
        if constraint is None:
            constraint = self.get_constraints()
        constraint.max_paths_per_lp = 1000
        constraint.max_path_len = 3

        log.info("entering prediction polling loop...")
        server = Server(self.args.web3_rpc_url)

        checkpoint = checkpointer(log.info, "constant_prediction checkpoint #{count}"
                                            ", uptime {elapsed_hr}"
                                            ", {events} events processed"
                                            ", {attacks} potential attacks routes spotted")

        events = 0
        attacks = 0
        stop_after_attacks = 1
        blockNumber = 0

        try:
            await server.ws_connect()
            while not self._constant_prediction_terminated.is_set():
                try:
                    result = await server.eth_consPredictLogs(0
                                                              , 0
                                                              , PREDICTION_LOG_TOPIC0_SYNC
                                                              , PREDICTION_LOG_TOPIC0_SWAP)
                    checkpoint(events=events, attacks=attacks)
                    if result["blockNumber"] <= blockNumber:
                        continue
                    blockNumber = result["blockNumber"]
                    log.debug("prediction results are in for block %r", blockNumber)
                except TransportError:
                    # server disconnected
                    raise
                except:
                    log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                with self.status_lock:
                    contract = self.get_contract()
                    prediction_key = self.graph.start_predicted_snapshot()
                    try:
                        try:
                            res = self.digest_prediction_payload(result, blockNumber, prediction_key)
                            if res: events += res
                        except:
                            log.exception("Error during parsing of eth_consPredictLogs() results")
                        try:
                            matches = self.graph.evaluate_paths_of_interest(constraint, prediction_key)
                            for i, attack_plan in enumerate(matches):

                                if constraint.match_limit and i >= constraint.match_limit:
                                    return
                                new_entry = self.post_attack_to_db(attack_plan=attack_plan
                                                                         , contract=contract
                                                                         , origin="pred")
                                if new_entry:
                                    if stop_after_attacks and attacks >= stop_after_attacks:
                                        continue
                                    attacks += 1
                                    self.execute_attack(attack_plan)
                                else:
                                    pass
                                    #log.debug("match having path id %r is already in mute_cache. "
                                    #          "activation inhibited", attack_plan.id())
                        except:
                            log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                    finally:
                        # forget about predicted states. go back to normal
                        self.pools_vs_txhashes.clear()
                        self.graph.terminate_predicted_snapshot(prediction_key)

                await sleep(self.args.pred_polling_interval * 0.001)
        except:
            log.exception("Error in prediction polling thread")
        finally:
            log.info("prediction polling loop terminated")
            await server.close()

    def post_attack_to_db(self, attack_plan, contract, origin):
        with self.attacks_db as curs:
            if curs.attack_is_in_mute_cache(
                    attack_plan=attack_plan
                    , cache_deadline=self.args.attacks_mute_cache_deadline
                    , max_size=self.args.attacks_mute_cache_size):
                return False
            tx, txindex, blockNumber = None, None, None
            for i in range(attack_plan.path.size()):
                swap = attack_plan.path.get(i)
                x = self.pools_vs_txhashes.pop(swap.pool.tag, None)
                if x:
                    tx, txindex, blockNumber = x
                    break
            curs.add_attack(attack_plan
                                  , origin=origin
                                  , blockNr=blockNumber
                                  , origin_tx=tx
                                  , contract_address=contract.address)
            return True

    def digest_prediction_payload(self, payload, blockNumber, prediction_key):
        events = 0
        logger = Loggers.constant_prediction
        assert isinstance(payload, dict)
        logs = payload["logs"]
        if not logs:
            return
        for log in logs:
            address = log["address"]
            if not address:
                continue
            pool = self.graph.lookup_lp(address, False)
            if not pool:
                logger.debug("unknown pool of interest: %s", address)
                continue
            tx = log["tx"]
            txindex = log["transactionIndex"]
            self.pools_vs_txhashes[pool.tag] = (tx, txindex, blockNumber)
            topic0 = log["topic0"]
            if topic0 == PREDICTION_LOG_TOPIC0_SYNC:
                events += 1
                try:
                    r0, r1 = parse_data_parameters(log["data"])
                    pool.set_predicted_reserves(prediction_key, r0, r1)
                except:
                    continue
                continue
        return events
