#!/usr/bin/env python3
"""
Unit tests for OmenKeyboard driver 4-zone sysfs integration and zone cut-offs.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import omen_rgb.driver as driver
from omen_rgb.driver import OmenKeyboard, ZONE_NAMES_4


class TestDriverZones(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cls.keys_path = os.path.join(cls.base_dir, "data", "keys.json")
        cls.zones_path = os.path.join(cls.base_dir, "data", "zones.json")

    def test_zones_json_integrity(self):
        """Verify data/zones.json contains all 4 zones and maps 100% of keys in keys.json."""
        with open(self.keys_path) as f:
            keys_data = json.load(f)
        with open(self.zones_path) as f:
            zones_data = json.load(f)

        self.assertIn("zones", zones_data)
        self.assertIn("cutoffs", zones_data)

        # Check the 4 expected zones
        for z in ["right", "center", "left", "wasd"]:
            self.assertIn(z, zones_data["zones"])
            self.assertIn("zone_id", zones_data["zones"][z])
            self.assertIn("sysfs_name", zones_data["zones"][z])
            self.assertIn("keys", zones_data["zones"][z])

        # Zone IDs must match hp-wmi.c hp_zone_names_4 indices:
        # 0: right, 1: center, 2: left, 3: wasd
        self.assertEqual(zones_data["zones"]["right"]["zone_id"], 0)
        self.assertEqual(zones_data["zones"]["center"]["zone_id"], 1)
        self.assertEqual(zones_data["zones"]["left"]["zone_id"], 2)
        self.assertEqual(zones_data["zones"]["wasd"]["zone_id"], 3)

        # All keys in keys.json must exist in zones.json with zero overlap
        all_keys = set()
        rows = keys_data.get("rows", keys_data)
        aliases = keys_data.get("aliases", {})
        for cat in rows.values():
            if isinstance(cat, dict):
                for k_name in cat.keys():
                    all_keys.add(k_name)

        seen_keys = set()
        for z_name, z_info in zones_data["zones"].items():
            for k_name in z_info["keys"]:
                resolved_k = aliases.get(k_name, k_name)
                self.assertNotIn(resolved_k, seen_keys, f"Duplicate key '{k_name}' found in zone '{z_name}'")
                seen_keys.add(resolved_k)

        self.assertEqual(all_keys, seen_keys, f"Mismatch: missing={all_keys - seen_keys}, extra={seen_keys - all_keys}")

    def test_wasd_keys(self):
        """WASD zone must strictly contain w, a, s, d."""
        with open(self.zones_path) as f:
            zones_data = json.load(f)
        wasd_keys = set(zones_data["zones"]["wasd"]["keys"])
        self.assertEqual(wasd_keys, {"w", "a", "s", "d"})


class TestOmenKeyboardSysfs4Zone(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.leds_dir = os.path.join(self.temp_dir.name, "leds")
        os.makedirs(self.leds_dir)

        # Create mock 4-zone sysfs devices
        for z in ZONE_NAMES_4:
            zdir = os.path.join(self.leds_dir, f"hp::kbd_zoned_backlight-{z}")
            os.makedirs(zdir)
            with open(os.path.join(zdir, "multi_intensity"), "w") as f:
                f.write("100 150 200\n")
            with open(os.path.join(zdir, "brightness"), "w") as f:
                f.write("255\n")
            with open(os.path.join(zdir, "max_brightness"), "w") as f:
                f.write("255\n")

        self.patcher = patch.object(driver, "SYSFS_LEDS_BASE", self.leds_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_backend_detection_4zone(self):
        backend = OmenKeyboard._detect_backend()
        self.assertEqual(backend, "sysfs_4zone")

    def test_driver_initialization_4zone(self):
        kb = OmenKeyboard()
        self.assertTrue(kb.is_4zone)
        self.assertFalse(kb.is_per_key)
        self.assertEqual(kb.zone_names, ZONE_NAMES_4)

        # Should load live colors from mock sysfs
        zone_colors = kb.get_zone_colors()
        for z in ZONE_NAMES_4:
            self.assertEqual(zone_colors[z], (100, 150, 200))

    def test_set_zone(self):
        kb = OmenKeyboard()
        kb.set_zone("wasd", 255, 0, 0, brightness=80)
        self.assertEqual(kb.zone_colors["wasd"], (255, 0, 0))
        self.assertEqual(kb.zone_brightness["wasd"], int(round(80 * 2.55)))

        # Also support index
        kb.set_zone(0, 0, 255, 0)  # index 0 is "right"
        self.assertEqual(kb.zone_colors["right"], (0, 255, 0))

    def test_set_key_color_maps_to_zone(self):
        kb = OmenKeyboard()
        # 'w' is in wasd
        kb.set_key_color("w", 255, 50, 50)
        self.assertEqual(kb.zone_colors["wasd"], (255, 50, 50))

        # 'esc' is in left
        kb.set_key_color("esc", 50, 255, 50)
        self.assertEqual(kb.zone_colors["left"], (50, 255, 50))

        # 'space' is in center
        kb.set_key_color("space", 50, 50, 255)
        self.assertEqual(kb.zone_colors["center"], (50, 50, 255))

        # 'enter' is in right
        kb.set_key_color("enter", 200, 200, 50)
        self.assertEqual(kb.zone_colors["right"], (200, 200, 50))

    def test_set_all(self):
        kb = OmenKeyboard()
        kb.set_all(42, 84, 126)
        for z in ZONE_NAMES_4:
            self.assertEqual(kb.zone_colors[z], (42, 84, 126))

    def test_apply_writes_to_sysfs(self):
        kb = OmenKeyboard()
        kb.set_zone("wasd", 255, 10, 20, brightness=100)
        kb.set_zone("left", 30, 255, 40)
        kb.set_zone("center", 50, 60, 255)
        kb.set_zone("right", 11, 22, 33)
        kb.apply()

        # Check sysfs files
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-wasd", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "255 10 20")
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-left", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "30 255 40")
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-center", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "50 60 255")
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-right", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "11 22 33")

    def test_get_colors_returns_all_keys(self):
        kb = OmenKeyboard()
        kb.set_zone("wasd", 255, 0, 0)
        kb.set_zone("center", 0, 0, 255)
        all_colors = kb.get_colors()

        self.assertEqual(all_colors["w"], (255, 0, 0))
        self.assertEqual(all_colors["a"], (255, 0, 0))
        self.assertEqual(all_colors["s"], (255, 0, 0))
        self.assertEqual(all_colors["d"], (255, 0, 0))
        self.assertEqual(all_colors["space"], (0, 0, 255))
        self.assertEqual(all_colors["t"], (0, 0, 255))


class TestOmenKeyboardSysfs1Zone(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.leds_dir = os.path.join(self.temp_dir.name, "leds")
        os.makedirs(self.leds_dir)

        # Create mock 1-zone sysfs device
        zdir = os.path.join(self.leds_dir, "hp::kbd_backlight")
        os.makedirs(zdir)
        with open(os.path.join(zdir, "multi_intensity"), "w") as f:
            f.write("200 100 50\n")
        with open(os.path.join(zdir, "brightness"), "w") as f:
            f.write("255\n")
        with open(os.path.join(zdir, "max_brightness"), "w") as f:
            f.write("255\n")

        self.patcher = patch.object(driver, "SYSFS_LEDS_BASE", self.leds_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_backend_detection_1zone(self):
        backend = OmenKeyboard._detect_backend()
        self.assertEqual(backend, "sysfs_1zone")

    def test_set_and_apply_1zone(self):
        kb = OmenKeyboard()
        self.assertTrue(kb.is_single_zone)
        self.assertEqual(kb.get_zone_brightness("backlight"), 100)
        kb.set_zone("backlight", 10, 20, 30, brightness=50)
        kb.apply()
        with open(os.path.join(self.leds_dir, "hp::kbd_backlight", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "10 20 30")
        with open(os.path.join(self.leds_dir, "hp::kbd_backlight", "brightness")) as f:
            self.assertIn(f.read().strip(), ["127", "128"])




class TestCli4Zone(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.leds_dir = os.path.join(self.temp_dir.name, "leds")
        os.makedirs(self.leds_dir)

        # Create mock 4-zone sysfs devices
        for z in ZONE_NAMES_4:
            zdir = os.path.join(self.leds_dir, f"hp::kbd_zoned_backlight-{z}")
            os.makedirs(zdir)
            with open(os.path.join(zdir, "multi_intensity"), "w") as f:
                f.write("0 0 0\n")
            with open(os.path.join(zdir, "brightness"), "w") as f:
                f.write("255\n")

        self.patcher = patch.object(driver, "SYSFS_LEDS_BASE", self.leds_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_cli_zone_command(self):
        from omen_rgb.cli import cmd_zone, cmd_zones
        import argparse
        kb = OmenKeyboard()

        args = argparse.Namespace(zone_id="wasd", color=["#ff0000"])
        cmd_zone(kb, args)
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-wasd", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "255 0 0")

        # Test zones command with 4 colors
        args_zones = argparse.Namespace(color=["#010203", "#040506", "#070809", "#0a0b0c"])
        cmd_zones(kb, args_zones)
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-right", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "1 2 3")
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-center", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "4 5 6")
        with open(os.path.join(self.leds_dir, "hp::kbd_zoned_backlight-left", "multi_intensity")) as f:
            self.assertEqual(f.read().strip(), "7 8 9")
    def test_p_icon_hid_linking(self):
        """Verify that setting 'p' in HID per-key mode links to 'p_icon' (offset 181)."""
        kb = OmenKeyboard.__new__(OmenKeyboard)
        kb.key_map = {
            "row_2": {"p": {"offset": 85, "width": 1}},
            "special": {"p_icon": {"offset": 181, "width": 1}}
        }
        kb.backend = "hid_perkey"
        kb.channels = {0x05: bytearray(186), 0x06: bytearray(186), 0x07: bytearray(186)}
        kb.set_key_color("p", 255, 128, 64)
        self.assertEqual(kb.channels[0x05][85], 255)
        self.assertEqual(kb.channels[0x06][85], 128)
        self.assertEqual(kb.channels[0x07][85], 64)
        self.assertEqual(kb.channels[0x05][181], 255)
        self.assertEqual(kb.channels[0x06][181], 128)
        self.assertEqual(kb.channels[0x07][181], 64)

    def test_init_hid_compatibility(self):
        """Verify _init_hid initializes with both hidapi (hid.device) and hid (hid.Device)."""
        from unittest.mock import MagicMock
        kb = OmenKeyboard.__new__(OmenKeyboard)
        kb.VID = 0x0d62
        kb.PID = 0x54bf

        # Mock hid module with hidapi device()
        mock_hidapi = MagicMock()
        del mock_hidapi.Device
        mock_hidapi.enumerate.return_value = [{'path': b'3-9:1.3', 'interface_number': 3}]
        with patch.dict("sys.modules", {"hid": mock_hidapi}):
            kb._init_hid()
            mock_hidapi.device().open_path.assert_called_with(b'3-9:1.3')

        # Mock hid module with ctypes Device()
        mock_hid = MagicMock()
        del mock_hid.device
        mock_hid.enumerate.return_value = [{'path': b'3-9:1.3', 'interface_number': 3}]
        with patch.dict("sys.modules", {"hid": mock_hid}):
            kb._init_hid()
            mock_hid.Device.assert_called_with(path=b'3-9:1.3')

    def test_p_gui_single_key(self):
        """Verify GUI treats 'p' as a single key without needing p_icon in session_state."""
        from omen_rgb.gui import OmenGUI
        import threading

        gui = OmenGUI.__new__(OmenGUI)
        gui.state_lock = threading.Lock()
        gui.selected_keys = {"p"}
        gui.lightbar_keys = []
        gui.key_items = {"p": (1, 2)}  # Only 'p', not split into p_icon
        gui.has_lightbar = False
        gui.session_state = {"p": (0, 0, 0)}
        gui.rainbow_thread = None
        gui._schedule_hardware_write = lambda do_kb, do_lb: None
        gui._schedule_state_save = lambda: None
        gui.update_key_visuals = lambda: None

        kb = OmenKeyboard.__new__(OmenKeyboard)
        kb.key_map = {
            "row_2": {"p": {"offset": 85, "width": 1}},
            "special": {"p_icon": {"offset": 181, "width": 1}}
        }
        kb.backend = "hid_perkey"
        kb.channels = {0x05: bytearray(186), 0x06: bytearray(186), 0x07: bytearray(186)}
        gui.kb = kb

        gui.apply_custom_color(200, 100, 50)
        self.assertEqual(gui.session_state["p"], (200, 100, 50))
        self.assertNotIn("p_icon", gui.session_state)
        self.assertEqual(kb.channels[0x05][85], 200)
        self.assertEqual(kb.channels[0x05][181], 200)

    def test_animation_dialog_static_and_effects(self):
        """Verify AnimationDialog contains Static, MCU effects, and Lightbar animations."""
        import tkinter as tk
        from unittest.mock import MagicMock
        from omen_rgb.gui import AnimationDialog

        root = tk.Tk()
        root.withdraw()

        gui = MagicMock()
        gui.kb = MagicMock()
        gui.kb.is_per_key = True
        gui.kb.is_simulation = False
        gui.lb = MagicMock()
        gui.has_lightbar = True
        gui.rainbow_thread = None
        gui.selected_keys = {"w", "a", "s", "d"}
        gui.session_state = {"w": (255, 0, 0), "a": (255, 0, 0), "s": (255, 0, 0), "d": (255, 0, 0)}

        dlg = AnimationDialog(root, gui)
        self.assertTrue(len(dlg.items) > 10)
        self.assertEqual(dlg.items[0]["id"], "static")

        # 1. Apply static
        dlg.do_apply()
        gui._flush_hardware_writes.assert_called_with(do_kb=True, do_lb=True)

        # 2. Apply MCU wave effect
        wave_idx = [i for i, item in enumerate(dlg.items) if item["id"] == "wave"][0]
        dlg.listbox.selection_clear(0, tk.END)
        dlg.listbox.selection_set(wave_idx)
        dlg.on_select(None)
        dlg.do_apply()
        self.assertTrue(gui.kb.set_effect.called)

        # 3. Apply Lightbar wave animation
        lb_wave_idx = [i for i, item in enumerate(dlg.items) if item["type"] == "lightbar" and item["id"] == "wave"][0]
        dlg.listbox.selection_clear(0, tk.END)
        dlg.listbox.selection_set(lb_wave_idx)
        dlg.on_select(None)
        dlg.do_apply()
        self.assertTrue(gui.lb.set_animation.called)

        dlg.destroy()
        root.destroy()

    def test_simulate_4zone_flag(self):
        """Verify 4-zone simulation mode can be activated via parameter or env var."""
        # 1. Via constructor parameter
        kb = OmenKeyboard(simulate_4zone=True)
        self.assertTrue(kb.simulate_4zone)
        self.assertTrue(kb.is_4zone)
        self.assertFalse(kb.is_per_key)
        self.assertEqual(len(kb.zone_names), 4)
        colors = kb.get_zone_colors()
        self.assertIn("wasd", colors)
        self.assertIn("left", colors)
        self.assertIn("center", colors)
        self.assertIn("right", colors)

        # 2. In-memory color and brightness manipulation
        kb.set_zone("wasd", 42, 84, 126, brightness=50)
        self.assertEqual(kb.zone_colors["wasd"], (42, 84, 126))
        self.assertEqual(kb.get_zone_brightness("wasd"), 50)

        # 3. Via environment variable
        old_env = os.environ.get("OMEN_SIMULATE_4ZONE")
        try:
            os.environ["OMEN_SIMULATE_4ZONE"] = "1"
            kb_env = OmenKeyboard()
            self.assertTrue(kb_env.simulate_4zone)
            self.assertTrue(kb_env.is_4zone)
        finally:
            if old_env is None:
                os.environ.pop("OMEN_SIMULATE_4ZONE", None)
            else:
                os.environ["OMEN_SIMULATE_4ZONE"] = old_env

    def test_simulate_4zone_no_writes(self):
        """Verify apply() and flush do not attempt to write to sysfs or filesystem."""
        kb = OmenKeyboard(simulate_4zone=True)
        # Point to a path that would fail if written to
        kb.zone_paths = {"wasd": "/dev/null/forbidden_path/does_not_exist"}
        # apply() must return cleanly without raising any error or attempting to write
        kb.apply()


class TestKeyboardTypeAndNumpad(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_sysfs_file = os.path.join(self.temp_dir.name, "keyboard_type")
        self.patcher = patch.object(driver, "SYSFS_KEYBOARD_TYPE_FILE", self.mock_sysfs_file)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_keyboard_type_reading(self):
        # 1. File does not exist -> None
        self.assertIsNone(OmenKeyboard.get_keyboard_type())

        # 2. File exists with ID 1 (4-Zone with numpad)
        with open(self.mock_sysfs_file, "w") as f:
            f.write("1\n")
        self.assertEqual(OmenKeyboard.get_keyboard_type(), 1)
        kb = OmenKeyboard(simulate_4zone=True)
        self.assertEqual(kb.keyboard_type, 1)
        self.assertEqual(kb.keyboard_type_name, "4-Zone with Numpad")
        self.assertTrue(kb.has_numpad)

        # 3. ID 2 (4-Zone without numpad)
        with open(self.mock_sysfs_file, "w") as f:
            f.write("2\n")
        self.assertEqual(kb.keyboard_type, 2)
        self.assertEqual(kb.keyboard_type_name, "4-Zone without Numpad")
        self.assertFalse(kb.has_numpad)

        # 4. ID 4 (Single-Zone with numpad)
        with open(self.mock_sysfs_file, "w") as f:
            f.write("4\n")
        self.assertEqual(kb.keyboard_type, 4)
        self.assertTrue(kb.has_numpad)

        # 5. ID 5 (Single-Zone without numpad)
        with open(self.mock_sysfs_file, "w") as f:
            f.write("5\n")
        self.assertEqual(kb.keyboard_type, 5)
        self.assertFalse(kb.has_numpad)

        # 6. Explicit override takes precedence
        kb_override = OmenKeyboard(simulate_4zone=True, has_numpad=True)
        self.assertTrue(kb_override.has_numpad)
        kb_override_no = OmenKeyboard(simulate_4zone=True, has_numpad=False)
        self.assertFalse(kb_override_no.has_numpad)


class TestOmenKeyboardSimulate1Zone(unittest.TestCase):
    def test_initialization_and_backend(self):
        kb = OmenKeyboard(simulate_1zone=True)
        self.assertTrue(kb.simulate_1zone)
        self.assertTrue(kb.is_simulation)
        self.assertTrue(kb.is_single_zone)
        self.assertFalse(kb.is_4zone)
        self.assertFalse(kb.is_per_key)
        self.assertEqual(kb.backend, "sysfs_1zone")
        self.assertEqual(kb.zone_names, ["backlight"])
        self.assertIn("backlight", kb.zone_paths)

    def test_zone_colors_and_brightness(self):
        kb = OmenKeyboard(simulate_1zone=True)
        self.assertEqual(kb.get_zone_colors(), {"backlight": (255, 120, 0)})
        self.assertEqual(kb.get_zone_brightness("backlight"), 100)

        kb.set_zone("backlight", 0, 255, 128, brightness=50)
        self.assertEqual(kb.get_zone_colors(), {"backlight": (0, 255, 128)})
        self.assertEqual(kb.get_zone_brightness("backlight"), 50)

    def test_set_all_and_key_color(self):
        kb = OmenKeyboard(simulate_1zone=True)
        kb.set_all(10, 20, 30)
        self.assertEqual(kb.get_zone_colors(), {"backlight": (10, 20, 30)})

        colors = kb.get_colors()
        self.assertIn("space", colors)
        self.assertEqual(colors["space"], (10, 20, 30))

        kb.set_key_color("esc", 200, 100, 50)
        self.assertEqual(kb.get_zone_colors(), {"backlight": (200, 100, 50)})

    def test_apply_is_noop(self):
        kb = OmenKeyboard(simulate_1zone=True)
        # Should not raise any error or touch files
        kb.set_zone("backlight", 255, 0, 0)
        kb.apply()

    def test_env_var_activation(self):
        with patch.dict(os.environ, {"OMEN_SIMULATE_1ZONE": "1"}):
            kb = OmenKeyboard()
            self.assertTrue(kb.simulate_1zone)
            self.assertTrue(kb.is_single_zone)


if __name__ == "__main__":
    unittest.main()



