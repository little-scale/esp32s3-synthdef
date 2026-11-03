# Standard check after installing a module

Use this procedure for the next newly connected AMOLED V2 or XIAO modules.
The standard listening source is [module-audio-check.scd](../examples/module-audio-check.scd),
the user's eight-saw/LFNoise2/Resonz/MiVerb Function. Deploy it as an autonomous
sound block, with the separate master FX slot bypassed. Its internal MiVerb
remains part of Main. It needs no touch, external gate or SC pattern to sound.

1. Identify the exact USB module and choose its matching firmware: headed
   AMOLED V2 (16 MB flash) or headless XIAO (8 MB flash). See [Build/flash](BUILD.md)
   and [XIAO wiring/build](HEADLESS.md). A fresh module needs its full matching
   bootloader/partition/application bundle. An application-only update requires
   a verified compatible partition table. Keep recovery backups private.
2. Verify its build identity, startup telemetry and saved settings. Open Studio
   using the session URL printed by `host/studio.sh`; a plain localhost page in
   a new tab may need that URL to obtain its session key. Connect by USB to the
   exact module. This procedure does not install firmware through the browser.
3. Run the standard check from the repository root:

   ```sh
   python3 host/qualify_module_audio.py \
     --device-id YOUR_EXACT_MODULE_ID \
     --report build/host/module-audio-check.json
   ```

The helper backs up the current Main package, selection and module volume under
`build/host/private/`, then replaces Main slot 1 with **Module audio check**.
It selects master Bypass, sets output volume to 20%, verifies upload/readback,
and observes telemetry for 30 seconds. The FX program is retained. It supports
an empty Main slot on a fresh installation; the protected factory patch is not
replaced. CPU peaks are recorded without stopping on a percentage threshold;
new clipping, numerical, queue, write or DMA faults fail the check and stop Main.
The helper leaves a successful test running. `--seconds` and `--volume` adjust
the observation duration and level. Module volume set this way is volatile;
the previous saved volume applies on reboot unless changed with the device slider
or Studio's **Output volume** slider (release to save).

Listen through the board's speaker or connected DAC and record a separate user
confirmation of clean sound. Telemetry alone cannot verify analogue output.
This is a demanding listening/load fixture, not a low-load factory fallback or
a guarantee that every admitted graph meets its deadline. Use Panic or
`ESP32.stop(target)` to stop it; Restart Main starts the autonomous block again.
The saved block also starts on reboot. Replace Main with the intended instrument
after commissioning, and enable or replace master FX explicitly when wanted.

The first AMOLED run [sounded clean according to the user](../evidence/amoled-module-audio-check.json),
with master bypass, 25% output volume, 92.5% maximum sampled average CPU and a
136.8% sampled peak over 30 seconds. No new reported audio fault counters occurred.
Those figures apply to that recorded build and workload; they are not a strict
per-block deadline pass.

The next fresh AMOLED V2, **AMOLED-8d5054** (`esp32-2884858d5054`), was
[installed and verified](../evidence/amoled-8d5054-install.json) with headed build
`33f68d0b61fb7cfd7b2dd7254e13db27765608ac1b566fd70e0b329254039e9f`.
This revision makes the first-boot volume and initial slider level 20%; existing
saved volume preferences continue to take precedence. Startup was queried at
20% before applying any host volume command. A private factory flash backup was
taken, then the matching bootloader, partition table and headed app were written
and hash-verified without a full-chip erase.

The [standard audio check](../evidence/amoled-8d5054-audio-check.json) was saved
to Main, played autonomously with master FX bypassed, and passed a 30-second
observation with no new reported audio faults. Maximum sampled average load was
93.1%, with a 134.1% peak. The user confirmed clean sound and the slider showing
20%. These are listening/telemetry results, not strict deadline qualification.

**AMOLED-8d507c** (`esp32-2884858d507c`) subsequently received the identical V2
image. Its [installation record](../evidence/amoled-8d507c-install.json) verifies
20% startup volume, and its [standard audio check](../evidence/amoled-8d507c-audio-check.json)
completed 30 seconds with no new reported audio faults, Main running and master
FX bypassed. The user confirmed clean sound and 20% on the slider. The first USB
handshake needed a reconnect after startup; the successful retry required no
additional firmware write. Its private recovery backup is retained locally.
