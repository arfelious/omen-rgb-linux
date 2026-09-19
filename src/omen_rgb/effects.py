#!/usr/bin/env python3
# Omen Keyboard MCU effect engine - hardware-rendered animations for 0d62:54bf
# Copyright (C) 2026 arfelious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

"""
The keyboard MCU renders twelve animations itself.

Selecting one is a *single* 64-byte report - command 0x03 carrying a 36-byte effect record.
The MCU then runs the animation with no host process, no repaint thread and no keep-alive.
This is a different mechanism from the per-key colour pages in ``driver.py``, which paint a
static picture the host has to redraw to animate.

This module is pure: it builds and parses the record and contains no I/O, so every table
below can be checked against a capture without a keyboard attached.  ``driver.py`` owns the
transport.

Provenance and scope
--------------------
Decoded from OMEN Gaming Hub 1101.2607.3.0 (``McuSDK2.dll``
``General.GeneralCommandHelper``, ``HP.Omen.Core.Common.StarmadeKbLightingEffectCommandHelper``,
and the embedded ``KbAnimationDefaultSetting_Voco.json``), then confirmed byte-for-byte against
a USB capture of OGH driving the device.  All twelve effects were written to real hardware and
looked at.

That was done on **Windows**, on one machine: HP OMEN MAX 16-ak0098nr, board 8D87, BIOS F.07.
The frames are device-level and carry no host dependency, but nothing here has been run on
Linux.  See docs/PROTOCOL.md.
"""

from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------
# Wire tables
# --------------------------------------------------------------------------------------

# StarmadeKbLightingEffectCommandHelper.EffectCommandTable maps OGH's dropdown row to the wire
# byte, and it is not the identity - the twelve names in HP's UI span two device families, so
# no single enum ever matches all of them.  Names here are kebab-case versions of the UI labels.
EFFECTS = {
    "color-cycle": 4,
    "starlight": 7,
    "breathing": 2,
    "ghosting": 8,
    "ripple": 9,
    "wave": 10,
    "omen-x": 13,
    "raindrop": 12,
    "audio-pulse": 14,
    "confetti": 15,
    "sun": 16,
    "swipe": 17,
}

# Wire values the UI never reaches.  Untested on this board; listed so a reader knows the enum
# is wider than the dropdown rather than rediscovering it.
UNEXERCISED_EFFECTS = {
    0: "OFF",
    1: "STEADY",
    3: "BLINKING",
    5: "STATIC_DPI_COLOR",
    6: "STATIC_SHUFFLE",
    11: "LINE_STREAK",
    159: "ALL_KEY_SINGLE_COLOR",
    160: "WAVE_RIGHT_TO_LEFT",
    161: "WAVE_LEFT_TO_RIGHT",
    162: "STATIC_TEMPLATE",
}

# ShowMode merges two ideas: 0 and 1 say how many custom colours there are, 2..5 name a
# firmware palette instead and make the colour block meaningless.
SHOW_MODES = {
    "single": 0,
    "multi": 1,
    "volcano": 2,
    "jungle": 3,
    "ocean": 4,
    "rainbow": 5,
}
PRESETS = ("volcano", "jungle", "ocean", "rainbow")

# ColorNumber is a zero-based count: four custom colours send 3.  The value 4 is a sentinel
# HP spells COLOR_NUMBER_PRESET, meaning "ignore the colour block".
COLOR_NUMBER_PRESET = 4

SPEEDS = {"slow": 0, "medium": 1, "fast": 2}
SIZES = {"small": 0, "medium": 1, "large": 2}

# The WIRE direction order.  HP's *UI* enum has the first two entries the other way round and
# StarmadeKbLightingEffectCommandHelper swaps 0 and 1 on the way out; 2..7 pass through.  Using
# the UI order here would silently invert inward and outward.
DIRECTIONS = {
    "inward": 0,
    "outward": 1,
    "right-to-left": 2,
    "left-to-right": 3,
    "up": 4,
    "down": 5,
    "clockwise": 6,
    "counter-clockwise": 7,
}
DIRECTION_ALIASES = {
    "in": 0,
    "out": 1,
    "left": 2,
    "rtl": 2,
    "right": 3,
    "ltr": 3,
    "cw": 6,
    "ccw": 7,
}

