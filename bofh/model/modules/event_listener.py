from json import loads
from logging import basicConfig
from threading import Thread, Event
from urllib.parse import urlparse, splitport

from twisted.internet.protocol import ReconnectingClientFactory
from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory
import json
from twisted.internet import reactor

from bofh.model.modules.loggers import Loggers
from bofh.utils.web3 import log_topic_id, parse_data_parameters


class SyncEventRealtimeTracker:
    def start(self):
        self._sync_event_rt_terminated = Event()
        self.track_swaps_thread()
        self.periodic_reserve_flush_thread()

    def stop(self):
        try:
            reactor.stop()
            self._sync_event_rt_terminated.set()
        except AttributeError:
            pass

    def join(self):
        th = getattr(self, "_track_swaps_thread", None)
        if th:
            th.join()
        th = getattr(self, "_periodic_reserve_flush_thread", None)
        if th:
            th.join()

    def track_swaps_thread(self):
        log = Loggers.realtime_sync_events
        if getattr(self, "_track_swaps_thread", None):
            log.error("track_swaps_thread already started")
        self._track_swaps_thread = Thread(target=self._track_swaps_task, daemon=True)
        self._track_swaps_thread.start()

    def _track_swaps_task(self):
        try:
            factory = EventLogListenerFactory(self, self.args.web3_rpc_url)
            factory.run()
        finally:
            del self._track_swaps_thread

    def periodic_reserve_flush_thread(self):
        log = Loggers.realtime_sync_events
        if getattr(self, "_periodic_reserve_flush_thread", None):
            log.error("periodic_reserve_flush_thread already started")
        self._periodic_reserve_flush_thread = Thread(target=self._periodic_reserve_flush_task, daemon=True)
        self._periodic_reserve_flush_thread.start()

    def _periodic_reserve_flush_task(self):
        log = Loggers.realtime_sync_events
        try:
            while True:
                if self._sync_event_rt_terminated.wait(timeout=60):
                    return
                if not self.reserves_update_batch:
                    continue
                log.debug("syncing %u pool reserves udates to db...", len(self.reserves_update_batch))
                with self.status_lock, self.db as curs:
                    curs.update_pool_reserves_batch(self.reserves_update_batch)
                    curs.reserves_block_number = self.reserves_update_blocknr
                    self.reserves_update_batch.clear()
        finally:
            del self._periodic_reserve_flush_thread

    def on_sync_event(self, address, reserve0, reserve1, blocknr):
        log = Loggers.realtime_sync_events
        with self.status_lock:
            pool = self.graph.lookup_lp(address)
            if pool:
                log.debug("use Sync event to update reserves of pool %r: %s(%s-%s), reserve=%r, reserve1=%r"
                              , pool.address
                              , pool.exchange.name
                              , pool.token0.symbol
                              , pool.token1.symbol
                              , reserve0
                              , reserve1)
                pool.setReserves(reserve0, reserve1)
                if not isinstance(reserve0, str): reserve0 = str(reserve0)
                if not isinstance(reserve1, str): reserve1 = str(reserve1)
                self.reserves_update_batch.append((reserve0, reserve1, pool.tag))
                if blocknr and blocknr > self.reserves_update_blocknr:
                    self.reserves_update_blocknr = blocknr



class EventLogClientProtocol(WebSocketClientProtocol):
    def onConnect(self, response):
        log = Loggers.realtime_sync_events
        log.info("Server connected: {0}".format(response.peer))

    def onConnecting(self, transport_details):
        log = Loggers.realtime_sync_events
        log.info("Connecting; transport details: {}".format(transport_details))
        return None  # ask for defaults

    TOPIC_SYNC = log_topic_id("Sync(uint112,uint112)")

    def onOpen(self):
        log = Loggers.realtime_sync_events
        log.info("WebSocket connection open.")
        # Change this part to the subscription you want to get
        self.sendMessage(json.dumps({"jsonrpc":"2.0","id": 1, "method": "eth_subscribe", "params": ["logs", {"topics": [self.TOPIC_SYNC]}]}).encode('utf8'))
        #self.sendMessage(json.dumps({"jsonrpc":"2.0","id": 1, "method": "eth_subscribe", "params": ["logs"]}).encode('utf8'))

    def onMessage(self, payload, isBinary):
        if isBinary:
            payload = payload.decode("utf-8")
        data = loads(payload)
        if not isinstance(data, dict):
            return
        params = data.get("params")
        if not isinstance(params, dict):
            return
        result = params.get("result")
        if not isinstance(result, dict):
            return
        blockNumber = result.get("blockNumber", None)
        if isinstance(blockNumber, str):
            if blockNumber.startswith("0x"):
                blockNumber = int(blockNumber, 16)
            else:
                blockNumber = int(blockNumber)
        address = result.get("address")
        topics = result.get("topics")
        hexdata = result.get("data")
        if not data or not address or not topics or not isinstance(topics, list):
            return
        if self.TOPIC_SYNC == topics[0]:
            reserve0, reserve1 = parse_data_parameters(hexdata)
            if self.factory.bofh:
                self.factory.bofh.on_sync_event(address, reserve0, reserve1, blockNumber)

    def onClose(self, wasClean, code, reason):
        log = Loggers.realtime_sync_events
        log.info("WebSocket connection closed: {0}".format(reason))


class EventLogListenerFactory(WebSocketClientFactory, ReconnectingClientFactory):
    def __init__(self, bofh, connection_url):
        self.bofh = bofh
        self.connection_url = connection_url
        super(EventLogListenerFactory, self).__init__(connection_url)

    protocol = EventLogClientProtocol

    def clientConnectionFailed(self, connector, reason):
        log = Loggers.realtime_sync_events
        log.info("Client connection failed .. retrying ..")
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        log = Loggers.realtime_sync_events
        log.info("Client connection lost .. retrying ..")
        self.retry(connector)

    def run(self):
        host, port = splitport(urlparse(self.connection_url).netloc)
        port = int(port)
        reactor.connectTCP(host, port, self)
        reactor.run(installSignalHandlers=False)

    def stop(self):
        reactor.stop()


if __name__ == '__main__':
    basicConfig(level="INFO")
    factory = EventLogListenerFactory(None, "ws://127.0.0.1:8546")
    factory.run()
