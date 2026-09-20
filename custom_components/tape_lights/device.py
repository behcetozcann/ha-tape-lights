"""BLE connection handling for one TAPE LIGHTS controller.

The controller stops advertising while it is connected, and Home Assistant
drops a device from its connectable list after ~195 s without an
advertisement. Holding the link for minutes therefore made the controller
unreachable ("is not in Bluetooth range"). This module keeps the link only
briefly, keeps the BLEDevice fresh from advertisements, and waits for a new
advertisement instead of hammering a device that cannot be seen.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging

from bleak.exc import BleakDBusError, BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    BleakNotFoundError,
    close_stale_connections_by_address,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import ADDRESS, BluetoothCallbackMatcher
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from . import protocol
from .const import (
    ADVERTISEMENT_WAIT_SECONDS,
    COMMAND_SETTLE_SECONDS,
    DEFAULT_MIC_SENSITIVITY,
    DEFAULT_SPEED,
    IDLE_DISCONNECT_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class TapeLightsDevice:
    """Sends encoded frames, connecting on demand."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self.hass = hass
        self.address = address
        self.name = name
        self.speed = DEFAULT_SPEED
        self.mic_sensitivity = DEFAULT_MIC_SENSITIVITY
        self.second_color: int | None = None  # effect second color, None = its own
        # Set by the light entity; other entities call it to re-apply settings.
        self.refresh_effect: Callable[[], Awaitable[None]] | None = None
        self._ble_device = bluetooth.async_ble_device_from_address(hass, address, True)
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._seq = 0
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._pending: dict[int, tuple[int, list[int]]] = {}
        self._worker: asyncio.Task | None = None

    @callback
    def async_start(self) -> Callable[[], None]:
        """Track advertisements so the BLEDevice stays fresh; returns unsubscribe."""

        @callback
        def _advertisement(service_info, change) -> None:
            self._ble_device = service_info.device

        return bluetooth.async_register_callback(
            self.hass,
            _advertisement,
            BluetoothCallbackMatcher({ADDRESS: self.address}),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

    def queue(self, command: tuple[int, list[int]]) -> None:
        """Send in the background so service calls never wait for Bluetooth.

        A newer command of the same kind replaces an older pending one, which
        keeps colour sliders from queueing up every intermediate value.
        """
        self._pending[command[0]] = command
        if self._worker is None or self._worker.done():
            self._worker = self.hass.async_create_task(self._drain())

    async def _drain(self) -> None:
        while self._pending:
            command = self._pending.pop(next(iter(self._pending)))
            try:
                await self.send(command)
            except HomeAssistantError as err:
                _LOGGER.warning("%s", err)

    async def send(self, command: tuple[int, list[int]]) -> None:
        """Encode and write one command, connecting first if needed."""
        cmd, params = command
        async with self._write_lock:
            self._seq = (self._seq + 1) & 0xFFFF
            frame = protocol.encode(cmd, params, seq=self._seq)
            for attempt in (1, 2):
                try:
                    client = await self._ensure_connected()
                    await client.write_gatt_char(self._write_char(client), frame, response=False)
                    break
                except BleakNotFoundError as err:
                    raise HomeAssistantError(f"{self.name}: not reachable: {err}") from err
                except (BleakDBusError, BleakError, TimeoutError) as err:
                    # Typically "org.bluez.Error.Failed: Not connected": the link
                    # dropped between the check and the write, so reconnect once.
                    await self._disconnect()
                    if attempt == 2:
                        raise HomeAssistantError(f"{self.name}: write failed: {err}") from err
            _LOGGER.debug("%s: sent cmd 0x%02X %s", self.name, cmd, params)
            await asyncio.sleep(COMMAND_SETTLE_SECONDS)
            self._reset_disconnect_timer()

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client and self._client.is_connected:
            return self._client
        async with self._connect_lock:
            if self._client and self._client.is_connected:
                return self._client
            ble_device = await self._async_ble_device()
            # BlueZ can hold a stale link from a crashed process or another
            # adapter, which makes establish_connection fail every time.
            await close_stale_connections_by_address(self.address)
            self._client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                self._on_disconnected,
                use_services_cache=True,
                max_attempts=3,
            )
            return self._client

    async def _async_ble_device(self):
        """The freshest BLEDevice, waiting for an advertisement if needed."""
        if device := bluetooth.async_ble_device_from_address(self.hass, self.address, True):
            self._ble_device = device
            return device
        _LOGGER.debug("%s: not advertising, waiting for it to come back", self.name)
        try:
            info = await bluetooth.async_process_advertisements(
                self.hass,
                lambda service_info: True,
                {ADDRESS: self.address, "connectable": True},
                bluetooth.BluetoothScanningMode.ACTIVE,
                ADVERTISEMENT_WAIT_SECONDS,
            )
        except TimeoutError as err:
            raise BleakNotFoundError(
                f"{self.name} ({self.address}) did not advertise for "
                f"{ADVERTISEMENT_WAIT_SECONDS}s"
            ) from err
        self._ble_device = info.device
        return info.device

    @staticmethod
    def _write_char(client: BleakClientWithServiceCache):
        service = client.services.get_service(protocol.SERVICE_UUID)
        if service and (char := service.get_characteristic(protocol.WRITE_CHAR_UUID)):
            return char
        return protocol.WRITE_CHAR_UUID

    @callback
    def _on_disconnected(self, _client) -> None:
        self._client = None
        # The controller starts advertising again now; clearing the history
        # makes sure that first packet reaches Home Assistant's callbacks.
        bluetooth.async_clear_advertisement_history(self.hass, self.address)

    def _reset_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._disconnect_timer = self.hass.loop.call_later(
            IDLE_DISCONNECT_SECONDS, lambda: self.hass.async_create_task(self._disconnect())
        )

    async def _disconnect(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None
        client, self._client = self._client, None
        if client and client.is_connected:
            try:
                await client.disconnect()
            except BleakError as err:
                _LOGGER.debug("%s: disconnect failed: %s", self.name, err)
        bluetooth.async_clear_advertisement_history(self.hass, self.address)

    async def async_shutdown(self) -> None:
        self._pending.clear()
        await self._disconnect()
