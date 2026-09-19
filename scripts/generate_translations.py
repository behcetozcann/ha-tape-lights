"""Regenerate strings.json and translations/*.json.

Effect names come from effects.CATEGORIES, so the 329 effect labels never
drift from the effect list. Run after changing texts or effects:

    python scripts/generate_translations.py
"""
import importlib.util
import json
import pathlib

PACKAGE = pathlib.Path(__file__).parents[1] / "custom_components" / "tape_lights"

TEXTS = {
    "en": {
        "user": "Choose the TAPE LIGHTS controller to add.",
        "device": "Device",
        "confirm": "Set up {name} ({address})?",
        "already_configured": "This controller is already configured.",
        "no_devices_found": "No TAPE LIGHTS controller found. Power it on and close the Rhythm Pro app so it advertises.",
        "effect_speed": "Effect speed",
        "mic_sensitivity": "Microphone sensitivity",
        "led_count": "LED count",
        "wire_order": "Wire color order",
        "second_color": "Effect second color",
        "effect_off": "Off (solid color)",
    },
    "tr": {
        "user": "Eklenecek TAPE LIGHTS kontrolcüsünü seçin.",
        "device": "Cihaz",
        "confirm": "{name} ({address}) kurulsun mu?",
        "already_configured": "Bu kontrolcü zaten ekli.",
        "no_devices_found": "TAPE LIGHTS bulunamadı. Cihazı açın ve yayın yapabilmesi için Rhythm Pro uygulamasını kapatın.",
        "effect_speed": "Efekt hızı",
        "mic_sensitivity": "Mikrofon hassasiyeti",
        "led_count": "LED sayısı",
        "wire_order": "Kablo renk sırası",
        "second_color": "Efekt 2. rengi",
        "effect_off": "Kapalı (düz renk)",
    },
}


def load_effects():
    spec = importlib.util.spec_from_file_location("effects", PACKAGE / "effects.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(language: str, effects) -> dict:
    text = TEXTS[language]
    return {
        "config": {
            "flow_title": "{name}",
            "step": {
                "user": {"description": text["user"], "data": {"address": text["device"]}},
                "confirm": {"description": text["confirm"]},
            },
            "abort": {
                "already_configured": text["already_configured"],
                "no_devices_found": text["no_devices_found"],
            },
        },
        "entity": {
            "light": {
                "strip": {
                    "state_attributes": {
                        "effect": {"state": {"off": text["effect_off"], **effects.effect_names(language)}}
                    }
                }
            },
            "number": {
                "effect_speed": {"name": text["effect_speed"]},
                "mic_sensitivity": {"name": text["mic_sensitivity"]},
                "led_count": {"name": text["led_count"]},
            },
            "select": {
                "wire_order": {"name": text["wire_order"]},
                "second_color": {"name": text["second_color"], "state": effects.SECOND_COLOR_NAMES[language]},
            },
        },
    }


def write(path: pathlib.Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    effects = load_effects()
    write(PACKAGE / "strings.json", build("en", effects))
    for language in TEXTS:
        write(PACKAGE / "translations" / f"{language}.json", build(language, effects))


if __name__ == "__main__":
    main()
