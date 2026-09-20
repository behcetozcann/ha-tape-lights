"""Transport tests.

The integration modules import Home Assistant, which is not a test dependency,
so the handful of names they use are stubbed before the package is imported.
"""
import asyncio
import importlib
import pathlib
import sys
import types

import pytest

PACKAGE = pathlib.Path(__file__).parents[1] / "custom_components"


def _module(name: str, **attributes) -> types.ModuleType:
    module = types.ModuleType(name)
    for attribute, value in attributes.items():
        setattr(module, attribute, value)
    sys.modules[name] = module
    return module


TRACKED = []


def _track(hass, entity_ids, action):
    """Stands in for async_track_state_change_event, keeping the callback."""
    TRACKED.append((entity_ids, action))
    return lambda: None


def _stub_homeassistant() -> None:
    class HomeAssistantError(Exception):
        pass

    class ConfigEntry:
        def __class_getitem__(cls, item):
            return cls

    _module("bleak")
    _module("bleak.exc", BleakError=Exception, BleakDBusError=Exception)
    _module(
        "bleak_retry_connector",
        BleakClientWithServiceCache=object,
        BleakNotFoundError=type("BleakNotFoundError", (Exception,), {}),
        close_stale_connections_by_address=lambda *args: None,
        establish_connection=lambda *args, **kwargs: None,
    )
    _module("homeassistant")
    _module("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
    _module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError)
    _module(
        "homeassistant.const",
        CONF_ADDRESS="address",
        CONF_NAME="name",
        STATE_ON="on",
        Platform=types.SimpleNamespace(LIGHT="light", NUMBER="number", SELECT="select"),
    )
    _module("homeassistant.config_entries", ConfigEntry=ConfigEntry)
    _module("homeassistant.components")
    _module(
        "homeassistant.components.bluetooth",
        async_ble_device_from_address=lambda *args: None,
        async_register_callback=lambda *args: (lambda: None),
        async_process_advertisements=None,
        async_clear_advertisement_history=lambda *args: None,
        BluetoothScanningMode=types.SimpleNamespace(PASSIVE="passive", ACTIVE="active"),
    )
    _module(
        "homeassistant.components.bluetooth.match",
        ADDRESS="address",
        BluetoothCallbackMatcher=dict,
    )
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.event", async_track_state_change_event=_track)


_stub_homeassistant()
sys.path.insert(0, str(PACKAGE))
transport = importlib.import_module("tape_lights.transport")
HomeAssistantError = sys.modules["homeassistant.exceptions"].HomeAssistantError


class FakeServices:
    def __init__(self, available):
        self._available = set(available)
        self.calls = []

    def has_service(self, domain, service):
        return service in self._available

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))


class FakeHass:
    def __init__(self, available=()):
        self.services = FakeServices(available)
        self.tasks = []

    def async_create_task(self, coroutine):
        self.tasks.append(coroutine)
        return coroutine


def test_service_name_uses_underscores():
    esp = transport.EsphomeTransport(FakeHass(), "TAPE LIGHTS", "tape-lights")
    assert esp.send_service == "tape_lights_send_frame"


def test_send_passes_the_frame_as_integers():
    hass = FakeHass(["tape_lights_send_frame"])
    esp = transport.EsphomeTransport(hass, "TAPE LIGHTS", "tape-lights")
    asyncio.run(esp.async_send(bytes([0x00, 0x7F, 0xFF])))
    domain, service, data, blocking = hass.services.calls[0]
    assert (domain, service, blocking) == ("esphome", "tape_lights_send_frame", True)
    assert data == {"frame": [0, 127, 255]}


def test_send_without_the_esp32_raises():
    esp = transport.EsphomeTransport(FakeHass(), "TAPE LIGHTS", "tape-lights")
    with pytest.raises(HomeAssistantError):
        asyncio.run(esp.async_send(b"\x00"))


def test_start_asks_for_a_fresh_link_and_survives_an_offline_esp32():
    hass = FakeHass(["tape_lights_reconnect_strip"])
    esp = transport.EsphomeTransport(hass, "TAPE LIGHTS", "tape-lights")
    asyncio.run(esp.async_start())
    assert hass.services.calls[0][1] == "tape_lights_reconnect_strip"
    asyncio.run(transport.EsphomeTransport(FakeHass(), "TAPE LIGHTS", "x").async_start())


def _entry(options):
    return types.SimpleNamespace(options=options)


def test_transport_choice_follows_the_options():
    hass = FakeHass()
    bluetooth = transport.async_create_transport(hass, _entry({}), "AA:BB", "TAPE LIGHTS")
    assert isinstance(bluetooth, transport.BleTransport)

    esphome = transport.async_create_transport(
        hass,
        _entry({"transport": "esphome", "esphome_node": "tape-lights"}),
        "AA:BB",
        "TAPE LIGHTS",
    )
    assert isinstance(esphome, transport.EsphomeTransport)

    # "esphome" without a node cannot work, so Bluetooth stays.
    fallback = transport.async_create_transport(
        hass, _entry({"transport": "esphome"}), "AA:BB", "TAPE LIGHTS"
    )
    assert isinstance(fallback, transport.BleTransport)


def _state(value):
    return types.SimpleNamespace(state=value)


def test_the_strip_is_put_back_when_the_link_returns():
    TRACKED.clear()
    hass = FakeHass(["tape_lights_reconnect_strip"])
    esp = transport.EsphomeTransport(
        hass, "TAPE LIGHTS", "tape-lights", "binary_sensor.bridge"
    )
    reapplied = []

    async def _reapply():
        reapplied.append(True)

    esp.on_reconnect = _reapply
    asyncio.run(esp.async_start())
    entity_ids, action = TRACKED[0]
    assert entity_ids == ["binary_sensor.bridge"]

    action(types.SimpleNamespace(data={"old_state": _state("off"), "new_state": _state("on")}))
    assert len(hass.tasks) == 1
    asyncio.run(hass.tasks.pop())
    assert reapplied == [True]

    # Still on, or gone: nothing to put back.
    action(types.SimpleNamespace(data={"old_state": _state("on"), "new_state": _state("on")}))
    action(types.SimpleNamespace(data={"old_state": _state("on"), "new_state": None}))
    assert hass.tasks == []
