# SuperCollider → ESP32

The extension adds `Function.sendESP32` and `String.sendESP32`, named parameter
updates, and pattern routing through the existing local Studio service. The
browser does not need to stay open. Saved Main/FX continue running without the
computer; live patterns require SuperCollider and Studio.

Studio's connected USB device can also be targeted by permanent ID, displayed name or alias;
Wi-Fi pairing is not required for USB. Both transports use the same deployment,
instance, named-control and pattern API. The USB connection is shared with
Studio's reader and serialized per transaction. See the [XIAO headless guide](HEADLESS.md)
for stereo output, physical input buses and capture without a DAC.

## Install and start

```sh
sh host/studio.sh
python3 host/install_supercollider.py
```

The installer links `supercollider/` into the user's SC Extensions directory and
links the private connection descriptor. Existing unrelated installations are
never overwritten. In an already open SuperCollider IDE, choose **Language →
Recompile Class Library** once. The connection descriptor contains a private
loopback token, is mode 0600, and is not committed. `ESP32.configPath` can select
a different descriptor before connecting.

```supercollider
ESP32.connect;
ESP32.scan.onDone(_.postln);
ESP32.alias(\amoled, "esp32-2884853ad390");
```

Alias registrations persist on this computer. A target may be a permanent ID
String, a unique paired module name, an alias Symbol, a saved/discovered IPv4
address, a list of targets, or `\all`. `\all` is reserved. IP use still verifies
the paired identity; names shared by multiple modules need an alias or ID.

For example, the displayed name `AMOLED-8d507c` can be used directly:

```supercollider
ESP32.set("AMOLED-8d507c", \freq, 330);
ESP32.module("AMOLED-8d507c", \volume, 0.2);
```

That module's permanent ID is `esp32-2884858d507c`; it stays unchanged if its
display name is edited. An unplugged USB module needs paired, online Wi-Fi to
remain reachable. The same target forms work in a pattern's `\module` key.

## Module settings

Use `ESP32.module(target, \volume, level)` for the module's global output scale:

```supercollider
ESP32.module("esp32-2884853ad390", \volume, 0.5); // 50%, this module.
ESP32.module(\all, \volume, 0.5);                 // 50%, all paired online modules.
ESP32.module(\amoled, \volume, 0);               // Mute; does not stop Main/FX.
ESP32.module(\amoled, \volume, 1);               // 100%.
```

Levels are linear, from 0 to 1, rounded to the slider's nearest 1%. This uses
the same smoothed output gain and updates the Controls slider without reloading
either patch. It applies after Main and FX and is independent of their arguments
(including any SynthDef argument named `volume`). These live changes do not save
to flash; releasing the physical slider saves its current value as before.
No firmware update is needed on boards with the existing global-volume support.

Targets also accept aliases and explicit lists. Calls return `ESP32Job`, with a
`verified` result and a `results` list containing each device ID, confirmed
`volume` (0–1), `percent` (0–100), or an error. A failed recipient does not undo
successful recipients. Commands from one SC connection retain send order;
all-module changes are concurrent deliveries, not sample-synchronized changes.
Only `volume` is currently accepted as a module setting; invalid values fail
before sending to any module. The one-argument `ESP32.module(target)` form still
returns the existing Main/FX handle.

## Connection failures and patch changes

If Studio restarts or its TCP connection fails, the affected SC patterns stop
and pending jobs fail. Cleanup does not reconnect to send an old cancellation,
and failed sends cannot escape into the pattern scheduler as cascading primitive
or `PauseStream` errors. A low-level socket diagnostic may still be printed once.
The client ignores late close callbacks from older connections. After restarting
Studio, use `ESP32.connect` and explicitly restart the desired patterns; events
that may already have been delivered are not automatically replayed.

`Patch changed; restart the pattern` is a deliberate revision check. Stop a
pattern before replacing/recreating its Main or FX definition, wait for the
upload/creation job to finish, then start the matching pattern again. This keeps
old control indices from being applied to a different graph. Parameter arguments
are name/value pairs, e.g. `ESP32.set(target, \slide, 5)` with both commas.

After updating the extension, **Language → Recompile Class Library** loads the
fix; doing so resets language-side patterns, which must then be restarted.

A retained `ESP32Player` can have a non-nil stream after a clock/stop-era reset,
while `wasStopped` is true and no events are scheduled. In that state an older
`playESP32` returned the existing player without restarting it, so uploading
worked but the pattern was silent. The extension now clears that stale state,
resets the stream and assigns a new remote stream ID before replay. Repeated
play calls on an actually running player still reuse it without doubling notes.
Before loading this fix, `p.stop; p = Pbindef(\yourPattern).playESP32;` recovers
the retained player. This is a host-side fix shared by AMOLED and headless XIAO;
no firmware update is required.

## Compact control messages

