# Portable normalized input buses (experimental)

Originally implemented and host-tested 6 November 2026; imported and rechecked
against this checkout's current engine and qualified kernels on 14 November.
This component is independent of GPIO, I2C, ESP-IDF tasks and the sensor model.
It performs normalization, freshness tracking, explicit slot configuration and
writes a caller-owned bus snapshot. **It is not yet connected to the production
application or a sensor driver.** The silent Voice PE probe does not select or
run it. Run `python3 host/test_input_buses.py` for the sanitized 44.1/48 kHz tests.

The Voice PE layout subsequently agreed with the user reserves **42 onward**
for future Grove inputs; 0–2 are physical inputs and 3–41 are LED controls.
The historical 16–31 draft below is retained only for these portable tests and
must not be wired into the production Voice PE snapshot. Remapping/activation
waits until a Grove sensor is available.

## Historical portable prototype contract

- Eight explicit source slots, values on buses 16–23 and validity on 24–31. This is the proposed Voice PE draft-2 layout. Buses 0–15 and memory after bus 31 remain untouched.
- Continuous finite raw float32 values normalize linearly using calibrated endpoints, clamp to [0,1], and optionally invert. Double intermediates avoid overflow even for extreme float32 endpoints. No smoothing or automatic range adjustment.
- Binary sources accept exactly 0/1 with no inversion; fallback must be zero. Debouncing belongs to the driver. This is sampled level data, not a lossless trigger queue.
- Unassigned slots are 0/invalid. Assigned slots start with their configured fallback/invalid. A successful measurement remains valid until age **>=** its timeout. Invalid/nonfinite measurements do not replace or refresh the last good measurement. Repeated successful measurements with the same value refresh freshness.
- Replacing the complete configuration validates first, advances a generation and resets all cached readings. Slot IDs remain exactly as supplied, including holes. Rejected configuration/batches leave state untouched. Reject duplicate/unknown source IDs, old configuration generations, samples from before configuration, out-of-order/future timestamps and backward clock movement.
- Time is a monotonic uint64 microsecond value, not an audio sample counter. Millisecond metadata requires a checked conversion in the future loader. The component makes no sample-rate assumptions.

`source_id` is a nonzero, stable installed-instance/channel key. The future configuration loader must assign/persist these keys and preserve the textual channel identity; do not derive them from discovery order or an unchecked hash. Source ID zero means an unused slot. All eight configuration entries are supplied to `ib_configure`; the caller must call `ib_init` first and treat internal bank fields as private.

## Integration sketch (not current application behavior)

```c
ib_bank inputs;
ib_init(&inputs);
ib_config slots[IB_SLOTS] = {0};
slots[0] = (ib_config){
    .source_id = 1, .minimum = 0, .maximum = 1000, .fallback = 0,
    .stale_after_us = 2000000, .kind = IB_CONTINUOUS, .invert = 0
};
/* Check every return value. Configuration runs under the same owner. */
int configured = ib_configure(&inputs, slots, now_us);
/* Driver acquisition carries the generation active when it was requested.
 * Transport the sample through a bounded synchronized mailbox to the owner. */
ib_sample reading = {.source_id = 1, .raw = 250,
                     .sampled_at_us = now_us, .valid = 1};
int accepted = configured && ib_ingest(&inputs, inputs.generation, &reading, 1, now_us);
ib_snapshot snapshot;
int published = accepted && ib_snapshot_at(&inputs, now_us, &snapshot)
    && ib_write_buses(&snapshot, control_buses, 32);
```

The code above illustrates a single successful reading. In the real loop, call `ib_snapshot_at` and `ib_write_buses` at every block boundary even when no reading arrived or the latest batch was rejected: that is how stale readings expire. A configuration change invalidates all in-flight acquisition batches from the previous generation. Do not stamp old data with a new generation when draining the queue.

**One owner serializes every API call.** There is no locking and no ISR/task concurrency claim. The worker-to-owner mailbox and persistent configuration loader are still to be implemented. A value/validity snapshot is coherent only under this ownership rule. The audio owner publishes before rendering and keeps its bus array unchanged through both stage renders. Once integrated, bind the persistent array with `fm_bind_control_buses` after every `fm_start`, before preparation, for both Main and FX. The production FX wrapper currently needs that binding added. Do not interpret a passing two-engine-voice test as completed Main/FX integration.

The component never creates/stops voices, writes named controls, releases Panic, operates on a peripheral or mounts storage. Graph replacement does not require sensor reconfiguration. `ib_write_buses` checks capacity and all values before any write; input and output buffers must not overlap. Configuration and samples must be immutable during their calls.

## Validation

From the repository root:

```sh
python3 host/test_input_buses.py
```

The host checks include normalization/clipping/inversion, binary validation, float extremes and nonfinite data, timestamp limits, stale/recovered/unchanged samples, configuration generations, preserved holes, rejected-batch rollback and output bounds. They feed the real generated FM1 engine a multichannel `In.kr` fixture, check all eight value/validity pairs in two separate voices at 44.1 and 48 kHz, and exercise rebinding after restart. A stopped raw engine voice remains stopped when inputs publish. No physical device or sound output is used. This is not full production Panic/lifecycle qualification or an SC numerical equivalence test.

Set `INPUT_BUSES_TARGET_CC` to an installed ESP32-S3 C compiler to also compile the portable component into a target object. This proves compilation only, not linking into a target application, running on hardware, CPU cost or real-time scheduling. Reports go to `build/host/input-buses/report.json`.

Next integration steps: bounded mailbox, metadata loader/persistence, the U136 BH1750 driver, shared Main/FX binding, capability/diagnostic reporting, and hardware commissioning. See [Grove design](../../../ports/voice_pe/GROVE.md) and [recovery plan](../../../ports/voice_pe/RECOVERY.md).
