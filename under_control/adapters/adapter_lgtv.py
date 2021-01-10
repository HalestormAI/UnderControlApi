import re
import subprocess
from enum import auto
from typing import Dict, List, Tuple, Union, Optional, Type

from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from pywebostv.connection import WebOSClient
from pywebostv.controls import (
    SystemControl,
    MediaControl,
    ApplicationControl,
    InputControl
)

import under_control.config as config
import under_control.logger as log
from under_control import adapters
from under_control.utils import AutoName

HostType = str


class LGTVException(Exception):
    pass


# Since the different commands use different controllers, we'll split them into several enums, which can then
# be used to direct the command. An important note is that this means we can only support any given command
# name on a single controller (e.g. cannot have Media.Up and Input.Up).
#
# This isn't currently a problem...

class MediaCommand(AutoName):
    """
    The auto() value will be the lower-case of the enum item's name (see utils.AutoName)
    """
    VOLUME_UP: str = auto()
    VOLUME_DOWN: str = auto()
    GET_VOLUME: str = auto()
    SET_VOLUME: str = auto()
    MUTE: str = auto()

    PLAY: str = auto()
    PAUSE: str = auto()
    STOP: str = auto()
    REWIND: str = auto()
    FAST_FORWARD: str = auto()


class AppCommand(AutoName):
    LAUNCH: str = auto()
    LIST_APPS: str = auto()
    GET_CURRENT: str = auto()


class SystemCommand(AutoName):
    NOTIFY: str = auto()
    POWER_OFF: str = auto()


class InputCommand(AutoName):
    UP: str = auto()
    DOWN: str = auto()
    LEFT: str = auto()
    RIGHT: str = auto()

    OK: str = auto()
    BACK: str = auto()
    EXIT: str = auto()

    HOME: str = auto()
    DASH: str = auto()
    INFO: str = auto()


GenericCommand = Union[InputCommand, MediaCommand, AppCommand, SystemCommand]


class LGTVCommander:
    """
    Wrapper for the WebOsClient to handle command funnelling.
    """

    def __init__(self, client):
        self.client: WebOSClient = client

        self._system: SystemControl = SystemControl(client)
        self._media: MediaControl = MediaControl(client)
        self._app: ApplicationControl = ApplicationControl(client)
        self._inp: InputControl = InputControl(client)

    def send_command(self, command: GenericCommand, message: str = None) -> Union[str, Dict]:
        """
        For a given command object, this will choose the Control class and instance, then send the command
        using it.

        For certain commands with messages, it will perform some setup on the message to make it compatible
        with the host.

        :param command: The enum for the chosen command
        :param message: An optional message.
        :return: The response from the host.
        """
        is_input: bool = isinstance(command, InputCommand)

        HandlerCls: Type
        handler: GenericCommand
        if is_input:
            HandlerCls = InputControl
            handler = self._inp
            self._inp.connect_input()
        elif isinstance(command, MediaCommand):
            HandlerCls = MediaControl
            handler = self._media
        elif isinstance(command, AppCommand):
            HandlerCls = ApplicationControl
            handler = self._app
        elif isinstance(command, SystemCommand):
            HandlerCls = SystemControl
            handler = self._system
        else:
            raise NotImplementedError(f"Couldn't find command handler for command: {command}")

        # Command names in the API are dynamically registered using the __getattr__ private function
        cmd_func = HandlerCls.__getattr__(handler, command.name.lower())

        if message is None:
            response = cmd_func()
        else:
            if command == MediaCommand.SET_VOLUME:
                message = int(message)
            elif command == AppCommand.LAUNCH:
                # The host expects an application object - we'll query the host for it here
                apps = self._app.list_apps()
                message = [x for x in apps if message in x["title"].lower()][0]
            elif command == MediaCommand.MUTE:
                message = message == "True"

            response = cmd_func(message)

        if is_input:
            self._inp.disconnect_input()

        return response


class CommandRequestModel(BaseModel):
    name: GenericCommand
    message: Optional[str] = None


