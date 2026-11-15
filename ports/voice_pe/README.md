# Home Assistant Voice PE — experimental port

Integrated into this checkout on 14 November 2026 from the reviewed starter
handover. There are now two separate builds: the preserved commissioning probe
and an **experimental shared Main/FX application** at 48 kHz. The shared application uses the
existing Studio/SC protocol, storage and engine; a matched native-16k variant is
available separately. Waveshare/XIAO remain at 44.1 kHz.
Studio now offers a guarded **Voice PE · 48 kHz** firmware option for recognized
stock layouts and project updates; [installation and backup details](../../docs/STUDIO.md#voice-pe-installation-and-recovery).

The connected Voice PE's original ESP firmware has two identical full backups;
an exact restore passed flash verification and a user check of the ring/controls.
See [recovery evidence and downloaded stock images](../../recovery/voice-pe/README.md).

An optional [native 16 kHz matched XMOS/ESP32 build](NATIVE_16K.md) now builds
and passes computer and on-board digital audio/SC integration tests. Physical
16 kHz clocks and XMOS stock recovery/readback are verified. Cold-power, physical IO and user listening checks pass; fresh Studio installation remains 48 kHz, while an
already connected native-16k unit can select its matching ESP update.

## Shared application

`bash host/voice_pe_app.sh build` builds the normal application with a Voice PE
adapter, in `firmware/build-voice-pe-app`. Its wrapper permits build, size and
reconfigure only. Do not follow IDF's generic full-flash commands for this board.

From 15 November 2026, the shared application uses **0 dB DAC gain**. Its first
upgrade from the quiet profile clamps startup software volume to at most **5%**,
before audio starts, and records that transition. Later power cycles retain the
user’s normal volume choice. The user confirmed stronger, clean output and a
cold power cycle retaining 10%. [Gain update evidence](../../evidence/voice-pe-unity-gain-20261115.json).
The separate commissioning probe remains at −24 dB.

The playback adapter retains the XMOS-provided clocks, configures the codec at
0 dB playback gain, and preserves stereo S16 application PCM in S32 I²S
slots. Main/FX and host admission use the actual 48 kHz rate. Ordinary graph
replacement retains the existing fades; hardware codec transactions remain off
the audio task. USB identity is `VoicePE-0697d4` / `esp32-1020ba0697d4` on the
commissioned unit. Patch/source readback, PCM capture and resource reporting use
the existing protocol. Actual SC discovery and a friendly-name volume message
have also passed through the refreshed Studio USB bridge. Wi-Fi code is shared, but Voice PE Wi-Fi qualification is
still pending.

[Button, dial, RGB LED bus map and examples](CONTROLS.md). Inputs are 0–2,
individual LEDs 3–38, shared RGB 39–41, and 42 onward is reserved for Grove.
No Grove driver is activated.

An [optional 16 kHz design](LOW_RATE.md) describes a lower-rate DSP pipeline
feeding the existing 48 kHz wire stream. It is not enabled or advertised as
supported firmware yet.

The reviewed storage table keeps the original bootloader, OTA metadata, app0 and
NVS at their original addresses. It shortens the originally empty app1 to
0x3c0000 bytes and assigns its tail at 0xb90000 to a 4 MiB `storage` filesystem.
A first-use format is allowed only at that exact new region. Existing stock NVS
is retained; project settings add their own namespace. The original same-unit migration has full recovery backups. Studio’s generic
installer additionally identifies recognized stock/project layouts, requires a
verified full ESP backup before stock migration, and selects app0 on first
installation. Unknown layouts are rejected. The commissioning probe below retains the original table.

## Build and computer checks

```sh
python3 host/test_voice_pe.py
python3 host/test_input_buses.py
python3 host/test_voice_pe_codec.py
bash host/voice_pe.sh build
bash host/voice_pe.sh size
```

The wrapper uses the existing ESP-IDF 5.5 environment and an isolated
`build/voice-pe` directory. It accepts one build/size/reconfigure action only;
it deliberately rejects flash, erase, monitor and extra arguments. The normal
IDF output prints generic flash instructions: **those are not the reviewed
deployment operation**. They would overwrite stock boot/partition/OTA data.

For this unit the application can instead be installed at the verified `app0`
offset `0x10000`, preserving its stock bootloader and partition table. Such a
write still replaces the stock application and requires the exact-unit recovery
checks; do not substitute a remembered port or another board's image. The local
partition CSV matches this inspected unit, not a guaranteed universal layout.

## Preserved commissioning probe scope

- Uses the current generated FM1 engine and qualified production kernels, with
  optional DSP candidates disabled.
- Checks actual 16 MiB flash and 8 MiB PSRAM, then renders the real gated-sine
  fixture **offline** at 48 kHz. Nothing rendered is sent to a DAC.
- Holds the speaker amplifier enable and LED-ring power low at boot. Only an
  explicit bench tone temporarily enables the speaker. A dark ring is expected;
  it is not the stock user interface.
- Uses slave/Philips/stereo-S32 I²S. Arbitrary audio start remains blocked:
  `voice_pe_audio_start()` returns `ESP_ERR_NOT_SUPPORTED`.
- Probes **only** the codec (`0x18`) and XMOS (`0x42`) for an I²C address ACK,
  without sending register addresses or payloads. Counts input-clock rising
  edges over two bounded, approximately 100 ms gates using hardware pulse
  counters with overflow accumulation. Logs measured frequencies and gate
  durations. The ±2% nominal windows are a coarse survey; they do not establish
  duty cycle, MCLK, I²S alignment or codec configuration.
- Initializes the codec at `0x18` with digital/analog mute retained, checks the
  programmed routing/gain registers and power flags, then verifies mute again
  after DMA. [Codec sequence, first listening test and bench commands](CODEC.md).
- Only after both devices acknowledge and both clocks fall within the nominal
  windows, runs a **literal-zeros-only** DMA test: preloads the whole 6,144-byte
  ring, enables slave TX, submits 1,500 blocks of 64 stereo frames with 100 ms
  write timeouts and an overall three-second submission budget, then disables
  and deletes the channel and leaves data low. Reports preload/submitted byte
  counts, write durations, partial writes and timeouts. The speaker amplifier
  remains low. This test alone does not qualify wire-level PCM contents or
  missing-clock recovery. The separate codec/tone results are documented above.
- Polls button, microphone-mute sense, jack sense and encoder A/B at a nominal
  1 ms interval. Once a second it logs raw levels, transition totals, encoder
  two-bit jumps, poll count and maximum observed polling gap. These are raw
  observations, not a debounced control or encoder-direction qualification.
- Does not initialize NVS, mount storage, start Wi-Fi/Bluetooth, drive Grove,
  reset/reflash XMOS or capture microphones. GPIO9/MCLK remains untouched. The
  survey's bus/counter resources are released, then a codec-only I²C device is
  retained by the bench app for mute control.

The [portable input-bus component](../../firmware/components/input_buses/README.md)
is imported and tested at 16/44.1/48 kHz. The shared application supplies its
button/dial/mute snapshot to Main and FX through the Voice PE adapter. Grove
sensor drivers remain deferred; the portable sensor prototype does not activate
them on the board.

## Remaining work

[Commissioning evidence](../../evidence/voice-pe-silent-20261114.json) records
the actual board memory, offline DSP, raw input observations, warm/cold clock
survey and original zero-DMA results. The newer [codec evidence](../../evidence/voice-pe-codec-20261114.json)
records the tone-capable build and its successful silent cold-start check.
That evidence records the earlier bench image. The [shared-app evidence](../../evidence/voice-pe-shared-app-20261114.json)
records verified USB transfers, stereo/FX captures, remote notes and the encoder
pull-up correction. The user confirmed ring/button response, subsequent physical encoder movement
and audible button-triggered speaker sound at 25% volume. The faster dial,
button release and normal operation after a physical power cycle also passed. Missing-clock recovery, physical
jack audio, Grove drivers and Voice PE Wi-Fi remain pending.
An observed maximum 6 ms gap across USB reopen intervals
means the 1 ms input poll is not a guarantee of lossless fast encoder capture.
Direction, detent resolution and debouncing need their own qualification.

The [integration map](PORTING.md) retains the original acceptance plan. The shared
board adapter, actual-rate admission, Main/FX, scheduling and diagnostics are
implemented. The master FX wrapper accepts 16/44.1/48 kHz, with delay/bus/reset
regressions and on-board Voice PE FX checks. Remaining work includes recovery
from missing clocks and runtime faults, loaded Wi-Fi, physical jack output and
broader sustained-load qualification. A rejected/failed audio initializer can
still require a normal power cycle; the literal-oscillator admission guard
catches the reproduced negative-LFPar case before upload.

[Source pin map](SOURCES.md) and [Grove draft](GROVE.md) retain their original
source-check dates. `source-manifest.json` describes the handover's pinned
references, not a claim that this checkout still equals its older base commit.
