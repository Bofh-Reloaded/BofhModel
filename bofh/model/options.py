from dataclasses import dataclass

from docopt import docopt

from bofh.model.modules.constants import START_TOKEN, ENV_SWAP_CONTRACT_ADDRESS, ENV_BOFH_WALLET_ADDRESS, \
    ENV_BOFH_WALLET_PASSWD
from bofh.utils.config_data import AttrDict, DynaConfig
from bofh.utils.misc import optimal_cpu_threads
from bofh.utils.web3 import JSONRPCConnector


STATEFUL_KEYS = AttrDict.deepcopy(
    bofh=dict(
        model=dict(
            status_db_dsn=("sqlite3://status.db", "DB status dsn connection string"),
            reports_db_dsn=("sqlite3://reports.db", "DB status dsn connection string"),
            attacks_db_dsn=("sqlite3://attacks.db", "DB status dsn connection string"),
            web3_rpc_url=(JSONRPCConnector.connection_uri(), "Web3 RPC connection URL"),
            max_workers=(optimal_cpu_threads(), "number of RPC data ingest workers, default one per hardware thread"),
            chunk_size=(100, "preloaded work chunk size per each worker"),
            runner=dict(
                pred_polling_interval=(1000, "Web3 prediction polling internal in millisecs"),
                max_reserves_snapshot_age_secs=(7200, "max age of usable LP reserves DB snapshot "
                                                      "(refuses to preload from DB if older)"),
                force_reuse_reserves_snapshot=(False, "disregard --max_reserves_snapshot_age_secs "
                                                      "(use for debug purposes, avoids download of reserves)"),
                do_not_update_reserves_from_chain=(False, "do not attempt to forward an existing reserves "
                                                          "DB snapshot to the latest known block"),
                initial_amount_min=(0, "min initial amount of start_token considered for swap operation"),
                initial_amount_max=(10 ** 16, "max initial amount of start_token considered for swap operation"),
                path_estimation_amount=(10 ** 16, "amount used for initial exploratory search of profitable paths"),
                min_profit_target_ppm=(10000, "minimum viable profit target in parts per million (relative)"),
                max_profit_target_ppm=(None, "minimum viable profit target in parts per million (relative)"),
                min_profit_target_amount=(0, "amount used for initial exploratory search of profitable paths"),
                attacks_mute_cache_size=(0, "size of the known attacks mute cache"),
                attacks_mute_cache_deadline=(3600, "expunge time deadline of the known attacks mute cache"),
                loglevel=("INFO", "set subsystem loglevel"),
                database=dict(loglevel=("INFO", "set subsystem loglevel")),
                model=dict(loglevel=("INFO", "set subsystem loglevel")),
                preloader=dict(loglevel=("INFO", "set subsystem loglevel")),
                contract=dict(loglevel=("INFO", "set subsystem loglevel")),
                realtime_sync_events=dict(loglevel=("INFO", "set subsystem loglevel")),
                constant_prediction=dict(loglevel=("INFO", "set subsystem loglevel")),
                path_evaluation=dict(loglevel=("INFO", "set subsystem loglevel")),
                logfile=(None, "log to file"),
                cli=(False, "preload status and stop at CLI (for debugging)"),
            ),
            start_token_address=(START_TOKEN, "start_token_address"),
            contract_address=(ENV_SWAP_CONTRACT_ADDRESS, "set contract counterpart address. "
                                                         "Reads BOFH_CONTRACT_ADDRESS envvar"),
            wallet_address=(ENV_BOFH_WALLET_ADDRESS, "funding wallet address. "
                                                     "Reads from BOFH_WALLET_ADDRESS envvar"),
            wallet_password=(ENV_BOFH_WALLET_PASSWD, "funding wallet address. "
                                                     "Reads BOFH_WALLET_PASSWD envvar"),
        ),
    )
)



@dataclass
class Args(DynaConfig("bofh.model.runner")):
    """DOCSTRING"""
    STATEFUL_KEYS=STATEFUL_KEYS


a=Args()