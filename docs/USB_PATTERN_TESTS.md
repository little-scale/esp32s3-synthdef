# USB pattern lifecycle checks — 13 November 2026

## Completed resumed run

The real SuperCollider extension, isolated Studio bridge and XIAO-3eeb84
(`esp32-1c29043eeb84`) passed **25 lifecycle checkpoints** and the full
**600-second DSP/control soak** at **5% output volume**. SC submitted **9,609
updates** across the prelude and timed run; **9,600 events applied** between the
recorded remote-info boundaries. Lookahead events were canceled when stopping.
No new late/rejected events or audio diagnostic errors occurred in the soak.
[Completed run](../evidence/usb-patterns-xiao-3eeb84-resumed-20261113.json)

The final checks verified that cancellation emptied the queue, held `freq`
unchanged, and left the autonomous audio playing. Original Main/FX packages,
generations, active states and live controls were independently verified after
restoration, with **5% saved** and normal Studio reconnected. The boot ID stayed
unchanged throughout. No firmware was flashed; build remains `b06188c54dbe`.

The earlier user-interrupted run remains archived as incomplete at 149.78
seconds; it has not been relabelled as a completed test.
[Earlier paused run](../evidence/usb-patterns-xiao-3eeb84-20261113.json)

## What passed

| Check | Observation |
| --- | --- |
| Definition upload | Temporary definition remained uninstantiated and silent |
| Explicit creation with gate 0 | Active instance, exactly zero captured PCM |
| 8 notes/second | Scheduled gates and audio captured; stop produced silence |
| Replay of stopped player | Fresh remote stream played successfully |
| 16 notes/second | Gate intervals and cancellation passed |
| Identical pitch at 16 notes/second | 52 acknowledged empty 32-byte note deltas in the capture window; gates still retriggered |
| Overlapping notes | One-block retrigger gaps measured at 64–65 samples |
| Finite pattern | Exactly three notes applied; final release completed |
| Cancel a future note | Pending event removed; capture spanning its due time stayed silent |
| Ownership handoff | Old-note expiry/cancellation did not release the newer 660 Hz note |
| Panic with a future event queued | Queue emptied and capture stayed silent |
| Definition replacement while queued | Old queue invalidated, old pattern stopped, new definition stayed silent |
| Restart after replacement | Fresh pattern played the new definition |
| ESP32 CmdPeriod hook | Registered player canceled and captured output became silent |

The CmdPeriod check directly invokes `ESP32.cmdPeriod` in an isolated sclang
process. It does not send a global stop to the user's IDE or a host audio server.
The fixture does not start scsynth or play sound on the computer.

Measured gate intervals in the short captured windows had maximum errors of
about **2.71 ms at 8 Hz** and **1.55 ms at 16 Hz**, with SC's default 0.25-second
scheduling lead. These are intervals in on-device post-volume PCM, not a
measurement of end-to-end latency, the external DAC clock or long-run jitter.
The gate-period acceptance threshold was 10 ms and missing transitions also fail.

Definition replacement deliberately caused **one SC stale-pattern warning**.
Two old-revision wire requests were rejected: the next note and its cleanup
cancellation. They are retained as expected stale-graph protection, not counted
as transport failures or silently discarded from the evidence. No warning flood
was observed, and the fresh pattern worked after explicit preparation.

## Diagnostic SynthDef and capture method

```supercollider
SynthDef(\UsbGateQA, {
    arg freq=440, amp=0.05, gate=0, attack=0.002, release=0.01;
    var env=EnvGen.kr(Env.asr(attack, 1, release), gate);
    Out.ar(0, [
        SinOsc.ar(freq) * amp * env,
        Select.ar(gate, [DC.ar(0), SinOsc.ar(880, 0, 0.02)])
    ]);
});
```

Left is the played note; right is an AC gate marker. Selecting between zero and
the marker preserves the control-block edge. Ordinary audio-rate multiplication
by a control-rate gate interpolates it, obscuring a one-block retrigger gap.
The first measurement attempt used that smoothed marker and correctly failed
its transition-count assertion; its cleanup restored the original sound.
[Preserved measurement failure](../evidence/usb-patterns-xiao-marker-ramp-attempt-20261113.json)

The decoder ignores short sine/quantisation zero crossings and identifies gate
lows of at least 16 samples. Offline tests cover regular and overlapping notes,
missing/displaced gates, wrong-device/state refusal, and detecting a stalled
control stream or new diagnostic error. Private PCM and native SC logs remain
under `build/host/private/`; the public report contains numeric observations.

## Completed soak and compact notes

The ten-minute soak uses Comb Cloud KR followed by temporary MiVerb, with an
actual `esp32Set` Pbind updating `freq` at **16 Hz**. Repeated pairs of frequencies
exercise unchanged-value deltas. There are **116 monitoring windows** and **20
periodic PCM samples**, with no new write failure, partial write, DMA event, DSP
fault, clipping, nonfinite value, control overflow, late event or rejected event.

Sampled average DSP load was **64.0–66.0%**, with a maximum reporting-window peak
of **102.1%**. This peak is retained; no claim of universal deadline compliance is
made. Internal free memory stayed **81,711 bytes** at both boundaries. Free PSRAM
went from **5,173,752 to 5,173,736 bytes** (16 bytes lower), within the pack's 1 KiB
stability tolerance. This is a ten-minute observation, not a long-term leak proof.

A separate repeated-pitch note phase captured **52 acknowledged note events**
with no argument records: a **32-byte binary body**, versus 52 bytes for the first
full four-argument note. The audio marker still shows 16 retriggers per second.
Counts include neither ASCII framing nor transport headers. The overall run
contains 61 empty-delta notes; the 52-event figure is the specifically measured
capture phase. Repeating controls does not suppress note timestamps or triggers.

The earlier 149.78-second interrupted attempt had sampled average load of
64.6–66.3% and a 103.2% peak, with clean sampled windows. Its completion and final
stop/hold assertions were pending then; both now pass in the resumed run.
The first smoothed-marker measurement failure also remains preserved separately.

Physical AMOLED, Wi-Fi-under-load/multiple-node tests, other hosts/hubs and
longer observations remain follow-ups. There is no new acoustic listening
confirmation for this resumed run; the results above use on-device PCM and
telemetry. The six focused offline guard/analysis tests and the full **118-test**
host/native regression set pass.
[Computer-only checks](../evidence/usb-patterns-resume-host-checks-20261113.json)

## Reproduction

`host/qualify_usb_patterns.py` requires a fresh private Studio backup matching
the exact module and saved Main/FX state, with original FX bypass. It refuses a
wrong device, changed saved state or output above the 5% test cap before mutation.
It compiles the fixtures first, borrows USB from normal Studio, and starts an
isolated authenticated loopback bridge using the same production classes.
All test uploads use temporary ACTIVATE; INSTALL/SAVE are never used.

```sh
PYTHONPATH=host python3 host/qualify_usb_patterns.py \
  --device-id esp32-1c29043eeb84 \
  --backup build/host/private/usb-patterns-resume-20261113-backup.json \
  --soak-seconds 600 \
  --output evidence/usb-patterns-xiao.json
```

Do not reuse a stale backup. Ctrl-C stops the native client/monitor, drains the
isolated bridge, panics pending events, restores and verifies original packages
and controls, saves 5%, and reattaches normal Studio. Physical loss of USB can
prevent restoration and is reported explicitly; the earlier paused session completed cleanup before the user unplugged, and
the resumed session also verified restoration.

```sh
PYTHONPATH=host python3 -m unittest test_qualify_usb_patterns
```
