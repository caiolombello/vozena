"""Check that a LADSPA library exposes the labels and controls Vozena sets.

Run as a standalone script in a separate process (python3 -I ladspa_check.py
PATH REQUIRED_JSON): loading a plugin library runs its code, and a broken
library must never crash the app. Only the standard library is used.
LADSPA 1.1 descriptor layout: https://www.ladspa.org/ladspa_sdk/ladspa.h.txt
"""

import ctypes
import json
import sys

PORT_INPUT, PORT_CONTROL = 0x1, 0x4


class _Descriptor(ctypes.Structure):
    # Only the leading fields are read; the struct is never allocated here.
    _fields_ = [
        ("unique_id", ctypes.c_ulong), ("label", ctypes.c_char_p),
        ("properties", ctypes.c_int), ("name", ctypes.c_char_p),
        ("maker", ctypes.c_char_p), ("copyright", ctypes.c_char_p),
        ("port_count", ctypes.c_ulong),
        ("port_descriptors", ctypes.POINTER(ctypes.c_int)),
        ("port_names", ctypes.POINTER(ctypes.c_char_p)),
    ]


def input_controls(path):
    """{label: [input control port names]} for every plugin in the library."""
    library = ctypes.CDLL(path)
    descriptor = library.ladspa_descriptor
    descriptor.argtypes = [ctypes.c_ulong]
    descriptor.restype = ctypes.POINTER(_Descriptor)
    plugins = {}
    index = 0
    while True:
        pointer = descriptor(index)
        if not pointer:
            return plugins
        item = pointer.contents
        wanted = PORT_INPUT | PORT_CONTROL
        plugins[item.label.decode("utf-8", "replace")] = [
            item.port_names[port].decode("utf-8", "replace")
            for port in range(item.port_count)
            if item.port_descriptors[port] & wanted == wanted
        ]
        index += 1


def missing_controls(path, required):
    available = input_controls(path)
    return [f"{label}: {name}" for label, names in required.items()
            for name in names if name not in available.get(label, ())]


def main(argv):
    if len(argv) != 3:
        print("usage: ladspa_check.py LIBRARY REQUIRED_JSON", file=sys.stderr)
        return 2
    try:
        missing = missing_controls(argv[1], json.loads(argv[2]))
    except (OSError, AttributeError, ValueError) as error:
        print(f"cannot inspect {argv[1]}: {error}", file=sys.stderr)
        return 1
    for line in missing:
        print("missing " + line, file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
