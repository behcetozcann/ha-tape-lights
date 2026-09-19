"""Effect catalogue of the Rhythm Pro app ("symphony" pixel effects).

Each category has its own command code. Within a category the style index
(0 based, "childIndex" in the app) decides a pattern number, a direction bit
and up to two colors from a fixed seven color palette. The formulas below are
transcribed from the app's `symphonyRgbChanged` handler.
"""
from __future__ import annotations

PALETTE = (0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0x00FFFF, 0xFF00FF, 0xFFFFFF)
PALETTE_HALF = (0x800000, 0x008000, 0x000080, 0x808000, 0x008080, 0x800080, 0x808080)

MIC_EFFECT = "Microphone"


def _color_pair(index: int) -> tuple[int, int]:
    """Groups of 12 styles: a fixed first color and six different second colors."""
    first = index // 12
    second = (index % 12) // 2
    if first <= second:
        second += 1
    return PALETTE[first], PALETTE[second]


def _open_close(style: int) -> tuple[int, int, int]:
    if style < 6:
        return style // 2 + 1, 0, 0
    return 4, PALETTE[(style - 6) // 2], 0


def _water(style: int) -> tuple[int, int, int]:
    if style < 6:
        return style // 2 + 1, 0, 0
    return 4, *_color_pair(style - 6)


def _trail(style: int) -> tuple[int, int, int]:
    if style < 2:
        return 1, 0, 0
    return 2, PALETTE[(style - 2) // 2], 0


def _flow(style: int) -> tuple[int, int, int]:
    return 0, *_color_pair(style)


def _run(style: int) -> tuple[int, int, int]:
    if style < 14:
        return 1, PALETTE_HALF[style // 2], 0
    return 2, *_color_pair(style - 14)


# name, command, number of styles, formula
CATEGORIES = (
    ("Open-Close", 0x18, 20, _open_close),
    ("Transition", 0x17, 20, _open_close),
    ("Water", 0x16, 90, _water),
    ("Trail", 0x15, 16, _trail),
    ("Flow", 0x14, 84, _flow),
    ("Run", 0x13, 98, _run),
)


def effect_list() -> list[str]:
    names = [f"{name} {style + 1}" for name, _, count, _ in CATEGORIES for style in range(count)]
    return [*names, MIC_EFFECT]


def _split_rgb(value: int) -> list[int]:
    return [(value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF]


def effect_command(effect: str, speed: int, brightness: int) -> tuple[int, list[int]]:
    """Command and 10 byte parameters for a named effect.

    speed is 1-100, brightness 0-255 (sent as max(12, percent * 255 / 100)).
    """
    name, _, number = effect.rpartition(" ")
    for category, command, count, formula in CATEGORIES:
        if category != name:
            continue
        style = int(number) - 1
        if not 0 <= style < count:
            break
        pattern, color_a, color_b = formula(style)
        level = max(12, min(255, brightness))
        return command, [pattern, style & 1, *_split_rgb(color_a), *_split_rgb(color_b), speed, level]
    raise ValueError(f"unknown effect: {effect}")
