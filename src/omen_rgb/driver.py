#!/usr/bin/env python3
# Omen Keyboard Driver - Linux Support for HP OMEN Keyboards
# Supports:
# 1. 4-Zone WMI Keyboard exposed via Linux Multicolor LED subsystem
#    (/sys/class/leds/hp::kbd_zoned_backlight-*) by hp-wmi kernel driver
# 2. Single-Zone WMI Keyboard (/sys/class/leds/hp::kbd_backlight)
# 3. Per-key USB HID Keyboard (0d62:54bf) with onboard MCU effect engine
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

import json
import os
import re

try:
    from . import effects as fx
    from . import layouts as kbl
except ImportError:
    import effects as fx
    import layouts as kbl

SYSFS_LEDS_BASE = "/sys/class/leds"

# 4-Zone naming corresponding to hp-wmi driver (hp_zone_names_4)
# Index 0: right, 1: center, 2: left, 3: wasd
ZONE_NAMES_4 = ["right", "center", "left", "wasd"]
ZONE_SYSFS_PREFIX = "hp::kbd_zoned_backlight-"
SINGLE_ZONE_SYSFS = "hp::kbd_backlight"
SYSFS_KEYBOARD_TYPE_FILE = "/sys/devices/platform/hp-wmi/keyboard_type"

KEYBOARD_TYPE_NAMES = {
    0: "No Backlight",
    1: "4-Zone with Numpad",
    2: "4-Zone without Numpad",
    3: "Per-Key RGB",
    4: "Single-Zone with Numpad",
    5: "Single-Zone without Numpad",
}

# Variable flags for simulating control without writing to hardware or filesystem
# Set to True or export OMEN_SIMULATE_4ZONE=1 / OMEN_SIMULATE_1ZONE=1
SIMULATE_4ZONE = os.environ.get("OMEN_SIMULATE_4ZONE", "0").lower() in ("1", "true", "yes")
SIMULATE_1ZONE = os.environ.get("OMEN_SIMULATE_1ZONE", "0").lower() in ("1", "true", "yes")


def _resolve_data_path(filename):
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    pkg_path = os.path.join(pkg_dir, "data", filename)
    if os.path.exists(pkg_path):
        return pkg_path
    repo_path = os.path.join(os.path.dirname(os.path.dirname(pkg_dir)), "data", filename)
    if os.path.exists(repo_path):
        return repo_path
    repo_path2 = os.path.join(os.path.dirname(pkg_dir), "data", filename)
    if os.path.exists(repo_path2):
        return repo_path2
    return pkg_path


