"""Effect catalogue of the Rhythm Pro app ("symphony" pixel effects).

Each category has its own command code. Within a category the style index
(0 based, "childIndex" in the app) decides a pattern number, a direction bit
and up to two colors from a fixed seven color palette. The formulas below are
transcribed from the app's `symphonyRgbChanged` handler.
"""
from __future__ import annotations

PALETTE = (0xFF0000, 0x00FF00, 0x0000FF, 0xFFFF00, 0x00FFFF, 0xFF00FF, 0xFFFFFF)
PALETTE_HALF = (0x800000, 0x008000, 0x000080, 0x808000, 0x008080, 0x800080, 0x808080)

MIC_EFFECT = "microphone"
MIC_NAMES = {"en": "Microphone", "tr": "Mikrofon (sese duyarlı)"}


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


# key, display names, command, number of styles, formula
CATEGORIES = (
    ("open_close", {"en": "Open-Close", "tr": "Açılıp Kapanma"}, 0x18, 20, _open_close),
    ("transition", {"en": "Transition", "tr": "Geçiş"}, 0x17, 20, _open_close),
    ("water", {"en": "Water", "tr": "Akan Su"}, 0x16, 90, _water),
    ("trail", {"en": "Trail", "tr": "Kuyruklu İz"}, 0x15, 16, _trail),
    ("flow", {"en": "Flow", "tr": "Akış"}, 0x14, 84, _flow),
    ("run", {"en": "Run", "tr": "Kovalamaca"}, 0x13, 98, _run),
)


def effect_list() -> list[str]:
    """Effect keys such as "water_20"; display names come from translations."""
    keys = [f"{key}_{style + 1}" for key, _, _, count, _ in CATEGORIES for style in range(count)]
    return [*keys, MIC_EFFECT]


def effect_names(language: str) -> dict[str, str]:
    """Key -> display name for one language, used to generate translations."""
    names = {
        f"{key}_{style + 1}": f"{labels[language]} {style + 1}"
        for key, labels, _, count, _ in CATEGORIES
        for style in range(count)
    }
    names[MIC_EFFECT] = MIC_NAMES[language]
    return names


def _split_rgb(value: int) -> list[int]:
    return [(value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF]


# Choices for the second effect color; "auto" keeps the style's own color.
SECOND_COLORS = {
    "auto": None,
    "red": 0xFF0000,
    "orange": 0xFF6000,
    "yellow": 0xFFFF00,
    "green": 0x00FF00,
    "cyan": 0x00FFFF,
    "blue": 0x0000FF,
    "purple": 0x8000FF,
    "pink": 0xFF00FF,
    "white": 0xFFFFFF,
}
SECOND_COLOR_NAMES = {
    "en": {"auto": "Effect's own color", "red": "Red", "orange": "Orange", "yellow": "Yellow",
           "green": "Green", "cyan": "Cyan", "blue": "Blue", "purple": "Purple", "pink": "Pink",
           "white": "White"},
    "tr": {"auto": "Efektin kendi rengi", "red": "Kırmızı", "orange": "Turuncu", "yellow": "Sarı",
           "green": "Yeşil", "cyan": "Camgöbeği", "blue": "Mavi", "purple": "Mor", "pink": "Pembe",
           "white": "Beyaz"},
}


def rgb_to_int(rgb: tuple[int, int, int]) -> int:
    return (rgb[0] << 16) | (rgb[1] << 8) | rgb[2]


def effect_command(
    effect: str,
    speed: int,
    brightness: int,
    first_color: int | None = None,
    second_color: int | None = None,
) -> tuple[int, list[int]]:
    """Command and 10 byte parameters for a named effect.

    speed is 1-100, brightness 0-255 (sent as max(12, percent * 255 / 100)).
    first_color / second_color replace the style's palette colors, but only
    in styles that use that color slot; rainbow styles are left untouched.
    """
    name, _, number = effect.rpartition("_")
    for category, _, command, count, formula in CATEGORIES:
        if category != name or not number.isdigit():
            continue
        style = int(number) - 1
        if not 0 <= style < count:
            break
        pattern, color_a, color_b = formula(style)
        if first_color is not None and color_a:
            color_a = first_color
        if second_color is not None and color_b:
            color_b = second_color
        level = max(12, min(255, brightness))
        return command, [pattern, style & 1, *_split_rgb(color_a), *_split_rgb(color_b), speed, level]
    raise ValueError(f"unknown effect: {effect}")
