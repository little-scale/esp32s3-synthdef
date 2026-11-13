# USB pattern lifecycle checks — 13 November 2026

## Result and pause point

The real SuperCollider extension, isolated Studio bridge and XIAO-3eeb84
(`esp32-1c29043eeb84`) passed **23 lifecycle checkpoints** at **5% output volume**.
The subsequent ten-minute DSP/control soak was **paused at the user's request**:
29 monitoring windows reached **149.78 seconds**, with no new errors observed in
those windows. This is **not a completed 600-second soak**. Hardware work is
paused until the board is available again.

The original Main/FX packages, storage generations, active states and live
controls were verified after cleanup, with **5% volume saved** and normal Studio
reconnected. No test graph was saved, no storage was erased, and this pack did
not flash firmware. The installed USB-qualified build remains `b06188c54dbe`.
[Interrupted run and restoration](../evidence/usb-patterns-xiao-3eeb84-20261113.json)

## What passed

| Check | Observation |
| --- | --- |
| Definition upload | Temporary definition remained uninstantiated and silent |
| Explicit creation with gate 0 | Active instance, exactly zero captured PCM |
| 8 notes/second | Scheduled gates and audio captured; stop produced silence |
| Replay of stopped player | Fresh remote stream played successfully |
| 16 notes/second | Gate intervals and cancellation passed |
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
about **1.26 ms at 8 Hz** and **1.55 ms at 16 Hz**, with SC's default 0.25-second
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

## Partial soak

The soak uses Comb Cloud KR followed by temporary MiVerb, with an actual
`esp32Set` Pbind updating `freq` at **16 Hz**. Repeated pairs of frequencies also
exercise unchanged-value delta packets. Controls and audio are observed every
five seconds; PCM is sampled periodically while the pattern keeps running.

The sampled average DSP load ranged **64.6–66.3%**. The maximum recorded reporting
window peak was **103.2%**; it is preserved rather than hidden. No additional
write failures, partial writes, DMA events, DSP faults, clipping, nonfinite
values, late events or rejected events were observed in the completed monitoring
windows. A peak over the per-block budget is not itself proof of a dropped sample,
and this partial run is not a long-term real-time guarantee.

**Still pending:** finish 600 seconds, execute the soak's final frequency-hold and
continuous-audio-after-cancel assertions, and qualify repeated identical-pitch
*note* events carrying empty deltas. The latter was not exercised by the pitched
note sequence in this pack. Physical AMOLED and Wi-Fi pattern testing are also
separate follow-ups.

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
  --backup build/host/private/usb-patterns-20261113-backup.json \
  --soak-seconds 600 \
  --output evidence/usb-patterns-xiao.json
```

Do not reuse a stale backup. Ctrl-C stops the native client/monitor, drains the
isolated bridge, panics pending events, restores and verifies original packages
and controls, saves 5%, and reattaches normal Studio. Physical loss of USB can
prevent restoration and is reported explicitly; this session completed cleanup
before the user unplugged.

```sh
PYTHONPATH=host python3 -m unittest test_qualify_usb_patterns
```