class LGTVAdapter(adapters.Adapter):

    def __init__(self, cfg, app: FastAPI):
        super().__init__(cfg, app)
        self._devices: Dict = {}
        self._connections: Dict[str, LGTVCommander] = {}
        self._online: List[str] = []

    def startup(self):
        # self._update_online_status()
        pass

    def shutdown(self):
        self._disconnect_all()

    @property
    def devices(self) -> Dict:
        """
        Retrieve all the devices listed in the config.

        NOTE: Makes no guarantee of connection or validity.
        :return: List of all devices from the config
        """
        return self.cfg['devices']

    @staticmethod
    def _device_connect(name: str, ip: HostType, key: str = None) -> LGTVCommander:
        """
        Connect to a WebOS LGTV client, check pairing status and attempt pairing if not paired.

        :param name: The human-readable name of the device
        :param ip:   The IP address for the device
        :param key:  The pairing key provided by the device. None if not paired.
        :return: The connected & registered client.
        """
        client = WebOSClient(ip)
        try:
            client.connect()

            store = {} if key is None else {'client_key': key}

            if key is None:
                log.logger.info(f"LGTV {name} is not paired - attempting to pair.")

            has_registered = False
            client_status = None
            for client_status in client.register(store):
                has_registered |= client_status == WebOSClient.REGISTERED

            if not has_registered:
                raise LGTVException(f"Could not pair with LGTV {name} [Status: {client_status}].")

            return LGTVCommander(client)

        except TimeoutError:
            raise LGTVException(f"Timed out connecting to LGTV {name}.")
        except Exception as e:
            if str(e) == "Failed to register.":
                raise LGTVException(f"Failed to pair LGTV {name}.")
            raise e

    def _disconnect_all(self):
        """
        Run through all connected hosts and disconnect them, then remove from the connections dict.
        """
        c: LGTVCommander
        for c in self._connections.values():
            c.client.close_connection()

        self._connections.clear()

    @staticmethod
    def _ping_device_unix(name: str, ip: HostType) -> bool:
        """
        Attempt to ping a given device to see if it is connected.

        :param name: The name of the device (used for debugging)
        :param ip:   The IP address of the device to ping
        :return:     True if the ping was successful, False otherwise.

        # TODO: Unix only - this won't play ball on Windows due to argument. Should be less lazy and differentiate...
        """
        ping = subprocess.Popen(["ping", "-c", "1", ip], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, error = ping.communicate()
        groups = re.search(r"\d packets transmitted, (\d) packets received", out.decode())

        if groups is None:
            log.logger.warn(f"Could not parse `ping` output for LGTV [{name}] - unable to check connectivity")
            log.logger.debug(out.decode())
            return False

        log.logger.info(f"Pinged LGTV [{name}], is connected: {int(groups[1]) == 1}.")
        return int(groups[1]) == 1

    def _discover(self) -> Tuple[Dict[str, HostType], List[HostType]]:
        """
        Discover devices connected to the network, both existing and new. These are then separated, based on
        whether they exist in the user config, and returned

        :return: A dict of existing host IP addresses (indexed by their name) and a list of new hosts.
        """
        clients = WebOSClient.discover()
        discovered_hosts = [c.host for c in clients]
        return self._separate_new_hosts(discovered_hosts)

    def _separate_new_hosts(self, hosts: List[HostType]) -> Tuple[Dict[str, HostType], List[HostType]]:
        """
        For each item in a list of hosts, check it exists in the config. If so, add it to the dictionary of
        existring hosts, indeced by its name. If not, add it to the new host list.

        :param hosts: All discovered hosts
        :return: A dict of existing host IP addresses (indexed by their name) and a list of new hosts.
        """
        existing_hosts = {n: h for h in hosts for n, d in self.devices.items() if h == d['host']}
        new_hosts = [h for h in hosts if h not in existing_hosts.values()]

        for n, h in existing_hosts.items():
            log.logger.debug(f"Discovered device {h}, which is already configured as {n}")

        for h in new_hosts:
            log.logger.debug(f"Discovered new device {h}.")

        return existing_hosts, new_hosts

    def _update_online_status(self):
        """
        Run through all hosts in the configuration and get the online status of each.
        Updates the member variable.
        """
        for n, d in self.devices.items():
            if self._ping_device_unix(n, d['host']):
                self._online.append(n)
            elif n in self._online:
                self._online.remove(n)

    def _register_endpoints(self, app: FastAPI):
        @app.get("/lgtv")
        def get_devices() -> Dict:
            def device_summary(name, data):
                return {
                    'host': data['host'],
                    'paired': 'key' in data,
                    'online': name in self._online,
                    'connected': name in self._connections
                }

            self._update_online_status()

            return {nm: device_summary(nm, data) for nm, data in self.devices.items()}

        @app.put("/lgtv/{name}/connect")
        def connect_device(name: str, response: Response) -> Dict:
            if name not in self.devices:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Device named {name} has not been configured."}

            try:
                data = self.devices[name]
                commander = self._device_connect(name, data['host'], data.get('key', None))

                key = commander.client.key
                dev_cfg = config.get(f"adapters.LGTVAdapter.devices.{name}")
                dev_cfg['key'] = key.decode()
                config.save()

                self._connections[name] = commander
                log.logger.info(f"Connected to LGTV {name}.")
                return {"message": "Connected"}
            except LGTVException as e:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": str(e)}

        @app.post("/lgtv/discover")
        def discover_device() -> Dict:
            existing, new = self._discover()
            return {
                "existing_hosts": existing,
                "new_hosts": new
            }

        @app.post("/lgtv/{name}/command")
        def send_command(name: str, command: CommandRequestModel, response: Response):
            if name not in self._connections:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Device named {name} has not been connected."}

            log.logger.info(f"Sending command [{command.name}: {command.message}] to device {name}.")

            client: LGTVCommander = self._connections[name]
            return {"response": client.send_command(command.name, command.message)}
