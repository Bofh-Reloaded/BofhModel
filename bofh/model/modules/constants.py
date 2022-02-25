from os import environ

from eth_utils import to_checksum_address

from bofh.utils.web3 import log_topic_id

PREDICTION_LOG_TOPIC0_SWAP = log_topic_id("Swap(address,uint256,uint256,uint256,uint256,address)")
PREDICTION_LOG_TOPIC0_SYNC = log_topic_id("Sync(uint112,uint112)")
WBNB_address = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c" # id=2
TETHER_address = "0x55d398326f99059ff775485246999027b3197955" # id=4
START_TOKEN = to_checksum_address(environ.get("BOFH_START_TOKEN_ADDRESS", WBNB_address))

DEFAULT_SWAP_CONTRACT_ADDRESS = '0x89FD75CBb35267DDA9Bd6d31CdE86607a06dcFAa'
DEFAULT_BOFH_WALLET_ADDRESS = '0xF567a3B93AF6Aa3ef8A084014b2fbc2C17D21A00'
DEFAULT_BOFH_WALLET_PASSWD = 'skajhn398abn.SASA'

ENV_SWAP_CONTRACT_ADDRESS = environ.get("BOFH_CONTRACT_ADDRESS", None)
ENV_BOFH_WALLET_ADDRESS = environ.get("BOFH_WALLET_ADDRESS", None)
ENV_BOFH_WALLET_PASSWD = environ.get("BOFH_WALLET_PASSWD", None)
