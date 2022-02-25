from functools import lru_cache
from os.path import join, dirname, realpath

from eth_utils import to_checksum_address
from hexbytes import HexBytes
from web3.types import TxReceipt

from bofh.model.modules.loggers import Loggers
from bofh.utils.deploy_contract import deploy_contract
from web3.exceptions import ContractLogicError

from bofh.utils.solidity import get_abi, find_contract, add_solidity_search_path
from bofh.utils.web3 import Web3Connector, JSONRPCConnector


log = Loggers.contract_activation

add_solidity_search_path(join(dirname(dirname(dirname(dirname(realpath(__file__))))), "bofh.contract", "contracts"))


class ContractCalling:
    @property
    def w3(self):
        try:
            return self.__w3
        except AttributeError:
            self.__w3 = Web3Connector.get_connection(self.args.web3_rpc_url)
        return self.__w3

    @property
    def jsonrpc(self):
        try:
            return self.__jsonrpc
        except AttributeError:
            self.__jsonrpc = JSONRPCConnector.get_connection(self.args.web3_rpc_url)
        return self.__jsonrpc

    @lru_cache
    def get_contract(self, address=None, abi=None):
        if address is None:
            address = self.args.contract_address
        if abi is None:
            abi = "BofhContract"
        return self.w3.eth.contract(address=address, abi=get_abi(abi))

    def getCoinBalance(self, address):
        return self.w3.eth.getBalance(to_checksum_address(address))

    def getTokenBalance(self, address, token):
        if hasattr(token, "address"):
            token = token.address
        token = to_checksum_address(token)
        address = to_checksum_address(address)
        return self.call(function_name="balanceOf"
                         , from_address=None
                         , to_address=token
                         , abi="IGenericFungibleToken"
                         , call_args=(address,)
                         )

    def unlock_wallet(self, address, password, timeout=120):
        address = to_checksum_address(address)
        self.w3.geth.personal.unlock_account(address, password, timeout)

    def transact(self, function_name, from_address, to_address, abi=None, call_args=None, gas=None) -> HexBytes:
        to_address = to_checksum_address(to_address)
        if from_address:
            from_address = to_checksum_address(from_address)
            d_from = {"from": from_address}
        else:
            d_from = {}
        if call_args is None:
            call_args = ()
        if gas is not None:
            d_from.update(gas=gas)
        contract_instance = self.get_contract(address=to_address, abi=abi)
        callable = getattr(contract_instance.functions, function_name)
        return callable(*call_args).transact(d_from)

    def estimate_gas(self, function_name, from_address, to_address, abi=None, call_args=None) -> int:
        to_address = to_checksum_address(to_address)
        if from_address:
            from_address = to_checksum_address(from_address)
            d_from = {"from": from_address}
        else:
            d_from = {}
        if call_args is None:
            call_args = ()
        contract_instance = self.get_contract(address=to_address, abi=abi)
        callable = getattr(contract_instance.functions, function_name)
        return callable(*call_args).estimateGas(d_from)

    def transact_and_wait(self, function_name, from_address, to_address, abi=None, call_args=None, gas=None) -> TxReceipt:
        txhash = self.transact(function_name=function_name, from_address=from_address, to_address=to_address, abi=abi, call_args=call_args, gas=gas)
        return self.w3.eth.wait_for_transaction_receipt(txhash)

    def get_calldata(self, function_name, from_address=None, to_address=None, abi=None, call_args=None):
        to_address = to_checksum_address(to_address)
        if call_args is None:
            call_args = ()
        contract_instance = self.get_contract(address=to_address, abi=abi)
        return contract_instance.encodeABI(function_name, call_args)

    def call(self, function_name, from_address, to_address, abi=None, call_args=None):
        to_address = to_checksum_address(to_address)
        if from_address:
            from_address = to_checksum_address(from_address)
            d_from = {"from": from_address}
        else:
            d_from = {}
        if call_args is None:
            call_args = ()
        contract_instance = self.get_contract(address=to_address, abi=abi)
        callable = getattr(contract_instance.functions, function_name)
        return callable(*call_args).call(d_from)


    def _call(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).call({"from": self.args.wallet_address})

    def _transact(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        self.w3.geth.personal.unlock_account(self.args.wallet_address, self.args.wallet_password, 120)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).transact({"from": self.args.wallet_address})

    def add_funding(self, amount, to_address, token):
        if hasattr(token, "address"):
            token = token.address
        token = to_checksum_address(token)
        to_address = to_checksum_address(to_address)
        log.info("approving %u of balance to on contract at %s, then calling adoptAllowance()", amount, to_address)
        self.transact("approve", to_address, amount, address=token, abi="IGenericFungibleToken")
        self.transact("adoptAllowance")

    def repossess_funding(self):
        caddr = self.args.contract_address
        log.info("calling withdrawFunds() on contract at %s", caddr)
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        self.transact("withdrawFunds")

    def kill_contract(self):
        caddr = self.args.contract_address
        self.transact("approve", caddr, 0, address=self.args.start_token_address, abi="IGenericFungibleToken")
        log.info("calling kill() on contract at %s", caddr)
        self.transact("kill")

    def contract_balance(self):
        return self.getTokenBalance(self.args.contract_address, self.args.start_token_address)

    def redeploy_contract(self, fpath="BofhContract.sol"):
        try:
            self.kill_contract()
        except ContractLogicError:
            log.exception("unable to kill existing contract at %s", self.args.contract_address)
        fpath = find_contract(fpath)
        log.info("attempting to deploy contract from %s", fpath)
        self.args.contract_address = deploy_contract(self.args.wallet_address, self.args.wallet_password, fpath,
                                                self.args.start_token_address)
        log.info("new contract address is established at %s", self.args.contract_address)

    @staticmethod
    def pack_args_payload(pools: list, fees: list, initialAmount: int, expectedAmount: int, stop_after_pool=None):
        assert len(pools) == len(fees)
        assert len(pools) <= 4
        args = []
        for i, (addr, fee) in enumerate(zip(pools, fees)):
            val = int(str(addr), 16) | (fee << 160)
            if stop_after_pool == i:
                val |= (1 << 180) # set this bit. on Debug contracts, it triggers OPT_BREAK_EARLY
            args.append(val)
        amounts_word = \
            ((initialAmount & 0xffffffffffffffffffffffffffffffff) << 0) | \
            ((expectedAmount & 0xffffffffffffffffffffffffffffffff) << 128)
        args.append(amounts_word)

        return [args]
