# Mac compilation and saved patches (M4)

The Mac runs SuperCollider; the ESP32 loads and renders the compiled graph.
The `catalog-voice-v2` policy retains the `simple-voice-v1` factory/Mac sine
family and adds exact tested binaries for Phase FM, Harmonic Mix and Filtered Tone. The 154 compiled engine types are a separate fact: they are not all
admitted for uploads or hardware-qualified. See `capabilities.json` for bounds.
An accepted graph still needs workload-specific timing/listening checks.

## Compile, upload and save

Use SuperCollider 3.14.1 and the ESP-IDF Python environment containing pyserial.
Close the serial monitor before using the uploader. Observe the current USB port;
`/dev/cu.usbmodem101` was last seen on this machine.

```sh
python3 host/patches.py compile examples/mac-sine.scd examples/mac-sine.scsyndef
# Activate the installed IDF Python environment, or use its Python executable:
python host/patches.py --port /dev/cu.usbmodem101 hello
python host/patches.py --port /dev/cu.usbmodem101 upload examples/mac-sine.scsyndef \
  --source examples/mac-sine.scd --name "Mac Sine" --save 1
python host/patches.py --port /dev/cu.usbmodem101 list
python host/patches.py --port /dev/cu.usbmodem101 load 0
python host/patches.py --port /dev/cu.usbmodem101 load 1
python host/patches.py --port /dev/cu.usbmodem101 download build/host/exported-sine
```

The source expression must return one `SynthDef`. Compilation does not require
a running audio server. Source is optional UTF-8 archival text; the device checks
its integrity but cannot prove that it compiled to the attached binary. Download
protects existing files and verifies both SHA-256 digests before writing results.
It exports the active graph, source and wire manifest; load a saved slot first to
export it. Existing FM1 `.fmslot` packages are not imported.

On the device, **PATCHES** opens factory slot 0 and eight numbered writable slots.
LOAD recalls a patch. SAVE HERE stores the current graph, attached source and UI
metadata. It stores the compiled defaults, not transient slider positions. Empty
slots cannot be loaded. Page changes release held notes. Load/save pauses audio
deliberately; resume with a new touch after it finishes. PANIC remains available.

At boot, tap PANIC during **TAP PANIC FOR FACTORY** to skip the saved selection
for that boot. The saved patch is retained. Load slot 0 to persist factory selection.
The uploader does not explicitly request a reset; native USB/host control-line
behavior can still cause a reset when connecting. An interrupted unsaved upload
is discarded on restart; the last saved selection remains available.

## Qualified one-voice examples

| Example | Source | Preferred empty slot | Second control |
| --- | --- | ---: | --- |
| Phase FM | `examples/phase-fm.scd` | 2 | Phase-modulation index |
| Harmonic Mix | `examples/additive.scd` | 3 | Second/third partial mix |
| Filtered Tone | `examples/filtered.scd` | 4 | Low-pass cutoff, smoothed at control rate |

All use the same pitch, attack and release controls. Phase FM uses audio-rate
phase modulation of a sine carrier. The filter includes a 100 ms `Lag.kr` on its
cutoff: the unsmoothed version clipped during extreme cutoff jumps and is excluded.

```sh
python host/patches.py --port /dev/cu.usbmodem101 install phase-fm --save 2
python host/patches.py --port /dev/cu.usbmodem101 install additive --save 3
python host/patches.py --port /dev/cu.usbmodem101 install filtered --save 4
```

Catalog admission uses the exact graph SHA after raw-byte verification and parsing;
it does not enable arbitrary graphs containing those UGens. Changing the compiled
name, constants or topology changes that SHA and requires qualification. Archive
source and UI metadata are checked separately. The handshake advertises catalog
IDs, hashes and qualification states; the host checks them before installation.

Here, “qualified” means the exact graph passed the recorded SuperCollider reference,
ESP32 numerical matrix and short timing/output checks. The user also confirmed
all three examples sound clean and stop on touch release. A release soak, two
voices and effects remain separate gates. The reports and measured configuration
are in `evidence/qualified-voices.json` and `catalog-device-final.json`.

For DSP changes, mark affected catalog entries `candidate` before regenerating;
changes to shared rendering/board/UI code require all entries to be rechecked.
Only explicit diagnostic builds accept candidates. `rejected` entries are never
admitted. `host/verify_catalog.py --diagnostic --rounds 3` exercises unsaved examples;
`host/qualify_catalog.py --promote` combines the recorded checks. Regenerate,
rebuild and flash after promotion. `host/verify_catalog.py --install` then installs
into empty slots, verifies saved graph/source/metadata bytes and checks the final
image. It reuses only identical existing entries and finishes on Mac Sine.

## Ownership and activation

Raw graph/source staging uses three preallocated PSRAM buffers. Two graphs reside
in internal RAM; only one graph and one voice render. The service validates the
inactive graph with SHA-256, UTF-8 checks, the authoritative `fm_load` parser and
the device admission policy. Invalid uploads leave the active graph unchanged.

Activation requires a separate acknowledgement. The audio owner fades two
blocks, drains twelve blocks of silence, stops DMA and acknowledges its parked
state. The service checks codec mute through the existing I2C control interface.
It may then write files or settings. Graph replacement runs on the parked audio
owner. DMA restarts on that owner before codec unmute; it continuously supplies
silence until play controls are enabled. An acknowledgement timeout locks further
mutations and requires reset, so neither graph can be reused with uncertain
ownership. No parsing, filesystem operation or allocation runs in the render loop.

