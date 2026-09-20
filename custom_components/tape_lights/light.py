"""Light entity: power, static color, brightness and effects."""
from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    EFFECT_OFF,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import TapeLightsConfigEntry, protocol
from .effects import MIC_EFFECT, effect_command, effect_list, rgb_to_int
from .entity import TapeLightsEntity

ATTR_CUSTOM_EFFECT_COLOR = "custom_effect_color"


async def async_setup_entry(
    hass: HomeAssistant, entry: TapeLightsConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    device = entry.runtime_data
    async_add_entities([TapeLightsLight(device), TapeLightsSecondColor(device)])


class TapeLightsLight(TapeLightsEntity, LightEntity, RestoreEntity):
    """The controller does not report state, so it is assumed and restored.

    Picking a color while an effect runs recolors the effect instead of
    stopping it; the "off" effect returns to a solid color.
    """

    _attr_name = None
    _attr_translation_key = "strip"
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, device) -> None:
        super().__init__(device, "light")
        self._attr_effect_list = [EFFECT_OFF, *effect_list()]
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_rgb_color = (255, 255, 255)
        self._attr_effect = EFFECT_OFF
        self._custom_effect_color = False
        device.refresh_effect = self._async_refresh_effect

    @property
    def _effect_running(self) -> bool:
        return self._attr_effect not in (None, EFFECT_OFF)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {ATTR_CUSTOM_EFFECT_COLOR: self._custom_effect_color}

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
        self._custom_effect_color = bool(last.attributes.get(ATTR_CUSTOM_EFFECT_COLOR))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self._attr_is_on:
            await self._device.send(protocol.power(True))
            self._attr_is_on = True
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]

        if ATTR_EFFECT in kwargs:
            self._attr_effect = kwargs[ATTR_EFFECT]
            # A new effect starts with its own colors unless a color came with it.
            self._custom_effect_color = ATTR_RGB_COLOR in kwargs
            await (self._async_send_effect() if self._effect_running else self._async_send_color())
        elif ATTR_RGB_COLOR in kwargs:
            if self._effect_running and self._attr_effect != MIC_EFFECT:
                self._custom_effect_color = True
                await self._async_send_effect()
            else:
                self._attr_effect = EFFECT_OFF
                await self._async_send_color()
        elif ATTR_BRIGHTNESS in kwargs:
            await (self._async_send_effect() if self._effect_running else self._async_send_color())
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
        first = rgb_to_int(protocol.balance(self._attr_rgb_color)) if self._custom_effect_color else None
        await self._device.send(
            effect_command(
                self._attr_effect,
                self._device.speed,
                self._attr_brightness,
                first_color=first,
                second_color=self._device.second_color,
            )
        )

    async def _async_refresh_effect(self) -> None:
        """Re-send the running effect after a setting changed."""
        if self._attr_is_on and self._effect_running:
            await self._async_send_effect()
            self.async_write_ha_state()


class TapeLightsSecondColor(TapeLightsEntity, LightEntity, RestoreEntity):
    """Color wheel for the second color of two color effects.

    Turning it off gives the effect its own second color back. It does not
    switch the strip itself on or off.
    """

    _attr_translation_key = "second_color"
    _attr_assumed_state = True
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_brightness = 255

    def __init__(self, device) -> None:
        super().__init__(device, "second_color")
        self._attr_is_on = False
        self._attr_rgb_color = (0, 0, 255)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is None:
            return
        if rgb := last.attributes.get(ATTR_RGB_COLOR):
            self._attr_rgb_color = tuple(rgb)
        if last.state == STATE_ON:
            self._attr_is_on = True
            self._device.second_color = rgb_to_int(protocol.balance(self._attr_rgb_color))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_RGB_COLOR in kwargs:
            self._attr_rgb_color = kwargs[ATTR_RGB_COLOR]
        self._attr_is_on = True
        self._device.second_color = rgb_to_int(protocol.balance(self._attr_rgb_color))
        await self._apply()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self._device.second_color = None
        await self._apply()

    async def _apply(self) -> None:
        if self._device.refresh_effect:
            await self._device.refresh_effect()
        self.async_write_ha_state()
