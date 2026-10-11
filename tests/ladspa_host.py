"""Tiny offline LADSPA host for deterministic DSP checks (LADSPA 1.1 ABI)."""

import ctypes
import math
import random


PORT_INPUT, PORT_OUTPUT, PORT_CONTROL, PORT_AUDIO = 1, 2, 4, 8
HINT_BOUNDED_BELOW, HINT_BOUNDED_ABOVE = 1, 2
HINT_TOGGLED, HINT_INTEGER, HINT_LOGARITHMIC = 4, 32, 16
HINT_DEFAULT_MASK = 0x3C0


class RangeHint(ctypes.Structure):
    _fields_ = [("descriptor", ctypes.c_int), ("lower", ctypes.c_float), ("upper", ctypes.c_float)]


Instantiate = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong)
Connect = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_float))
Activate = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
Run = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_ulong)
Deactivate = ctypes.CFUNCTYPE(None, ctypes.c_void_p)
Cleanup = ctypes.CFUNCTYPE(None, ctypes.c_void_p)


class Descriptor(ctypes.Structure):
    _fields_ = [
        ("unique_id", ctypes.c_ulong), ("label", ctypes.c_char_p),
        ("properties", ctypes.c_int), ("name", ctypes.c_char_p),
        ("maker", ctypes.c_char_p), ("copyright", ctypes.c_char_p),
        ("port_count", ctypes.c_ulong),
        ("port_descriptors", ctypes.POINTER(ctypes.c_int)),
        ("port_names", ctypes.POINTER(ctypes.c_char_p)),
        ("port_hints", ctypes.POINTER(RangeHint)),
        ("implementation_data", ctypes.c_void_p),
        ("instantiate", Instantiate), ("connect_port", Connect),
        ("activate", Activate), ("run", Run), ("run_adding", ctypes.c_void_p),
        ("set_run_adding_gain", ctypes.c_void_p), ("deactivate", Deactivate),
        ("cleanup", Cleanup),
    ]


def _default(hint):
    flags = hint.descriptor
    lo, hi = hint.lower, hint.upper
    if flags & HINT_BOUNDED_BELOW == 0:
        lo = 0.0
    if flags & HINT_BOUNDED_ABOVE == 0:
        hi = 0.0
    default = flags & HINT_DEFAULT_MASK
    if default == 0x40:
        value = lo
    elif default == 0x80:
        value = math.exp(math.log(lo) * .75 + math.log(hi) * .25) if flags & HINT_LOGARITHMIC else lo * .75 + hi * .25
    elif default == 0xC0:
        value = math.sqrt(lo * hi) if flags & HINT_LOGARITHMIC else (lo + hi) / 2
    elif default == 0x100:
        value = math.exp(math.log(lo) * .25 + math.log(hi) * .75) if flags & HINT_LOGARITHMIC else lo * .25 + hi * .75
    elif default == 0x140:
        value = hi
    elif default == 0x200:
        value = 0.0
    elif default == 0x240:
        value = 1.0
    elif default == 0x280:
        value = 100.0
    elif default == 0x2C0:
        value = 440.0
    elif default == 0x300:
        value = 0.0
    elif default == 0x340:
        value = -1.0
    elif default == 0x380:
        value = 1.0
    elif default == 0x3C0:
        value = 0.0
    else:
        value = (lo + hi) / 2 if flags & (HINT_BOUNDED_BELOW | HINT_BOUNDED_ABOVE) else 0.0
    if flags & HINT_INTEGER:
        value = round(value)
    if flags & HINT_TOGGLED:
        value = float(value > 0)
    return value


def process(plugin_path, label, controls, samples, sample_rate=48000):
    """Process mono samples using a plugin's real descriptor and graph controls."""
    lib = ctypes.CDLL(str(plugin_path))
    get_descriptor = lib.ladspa_descriptor
    get_descriptor.argtypes = [ctypes.c_ulong]
    get_descriptor.restype = ctypes.POINTER(Descriptor)
    descriptor_ptr = next((p for i in range(128) if (p := get_descriptor(i)) and p.contents.label.decode() == label), None)
    if descriptor_ptr is None:
        raise AssertionError(f"LADSPA label not found: {label}")
    desc = descriptor_ptr.contents
    audio_in = [i for i in range(desc.port_count) if desc.port_descriptors[i] & (PORT_AUDIO | PORT_INPUT) == PORT_AUDIO | PORT_INPUT]
    audio_out = [i for i in range(desc.port_count) if desc.port_descriptors[i] & (PORT_AUDIO | PORT_OUTPUT) == PORT_AUDIO | PORT_OUTPUT]
    if len(audio_in) != 1 or len(audio_out) != 1:
        raise AssertionError(f"expected mono audio ports; found {len(audio_in)} in, {len(audio_out)} out")
    n = len(samples)
    input_buffer = (ctypes.c_float * n)(*samples)
    output_buffer = (ctypes.c_float * n)()
    control_buffers = {}
    controls_seen = set()
    handle = desc.instantiate(descriptor_ptr, sample_rate)
    if not handle:
        raise RuntimeError(f"instantiate failed for {label}")
    active = False
    try:
        for port in range(desc.port_count):
            flags = desc.port_descriptors[port]
            if flags & PORT_CONTROL:
                name = desc.port_names[port].decode()
                value = float(controls[name]) if name in controls else _default(desc.port_hints[port])
                if name in controls:
                    controls_seen.add(name)
                storage = ctypes.c_float(value)
                control_buffers[port] = storage
                desc.connect_port(handle, port, ctypes.pointer(storage))
            elif port == audio_in[0]:
                desc.connect_port(handle, port, input_buffer)
            elif port == audio_out[0]:
                desc.connect_port(handle, port, output_buffer)
        missing = set(controls) - controls_seen
        if missing:
            raise AssertionError(f"graph controls not exposed by plugin: {sorted(missing)}")
        if bool(desc.activate):
            desc.activate(handle)
            active = True
        desc.run(handle, n)
        return list(output_buffer)
    finally:
        if active:
            desc.deactivate(handle)
        desc.cleanup(handle)


def rms(samples):
    return math.sqrt(sum(x * x for x in samples) / len(samples))


def white_noise(size, amplitude, seed):
    rng = random.Random(seed)
    return [rng.uniform(-amplitude, amplitude) for _ in range(size)]
