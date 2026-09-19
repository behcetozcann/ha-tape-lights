"""Shared base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .device import TapeLightsDevice


class TapeLightsEntity(Entity):
    _attr_has_entity_name = True

    def __init__(self, device: TapeLightsDevice, key: str) -> None:
        self._device = device
        self._attr_unique_id = f"{device.address}_{key}"
        self._attr_device_info = DeviceInfo(
            connections={(CONNECTION_BLUETOOTH, device.address)},
            name=device.name,
            manufacturer="Shenzhen Jingyuan (Rhythm Pro)",
            model="TAPE LIGHTS",
        )
