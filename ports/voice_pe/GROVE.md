# Grove inputs for the shared SynthDef target

**Historical design draft.** The production [M5Stack DLight driver](GROVE_DLIGHT.md)
now uses bus 42 (normalised) and 43 (lux), with fresh-only publication and native
16 kHz hardware checks. The older 16–31 prototype below remains unconnected;
its proposed configuration files are not accepted by current firmware.

Design draft, source-checked 6 November 2026. At the time of this draft, only a portable normalization/freshness/bus-writing component was implemented and host-tested; it was not connected to the production application. No Grove driver, configuration loader or concurrent sensor mailbox existed, and no sensor or board had been tested. The preserved silent probe still leaves Grove untouched. The JSON files below are proposed metadata, not files accepted by current firmware or Studio.

## Intended user experience

Expose each Grove sensor channel as a **normalized, read-only control-bus signal in [0, 1]**, consumed using ordinary `In.kr`. A multi-channel module occupies one value bus per reading. Musical scaling, smoothing and modulation belong in the SynthDef. No automatic writes to named Main/FX parameters are required.

Select the exact attached module, assign its named channels to persistent bus slots and configure normalization endpoints in the sensor's native units. The same SynthDef can use simulated desktop buses or hardware buses by changing the bank base arguments. This follows the project's existing physical-input model and keeps the shared SC workflow intact.

## Verified board boundary

