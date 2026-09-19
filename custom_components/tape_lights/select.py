"""Color order of the strip's wires (the app's "Adjust line sequence")."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import TapeLightsConfigEntry, protocol
from .effects import SECOND_COLORS
from .entity import TapeLightsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TapeLightsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    device = entry.runtime_data
    async_add_entities([TapeLightsWireOrder(device), TapeLightsSecondColor(device)])


class TapeLightsWireOrder(TapeLightsEntity, SelectEntity, RestoreEntity):
    """Only sent when changed, so the value set in the phone app is kept."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "wire_order"
    _attr_options = list(protocol.WIRE_ORDERS)

    def __init__(self, device) -> None:
        super().__init__(device, "wire_order")
        self._attr_current_option = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in protocol.WIRE_ORDERS:
            self._attr_current_option = last.state

    async def async_select_option(self, option: str) -> None:
        await self._device.send(protocol.wire_order(option))
        self._attr_current_option = option
        self.async_write_ha_state()


class TapeLightsSecondColor(TapeLightsEntity, SelectEntity, RestoreEntity):
    """Second color of two color effects, applied to the running effect."""

    _attr_translation_key = "second_color"
    _attr_options = list(SECOND_COLORS)

    def __init__(self, device) -> None:
        super().__init__(device, "second_color")
        self._attr_current_option = device.second_color

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.state in SECOND_COLORS:
            self._attr_current_option = last.state
            self._device.second_color = last.state

    async def async_select_option(self, option: str) -> None:
        self._device.second_color = option
        self._attr_current_option = option
        if self._device.refresh_effect:
            await self._device.refresh_effect()
        self.async_write_ha_state()
