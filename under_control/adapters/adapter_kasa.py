import asyncio
from typing import Dict

from fastapi import FastAPI, Response, status, Path
from kasa import Discover

import under_control.logger as log
from under_control import adapters


class KasaAdapter(adapters.Adapter):

    def __init__(self, cfg, app: FastAPI):
        super().__init__(cfg, app)
        self._devices = {}

    def startup(self):
        self.discover_devices()

    def shutdown(self):
        pass

    def get_devices(self):
        return self._devices

    def update_devices(self):
        """
        The kasa library caches the state of the devices. This might change (device turned on/off elsewhere, energy
        usage state, etc.), so we need to provide a way to update the status of the devices.

        This should be cheaper than discovery, because we already know the IPs.
        """
        for dev in self._devices.values():
            log.logger.info(f"KasaAdapter: Updating device {dev.alias}: {dev}")
            asyncio.run(dev.update())
            log.logger.info(f"KasaAdapter: Updated device {dev.alias}: {dev}")

    def discover_devices(self):
        """
        Call the discovery method of the Kasa API. This is quite slow and shouldn't be done regularly.
        For all detected devices, we update their state and store them in the device list, indexed by
        their alias.
        """
        self._devices.clear()
        log.logger.info("KasaAdapter: Discovering devices...")
        devices = asyncio.run(Discover.discover())
        for dev in devices.values():
            asyncio.run(dev.update())
            self._devices[dev.alias] = dev
            log.logger.info(f"KasaAdapter: Found device {dev.alias}: {dev}")

    def _get_device(self, alias: str):
        """
        Get an individual device by its alias. Not intended for use from outside the adapter.
        """
        devices = self.get_devices()
        if not alias in devices:
            return None
        return devices[alias]

    def _register_endpoints(self, app: FastAPI):

        @app.get("/kasa")
        def kasa_devices() -> Dict:
            self.update_devices()
            return self.get_devices()

        @app.get("/kasa/{alias}")
        def kasa_single_device(alias: str) -> Dict:
            devices = self.get_devices()
            if not alias in devices:
                return {}

            dev = devices[alias]
            asyncio.run(dev.update())
            return dev

        @app.put("/kasa/{alias}/on")
        def device_on(alias: str, response: Response) -> Dict:
            dev = self._get_device(alias)
            if dev is None:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Could not find device [{alias}]"}
            asyncio.run(dev.turn_on())
            asyncio.run(dev.update())
            return {"message": f"Turned on [{alias}]"}

        @app.put("/kasa/{alias}/off")
        def device_off(alias: str, response: Response) -> Dict:
            dev = self._get_device(alias)
            if dev is None:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Could not find device [{alias}]"}
            asyncio.run(dev.turn_off())
            asyncio.run(dev.update())
            return {"message": f"Turned off [{alias}]"}

        @app.put("/kasa/{alias}/colour/{colour_spec}")
        def set_bulb_colour(response: Response,
                            alias: str = Path(..., title="Device Alias"),
                            colour_spec: str = Path(...,
                                                    title="Comma-separated HSV tuple",
                                                    description="Hue: 0...360, S: 0...100, V: 0...100.",
                                                    regex=r'^\d{1,3},\d{1,3},\d{1,3}$'),
                            ) -> Dict:
            dev = self._get_device(alias)
            if dev is None:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Could not find device [{alias}]"}

            if not dev.is_color:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Cannot set the colour of [{alias}]"}

            h, s, v = [int(i) for i in colour_spec.split(',')]
            asyncio.run(dev.set_hsv(h, s, v))
            asyncio.run(dev.update())
            return {"message": f"Set the colour of [{alias}] to {colour_spec}"}

        @app.put("/kasa/{alias}/colour_temp/{colour_temp}")
        def set_bulb_colour_temp(response: Response,
                                 alias: str = Path(..., title="Device Alias"),
                                 colour_temp: int = Path(...,
                                                         title="Colour temperature in Kelvin",
                                                         description="An integer between 2500 and 9000",
                                                         ge=2500, le=9000),
                                 ) -> Dict:
            dev = self._get_device(alias)
            if dev is None:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Could not find device [{alias}]"}

            if not dev.is_variable_color_temp:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Cannot set the colour temperature of [{alias}]"}

            asyncio.run(dev.set_color_temp(colour_temp))
            asyncio.run(dev.update())
            return {"message": f"Set the colour temperature of [{alias}] to {colour_temp}K"}

        @app.put("/kasa/{alias}/brightness/{brightness}")
        def set_bulb_brightness(response: Response,
                                alias: str = Path(..., title="Device Alias"),
                                brightness: int = Path(...,
                                                       title="Colour brightness",
                                                       description="An integer between 0 and 100",
                                                       ge=0, le=100),
                                ) -> Dict:
            dev = self._get_device(alias)
            if dev is None:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Could not find device [{alias}]"}

            if not dev.is_dimmable:
                response.status_code = status.HTTP_400_BAD_REQUEST
                return {"message": f"Cannot set the brightness of ¬[{alias}]"}

            asyncio.run(dev.set_brightness(brightness))
            asyncio.run(dev.update())
            return {"message": f"Set the brightness of [{alias}] to {brightness}"}
