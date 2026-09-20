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
        "options_title": "Connection",
        "options_description": "How commands reach the controller. The ESP32 bridge (ha/esphome/tape-lights.yaml) keeps one Bluetooth link open, which is the only way the controller receives every command reliably.",
        "transport": "Path",
        "esphome_node": "ESP32 node",
        "esphome_node_help": "ESPHome node name, e.g. tape-lights.",
        "connection_sensor": "ESP32 connection sensor",
        "connection_sensor_help": "Optional: when it turns on again, the current color or effect is sent once more.",
        "node_required": "Enter the ESPHome node name.",
        "unknown_node": "No esphome.<node>_send_frame action found. Flash tape-lights.yaml and make sure the ESP32 is online.",
        "transport_esphome": "Through the ESP32 (recommended)",
        "transport_bluetooth": "Direct Bluetooth",
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
        "options_title": "Bağlantı",
        "options_description": "Komutların kontrolcüye hangi yoldan gittiği. ESP32 köprüsü (ha/esphome/tape-lights.yaml) tek bir Bluetooth bağlantısını sürekli açık tutar; kontrolcünün her komutu almasının tek güvenilir yolu budur.",
        "transport": "Yol",
        "esphome_node": "ESP32 düğümü",
        "esphome_node_help": "ESPHome düğüm adı, örn. tape-lights.",
        "connection_sensor": "ESP32 bağlantı sensörü",
        "connection_sensor_help": "İsteğe bağlı: tekrar açıldığında mevcut renk veya efekt yeniden gönderilir.",
        "node_required": "ESPHome düğüm adını yazın.",
        "unknown_node": "esphome.<düğüm>_send_frame servisi bulunamadı. tape-lights.yaml yüklü mü ve ESP32 çevrimiçi mi?",
        "transport_esphome": "ESP32 üzerinden (önerilen)",
        "transport_bluetooth": "Doğrudan Bluetooth",
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
        "options": {
            "step": {
                "init": {
                    "title": text["options_title"],
                    "description": text["options_description"],
                    "data": {
                        "transport": text["transport"],
                        "esphome_node": text["esphome_node"],
                        "connection_sensor": text["connection_sensor"],
                    },
                    "data_description": {
                        "esphome_node": text["esphome_node_help"],
                        "connection_sensor": text["connection_sensor_help"],
                    },
                }
            },
            "error": {
                "node_required": text["node_required"],
                "unknown_node": text["unknown_node"],
            },
        },
        "selector": {
            "transport": {
                "options": {
                    "esphome": text["transport_esphome"],
                    "bluetooth": text["transport_bluetooth"],
                }
            }
        },
        "entity": {
            "light": {
                "strip": {
                    "state_attributes": {
                        "effect": {"state": {"off": text["effect_off"], **effects.effect_names(language)}}
                    }
                },
                "second_color": {"name": text["second_color"]},
            },
            "number": {
                "effect_speed": {"name": text["effect_speed"]},
                "mic_sensitivity": {"name": text["mic_sensitivity"]},
                "led_count": {"name": text["led_count"]},
            },
            "select": {"wire_order": {"name": text["wire_order"]}},
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
