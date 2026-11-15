# Codec and first-audio commissioning — 14 November 2026

The isolated Voice PE application now initializes the codec muted and supports
one explicitly requested speaker test. It is not yet the production Main/FX
application or a Studio installation target. The original ESP backups and
[tested stock recovery](../../recovery/voice-pe/README.md) remain available.

## Configuration and evidence

Configuration follows the board's [pinned ESPHome AIC3204 implementation](https://github.com/esphome/esphome/blob/fc106564ed1fd2e1047428878b0333baf1cbcd29/esphome/components/aic3204/aic3204.cpp),
with mute retained instead of its final unmute. Register fields were checked in
the [TI application reference, SLAA557](https://www.ti.com/lit/ml/slaa557/slaa557.pdf),
particularly pages 96, 104, 110–111 and 126–127.

- All register transactions use the codec device at `0x18`. The adapter has no
  XMOS device handle, reset operation or firmware-update implementation.
- The amplifier remains low during initialization. Digital DAC mute is
  `P0/R64 = 0x0c`; headphone gain/mute registers are `P1/R16–17 = 0x7e` and
  line gain/mute registers `P1/R18–19 = 0x40`.
- Codec reset is followed by NDAC=2, MDAC=2, DOSR=128, stereo 32-bit I²S and the
  board's alternate **SCLK/MFP3 data-input** selection. Nominal MCLK is
  24.576 MHz according to the reference configuration; MCLK was not measured
  in this test and GPIO9 is not driven.
- The reference analog-power/common-mode/output sequence is followed with
  output mute retained, including its 2.5-second soft-start interval. Both DAC
  channels and all four output drivers must report powered (`P0/R37 & 0xee`).
  Missing readiness expires after a bounded poll; initialization never unmutes.
- DAC digital gain is fixed at **−24 dB** (`P0/R65–66 = 0xd0`) for this bench
  test. Unmute requires this gain and all mute readbacks to match first.
- On the connected unit, 28 register checks passed and power flags were `0xee`.
  Mute passed again after the zero-stream DMA test and after physical cold boot.
  These are configuration/status checks, not a unique silicon-ID query.

[Machine-readable results](../../evidence/voice-pe-codec-20261114.json) separate
host fault-model tests, actual device results and the user's listening report.

## Output routing

The [official DAC schematic](https://github.com/esphome/home-assistant-voice-pe/blob/d4e6fa43d6a1a7d342b7d4d403567e06516719de/hardware/KiCad/DAC.kicad_sch)
shows LOL through R100/C20/R20 and LOR through R99/C19/R21 joining the mono
speaker amplifier's inverting input. Its other input is AC-referenced through
R22/C21. This route was checked against the rendered DAC sheet and the cached
net extraction. HPL/HPR separately feed the jack through C16/C15.

Keep left/right separate in software: the internal speaker performs an analog
sum. Hearing the speaker sequence does not qualify stereo separation at the
jack. Analog output levels, noise/distortion and acoustic loudness have not
been measured.

## Explicit bench commands

The application installs the buffered native USB console. It stays muted at
boot, runs only zero DMA automatically, then accepts these newline-terminated
commissioning commands:

```text
VPE_STATUS
VPE_TONE <eight-lowercase-hex-token>
```

`VPE_STATUS` prints `TONE_READY` with the current token and readiness, mute,
amplifier and jack state. A tone requires an exact command with that token.
The token changes on boot, on each accepted attempt and on an idle panic. It
prevents accidental/replayed bench requests; it is not network authentication.
Bare `t`, stale tokens, partial/overlong commands and ordinary Studio traffic
do not select the tone path. Another accepted attempt has a five-second cooldown.

The test refuses an inserted jack and requires the ready/muted state. It
preloads the full DMA ring with zeros, starts a zero stream, unmutes the codec,
then enables the internal amplifier. After a settling interval it plays:

1. One second of left-channel 440 Hz.
2. A short silent gap, then one second of right-channel 660 Hz.
3. Another gap, then one second of 550 Hz on both channels.

Each note has 50 ms ramps and a PCM peak of 1,638/32,768 (approximately 5%,
−26 dBFS). The codec adds −24 dB gain. The complete stream, including zero
lead-in/tail, is about 3.6 seconds. There is no automatic repeat or boot playback.

Pressing the center button, inserting a jack, or sending `!` aborts the active
test. Cleanup first sets amplifier enable low, then attempts/verifies digital
and analog mute, disables/deletes DMA and leaves data low. All writes have
100 ms timeouts; the submission loop also has a five-second budget. I²C cleanup
transactions have separate bounded timeouts. Normal input logging pauses during
this blocking bench test; dedicated abort checks continue at block boundaries.

The first sequence completed 2,700 writes without a partial write or timeout,
restored verified mute/amplifier-off, and the user confirmed **clean sound that
stopped**. No louder test was sent. A further USB abort was tested during the
zero lead-in, before amplifier enable; physical-button and audible-midstream
abort listening checks remain pending.

## Tests and remaining qualification

```sh
python3 host/test_voice_pe_codec.py
```

Sanitized host tests cover every one of 140 initialization I/O failure positions,
21 corrupt readbacks, absent power readiness, stuck reset, 34 unmute I/O failure
positions, the fixed-gain guard and reinitialization. The tone test covers all
frames, peak/ramp bounds, channel isolation, S32 packing, deterministic restart,
expected cycle counts and exact command matching.

Actual hardware checks include register/power/mute readbacks, normal zero DMA,
one low-level listening sequence, stale-command rejection, pre-amplifier USB
abort and silent physical cold boot. They do not qualify clock-loss or I²C
electrical fault recovery, headphone output, microphone capture, full DSP load,
or production SC/Studio/transport/Main/FX behavior.


## Shared playback gain (15 November 2026)

The historical bench sequence above remains fixed at −24 dB. The shared
application now explicitly initializes the same routing at **0 dB DAC gain**
(P0/R65–66 = 0), and the general playback unmute validates those exact readbacks.
Only −24 and 0 dB profiles are supported. The bench unmute wrapper rejects the
0 dB profile; unsupported profiles and mismatched gain registers fail muted.
Both profiles pass the full portable initialization/unmute fault suite.

Before enabling audio on the first unity-gain boot, the application clamps the
saved software volume to at most 5% and records `wsynthfx/vpe_unity`. On later
boots, acknowledged unity-gain firmware retains normal user volume choices.
This accommodates existing saved 100% settings without a sudden +24 dB change.
The shared engine’s 0.8 master gain is unchanged. The output remains stereo S16
in S32 I²S slots at 48 kHz; gain transactions stay off the audio task.


The shared update was installed through Studio on VoicePE-0697d4. Both gain
registers passed initialization/readback checks, HELLO reports 0 dB, and the saved
sound block was unchanged. The user confirmed stronger, clean output at the new
profile. A physical power cycle then retained their selected 10% rather than
reapplying the initial 5% clamp. See
[15 November gain evidence](../../evidence/voice-pe-unity-gain-20261115.json).
