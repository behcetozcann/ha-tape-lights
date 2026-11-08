"""Maps a picked color to the values that look like it on this strip.

The strip's channels are far from balanced: 255, 255, 0 looks green and
255, 255, 255 looks cyan. A fixed factor per channel cannot fix that (yellow
needs green at 90, white at 232), so each hue has its own measured value.
"""
from __future__ import annotations

import colorsys

WHITE = (255, 232, 226)

# Hue in degrees -> value that showed that color on the strip.
HUE_ANCHORS = (
    (0, (255, 0, 0)),  # red
    (30, (255, 15, 0)),  # orange
    (60, (255, 90, 0)),  # yellow
    (120, (0, 255, 0)),  # green
    (180, (255, 255, 255)),  # cyan
    (240, (0, 0, 255)),  # blue
    (270, (255, 225, 229)),  # purple
    (330, (255, 90, 110)),  # pink
    (360, (255, 0, 0)),  # red again, to close the wheel
)


def _blend(start: tuple[int, ...], end: tuple[int, ...], amount: float) -> list[float]:
    return [low + (high - low) * amount for low, high in zip(start, end)]


def _saturated_color(hue_degrees: float) -> list[float]:
    for (low_hue, low_color), (high_hue, high_color) in zip(HUE_ANCHORS, HUE_ANCHORS[1:]):
        if hue_degrees <= high_hue:
            return _blend(low_color, high_color, (hue_degrees - low_hue) / (high_hue - low_hue))
    return list(HUE_ANCHORS[-1][1])


def calibrate(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Value to send for a picked color; its brightness is kept."""
    hue, saturation, value = colorsys.rgb_to_hsv(*(channel / 255 for channel in rgb))
    pure = _blend(WHITE, _saturated_color(hue * 360), saturation)
    return tuple(round(channel * value) for channel in pure)
