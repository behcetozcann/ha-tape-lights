"""Config flow: pick a discovered TAPE LIGHTS controller and how to reach it."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_CONNECTION_SENSOR,
    CONF_ESPHOME_NODE,
    CONF_TRANSPORT,
    DEFAULT_NAME,
    DEFAULT_TRANSPORT,
    DOMAIN,
    ESPHOME_DOMAIN,
    TRANSPORT_BLUETOOTH,
    TRANSPORT_ESPHOME,
)

SEND_FRAME_SUFFIX = "_send_frame"


def _is_tape_lights(info: BluetoothServiceInfoBleak) -> bool:
    return (info.name or "").upper().startswith(DEFAULT_NAME)


def _esphome_nodes(hass) -> list[str]:
    """ESPHome nodes running the tape-lights firmware, by their action name."""
    services = hass.services.async_services().get(ESPHOME_DOMAIN, {})
    return sorted(
        service[: -len(SEND_FRAME_SUFFIX)]
        for service in services
        if service.endswith(SEND_FRAME_SUFFIX)
    )


class TapeLightsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TapeLightsOptionsFlow:
        return TapeLightsOptionsFlow()

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._candidates: dict[str, str] = {}

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self._create(self._discovery.address, self._discovery.name)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": self._discovery.name, "address": self._discovery.address},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(address, self._candidates.get(address, DEFAULT_NAME))

        configured = self._async_current_ids(include_ignore=False)
        self._candidates = {
            info.address: info.name
            for info in async_discovered_service_info(self.hass, connectable=True)
            if _is_tape_lights(info) and info.address not in configured
        }
        if not self._candidates:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {address: f"{name} ({address})" for address, name in self._candidates.items()}
                    )
                }
            ),
        )

    def _create(self, address: str, name: str) -> ConfigFlowResult:
        return self.async_create_entry(title=name, data={CONF_ADDRESS: address, CONF_NAME: name})


class TapeLightsOptionsFlow(OptionsFlowWithReload):
    """Choose between the ESP32 bridge and direct Bluetooth."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        nodes = _esphome_nodes(self.hass)
        errors: dict[str, str] = {}
        if user_input is not None:
            node = (user_input.get(CONF_ESPHOME_NODE) or "").strip()
            if user_input[CONF_TRANSPORT] == TRANSPORT_ESPHOME and not node:
                errors[CONF_ESPHOME_NODE] = "node_required"
            elif node and not self.hass.services.has_service(
                ESPHOME_DOMAIN, f"{node.replace('-', '_')}{SEND_FRAME_SUFFIX}"
            ):
                errors[CONF_ESPHOME_NODE] = "unknown_node"
            if not errors:
                return self.async_create_entry(data={**user_input, CONF_ESPHOME_NODE: node})

        options = self.config_entry.options
        suggested_node = options.get(CONF_ESPHOME_NODE) or (nodes[0] if nodes else "")
        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TRANSPORT,
                        default=options.get(
                            CONF_TRANSPORT,
                            TRANSPORT_ESPHOME if nodes else DEFAULT_TRANSPORT,
                        ),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[TRANSPORT_ESPHOME, TRANSPORT_BLUETOOTH],
                            translation_key="transport",
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(
                        CONF_ESPHOME_NODE,
                        description={"suggested_value": suggested_node},
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=nodes, custom_value=True, mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Optional(
                        CONF_CONNECTION_SENSOR,
                        description={"suggested_value": options.get(CONF_CONNECTION_SENSOR)},
                    ): EntitySelector(
                        EntitySelectorConfig(domain="binary_sensor", integration=ESPHOME_DOMAIN)
                    ),
                }
            ),
        )
