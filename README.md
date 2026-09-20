# TAPE LIGHTS (Rhythm Pro) for Home Assistant

Local Bluetooth control for the cheap addressable LED strip controllers that
advertise as **`TAPE LIGHTS`** and are normally used with the **Rhythm Pro**
app (Shenzhen Jingyuan Micro Control, `com.jingyuan.rhythm`). No cloud and no
phone. The Home Assistant host's own Bluetooth adapter works, but these
controllers lose commands unless something stays connected to them, so an ESP32
bridge ([see below](#recommended-an-esp32-that-keeps-the-link-open)) is the
reliable setup.

## Features

| Entity | What it does |
|---|---|
| `light` | on / off, RGB color, brightness |
| `light` effects | 328 app effects in 6 families + the controller's built-in microphone mode |
| `number` Effect speed | 1-100, applied to the running effect |
| `number` Microphone sensitivity | 0-100, applied in microphone mode |
| `number` LED count | 100-1024 pixels on the strip (see below) |
| `select` Wire color order | RGB / RBG / GRB / GBR / BRG / BGR |
| `light` Effect second color | color wheel for the second color of two color effects |

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

**Effect colors:** an effect starts with its own palette colors. Pick a color
while it runs and the effect keeps running in that color. The separate
*Effect second color* light is a color wheel for the second color of two
color effects; switch it off to get the effect's own second color back (it
does not switch the strip itself). Rainbow styles ignore
custom colors. Choose the effect **Off** to go back to a solid color.

Effect names are translated (English, Turkish). In automations and service
calls use the effect key, e.g. `effect: water_20`, `open_close_1`, `microphone`.

The controller never reports its state, so the entity uses an assumed state
that is restored after a restart.

### LED count and wire order

The controller has to know how many pixels the strip has. If the LED count is
wrong, effects do not fit the strip: patterns restart or stop part way along
and the strip looks split into differently colored sections. Set **LED count**
to the real number of LEDs (for example 60 LEDs/m × 5 m = 300). If red, green
and blue come out swapped, change **Wire color order** (GRB is common).
Both are only sent when you change them, so values already set in the Rhythm
Pro app are kept.

**Verified on real hardware:** power, RGB color, Open-Close and Water effects
and the microphone mode. The other families use the same frame format with the
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

### Recommended: an ESP32 that keeps the link open

Connecting and disconnecting for every command makes this controller drop
commands now and then. The phone app keeps a single GATT link open, and an
ESP32 running ESPHome can do the same. Home Assistant then only encodes the
frame and hands it over:

```
Home Assistant --esphome.<node>_send_frame--> ESP32 --BLE (always connected)--> strip
```

1. Flash an ESP32 with an ESPHome configuration that holds the link and exposes
   the frame action ([example](https://github.com/behcetozcann/ha-tape-lights/blob/main/docs/tape-lights.yaml)):
   a `ble_client` with the strip's MAC and `auto_connect: true`, plus an
   `api: actions:` entry named `send_frame` taking `frame: int[]` and writing it
   with `ble_client.ble_write` to `0000fff3-…` in
   `49535343-fe7d-4be5-8fa9-9fafd205e455`. A second action, `reconnect_strip`,
   disconnects and reconnects.
2. *Settings → Devices & services → TAPE LIGHTS → Configure* → **Through the
   ESP32**, and enter the ESPHome node name.
3. Optionally point the *connection sensor* at the ESP32's connectivity binary
   sensor; the current color or effect is sent again whenever the link returns.

The ESP32 is dedicated to the strip: while it is connected the strip no longer
advertises, so a Bluetooth proxy on the same board should stay passive
(`active: false`). *Direct Bluetooth* remains available as a fallback.

## Notes

- Commands are queued and sent in the background, so the UI never waits for
  Bluetooth; a newer command of the same kind replaces a pending one, which
  keeps dragging the color wheel from flooding the controller. Failures are
  logged as warnings instead of failing the service call.
- With the direct Bluetooth path, the controller only advertises while it is disconnected, and Home Assistant
  forgets a device that has not advertised for about 195 seconds. The link is
  therefore dropped 10 seconds after the last command; the BLEDevice is kept
  fresh from advertisements, stale BlueZ links are closed before connecting,
  and the integration waits for a new advertisement instead of retrying
  against a device it cannot see.
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
| `0x30` wire color order | `[index]` 0=RGB 1=RBG 2=GRB 3=GBR 4=BRG 5=BGR |
| `0x31` LED count | `[count & 0xFF, count >> 8]`, 100-1024 |
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
yönetir: aç/kapa, renk, parlaklık, 328 efekt (Türkçe adlarla) ve cihazın
kendi mikrofonuyla sese duyarlı mod. Şerit parça parça farklı renkte yanıyorsa
**LED sayısı** ayarını şeridin gerçek LED sayısına getirin (ör. 5 m × 60 = 300).
Efekt çalışırken renk seçerseniz efekt o renkte devam eder; iki renkli efektlerde
ikinci renk için **Efekt 2. rengi** ışığını kullanın (kapatınca efekt kendi
rengine döner), düz renge dönmek için
**Kapalı** efektini seçin. Kurulum için yukarıdaki HACS adımlarını izleyin; kurulumdan
önce Rhythm Pro uygulamasını kapatın.

Komutların arada bir kaybolmaması için önerilen yol, şeride sürekli bağlı kalan
bir **ESP32** köprüsüdür: ESPHome'da `ble_client` + `send_frame` servisi kurulur,
entegrasyonun *Yapılandır* ekranından **ESP32 üzerinden** seçilir ve düğüm adı
yazılır.

## License

MIT
