from typing import AnyStr

from fastapi import FastAPI

from under_control import adapters
import under_control.config as config
import under_control.logger as log


def setup(config_path: AnyStr):
    """
    Initial module setup - load the config, set up the logger and find all the adapter plugins
    :param config_path: The path to the config file
    """
    config.load(config_path)

    logger.setup_logger(config.get('logging.level'))

    adapters.find_adapters()
    log.logger.info("Setup complete")


def start(app: FastAPI):
    """
    Run through all the adapter plugins found during setup and instantiate them.

    Then trigger startup on all plugins.
    :param app: The FastIO app, used to register plugin endpoints.
    """
    adapters.create(app)
    adapters.startup()


def stop():
    """
    Run through all the adapter plugins found during setup and shut them down.
    """
    adapters.shutdown()
