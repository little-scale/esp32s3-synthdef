# Voice PE Grove DLight input

The **M5Stack Unit DLight U136 (BH1750FVI)** now connects to the shared SynthDef
application through Voice PE's external Grove socket. The driver is included in
the standard 48 kHz and matched native-16k builds. Hardware verification below
used **VoicePE-0697d4 at native 16 kHz**, with its existing XMOS image unchanged.
This does not add a Grove driver to the separate RNBO application.

| Bus | Read with | Value |
| --- | --- | --- |
| 42 | `In.kr(42)` | Linear normalised light: `clip(lux / 1000, 0, 1)` |
| 43 | `In.kr(43)` | Lux, without the 1,000-lux normalisation clamp |
| 44 onward | Reserved | Further Grove channels |

Both Main and FX read the same physical bank. These are input-only addresses;
physical LED `Out.kr` writes remain limited to buses 3–41. Existing button,
dial, mute and LED assignments retain their meanings.

## New data and held values

Bus 42 and 43 change **only after a successful new sensor reading**. The audio
task checks a generation mailbox once per block and writes both values only
when that generation is new. Between sensor readings, audio blocks retain their
previous values. A failed read does not publish a fake zero or reset the buses.
Availability, error count and data age are reported separately. Before the first
valid measurement, both buses start at zero.

The sensor uses continuous high-resolution mode with default MTreg=69. The
first read waits at least 180 ms after starting measurement; later reads are
spaced at least 200 ms apart, approximately five readings per second. There is
no data-ready pin on this unit: the interval exceeds the documented worst-case
conversion time. Equal-valued readings still count as fresh measurements; this
is freshness handling, not value deduplication. There is no extra smoothing in
the driver; use `Lag.kr` in a patch when desired.

I2C transactions run on the controls task, with a 5 ms timeout. The audio path
has no I2C transaction, allocation, spin/retry loop or waiting. Its mailbox uses
aligned 32-bit atomic loads/stores; the Xtensa build audit rejects atomic runtime
helpers. A missing sensor or failed read is retried after one second, while
button/dial/LED operation continues. Ordinary sensor unplug/reconnect is handled
by reissuing power-on, measurement-time and mode commands. Initial GPIO/I2C
allocation failure disables this optional driver until restart.

## Connection and protocol

The existing unmodified Grove cable was used for the hardware test. Voice PE's
dedicated external bus is **SDA GPIO1, SCL GPIO2, power-enable GPIO46**. It is
separate from the internal codec/XMOS control bus on GPIO5/6. The port's power
enable is set high, and only the DLight's configured I2C address **0x23** is
accessed, at 100 kHz. This is a module-specific driver, not a general I2C scan or
automatic identification system for arbitrary Grove sensors.

The [M5Stack unit documentation](https://docs.m5stack.com/en/unit/Unit_DLight)
identifies the BH1750FVI and address. The [official Voice PE Grove configuration](https://github.com/esphome/home-assistant-voice-pe/blob/dev/modules/grove-i2c.yaml)
provides the pin/power assignments. The [BH1750FVI datasheet](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/hat/BH1750FVI.pdf)
documents the high-resolution timing and big-endian result conversion
`lux = raw / 1.2`. No codec clocks, XMOS firmware or microphone route are changed.

## Use from SuperCollider or Studio

Inside a sound Function or SynthDef:

```supercollider
var light = In.kr(42);  // 0..1 for 0..1000 lux
var lux = In.kr(43);    // retain values above 1000 lux
```

The [complete sound/LED example](../../examples/voice-pe-dlight.scd) uses normalised
light for ring colour and raw lux for pitch. Compile it as a Sound block in
Studio. For SC deployment, replace its `.play` suffix with
`.playESP32("VoicePE-0697d4")`. The example was compiled and admitted at both
16 and 48 kHz; it was not installed over the user's existing patch.
No SC extension update is needed to use the input buses.

For status using the existing SC request API:

```supercollider
ESP32.request(\inputs, (target: "VoicePE-0697d4")).onDone(_.postln);
```

Each result includes `grove_light`: `enabled`, `available`, `has_sample`,
`values`, `normalise_lux`, `samples`, `errors`, `age_ms`, `sequence`,
`audio_sequence`, `last_error` and `hold_last`. `age_ms` is −1 before the first
sample. `audio_sequence` identifies the latest new sample consumed by the audio
owner. Failed reads change status, not the retained sensor values or sample
generation. While disconnected, held bus values alone do not indicate whether
the sensor is currently available; inspect the separate status.

## Verification — 19 November 2026

[Hardware and preservation evidence](../../evidence/voice-pe-dlight-20261119.json)
records the measured range, freshness checks and remaining qualification.

- Sanitised computer tests cover command order, conversion deadlines, fresh-only
  publication, held values on read failure, reconnection, dark/full-scale data,
  generation rollover and skipping an in-progress publication without spinning.
- The actual Grove adapter is exercised with fake IDF I/O: the dedicated pins,
  address, clock and timeout, feature disabled, three initialisation failure
  positions, JSON status and successful recovery are checked.
- Native engine tests exercise `In.kr(42, 2)` with two voices sharing the bank
  at 16/44.1/48 kHz, including held values and graph restart. Existing control,
  LED priority and multi-rate delay/admission tests pass. Both Voice PE images
  cross-build and pass their strict build audits.
- The native-16k app was installed through the protected app-only updater.
  Its verified recovery backup and checksums retain boot metadata, NVS, the
  RNBO app and storage. Main and FX graph/source readback were unchanged, and
  the latest user-selected 18% volume was retained.
- Cover/light testing recorded 752 observations, spanning **0–3,157.5 lux**,
  with no sensor communication errors. Repeated queries between fresh samples
  retained the same values; normalisation and the raw-lux channel agreed.
  The audio owner consumed each observed publication within at most one sample
  generation of the status snapshot.

Physical 48 kHz sensor operation, unplug/reconnect and cold power-cycle have
not been tested in this session. Initialisation/failure/recovery behaviour has
computer coverage. Audio-health evidence retains the existing cumulative DMA
queue counter rather than hiding or resetting it.

```sh
python3 host/test_voice_pe_dlight.py
python3 host/test_voice_pe_controls.py
python3 host/test_voice_pe_rates.py
```
