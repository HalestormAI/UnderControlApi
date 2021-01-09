from typing import Dict

from fastapi import FastAPI, Response, status
from pywebostv.connection import WebOSClient

import under_control.logger as log
from under_control import adapters


class LGTVException(Exception):
    pass


class LGTVAdapter(adapters.Adapter):

    def __init__(self, cfg, app: FastAPI):
        super().__init__(cfg, app)
        self._devices = {}
        self._connections = {}

    def startup(self):
        pass

    def shutdown(self):
        pass

    @property
    def devices(self) -> Dict:
        """
        Retrieve all the devices listed in the config.

        NOTE: Makes no guarantee of connection or validity.
        :return: List of all devices from the config
        """
        return self.cfg['devices']

    @staticmethod
    def _device_connect(name, ip, key):
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

            return client

        except TimeoutError:
            raise LGTVException(f"Timed out connecting to LGTV {name}.")

    def _discover(self):
        clients = WebOSClient.discover()

        for client in clients:
            # TODO
            pass

    def _register_endpoints(self, app: FastAPI):
        @app.get("/lgtv")
        def get_devices(response: Response) -> Dict:
            def device_summary(name, data):
                return {
                    'host': data['host'],
                    'paired': 'key' in data,
                    'connected': name in self._connections
                }

            return {nm: device_summary(nm, data) for nm, data in self.devices.items()}

        @app.get("/lgtv/{name}/connect")
        def connect_device(name: str, response: Response) -> Dict:
            if name not in self.devices:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Device named {name} has not been configured."}

            try:
                data = self.devices[name]
                client = self._device_connect(name, data['host'], data.get('key', None))

                self._connections[name] = client
                log.logger.info(f"Connected to LGTV {name}.")
                return {"message": "Connected"}
            except LGTVException as e:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": str(e)}
