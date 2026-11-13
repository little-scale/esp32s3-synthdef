# Native USB reliability — 13 November 2026

## Current result

The buffered console with **batched protocol replies** is qualified for the
conditions tested on **XIAO-3eeb84** (`esp32-1c29043eeb84`, chip revision v0.2),
using source build **`b06188c54dbe`**. Output is limited to **5%**. Main/FX,
storage generations and live controls are preserved, and Studio is reattached.
Physical AMOLED testing and Wi-Fi-under-load testing remain pending. The
attached XIAO is configured for Wi-Fi but currently offline; network settings
were left unchanged.

The latest [requalification summary](../evidence/usb-buffered-requalification-xiao-3eeb84-20261113.json)
supersedes the earlier decision to withdraw the bytewise buffered candidate.
The old failed records remain available; they have not been relabelled as passes.

## Confirmed host opening fix

On macOS, pySerial's separate DTR/RTS updates could pass through a native ESP
reset combination even when both lines were configured false before opening.
The legacy baseline recorded `USB_UART_CHIP_RESET` ROM messages and a changed
boot ID. An initial two-second HELLO timeout contained boot logs, distinguishing
startup delay from a dead USB controller.

`host/serial_port.py` updates the pair together using one POSIX `TIOCMSET`,
preserving other modem bits. Studio and the SC bridge share this `Device` path.
Automatic selection is restricted to **macOS and VID/PID 303a:1001**; other
platforms/adapters retain their existing path. Unsupported combined updates fail
explicitly. Esptool still performs intentional resets when flashing.

The retained host change passed **68 lifecycle cases on the original polled
image**, including **50 consecutive close/reopen cycles** and Studio handoff
with the same boot ID. The [earlier summary](../evidence/usb-reliability-xiao-3eeb84-summary-20261113.json)
records those cases separately from experimental-image results.

## Buffered transport and batched replies

On the original polled console, a 60-second unread-port test left USB responsive
but stopped audio after a **100,484 µs I²S write timeout**, with one failed/partial
write. Later remote commands reported uncertain ownership. There was no observed
MCU reboot. This is distinct from a missing or entirely unresponsive USB device.

The selected firmware installs the SDK USB Serial/JTAG driver with **2,048 bytes
RX and 4,096 bytes TX**, replacing FIFO busy-waits with driver buffering.
Input remains nonblocking, so buttons/network work continue without incoming USB
commands. Initialization failures stop startup explicitly. Existing audio
write-failure checks remain intact; there is no automatic restart masking them.

The first buffered candidate (`414cacc09e45`) still sent protocol replies through
SDK stdio, which enqueues one character per driver call. A 0.1-second recording
needed **1.224 seconds** to capture and download. The selected version routes
USB protocol replies through a small callback that:

- Serializes with stdout and flushes earlier stdio output.
- Queues at most **256 bytes per driver write**, using nonblocking writes and
  yielding one scheduler tick when full.
- Uses a **50 ms enqueue budget** after acquiring stdout and flushing it; lock
  acquisition/stdio flushing are outside that budget, so this is not a hard
  end-to-end latency guarantee.
- Starts on a fresh line, allowing a valid frame after an earlier partial write.
- Preserves the existing reply cache: a lost reply cannot undo an admitted
  command, and a same-ID retry can recover its cached response.

Network exchanges continue to return their reply through the existing network
buffer; only USB console replies use the callback. Telemetry keeps SDK stdio.
Frame encoding, CRCs, upload acknowledgements and patch formats are unchanged.

Three matched 0.1-second capture/download trials now take **0.390–0.395 seconds**
(median 0.391), versus the single 1.224-second bytewise measurement. This is a
capture/transfer timing comparison, **not a DSP speed-up** or universal throughput
benchmark. [Bytewise timing](../evidence/usb-buffered-bytewise-capture-timing-20261113.json),
[batched timing](../evidence/usb-buffered-batched-capture-timing-20261113.json)

## Corrected integration and idle checks

The Main/FX sequence exercises Comb Cloud with temporary MiVerb and frequent
controls, then eight-saw, Comb Cloud KR, triggered harmonics, separate FX tail,
Main Stop and Panic. The user confirmed **clean sound, including the tail**, at
5% during this requalification. Digital assertions are recorded separately.

The final tail fixture keeps a tone running while its first capture downloads,
then stops Main and waits **50 ms** before recording the tail. This excludes the
Main fade and the 6×128-frame DMA queue (about 17.4 ms at 44.1 kHz). Panic must
produce entirely zero PCM.
[Final integration](../evidence/usb-buffered-batched-xiao-final-20261113.json)
The previous one-shot could finish decaying during a
slow download; that test timing failure was not proof of a broken reverb.

The long-idle sequence checks **60 and 300 seconds** in each mode:

- Open USB with no application reads during the gap.
- Closed USB followed by reopening through the production host policy.

