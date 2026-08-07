#!/usr/bin/env python3
"""
Hardware-rendered effects: one report each, no host loop.

The MCU owns twelve animations. Selecting one is a single 64-byte report; the animation then
runs with this process exited and nothing maintaining it. Compare examples/rainbow.py, which
redraws nine reports every 20 ms to do less.

    sudo python3 examples/effects.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from driver import OmenKeyboard
from effects import EffectSetting


def main():
    kb = OmenKeyboard()
    try:
        # What is installed right now. This is a real state read - the MCU returns its stored
        # record - but it is the *merged* record, and it says nothing about what is lit.
        before = kb.get_effect()
        print("current:", before and before["raw"].hex())

        # 1. HP's own defaults for an effect: name it and nothing else.
        kb.set_effect("ghosting")
        time.sleep(4)

        # 2. Custom colours. ShowMode and ColorNumber are derived from the list you pass.
        kb.set_effect(EffectSetting(
            "wave",
            colors=[(0xFA, 0xAC, 0x0F), (0x0F, 0xFA, 0x36), (0xEA, 0x00, 0x2A), (0xFA, 0x0F, 0xE7)],
            speed="fast",
            direction="left-to-right",
        ))
        time.sleep(4)

        # 3. A firmware palette instead of custom colours.
        kb.set_effect(EffectSetting("ripple", show_mode="ocean", ripple_size="large"))
        time.sleep(4)

        # 4. Audio Pulse is host-fed: the two levels ARE the animation. Feed it at ~5 Hz with
        #    your own band levels; at 0/0 it renders black.
        for i in range(25):
            level = int(120 + 80 * ((i % 10) / 10.0))
            kb.set_effect(EffectSetting("audio-pulse",
                                        inner_brightness=level, outer_brightness=255 - level))
            time.sleep(0.2)

        # Warnings are advisory - the firmware is the authority, not this table.
        bad = EffectSetting("swipe", show_mode="volcano")
        print("\n".join(bad.warnings()))

        after = kb.get_effect()
        if after:
            print("installed:", after["effect"], after["show_mode"], after["colors"])

        # Nothing above wrote flash. Persist deliberately, once, if you want it to survive a
        # reboot:
        #     kb.set_effect("wave", persist=True)
    finally:
        kb.close()


if __name__ == "__main__":
    main()
