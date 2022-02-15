__all__ = [ "Loggers" ]

from logging import *
from bofh_model_ext import log_level, log_set_level


class ModelLogAdapter:
    def __init__(self, name="bofh_model", level=INFO):
        self.levels = {
            log_level.trace: DEBUG,
            log_level.debug: DEBUG,
            log_level.info: INFO,
            log_level.warning: WARNING,
            log_level.error: ERROR,
        }
        self.name2levels = {
            "TRACE": log_level.trace,
            "DEBUG": log_level.debug,
            "INFO": log_level.info,
            "WARNING": log_level.warning,
            "ERROR": log_level.error,
        }
        self.log = getLogger(name)
        self.log.setLevel(level)

    def setLevel(self, level):
        self.log.setLevel(level)
        if isinstance(level, str):
            level = level.upper()
            level = self.name2levels.get(level, level)
        log_set_level(level)

    def __call__(self, lvl, msg):
        self.log.log(self.levels.get(lvl, INFO), msg)


class Loggers:
    runner = getLogger("runner")
    model = ModelLogAdapter()
    preloader = getLogger("preloader")
    contract_activation = getLogger("contract_activation")
    realtime_sync_events = getLogger("realtime_sync_events")
    constant_prediction = getLogger("constant_prediction")
    path_evaluation = getLogger("path_evaluation")


