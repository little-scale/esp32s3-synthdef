# Combined DSP qualification — 12 November 2026

The selective smoothing, partial-bank and delay/MiVerb binding build completed
the same-board numerical/performance comparison on **XIAO-3eeb84**
(`esp32-1c29043eeb84`). This is a selected-case qualification of the shared DSP,
not a full hardware sweep or physical AMOLED qualification.

## Controlled comparison

Both applications were cross-built from the current TDelay-capable source,
with all seven experimental switches off. Only `SYNTHDEF_QUALIFIED_KERNELS`
changed between the legacy and selected builds. Main output was saved at mute
before flashing. Application writes were verified; patch storage was preserved.

Twenty-eight precompiled graphs ran three times on each image. Each fixed-seed
trial used seed 12345, 128 warm-up blocks and 1,024 measured blocks at 44.1 kHz,
64 frames and the reported 240 MHz CPU clock. All 168 normal/instrumented pairs
matched their audio, voice-state, scratch and arena checks within each image.
The host also required matching graph bytes, warm-up/measured audio SHA-256 and
final RNG words across trials and images. The cross-image check does not compare
normalized whole-voice state; the offline suite provides that separate evidence.

These times measure the normal DSP renderer. Per-node attribution comes from a
separate instrumented pass and is not used as the whole-graph speed measurement.
PCM conversion, USB reporting, allocation and flash operations are outside the
timing interval. Figures are specific to the recorded fixtures and this module.

| Musical graph | Legacy µs/block | Selected µs/block | Less DSP time |
| --- | ---: | ---: | ---: |
| Eight-Saw / Resonz / MiVerb | 1,176.89 | 1,159.12 | 1.51% |
| Comb Cloud KR | 410.85 | 384.45 | 6.42% |
| Triggered harmonics | 310.60 | 311.06 | −0.15% |
| Eight-filter bank | 277.73 | 277.99 | −0.09% |

The six eight-UGen smoothing graphs use **52.60–62.51% less DSP time**. The
16-partial Klang and Klank graphs improve by **29.24% and 25.48%**. The nine delay
graphs improve by **6.88–8.12%**, and modulated MiVerb improves by **2.91%**.

Negative results are retained. The unchanged isolated SinOscFB graph increases
from 31.44 to 32.62 µs (**3.75% slower**), and Formant from 36.12 to 38.14 µs
(**5.61% slower**). Their three trials are consistent, so these are not labelled
noise. The selected update does not change their oscillator arithmetic; the
dispatch/code-placement contribution has not been isolated. Blip is 0.49%
slower; Gendy changes are small. No universal or additive speed-up is claimed.

[Raw baseline](../evidence/dsp-combined-xiao-3eeb84-baseline.json),
[selected image](../evidence/dsp-combined-xiao-3eeb84-qualified.json),
[comparison](../evidence/dsp-combined-xiao-3eeb84-summary.json),
[build audits and image identities](../evidence/dsp-combined-xiao-3eeb84-builds.json).
The two modes share a source-derived build ID; their application hashes and
effective `qualified=0/1` profiler tags distinguish the actual images.

## TDelay hardware follow-up

Six XIAO stereo PCM cases verify `TDelay.ar/kr`: minimum/zero delay, five-tick
delay and ignored triggers while a longer delay is pending. The trigger is
captured on the left channel and the output on the right, at 50% main volume.
**100,588 captured frames** match the countdown oracle after synchronizing to an
observed output pulse. Control pulses are checked as complete 64-frame plateaus.
This synchronization handles the unknown pending state at capture start; merely
discarding one delay interval does not synchronize periodic ignored triggers.

These are selected physical timing checks. They do not replace the fuller
offline constructor/rate/layout/sanitizer tests, establish isolated TDelay CPU
cost, or qualify an analogue audio path.
[Hardware captures](../evidence/tdelay-xiao-3eeb84.json),
[offline tests](../evidence/tdelay-host.json).

## Main/FX, telemetry and connection follow-up

The first one-minute Comb Cloud → MiVerb/control/capture attempt observed 16
additional DMA queue events and was recorded as **failed**, with no DSP fault,
clipping, nonfinite value, write failure, partial write or control overflow.
Its initial telemetry boundary could include delayed setup reports.

A separate 15-second Main/FX run waited for fresh telemetry after activation,
then ran without control or capture traffic. DMA events rose from 21 to 35
during setup and remained at 35 throughout settled playback. All measured fault
deltas were zero and free memory was stable. This distinguishes observed setup
events from that playback interval; it does not certify the longer live-control
case. Setup DMA events remain visible rather than being removed from counters.

USB stopped responding before the longer settled rerun could identify the
module. A non-erasing software reset did not recover the link. That attempt is
**incomplete**, not a passing soak. The user reconnected the XIAO; a later run was
interrupted to lower listening volume as requested, and another reconnect was
needed. The recovered final check used one connection for its soak and listening
sequence. These connection failures remain part of the session record.

The final **30.11-second Main/FX run at 5% volume** sent **199 live controls**,
periodically captured PCM, and observed zero new DSP faults, clips, nonfinite
values, write failures, partial writes, DMA queue events or control overflows.
Free internal RAM remained **92,387 bytes** and free PSRAM **5,172,972 bytes**
at both measurement boundaries. This is a short stability observation, not a
long-run leak proof, and does not relabel the initial failed attempt as passing.

The subsequent eight-saw, Comb Cloud, triggered-harmonics and separate-MiVerb
listening sequence also used **5%**. Captures show a nonzero reverb tail after
stopping Main and exact PCM silence after Panic. Digital assertions pass. On 12 November the user also confirmed the sequence
sounded **clean, including the tail**, at 5%. This listening confirmation applies
to these musical examples and the attached output, not every UGen/input case.

The original Main bytes, unchanged Main/FX generations, instance states and live
controls were restored. The empty saved FX slot remains empty. The user's final
requested **5% volume is saved**, superseding the original backed-up 20% setting.
Studio reconnected and independently verified saved lists, Main control values
and live 5% volume. The new selective headless application remains installed.

[Initial attempt](../evidence/dsp-combined-xiao-3eeb84-soak.json),
[settled short playback](../evidence/dsp-combined-xiao-3eeb84-soak-idle.json),
[interrupted rerun](../evidence/dsp-combined-xiao-3eeb84-soak-settled.json),
[completed control/listening/restoration checks](../evidence/dsp-combined-xiao-3eeb84-final.json).

## Reproduction and remaining work

`host/qualify_dsp_transient.py` keeps one USB connection for each phase and uses
`COMMIT`/`ACTIVATE` without saving test Main/FX packages. This permits a test FX
without populating the user's empty stored FX slot. It requires an exact private
Studio snapshot and original FX bypass, checks module identity before mutations,
verifies stored packages/generations on restoration, and caps all further output settings
at 5%, following the user’s revised limit. Profiling is muted. Four offline safeguard tests cover the volume cap,
wrong-device refusal, unchanged storage and restoration failures.

The broader 324-graph hardware sweep, long soak, cross-image normalized state
replay, physical AMOLED checks, and isolation of the small oscillator slowdowns
remain separate work. See the [original qualification plan](QUALIFIED_DSP_UPDATE.md).
