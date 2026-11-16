# Voice PE recovery

The current exact-unit backup, restore results, downloaded official images and
reset workaround are recorded in the [project recovery directory](../../recovery/voice-pe/README.md).

Do not use the XIAO or Waveshare flash commands on this board. The isolated
probe's generic IDF flash suggestions are also not an app-only deployment.
Preserve the stock bootloader, partition table, OTA data and NVS while evaluating
the probe. Keep the private full images and verify the exact unit before any
future restore. A full ESP image does not back up the separate XMOS flash.


## Studio backups

Studio’s 48 kHz Voice PE firmware option now has a separate guarded installer.
Before a stock migration it saves a complete, MD5-verified 16 MiB ESP flash image
under `recovery/voice-pe/private/studio/<mac>/<timestamp>/`. Before a project
update it saves the application sector range and boot/partition metadata. Its
`backup.json` gives exact offsets and hashes. Never substitute an update's
application-only backup for a full factory recovery image.

A first Studio migration preserves bootloader/NVS/PHY but initializes the OTA
records to select app0; the existing-unit app-only update preserves those OTA
records too. These semantics differ from the initial manual same-unit migration,
which retained its existing app0 OTA records. Both keep XMOS untouched.

The known-unit original recovery described above remains available separately.
Unknown layouts and secured/encrypted devices are refused by the new installer.

## Returning from the RNBO player

The guarded updater recognizes the companion `rnbo_s3_voice-pe` application in
app0 on the exact reviewed project layouts. It saves and verifies the installed
application before replacing only app0 with SynthDef firmware; partition/OTA
metadata, NVS, patch storage, the bootloader and XMOS are preserved. The old
application must pass its complete image verification and contain the Voice PE
board marker. An arbitrary project name or app1 selection is still refused.

Choose the SynthDef build matching the installed XMOS clocks. For a device
already clocked at 16 kHz, use the guarded command in
[the native-16 guide](NATIVE_16K.md), without changing XMOS. RNBO package files
remain in storage but cannot be executed as SynthDefs. Previously saved SynthDef
patches/settings may be restored by the SynthDef application after conversion.
