"""Protocol tests. The hex frames below were accepted by a real controller."""
import importlib.util
import pathlib
import sys

import pytest

PACKAGE = pathlib.Path(__file__).parents[1] / "custom_components" / "tape_lights"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PACKAGE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = _load("protocol")
effects = _load("effects")

VERIFIED_ON_DEVICE = {
    "power off": ("27c3b2f813875307624fc460219079bc0b", 0x10, [0]),
    "power on": ("5b1e42cfd576319078bc0190def3b53791", 0x10, [1]),
    "red": ("20f97e1269196843f8624fc4602190798a", 0x22, [255, 0, 0]),
    "green": ("52f0a52f8a6d7c9278fd4a4307624fc466", 0x22, [0, 255, 0]),
    "open-close 1": ("791f1769e1487cd8d57d85af9b2e5e92be", 0x18, [1, 0, 0, 0, 0, 0, 0, 0]),
    "microphone": ("1d5dd33526454a3e65d8d47d85af9b2efc", 0x54, [1]),
}


@pytest.mark.parametrize("name", VERIFIED_ON_DEVICE)
def test_verified_frames_decode(name):
    raw, cmd, params = VERIFIED_ON_DEVICE[name]
    frame = protocol.decode(bytes.fromhex(raw))
    assert frame.crc_ok
    assert frame.cmd == cmd
    assert frame.params[: len(params)] == params


def test_ten_byte_params_use_header_slots():
    frame = protocol.decode(bytes.fromhex(VERIFIED_ON_DEVICE["open-close 1"][0]))
    assert (frame.x3, frame.x4) == (50, 255)


@pytest.mark.parametrize("params", [[0], [1], [255, 0, 0], list(range(10))])
def test_encode_decode_roundtrip(params):
    frame = protocol.decode(protocol.encode(0x22, params, seq=0x1234, rnd=0x5A))
    assert frame.crc_ok and frame.seq == 0x1234
    assert frame.params[: min(8, len(params))] == params[:8]


def test_effect_catalogue_size_matches_app():
    names = effects.effect_list()
    assert len(names) == 328 + 1
    assert len(set(names)) == len(names)


def test_open_close_1_matches_verified_frame():
    assert effects.effect_command("open_close_1", 50, 255) == (0x18, [1, 0, 0, 0, 0, 0, 0, 0, 50, 255])


def test_color_pairs_never_repeat_first_color():
    for style in range(84):
        _, color_a, color_b = effects._flow(style)
        assert color_a != color_b


def test_unknown_effect_rejected():
    with pytest.raises(ValueError):
        effects.effect_command("water_91", 50, 255)


def test_led_count_is_little_endian_16_bit():
    assert protocol.led_count(300) == (0x31, [300 & 0xFF, 300 >> 8])
    assert protocol.led_count(5000)[1] == [1024 & 0xFF, 1024 >> 8]


def test_wire_order_index_matches_app():
    assert protocol.wire_order("RGB") == (0x30, [0])
    assert protocol.wire_order("GRB") == (0x30, [2])
    assert protocol.wire_order("BGR") == (0x30, [5])


@pytest.mark.parametrize("language", ["en", "tr"])
def test_every_effect_has_a_translation(language):
    import json
    data = json.loads((PACKAGE / "translations" / f"{language}.json").read_text(encoding="utf-8"))
    names = data["entity"]["light"]["strip"]["state_attributes"]["effect"]["state"]
    assert set(names) == {"off", *effects.effect_list()}


def test_custom_colors_replace_palette_colors():
    assert effects.effect_command("water_20", 50, 255, 0x0000FF, 0xFFFF00)[1][2:8] == [0, 0, 255, 255, 255, 0]


def test_custom_color_ignored_by_rainbow_styles():
    assert effects.effect_command("open_close_1", 50, 255, first_color=0xFF6000)[1][2:8] == [0] * 6


@pytest.mark.parametrize("pure", [(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0)])
def test_balance_keeps_pure_colors(pure):
    assert protocol.balance(pure) == pure


def test_balance_tames_green_in_mixes_without_dimming():
    balanced = protocol.balance((255, 96, 0))
    assert balanced[0] == 255 and balanced[1] < 96
