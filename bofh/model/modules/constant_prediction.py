from asyncio import sleep
from threading import Thread

from jsonrpc_base import TransportError
from jsonrpc_websocket import Server
from bofh_model_ext import TheGraph, log_level, log_register_sink, log_set_level, PathEvalutionConstraints

from bofh.model.database import Intervention
from bofh.model.modules.constants import PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP
from bofh.utils.web3 import parse_data_parameters


class ConstantPrediction:

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
        if initialAmount is None:
            initialAmount = self.args.initial_amount_min
        if expectedAmount is None:
            expectedAmount = (initialAmount * (1000000 + self.args.min_profit_target_ppm)) // 1000000
        return self.pack_args_payload(pools, feesPPM, initialAmount, expectedAmount)


    async def prediction_polling_task(self, constraint=None):
        # await self.polling_started.wait()
        if constraint is None:
            constraint = self.get_constraints()

        log_set_level(log_level.info)
        intervention = Intervention(origin="pred")
        intervention.blockNr = 0
        intervention.amountIn = int(str(constraint.initial_token_wei_balance))
        contract = self.get_contract()

        self.log.info("entering prediction polling loop...")
        server = Server(self.args.web3_rpc_url)
        try:
            await server.ws_connect()
            while True:  # self.polling_started.is_set():
                try:
                    result = await server.eth_consPredictLogs(0, 0, PREDICTION_LOG_TOPIC0_SYNC, PREDICTION_LOG_TOPIC0_SWAP)
                    blockNumber = result["blockNumber"]
                    if blockNumber <= intervention.blockNr:
                        continue
                    self.log.info("prediction results are in for block %r", blockNumber)
                    intervention.blockNr = blockNumber
                except TransportError:
                    # server disconnected
                    raise
                except:
                    self.log.exception("Error during eth_consPredictLogs() RPC execution")
                    continue
                with self.status_lock:
                    try:
                        try:
                            self.digest_prediction_payload(result)
                        except:
                            self.log.exception("Error during parsing of eth_consPredictLogs() results")
                        try:
                            matches = self.graph.evaluate_paths_of_interest(constraint)
                            for i, match in enumerate(matches):
                                if constraint.match_limit and i >= constraint.match_limit:
                                    return
                                intervention.amountIn = int(str(match.initial_balance))
                                intervention.amountOut = int(str(match.yieldPercent))
                                payload = self.pack_payload_from_pathResult(match)
                                intervention.calldata = str(contract.encodeABI("multiswap", payload))
                                with self.db as curs:
                                    curs.add_intervention(intervention)
                                #self.delayed_executor.post(self.on_profitable_path_execution, match)
                                print(len(self.delayed_executor.queue.queue))
                                #self.on_profitable_path_execution(match)
                        except:
                            self.log.exception("Error during execution of TheGraph::evaluate_paths_of_interest()")
                    finally:
                        # forget about predicted states. go back to normal
                        self.graph.clear_lp_of_interest()

                await sleep(self.args.pred_polling_interval * 0.001)
        except:
            self.log.exception("Error in prediction polling thread")
        finally:
            self.log.info("prediction polling loop terminated")
            await server.close()

    def digest_prediction_payload(self, payload):
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
                if self.args.verbose:
                    self.log.debug("unknown pool of interest: %s", address)
                continue
            topic0 = log["topic0"]
            if topic0 == PREDICTION_LOG_TOPIC0_SYNC:
                pool.enter_predicted_state(0, 0, 0, 0)
                try:
                    r0, r1 = parse_data_parameters(log["data"])
                    self.update_pool_reserves_by_tx_sync_log(pool, r0, r1)
                    self.graph.add_lp_of_interest(pool)
                except:
                    continue
                continue
            """
            if topic0 == PREDICTION_LOG_TOPIC0_SWAP:
                data = log["data"]
                try:
                    amount0In, amount1In, amount0Out, amount1Out = parse_data_parameters(data)
                except:
                    self.log.exception("unable to decode swap log data")
                    continue
                if self.args.verbose:
                    self.log.info("pool %r: %s(%s-%s) entering predicted state "
                                   "(amount0In=%r, amount1In=%r, amount0Out=%r, amount1Out=%r)"
                                   , address
                                   , pool.exchange.name
                                   , pool.token0.symbol
                                   , pool.token1.symbol
                                   , amount0In, amount1In, amount0Out, amount1Out
                                   )
                pool.enter_predicted_state(amount0In, amount1In, amount0Out, amount1Out)
                self.graph.add_lp_of_interest(pool)
                continue
            """