class OmenKeyboard:
    """
    SDK for controlling HP OMEN Keyboard lighting on Linux.
    Automatically detects and supports:
      - 4-Zone WMI multicolor LED interface (/sys/class/leds/hp::kbd_zoned_backlight-*)
      - Single-Zone WMI multicolor LED interface (/sys/class/leds/hp::kbd_backlight)
      - Per-key USB HID interface (0d62:54bf) with MCU hardware effect engine
      - 4-Zone in-memory simulation mode (simulate_4zone=True)
      - Single-Zone in-memory simulation mode (simulate_1zone=True)
    """
    VID = 0x0d62
    PID = 0x54bf

    REPORT_LENGTH = 64

    # One page is 62 buffer bytes: two of BLength and 60 of colour map. Three pages per
    # channel, so 186 buffer bytes carrying 180 transmitted LED positions.
    PAGES = 3
    PAGE_BYTES = 62
    PAYLOAD_BYTES = 60
    CHANNEL_BYTES = PAGES * PAGE_BYTES              # 186
    TRANSMITTED_POSITIONS = PAGES * PAYLOAD_BYTES   # 180
    DEFAULT_LIVE_POSITIONS = 176

    # Commands. Names are HP's, from McuSDK2 General.GeneralCommandHelper.
    CMD_SET_EFFECT = 0x03
    CMD_COLOR_R = 0x05
    CMD_COLOR_G = 0x06
    CMD_COLOR_B = 0x07
    CMD_LIGHTING_ON_OFF = 0x09
    CMD_STORE_TO_FLASH = 0x0a
    CMD_RESTORE_DEFAULT = 0x10
    CMD_GET_DEVICE_INFO = 0x80
    CMD_GET_EFFECT = 0x83

    TARGET_ALL = 0

    FLASH_MAGIC = bytes((0xac, 0x53))
    RESTORE_MAGIC = bytes((0x94, 0x10, 0x98, 0x27))

    ACK = bytes((0xec, 0xac))
    NAK = bytes((0xec, 0xfa))

    def __init__(self, key_map_path=None, zones_path=None, simulate_4zone=None,
                 simulate_1zone=None, has_numpad=None, layout=None):
        if simulate_4zone is None:
            simulate_4zone = SIMULATE_4ZONE or (os.environ.get("OMEN_SIMULATE_4ZONE", "0").lower() in ("1", "true", "yes"))
        if simulate_1zone is None:
            simulate_1zone = SIMULATE_1ZONE or (os.environ.get("OMEN_SIMULATE_1ZONE", "0").lower() in ("1", "true", "yes"))
        self.simulate_4zone = bool(simulate_4zone)
        self.simulate_1zone = bool(simulate_1zone)
        self._custom_has_numpad = has_numpad

        # 1. Load layout and key catalog
        self._load_layout(key_map_path, layout)

        # 2. Load zone definitions and cut-offs (for 4-zone support)
        if not zones_path:
            zones_path = _resolve_data_path("zones.json")
        self.zones_data = {}
        self.key_to_zone = {}
        try:
            with open(zones_path, 'r') as f:
                self.zones_data = json.load(f)
                for z_name, z_info in self.zones_data.get("zones", {}).items():
                    for k in z_info.get("keys", []):
                        self.key_to_zone[k] = z_name
        except Exception as e:
            print(f"Notice: Could not load zones definition: {e}")

        # 3. Detect hardware backend or initialize simulation
        if self.simulate_4zone:
            self.backend = "sysfs_4zone"
            self.device = None
            self.zone_names = list(ZONE_NAMES_4)
            self.zone_paths = {name: f"/virtual/hp::kbd_zoned_backlight-{name}" for name in self.zone_names}
            self.zone_colors = {
                "wasd": (255, 200, 0),
                "left": (255, 0, 50),
                "center": (180, 0, 255),
                "right": (0, 150, 255),
            }
            self.zone_brightness = {name: 255 for name in self.zone_names}
        elif self.simulate_1zone:
            self.backend = "sysfs_1zone"
            self.device = None
            self.zone_names = ["backlight"]
            self.zone_paths = {"backlight": f"/virtual/{SINGLE_ZONE_SYSFS}"}
            self.zone_colors = {"backlight": (255, 120, 0)}
            self.zone_brightness = {"backlight": 255}
        else:
            self.backend = self._detect_backend()
            self.device = None

            if self.backend == "sysfs_4zone":
                self.zone_names = list(ZONE_NAMES_4)
                self.zone_paths = {}
                self.zone_colors = {}
                self.zone_brightness = {}
                self._init_sysfs_4zone()
            elif self.backend == "sysfs_1zone":
                self.zone_names = ["backlight"]
                self.zone_paths = {"backlight": os.path.join(SYSFS_LEDS_BASE, SINGLE_ZONE_SYSFS)}
                self.zone_colors = {"backlight": (255, 153, 0)}
                self.zone_brightness = {"backlight": 255}
                self._init_sysfs_1zone()
            elif self.backend == "hid_perkey":
                self._init_hid()
            else:
                raise RuntimeError(
                    "No supported Omen keyboard lighting interface found.\n"
                    "Neither hp-wmi sysfs (/sys/class/leds/hp::kbd_zoned_backlight-*) "
                    "nor USB HID device (0d62:54bf) was detected."
                )

    def _load_layout(self, key_map_path=None, layout=None):
        """
        Loads layout definition from data/keyboards.json and data/keys.json.
        """
        self.board = kbl.board_id()
        self.layout_warning = None

        try:
            self.catalog = kbl.Catalog()
            self.names = kbl.KeyNames(key_map_path) if key_map_path else kbl.KeyNames()
        except Exception as e:
            print(f"Warning: Could not load keyboard layouts: {e}")
            self.catalog, self.names = None, None
            self.layout, self.key_map = None, {}
            self.live_positions = self.DEFAULT_LIVE_POSITIONS
            return

        if layout:
            self.layout = self.catalog.by_id(layout)
            if self.layout is None:
                raise ValueError(f"No layout '{layout}' in data/keyboards.json.")
            if not self.layout.verified:
                self.layout_warning = kbl.describe(self.layout, self.board)
        else:
            self.layout = self.catalog.for_board(self.board)
            if self.layout is None:
                self.layout = self.catalog.by_id(self.names.layout_id)
                self.layout_warning = kbl.describe(None, self.board)
            elif not self.layout.verified:
                self.layout_warning = kbl.describe(self.layout, self.board)

        self.live_positions = self.layout.leds if self.layout else self.DEFAULT_LIVE_POSITIONS

        if self.layout is None:
            print(f"Warning: data/keys.json names layout '{self.names.layout_id}', which is not "
                  f"in data/keyboards.json.")
            self.key_map = {}
        elif self.layout.id == self.names.layout_id:
            self.key_map = self.names.rows
        else:
            self.key_map = {'keys': {
                k.name: {'hp': k.name, 'leds': k.leds}
                for k in sorted(self.layout.keys, key=lambda k: k.leds[0])}}

    @classmethod
    def get_sysfs_4zone_devices(cls):
        """Returns dict of {zone_name: sysfs_path} for detected 4-zone sysfs nodes."""
        if not os.path.exists(SYSFS_LEDS_BASE):
            return {}
        found = {}
        for name in ZONE_NAMES_4:
            p = os.path.join(SYSFS_LEDS_BASE, f"{ZONE_SYSFS_PREFIX}{name}")
            if os.path.exists(p) and os.path.exists(os.path.join(p, "multi_intensity")):
                found[name] = p
        return found

    @classmethod
    def _detect_backend(cls):
        # 1. Check for complete 4-zone sysfs support
        four_zones = cls.get_sysfs_4zone_devices()
        if len(four_zones) == len(ZONE_NAMES_4):
            return "sysfs_4zone"

        # 2. Check for single-zone sysfs support
        single_path = os.path.join(SYSFS_LEDS_BASE, SINGLE_ZONE_SYSFS)
        if os.path.exists(single_path) and os.path.exists(os.path.join(single_path, "multi_intensity")):
            return "sysfs_1zone"

        # 3. Check for USB HID per-key device
        try:
            import hid
            for d in hid.enumerate(cls.VID, cls.PID):
                if d.get('interface_number') == 3:
                    return "hid_perkey"
        except Exception:
            pass

        if four_zones:
            return "sysfs_4zone"

        return None

    @property
    def is_4zone(self):
        return self.backend == "sysfs_4zone"

    @property
    def is_single_zone(self):
        return self.backend == "sysfs_1zone"

    @property
    def is_per_key(self):
        return self.backend == "hid_perkey"

    @property
    def is_simulation(self):
        return bool(self.simulate_4zone or self.simulate_1zone)

    @classmethod
    def get_keyboard_type(cls):
        """Reads /sys/devices/platform/hp-wmi/keyboard_type (0..5) or None."""
        if os.path.exists(SYSFS_KEYBOARD_TYPE_FILE):
            try:
                with open(SYSFS_KEYBOARD_TYPE_FILE, "r") as f:
                    return int(f.read().strip())
            except Exception:
                pass
        return None

    @property
    def keyboard_type(self):
        return self.get_keyboard_type()

    @property
    def keyboard_type_name(self):
        t = self.keyboard_type
        return KEYBOARD_TYPE_NAMES.get(t, "Unknown") if t is not None else "Unknown"

    @property
    def has_numpad(self):
        if self._custom_has_numpad is not None:
            return bool(self._custom_has_numpad)

        kb_type = self.keyboard_type
        if kb_type in (1, 3, 4):
            return True
        if kb_type in (2, 5):
            return False

        if self.is_per_key:
            return True

        return True

    def _init_sysfs_4zone(self):
        for name in self.zone_names:
            z_path = os.path.join(SYSFS_LEDS_BASE, f"{ZONE_SYSFS_PREFIX}{name}")
            self.zone_paths[name] = z_path
            self.zone_colors[name] = (255, 153, 0)
            self.zone_brightness[name] = 255

        live_colors = self.get_zone_colors()
        if live_colors:
            for zn, color in live_colors.items():
                self.zone_colors[zn] = color

    def _init_sysfs_1zone(self):
        z_path = self.zone_paths["backlight"]
        intensity_file = os.path.join(z_path, "multi_intensity")
        if os.path.exists(intensity_file):
            try:
                with open(intensity_file, "r") as f:
                    parts = [int(x) for x in f.read().split()]
                if len(parts) >= 3:
                    self.zone_colors["backlight"] = (parts[0], parts[1], parts[2])
            except Exception:
                pass
        b_file = os.path.join(z_path, "brightness")
        if os.path.exists(b_file):
            try:
                with open(b_file, "r") as f:
                    self.zone_brightness["backlight"] = int(f.read().strip())
            except Exception:
                pass

    def _init_hid(self):
        import hid
        target_path = None
        for d in hid.enumerate(self.VID, self.PID):
            if d.get('interface_number') == 3:
                target_path = d['path']
                break
        if not target_path:
            raise RuntimeError("Omen Keyboard Lighting Interface (0d62:54bf) not found.")

        path_bytes = target_path if isinstance(target_path, bytes) else target_path.encode('utf-8')
        if hasattr(hid, "Device"):
            self.device = hid.Device(path=path_bytes)
        elif hasattr(hid, "device"):
            dev = hid.device()
            dev.open_path(path_bytes)
            self.device = dev
        else:
            raise RuntimeError("Installed 'hid' module does not provide 'device' or 'Device'.")

        self.channels = {
            0x05: bytearray(self.CHANNEL_BYTES),  # Red
            0x06: bytearray(self.CHANNEL_BYTES),  # Green
            0x07: bytearray(self.CHANNEL_BYTES)   # Blue
        }

    @staticmethod
    def _permission_error_msg(path):
        return (
            f"Permission denied writing to {path}.\n"
            "To resolve this, run as root (sudo) or install a udev rule:\n"
            '  echo \'SUBSYSTEM=="leds", KERNEL=="hp::kbd_*", ACTION=="add", '
            'RUN+="/bin/chmod a+w /sys/class/leds/%k/brightness /sys/class/leds/%k/multi_intensity"\' '
            "| sudo tee /etc/udev/rules.d/99-hp-omen-keyboard.rules\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger"
        )

    # ----------------- Zone Controls (4-Zone / 1-Zone) -----------------

    def set_zone(self, zone_name_or_id, r, g, b, brightness=None):
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))

        if isinstance(zone_name_or_id, int):
            if 0 <= zone_name_or_id < len(ZONE_NAMES_4):
                zone_name = ZONE_NAMES_4[zone_name_or_id]
            else:
                raise ValueError(f"Invalid zone ID {zone_name_or_id}. Expected 0..3.")
        else:
            zone_name = str(zone_name_or_id).lower().strip()

        if self.is_4zone:
            if zone_name not in self.zone_colors:
                raise KeyError(f"Unknown zone '{zone_name}'. Expected one of {list(self.zone_colors.keys())}")
            self.zone_colors[zone_name] = (r, g, b)
            if brightness is not None:
                self.zone_brightness[zone_name] = max(0, min(255, int(round(brightness * 2.55))))
            return

        if self.is_single_zone:
            self.zone_colors["backlight"] = (r, g, b)
            if brightness is not None:
                self.zone_brightness["backlight"] = max(0, min(255, int(round(brightness * 2.55))))
            return

        if self.is_per_key:
            keys_in_z = self.zones_data.get("zones", {}).get(zone_name, {}).get("keys", [])
            for k in keys_in_z:
                self.set_key_color(k, r, g, b)

    def get_zone_brightness(self, zone_name_or_id):
        """Returns brightness percentage (0-100) for a zone."""
        if isinstance(zone_name_or_id, int):
            zone_name = ZONE_NAMES_4[zone_name_or_id] if 0 <= zone_name_or_id < len(ZONE_NAMES_4) else "right"
        else:
            zone_name = str(zone_name_or_id).lower()

        if self.simulate_4zone:
            return int(round((self.zone_brightness.get(zone_name, 255) / 255.0) * 100))

        if self.simulate_1zone:
            return int(round((self.zone_brightness.get("backlight", 255) / 255.0) * 100))

        if self.is_4zone:
            z_dir = self.zone_paths.get(zone_name)
            if z_dir:
                b_file = os.path.join(z_dir, "brightness")
                if os.path.exists(b_file):
                    try:
                        with open(b_file, "r") as f:
                            val = int(f.read().strip())
                        return int(round((val / 255.0) * 100))
                    except Exception:
                        pass
            return int(round((self.zone_brightness.get(zone_name, 255) / 255.0) * 100))

        if self.is_single_zone:
            z_dir = self.zone_paths.get("backlight")
            if z_dir:
                b_file = os.path.join(z_dir, "brightness")
                if os.path.exists(b_file):
                    try:
                        with open(b_file, "r") as f:
                            val = int(f.read().strip())
                        return int(round((val / 255.0) * 100))
                    except Exception:
                        pass
            return int(round((self.zone_brightness.get("backlight", 255) / 255.0) * 100))

        return 100

    def set_zones(self, colors):
        if len(colors) != len(ZONE_NAMES_4):
            raise ValueError(f"Expected {len(ZONE_NAMES_4)} colors, got {len(colors)}")
        for idx, (r, g, b) in enumerate(colors):
            self.set_zone(idx, r, g, b)

    def get_zone_colors(self):
        if self.is_simulation:
            return dict(self.zone_colors)

        if not self.is_4zone:
            return {}

        colors = {}
        for name in self.zone_names:
            z_dir = self.zone_paths.get(name)
            if not z_dir:
                continue
            intensity_file = os.path.join(z_dir, "multi_intensity")
            if os.path.exists(intensity_file):
                try:
                    with open(intensity_file, "r") as f:
                        parts = [int(x) for x in f.read().split()]
                    if len(parts) >= 3:
                        colors[name] = (parts[0], parts[1], parts[2])
                except Exception:
                    pass
        return colors

    # ----------------- HID Framing & Protocol -----------------

    def _frame(self, command, index=0, blength=0, payload=b""):
        if len(payload) > self.REPORT_LENGTH - 4:
            raise ValueError(f"Payload is {len(payload)} bytes; 60 is the maximum.")
        report = bytearray(self.REPORT_LENGTH)
        report[0] = command & 0xFF
        report[1] = index & 0xFF
        report[2] = blength & 0xFF
        report[3] = (blength >> 8) & 0xFF
        report[4:4 + len(payload)] = payload
        return bytes(report)

    def _send(self, command, index=0, blength=0, payload=b""):
        if not self.device:
            return 0
        return self.device.write(self._frame(command, index, blength, payload))

    def _read_reply(self, timeout_ms=250):
        if not self.device:
            return None
        try:
            data = self.device.read(self.REPORT_LENGTH, timeout_ms)
        except Exception:
            return None
        return bytes(data) if data else None

    @classmethod
    def _acknowledged(cls, reply):
        return bool(reply) and len(reply) >= 6 and bytes(reply[4:6]) == cls.ACK

    @classmethod
    def _offset(cls, position):
        if not 0 <= position < cls.TRANSMITTED_POSITIONS:
            return None
        page, within = divmod(position, cls.PAYLOAD_BYTES)
        return page * cls.PAGE_BYTES + 2 + within

    # ----------------- Per-Key & LED Addressing -----------------

    def set_led_color(self, position, r, g, b):
        """Colour ONE LED, addressed by colour-map position."""
        if not self.is_per_key and not hasattr(self, 'channels'):
            return False
        offset = self._offset(position)
        if offset is None:
            return False
        self.channels[0x05][offset] = r & 0xFF
        self.channels[0x06][offset] = g & 0xFF
        self.channels[0x07][offset] = b & 0xFF
        return True

    def key_leds(self, key_name):
        """The colour-map positions of a key."""
        for category in self.key_map.values():
            if isinstance(category, dict) and key_name in category:
                info = category[key_name]
                if "leds" in info:
                    return info["leds"]
                if "offset" in info:
                    return list(range(info["offset"], info["offset"] + info.get("width", 1)))
        if self.names and self.layout:
            hp = self.names.hp_name(key_name, self.layout)
            if hp:
                return self.layout.key(hp).leds
        return None

    def keys(self):
        """Every key name this keyboard answers to, in colour-map order."""
        return [name for category in self.key_map.values() if isinstance(category, dict) for name in category]

    def set_key_color(self, key_name, r, g, b):
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))

        if self.is_4zone:
            zone = self.key_to_zone.get(key_name, "center")
            self.zone_colors[zone] = (r, g, b)
            return True

        if self.is_single_zone:
            self.zone_colors["backlight"] = (r, g, b)
            return True

        if self.is_per_key:
            # Check legacy offset dictionary directly if present in key_map
            for cat in self.key_map.values():
                if isinstance(cat, dict) and key_name in cat:
                    info = cat[key_name]
                    if "offset" in info and "leds" not in info:
                        offset = info["offset"]
                        width = info.get("width", 1)
                        for i in range(width):
                            self.channels[0x05][offset + i] = r
                            self.channels[0x06][offset + i] = g
                            self.channels[0x07][offset + i] = b
                        if key_name == "p" and "p_icon" in self.keys():
                            self.set_key_color("p_icon", r, g, b)
                        return True

            leds = self.key_leds(key_name)
            if not leds:
                return False
            for position in leds:
                self.set_led_color(position, r, g, b)
            return True

        return False

    def set_all(self, r, g, b):
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))

        if self.is_4zone:
            for zn in self.zone_names:
                self.zone_colors[zn] = (r, g, b)
            return

        if self.is_single_zone:
            self.zone_colors["backlight"] = (r, g, b)
            return

        if self.is_per_key:
            for channel_id, value in ((0x05, r), (0x06, g), (0x07, b)):
                self.channels[channel_id] = bytearray(self.CHANNEL_BYTES)
                for position in range(self.live_positions):
                    self.channels[channel_id][self._offset(position)] = value & 0xFF

    def apply(self, persist=True):
        """Flushes buffers and applies changes to hardware."""
        if self.is_simulation:
            return

        if self.is_4zone:
            for name, z_dir in self.zone_paths.items():
                if not os.path.exists(z_dir):
                    continue
                r, g, b = self.zone_colors[name]
                try:
                    with open(os.path.join(z_dir, "multi_intensity"), "w") as f:
                        f.write(f"{r} {g} {b}\n")
                    b_val = self.zone_brightness.get(name, 255)
                    with open(os.path.join(z_dir, "brightness"), "w") as f:
                        f.write(f"{b_val}\n")
                except PermissionError:
                    raise PermissionError(self._permission_error_msg(z_dir))
            return

        if self.is_single_zone:
            z_dir = self.zone_paths["backlight"]
            r, g, b = self.zone_colors["backlight"]
            try:
                with open(os.path.join(z_dir, "multi_intensity"), "w") as f:
                    f.write(f"{r} {g} {b}\n")
                b_val = self.zone_brightness.get("backlight", 255)
                with open(os.path.join(z_dir, "brightness"), "w") as f:
                    f.write(f"{b_val}\n")
            except PermissionError:
                raise PermissionError(self._permission_error_msg(z_dir))
            return

        if self.is_per_key:
            reports = []
            for channel_id in [0x05, 0x06, 0x07]:
                data = self.channels[channel_id]
                for chunk_idx in range(self.PAGES):
                    report = bytearray(self.REPORT_LENGTH)
                    report[0] = channel_id
                    report[1] = chunk_idx
                    chunk_data = data[chunk_idx * self.PAGE_BYTES:(chunk_idx + 1) * self.PAGE_BYTES]
                    report[2:64] = chunk_data
                    reports.append(report)

            for r in reports:
                self.device.write(bytes(r))

            if persist:
                self.store_to_flash()

    # ----------------- MCU Hardware Effects & Commands -----------------

    def store_to_flash(self, target=TARGET_ALL):
        self._send(self.CMD_STORE_TO_FLASH, target, 2, self.FLASH_MAGIC)
        return self._send(self.CMD_STORE_TO_FLASH, target, 2, self.FLASH_MAGIC)

    def set_lighting_on(self, on=True):
        return self._send(self.CMD_LIGHTING_ON_OFF, 0, 1,
                          bytes((0x01 if on is True else (0x00 if on is False else int(on) & 0xFF),)))

    def set_effect(self, setting, persist=False, target=TARGET_ALL):
        if not isinstance(setting, fx.EffectSetting):
            setting = fx.EffectSetting(setting)

        self.set_lighting_on(True)
        self._read_reply()

        self._send(self.CMD_SET_EFFECT, target, fx.RECORD_LENGTH, setting.to_bytes())
        reply = self._read_reply()

        if persist:
            self.store_to_flash(target)
            self._read_reply()

        return reply

    def get_effect(self, target=TARGET_ALL):
        self._send(self.CMD_GET_EFFECT, target, 0, b"")
        reply = self._read_reply()
        if not reply or len(reply) < fx.FX_COLOR_0 + 3 + 4:
            return None
        if bytes(reply[4:6]) == self.NAK:
            return None
        return fx.parse_record(reply[4:46])

    def get_device_info(self):
        self._send(self.CMD_GET_DEVICE_INFO, 1, 0, b"")
        reply = self._read_reply()
        if not reply or len(reply) < 13:
            return None
        return {
            "effect": fx.effect_name(reply[11]),
            "effect_wire": reply[11],
            "brightness": reply[12],
            "raw": reply,
        }

    def restore_lighting_defaults(self, index=7):
        return self._send(self.CMD_RESTORE_DEFAULT, index, len(self.RESTORE_MAGIC),
                          self.RESTORE_MAGIC)

    def get_colors(self):
        if self.is_4zone:
            key_colors = {}
            for row in self.key_map.values():
                for key_name in row.keys():
                    z = self.key_to_zone.get(key_name, "center")
                    key_colors[key_name] = self.zone_colors.get(z, (255, 153, 0))
            return key_colors

        if self.is_single_zone:
            c = self.zone_colors.get("backlight", (255, 153, 0))
            return {name: c for row in self.key_map.values() for name in row.keys()}

        if self.is_per_key:
            colors = self.get_led_colors()
            return {name: colors[info['leds'][0]]
                    for row in self.key_map.values()
                    for name, info in row.items()
                    if info.get('leds') and info['leds'][0] < len(colors)}

        return {}

    def get_led_colors(self):
        if not self.is_per_key and not hasattr(self, 'channels'):
            return []
        return [(self.channels[0x05][self._offset(p)],
                 self.channels[0x06][self._offset(p)],
                 self.channels[0x07][self._offset(p)])
                for p in range(self.live_positions)]

    def close(self):
        if self.device:
            self.device.close()
            self.device = None


LAMP_CONTROL_REPORT_ID = 6
LAMPARRAY_INTERFACE = 4


def restore_device_lighting_control(vid=OmenKeyboard.VID, pid=OmenKeyboard.PID):
    """
    Tell the keyboard to go back to drawing its own lighting: AutonomousMode = 1.
    Writes report 6 to mi_04 LampArray to clear Windows Dynamic Lighting lockups.
    """
    import hid
    written = 0
    for entry in hid.enumerate(vid, pid):
        if entry.get('interface_number') not in (LAMPARRAY_INTERFACE, -1):
            continue
        if entry.get('usage_page') not in (0x59, 0, None):
            continue
        try:
            device = hid.Device(path=entry['path'])
        except Exception:
            continue
        try:
            device.send_feature_report(bytes((LAMP_CONTROL_REPORT_ID, 0x01)))
            written += 1
        except Exception:
            pass
        finally:
            device.close()
    return written
