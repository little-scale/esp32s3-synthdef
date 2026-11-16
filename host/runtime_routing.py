"""Pure admission/planning for payload-selected SynthDef/RNBO dual runtimes.

Transport adapters must provide validated artifacts and verified device state.
No compilation, device I/O, partition writes or executable loading happens here.
"""
from dataclasses import dataclass

ENGINES = frozenset(('synthdef', 'rnbo'))
BOARDS = frozenset(('voice-pe', 'xiao', 'amoled-v2'))


@dataclass(frozen=True)
class Upload:
    engine: str
    rate: int
    identity: str

    def __post_init__(self):
        if self.engine not in ENGINES or type(self.rate) is not int or self.rate not in (16000, 44100, 48000):
            raise ValueError('Unsupported validated artifact engine/rate')
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError('A validated artifact identity is required')


def plan_upload(upload, *, board, current_engine, device_rate, installed, action='upload'):
    """Only a deliberate, already-validated patch upload can request a reboot."""
    if not isinstance(upload, Upload):
        raise ValueError('Validate the payload before planning a runtime switch')
    if board not in BOARDS or current_engine not in ENGINES or device_rate != upload.rate:
        raise ValueError('Device identity, current runtime or sample rate is incompatible')
    allowed = (16000, 48000) if board == 'voice-pe' else (16000,44100) if board=='xiao' else (44100,)
    if upload.rate not in allowed:
        raise ValueError('Unsupported board/sample-rate combination')
    if action != 'upload' and upload.engine != current_engine:
        raise ValueError('Notes, control messages and discovery must not switch runtimes')
    needs_switch = current_engine != upload.engine
    if needs_switch and upload.engine not in installed:
        raise ValueError('Required runtime is not installed; no reboot requested')
    return dict(engine=upload.engine, rate=upload.rate, switch=needs_switch,
                reconnect=needs_switch, artifact_identity=upload.identity)


def compact_layout(board, synthdef_bytes, rnbo_bytes):
    """Plan a split inside the old 3 MiB app region, preserving storage/NVS.

    This is a size/admission planner, not a migration authorization. The real
    installer must check exact device images, back up flash and check every
    overwritten byte. No filesystem resizing or automatic formatting is implied.
    """
    if board not in ('xiao', 'amoled-v2'):
        raise ValueError('This planner is for the existing XIAO/AMOLED factory layout')
    if any(type(n) is not int or n <= 0 for n in (synthdef_bytes, rnbo_bytes)):
        raise ValueError('Both complete validated image lengths are required')
    align = 0x10000
    synth_capacity = (synthdef_bytes + align - 1) & ~(align - 1)
    rnbo_minimum = (rnbo_bytes + align - 1) & ~(align - 1)
    spare = 0x2f0000 - synth_capacity - rnbo_minimum
    if spare >= 0:
        synth_capacity += (spare // (2 * align)) * align
    ota_offset = 0x300000
    rnbo_offset = 0x10000 + synth_capacity
    rnbo_capacity = ota_offset - rnbo_offset
    if rnbo_capacity < rnbo_minimum:
        raise ValueError('Images do not fit the existing app region; a separately reviewed storage migration is required')
    flash_bytes = 0x800000 if board == 'xiao' else 0x1000000
    return dict(board=board, flash_bytes=flash_bytes,
                app0=dict(offset=0x10000, capacity=synth_capacity, engine='synthdef'),
                app1=dict(offset=rnbo_offset, capacity=rnbo_capacity, engine='rnbo'),
                otadata=dict(offset=ota_offset, bytes=0x2000),
                storage=dict(offset=0x310000, bytes=flash_bytes - 0x310000),
                nvs=dict(offset=0x9000, bytes=0x6000),
                preserves_storage_geometry=True)
