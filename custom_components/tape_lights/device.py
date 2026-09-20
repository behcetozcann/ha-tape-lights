"""One TAPE LIGHTS controller: encodes commands and hands them to a transport."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import logging
import random

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from . import protocol
from .const import COMMAND_SETTLE_SECONDS, DEFAULT_MIC_SENSITIVITY, DEFAULT_SPEED
from .transport import Transport

_LOGGER = logging.getLogger(__name__)


class TapeLightsDevice:
    """Encodes commands and sends them one at a time through a transport."""

    def __init__(
        self, hass: HomeAssistant, transport: Transport, address: str, name: str
    ) -> None:
        self.hass = hass
        self.transport = transport
        self.address = address
        self.name = name
        self.speed = DEFAULT_SPEED
        self.mic_sensitivity = DEFAULT_MIC_SENSITIVITY
        self.second_color: int | None = None  # effect second color, None = its own
        # Set by the light entity; other entities call it to re-apply settings.
        self.refresh_effect: Callable[[], Awaitable[None]] | None = None
        self._write_lock = asyncio.Lock()
        # The controller ignores frames whose sequence number is not newer than
        # the last one it saw, so starting from 0 after a restart silently
        # dropped the first commands. Start somewhere random instead.
        self._seq = random.randint(0, 0xFFFF)
        self._pending: dict[int, tuple[int, list[int]]] = {}
        self._worker: asyncio.Task | None = None
        transport.on_reconnect = self.async_reapply

    async def async_start(self) -> None:
        await self.transport.async_start()

    def queue(self, command: tuple[int, list[int]]) -> None:
        """Send in the background so service calls never wait for the transport.

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
        """Encode and send one command."""
        cmd, params = command
        async with self._write_lock:
            self._seq = (self._seq + 1) & 0xFFFF
            frame = protocol.encode(cmd, params, seq=self._seq)
            await self.transport.async_send(frame)
            _LOGGER.debug("%s: sent cmd 0x%02X %s", self.name, cmd, params)
            await asyncio.sleep(COMMAND_SETTLE_SECONDS)

    async def async_reapply(self) -> None:
        """Put the strip back in the state Home Assistant believes it is in."""
        if self.refresh_effect:
            await self.refresh_effect()

    async def async_shutdown(self) -> None:
        self._pending.clear()
        await self.transport.async_shutdown()
