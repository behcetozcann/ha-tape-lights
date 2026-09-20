"""TAPE LIGHTS (Rhythm Pro) Bluetooth LED controller integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant

from .const import DEFAULT_NAME
from .device import TapeLightsDevice
from .transport import async_create_transport

PLATFORMS = [Platform.LIGHT, Platform.NUMBER, Platform.SELECT]

type TapeLightsConfigEntry = ConfigEntry[TapeLightsDevice]


async def async_setup_entry(hass: HomeAssistant, entry: TapeLightsConfigEntry) -> bool:
    address = entry.data[CONF_ADDRESS]
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    transport = async_create_transport(hass, entry, address, name)
    device = TapeLightsDevice(hass, transport, address, name)
    entry.runtime_data = device
    await device.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TapeLightsConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
