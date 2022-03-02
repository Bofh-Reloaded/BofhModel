from asyncio import sleep
from collections import defaultdict
from threading import Thread, Event
from time import time

from eth_utils import to_checksum_address
from jsonrpc_base import TransportError
from jsonrpc_websocket import Server

from bofh.model.database import Intervention, InterventionStep
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

    def pack_payload_from_pathResult(self, pr, initialAmount=None, expectedAmount=None):
        path = pr.path
        pools = []
        feesPPM = []
        for i in range(path.size()):
            swap = path.get(i)
            pools.append(str(swap.pool.address))
            feesPPM.append(swap.feesPPM())
        if not initialAmount:
            initialAmount = int(str(pr.initial_balance()))
        if not initialAmount:
            initialAmount = self.args.initial_amount_min
        if expectedAmount is None:
            initialAmount = int(str(pr.final_balance()))
        if not expectedAmount:
            expectedAmount = 0
        return self.pack_args_payload(pools, feesPPM, initialAmount, expectedAmount)

    async def prediction_polling_task(self, constraint=None):
        # await self.polling_started.wait()
        if constraint is None:
            constraint = self.get_constraints()

        contract = self.get_contract()
        intervention = Intervention(origin="pred")
        intervention.blockNr = 0
        intervention.contract = str(to_checksum_address(self.args.contract_address))
        intervention.amountIn = int(str(constraint.initial_token_wei_balance))

        log.info("entering prediction polling loop...")
        server = Server(self.args.web3_rpc_url)

        checkpoint = checkpointer(log.info, "constant_prediction checkpoint #{count}"
                                            ", uptime {elapsed_hr}"
                                            ", {events} events processed"
                                            ", {interventions} potential attacks routes spotted")
        events = 0
        interventions = 0
        try:
            await server.ws_connect()
            while not self._constant_prediction_terminated.is_set():
                try:
                    result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP)
                    checkpoint(events=events, interventions=interventions)
                    blockNumber = result["blockNumber"]
                    if blockNumber <= intervention.blockNr:
                        continue
                    log.debug("prediction results are in for block %r", blockNumber)
                    intervention.blockNr = blockNumber
                except TransportError:
                    # server disconnected
                    raise
                except:
                    log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                with self.status_lock:
                    try:
                        try:
                            res = self.digest_prediction_payload(result)
                            if res: events += res
                        except:
                            log.exception("Error during parsing of eth_consPredictLogs() results")
                        try:
                            matches = self.graph.evaluate_paths_of_interest(constraint, True)
                            for i, match in enumerate(matches):

                                if constraint.match_limit and i >= constraint.match_limit:
                                    return
                                new_entry = self.post_intervention_to_db(intervention, match, contract)
                                if new_entry:
                                    self.execute_attack(intervention.tag)
                                    interventions += 1
                                else:
                                    log.debug("match having path id %r is already in mute_cache. "
                                              "activation inhibited", match.id())
                        except:
                            log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                    finally:
                        # forget about predicted states. go back to normal
                        self.graph.clear_lp_of_interest()

                await sleep(self.args.pred_polling_interval * 0.001)
        except:
            log.exception("Error in prediction polling thread")
        finally:
            log.info("prediction polling loop terminated")
            await server.close()

    def post_intervention_to_db(self, intervention, match, contract):
        intervention.path_id = match.path.id()
        intervention.origin_ts = time()
        with self.attacks_db as curs:
            if curs.intervention_is_in_mute_cache(
                    intervention
                    , cache_deadline=self.args.attacks_mute_cache_deadline
                    , max_size=self.args.attacks_mute_cache_size):
                return False
            intervention.amountIn = int(str(match.initial_balance()))
            intervention.amountOut = int(str(match.final_balance()))
            payload = self.pack_payload_from_pathResult(match)
            intervention.calldata = str(contract.encodeABI("multiswap", payload))
            intervention.steps = steps = []
            tx, tid = None, None
            for i in range(match.path.size()):
                swap = match.path.get(i)
                pool = swap.pool
                try:
                    tx, tid = self.pools_vs_txhashes[pool.tag]
                except KeyError:
                    pass
                steps.append(InterventionStep(pool_id=pool.tag
                                              , pool_addr=pool.address
                                              , reserve0=int(str(pool.reserve0))
                                              , reserve1=int(str(pool.reserve1))
                                              , amountIn=int(str(match.balance_before_step(i)))
                                              , amountOut=int(str(match.balance_after_step(i)))
                                              , tokenIn_addr=str(swap.tokenSrc.address)
                                              , tokenOut_addr=str(swap.tokenDest.address)
                                              , tokenIn_id=swap.tokenSrc.tag
                                              , tokenOut_id=swap.tokenDest.tag
                                              , feePPM=swap.feesPPM()
                                              ))
            intervention.origin_tx = tx
            curs.add_intervention(intervention)
            return True

    def digest_prediction_payload(self, payload):
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
            pool = self.graph.lookup_lp(address)
            if not pool:
                logger.debug("unknown pool of interest: %s", address)
                continue
            tx = log["tx"]
            txindex = log["transactionIndex"]
            self.pools_vs_txhashes[pool.tag] = (tx, txindex)
            topic0 = log["topic0"]
            if topic0 == PREDICTION_LOG_TOPIC0_SYNC:
                events += 1
                pool.enter_predicted_state()
                try:
                    r0, r1 = parse_data_parameters(log["data"])
                    pool.set_predicted_reserves(r0, r1)
                    self.graph.add_lp_of_interest(pool)
                except:
                    continue
                continue
        return events
