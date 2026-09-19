#!/usr/bin/env python3
# Omen Lightbar Controller - Linux Support for HP OMEN Light Strip
# Supports:
# 1. Linux Multicolor LED subsystem (/sys/class/leds/hp::lightbar-*) via hp-wmi
# 2. ACPI/WMI command interface (/proc/acpi/call) with onboard animation engine
# Copyright (C) 2026 arfelious

import os
import re
import struct

SYSFS_LEDS_BASE = "/sys/class/leds"
LED_NAME_PREFIX = "hp::lightbar-"
DEFAULT_NUM_ZONES = 4

# The bar's nine device-side animations, selected by payload byte [1] of command 131081.
LB_ANIMATIONS = {
    "lighting-sync": 1,
    "color-cycle": 2,
    "starlight": 3,
    "breathing": 4,
    "wave": 6,
    "raindrop": 7,
    "audio-pulse": 8,
    "confetti": 9,
    "sun": 10,
    "swipe": 11,
}

LB_SPEEDS = {"slow": 0, "medium": 1, "fast": 2}
LB_DIRECTIONS = {"left": 4, "right": 8}
LB_THEMES = {"galaxy": 16, "volcano": 32, "jungle": 48, "ocean": 64, "custom": 80}

# The firmware special-cases #FFFFFF and stores #FEA3DA (purple).
# #FFFFFE avoids the substitution and renders pure white.
_WHITE_SUBSTITUTION = {(0xFF, 0xFF, 0xFF): (0xFF, 0xFF, 0xFE)}