# --------------------------------------------------------------------------------------
# Record layout - payload offsets inside the 36 bytes at report[4:40]
# --------------------------------------------------------------------------------------

RECORD_LENGTH = 36          # GeneralCommandHelper writes BLength = 36

FX_EFFECT = 0
FX_SHOW_MODE = 1
FX_COLOR_NUMBER = 2
FX_LED_SPEED = 3
FX_BRIGHTNESS = 4
FX_DIRECTION = 5
FX_RIPPLE_SIZE = 6
FX_RAINDROP_FREQ = 7
FX_INNER_BRIGHTNESS = 8
FX_OUTER_BRIGHTNESS = 9
FX_COLOR_0 = 24             # four RGB triples at [24..35]
FX_MAX_COLORS = 4

# HP's builder also writes a fifth and sixth colour at [36..41].  They are physically
# transmitted - the report is 64 bytes - but BLength is 36, which ends the record at colour 4,
# and OGH's UI caps at four.  Whether the MCU would honour six under BLength = 42 is untested,
# so this module does not send them.

# --------------------------------------------------------------------------------------
# Which options each effect actually consumes
# --------------------------------------------------------------------------------------
#
# From OGH's animation view-model.  This matters for more than help text: the MCU *merges* an
# effect frame into its stored record rather than replacing it, and it only takes the fields
# the selected effect consumes.  A field an effect ignores keeps whatever it held before, so
# you cannot clear it by sending zero - you have to select an effect that consumes it first.
#
# colors: 0 = none accepted, 2 = two fixed slots, 4 = up to four
# presets: which ShowMode values the UI offers (the firmware does not enforce this)

@dataclass(frozen=True)
class EffectInfo:
    colors: int
    presets: tuple
    speed: bool = True
    direction: bool = False
    size: bool = False
    levels: bool = False        # InnerBrightness / OuterBrightness


_STD = ("volcano", "jungle", "ocean")

EFFECT_INFO = {
    "color-cycle": EffectInfo(colors=4, presets=_STD),
    "starlight":   EffectInfo(colors=4, presets=_STD),
    "breathing":   EffectInfo(colors=4, presets=_STD),
    "ghosting":    EffectInfo(colors=4, presets=_STD),
    "ripple":      EffectInfo(colors=4, presets=_STD, size=True),
    "wave":        EffectInfo(colors=4, presets=_STD + ("rainbow",), direction=True),
    "omen-x":      EffectInfo(colors=4, presets=_STD),
    "raindrop":    EffectInfo(colors=4, presets=_STD),
    "audio-pulse": EffectInfo(colors=2, presets=(), speed=False, levels=True),
    "confetti":    EffectInfo(colors=0, presets=_STD + ("rainbow",)),
    "sun":         EffectInfo(colors=0, presets=_STD),
    "swipe":       EffectInfo(colors=4, presets=(), direction=True),
}

# --------------------------------------------------------------------------------------
# HP's own per-effect defaults
# --------------------------------------------------------------------------------------
#
# Transcribed from KbAnimationDefaultSetting_Voco.json, embedded in
# HP.Omen.Core.Model.DataStructure.dll.  Every effect defaults to left-to-right and medium
# ripple size, which is why neither appears below.

