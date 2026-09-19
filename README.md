# TAPE LIGHTS (Rhythm Pro) for Home Assistant

Local Bluetooth control for the cheap addressable LED strip controllers that
advertise as **`TAPE LIGHTS`** and are normally used with the **Rhythm Pro**
app (Shenzhen Jingyuan Micro Control, `com.jingyuan.rhythm`). No cloud, no
phone, no ESP32 needed. The Home Assistant host's own Bluetooth adapter is
enough if the strip is in range.

## Features

| Entity | What it does |
|---|---|
| `light` | on / off, RGB color, brightness |
| `light` effects | 328 app effects in 6 families + the controller's built-in microphone mode |
| `number` Effect speed | 1-100, applied to the running effect |
| `number` Microphone sensitivity | 0-100, applied in microphone mode |

Effect families (same order and numbering as the app):

| Family | Styles |
|---|---|
| Open-Close | 20 |
| Transition | 20 |
| Water | 90 |
| Trail | 16 |
| Flow | 84 |
| Run | 98 |
| Microphone | sound reactive, uses the mic on the controller |

The controller never reports its state, so the entity uses an assumed state
that is restored after a restart.

**Verified on real hardware:** power, RGB color, Open-Close effects and the
microphone mode. The other families use the same frame format with the
formulas from the app; please open an issue if one misbehaves. The
microphone sensitivity mapping is decoded from the app but not yet confirmed.

## Installation

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/behcetozcann/ha-tape-lights` as *Integration*.
2. Install **TAPE LIGHTS (Rhythm Pro)** and restart Home Assistant.
3. Power the strip on and **close the Rhythm Pro app** (the controller stops
   advertising while a phone is connected). It is discovered automatically,
   or add it from *Settings → Devices & services → Add integration*.

Manual install: copy `custom_components/tape_lights` into your
`config/custom_components` folder and restart.

## Notes

- Only one Bluetooth connection is possible at a time. The integration drops
  its link after 30 idle seconds so the phone app can connect again.
- Tested with a Raspberry Pi's built-in adapter; ESPHome Bluetooth proxies
  with `active: true` should work as well.

## Protocol

Frames are written without response to characteristic `0000fff3-…` in
service `49535343-fe7d-4be5-8fa9-9fafd205e455`:

```
[seq_lo, seq_hi, 0x20, 0x80, 0x11, rnd, cmd_lo, cmd_hi, p0 … p7, crc_lo]
```

- CRC-16/CCITT (poly 0x1021) over the first 16 bytes, seeded with `~rnd`.
- The first 16 bytes are XOR-whitened with a 32 byte table starting at `crc_lo & 31`.
- With 10 byte parameters the last two bytes replace `0x80 0x11`.

| Command | Parameters |
|---|---|
| `0x10` power | `[1]` on / `[0]` off |
| `0x22` color | `[R, G, B]` |
| `0x13`-`0x18` effect family | `[pattern, direction, R1, G1, B1, R2, G2, B2, speed, brightness]` |
| `0x54` built-in microphone | `[mode + 1]` |
| `0x56` microphone sensitivity | `[1, v-50]` or `[0, 50-v]` |

See [`protocol.py`](custom_components/tape_lights/protocol.py) and
[`effects.py`](custom_components/tape_lights/effects.py) for the full details.
The protocol was reverse engineered from the Android app for interoperability.
The tests in `tests/` decode frames that were accepted by a real controller.

This project is not affiliated with the app or hardware vendor.

---

### Türkçe özet

Rhythm Pro uygulamasıyla kullanılan, Bluetooth'ta `TAPE LIGHTS` adıyla görünen
LED şerit kontrolcülerini Home Assistant'tan buluta ve telefona gerek olmadan
yönetir: aç/kapa, renk, parlaklık, 328 efekt ve cihazın kendi mikrofonuyla
sese duyarlı mod. Kurulum için yukarıdaki HACS adımlarını izleyin; kurulumdan
önce Rhythm Pro uygulamasını kapatın.

## License

MIT
