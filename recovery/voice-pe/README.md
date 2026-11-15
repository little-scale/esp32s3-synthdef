# Home Assistant Voice Preview Edition recovery

Recovery assets collected on 14 November 2026, before installing any SynthDef
firmware on the connected Nabu Casa Voice PE. These are **Voice PE** assets, not
XIAO or Waveshare firmware.

## Downloaded manufacturer firmware

| Source | Release | Local image | Size | Flash offset in manifest |
| --- | --- | --- | ---: | ---: |
| Current Nabu Casa installer | 2026.9.1 | `2026.9.1/stock.factory.bin` | 3,346,432 bytes | `0x0` |
| Legacy ESPHome installer | 26.9.0 | `26.9.0/stock.factory.bin` | 3,315,584 bytes | `0x0` |

Both image SHA-256 hashes were checked against their corresponding official
manifests. The legacy image also matched the GitHub release asset digest.
`download.json` in each release directory records the exact URL, size, hash and
manufacturer-specified offset. `official-manifest.json` and
`legacy-manifest.json` preserve the manifests fetched that day.

The newer manufacturer's release number differs from the legacy site's release
number. Neither is assumed to be the version originally installed on this unit.

- [Current manufacturer installer](https://firmware.nabucasa.com/install/voice-pe/)
- [Normal stock reinstall instructions](https://support.nabucasa.com/hc/en-us/articles/25800241218717-Reinstalling-the-firmware-on-Home-Assistant-Voice-Preview-Edition)
- [Reinstall from bootloader mode](https://support.nabucasa.com/hc/en-us/articles/25800285426589-Reinstalling-the-firmware-on-Home-Assistant-Voice-Preview-Edition-from-bootloader-mode)

## Exact-unit backup and recovery test

The connected unit was positively matched using USB serial and eFuse MAC:
`10:20:ba:06:97:d4`. At inspection it enumerated as `/dev/cu.usbmodem1101`.
Port names may change: identify the device again before any future operation.

Verified inventory:

- ESP32-S3 QFN56, silicon revision v0.2.
- 16 MiB SPI flash; chip features report 8 MiB embedded PSRAM.
- Secure boot, flash encryption and secure download mode disabled.
- A valid ESP-IDF partition table at `0x8000`, decoded and checked using
  ESP-IDF's partition-table utility.
- The first application's descriptor names `home-assistant-voice`, reports
  version `2025.3.3` and ESP-IDF `5.1.5`. This descriptor alone does not establish
  the Voice PE product release number or the running OTA slot.

The observed layout is unit-specific evidence, not a flash recipe for other
boards:

| Partition | Type/subtype | Offset | Length |
| --- | --- | ---: | ---: |
| otadata | data/ota | `0x9000` | `0x2000` |
| phy_init | data/phy | `0xb000` | `0x1000` |
| app0 | app/ota_0 | `0x10000` | `0x7c0000` |
| app1 | app/ota_1 | `0x7d0000` | `0x7c0000` |
| nvs | data/nvs | `0xf90000` | `0x6d000` |

Private evidence is kept in `private/1020ba0697d4-20261114/`, including inventory,
raw serial logs, decoded partition information and full-flash backups. Backups
are read twice without a normal application boot between them and must match
byte for byte before a recovery write is allowed. Treat an incomplete image or
an absent successful `backup.json` as **not a verified backup**.

Recovery execution on this unit:

- **PASS:** two complete 16,777,216-byte reads matched byte for byte, with no
  normal application boot between them. The original image SHA-256 is recorded
  in the private `backup.json` and `image-inspection.json` records.
- **PASS:** original bootloader and application embedded SHA-256 checks; valid
  partition-table checksum and partition bounds. `app1` was empty. The valid
  OTA record selected `app0`.
- **PASS:** restored the original full image to `0x00000000–0x00ffffff`, keeping
  its flash-mode, frequency and size header parameters. The write necessarily
  erased and rewrote those sectors; no separate chip-erase command was used.
- **PASS:** the flashing tool's digest check and a separate full-range device
  MD5 comparison both matched the original image **before normal boot**. This
  was digest verification, not a third full USB read or an on-device SHA-256
  comparison.
- **PASS, user-confirmed:** stock LED ring/physical controls working again after
  the reset recovery described below. Speaker, microphones, Home Assistant
  pairing and voice recognition were not separately tested.

The first full read took 381 seconds; increasing the transfer setting to
3,000,000 baud reduced the second to 167 seconds. The full-image recovery write
took 67 seconds, transferring 2,305,777 compressed bytes. These are measurements
of this host/connection/tool combination, not limits on the ESP32's USB or DSP.
Tool: esptool `4.12.dev2`, ESP-IDF 5.5 Python environment. `restore.json` and
`restore.log` preserve the concrete image hash, range, checks and operation log.

**Neither downloaded newer stock release has been flashed.** This test restored
the unit's own starting ESP state; it did not test a fresh installation using
the manufacturer's current image.

### Reset issue observed on this host

The first RTS-based reset did not start the app: the user reported a dark ring,
and the flasher stub still answered through an atomic serial open that did not
request a reset. A subsequent volatile RTC watchdog reset, after clearing the
volatile force-download bit, caused USB to disconnect and re-enumerate. A
further loader check through an atomic open received no reply; the user then
confirmed the ring and controls worked. **No second flash write was needed.**

All attempted USB console captures were empty, including the initial capture.
An empty console is therefore not used as evidence for either a healthy boot or
a failed boot. The recovery result combines verified flash contents, the reset
observations and the user's physical check.

If the same reset problem recurs, do not repeatedly rewrite verified firmware.
Recheck the unit, control-line handling and loader state, then use the appropriate
reset method. This checkout's `host/serial_port.py` provides an atomic DTR/RTS
opening method for native ESP USB on macOS. A command labelled `no_reset` is not
by itself proof that a serial port's opening sequence cannot reset the device.

## Scope and precautions

- Full ESP flash can contain Wi-Fi credentials, API keys and pairing settings.
  The entire `private/` directory is ignored by the repository, and `.bin`/`.elf`
  files in this directory are also ignored. Keep backups private and retain a
  separate secure copy before relying on them for a future restore.
- The planned first recovery test restores this unit's own verified image at
  offset zero, keeping its existing ESP firmware version, partitions and
  settings. It is not a settings wipe or an upgrade to the downloaded release.
- A full ESP backup does **not** include eFuses or the separate XMOS flash.
  No eFuse changes, security changes or direct XMOS firmware writes are part of
  this test. Stock firmware may manage XMOS updates during normal operation;
  restoring the original ESP image avoids deliberately selecting a newer stock
  release, but does not independently verify XMOS state.
- Re-check the exact unit, security state, full image size and hashes before
  restoring. Do not use another unit's private backup, `erase_flash`, `--force`,
  or the XIAO/Waveshare flashing instructions.
- Official factory images can restore supported stock ESP firmware but may
  require setup again and are not substitutes for an exact-unit backup.
- If software cannot enter the loader, the official procedure is to disconnect
  power, hold the center button, reconnect USB, briefly keep holding and release.
  This differs from holding the button for a long time while the stock app is
  running, which can reset settings.

Flash-tool checks and a successful boot are separate from checking the physical
speaker, microphones, dial, buttons and LED ring. Record those outcomes separately.

## Native-16k XMOS experiment recovery asset

On 15 November 2026, the official XMOS v1.3.1 **upgrade** image was saved in
`xmos/ffva_v1.3.1_upgrade.bin`. Its MD5 matches the official pinned ESPHome
configuration; `xmos/download.json` records its source URL and SHA-256.
This is a separate processor image, not an ESP32 image and not a full XMOS
flash backup. A stock-recovery trial wrote it only to XMOS upgrade alternate 1,
rebooted and read it back exactly before the custom native16 trial. Factory
readbacks remained unchanged after both writes; the originally unused upgrade
slot now contains the verified native16 image. The data interface returned zero
bytes before and after; no write targeted factory or data alternates.

The [native-16k build and paired recovery procedure](../../ports/voice_pe/NATIVE_16K.md)
requires readback of the actual unit's XMOS partitions before any upgrade write.
The latest user Main/FX/source and 9% volume setting were saved privately under
`private/native16-20261115/`; test mute was persisted for preparation. While
awaiting the USB-selector change, original 48k playback and 9% volume were
restored and verified (`waiting-cleanup.json`). Original 48k ESP and new
16k images are snapshotted under ignored `build/host/voice-pe-native16/images/`.

The completed native16 trial verified the stock recovery upgrade, custom XMOS
reboot/readback, physical clocks, digital/SC audio, cold restart and user listening.
The original Main/FX packages, controls, bypass, active playback and saved 9%
volume were restored and verified afterward. The unit remains on the matched
native16 pair; stock 48k recovery images and private backups remain available.
See [final native16 evidence](../../evidence/voice-pe-native16-final-20261115.json).