DEFAULTS = {
    "color-cycle": {"show_mode": "volcano", "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "starlight":   {"show_mode": "ocean",   "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "breathing":   {"show_mode": "single",  "speed": "slow",   "colors": [(0xEA, 0x00, 0x2A)]},
    "ghosting":    {"show_mode": "jungle",  "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "ripple":      {"show_mode": "ocean",   "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "wave":        {"show_mode": "rainbow", "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "omen-x":      {"show_mode": "volcano", "speed": "medium", "colors": [(0xEA, 0x00, 0x2A)]},
    "raindrop":    {"show_mode": "single",  "speed": "fast",   "colors": [(0x0F, 0xFA, 0x36)]},
    # Audio Pulse has no theme control, so its ShowMode is not consumed at all; colour 1 is the
    # bass/outer band and colour 2 the treble/inner band.  The levels default non-zero because
    # at 0/0 the effect renders black, which reads as a broken keyboard.
    "audio-pulse": {"show_mode": "multi",   "speed": "medium",
                    "colors": [(0x0F, 0x36, 0xFA), (0xFA, 0x0F, 0xE7)],
                    "inner_brightness": 200, "outer_brightness": 200},
    "confetti":    {"show_mode": "rainbow", "speed": "medium", "colors": [(0x0F, 0x36, 0xFA)]},
    "sun":         {"show_mode": "volcano", "speed": "medium", "colors": [(0x0F, 0x36, 0xFA)]},
    # Swipe renders black on a preset - it is custom-colour only, which is why OGH offers it no
    # themes.  A firmware constraint, not a UI choice.
    "swipe":       {"show_mode": "multi",   "speed": "medium",
                    "colors": [(0xFF, 0x00, 0x00), (0x00, 0x00, 0xFF)]},
}


# --------------------------------------------------------------------------------------
# Lookup helpers
# --------------------------------------------------------------------------------------

def _lookup(table, value, what, aliases=None):
    """Accept either a name from ``table`` or a raw integer wire value."""
    if isinstance(value, int):
        return value & 0xFF
    key = str(value).strip().lower().replace("_", "-")
    if key in table:
        return table[key]
    if aliases and key in aliases:
        return aliases[key]
    if key.isdigit():
        return int(key) & 0xFF
    raise ValueError(f"Unknown {what} '{value}'. Choose one of: {', '.join(sorted(table))}")


def effect_name(wire):
    """Wire byte -> effect name, or a descriptive string for values the UI never sends."""
    for name, value in EFFECTS.items():
        if value == wire:
            return name
    if wire in UNEXERCISED_EFFECTS:
        return f"{UNEXERCISED_EFFECTS[wire].lower()}({wire}, not in OGH's list)"
    return f"wire {wire}"


def _reverse(table, wire, fallback="?"):
    for name, value in table.items():
        if value == wire:
            return name
    return f"{fallback}({wire})"


# --------------------------------------------------------------------------------------
# The record
# --------------------------------------------------------------------------------------

@dataclass
class EffectSetting:
    """
    One 36-byte effect record.

    ``effect`` and ``show_mode`` take names from EFFECTS / SHOW_MODES or raw wire integers.
    Fields left as ``None`` fall back to HP's default for the chosen effect.
    """

    effect: object
    show_mode: object = None
    colors: list = field(default_factory=list)     # up to four (r, g, b) tuples
    speed: object = None
    direction: object = None                       # every effect defaults to left-to-right
    ripple_size: object = None                     # and to medium
    raindrop_frequency: object = None              # defaults to ``speed``; HP never differs
    inner_brightness: int = None                   # Audio Pulse treble level
    outer_brightness: int = None                   # Audio Pulse bass level
    brightness: int = 0                            # OGH always sends 0; see below

    # Brightness travels separately, on command 0x0C, and this field read back unchanged
    # through every frame ever sent to this board - which under the merge rule means no effect
    # consumes it.  Command 0x0C is *refused* on board 8D87 / BIOS F.07, so there is no working
    # brightness lever on this interface at all.  Leave this at 0 unless you are experimenting.

    def __post_init__(self):
        self.name = self.effect if isinstance(self.effect, str) else effect_name(self.effect)
        self.wire = _lookup(EFFECTS, self.effect, "effect")

        defaults = DEFAULTS.get(self.name, {})
        if self.show_mode is None:
            self.show_mode = defaults.get("show_mode", "single")
        if self.speed is None:
            self.speed = defaults.get("speed", "medium")
        if not self.colors:
            self.colors = list(defaults.get("colors", []))
        if self.direction is None:
            self.direction = "left-to-right"
        if self.ripple_size is None:
            self.ripple_size = "medium"
        if self.inner_brightness is None:
            self.inner_brightness = defaults.get("inner_brightness", 0)
        if self.outer_brightness is None:
            self.outer_brightness = defaults.get("outer_brightness", 0)
        if self.raindrop_frequency is None:
            self.raindrop_frequency = self.speed

    # -- warnings -----------------------------------------------------------------------

    def warnings(self):
        """
        Reasons this record may render black or ignore an argument, as plain strings.

        Every entry below was observed on hardware.  A caller can print them; nothing here
        blocks a write, because the firmware is the authority and this table is not.
        """
        out = []
        info = EFFECT_INFO.get(self.name)
        if info is None:
            return ["Effect is not one of OGH's twelve; behaviour on this firmware is untested."]

        show = _lookup(SHOW_MODES, self.show_mode, "show mode")
        using_preset = show >= 2

        if using_preset and not info.presets:
            out.append(
                f"'{self.name}' has no preset palette and renders BLACK on one. "
                "Give it custom colours instead."
            )
        elif using_preset:
            preset = _reverse(SHOW_MODES, show)
            if preset not in info.presets:
                out.append(
                    f"OGH does not offer '{preset}' for '{self.name}' (it offers "
                    f"{', '.join(info.presets)}). The firmware does not enforce this, so it may "
                    "well work - it is simply untested."
                )
        if not using_preset and info.colors == 0:
            out.append(f"'{self.name}' takes no custom colours; the colour block is ignored.")
        if not using_preset and info.colors and len(self.colors) > info.colors:
            out.append(
                f"'{self.name}' uses at most {info.colors} colour(s); the rest are ignored."
            )
        if info.levels and not (self.inner_brightness or self.outer_brightness):
            out.append(
                f"'{self.name}' renders BLACK with both levels at 0 - the levels ARE the "
                "animation. It is host-fed: OGH re-sends the record every 200 ms with the "
                "high band in inner_brightness and the low band in outer_brightness."
            )
        if not info.speed and self.speed not in (None, "medium"):
            out.append(f"'{self.name}' has no speed control; the value is ignored.")
        if not info.direction and _lookup(DIRECTIONS, self.direction, "direction",
                                          DIRECTION_ALIASES) != 3:
            out.append(f"'{self.name}' has no direction control; the value is ignored.")
        if not info.size and _lookup(SIZES, self.ripple_size, "size") != 1:
            out.append(f"'{self.name}' has no size control; the value is ignored.")
        if self.brightness:
            out.append(
                "No effect on this firmware consumes the record's brightness field; it read "
                "back unchanged through every frame. Brightness is command 0x0C, which board "
                "8D87 refuses."
            )
        return out

    # -- serialisation ------------------------------------------------------------------

    def to_bytes(self):
        """The 36-byte payload for command 0x03."""
        show = _lookup(SHOW_MODES, self.show_mode, "show mode")
        colors = list(self.colors)[:FX_MAX_COLORS]

        if show >= 2:
            color_number = COLOR_NUMBER_PRESET
        else:
            color_number = max(0, len(colors) - 1)
            # ShowMode 0 means one custom colour and 1 means several. Keep the two consistent
            # so the record cannot claim a count its mode contradicts.
            show = 0 if len(colors) <= 1 else 1

        p = bytearray(RECORD_LENGTH)
        p[FX_EFFECT] = self.wire
        p[FX_SHOW_MODE] = show
        p[FX_COLOR_NUMBER] = color_number
        p[FX_LED_SPEED] = _lookup(SPEEDS, self.speed, "speed")
        p[FX_BRIGHTNESS] = int(self.brightness) & 0xFF
        p[FX_DIRECTION] = _lookup(DIRECTIONS, self.direction, "direction", DIRECTION_ALIASES)
        p[FX_RIPPLE_SIZE] = _lookup(SIZES, self.ripple_size, "size")
        p[FX_RAINDROP_FREQ] = _lookup(SPEEDS, self.raindrop_frequency, "raindrop frequency")
        p[FX_INNER_BRIGHTNESS] = int(self.inner_brightness) & 0xFF
        p[FX_OUTER_BRIGHTNESS] = int(self.outer_brightness) & 0xFF

        # Colour bytes are RGB, confirmed against HP's own swatch palette.  OGH leaves the
        # block zeroed whenever a preset is selected, and this matches it so a frame from here
        # is byte-identical to a frame from HP's client.
        if color_number != COLOR_NUMBER_PRESET:
            for i, (r, g, b) in enumerate(colors):
                off = FX_COLOR_0 + i * 3
                p[off] = int(r) & 0xFF
                p[off + 1] = int(g) & 0xFF
                p[off + 2] = int(b) & 0xFF

        return bytes(p)

    def __str__(self):
        p = self.to_bytes()
        return describe_record(p)


def parse_record(payload):
    """
    Decode a 36-byte effect record - from :meth:`EffectSetting.to_bytes` or from a 0x83 reply -
    into a dict of decoded values plus the raw bytes.

    The reply to 0x83 is the MCU's *merged* state, not an echo of the last write, so a field
    that matches what you sent does not prove the firmware took it from your frame.
    """
    p = bytes(payload)
    if len(p) < FX_COLOR_0 + 3:
        raise ValueError(f"Effect record is {len(p)} bytes; need at least {FX_COLOR_0 + 3}.")

    count = p[FX_COLOR_NUMBER]
    n = 0 if count == COLOR_NUMBER_PRESET else min(count + 1, FX_MAX_COLORS)
    colors = [
        (p[FX_COLOR_0 + i * 3], p[FX_COLOR_0 + i * 3 + 1], p[FX_COLOR_0 + i * 3 + 2])
        for i in range(n)
        if len(p) >= FX_COLOR_0 + i * 3 + 3
    ]

    return {
        "effect": effect_name(p[FX_EFFECT]),
        "effect_wire": p[FX_EFFECT],
        "show_mode": _reverse(SHOW_MODES, p[FX_SHOW_MODE], "show_mode"),
        "color_number": "preset" if count == COLOR_NUMBER_PRESET else count + 1,
        "speed": _reverse(SPEEDS, p[FX_LED_SPEED], "speed"),
        "brightness": p[FX_BRIGHTNESS],
        "direction": _reverse(DIRECTIONS, p[FX_DIRECTION], "direction"),
        "ripple_size": _reverse(SIZES, p[FX_RIPPLE_SIZE], "size"),
        "raindrop_frequency": _reverse(SPEEDS, p[FX_RAINDROP_FREQ], "speed"),
        "inner_brightness": p[FX_INNER_BRIGHTNESS],
        "outer_brightness": p[FX_OUTER_BRIGHTNESS],
        "colors": colors,
        "raw": p,
    }


def describe_record(payload):
    """One line of English for a record, so a write and its readback compare by eye."""
    d = parse_record(payload)
    parts = [
        d["effect"],
        d["show_mode"],
        d["color_number"] if d["color_number"] == "preset" else f"{d['color_number']} colour(s)",
        f"speed {d['speed']}",
        f"dir {d['direction']}",
        f"size {d['ripple_size']}",
    ]
    if d["brightness"]:
        parts.append(f"brightness {d['brightness']}")
    if d["raindrop_frequency"] != d["speed"]:
        parts.append(f"raindrop {d['raindrop_frequency']}")
    if d["inner_brightness"] or d["outer_brightness"]:
        parts.append(f"inner {d['inner_brightness']} outer {d['outer_brightness']}")
    line = ", ".join(parts)
    if d["colors"]:
        line += "  [" + " ".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in d["colors"]) + "]"
    return line
