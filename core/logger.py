import logging
import sys

def setup_logger(name: str = __name__) -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ))
        log.addHandler(handler)
    log.setLevel(logging.INFO)
    return log

logger = setup_logger("app")