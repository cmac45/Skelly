# Hardware and wiring

## Parts

| Part | Role |
|---|---|
| **Seeed reSpeaker XVF3800 USB 4-Mic Array with XIAO ESP32-S3** | Skelly's ears and voice: wake words, speech capture with echo cancellation, his speech out of its 3.5 mm jack |
| **ESP32-S3 DevKitC-1 (N16R8)** + **PCM5102A I2S DAC board** | The music player: sound effects and songs on a second speaker |
| **12 V class-D stereo amplifier** + two weatherproof speakers | Left channel: Skelly's voice (speaker in the skull). Right channel: effects and music (speaker at his feet) |
| **2-port 5 V USB charger** (2.4 A per port) | Powers both ESP boards |
| **Camera + [Frigate](https://frigate.video/)** | Person detection that starts a conversation when someone walks up |
| **Smart lights** (optional) | Skelly's stage effects; this build uses Govee curtain lights, a roofline strip and spotlights |

## Music player wiring (ESP32-S3 → PCM5102A)

A full illustrated guide is in [`dac-wiring.html`](dac-wiring.html) (open it in
a browser). The short version:

| DAC pin | ESP32-S3 pin | Notes |
|---|---|---|
| VIN | **3V3** | Not 5V — see below |
| GND | GND | |
| BCK | GPIO5 | Bit clock |
| LCK / LRCK | GPIO6 | Word clock |
| DIN | GPIO7 | Audio data |
| SCK | GND | Grounding SCK makes the DAC generate its own clock |

Solder jumpers on the back of the DAC: **H1L, H2L, H4L to L; H3L (XSMT) to H**
(XSMT low keeps the DAC muted). Avoid GPIO35–37 on N16R8 boards (octal PSRAM)
and GPIO0/3/45/46 (boot strapping).

The firmware sends the **same mono signal to both DAC channels**, so either
RCA plug into the amp carries the whole mix.

## Lessons learned (save yourself an evening)

- **The DAC was silent with its jumpers right.** On these N16R8 boards the
  **5V pin isn't powered from USB**, so the DAC had no power. Touching its LOUT
  pin gave a loud hum — the giveaway that the output stage is switched off.
  Powering VIN from **3V3** fixed it.
- **Everything was quiet even at 100%.** The amp keeps its *own* volume,
  set by whatever phone last connected over Bluetooth. Max it once from a phone.
- **The reSpeaker's voice is quiet compared with music.** Its codec (TLV320AIC3104)
  has a 0–9 dB analog output stage the stock firmware never sets. This build
  adds a **Voice output boost** number entity (`esphome/skelly-voice.yaml`).
  Back it off if loud lines crackle.
- **Volume settings are logarithmic.** Both devices map 0–100% onto a dB scale:
  the music player's 60% is about −20 dB. Keep both at 100% and balance on the amp.
- **USB-C chargers:** many of these dev boards lack the USB-C "sink" resistors,
  so a USB-C-to-C charger may deliver nothing. Use a USB-A charger and an A-to-C cable.
- **Ground loops:** plug the amp's 12 V supply and the USB charger into the
  same outlet or strip.

## Voice satellite (reSpeaker XVF3800)

`esphome/skelly-voice.yaml` builds on
[formatBCE's Respeaker XVF3800 ESPHome integration](https://github.com/formatBCE/Respeaker-XVF3800-ESPHome-integration),
which also updates the XMOS DSP firmware over I2C on first boot. This build adds:

- the two custom wake words, both active at once (Home Assistant's two
  wake-word slots), with per-word sensitivity numbers adjustable from HA;
- a raven caw instead of the stock wake chime (`esphome/sounds/chime_raven.flac`);
- the voice output boost described above.
