#!/usr/bin/env python3
# Omen Keyboard Driver - Linux Support for HP OMEN Keyboards
# Supports both:
# 1. 4-Zone WMI Keyboard exposed via Linux Multicolor LED subsystem
#    (/sys/class/leds/hp::kbd_zoned_backlight-*) by hp-wmi kernel driver
# 2. Per-key USB HID Keyboard (0d62:54bf)
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
      - Per-key USB HID interface (0d62:54bf)
      - 4-Zone in-memory simulation mode (simulate_4zone=True)
      - Single-Zone in-memory simulation mode (simulate_1zone=True)
    """
    VID = 0x0d62
    PID = 0x54bf

    def __init__(self, key_map_path=None, zones_path=None, simulate_4zone=None, simulate_1zone=None, has_numpad=None):
        if simulate_4zone is None:
            simulate_4zone = SIMULATE_4ZONE or (os.environ.get("OMEN_SIMULATE_4ZONE", "0").lower() in ("1", "true", "yes"))
        if simulate_1zone is None:
            simulate_1zone = SIMULATE_1ZONE or (os.environ.get("OMEN_SIMULATE_1ZONE", "0").lower() in ("1", "true", "yes"))
        self.simulate_4zone = bool(simulate_4zone)
        self.simulate_1zone = bool(simulate_1zone)
        self._custom_has_numpad = has_numpad


        # 1. Load keys map
        if not key_map_path:
            key_map_path = _resolve_data_path("keys.json")
        try:
            with open(key_map_path, 'r') as f:
                self.key_map = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load key map: {e}")
            self.key_map = {}

        # 2. Load zone definitions and cut-offs
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
            # Distinct default colors for each zone matching OCC zone layout:
            # WASD: yellow, Left: red, Center: purple, Right: blue
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

    @classmethod
    def get_sysfs_4zone_devices(cls):
        """Returns dict of {zone_name: sysfs_path} for detected 4-zone sysfs nodes."""
        if not os.path.exists(SYSFS_LEDS_BASE):
            return {}
        found = {}
        try:
            for name in ZONE_NAMES_4:
                expected_dir = os.path.join(SYSFS_LEDS_BASE, f"{ZONE_SYSFS_PREFIX}{name}")
                if os.path.exists(os.path.join(expected_dir, "multi_intensity")):
                    found[name] = expected_dir
        except Exception:
            return {}
        return found

    @classmethod
    def _detect_backend(cls):
        """
        Detects available keyboard control interface.
        Priority:
          1. sysfs_4zone: Standard 4-zone Linux Multicolor LED subsystem
          2. sysfs_1zone: Single-zone Linux Multicolor LED subsystem
          3. hid_perkey: Per-key USB HID interface (0d62:54bf)
        """
        four_zones = cls.get_sysfs_4zone_devices()
        if len(four_zones) == 4:
            return "sysfs_4zone"

        single_zone = os.path.join(SYSFS_LEDS_BASE, SINGLE_ZONE_SYSFS)
        if os.path.exists(os.path.join(single_zone, "multi_intensity")):
            return "sysfs_1zone"

        # Check USB HID
        try:
            import hid
            for d in hid.enumerate(cls.VID, cls.PID):
                if d.get('interface_number') == 3:
                    return "hid_perkey"
        except Exception:
            pass

        # Also support partial 4-zone if some zones exist
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
        """
        Reads /sys/devices/platform/hp-wmi/keyboard_type.
        Returns integer 0..5, or None if unavailable.
        """
        if os.path.exists(SYSFS_KEYBOARD_TYPE_FILE):
            try:
                with open(SYSFS_KEYBOARD_TYPE_FILE, "r") as f:
                    return int(f.read().strip())
            except Exception:
                pass
        return None

    @property
    def keyboard_type(self):
        """Returns detected kernel keyboard type ID (0..5) or None."""
        return self.get_keyboard_type()

    @property
    def keyboard_type_name(self):
        """Returns human-readable name for detected keyboard type."""
        t = self.keyboard_type
        return KEYBOARD_TYPE_NAMES.get(t, "Unknown") if t is not None else "Unknown"

    @property
    def has_numpad(self):
        """
        Returns whether the keyboard has a numeric keypad.
        Priority:
          1. Explicit override passed to constructor or config
          2. /sys/devices/platform/hp-wmi/keyboard_type (1, 3, 4 -> True; 2, 5 -> False)
          3. HID per-key (0d62:54bf) -> True
          4. Default True
        """
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

        # Query live state from sysfs if available
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
        if hasattr(hid, "device"):
            # hidapi Cython package
            dev = hid.device()
            dev.open_path(path_bytes)
            self.device = dev
        elif hasattr(hid, "Device"):
            # hid ctypes package
            self.device = hid.Device(path=path_bytes)
        else:
            raise RuntimeError("Installed 'hid' module does not provide 'device' or 'Device'.")

        # Buffer for each color channel (3 chunks of 62 bytes = 186 bytes)
        self.channels = {
            0x05: bytearray(186),  # Red
            0x06: bytearray(186),  # Green
            0x07: bytearray(186)   # Blue
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

    # ----------------- Zone Controls -----------------

    def set_zone(self, zone_name_or_id, r, g, b, brightness=None):
        """
        Sets color (and optional brightness) for a specific zone.
        zone_name_or_id can be string ('right', 'center', 'left', 'wasd') or int (0..3).
        """
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
            if zone_name not in self.zone_paths:
                raise ValueError(f"Zone '{zone_name}' not found. Available: {list(self.zone_paths.keys())}")
            self.zone_colors[zone_name] = (r, g, b)
            if brightness is not None:
                self.zone_brightness[zone_name] = max(0, min(255, int(round(brightness * 2.55))))
            return True

        if self.is_single_zone:
            self.zone_colors["backlight"] = (r, g, b)
            if brightness is not None:
                self.zone_brightness["backlight"] = max(0, min(255, int(round(brightness * 2.55))))
            return True

        if self.is_per_key:
            # Color all keys that map to this zone
            z_keys = self.zones_data.get("zones", {}).get(zone_name, {}).get("keys", [])
            if not z_keys:
                return False
            for k in z_keys:
                self._set_key_color_hid(k, r, g, b)
            return True

        return False

    def set_zones(self, colors_dict_or_list, brightness=None):
        """
        Set colors for all 4 zones.
        Can be list of 4 (R, G, B) tuples in driver index order [right, center, left, wasd]
        or dict { "right": (r,g,b), "center": ..., ... }.
        """
        if isinstance(colors_dict_or_list, (list, tuple)):
            for i, c in enumerate(colors_dict_or_list[:4]):
                self.set_zone(i, c[0], c[1], c[2], brightness=brightness)
        elif isinstance(colors_dict_or_list, dict):
            for zn, c in colors_dict_or_list.items():
                self.set_zone(zn, c[0], c[1], c[2], brightness=brightness)

    def get_zone_colors(self):
        """
        Reads live active zone colors directly from sysfs.
        Returns dict {zone_name: (R, G, B)}.
        """
        if self.is_simulation:
            return dict(self.zone_colors)

        if self.is_4zone:
            res = {}
            for name, z_dir in self.zone_paths.items():
                i_path = os.path.join(z_dir, "multi_intensity")
                if os.path.exists(i_path):
                    try:
                        with open(i_path, "r") as f:
                            parts = [int(x) for x in f.read().split()]
                        if len(parts) >= 3:
                            res[name] = (parts[0], parts[1], parts[2])
                    except Exception:
                        res[name] = self.zone_colors.get(name, (0, 0, 0))
                else:
                    res[name] = self.zone_colors.get(name, (0, 0, 0))
            return res

        if self.is_single_zone:
            i_path = os.path.join(self.zone_paths["backlight"], "multi_intensity")
            if os.path.exists(i_path):
                try:
                    with open(i_path, "r") as f:
                        parts = [int(x) for x in f.read().split()]
                    if len(parts) >= 3:
                        return {"backlight": (parts[0], parts[1], parts[2])}
                except Exception:
                    pass
            return {"backlight": self.zone_colors.get("backlight", (0, 0, 0))}

        # HID fallback: derive from key buffers
        return None

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


    # ----------------- Key / General Controls -----------------

    def _set_zone_hid(self, channel_id, zone_idx, value):
        if 0 <= zone_idx < 186:
            self.channels[channel_id][zone_idx] = value & 0xFF

    def _set_key_color_hid(self, key_name, r, g, b):
        mapping = None
        for category in self.key_map.values():
            if key_name in category:
                mapping = category[key_name]
                break
        if not mapping:
            return False

        offset = mapping["offset"]
        width = mapping.get("width", 1)
        for i in range(width):
            self._set_zone_hid(0x05, offset + i, r)
            self._set_zone_hid(0x06, offset + i, g)
            self._set_zone_hid(0x07, offset + i, b)

        if key_name == "p":
            self._set_key_color_hid("p_icon", r, g, b)

        return True

    def set_key_color(self, key_name, r, g, b):
        """
        Sets color for a key.
        In 4-zone mode, updates the zone containing this key.
        In HID per-key mode, updates the specific key in buffer.
        """
        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))

        if self.is_4zone:
            zone = self.key_to_zone.get(key_name)
            if not zone:
                # Fallback to center if unknown
                zone = "center"
            self.zone_colors[zone] = (r, g, b)
            return True

        if self.is_single_zone:
            self.zone_colors["backlight"] = (r, g, b)
            return True

        if self.is_per_key:
            return self._set_key_color_hid(key_name, r, g, b)

        return False

    def set_all(self, r, g, b):
        """Sets all keys / zones to the given RGB color."""
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
            for ch_id in [0x05, 0x06, 0x07]:
                val = [r, g, b][[0x05, 0x06, 0x07].index(ch_id)]
                self.channels[ch_id] = bytearray([val] * 186)
                for chunk_idx in range(3):
                    self.channels[ch_id][chunk_idx * 62] = 0
                    self.channels[ch_id][chunk_idx * 62 + 1] = 0

    def apply(self):
        """Flushes buffers and applies changes to hardware."""
        if self.is_simulation:
            # Simulation mode: strictly in-memory UI testing, do not write to hardware or filesystem
            return

        if self.is_4zone:
            for name, z_dir in self.zone_paths.items():
                if not os.path.exists(z_dir):
                    continue
                r, g, b = self.zone_colors[name]
                intensity_file = os.path.join(z_dir, "multi_intensity")
                brightness_file = os.path.join(z_dir, "brightness")
                try:
                    with open(intensity_file, "w") as f:
                        f.write(f"{r} {g} {b}\n")
                    b_val = self.zone_brightness.get(name, 255)
                    with open(brightness_file, "w") as f:
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
                for chunk_idx in range(3):
                    report = bytearray(64)
                    report[0] = channel_id
                    report[1] = chunk_idx
                    chunk_data = data[chunk_idx * 62 : (chunk_idx + 1) * 62]
                    report[2:64] = chunk_data
                    reports.append(report)

            # Commit report (ID 0x0a)
            commit = bytearray(64)
            commit[0] = 0x0a
            commit[1] = 0x00
            commit[2] = 0x02
            commit[4] = 0xac
            commit[5] = 0x53
            reports.append(commit)

            # Execute all reports
            for r in reports:
                self.device.write(bytes(r))

            # Mandatory double-apply for the commit packet
            self.device.write(bytes(commit))

    def get_colors(self):
        """
        Returns a dict mapping key_name -> (R, G, B).
        In 4-zone mode, maps keys to their respective zone colors.
        In HID per-key mode, reads from internal HID channel buffers.
        """
        key_colors = {}

        if self.is_4zone:
            for row in self.key_map.values():
                for key_name in row.keys():
                    z = self.key_to_zone.get(key_name, "center")
                    key_colors[key_name] = self.zone_colors.get(z, (255, 153, 0))
            return key_colors

        if self.is_single_zone:
            c = self.zone_colors.get("backlight", (255, 153, 0))
            for row in self.key_map.values():
                for key_name in row.keys():
                    key_colors[key_name] = c
            return key_colors

        if self.is_per_key:
            r_buf = self.channels.get(0x05, bytearray(186))
            g_buf = self.channels.get(0x06, bytearray(186))
            b_buf = self.channels.get(0x07, bytearray(186))

            for row in self.key_map.values():
                for key_name, info in row.items():
                    offset = info.get("offset", 0)
                    if 0 <= offset < 186:
                        key_colors[key_name] = (r_buf[offset], g_buf[offset], b_buf[offset])
            return key_colors

        return {}

    def close(self):
        if self.device:
            self.device.close()
            self.device = None
