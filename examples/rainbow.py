#!/usr/bin/env python3
"""
Example: Rainbow Wave Animation
Adapts automatically to the detected hardware:
  - Per-Key RGB keyboards: Waves across each key individually
  - 4-Zone keyboards: Waves across the 4 zones (Left -> WASD -> Center -> Right)
  - Single-Zone keyboards: Cycles backlight color smoothly through the rainbow spectrum
  - Lightbar (if present): Synchronizes bottom light strip animation

Usage:
    sudo python3 examples/rainbow.py
"""

import sys
import os
import time
import colorsys

# Allow running directly from repository clone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from omen_rgb import OmenKeyboard, OmenLightbar


def main():
    try:
        kb = OmenKeyboard()
    except RuntimeError as e:
        print(f"Initialization Error: {e}", file=sys.stderr)
        print("Ensure you run with sudo and appropriate drivers are installed.", file=sys.stderr)
        sys.exit(1)

    lb = None
    if OmenLightbar.is_supported():
        try:
            lb = OmenLightbar()
        except Exception:
            lb = None

    print(f"Connected to keyboard: {kb.backend}")
    if lb:
        print(f"Connected to lightbar: {lb.backend}")
    print("Press Ctrl+C to stop rainbow animation.\n")

    hue = 0.0
    try:
        if kb.is_4zone:
            # 4-zone wave: Left -> WASD -> Center -> Right
            zone_offsets = {"left": 0.0, "wasd": 0.15, "center": 0.35, "right": 0.6}
            while True:
                for zn, offset in zone_offsets.items():
                    zhue = (hue + offset) % 1.0
                    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(zhue, 1.0, 1.0)]
                    kb.set_zone(zn, r, g, b)
                kb.apply()

                if lb and lb.is_available():
                    lb_colors = [
                        [int(c * 255) for c in colorsys.hsv_to_rgb((hue + zi * 0.25) % 1.0, 1.0, 1.0)]
                        for zi in range(4)
                    ]
                    lb.set_colors(lb_colors)

                hue = (hue + 0.02) % 1.0
                time.sleep(0.04)

        elif kb.is_single_zone:
            # Single-zone: cycle backlight hue smoothly
            while True:
                r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
                kb.set_all(r, g, b)
                kb.apply()

                if lb and lb.is_available():
                    lb_colors = [
                        [int(c * 255) for c in colorsys.hsv_to_rgb((hue + zi * 0.25) % 1.0, 1.0, 1.0)]
                        for zi in range(4)
                    ]
                    lb.set_colors(lb_colors)

                hue = (hue + 0.01) % 1.0
                time.sleep(0.03)

        elif kb.is_per_key:
            # Per-key: wave across each key
            keys = {}
            for category in kb.key_map.values():
                keys.update(category)
            sorted_keys = sorted(keys.keys(), key=lambda k: keys[k]["offset"])
            num_keys = len(sorted_keys)

            while True:
                for i, name in enumerate(sorted_keys):
                    khue = (hue + (i / num_keys)) % 1.0
                    r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb(khue, 1.0, 1.0)]
                    kb.set_key_color(name, r, g, b)
                kb.apply()

                if lb and lb.is_available():
                    lb_colors = [
                        [int(c * 255) for c in colorsys.hsv_to_rgb((hue + zi * 0.25) % 1.0, 1.0, 1.0)]
                        for zi in range(4)
                    ]
                    lb.set_colors(lb_colors)

                hue = (hue + 0.03) % 1.0
                time.sleep(0.03)

    except KeyboardInterrupt:
        print("\nStopping rainbow animation...")
    finally:
        # Turn off or clear before exit
        kb.set_all(0, 0, 0)
        kb.apply()
        if lb and lb.is_available():
            lb.turn_off()
        kb.close()
        print("Lights turned off.")


if __name__ == "__main__":
    main()