class OmenLightbar:
    """
    Controller for the HP OMEN Laptop bottom light strip (Dojo Lightbar).
    Supports Linux Multicolor LED subsystem (/sys/class/leds/hp::lightbar-*)
    and ACPI call direct WMI interface (/proc/acpi/call) with hardware animations.
    """

    AVOID_FIRMWARE_WHITE = True

    def __init__(self, acpi_path=None):
        self.acpi_path = acpi_path or self._detect_acpi_path()
        self.backend = self._detect_backend()

    def _detect_acpi_path(self):
        return "\\_SB.WMID.WMAA"

    @classmethod
    def get_zone_devices(cls):
        """Discovers registered Linux Multicolor LED devices for the lightbar."""
        if not os.path.exists(SYSFS_LEDS_BASE):
            return []
        devices = []
        try:
            for entry in os.listdir(SYSFS_LEDS_BASE):
                if entry.startswith(LED_NAME_PREFIX):
                    m = re.match(r"^hp::lightbar-(\d+)$", entry)
                    if m:
                        zone_num = int(m.group(1))
                        zone_path = os.path.join(SYSFS_LEDS_BASE, entry)
                        if os.path.exists(os.path.join(zone_path, "multi_intensity")):
                            devices.append((zone_num, zone_path))
        except Exception:
            return []
        devices.sort(key=lambda x: x[0])
        return devices

    @classmethod
    def get_num_zones(cls):
        zones = cls.get_zone_devices()
        return len(zones) if zones else DEFAULT_NUM_ZONES

    @classmethod
    def _detect_backend(cls):
        if cls.get_zone_devices():
            return "sysfs_leds"
        return None

    @classmethod
    def ensure_available(cls, auto_load=True):
        if cls.get_zone_devices():
            return True

        msg = (
            "Lightbar control error: No supported kernel interface found.\n"
            "The hp-wmi driver (/sys/class/leds/hp::lightbar-*) is not available.\n\n"
            "Options to enable lightbar control:\n"
            "  - Install and load omen-fan-control kernel module with multicolor LED support.\n"
        )
        raise RuntimeError(msg)

    @classmethod
    def is_available(cls):
        try:
            return cls.ensure_available(auto_load=True)
        except RuntimeError:
            return False

    @staticmethod
    def _is_success_response(response):
        if not response:
            return False
        res = response.upper()
        if "50415353" in res or "PASS" in res:
            return True
        if "0X50, 0X41, 0X53, 0X53" in res or "0X50,0X41,0X53,0X53" in res.replace(" ", ""):
            return True
        if res.startswith("{"):
            parts = [p.strip() for p in res.strip("{}").split(",") if p.strip()]
            if len(parts) >= 4:
                try:
                    bytes_val = [int(p, 16) for p in parts[:4]]
                    if bytes_val == [0x50, 0x41, 0x53, 0x53]:
                        return True
                except ValueError:
                    pass
        return False

    @classmethod
    def is_supported(cls):
        return len(cls.get_zone_devices()) > 0

    @staticmethod
    def _permission_error_msg(path):
        return f"Permission denied writing to {path}. Please run as root (sudo)."

    def set_zone(self, zone_idx, r, g, b, brightness=None):
        """Sets color (and optional brightness) for a single lightbar zone (1-indexed)."""
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        if self.AVOID_FIRMWARE_WHITE and (r, g, b) in _WHITE_SUBSTITUTION:
            r, g, b = _WHITE_SUBSTITUTION[(r, g, b)]

        zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
        if not os.path.exists(zone_dir):
            raise ValueError(f"Lightbar zone {zone_idx} not found at {zone_dir}")
        try:
            r_c = max(0, min(255, int(r)))
            g_c = max(0, min(255, int(g)))
            b_c = max(0, min(255, int(b)))
            with open(os.path.join(zone_dir, "multi_intensity"), "w") as f:
                f.write(f"{r_c} {g_c} {b_c}\n")
            if brightness is not None:
                scaled_b = max(0, min(255, int(round(brightness * 2.55))))
                with open(os.path.join(zone_dir, "brightness"), "w") as f:
                    f.write(f"{scaled_b}\n")
            return True
        except PermissionError:
            raise PermissionError(self._permission_error_msg(zone_dir))

    def set_zone_brightness(self, zone_idx, brightness):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()
        scaled_b = max(0, min(255, int(round(brightness * 2.55))))

        zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
        if not os.path.exists(zone_dir):
            raise ValueError(f"Lightbar zone {zone_idx} not found at {zone_dir}")
        try:
            with open(os.path.join(zone_dir, "brightness"), "w") as f:
                f.write(f"{scaled_b}\n")
            return True
        except PermissionError:
            raise PermissionError(self._permission_error_msg(zone_dir))

    # ----------------- ACPI Transport Helpers -----------------

    def _build_payload(self, colors, brightness=100, effect=0, config=0, tribe=0, bass=0):
        colors = list(colors)
        if len(colors) > 4:
            colors = colors[:4]
        while len(colors) < 4:
            colors.append((0, 0, 0))

        if self.AVOID_FIRMWARE_WHITE:
            colors = [_WHITE_SUBSTITUTION.get(tuple(c), c) for c in colors]

        data = bytearray(128)
        data[0] = 0
        data[1] = effect & 0xFF
        data[2] = config & 0xFF
        data[3] = max(0, min(100, brightness))
        data[4] = max(0, min(255, tribe))
        data[5] = max(0, min(255, bass))
        data[6] = len(colors)

        offset = 7
        for r, g, b in colors:
            data[offset] = max(0, min(255, r))
            data[offset + 1] = max(0, min(255, g))
            data[offset + 2] = max(0, min(255, b))
            offset += 3

        header = struct.pack("<4sIII", b"SECU", 131081, 11, 128)
        full_buffer = header + data
        return f"b{full_buffer.hex()}"

    def _write_acpi(self, hex_arg):
        acpi_cmd = f"{self.acpi_path} 0 3 {hex_arg}"
        try:
            with open("/proc/acpi/call", "w") as f:
                f.write(acpi_cmd)
            with open("/proc/acpi/call", "r") as f:
                response = f.read().strip()
            if self._is_success_response(response):
                return True
            raise RuntimeError(f"BIOS ACPI call failed. Response: {response}")
        except PermissionError:
            raise PermissionError("Permission denied when writing to /proc/acpi/call. Please run as root (sudo).")
        except FileNotFoundError:
            raise RuntimeError("acpi_call module missing (/proc/acpi/call not found).")

    @staticmethod
    def _pack_config(speed="medium", direction="left", theme="galaxy"):
        def pick(table, value, what):
            if isinstance(value, int):
                return value
            key = str(value).strip().lower()
            if key not in table:
                raise ValueError(f"Unknown {what} '{value}'. Choose one of: {', '.join(table)}")
            return table[key]

        return (pick(LB_SPEEDS, speed, "speed")
                | pick(LB_DIRECTIONS, direction, "direction")
                | pick(LB_THEMES, theme, "theme"))

    # ----------------- Control Methods -----------------

    def set_colors(self, colors, brightness=100):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        num_zones = self.get_num_zones()
        colors = list(colors)
        if len(colors) > num_zones:
            colors = colors[:num_zones]
        while len(colors) < num_zones:
            colors.append((0, 0, 0))

        if self.AVOID_FIRMWARE_WHITE:
            colors = [_WHITE_SUBSTITUTION.get(tuple(c), c) for c in colors]

        if self.backend == "sysfs_leds":
            try:
                zones = self.get_zone_devices() or [
                    (i, os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{i}"))
                    for i in range(1, num_zones + 1)
                ]
                for (zone_num, zone_dir), (r, g, b) in zip(zones, colors):
                    r_c = max(0, min(255, int(r)))
                    g_c = max(0, min(255, int(g)))
                    b_c = max(0, min(255, int(b)))
                    with open(os.path.join(zone_dir, "multi_intensity"), "w") as f:
                        f.write(f"{r_c} {g_c} {b_c}\n")

                for zone_num, zone_dir in zones:
                    if brightness is not None:
                        scaled_b = max(0, min(255, int(round(brightness * 2.55))))
                    else:
                        scaled_b = 255
                    with open(os.path.join(zone_dir, "brightness"), "w") as f:
                        f.write(f"{scaled_b}\n")
                return True
            except PermissionError:
                raise PermissionError(self._permission_error_msg(SYSFS_LEDS_BASE))

        # Fallback to ACPI call
        return self._write_acpi(self._build_payload(colors, brightness))

    def set_animation(self, effect, theme="galaxy", speed="medium", direction="left",
                      colors=None, brightness=100, levels=(0, 0)):
        """
        Run one of the bar's nine device-side animations via ACPI WMI command 131081.
        """
        self.ensure_available(auto_load=True)

        if isinstance(effect, str):
            key = effect.strip().lower()
            if key not in LB_ANIMATIONS:
                raise ValueError(
                    f"Unknown animation '{effect}'. Choose one of: {', '.join(LB_ANIMATIONS)}")
            effect = LB_ANIMATIONS[key]

        tribe, bass = (list(levels) + [0, 0])[:2]
        payload = self._build_payload(
            colors or [(0, 0, 0)] * 4,
            brightness=brightness,
            effect=effect,
            config=self._pack_config(speed, direction, theme),
            tribe=tribe,
            bass=bass,
        )
        return self._write_acpi(payload)

    def set_brightness(self, brightness):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        if self.backend == "sysfs_leds":
            scaled_b = max(0, min(255, int(round(brightness * 2.55))))
            try:
                zones = self.get_zone_devices() or [
                    (i, os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{i}"))
                    for i in range(1, self.get_num_zones() + 1)
                ]
                for zone_num, zone_dir in zones:
                    with open(os.path.join(zone_dir, "brightness"), "w") as f:
                        f.write(f"{scaled_b}\n")
                return True
            except PermissionError:
                raise PermissionError(self._permission_error_msg(SYSFS_LEDS_BASE))

        # Under ACPI call, re-apply current colors with new brightness
        cur_colors = self.get_colors() or [(255, 153, 0)] * 4
        return self.set_colors(cur_colors, brightness=brightness)

    def set_static(self, r, g, b, brightness=100):
        num_zones = self.get_num_zones()
        return self.set_colors([(r, g, b)] * num_zones, brightness=brightness)

    def turn_off(self):
        return self.set_static(0, 0, 0, brightness=0)

    def get_zone_brightness(self, zone_idx):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        if self.backend == "sysfs_leds":
            zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
            b_file = os.path.join(zone_dir, "brightness")
            if not os.path.exists(b_file):
                return None
            try:
                with open(b_file, "r") as f:
                    val = int(f.read().strip())
                return int(round((val / 255.0) * 100))
            except Exception:
                return None
        return None

    def get_zone_color(self, zone_idx, effective=False):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        if self.backend == "sysfs_leds":
            zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
            intensity_file = os.path.join(zone_dir, "multi_intensity")
            if not os.path.exists(intensity_file):
                return None
            try:
                with open(intensity_file, "r") as f:
                    parts = [int(v) for v in f.read().split()]
                if len(parts) < 3:
                    return None
                r, g, b = parts[0], parts[1], parts[2]
                if effective:
                    b_pct = (self.get_zone_brightness(zone_idx) or 100) / 100.0
                    r = int(round(r * b_pct))
                    g = int(round(g * b_pct))
                    b = int(round(b * b_pct))
                return (r, g, b)
            except Exception:
                return None
        return None

    def get_brightness(self):
        return self.get_zone_brightness(1)

    def get_colors(self, effective=False):
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        if self.backend == "sysfs_leds":
            try:
                zones = self.get_zone_devices() or [
                    (i, os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{i}"))
                    for i in range(1, self.get_num_zones() + 1)
                ]
                colors = []
                for zone_num, zone_dir in zones:
                    color = self.get_zone_color(zone_num, effective=effective)
                    if color is None:
                        return None
                    colors.append(color)
                return colors if colors else None
            except Exception as e:
                print(f"Lightbar leds get_colors notice: {e}")
                return None
        return None
