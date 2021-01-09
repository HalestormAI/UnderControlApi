import sys
import logging
from typing import AnyStr

logger = logging.getLogger()


def setup_logger(log_level: AnyStr):
    logger.setLevel(log_level)
    out_handler = logging.StreamHandler(sys.stdout)
    out_handler.setFormatter(
        logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s', '%Y-%m-%d %H:%M:%S')
    )
    logger.addHandler(out_handler)