## Storage and recovery scope

IDF 5.5's bundled SPIFFS uses the dedicated 0x310000–0xffffff partition. First use
formats this project partition only if it cannot mount and no provisioning marker
exists. Once provisioned, mount failure never triggers automatic formatting.
NVS namespace `wsynth4` stores provisioning and selected slot; NVS errors never
trigger blanket erasure. Normal application flashing preserves both partitions.

Each slot retains two independently checked generations. Saving replaces the
older/invalid bank, flushes and syncs, closes, then rereads and verifies the whole
record. Only then is selected-slot metadata committed. Repeating an identical
save does not create a new generation. Loading scans both banks and selects the
highest complete, SHA-valid, currently admissible generation. Truncated or corrupt
banks are ignored. Factory bytes remain compiled into the application.

Individual-file interruption/corruption is covered by host tests; hardware tests
cover save/readback/restart and interruption of RAM transfers. Two files on one
SPIFFS partition do not guarantee recovery from every filesystem-wide corruption
or physical brownout. Physical power-cut testing and a release soak remain open.
Factory boot and the original ROM flashing path remain available if storage fails.
The current flashed app is copied to `recovery/m4-current.bin`; its hash is in
`evidence/esp32-ui-build.json`. Upload/play/save, saved-package readback after
physical reconnect and user inspection of the library passed. The initial
interaction overruns were reproduced and resolved for the selected workload by
moving rendering kernels into instruction RAM; see `PERFORMANCE.md`. Historical
observations remain in `evidence/patch-device-powercycle*.json`. Flash backups are
excluded from Git; the original full-board backup and M2 known-working app remain.

During repeated tests, native USB stopped at the bootloader/app handoff and no
longer accepted software reset commands. A closely matching symptom is described
in [Espressif issue 18996](https://github.com/espressif/esp-idf/issues/18996).
That report is for a different IDF version; it supports an investigation lead,
not a confirmed cause for this board. Reconnect power or use the physical reset
button before retrying; ordinary uploads do not require resetting the board.

Record schema `WSP1`/version 1 is defined for the pinned engine commit
`00ac338904304e87845477808e598ef973f49b52` and this upload policy. A future incompatible
engine or package interpretation must change the schema or implement migration.

## Protocol

Native USB Serial/JTAG shares one stream with console logs. Requests and replies
are complete ASCII lines. Ignore non-protocol lines; never treat a log as an ACK.

```text
@SD1 <8 lowercase hex request ID> <UPPERCASE OP> <lowercase hex payload or -> <8 hex CRC32>\n
```

CRC32 is the standard reflected 0xedb88320 polynomial, initial/final XOR 0xffffffff,
over the bytes from the request ID through the payload, excluding the final space
and checksum. Payload integers are little-endian. Request payload maximum is 512
bytes; device replies contain hex-encoded UTF-8 JSON (`OK`) or an error (`ERR`),
with a 4,000-byte text bound. CRC failures use uncorrelated request ID 0.
Metadata strings are nonempty, NUL-padded printable ASCII, excluding quote and
backslash. Full source remains UTF-8.

| Operation | Request payload / result |
| --- | --- |
| HELLO | Empty; model/revision, source build, engine/profile hashes, 44.1 kHz, block 64, voice/effect limits, transport, storage and package limits, policy ID |
| STATUS | Empty; stage, received count, transfer, active slot/name/hash, reset requirement |
| INFO | Empty; active slot and the 160-byte manifest as hex |
| READ | u32 offset + u16 count (1–256); bytes from active graph followed by source |
| LIST | Empty; slot names and valid generation counters |
| BEGIN | 160-byte manifest; validates bounds before receiving |
| DATA | u32 transfer + u32 offset + 1–256 bytes; sequential, identical duplicates accepted |
| COMMIT | u32 transfer; verifies complete data/digests/source/graph/policy, enters ready state |
| ACTIVATE | u32 transfer; explicit acknowledged graph replacement |
| ABORT | Empty; discards staging, preserves active patch |
| SAVE / LOAD | One slot byte; SAVE 1–8, LOAD 0–8 |
| PANIC | Empty; acknowledged stop through maintenance |

Manifest offsets: u32 transfer at 0 (nonzero for upload), u32 graph length at 4,
u32 source length at 8, graph SHA-256 at 12, source SHA-256 at 44, name[32] at 76,
four label[12] fields at 108, mapping byte at 156, three zero bytes at 157.
Mapping 1 describes the included sine controls; mapping 0 displays normalized
percentages. Graph/source are each bounded to 65,536 bytes.

One host request may be outstanding. The last request/reply is cached: retry the
same ID and content after a lost ACK; reusing it with different content is an
error. Do not pipeline requests. DATA also recognizes identical earlier chunks;
gaps/conflicting duplicates fail. Ten seconds without a valid operation expires
receiving/ready staging. A failed commit discards staging. Reconnect with a fresh
ID, HELLO and STATUS after uncertain communication; never assume a timeout means
a mutation failed. Oversized input is discarded through newline, a new `@` starts
resynchronization, and the legacy `!` always requests panic outside valid frames.

Saved record: `WSP1`, u32 schema=1, u32 generation, u32 combined payload length,
160-byte manifest, graph, source, `DONE`, and u32 CRC32 over header plus payload.
Exact file length, trailer, CRC, both SHA values and admission must all pass.
