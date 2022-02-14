from json import loads
from logging import getLogger, basicConfig
from pprint import pprint
from urllib.parse import urlparse, splitport

from twisted.internet.protocol import ReconnectingClientFactory
from autobahn.twisted.websocket import WebSocketClientProtocol, \
    WebSocketClientFactory
import json
from twisted.internet import reactor

from bofh.utils.web3 import log_topic_id, parse_data_parameters

log = getLogger("bofh.model.modules.event_listener")


class EventLogClientProtocol(WebSocketClientProtocol):
    def onConnect(self, response):
        log.info("Server connected: {0}".format(response.peer))

    def onConnecting(self, transport_details):
        log.info("Connecting; transport details: {}".format(transport_details))
        return None  # ask for defaults

    TOPIC_SYNC = log_topic_id("Sync(uint112,uint112)")

    def onOpen(self):
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
        log.info("WebSocket connection closed: {0}".format(reason))


class EventLogListenerFactory(WebSocketClientFactory, ReconnectingClientFactory):
    def __init__(self, bofh, connection_url):
        self.bofh = bofh
        self.connection_url = connection_url
        super(EventLogListenerFactory, self).__init__(connection_url)

    protocol = EventLogClientProtocol

    def clientConnectionFailed(self, connector, reason):
        log.info("Client connection failed .. retrying ..")
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
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