Unchanged float32 control values are omitted automatically from SC pattern and
`.set` traffic to firmware advertising `control_deltas: 1`. Your existing SC
code is unchanged. The first event for each node/stream/stage sends the full
argument list; later events send only changed values. A changed argument list,
new stream, new patch/reboot or a gap of eight seconds sends a full packet again.
Older firmware continues receiving the original complete packets.

Every note still sends its timestamp, duration, sequence and retrigger command,
even if pitch and all other arguments repeat. The node reconstructs and queues
a complete event snapshot from that stream's baseline. Other patterns, direct
sets, touch controls or future events cannot change the already queued note's
intended arguments. Fields removed from a Pbindef stop being reapplied; trigger
controls still get applied on each event. Baselines are separate for Main/FX
and for each recipient, so Pseq/Prand module routing and `\all` remain safe.

Only an acknowledged packet advances the host baseline. An explicit
`need_full` reply means the device did not enqueue the event, allowing one full
resend with the same timestamp/sequence. Unknown acknowledgements/timeouts are
not retried. The device uses a fixed extra 17 KiB of PSRAM for 32 streams' Main/FX
baselines; it expands packets in bounded time before placing them in the existing
16-event queue, with no allocation in the audio task.

For four arguments (`freq`, `amp`, `curve`, `attack`), an event is initially 52
binary bytes. With only pitch changing it becomes 37 bytes (29% smaller); with
all values unchanged it becomes 32 bytes. The existing ASCII request body falls
from 136 to 106 bytes for pitch changes (22% smaller). These figures exclude
HTTP/TCP/Wi-Fi overhead: request frequency and transport headers are unchanged.
SC-to-Studio loopback messages and compiled SynthDef uploads are unchanged.

## Send Functions and selected code

SC `.sendESP32` now uploads and saves a definition without starting it. It replaces
that stage's previous definition and stops its old instance. This applies to
Functions, literal SynthDefs, source Strings and the SC selected-code helper.
The browser uploader retains its existing explicit upload/play workflow.
Older device firmware is rejected before transfer rather than playing implicitly.

After the saved-and-verified reply, instantiate Main explicitly:

```supercollider
ESP32.play(\amoled, [\freq, 440, \gate, 1]);
ESP32.stop(\amoled);
```

Creation arguments are applied before UGen constructors and may include initial-
rate controls. They are temporary: each explicit play begins with the definition's
saved defaults, applies that call's arguments, and creates fresh DSP state. In
contrast, `args:` supplied to `.sendESP32` edits the saved default table.
A newly uploaded definition also remains uninstantiated after reboot. Existing
legacy saved packages retain their old startup behaviour.

For upload-and-play in one call, use `Function.playESP32(target, args:)` or
`SynthDef.playESP32(target, args:)`. Both return a job that completes after creation.

**Function `.playESP32` saves an autonomous block.** It starts on upload and
again after power-up, independently of SC or touch. Its `args:` are saved as
initial defaults too. A Main Function receives the reserved scalar autoplay
marker; an FX Function is saved as an active processor. Upload activation creates
the instance once, without an additional restart. Later `.set` values remain
runtime changes. The SC IDE needs **Language → Recompile Class Library** once
after installing this extension update.

| Call | Plays now | Plays after power-up |
| --- | --- | --- |
| `Function.playESP32(...)` | Yes | Yes, using saved initial defaults |
| `Function.sendESP32(...)` | No | No; saved definition |
| `SynthDef.playESP32(...)` | Yes | No; saved definition, runtime instance |
| `SynthDef.sendESP32(...)` | No | No; saved definition |

Calling `ESP32.play` on an existing saved definition creates a runtime instance;
it does not convert its boot policy. Existing packages are not automatically
rewritten by updating the extension: resend a Function with `.playESP32` to make
it autonomous. Browser Function uploads already use autonomous mode.

A `\esp32Note` event can create Main on its first note and then reuse the one
persistent voice; this is still not a polyphonic scsynth server.

Literal SynthDefs keep their authored outputs and compiled graph:

```supercollider
(
d = SynthDef(\tone, { arg freq=440, amp=0.1, gate=1;
    Out.ar(0, (SinOsc.ar(freq) * amp * EnvGen.kr(Env.asr, gate)) ! 2);
});
d.sendESP32(\amoled); // Upload only, even though gate defaults to 1.
)
// After verification:
ESP32.play(\amoled, [\freq, 330]);
ESP32.stop(\amoled);
```

The graph is not rebuilt or wrapped, and is byte-identical unless saved-default
`args:` are explicitly supplied. The default display source wraps the original
Function body with the definition's name; supply `source:` to preserve the exact
outer declaration, including external rates/metadata. Binary/source correspondence
is not independently recompiled. Main hardware output and the FX input use bus 0.


