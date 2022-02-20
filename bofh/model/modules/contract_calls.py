from functools import lru_cache
from os.path import join, dirname, realpath

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

    def call(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).call({"from": self.args.wallet_address})

    def transact(self, name, *args, address=None, abi=None):
        contract_instance = self.get_contract(address=address, abi=abi)
        self.w3.geth.personal.unlock_account(self.args.wallet_address, self.args.wallet_password, 120)
        callable = getattr(contract_instance.functions, name)
        return callable(*args).transact({"from": self.args.wallet_address})

    def add_funding(self, amount):
        caddr = self.args.contract_address
        log.info("approving %u of balance to on contract at %s, then calling adoptAllowance()", amount, caddr)
        self.transact("approve", caddr, amount, address=self.args.start_token_address, abi="IGenericFungibleToken")
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
        caddr = self.args.contract_address
        return self.call("balanceOf", caddr, address=self.args.start_token_address, abi="IGenericFungibleToken")

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
    def pack_args_payload(pools: list, fees: list, initialAmount: int, expectedAmount: int):
        assert len(pools) == len(fees)
        assert len(pools) <= 4
        args = []
        for addr, fee in zip(pools, fees):
            args.append(int(str(addr), 16) | (fee << 160))
        amounts_word = \
            ((initialAmount & 0xffffffffffffffffffffffffffffffff) << 0) | \
            ((expectedAmount & 0xffffffffffffffffffffffffffffffff) << 128)
        args.append(amounts_word)
        return args
