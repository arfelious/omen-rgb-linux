#!/usr/bin/env python3
"""
Example: 4-Zone RGB Keyboard Control (hp-wmi Linux Multicolor LED subsystem)
Targets HP OMEN 4-zone laptops (requires omen-fan-control kernel driver).

Zone Mapping:
  - "wasd"   (Zone 3): W, A, S, D cluster
  - "left"   (Zone 2): Left cluster (Esc, Tab, Caps, LShift, Q, E, R, etc.)
  - "center" (Zone 1): Center cluster (T through P, G through L, B through /, etc.)
  - "right"  (Zone 0): Right cluster (Delete, Arrows, Numpad)

Usage:
    sudo python3 examples/four_zone.py
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

    if not kb.is_4zone:
        print(f"Notice: Device backend is '{kb.backend}', not 4-zone.")

    # 1. Query current live zone colors and brightness from sysfs
    print("\nReading active zone status:")
    live_colors = kb.get_zone_colors()
    for zn in ["right", "center", "left", "wasd"]:
        c = live_colors.get(zn, (0, 0, 0)) if live_colors else (0, 0, 0)
        b = kb.get_zone_brightness(zn)
        print(f"  Zone '{zn}': RGB{c}, Brightness={b}%")

    # 2. Set distinct colors for individual zones (OCC color palette)
    print("\nSetting zone colors:")
    print("  - WASD   -> Yellow RGB(255, 200, 0)")
    kb.set_zone("wasd", 255, 200, 0, brightness=100)

    print("  - Left   -> Red    RGB(255, 0, 50)")
    kb.set_zone("left", 255, 0, 50, brightness=100)

    print("  - Center -> Purple RGB(180, 0, 255)")
    kb.set_zone("center", 180, 0, 255, brightness=100)

    print("  - Right  -> Blue   RGB(0, 150, 255)")
    kb.set_zone("right", 0, 150, 255, brightness=100)

    # 3. Commit changes to sysfs / hardware
    kb.apply()
    print("Zone colors applied successfully.")

    # 4. Alternatively: Set all 4 zones in one call
    time.sleep(1)
    print("\nSetting all zones simultaneously via set_zones()...")
    kb.set_zones({
        "wasd": (0, 255, 255),    # Cyan
        "left": (0, 255, 128),    # Mint
        "center": (0, 128, 255),  # Sky blue
        "right": (0, 0, 255),     # Deep blue
    }, brightness=90)
    kb.apply()
    print("All zones updated.")

    # 5. Key-to-zone routing:
    # On 4-zone keyboards, set_key_color automatically maps keys to their zone:
    print("\nSetting 'w' key to orange (updates the WASD zone containing 'w')...")
    kb.set_key_color("w", 255, 128, 0)
    kb.apply()
    print("Done.")


if __name__ == "__main__":
    main()