The pinned official [Grove I2C package](https://github.com/esphome/home-assistant-voice-pe/blob/d4e6fa43d6a1a7d342b7d4d403567e06516719de/modules/grove-i2c.yaml) uses GPIO1 for SDA, GPIO2 for SCL and GPIO46 high for port power. This is separate from the codec/XMOS bus on GPIO5/6. The [power-only package](https://github.com/esphome/home-assistant-voice-pe/blob/d4e6fa43d6a1a7d342b7d4d403567e06516719de/modules/grove-power.yaml) supplies digital modules without starting I2C.

The official [LED & Connector schematic](https://github.com/esphome/home-assistant-voice-pe/blob/d4e6fa43d6a1a7d342b7d4d403567e06516719de/hardware/KiCad/LED%20%26%20Connector.kicad_sch) shows switched 5 V at J4, a TXS0102 U20 between the 3.3 V MCU and connector-side supply, and GPIO46's GROVE_PWR controlling the power switch and translator enable. J4 signals are pin 1 SCL and pin 2 SDA; pin 3 is power and pin 4 ground. Confidence: verified against official schematic and YAML; electrical operation unmeasured.

**Design inference:** this is a digital interface, not a direct analog connection to the ESP's ADC. Do not reuse XIAO's GPIO1/2 ADC driver, connect arbitrary analog sensors on the assumption that their connector fits, or infer a 3.3 V connector supply. An analog knob would need a separately qualified I2C ADC/module. The connector's usable current budget, permitted cable/loading and sensor power-up behavior are not established here. No general Grove compatibility claim follows from the connector shape.

The [Nabu Casa guide](https://support.nabucasa.com/hc/en-us/articles/25938245892765-Connecting-a-sensor-to-the-Grove-port-of-Home-Assistant-Voice-Preview-Edition) documents environment, light, gas and PIR examples under ESPHome. Its firmware setup is reference evidence, not an instruction to replace our native ESP-IDF application. Connect modules with device power disconnected. Our eventual drivers must explicitly manage power, initialization, conversion timing, errors and shutdown.

## Initial candidate catalog

All candidates below are **planned for our firmware**, not supported yet. Exact model/revision matters.

| Profile | Channels | Interface | Musical use / qualification issue |
|---|---|---|---|
| M5Stack DLight U136, BH1750FVI | Illuminance, lx | I2C 0x23 | Hand shading / brightness to timbre; qualify conversion latency before promising gesture response. [Manufacturer](https://shop.m5stack.com/products/dlight-unit-ambient-light-sensor-bh1750fvi-tr) |
| M5Stack ENV IV U001-D, SHT40 + BMP280 | Temperature °C, humidity %RH, pressure hPa | I2C 0x44 and 0x76 | Three slow modulation sources from one module. Manufacturer currently marks this revision EOL; it is a reference profile, not a purchase recommendation. Other ENV revisions need distinct profiles. [Manufacturer](https://shop.m5stack.com/products/env-iv-unit-with-temperature-humidity-air-pressure-sensor-sht40-bmp280) |
| M5Stack PIR U004 | Motion, boolean | Digital; signal mapping unresolved | Presence-controlled textures. Fixed 2-second, retriggerable output makes it unsuitable as a precise rapid note trigger. [Manufacturer](https://docs.m5stack.com/en/unit/PIR) |

**PIR discrepancy to resolve before enabling:** Nabu Casa's example specifies GPIO2, while M5Stack labels U004's digital output as the white conductor (yellow NC). Voice PE's schematic assigns SDA to J4 pin 2, and the official bus package assigns SDA to GPIO1. Cable conventions alone cannot resolve this. The draft profile records the official GPIO2 example but deliberately leaves `qualified_gpio` null. Verify the actual module revision, connector continuity with power off, and signal level after arrival. Do not silently turn either assumption into a driver default.

For several I2C modules, the [M5Stack U006 hub](https://docs.m5stack.com/en/unit/hub) directly parallels its ports. It is not an address multiplexer: addresses must be unique across all chips, including both chips inside ENV IV. Two DLight modules at 0x23 cannot coexist on that passive hub without another qualified arrangement. The catalog does not assume a chip's optional address is selectable on its assembled module. A digital PIR and I2C cannot share those same signal wires through this hub. A GPIO expander or true I2C multiplexer would need its own driver and topology metadata.

Distance, IMU, rotary/ADC and touch modules are useful next candidates for expressive control, but none is qualified by this draft. Gas sensors are lower priority for interaction; their warm-up, compensation and measurement semantics need separate profiles.

## Normalized bus contract (draft 2)

The engine currently has 32 control buses (0–31). Preserve touch buses 0–2 and XIAO buses 8–10. Reserve the following **proposed** Grove layout within the existing bank; these buses are not populated by the current firmware:

| Buses | Meaning | Values |
|---|---|---|
| 16–23 | Eight configurable Grove channel slots | Finite float32, clamped 0–1 |
| 24–31 | Matching validity slots | Exactly 1 when fresh/valid, otherwise 0 |

For slot `k`, read value `16+k` and validity `24+k`. Eight is a deliberate initial capacity, not a claim about the number of electrical devices the port can power. Reject configurations exceeding it. Control and audio buses are separate namespaces; this allocation does not alter `In.ar(0, 2)`.

Slots bind to **instance ID + channel ID**, not scan order or I2C address order. Save assignments explicitly; removal leaves a hole, reconnect restores the original slot, and adding another sensor never renumbers existing channels. Unassigned/disabled slots read value 0 and validity 0. The example assigns light to 16, temperature to 17, humidity to 18 and pressure to 19; validity is 24–27. All configuration examples remain disabled until implemented and qualified.

### Normalization

For a continuous channel with native-unit endpoints `min < max`:

```text
u = clamp((raw - min) / (max - min), 0, 1)
value = invert ? 1 - u : u
```

Endpoints must be finite and produce a finite positive span. Reject invalid configurations. Compute with sufficient intermediate precision to avoid overflow and reject nonfinite measurements before conversion; no NaN/Inf reaches the bus. A valid measurement outside the selected calibration range clamps to an endpoint and remains valid; sensor-reported errors do not become endpoint values. Report clipping separately in diagnostics.

The calibrated range is explicit, saved and stable; do not automatically rescale according to recent minima/maxima. For example 0–1000 lx can map to 0–1 for an indoor light setup. That is a user-selected normalization range, not the sensor's full measurement range. Each channel has independent endpoints in its own units. Naturally signed inputs can also map to 0–1 with zero at the appropriate midpoint. Digital channels expose false = 0, true = 1 after driver-level debounce, without interpolating binary states.

No hidden musical response curve, deadband or smoothing is applied to the value buses in this first contract. Use `Lag.kr`, range mapping and other supported UGens in the SynthDef. Driver-level filtering/conversion mode, if present, must be documented. Bus updates happen at the audio block boundary; between sensor samples, values are held. This is control-rate data, not a claim of audio-rate acquisition or sample-accurate edges.

Before the first valid reading, or when `stale_after_ms` elapses since the last successful reading, publish the configured finite `fallback_normalized` (default 0) and validity 0 **together**. An unchanged successful reading refreshes freshness. On recovery, publish the new normalized reading and validity 1 together. A low measurement of 0 is distinguishable from a disconnected sensor through validity. Fallback is immediate at the next block; the SynthDef can smooth if desired. For motion/gate use, fallback must be 0. Polling a digital level can miss short pulses; queued trigger events are outside this contract.

### Metadata files

- `grove/catalog.draft.json`: exact modules/chips, occupied addresses, channel IDs/types/native units, sources, planned driver keys and qualification status. This remains hardware capability metadata. Unknown limits are null. An ACK is not sensor identification, and metadata is not a driver.
- `grove/example-i2c-device.draft.json` and `example-pir-device.draft.json`: installed instances, exclusive port mode, topology and proposed polling intervals. Both are disabled; PIR additionally awaits signal-pin qualification.
- `grove/example-buses.draft.json`: versioned `synthdef-input-buses-draft-2` allocation, source channel, normalization endpoints, inversion, stale timeout and normalized fallback. It replaces the earlier named-parameter bindings example. There are no stage/parameter targets or musical output ranges in this contract.

The JSON files are design examples, not a production schema or files current firmware/Studio accepts. Configuration belongs to the device and is independent of the loaded graph. Report resolved value/validity bus numbers through capabilities/input diagnostics, together with raw units, raw/normalized values, age, validity, clipping and faults. Graph changes do not reorder or reset sensor assignments. Any eventual named-control mapping UI would be an optional layer over these buses, not their primary interface.

## SynthDef example

Illustrative bank addresses are the proposed allocation above. The checked-in [grove/example.scd](grove/example.scd) defines this graph without starting audio:

```supercollider
SynthDef(\GroveLight, { |groveBus = 16, groveValidBus = 24|
    var light = In.kr(groveBus, 1);
    var valid = In.kr(groveValidBus, 1);
    var freq = Lag.kr(light, 0.1).linlin(0, 1, 110, 880);
    Out.ar(0, (SinOsc.ar(freq) * Lag.kr(valid, 0.02) * 0.03) ! 2);
});
```

Several readings are simply `In.kr(groveBus, 4)` with `In.kr(groveValidBus, 4)`. Different readers can consume the same buses; there is no parameter-ownership conflict. The SynthDef defines what each reading means musically. Other SC controls can still set musical ranges or modulation depths.

On a desktop SC server, allocate separate `Bus.control(s, 8)` value and validity banks, initialize them to zero, set sample values with `setn`, and pass their actual indices to the same graph. ESP buses are fixed read-only hardware snapshots, not dynamically allocated server buses. Do not add `Out.kr` support or increase the bank size merely for this port.

## Shared implementation boundary

The existing `docs/TOUCH_BUSES.md` describes the 32-channel snapshot extension; `docs/HEADLESS.md` and `headless_io.c` establish XIAO's additional 8–10 allocation. The touch document's older “3–31 reserved” table must be read alongside the newer headless allocation. `main.c` currently copies headless inputs to `synth.buses[8+i]` before rendering. Reuse this model with board-independent bus publication, not XIAO GPIO code.

```text
Board adapter + allowlisted sensor drivers (bounded peripheral I/O outside audio task)
    -> coherent raw samples {instance, channel, value, timestamp, valid, sequence}
    -> normalization + freshness + persistent slot allocation
    -> audio owner publishes value AND validity into its stable bus snapshot
    -> In.kr in Main and FX; SynthDef performs musical mapping/smoothing
```

Use preallocated storage and a race-free publication protocol. Individually atomic fields do not guarantee a coherent value/validity pair. Coalesce continuous updates to the latest complete sample, publish before rendering the block, and leave the snapshot unchanged throughout prepare/render. Multi-chip modules do not measure every channel simultaneously: track freshness per channel and do not invent simultaneity. Reconfiguration swaps an entire validated allocation at a block boundary, never half a table.

**Main/FX integration gap:** `instrument.c` binds Main with `fm_bind_control_buses` after `fm_start`. `master_effect_start` currently does not bind a control snapshot before `fm_prepare`, so FX bus access is not already wired up. Add a persistent shared physical-input snapshot (or consistent copies) and bind both voices after every start/restart/replacement, before preparation. Audit all creation/reset paths, including SC-managed instances. Preserve existing touch lifecycle and headless behavior. Both stages must see the same Grove value/validity pairs for the same audio block, including after FX bypass/re-enable.

Sensor work never calls `rc_enqueue`, mutates voice controls, creates an instance or clears Panic. Peripheral reads, waits, retries, identification, parsing, allocation and logging remain outside the audio task. Stalled Grove must not stall audio or the separate codec bus. Panic retains authority over voice/output lifecycle; sensor publishing may continue for diagnostics but cannot restart sound. Existing explicit play/restart semantics remain authoritative.

## Implementation and acceptance plan

Implemented before hardware arrival: [portable input-bus core](../../firmware/components/input_buses/README.md), with host normalization/freshness tests and actual FM1 `In.kr` checks at both rates. Remaining software work: the synchronized sensor mailbox and configuration loader, followed by block-boundary publication in the shared application and both Main/FX start paths. Cover endpoints/midpoints, out-of-range clamping, invalid spans and NaN/Inf, independent channels, stale/recovered/unchanged readings, missing sensor holes, configuration replacement and value/validity coherence. Exercise multichannel `In.kr`, repeated starts, FX bypass, Panic and identical normalization at 44.1/48 kHz. Retain existing bus and graph limits. No sensor-specific UGen or direct named-parameter writer is needed.

After arrival and stock backup: with power off, inspect connector/revision and attach one exact module. Confirm supply/ground, power gating and signal mapping; begin read-only sensor logging with audio blocked. Qualify identification, conversion timing, raw units, calibrated 0–1 endpoints, timeout/disconnect/stuck-bus behavior and restart. Then run the bus-driven SynthDef, and finally qualify multiple channels/hub addresses under sustained audio plus USB/Wi-Fi load. Record actual latency, jitter, memory/CPU load and fault counters. Verify no sensor can defeat Panic. Leave unresolved profiles disabled. Flash/storage policy remains governed by [RECOVERY.md](RECOVERY.md).

For equal-target acceptance, normalized sensor buses must be configured and diagnosed through the same SC/Studio ecosystem with honest board capability reporting. The portable core implements normalization and bus-array writes; production integration, sensor drivers and board qualification remain pending.
