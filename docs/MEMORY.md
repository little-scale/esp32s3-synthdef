# Initial memory budget

These structure sizes were produced by Xtensa GCC 14.2.0, with the pinned engine,
and recorded by `host/record_build.py`. They are compile-time sizes, not free-heap
measurements. The app logs actual allocations/free memory after boot.

| Allocation | Bytes | Placement / lifetime |
| --- | ---: | --- |
| Two graph buffers | 27,240 | Internal; inactive parser buffer becomes active only after acknowledgement |
| One voice | 35,744 | Internal RAM, audio owner |
| One shared scratch | 49,152 | Internal RAM, audio owner |
| Engine fixed total | 112,136 | Excludes stacks, queues and peripheral state |
| Engine arena | 0 | Gated sine does not require one |
| Audio task stack | 16,384 | Internal; verify stack high-water mark on target |
| Console/patch service task stack | 16,384 | Internal; allocated once |
| Package buffers | 3 × 131,072 | PSRAM; active, staged and file verification |
| LVGL fixed heap | 65,536 | Internal BSS; expanded library, no theme transitions |
| Selected rendering kernel bodies | 29,614 plus literals/alignment | Internal instruction RAM via linker fragment; immutable tables stay in flash |
| Audio adapter hot bodies | 1,470 plus literals/alignment | Internal instruction RAM |
| Diagnostic results | 13,440 | Preallocated PSRAM; historical benchmark results |
| Diagnostic waveforms | 107,520 | Preallocated PSRAM; 280 cases, three mono blocks each |
| Mono PCM block | 128 | Audio task stack |
| Temporary stereo mix | 512 | Audio task stack |
| Pending event batch | (16 + 6) × sizeof(inst_event) | Audio task stack |
| Event queue | 16 events plus RTOS metadata | Allocated at startup |
| Telemetry queue | One snapshot plus RTOS metadata | Allocated at startup |
| I2S DMA payload | Six × 128 frames, physical size driver-dependent | IDF internal DMA-capable storage |

The host voice is 35,752 bytes because of pointer layout/alignment differences;
do not substitute it for the target size.
PSRAM is enabled and reported, but the first graph/voice/scratch stay internal.
DMA and codec resources are allocated at startup; steady-state synthesis and
conversion allocate no heap. Note starts clear/reprepare fixed state and are timed
separately. Upload staging is preallocated; delay/effect arenas remain disabled.

The touchscreen variant adds a single 368 × 20 RGB565 draw buffer (14,720 bytes)
in internal DMA-capable memory and a 10,240-byte LVGL task stack. A diagnostic
screen snapshot temporarily uses 329,728 bytes of PSRAM, after stopping notes.
The recorded 30-second UI/redraw run had 178,371 bytes minimum internal free
heap, a 73,728-byte largest free block and 13,632 bytes of audio stack margin.
These are workload-specific observations, not admission limits for future patches.
The timing fix moves admitted kernels into instruction RAM. Its diagnostic
exercise retained at least 75,915 bytes internal free, with a 31,744-byte largest
free block. The original matrix capture used 32,256 bytes of PSRAM per patch.
The expanded matrix uses the allocations above; moving results out of internal
BSS also frees the earlier 3,696-byte result array. See `PERFORMANCE.md` and final
runtime reports for scope.

The partition map reserves 3 MiB for a factory application and the remaining
12.94 MiB for SPIFFS patch storage, after NVS/PHY data. Flash writes occur only
after the audio owner parks and DMA stops. No OTA layout is claimed.
`evidence/esp32-ui-build.json` records current image and configuration hashes.
The 178,371-byte UI free-heap observation above predates M4's staging and larger
LVGL heap; use the M4 runtime evidence for the current workload's margins.

## Proposed smaller capacity profile (not selected)

A target-compiler size probe with 24 nodes, 32 signals and 256 input references
produced graph/voice/scratch sizes of 8,076 / 6,720 / 8,192 bytes. Two graphs plus
one voice and scratch would use 31,064 bytes, saving **81,072 internal bytes**
against the current 112,136. Constants, controls and partial capacities were left
unchanged. See `evidence/proposed-capacity-sizes.json`.

This is a size calculation only. The selected firmware and vendored header keep
their original capacities. A future implementation must compile parser, renderer
and adapters against one consistent target ABI, check stored-patch compatibility,
and repeat numerical and timing checks before selecting that profile.
