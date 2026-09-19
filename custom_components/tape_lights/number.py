"""Effect speed and microphone sensitivity."""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import TapeLightsConfigEntry, protocol
from .entity import TapeLightsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TapeLightsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    device = entry.runtime_data
    async_add_entities(
        [
            TapeLightsSetting(device, "effect_speed", "speed", 1),
            TapeLightsSetting(device, "mic_sensitivity", "mic_sensitivity", 0),
            TapeLightsLedCount(device),
        ]
    )


class TapeLightsSetting(TapeLightsEntity, RestoreNumber):
    """A 0-100 slider stored on the device object and applied to the running effect."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, device, key: str, attribute: str, minimum: int) -> None:
        super().__init__(device, key)
        self._attr_translation_key = key
        self._attribute = attribute
        self._attr_native_min_value = minimum
        self._attr_native_value = getattr(device, attribute)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._attr_native_value = last.native_value
            setattr(self._device, self._attribute, int(last.native_value))

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        setattr(self._device, self._attribute, int(value))
        if self._device.refresh_effect:
            await self._device.refresh_effect()
        self.async_write_ha_state()


class TapeLightsLedCount(TapeLightsEntity, RestoreNumber):
    """Pixel count of the strip. Only sent when changed, never on startup,
    so a value already set in the phone app is not overwritten."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = protocol.LED_COUNT_MIN
    _attr_native_max_value = protocol.LED_COUNT_MAX
    _attr_native_step = 1
    _attr_translation_key = "led_count"

    def __init__(self, device) -> None:
        super().__init__(device, "led_count")
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_number_data()) and last.native_value is not None:
            self._attr_native_value = last.native_value

    async def async_set_native_value(self, value: float) -> None:
        await self._device.send(protocol.led_count(int(value)))
        self._attr_native_value = int(value)
        self.async_write_ha_state()