```supercollider
(
{
    arg freq=440, dev=20;
    MiVerb.ar(
        Resonz.ar(
            Splay.ar(Saw.ar(freq + {Lag.kr(LFNoise2.kr(1,dev),1)}!2,0.1)),
            SinOsc.kr(0.1).range(110,1720),0.1,4
        ),0.99,1,0.01
    );
}.sendESP32(\amoled, args:[\freq,440.0]);
)
```

Use `.sendESP32(\all)` for the paired online fleet, or
`.sendESP32([\left,\right])` for an explicit group. The Function is compiled in
the current language session, without playing on the computer. Studio validates
one compiled graph, applies supplied initial arguments to its SCgf default table,
then sends the same final graph/source bytes to every recipient. Readback verifies
each saved package. The original Function body is retained for the display.
Closed Functions supply their original source; open Functions need an explicit
`source:` String, or the selected-text workflow. No source is reconstructed from
the compiled graph. An explicitly attached source is not independently recompiled
to prove correspondence to a supplied binary.

```supercollider
ESP32.gui; // Small module/Main/FX picker with a Send selected code button.
// Select a complete { ... }.play block or SynthDef in the IDE, then click Send.
ESP32.sendSelection(\amoled); // Also available for an editor shortcut binding.
"{ SinOsc.ar(220,0,0.05)!2 }.play".sendESP32(\amoled);
```

Selected text/source Strings use the existing host compiler; trailing `.play` is
accepted without host playback. Initial arguments are applied before preparation
and saved in the graph, so they survive reboot. Live `.set` values are temporary.
Reserved `__esp32_` controls cannot be changed.

Uploads return an asynchronous `ESP32Job`. Successful deployments post results;
`job.onDone(...)`, `job.onError(...)` and `job.result` expose completion/reporting.
Use `.wait` inside a Routine when the next action depends on deployment:

```supercollider
Routine({
    {arg freq=220; SinOsc.ar(freq,0,0.05)!2}.sendESP32(\amoled).wait;
    ESP32.play(\amoled,[\freq,330.0]).wait;
}).play;
```

## Named controls and FX

```supercollider
ESP32.set(\amoled, \freq,440.0, \dev,10.0);
ESP32.module(\amoled).main.set(\freq,660.0);
ESP32.module(\amoled).main.setn(\frequencies,[220,330,440]);
ESP32.module(\amoled).main.info.onDone(_.postln);
ESP32.module(\amoled).main.restart;
ESP32.module(\amoled).main.panic;

{arg wet=0.3;
    var input=In.ar(0,2);
    FreeVerb2.ar(input[0],input[1],wet,0.8,0.4);
}.sendESP32(\amoled,stage:\fx);
// After the FX upload reports verified:
ESP32.module(\amoled).fx.play([\wet,0.5]);
ESP32.module(\amoled).fx.set(\wet,0.6);
ESP32.module(\amoled).fx.bypass(true);
ESP32.module(\amoled).fx.bypass(false);
```

Parameters use their authored units and finite float32 values, not the legacy
normalized knob ranges. Unknown names, duplicate/overlapping indices and wrong
array lengths are rejected before a transaction is sent. A batch applies together
at an audio boundary. Live Control/LagControl values and TrigControl pulses are
supported. Initial-rate values are accepted in creation arguments or saved deployment `args:`, not live `.set`. There are at
most 64 scalar control entries, including internal controls and array elements.

FX controls address the active processor. Enable FX before automating it: while
bypassed, the active processor is the protected transparent graph with no FX
parameters. Reload/restart and maintenance can reset live state; put required
boot values in deployment `args:`. Hardware `In.kr` buses retain their existing
separate meaning.

## Pseq / Prand endpoint patterns

```supercollider
(
p=Pbind(
    \type,\esp32Set,
    \module,Pseq([\left,\right],inf),
    \freq,Pseq([220,330,440,660],inf),
    \dev,Prand([2.0,5.0,10.0,20.0],inf),
    \dur,0.5
).playESP32;
)
p.stop;
```

Module values can be IDs, alias Symbols, addresses, lists or `\all`:

```supercollider
\module, Prand([\left, "esp32-2884853ad390", \all], inf)
```

`\esp32Set` updates named parameters without gating or restarting Main. Each
module continues its previous sound when the next event addresses another module.
For FX automation, add `\stage,\fx`. Use a `\params` Dictionary for argument names
that collide with pattern bookkeeping keys.

`\esp32Note` derives `freq`/`amp` using normal Event pitch/amplitude conventions,
and schedules a gate plus a device-owned release from sustain/legato. It needs a
live scalar `gate` on Main. A persistent ASR envelope without freeing Main is the
efficient default; patches that free themselves must rebuild on the next note.
Pass the named `gate` explicitly into `EnvGen.kr(envelope, gate)`. Declaring a
gate argument alone leaves EnvGen's default constant gate unchanged. Adjacent
and overlapping notes preserve a low block before raising the gate again, so
the persistent envelope sees each retrigger (one 64-frame block is about 1.45 ms).
Trigger-only patches can use `\esp32Set` with a trigger parameter.

