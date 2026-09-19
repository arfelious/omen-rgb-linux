#!/usr/bin/env python3
# Omen Lightbar Controller - Linux Support for HP OMEN Light Strip
# Copyright (C) 2026 arfelious

import os
import re

SYSFS_LEDS_BASE = "/sys/class/leds"
LED_NAME_PREFIX = "hp::lightbar-"
DEFAULT_NUM_ZONES = 4


class OmenLightbar:
    """
    Controller for the HP OMEN Laptop bottom light strip (Dojo Lightbar).
    Uses the Linux Multicolor LED subsystem (/sys/class/leds/hp::lightbar-*)
    exposed by the custom hp-wmi kernel driver of omen-fan-control.
    """

    def __init__(self):
        self.backend = self._detect_backend()

    @classmethod
    def get_zone_devices(cls):
        """
        Discovers registered Linux Multicolor LED devices for the lightbar.
        Returns a list of tuples: [(zone_idx, sysfs_path), ...] sorted by zone_idx (1-indexed).
        """
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
        """Returns the number of detected hardware lightbar zones (defaults to 4)."""
        zones = cls.get_zone_devices()
        return len(zones) if zones else DEFAULT_NUM_ZONES

    @classmethod
    def _detect_backend(cls):
        """
        Detects the available hardware control interface.
        Returns 'sysfs_leds' if hp::lightbar-* multicolor LED devices exist, else None.
        """
        if cls.get_zone_devices():
            return "sysfs_leds"
        return None

    @classmethod
    def ensure_available(cls, auto_load=True):
        """
        Ensures a lightbar interface is available.
        Checks for native kernel sysfs (/sys/class/leds/hp::lightbar-*).
        """
        backend = cls._detect_backend()
        if backend == "sysfs_leds":
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
        """Checks if a lightbar interface is available."""
        try:
            return cls.ensure_available(auto_load=True)
        except RuntimeError:
            return False

    @classmethod
    def is_supported(cls):
        """
        Queries system to detect if HP OMEN Lightbar hardware is supported.
        Under the hp-wmi driver, hp_wmi_lightbar_setup probes the hardware;
        if unsupported, it returns -ENODEV and no sysfs entries are registered.
        """
        return len(cls.get_zone_devices()) > 0

    @staticmethod
    def _permission_error_msg(path):
        return (
            f"Permission denied writing to {path}.\n"
            "To resolve this, run as root (sudo) or install a udev rule:\n"
            '  echo \'SUBSYSTEM=="leds", KERNEL=="hp::lightbar-*", ACTION=="add", '
            'RUN+="/bin/chmod a+w /sys/class/leds/%k/brightness /sys/class/leds/%k/multi_intensity"\' '
            "| sudo tee /etc/udev/rules.d/99-hp-omen-lightbar.rules\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger"
        )

    def set_zone(self, zone_idx, r, g, b, brightness=None):
        """
        Set color (and optional brightness) for a single specific zone.

        Parameters:
            zone_idx (int): Zone number (1-indexed: 1 to 4).
            r, g, b (int): Color components (0-255).
            brightness (int, optional): Brightness level (0-100).
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        r = max(0, min(255, int(r)))
        g = max(0, min(255, int(g)))
        b = max(0, min(255, int(b)))

        zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
        if not os.path.exists(zone_dir):
            raise ValueError(f"Lightbar zone {zone_idx} not found at {zone_dir}")
        try:
            with open(os.path.join(zone_dir, "multi_intensity"), "w") as f:
                f.write(f"{r} {g} {b}\n")
            if brightness is not None:
                scaled_b = max(0, min(255, int(round(brightness * 2.55))))
            else:
                try:
                    with open(os.path.join(zone_dir, "brightness"), "r") as f:
                        scaled_b = int(f.read().strip())
                except Exception:
                    scaled_b = 255
            with open(os.path.join(zone_dir, "brightness"), "w") as f:
                f.write(f"{scaled_b}\n")
            return True
        except PermissionError:
            raise PermissionError(self._permission_error_msg(zone_dir))

    def set_zone_brightness(self, zone_idx, brightness):
        """
        Sets brightness (0-100) for a single specific zone.
        """
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

    def set_colors(self, colors, brightness=100):
        """
        Set color of all lightbar zones.

        Parameters:
            colors (list of tuples): Up to 4 (R, G, B) tuples for zones 1 to 4.
            brightness (int, optional): Brightness level (0-100). Default is 100.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        num_zones = self.get_num_zones()
        colors = list(colors)
        if len(colors) > num_zones:
            colors = colors[:num_zones]
        while len(colors) < num_zones:
            colors.append((0, 0, 0))

        try:
            zones = self.get_zone_devices() or [
                (i, os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{i}"))
                for i in range(1, num_zones + 1)
            ]

            # Write multi_intensity to all zones first
            for (zone_num, zone_dir), (r, g, b) in zip(zones, colors):
                r_c = max(0, min(255, int(r)))
                g_c = max(0, min(255, int(g)))
                b_c = max(0, min(255, int(b)))
                with open(os.path.join(zone_dir, "multi_intensity"), "w") as f:
                    f.write(f"{r_c} {g_c} {b_c}\n")

            # Apply brightness to commit hardware changes
            for zone_num, zone_dir in zones:
                if brightness is not None:
                    scaled_b = max(0, min(255, int(round(brightness * 2.55))))
                else:
                    try:
                        with open(os.path.join(zone_dir, "brightness"), "r") as f:
                            scaled_b = int(f.read().strip())
                    except Exception:
                        scaled_b = 255
                with open(os.path.join(zone_dir, "brightness"), "w") as f:
                    f.write(f"{scaled_b}\n")
            return True
        except PermissionError:
            raise PermissionError(self._permission_error_msg(SYSFS_LEDS_BASE))

    def set_brightness(self, brightness):
        """
        Sets brightness level (0-100) across all zones without modifying their RGB color intensities.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()
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

    def set_static(self, r, g, b, brightness=100):
        """Sets all lightbar zones to the same RGB color."""
        num_zones = self.get_num_zones()
        return self.set_colors([(r, g, b)] * num_zones, brightness=brightness)

    def turn_off(self):
        """Turns off all lightbar zones."""
        return self.set_static(0, 0, 0, brightness=0)

    def get_zone_brightness(self, zone_idx):
        """
        Queries brightness level (0-100) for a specific zone.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}{zone_idx}")
        b_file = os.path.join(zone_dir, "brightness")
        if not os.path.exists(b_file):
            return None
        try:
            with open(b_file, "r") as f:
                val = int(f.read().strip())
            max_b = 255
            max_file = os.path.join(zone_dir, "max_brightness")
            if os.path.exists(max_file):
                try:
                    with open(max_file, "r") as mf:
                        max_b = int(mf.read().strip()) or 255
                except Exception:
                    pass
            return int(round((val / max_b) * 100))
        except Exception:
            return None

    def get_zone_color(self, zone_idx, effective=False):
        """
        Queries active color for a specific zone.

        Parameters:
            zone_idx (int): 1-indexed zone number.
            effective (bool): If True, scales intensity by the zone's brightness.

        Returns:
            (R, G, B) tuple or None.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

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

    def get_brightness(self):
        """
        Returns the current lightbar brightness level (0-100), or None if unavailable.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

        try:
            zone_dir = os.path.join(SYSFS_LEDS_BASE, f"{LED_NAME_PREFIX}1")
            with open(os.path.join(zone_dir, "brightness"), "r") as f:
                val = int(f.read().strip())
            max_b = 255
            max_file = os.path.join(zone_dir, "max_brightness")
            if os.path.exists(max_file):
                try:
                    with open(max_file, "r") as mf:
                        max_b = int(mf.read().strip()) or 255
                except Exception:
                    pass
            return int(round((val / max_b) * 100))
        except Exception:
            return None

    def get_colors(self, effective=False):
        """
        Queries active lightbar zone colors.

        Parameters:
            effective (bool): If True, returned RGB values are scaled by current brightness.
                              If False (default), returns raw RGB intensity palette.

        Returns:
            list of (R, G, B) tuples or None if unsupported/failed.
        """
        self.ensure_available(auto_load=True)
        self.backend = self._detect_backend()

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
