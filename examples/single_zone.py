#!/usr/bin/env python3
"""
Example: Single-Zone RGB Keyboard Control (hp-wmi Linux Multicolor LED subsystem)
Targets HP Victus and single-zone RGB laptops (requires omen-fan-control kernel driver).

Sysfs Node:
  - /sys/class/leds/hp::kbd_backlight/multi_intensity
  - /sys/class/leds/hp::kbd_backlight/brightness

Usage:
    sudo python3 examples/single_zone.py
"""

import sys
import os
import time

# Allow running directly from repository clone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from omen_rgb import OmenKeyboard


def main():
    try:
        kb = OmenKeyboard()
    except RuntimeError as e:
        print(f"Initialization Error: {e}", file=sys.stderr)
        print("Ensure omen-fan-control driver is installed and you run with sudo.", file=sys.stderr)
        sys.exit(1)

    print(f"Keyboard Backend: {kb.backend}")
    if kb.keyboard_type is not None:
        print(f"Detected Hardware Type: {kb.keyboard_type} ({kb.keyboard_type_name})")
    print(f"Numeric Keypad Present: {kb.has_numpad}")

    if not kb.is_single_zone:
        print(f"Notice: Device backend is '{kb.backend}', not single-zone.")

    # 1. Query active backlight color and brightness from sysfs
    print("\nReading active backlight status:")
    colors = kb.get_zone_colors()
    c = colors.get("backlight", (0, 0, 0)) if colors else (0, 0, 0)
    b = kb.get_zone_brightness("backlight")
    print(f"  Backlight Color: RGB{c}, Brightness={b}%")

    # 2. Set static color and brightness (Amber / Orange)
    print("\nSetting single-zone backlight to Amber (255, 120, 0) at 80% brightness...")
    kb.set_zone("backlight", 255, 120, 0, brightness=80)
    kb.apply()
    print("Backlight color applied.")

    time.sleep(1.5)

    # 3. Change color using set_all() (Cyan)
    print("Changing backlight to Cyan (0, 255, 255)...")
    kb.set_all(0, 255, 255)
    kb.apply()
    print("Backlight updated.")

    time.sleep(1.5)

    # 4. Turn off
    print("Turning off keyboard backlight...")
    kb.set_all(0, 0, 0)
    kb.apply()
    print("Backlight turned off.")


if __name__ == "__main__":
    main()