```supercollider
(
Routine({
    {arg freq=440,amp=0.1,gate=0;
        (SinOsc.ar(freq)*amp*EnvGen.kr(Env.asr(0.01,1,0.1),gate))!2;
    }.sendESP32(\amoled).wait;
    p=Pbind(
        \type,\esp32Note,\module,Prand([\amoled],inf),
        \midinote,Pseq([60,64,67,72],inf),\amp,0.12,\dur,0.25,\legato,0.8
    ).playESP32;
}).play;
)
p.stop;
```

Use **`.playESP32`**, which installs a dedicated EventStreamPlayer and cleanup.
Plain `.play` is rejected for these event types. Stop/CmdPeriod cancels future
queued events and releases only notes owned by that pattern. Replay receives a
fresh stream ID. A previous note's release cannot cut a newer note. Natural pattern
completion lets its last note finish its scheduled sustain. `\all` membership is
frozen on first use in that pattern; release/cancel follows actual recipients.
Each module has one Main voice; this is not automatic scsynth polyphony or a
transparent Server/Pmono replacement. Patch changes invalidate older bindings;
restart a pattern after replacing its code.

The Studio reply listener stays connected across Cmd–Period, so you can stop and
start another pattern, scan modules or send controls without reconnecting. Pending
request deadlines also survive the clock reset. If using an older extension that
reports request timeouts after Cmd–Period, recompile the class library once to
load this fix; device firmware is unchanged.

Named `Pdef`/`Pbindef` patterns keep their ESP32 player: repeated `.playESP32`
calls reuse it, and `Pbindef(name).stop` stops it. Adding or removing pattern
keys while playing does not cancel the transport stream. Anonymous patterns
still return a separate player; retain it if you need to stop that instance.

Control requests and cancellation retain their receive order per pattern. A
delivery failure stops that run once; its remaining pending events do not keep
submitting to the device, and delayed errors from a stopped run cannot stop a
replay. Missed deadlines are reported rather than played late. Before a cold
start, `ESP32.prepare(target).wait` inside a Routine warms the parameter schema
and clock estimate. Larger `ESP32.latency` can accommodate more network jitter,
but increases the number of queued events; each device has 16 queue entries.

## Timing, transport and bounds

The SC connection is authenticated **OSC over loopback TCP**. Initial source and
binary data use nonempty blobs and chunked transfers above 30 KiB, avoiding SC's
empty-blob issue and fixed OSC builder size. Individual code/source limits remain
64 KiB. Code is not evaluated until the full transfer commits.

The bridge forwards controls over existing paired HTTP, using a separate host
worker pool from bulk uploads. This first version does not open an unauthenticated
OSC/UDP port on the ESP32. Device timestamps use measured clock offsets, refreshed
for long streams; the host queues future events with configurable lookahead.

`ESP32.latency` defaults to **0.25 seconds** for patterns. This adds intentional
latency and allows the paired transport to deliver commands before their deadline.
For a cold or large fleet, call `ESP32.prepare(target).wait` inside a Routine before
starting the pattern. Deployments also warm their control schemas. Starts are
quantized to 64-frame audio boundaries (about 1.45 ms at 44.1 kHz), with additional
I2S output latency. Independent boards are not sample-locked. Multi-board RF jitter
and high event-rate qualification remain separate work; two-node software testing
is not a substitute for that measurement.

The device uses a preallocated 16-event queue and 32 recent stream records, in
PSRAM. Commands may schedule up to five seconds ahead, have a 100 ms late window,
and note sustain is limited to 60 seconds. Full/late/stale/invalid commands fail;
pattern errors stop that player instead of silently continuing. No parameter
updates allocate memory, write flash or perform network work on the audio task.
Control snapshots are copied on the audio owner and formatted on the controls task.
Boot IDs and per-stage activation revisions reject delayed commands after reboot,
Panic or code replacement. Automatic finite note releases remain on the device
when the host disappears. Autonomous patches continue independently.

## Verification

```sh
python3 host/test_remote_control.py
python3 host/test_control_client.py
python3 host/test_ide_bridge.py
python3 host/test_studio.py
python3 host/test_network.py
```

The native SC test uses two isolated real HTTP servers and the actual extension,
with no audio playback. It checks identical compiled bytes, original source,
near-64 KiB source, aliases, Pseq/Prand, timestamps, stop/replay and cancellation.
Portable C tests cover ownership, revisions, atomic updates and queue bounds.
Physical results are in `evidence/ide-device.json`; output was muted during
functional tests and the original packages/selection/volume restored afterward.
