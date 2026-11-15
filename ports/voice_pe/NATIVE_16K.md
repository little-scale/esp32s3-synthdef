# Voice PE native 16 kHz experiment

15 November 2026: **the matched XMOS/ESP32 pair is installed on VoicePE-0697d4
and digital audio/SC integration checks pass on the board.** Measured startup
WS is 15,996.5 Hz and BCLK is 1,023,986.6 Hz. Cold-power, physical IO and user
listening checks pass. Stock/fresh Voice PE installation remains 48 kHz. Studio offers
the native ESP update only for an already connected native-16k USB unit and
rejects mismatched rate updates; first conversion still uses the paired procedure.

This is a matched XMOS/ESP32/codec configuration. Installing only the ESP image
against stock 48 kHz XMOS clocks fails the clock check and leaves the amplifier
off. Use the paired procedure below, not IDF's generic full-flash command.

| Property | Normal Voice PE | Native experiment |
| --- | ---: | ---: |
| Main and FX sample rate | 48,000 Hz | 16,000 Hz |
| Physical stereo I²S WS | 48,000 Hz | 16,000 Hz |
| Stereo 32-bit BCLK | 3.072 MHz | 1.024 MHz |
| MCLK | 24.576 MHz | 24.576 MHz |
| Codec NDAC / MDAC / DOSR | 2 / 2 / 128 | 6 / 2 / 128 |
| Engine block | 64 frames | 64 frames |
| Control period | 1.333 ms | 4 ms |
| Output converter | None | None |
| Audio bandwidth upper bound | 24 kHz | 8 kHz |

Most potential DSP savings come from rendering fewer samples. Native output
also avoids a sample-rate converter, but requires maintaining a custom XMOS
image. A threefold reduction in sample count is not a measured threefold CPU
improvement. Graph node/workspace limits remain unchanged. Delay arena savings
depend on power-of-two allocation; fixed reverb/model memory is not reduced.

The shared SC compilation, Main/FX definitions and instances, exposed arguments,
network messages, groups and patterns remain the existing implementations.
Admission is evaluated independently at each recipient's rate. Voice PE's
button/dial/mute buses 0–2, LED channels 3–38 and broadcast channels 39–41 retain
their assignments. Grove buses 42 onward remain reserved.

For a first sound after commissioning, choose this module's actual ID or alias:

```supercollider
~voice = "VoicePE-0697d4"; // replace with the selected module
ESP32.module(~voice, \volume, 0.05);
{ SinOsc.ar([440, 660], 0, 0.1) }.playESP32(~voice);
```

The first native-16k activation starts at **0% volume** and records a separate
`vpe_16k` commissioning marker before autoplay or codec DMA can start. Later
boots retain the user's saved volume. This does not change normal 48k startup.
The 6×128-frame DMA queue has 48 ms of capacity at 16 kHz; capacity is not a
measurement of total latency. The control period remains 4 ms.

MiRings1–6 require at least 32 kHz in the current renderer and are rejected
before activation at 16 kHz. Other effects are not promised to have identical
frequency response or tail lengths across rates: the finite-output smoke test
is not a spectral or reverb-tuning equivalence test. The existing 16-to-48 kHz
converter draft is a separate, unfinished alternative and is not selected here.

## Building the pair

ESP32, with the usual installed ESP-IDF 5.5 environment:

```sh
python3 host/prepare.py
bash host/voice_pe_native16.sh build
python3 host/record_build.py --build-dir build-voice-pe-native16 --output voice-pe-native16-build-20261115.json
```

The wrapper permits build/size/reconfigure only. It uses a separate sdkconfig
and output folder. The measured Saw/Impulse candidates are enabled for this
experiment, matching the connected unit's preceding oscillator test build.

XMOS, with Docker running and enough disk space for its compiler and sources:

```sh
python3 host/build_voice_pe_xmos.py prepare
python3 host/build_voice_pe_xmos.py verify
python3 host/build_voice_pe_xmos.py build
```

Preparation downloads the pinned official v1.3.1 source and recursive submodules
and applies the three reviewed patches in `xmos/native16/`. It refuses a
different source revision or unexpected tracked changes in those repositories.
The build runs the pinned official XMOS compiler container without network or
USB access. It never flashes hardware.

- Source: `esphome/voice-kit-xmos-firmware` commit
  `1a1df7c2b3e578431b1550a8defe8ae2c8b54d93`.
- Compiler: XTC 15.3.0, official `ghcr.io/xmos/xcore_builder` digest
  `cb301ec2c847d622a4a779a7fbbb131eba0c8f1931f53b938516b09529065e16`.
- Application patch: select native 16 kHz, I²C version 1.3.116 and distinctive
  USB `bcdDevice=0x1610` marker. The USB marker is not a normal release number.
