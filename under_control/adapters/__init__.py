import importlib
import inspect
import pathlib
from abc import ABC, abstractmethod
from typing import Type, Dict

from fastapi import FastAPI

import under_control.config as config
import under_control.logger as log


class AdapterException(Exception):
    pass


class Adapter(ABC):
    """
    Abstract base class for the Adapter plugin classes.

    Adapters are used to integrate with third party services (the initial example here is the Kasa API).
    They are auto-registered from the `adapters` directory. Any files prefixed with 'adapter_' will be
    loaded and the application will search for any classes suffixed with `Adapter`.

    The adapter should handle initialising the third party API and registering any application end-points
    that are required.

    We place the reasonable limitation that only one instance of a givcn adapter class is permitted, to
    prevent clashes within the API namespace.
    """
    _instance_count: int = 0

    def __init__(self, cfg: Dict, app: FastAPI):
        self.cfg = cfg
        self._register_endpoints(app)

        if type(self)._instance_count > 0:
            raise Exception(
                f"Adapter {type(self).__name__} has already been loaded. Only a single instance is permitted")

        type(self)._instance_count += 1

    @abstractmethod
    def startup(self):
        """
        The startup method should initialise the API and perform any steps that need to be carried out before
        general use.
        """
        pass

    @abstractmethod
    def shutdown(self):
        """
        This will get fired when the app closes down, to perform any necessary clean up the 3rd party API.
        """
        pass

    @abstractmethod
    def _register_endpoints(self, app: FastAPI):
        """
        This method is called from the constructor to register endpoints against the FastAPI app. The easiest
        way to implement this is using nested functions, and the FastAPI @app.* annotations.
        :param app: The FastAPI app instance.
        """
        pass


# Dictionary of classes for the discovered adapter plugins.
_registered_adapters: Dict[str, Type] = {}

# Instantiated instances of adapter plugins.
_created_adapters: Dict[str, Adapter] = {}


def find_adapters():
    """
    Search the adapters directory for all adapter plugin classes.

    This will look for any python files prefixed with `adapter_`, then search them for classes suffixed
    'Adapter`.

    All detected classes will be registered in the module-level dictionary above, indexed by name.
    """

    def adapter_predicate(obj: Type):
        """
        The object should be a class, it's name should end with 'Adapter". Explicitly excludes
        classes named 'Adapter' to prevent detection of the base class.

        # TODO the 'Adapter' equality check is probably no longer required
        :param obj: The object loaded from the module to be checked.
        :return: True if the object is a class and named as an adapter, False otherwise.
        """
        return inspect.isclass(obj) and obj.__name__ != "Adapter" and obj.__name__.endswith("Adapter")

    adapters_path = pathlib.Path(__file__).parent
    files = [f"{__name__}.{f.stem}" for f in adapters_path.glob("adapter_*.py")]

    for f in files:
        module = importlib.import_module(f)
        for nm, cls in inspect.getmembers(module, adapter_predicate):
            _registered_adapters[nm] = cls
            log.logger.info(f"Registered adapter {nm}.")


def create(app: FastAPI):
    """
    Instantiate the adapter instances. For each class detected in `find_adapters`, check to see if there are any
    config parameters given for this adapter, and if so pass them to the adapter constructor.

    Instances are stored in the module level dict above, and indexed by their name, in lowercase, with the
    'Adapter' suffix removed.

    :param app: The FastAPI app instance, used for registering endpoints in the adapter constructor.
    """
    for cls_name, AdapterCls in _registered_adapters.items():
        # Try to get any config
        try:
            cfg = config.get(f"adapters.{cls_name}")
        except config.ConfigException as err:
            log.logger.warn(err)
            cfg = {}

        adapter_name = cls_name.replace("Adapter", "").lower()
        _created_adapters[adapter_name] = AdapterCls(cfg, app)
    log.logger.info("All adapters loaded")
    log.logger.debug(f"Adapters: {', '.join(a for a in _created_adapters)}")


def startup():
    """
    Run through all adapter instances and call their startup methods
    """
    for a in _created_adapters.values():
        a.startup()


def shutdown():
    """
    Run through all adapter instances and call their shutdown methods
    """
    for a in _created_adapters.values():
        a.shutdown()


def get(adapter_name: str) -> Adapter:
    """
    Get an adapter, based on its name.

    :param adapter_name: The name of the adapter
    :return: The adapter from the list. Will raise a KeyException if the adapter cannot be found.
    """
    return _created_adapters[adapter_name]
