#!/usr/bin/env python3
"""
Example: Bottom Lightbar Control
Targets HP OMEN laptops with 4-zone addressable bottom lightbar (e.g. OMEN MAX).
Requires omen-fan-control kernel driver.

Usage:
    sudo python3 examples/lightbar.py
"""

import sys
import os
import time

# Allow running directly from repository clone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from omen_rgb import OmenLightbar


def main():
    if not OmenLightbar.is_supported():
        print("Notice: Bottom lightbar is not supported or detected on this hardware.")
        print("Ensure omen-fan-control is installed and you run with sudo.")
        sys.exit(1)

    lb = OmenLightbar()
    print(f"Connected to Lightbar backend: {lb.backend}")

    # 1. Query current active hardware status
    b = lb.get_brightness()
    colors = lb.get_colors()
    print(f"Active Brightness: {b if b is not None else 'unknown'}%")
    if colors:
        print("Active Zone Colors:")
        for i, c in enumerate(colors, 1):
            print(f"  Zone {i}: RGB{c}")

    # 2. Set static solid color across all 4 zones (Warm Orange at 100% brightness)
    print("\nSetting static Orange (255, 120, 0) across all 4 zones...")
    lb.set_static(255, 120, 0, brightness=100)
    time.sleep(2)

    # 3. Set distinct colors for each of the 4 zones
    print("Setting 4 distinct zone colors (Red, Green, Blue, Yellow)...")
    lb.set_colors([
        (255, 0, 0),    # Zone 1: Red
        (0, 255, 0),    # Zone 2: Green
        (0, 0, 255),    # Zone 3: Blue
        (255, 255, 0),  # Zone 4: Yellow
    ], brightness=90)
    time.sleep(2)

    # 4. Turn off lightbar
    print("Turning off bottom lightbar...")
    lb.turn_off()
    print("Done.")


if __name__ == "__main__":
    main()
