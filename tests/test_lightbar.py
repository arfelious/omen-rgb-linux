#!/usr/bin/env python3
"""
Unit tests for OmenLightbar driver and sysfs_leds integration.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Ensure src is in python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import omen_rgb.lightbar as lightbar
from omen_rgb.lightbar import OmenLightbar


class TestOmenLightbarSysfsLeds(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.leds_dir = os.path.join(self.temp_dir.name, "leds")
        os.makedirs(self.leds_dir)

        # Create mock devices for 4 zones
        for zone in range(1, 5):
            zdir = os.path.join(self.leds_dir, f"hp::lightbar-{zone}")
            os.makedirs(zdir)
            with open(os.path.join(zdir, "multi_index"), "w") as f:
                f.write("red green blue\n")
            with open(os.path.join(zdir, "multi_intensity"), "w") as f:
                f.write("255 128 64\n")
            with open(os.path.join(zdir, "brightness"), "w") as f:
                f.write("255\n")
            with open(os.path.join(zdir, "max_brightness"), "w") as f:
                f.write("255\n")

        self.leds_patcher = patch.object(lightbar, "SYSFS_LEDS_BASE", self.leds_dir)
        self.leds_patcher.start()

    def tearDown(self):
        self.leds_patcher.stop()
        self.temp_dir.cleanup()

    def test_backend_detection(self):
        backend = OmenLightbar._detect_backend()
        self.assertEqual(backend, "sysfs_leds")

    def test_zone_discovery(self):
        zones = OmenLightbar.get_zone_devices()
        self.assertEqual(len(zones), 4)
        self.assertEqual([z[0] for z in zones], [1, 2, 3, 4])
        self.assertEqual(OmenLightbar.get_num_zones(), 4)

    def test_is_supported_and_available(self):
        self.assertTrue(OmenLightbar.is_supported())
        self.assertTrue(OmenLightbar.is_available())

    def test_get_colors(self):
        lb = OmenLightbar()
        colors = lb.get_colors()
        self.assertIsNotNone(colors)
        self.assertEqual(len(colors), 4)
        self.assertEqual(colors[0], (255, 128, 64))
        self.assertEqual(colors[3], (255, 128, 64))

    def test_get_brightness(self):
        lb = OmenLightbar()
        self.assertEqual(lb.get_brightness(), 100)

        # Update zone 1 brightness to 128 (~50%)
        with open(os.path.join(self.leds_dir, "hp::lightbar-1", "brightness"), "w") as f:
            f.write("128\n")
        self.assertEqual(lb.get_brightness(), 50)

    def test_set_colors(self):
        lb = OmenLightbar()
        new_colors = [
            (255, 0, 0),
            (0, 255, 0),
            (0, 0, 255),
            (255, 255, 0),
        ]
        ret = lb.set_colors(new_colors, brightness=80)
        self.assertTrue(ret)

        # Check multi_intensity files
        for i, (r, g, b) in enumerate(new_colors, 1):
            with open(os.path.join(self.leds_dir, f"hp::lightbar-{i}", "multi_intensity")) as f:
                content = f.read().strip()
                self.assertEqual(content, f"{r} {g} {b}")
            with open(os.path.join(self.leds_dir, f"hp::lightbar-{i}", "brightness")) as f:
                content = int(f.read().strip())
                self.assertEqual(content, int(round(80 * 2.55)))

    def test_set_zone(self):
        lb = OmenLightbar()
        # Change only zone 2
        lb.set_zone(2, 42, 84, 168, brightness=50)

        with open(os.path.join(self.leds_dir, "hp::lightbar-2", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "42 84 168")
        with open(os.path.join(self.leds_dir, "hp::lightbar-2", "brightness")) as f:
            self.assertEqual(int(f.read().strip()), int(round(50 * 2.55)))

        # Other zones should be unchanged
        with open(os.path.join(self.leds_dir, "hp::lightbar-1", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "255 128 64")

    def test_set_zone_brightness(self):
        lb = OmenLightbar()
        lb.set_zone_brightness(3, 25)
        with open(os.path.join(self.leds_dir, "hp::lightbar-3", "brightness")) as f:
            self.assertEqual(int(f.read().strip()), int(round(25 * 2.55)))

    def test_get_zone_color_and_brightness(self):
        lb = OmenLightbar()
        self.assertEqual(lb.get_zone_color(1), (255, 128, 64))
        self.assertEqual(lb.get_zone_brightness(1), 100)

        # Test effective color calculation with 50% brightness
        lb.set_zone_brightness(1, 50)
        eff_color = lb.get_zone_color(1, effective=True)
        self.assertEqual(eff_color, (128, 64, 32))

    def test_set_static_and_turn_off(self):
        lb = OmenLightbar()
        lb.set_static(100, 150, 200, brightness=75)
        for i in range(1, 5):
            self.assertEqual(lb.get_zone_color(i), (100, 150, 200))
            self.assertEqual(lb.get_zone_brightness(i), 75)

        lb.turn_off()
        for i in range(1, 5):
            self.assertEqual(lb.get_zone_color(i), (0, 0, 0))
            self.assertEqual(lb.get_zone_brightness(i), 0)

    def test_set_brightness(self):
        lb = OmenLightbar()
        lb.set_brightness(60)
        for i in range(1, 5):
            self.assertEqual(lb.get_zone_brightness(i), 60)


class TestOmenLightbarNoBackend(unittest.TestCase):
    def test_no_backend_when_sysfs_missing(self):
        # When sysfs is missing, backend should be None
        with patch.object(lightbar, "SYSFS_LEDS_BASE", "/nonexistent/leds"):
            self.assertIsNone(OmenLightbar._detect_backend())
            self.assertFalse(OmenLightbar.is_supported())
            self.assertFalse(OmenLightbar.is_available())


class TestCLILightbarIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.leds_dir = os.path.join(self.temp_dir.name, "leds")
        os.makedirs(self.leds_dir)

        for zone in range(1, 5):
            zdir = os.path.join(self.leds_dir, f"hp::lightbar-{zone}")
            os.makedirs(zdir)
            with open(os.path.join(zdir, "multi_index"), "w") as f:
                f.write("red green blue\n")
            with open(os.path.join(zdir, "multi_intensity"), "w") as f:
                f.write("0 0 0\n")
            with open(os.path.join(zdir, "brightness"), "w") as f:
                f.write("255\n")
            with open(os.path.join(zdir, "max_brightness"), "w") as f:
                f.write("255\n")

        self.leds_patcher = patch.object(lightbar, "SYSFS_LEDS_BASE", self.leds_dir)
        self.leds_patcher.start()

    def tearDown(self):
        self.leds_patcher.stop()
        self.temp_dir.cleanup()

    def test_cli_zone_command(self):
        from omen_rgb.cli import main
        import sys
        test_args = ["omen-rgb", "lightbar", "zone", "2", "#00ffaa", "--brightness", "90"]
        with patch.object(sys, "argv", test_args):
            main()

        lb = OmenLightbar()
        self.assertEqual(lb.get_zone_color(2), (0, 255, 170))
        self.assertEqual(lb.get_zone_brightness(2), 90)

    def test_cli_brightness_command(self):
        from omen_rgb.cli import main
        import sys
        test_args = ["omen-rgb", "lightbar", "brightness", "70"]
        with patch.object(sys, "argv", test_args):
            main()

        lb = OmenLightbar()
        self.assertEqual(lb.get_brightness(), 70)


if __name__ == "__main__":
    unittest.main()