- RTOS patch: exact upstream [internal-tools-API compatibility fix](https://github.com/xmos/fwk_rtos/commit/180633d44f1eef9a6a4d841930d188565a612891).
- Microphone-array patch: explicitly include the generated `platform.h` board
  port declarations required by this newer compiler; no pin assignments change.
- Upgrade output: `build/host/voice-pe-native16/xmos-src/build-native16/example_ffva_int_fixed_delay_upgrade.bin`.
- Build manifest: `build/host/voice-pe-native16/xmos-build.json`.

The image is 278,528 bytes. Both factory-loader 15.2 and 15.3 packaging produced
byte-identical images. XMOS linker estimates remain within each 512 KiB tile:
tile 0 uses at least 455,940 bytes and tile 1 uses 443,412 bytes. The linker reports
stack-analysis caveats, so these are build constraints, not measured runtime
stack/heap headroom.

## Tests completed on the computer

```sh
python3 host/test_voice_pe_native16.py
python3 host/test_voice_pe_rates.py
python3 host/test_voice_pe_controls.py
python3 host/test_voice_pe_codec.py
python3 host/test_input_buses.py
python3 host/test_audio_transition.py
python3 -m unittest discover -s host -p test_voice_pe_firmware.py
python3 -m unittest discover -s host -p test_studio.py
python3 -m unittest discover -s host -p test_voice_pe_xmos_dfu.py
```

The SC tests require the installed SuperCollider app and permission for its GUI
runtime, even though compilation is silent and no local audio server is booted.

- Thirteen graphs, including twelve-oscillator/Impulse variants, Comb Cloud,
  Saw/Resonz/MiVerb and separate master MiVerb, render for four seconds twice at
  each of 16/48 kHz. Audio/control outputs remain finite; repeated seed-12345
  starts reproduce the same within-rate sample hash under bounds/undefined and
  float-conversion sanitizers. Different-rate audio hashes are not compared.
- Saw/Impulse reference comparisons additionally pass 48 boundary graphs at
  16 kHz: 294,912 blocks, 37,748,736 interleaved sample values, 96 explicit
  constructor checks and 42 matching fault cases. Audio, RNG and recursive state
  match, excluding only the documented new Saw setup-cache fields.
- A further 1,454-graph candidate/reference comparison passes at 16 kHz over
  93,056 blocks. This includes matching raw-renderer fault cases and does not
  establish that every fixture is admitted or every UGen is hardware-qualified
  at 16 kHz. [Inventory evidence](../../evidence/voice-pe-native16-inventory-20261115.json).
- Instrument wrapper: 16 kHz pitch, note release, stale IDs, panic, cancellation
  and retrigger checks pass alongside 44.1/48 kHz.
- Main/FX: delay admission budgets, 100 ms stereo delay timing and control-bus
  binding survive reset and definition start at 16/44.1/48 kHz. Both admission
  paths reject Rings at 16 kHz.
- Physical input normalization and LED control-output lifecycle pass at all
  three rates; fade timing also covers 16 kHz.
- Codec tests cover quiet/unity gain at both 16/48 kHz, all 140 initialization
  I/O failure positions per profile, corrupted readbacks and all 36 unmute I/O
  failure positions. NDAC readback must match before unmute.
- Twenty firmware-loader tests and fifty-four Studio/compiler regressions pass.
- Eleven XMOS backup-helper checks pass with simulated USB responses, including
  wrong/replaced devices, duplicate interfaces, read failures, unequal repeated
  reads, private file permissions and an actual child-process file-size bound.
  These do not count as a hardware XMOS backup or recovery test.

## Hardware procedure and recovery

The original Main/FX/source/settings were backed up privately before testing.
Two factory reads matched official XMOS v1.3.1 exactly; the upgrade and data
interfaces initially returned zero bytes (unused or not exposed). The read-only
helper records this explicitly rather than claiming a full physical flash dump.
The stock recovery image was written to **upgrade alternate 1**, rebooted and
read back exactly. The native image then passed the same reboot/readback check;
factory readback remained unchanged after both writes. No factory/data write
was issued. The guarded ESP updater installed the matched native app and
verified protected-region hashes before restarting. Its first activation
reported 0% and a captured zero PCM stream.

On-board results are in the [XMOS](../../evidence/voice-pe-native16-xmos-hardware-20261115.json),
[audio](../../evidence/voice-pe-native16-audio-hardware-20261115.json) and
[actual SuperCollider](../../evidence/voice-pe-native16-sc-hardware-20261115.json)
evidence records:

| Workload | Average CPU | Maximum window peak in short run |
| --- | ---: | ---: |
| Twelve SinOsc with LED/Splay controls | 16.2% | 18.5% |
| Twelve Saw with LED/Splay controls | 37.2% | 45.9% |
| Twelve audio-rate Impulse branches | 20.5% | 22.6% |

These are short normal-firmware observations, not a matched-seed rate-to-rate
benchmark or a worst-case CPU bound. Stereo capture confirms 440/660 Hz, live
updates to 550/825 Hz, a 100 ms delay at 1,600 frames, stop/panic silence and a
separate MiVerb tail after stopping Main. Real `sclang` checked Function
`.playESP32`, `ESP32.set`, a literal SynthDef `.sendESP32` remaining silent until
played, and Pbind note events. Original Main/FX packages were restored and
verified between tests. The user confirmed the button, dial and LEDs before/after a normal power cycle.
The new boot identity, retained 5% volume, active autoplay and fresh clock
measurements (WS=15,997.7 Hz; BCLK=1,023,986.1 Hz) were also verified over USB.
[Cold-start evidence](../../evidence/voice-pe-native16-cold-start-20261115.json).
The user confirmed the repeated musical sequence was clean, including its
reverb tail. Original Main/FX packages, controls, active playback, bypass and
saved 9% volume were then restored and verified. No faults, non-finite samples
or failed audio writes were reported.
[Final verification](../../evidence/voice-pe-native16-final-20261115.json).

1. Unplug USB before opening the enclosure or moving the internal **USB SELECT
   (SW3)** switch. It is on the LED/dial face, near a corner outside the LED ring,
   at the opposite edge from USB-C. Look for **USB SELECT** and **XU316 / ESP32**. Select XU316 and reconnect. No soldering is needed.
2. Match the XMOS USB VID/PID and physical USB path. Its USB serial is not unique;
   keep other XMOS DFU units disconnected. Read the factory, upgrade and data
   partitions through DFU; repeat the reads and compare hashes before writing.
   The read-only helper provides `python3 host/voice_pe_xmos_dfu.py inspect`,
   then `python3 host/voice_pe_xmos_dfu.py backup --path <reported-path>`.
   It binds the topology/device/interface identity on each read, limits each
   read to 180 seconds and applies a real 16 MiB file-size bound to the child
   process. Private files and a success/failure journal go under
   `recovery/voice-pe/private/xmos/`. It never downloads, detaches or resets.
3. Record the installed version/layout and verify the upgrade fits. Write only
   DFU alternate 1, then read back and compare the exact installed bytes. Never
   overwrite the factory or data partitions for this experiment.
4. Unplug, return USB SELECT to ESP32, reconnect and install the matched ESP16
   app with the guarded Voice PE updater, preserving bootloader, NVS and patches.
   For the initial ESP update, activate a Python environment with esptool 4.9–4.x,
   finish the build first, replace the port/MAC placeholders with this exact unit,
   and use the existing guarded updater (not `idf.py flash`):

   ```sh
   python host/firmware_upload.py --board voice-pe \
     --port <USB-port> --mac <12-digit-MAC> \
     --flash-size 16MB --mode dio --frequency 80m \
     --images firmware/build-voice-pe-native16/bootloader/bootloader.bin \
       firmware/build-voice-pe-native16/partition_table/partition-table.bin \
       firmware/build-voice-pe-native16/waveshare_synthdef.bin
   ```

5. Begin muted. Verify WS/BCLK and codec readback, then test known low-level
   tones, notes, delay timing, captures, CPU, bus controls and stop/reload. Test
   cold power and the user's patch only after those pass.
6. To return to normal, restore the verified previous XMOS upgrade and ESP48
   app, then the saved playback/settings state. Keep mute across mismatched-rate
   boots. Test the return to 48 kHz, not just the flash write.

Official stock recovery asset: `recovery/voice-pe/xmos/ffva_v1.3.1_upgrade.bin`,
SHA-256 `11b563d6c51424f49f1e1d3585ba03a073e2802798e6aa067c6734d7ecb6935b`,
MD5 `964635c5bf125529dab14a2472a15401`, checked against the official pinned
ESPHome configuration. This download is not a backup of the installed unit.
An ESP flash backup does not contain XMOS flash.

The manufacturer documents fallback to the factory image when an upgrade is
invalid. A valid image that hangs may not provide USB DFU; retaining the factory
partition alone does not prove recovery from every runtime failure. Establish
the actual unit's readback/recovery behaviour before committing a fleet to this.

## Qualification boundary

This is an experimental native16 profile qualified on the connected Voice PE
using USB/Studio, actual SC authoring/control/pattern messages, digital PCM,
physical dial/button/LED operation, a cold power cycle and user listening.
It is not qualification of every UGen or every peripheral at 16 kHz. Voice PE
Wi-Fi, microphone input, external-jack-specific behaviour and Grove drivers
were not newly tested in this native-rate trial. Existing default Waveshare and
XIAO builds remain 44.1 kHz; normal Voice PE installation remains 48 kHz.
