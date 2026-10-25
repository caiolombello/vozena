"""PipeWire graph: RNNoise, gentle EQ, compression, gain and peak limiting.

Graph syntax: https://docs.pipewire.org/page_module_filter_chain.html
Controls are verified against the bundled LADSPA descriptors.
"""

import json
from pathlib import Path

from .plugins import plugin_paths
from .settings import Settings

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_NODE = "yeti_voice.processed"
CAPTURE_NODE = "yeti_voice.capture"


def controls(settings: Settings, *, bypass=False, muted=False):
    wet = settings.noise / 100
    return {
        "blend": {"Gain 1": 1 - wet, "Gain 2": wet},
        "body": {"Freq": 150.0, "Q": 0.707, "Gain": -0.02 * settings.clarity},
        "presence": {"Freq": 3000.0, "Q": 0.8, "Gain": 0.04 * settings.clarity},
        "gain": {"Gain 1": 10 ** (settings.gain_db / 20)},
        "compare": {
            "Gain 1": float(bypass and not muted),
            "Gain 2": float(not bypass and not muted),
        },
    }


def make_config(settings: Settings, source_name: str, *, output_node=OUTPUT_NODE, capture_node=CAPTURE_NODE,
                bypass=False, muted=False, plugins=None):
    values = controls(settings, bypass=bypass, muted=muted)
    plugins = plugins or plugin_paths()
    rnnoise, lsp = str(plugins["rnnoise"]), str(plugins["lsp"])
    nodes = [
        {"type": "builtin", "name": "input", "label": "copy"},
        {"type": "builtin", "name": "rumble", "label": "bq_highpass",
         "control": {"Freq": 80.0, "Q": 0.707}},
        {"type": "ladspa", "name": "denoise", "plugin": rnnoise,
         "label": "noise_suppressor_mono", "control": {
             "VAD Threshold (%)": 0.0, "VAD Grace Period (ms)": 200.0,
             "Retroactive VAD Grace (ms)": 0.0}},
        # RNNoise delays by one 480-sample frame at 48 kHz. Align the dry branch.
        {"type": "builtin", "name": "dry_delay", "label": "delay",
         "config": {"max-delay": 0.02, "latency": 0.01},
         "control": {"Delay (s)": 0.01, "Feedback": 0.0, "Feedforward": 0.0}},
        {"type": "builtin", "name": "blend", "label": "mixer", "control": values["blend"]},
        {"type": "builtin", "name": "body", "label": "bq_lowshelf", "control": values["body"]},
        {"type": "builtin", "name": "presence", "label": "bq_peaking", "control": values["presence"]},
        {"type": "ladspa", "name": "compressor", "plugin": lsp,
         "label": "http://lsp-plug.in/plugins/ladspa/compressor_mono", "control": {
             "Bypass": 0.0, "Input gain (G)": 1.0, "Output gain (G)": 1.0,
             "Sidechain type": 0.0, "Sidechain mode": 1.0,
             "Sidechain reactivity (ms)": 10.0, "Sidechain lookahead (ms)": 0.0,
             "Sidechain preamp (G)": 1.0, "Compression mode": 0.0,
             "Attack threshold (G)": 10 ** (-18 / 20), "Attack time (ms)": 10.0,
             "Release threshold (G)": 0.0, "Release time (ms)": 150.0,
             "Ratio": 2.5, "Knee (G)": 10 ** (-6 / 20),
             "Makeup gain (G)": 10 ** (3 / 20), "Dry gain (G)": 0.0,
             "Wet gain (G)": 1.0, "Dry/Wet balance (%)": 100.0}},
        {"type": "builtin", "name": "gain", "label": "mixer", "control": values["gain"]},
        {"type": "ladspa", "name": "limiter", "plugin": lsp,
         "label": "http://lsp-plug.in/plugins/ladspa/limiter_mono", "control": {
             "Bypass": 0.0, "Input gain (G)": 1.0, "Output gain (G)": 1.0,
             "Sidechain preamp (G)": 1.0, "Automatic level regulation": 0.0,
             "Operating mode": 0.0, "Threshold (G)": 10 ** (-1 / 20),
             "Gain boost": 0.0, "Lookahead (ms)": 3.0, "Attack time (ms)": 1.0,
             "Release time (ms)": 5.0, "Oversampling": 0.0, "Dithering": 0.0}},
        {"type": "builtin", "name": "compare", "label": "mixer", "control": values["compare"]},
    ]
    pairs = [
        ("input:Out", "rumble:In"), ("input:Out", "compare:In 1"),
        ("rumble:Out", "denoise:Input"), ("rumble:Out", "dry_delay:In"),
        ("dry_delay:Out", "blend:In 1"),
        ("denoise:Output", "blend:In 2"), ("blend:Out", "body:In"),
        ("body:Out", "presence:In"), ("presence:Out", "compressor:Input"),
        ("compressor:Output", "gain:In 1"), ("gain:Out", "limiter:Input"),
        ("limiter:Output", "compare:In 2"),
    ]
    return {
        "context.properties": {"log.level": 1},
        "context.spa-libs": {"audio.convert.*": "audioconvert/libspa-audioconvert",
                             "support.*": "support/libspa-support"},
        "context.modules": [
            {"name": "libpipewire-module-rt", "flags": ["ifexists", "nofail"]},
            {"name": "libpipewire-module-protocol-native"},
            {"name": "libpipewire-module-client-node"},
            {"name": "libpipewire-module-adapter"},
            {"name": "libpipewire-module-filter-chain", "args": {
                "node.description": "Yeti Processado", "media.name": "Vozena",
                "audio.rate": 48000, "audio.channels": 1, "audio.position": ["MONO"],
                "filter.graph": {"nodes": nodes, "links": [
                    {"output": a, "input": b} for a, b in pairs],
                    "inputs": ["input:In"], "outputs": ["compare:Out"]},
                "capture.props": {"node.name": capture_node,
                                  "target.object": source_name, "node.passive": True,
                                  "node.dont-fallback": True},
                "playback.props": {"node.name": output_node, "node.description": "Yeti Processado",
                                   "media.class": "Audio/Source", "node.virtual": True,
                                   "priority.session": 0},
            }},
        ],
    }


def ladspa_requirements():
    """{plugin: {label: [controls Vozena sets]}}, taken from the graph itself."""
    config = make_config(Settings(), "requirements", plugins={"rnnoise": "rnnoise", "lsp": "lsp"})
    required = {}
    for node in config["context.modules"][-1]["args"]["filter.graph"]["nodes"]:
        if node["type"] == "ladspa":
            required.setdefault(node["plugin"], {}).setdefault(node["label"], []).extend(node.get("control", {}))
    return required


def props_payload(settings: Settings, *, bypass=False, muted=False):
    params = []
    for node, ports in controls(settings, bypass=bypass, muted=muted).items():
        for port, value in ports.items():
            params.extend((f"{node}:{port}", value))
    return spa_value({"params": params})


def spa_value(value):
    if isinstance(value, dict):
        return "{ " + " ".join(f"{json.dumps(key)} = {spa_value(item)}" for key, item in value.items()) + " }"
    if isinstance(value, list):
        return "[ " + " ".join(spa_value(item) for item in value) + " ]"
    return json.dumps(value, allow_nan=False)


def serialize_config(config):
    # Module arrays use SPA separators, without commas between objects.
    return "\n".join(f"{key} = {spa_value(value)}" for key, value in config.items()) + "\n"
