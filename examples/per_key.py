#!/usr/bin/env python3
"""
Example: Per-Key RGB Keyboard Control (HP Gaming Keyboard II / USB ID 0d62:54bf)
Targets HP OMEN laptops with per-key addressable RGB (e.g. OMEN Max 16).

Usage:
    sudo python3 examples/per_key.py
"""

import sys
import os
import time

# Allow running directly from repository clone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from omen_rgb import OmenKeyboard


def main():
    try:
        # Initialize the keyboard interface
        kb = OmenKeyboard()
    except RuntimeError as e:
        print(f"Initialization Error: {e}", file=sys.stderr)
        print("Ensure your per-key keyboard is connected and you run with sudo.", file=sys.stderr)
        sys.exit(1)

    print(f"Connected to backend: {kb.backend}")
    if not kb.is_per_key:
        print("Notice: Connected device is not a per-key USB keyboard (backend:", kb.backend, ")")

    try:
        # 1. Turn off all lights first
        print("Clearing all keyboard lights...")
        kb.set_all(0, 0, 0)
        kb.apply()
        time.sleep(0.3)

        # 2. Highlight WASD cluster in Red
        print("Highlighting WASD cluster in Red...")
        for key in ["w", "a", "s", "d"]:
            kb.set_key_color(key, 255, 0, 0)

        # 3. Highlight ESC in Green
        print("Setting ESC to Green...")
        kb.set_key_color("esc", 0, 255, 0)

        # 4. Highlight Spacebar in Blue
        print("Setting Spacebar to Blue...")
        kb.set_key_color("space", 0, 0, 255)

        # 5. Highlight Arrow Keys in Yellow
        print("Setting Arrow keys to Yellow...")
        for key in ["up", "down", "left", "right"]:
            kb.set_key_color(key, 255, 200, 0)

        # 6. Set 'P' key (automatically synchronizes both letter 'P' and the 'p_icon' LED)
        print("Setting 'P' key to Cyan (syncs both letter and logo LED)...")
        kb.set_key_color("p", 0, 255, 255)

        # 7. Write changes to keyboard hardware
        kb.apply()
        print("Lighting applied successfully.")

    finally:
        # Cleanly release the HID USB connection
        kb.close()


if __name__ == "__main__":
    main()
