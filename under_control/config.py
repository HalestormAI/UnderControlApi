from typing import AnyStr, Optional, Any

import toml

_config = {}


class ConfigException(Exception):
    def __init__(self, message: AnyStr):
        super().__init__(message)


def get(item_path: AnyStr) -> Any:
    """
    We use the concept of 'paths' in config to refer to the nested indices of the config items.

    For example, 'Adapters.MyAdapter.MySetting' would look first look for the Adapters key, then assuming its
    value was a dict, it would look for the `MyAdapter` key, and so one.

    If an interim value is not a dict, or a key cannot be found, this will throw a ConfigException.

    # TODO: Handle list indexing - currently only digs into dicts. Workaround is to retrieve the list and index
    from the caller.

    :param item_path: The dot-separated path to the config item
    :return: The value at the path (could
    """

    if _config == {}:
        raise ConfigException("Config is empty - has the app setup run?")

    pieces = item_path.split('.')
    ptr = _config
    for p in pieces:

        if not isinstance(ptr, dict):
            raise ConfigException(f"Could not get config item {item_path} [{p}] - can only examine dict entries.")

        if p not in ptr:
            raise ConfigException(f"Could not get config item {item_path} - [{p}] is not in config path.")

        ptr = ptr[p]
    return ptr


def load(file_path: AnyStr):
    """
    Load the config from the TOML file at the given file path. Updates the module-level config dict with the
    valuesstored therein.

    Adds an internal state var `__file_path` to keep track of the config file that was loaded.

    :param file_path: Path to the config file.
    """
    with open(file_path) as fh:
        _config.update(toml.load(fh))
    _config['__file_path'] = file_path


def save(file_path: Optional[str] = None):
    """
    Save out the current config to the TOML file at the given file path.

    If the file path is not provided, it will use the internal state var added when the original config was
    loaded.

    Removes any internal state vars that might have been added to the config file (prefixed by `__`).
    :param file_path:
    :return:
    """
    if file_path is None:
        file_path = _config['__file_path']

    with open(file_path, 'w') as fh:
        toml.dump({k: v for k, v in _config.items() if not k.startswith('__')}, fh)
