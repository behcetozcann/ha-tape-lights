"""BLE connection handling for one TAPE LIGHTS controller."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import random

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import protocol
from .const import DEFAULT_MIC_SENSITIVITY, DEFAULT_SPEED, IDLE_DISCONNECT_SECONDS

_LOGGER = logging.getLogger(__name__)


class TapeLightsDevice:
    """Keeps a short lived connection and writes encoded frames."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.speed = DEFAULT_SPEED
        self.mic_sensitivity = DEFAULT_MIC_SENSITIVITY
        self.second_color: int | None = None  # effect second color, None = its own
        # Set by the light entity; number entities call it to re-apply settings.
        self.refresh_effect: Callable[[], Awaitable[None]] | None = None
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._seq = random.randint(0, 0xFFFF)
        self._disconnect_timer: asyncio.TimerHandle | None = None

    async def send(self, command: tuple[int, list[int]]) -> None:
        """Encode and write one command, connecting first if needed."""
        cmd, params = command
        async with self._lock:
            self._seq = (self._seq + 1) & 0xFFFF
            frame = protocol.encode(cmd, params, seq=self._seq)
            try:
                client = await self._ensure_connected()
                await client.write_gatt_char(self._write_char(client), frame, response=False)
            except (BleakError, TimeoutError) as err:
                await self._disconnect()
                raise HomeAssistantError(f"{self.name}: write failed: {err}") from err
            _LOGGER.debug("%s: sent cmd 0x%02X %s", self.name, cmd, params)
            self._reset_disconnect_timer()

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client and self._client.is_connected:
            return self._client
        ble_device = bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)
        if ble_device is None:
            raise HomeAssistantError(f"{self.name} ({self.address}) is not in Bluetooth range")
        self._client = await establish_connection(
            BleakClientWithServiceCache, ble_device, self.name, max_attempts=3
        )
        return self._client

    @staticmethod
    def _write_char(client: BleakClientWithServiceCache):
        service = client.services.get_service(protocol.SERVICE_UUID)
        if service and (char := service.get_characteristic(protocol.WRITE_CHAR_UUID)):
            return char
        return protocol.WRITE_CHAR_UUID

    def _reset_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._disconnect_timer = self.hass.loop.call_later(
            IDLE_DISCONNECT_SECONDS, self._schedule_disconnect
        )

    @callback
    def _schedule_disconnect(self) -> None:
        self.hass.async_create_task(self._disconnect_when_idle())

    async def _disconnect_when_idle(self) -> None:
        async with self._lock:
            await self._disconnect()

    async def _disconnect(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None
        client, self._client = self._client, None
        if client and client.is_connected:
            await client.disconnect()

    async def async_shutdown(self) -> None:
        async with self._lock:
            await self._disconnect()
