"""Light entity: power, static color, brightness and effects."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import TapeLightsConfigEntry, protocol
from .effects import MIC_EFFECT, effect_command, effect_list
from .entity import TapeLightsEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TapeLightsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([TapeLightsLight(entry.runtime_data)])


class TapeLightsLight(TapeLightsEntity, LightEntity, RestoreEntity):
    """The controller does not report state, so it is assumed and restored."""

    _attr_name = None
    _attr_translation_key = "strip"
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, device) -> None:
        super().__init__(device, "light")
        self._attr_effect_list = effect_list()
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_rgb_color = (255, 255, 255)
        self._attr_effect = None
        device.refresh_effect = self._async_refresh_effect

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is None:
            return
        self._attr_is_on = last.state == STATE_ON
        self._attr_brightness = last.attributes.get(ATTR_BRIGHTNESS) or 255
        if rgb := last.attributes.get(ATTR_RGB_COLOR):
            self._attr_rgb_color = tuple(rgb)
        if (effect := last.attributes.get(ATTR_EFFECT)) in self._attr_effect_list:
            self._attr_effect = effect

    async def async_turn_on(self, **kwargs: Any) -> None:
        was_on = self._attr_is_on
        if not was_on:
            await self._device.send(protocol.power(True))
            self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]

        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs[ATTR_EFFECT]
            await self._async_send_effect()
        elif ATTR_RGB_COLOR in kwargs:
            self._attr_effect = None
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
            await self._async_send_color()
        elif ATTR_BRIGHTNESS in kwargs:
            await (self._async_send_effect() if self._attr_effect else self._async_send_color())
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._device.send(protocol.power(False))
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _async_send_color(self) -> None:
        await self._device.send(protocol.color(*self._attr_rgb_color, self._attr_brightness))

    async def _async_send_effect(self) -> None:
        if self._attr_effect == MIC_EFFECT:
            await self._device.send(protocol.mic_mode(0))
            await self._device.send(protocol.mic_sensitivity(self._device.mic_sensitivity))
            return
        await self._device.send(
            effect_command(self._attr_effect, self._device.speed, self._attr_brightness)
        )

    async def _async_refresh_effect(self) -> None:
        """Re-send the running effect after speed or sensitivity changed."""
        if self._attr_is_on and self._attr_effect:
            await self._async_send_effect()