After every case, checks require the same boot ID, revision, graph and 5% volume,
advancing audio frames, fresh nonzero stereo PCM, stable free memory and no new
fault, clipping, nonfinite, write-failure, partial-write, DMA-event or control
queue counts. The OS can buffer unread USB data, so an unread application alone
does not prove the hardware FIFO stayed full throughout the interval.
[Idle and audio evidence](../evidence/usb-buffered-batched-xiao-idle-audio-20261113.json)

A bounded replacement test alternates two light Main graphs, temporary MiVerb and
FX bypass. It checks valid PCM, instance ownership, memory and error counters,
then restores the original packages and verifies unchanged saved generations.
[Replacement evidence](../evidence/usb-buffered-batched-xiao-replacement-cycles-20261113.json)

## Harness corrections and preserved failures

The earlier records remain important:

- Reusing stream 712 while restarting sequence numbers correctly triggered
  firmware replay protection. Each soak now gets a fresh nonzero stream.
- Test setup initially enabled extra MiVerb on a saved Main that already had
  MiVerb. Muting output did not reduce that DSP load. Setup now replaces Main
  with the light fixture before enabling test FX; listening also bypasses soak FX.
- The overloaded fixture failed on the original image too, so those maintenance
  failures cannot be attributed solely to buffered console I/O.
- A bytewise buffered run lost capture replies, and another timed out in audio
  maintenance. That image was withdrawn; the later batched build is a separate
  implementation with its own qualification records.

Identified `CAPREAD` now gets **one same-request retry**. `CAPBEGIN` is never
retried, legacy untagged reads remain single-attempt, and a changed recording ID
still aborts the download. Offline tests simulate a lost ACK, permanent loss and
recording replacement. A bounded retry is recovery, not proof that all transport
loss has been eliminated. The intentional unplug on 12 November is excluded
from USB fault evidence.

## Memory, builds and remaining scope

Both board profiles cross-build and pass their audits; **only the XIAO was
physically flashed/tested**. Cached DSP settings were preserved: qualified DSP
kernels enabled for XIAO, disabled for this AMOLED build. A shared source build
ID does not imply identical board configuration.

The selected XIAO application is **1,358,352 bytes** (+9,184 from the polled
image); AMOLED is **1,697,264 bytes** (+9,120). Runtime free internal memory on
the restored XIAO graph is about **81.8 KB**, versus about **92.4 KB** previously:
roughly **10.6 KB** for rings/driver overhead and small transport-state changes.
Graph (21,720), scratch (51,200) and voice (57,896) structure sizes are unchanged.
No DSP equations, precision, audio block size, graph limits or PCM scaling changed.
[Selected build audits](../evidence/usb-buffered-batched-builds-20261113.json)

Startup/graph-maintenance DMA counts are retained in the records; zero deltas
refer to the stated settled test windows, not a claim that boot counters were
zero. These are single-board observations over minutes, not an exhaustive
long-term reliability guarantee. The earlier entirely unresponsive native-USB
symptom has not been conclusively reproduced or explained. No silicon-reset
watchdog, low-level peripheral workaround or automatic audio restart was added.

## Reproducing the checks

The read-only lifecycle probe finds the exact permanent USB identity, refuses
another selected module or an initial volume above 5%, borrows Studio's USB
connection, and verifies boot/state across each gap. Raw console bytes remain
private; public records contain identity, numeric state/timing and reset codes.

```sh
python3 host/probe_usb_lifecycle.py \
  --device-id esp32-1c29043eeb84 \
  --modes unread,closed --gaps 60,300 \
  --output evidence/usb-lifecycle-xiao-long-idle.json
```

Use `--modes closed --gaps .05 --repeat 50` for repeated opening. Production uses
`--open-policy auto`; `legacy` deliberately reproduces old line transitions and
can reset this board. Allowed gaps are 0–300 seconds, with progress every 20
seconds and no reads during a gap. HELLO may retry read-only on the same handle
at startup; changed boot/state still fails the case. The probe sends no patch,
volume, firmware or reset commands. PCM postchecks additionally arm transient
captures, without changing the patch or output level.

The final offline set passes **112 tests**, including host/native SuperCollider checks, patch
transactions and network routing. The real console C code is compiled with
sanitizers against driver stubs: USB enabled/disabled, initialization/fd failure,
packet boundaries through 8,999 bytes, short writes, backpressure, timeout,
invalid driver returns and fresh-line recovery after truncation.

```sh
PYTHONPATH=host python3 -m unittest \
  test_usb_console test_serial_port test_probe_usb_lifecycle \
  test_qualify_dsp_transient test_capture test_control_client test_studio \
  test_patches test_network
```

Local SDK inspection and Espressif's [USB Serial/JTAG guide](https://docs.espressif.com/projects/esp-idf/en/release-v5.5/esp32s3/api-guides/usb-serial-jtag-console.html)
explain the transport paths. Automatic power management is disabled, and I²S
GPIO 7/8/9 do not repurpose USB GPIO 19/20.
[Espressif issue 18996](https://github.com/espressif/esp-idf/issues/18996) remains an
upstream lead for macOS/native-USB problems, not a confirmed identical silicon
fault; it uses IDF 6.0.2, while this project uses 5.5.
