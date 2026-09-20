"""Ways of getting an encoded frame to the controller.

Direct Bluetooth from Home Assistant means connecting and disconnecting for
every command, and this controller loses commands when it is treated that way.
The phone app keeps a single GATT link open instead, which is what an ESP32
running the `tape-lights.yaml` ESPHome firmware does: it stays connected and
Home Assistant hands it the finished frame through an ESPHome action.
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
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event

from . import protocol
from .const import (
    ADVERTISEMENT_WAIT_SECONDS,
    CONF_CONNECTION_SENSOR,
    CONF_ESPHOME_NODE,
    CONF_TRANSPORT,
    DEFAULT_TRANSPORT,
    ESPHOME_DOMAIN,
    IDLE_DISCONNECT_SECONDS,
    TRANSPORT_ESPHOME,
)

_LOGGER = logging.getLogger(__name__)


class Transport:
    """What a device needs from a way of reaching the controller."""

    def __init__(self, hass: HomeAssistant, name: str) -> None:
        self.hass = hass
        self.name = name
        # Called when the link comes back, so the strip is put in the state
        # Home Assistant believes it is in.
        self.on_reconnect: Callable[[], Awaitable[None]] | None = None

    async def async_start(self) -> None:
        """Prepare the transport; called once when the entry is set up."""

    async def async_send(self, frame: bytes) -> None:
        raise NotImplementedError

    async def async_shutdown(self) -> None:
        """Release everything the transport holds."""


class EsphomeTransport(Transport):
    """Writes through an ESP32 that holds the BLE link open."""

    def __init__(
        self, hass: HomeAssistant, name: str, node: str, connection_sensor: str | None = None
    ) -> None:
        super().__init__(hass, name)
        self.node = node
        self._slug = node.replace("-", "_")
        self._connection_sensor = connection_sensor
        self._unsubscribe: Callable[[], None] | None = None

    @property
    def send_service(self) -> str:
        return f"{self._slug}_send_frame"

    async def async_start(self) -> None:
        # Home Assistant picks a new random sequence number when it restarts and
        # the controller ignores frames that are not newer than the last one it
        # saw, so the link is rebuilt first.
        await self._async_call(f"{self._slug}_reconnect_strip", {}, required=False)
        self._unsubscribe = self._track_connection()

    async def async_send(self, frame: bytes) -> None:
        await self._async_call(self.send_service, {"frame": list(frame)})

    async def async_shutdown(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    async def _async_call(self, service: str, data: dict, required: bool = True) -> None:
        if not self.hass.services.has_service(ESPHOME_DOMAIN, service):
            message = (
                f"{self.name}: {ESPHOME_DOMAIN}.{service} is missing; "
                f"is the {self.node} ESP32 online?"
            )
            if required:
                raise HomeAssistantError(message)
            _LOGGER.warning("%s", message)
            return
        await self.hass.services.async_call(ESPHOME_DOMAIN, service, data, blocking=True)

    def _track_connection(self) -> Callable[[], None] | None:
        if not self._connection_sensor:
            return None

        @callback
        def _changed(event) -> None:
            new_state = event.data["new_state"]
            old_state = event.data["old_state"]
            came_back = new_state and new_state.state == STATE_ON and (
                old_state is None or old_state.state != STATE_ON
            )
            if came_back and self.on_reconnect:
                self.hass.async_create_task(self.on_reconnect())

        return async_track_state_change_event(self.hass, [self._connection_sensor], _changed)


class BleTransport(Transport):
    """Connects from Home Assistant itself for every burst of commands.

    The controller stops advertising while it is connected, and Home Assistant
    drops a device from its connectable list after ~195 s without an
    advertisement. The link is therefore held only briefly and the BLEDevice is
    kept fresh from advertisements.
    """

    def __init__(self, hass: HomeAssistant, name: str, address: str) -> None:
        super().__init__(hass, name)
        self.address = address
        self._ble_device = bluetooth.async_ble_device_from_address(hass, address, True)
        self._client: BleakClientWithServiceCache | None = None
        self._connect_lock = asyncio.Lock()
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._ack_writes = True
        self._unsubscribe: Callable[[], None] | None = None

    async def async_start(self) -> None:
        @callback
        def _advertisement(service_info, change) -> None:
            self._ble_device = service_info.device

        self._unsubscribe = bluetooth.async_register_callback(
            self.hass,
            _advertisement,
            BluetoothCallbackMatcher({ADDRESS: self.address}),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )

    async def async_send(self, frame: bytes) -> None:
        for attempt in (1, 2):
            try:
                client = await self._ensure_connected()
                await self._write(client, frame)
                break
            except BleakNotFoundError as err:
                raise HomeAssistantError(f"{self.name}: not reachable: {err}") from err
            except (BleakDBusError, BleakError, TimeoutError) as err:
                # Typically "org.bluez.Error.Failed: Not connected": the link
                # dropped between the check and the write, so reconnect once.
                await self._disconnect()
                if attempt == 2:
                    raise HomeAssistantError(f"{self.name}: write failed: {err}") from err
        self._reset_disconnect_timer()

    async def async_shutdown(self) -> None:
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        await self._disconnect()

    async def _write(self, client: BleakClientWithServiceCache, frame: bytes) -> None:
        """Acknowledged write when the characteristic allows it.

        The phone app writes without a response, but those frames are silently
        lost now and then ("a command works, the next one does not"), so an
        acknowledged write is used whenever the controller supports it.
        """
        char = self._write_char(client)
        if self._ack_writes:
            try:
                await client.write_gatt_char(char, frame, response=True)
                return
            except (BleakDBusError, BleakError) as err:
                if not self._client or not self._client.is_connected:
                    raise
                _LOGGER.debug("%s: acknowledged write rejected (%s), falling back", self.name, err)
                self._ack_writes = False
        await client.write_gatt_char(char, frame, response=False)

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


def async_create_transport(
    hass: HomeAssistant, entry: ConfigEntry, address: str, name: str
) -> Transport:
    """The transport the entry's options ask for."""
    options = entry.options
    node = options.get(CONF_ESPHOME_NODE)
    if options.get(CONF_TRANSPORT, DEFAULT_TRANSPORT) == TRANSPORT_ESPHOME and node:
        return EsphomeTransport(hass, name, node, options.get(CONF_CONNECTION_SENSOR))
    return BleTransport(hass, name, address)
