#!/usr/bin/env python3
"""
Check the bytes this driver puts on the wire against the bytes OMEN Gaming Hub puts on the wire.

No hardware, no dependencies, no test framework:

    python3 tests/test_frames.py

The reference frames below are transcribed from a USB capture of OGH driving an
HP Gaming Keyboard II (0d62:54bf) on an OMEN MAX 16, board 8D87. They are the only external
authority this project has for the effect protocol, so a change that breaks one of these is a
change that has stopped matching HP's client.
"""

import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


# --------------------------------------------------------------------------------------
# A fake hidapi that records what would have been written
# --------------------------------------------------------------------------------------

class FakeDevice:
    def __init__(self, *a, **kw):
        self.writes = []
        self.replies = []

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def read(self, size, timeout=None):
        return self.replies.pop(0) if self.replies else b""

    def close(self):
        pass


_fake_hid = types.ModuleType("hid")
_fake_hid.Device = FakeDevice
_fake_hid.enumerate = lambda vid=0, pid=0: [{"interface_number": 3, "path": b"fake"}]
sys.modules["hid"] = _fake_hid

import effects as fx                      # noqa: E402
from driver import OmenKeyboard           # noqa: E402
from lightbar import OmenLightbar, LB_ANIMATIONS   # noqa: E402


FAILURES = []


def check(name, expected, actual):
    if expected == actual:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}")
        print(f"          expected {expected!r}")
        print(f"          actual   {actual!r}")
        FAILURES.append(name)


def record(head, colors_hex=""):
    """Build a 36-byte effect record from its leading fields and colour block."""
    body = bytes(head) + bytes(fx.FX_COLOR_0 - len(head)) + bytes.fromhex(colors_hex)
    return body + bytes(fx.RECORD_LENGTH - len(body))


# --------------------------------------------------------------------------------------
# The captured effect frames
# --------------------------------------------------------------------------------------
#
# Fields in order: Effect, ShowMode, ColorNumber, LedSpeed, Brightness, Direction, RippleSize,
# RaindropFrequency, InnerBrightness, OuterBrightness.

def test_captured_effect_records():
    print("effect records match the OGH capture")

    # Wave, four custom colours (yellow, green, red, purple), fast, left-to-right.
    # The person driving OGH described this as "a wave effect with four colors, Yellow, green,
    # red, and purple" before the frame was decoded.
    check(
        "capture frame [0] - Wave, 4 custom colours",
        record([0x0A, 0x01, 0x03, 0x02, 0x00, 0x03, 0x01, 0x02, 0x00, 0x00],
               "faac0f0ffa36ea002afa0fe7"),
        fx.EffectSetting(
            "wave", show_mode="multi", speed="fast", direction="left-to-right",
            colors=[(0xFA, 0xAC, 0x0F), (0x0F, 0xFA, 0x36),
                    (0xEA, 0x00, 0x2A), (0xFA, 0x0F, 0xE7)],
        ).to_bytes(),
    )

    # Wave on the Rainbow preset. ColorNumber 4 is the "a preset is in use" sentinel and OGH
    # leaves the colour block zeroed.
    check(
        "capture frame [1] - Wave, Rainbow preset",
        record([0x0A, 0x05, 0x04, 0x02, 0x00, 0x03, 0x01, 0x02, 0x00, 0x00]),
        fx.EffectSetting("wave", show_mode="rainbow", speed="fast").to_bytes(),
    )

    # Wave on Jungle. The session ended here and the person reported "ended on Wave, jungle
    # color scheme".
    check(
        "capture frame [3] - Wave, Jungle preset",
        record([0x0A, 0x03, 0x04, 0x02, 0x00, 0x03, 0x01, 0x02, 0x00, 0x00]),
        fx.EffectSetting("wave", show_mode="jungle", speed="fast").to_bytes(),
    )


def test_effect_readback_decode():
    print("0x83 readback decodes to what the keyboard was showing")

    # The first 0x83 read ever taken on this board: 08 03 04 01 A0 03 01 01. Decoded to
    # "Ghosting, Jungle" BEFORE anyone was asked what the keyboard looked like; the person at it
    # then said "Ghosting in greens", unprompted.
    reply = record([0x08, 0x03, 0x04, 0x01, 0xA0, 0x03, 0x01, 0x01, 0x00, 0x00])
    d = fx.parse_record(reply)
    check("effect", "ghosting", d["effect"])
    check("show mode", "jungle", d["show_mode"])
    check("colour count", "preset", d["color_number"])
    check("speed", "medium", d["speed"])
    check("brightness", 160, d["brightness"])


def test_effect_numbering():
    print("effect numbering is HP's EffectCommandTable, not the identity")
    check("UI order -> wire",
          [4, 7, 2, 8, 9, 10, 13, 12, 14, 15, 16, 17],
          list(fx.EFFECTS.values()))
    check("record length is 36 for every effect",
          {36},
          {len(fx.EffectSetting(n).to_bytes()) for n in fx.EFFECTS})


def test_black_screen_warnings():
    print("the two effects that render black are warned about")
    swipe = fx.EffectSetting("swipe", show_mode="volcano").warnings()
    check("swipe on a preset warns", True, any("BLACK" in w for w in swipe))
    pulse = fx.EffectSetting("audio-pulse", inner_brightness=0, outer_brightness=0).warnings()
    check("audio-pulse at level 0 warns", True, any("BLACK" in w for w in pulse))
    check("swipe with colours is quiet",
          [], fx.EffectSetting("swipe", colors=[(255, 0, 0), (0, 0, 255)]).warnings())


# --------------------------------------------------------------------------------------
# Transport
# --------------------------------------------------------------------------------------

def test_frame_header():
    print("frames carry the four-byte header the MCU expects")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"))
    dev = kb.device

    kb.set_effect(fx.EffectSetting("wave", show_mode="jungle", speed="fast"))
    # set_effect opens with 0x09 (lighting on) exactly as OGH does, then sends the record.
    check("frame count", 2, len(dev.writes))
    check("lighting-on frame",
          bytes.fromhex("09000100" + "01") + bytes(59),
          dev.writes[0])
    check("effect header", bytes.fromhex("03002400"), dev.writes[1][:4])
    check("effect record",
          record([0x0A, 0x03, 0x04, 0x02, 0x00, 0x03, 0x01, 0x02, 0x00, 0x00]),
          dev.writes[1][4:40])
    check("report is 64 bytes", 64, len(dev.writes[1]))

    dev.writes.clear()
    kb.store_to_flash()
    check("flash write is 0a 00 02 00 ac 53",
          bytes.fromhex("0a000200ac53") + bytes(58),
          dev.writes[0])
    check("flash write is sent twice", 2, len(dev.writes))

    dev.writes.clear()
    kb.restore_lighting_defaults()
    check("restore-defaults frame",
          bytes.fromhex("10070400" + "94109827") + bytes(56),
          dev.writes[0])

    dev.writes.clear()
    kb.get_effect()
    check("0x83 read frame", bytes.fromhex("83000000") + bytes(60), dev.writes[0])
    kb.close()


def test_apply_persist():
    print("apply(persist=False) sends the colour pages and no flash write")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"))
    dev = kb.device

    kb.set_all(0x11, 0x22, 0x33)
    kb.apply(persist=False)
    check("nine colour pages, no flash", 9, len(dev.writes))
    check("page commands", [5, 5, 5, 6, 6, 6, 7, 7, 7], [w[0] for w in dev.writes])
    check("page indices", [0, 1, 2, 0, 1, 2, 0, 1, 2], [w[1] for w in dev.writes])
    # BLength is 0 on a colour page - HP's own client writes that zero as a literal.
    check("BLength is zero on every page", {(0, 0)}, {(w[2], w[3]) for w in dev.writes})
    check("60 colour bytes per page", {60}, {len(w[4:]) for w in dev.writes})
    check("red page carries 0x11", bytes([0x11] * 60), dev.writes[0][4:])

    dev.writes.clear()
    kb.apply()
    check("default still persists", 11, len(dev.writes))
    check("last two frames are the flash write",
          [0x0a, 0x0a], [w[0] for w in dev.writes[-2:]])
    kb.close()


def test_apply_layout_unchanged():
    print("apply() still produces exactly the bytes it did before this change")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"))
    dev = kb.device
    kb.set_all(0xAB, 0xCD, 0xEF)
    kb.apply()

    # Reconstruct the pre-existing implementation and compare frame for frame.
    legacy = []
    for channel_id in (0x05, 0x06, 0x07):
        data = kb.channels[channel_id]
        for chunk_idx in range(3):
            report = bytearray(64)
            report[0] = channel_id
            report[1] = chunk_idx
            report[2:64] = data[chunk_idx * 62:(chunk_idx + 1) * 62]
            legacy.append(bytes(report))
    commit = bytearray(64)
    commit[0], commit[1], commit[2], commit[4], commit[5] = 0x0a, 0x00, 0x02, 0xac, 0x53
    legacy += [bytes(commit), bytes(commit)]

    check("byte-identical to the previous apply()", legacy, dev.writes)
    kb.close()


# --------------------------------------------------------------------------------------
# Light bar
# --------------------------------------------------------------------------------------

def lb_payload(hex_arg):
    """Strip acpi_call's 'b' prefix and the 16-byte SECU header."""
    return bytes.fromhex(hex_arg[1:])[16:]


def test_lightbar_static_unchanged():
    print("the light bar's static payload is unchanged")
    lb = OmenLightbar.__new__(OmenLightbar)
    d = lb_payload(lb._build_payload([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]))
    check("header bytes [0..6]", bytes.fromhex("00000064000004"), d[:7])
    check("zones [7..18]", bytes.fromhex("ff000000ff000000ffffff00"), d[7:19])


def test_lightbar_animation():
    print("light bar animations pack byte [2] correctly")
    lb = OmenLightbar.__new__(OmenLightbar)
    cfg = lb._pack_config(speed="fast", direction="right", theme="custom")
    check("fast|right|custom = 2|8|80", 0x5A, cfg)

    d = lb_payload(lb._build_payload(
        [(255, 0, 0), (0, 0, 255), (0, 0, 0), (0, 0, 0)], 100,
        effect=LB_ANIMATIONS["swipe"], config=cfg))
    check("effect byte [1] is Swipe", 11, d[1])
    check("config byte [2]", 0x5A, d[2])
    check("brightness byte [3]", 100, d[3])
    check("zone count byte [6]", 4, d[6])

    d = lb_payload(lb._build_payload([(0, 0, 255)] * 4, 100, effect=8, tribe=100, bass=100))
    check("audio levels land in [4],[5]", (100, 100), (d[4], d[5]))


def test_lightbar_white():
    print("#FFFFFF is rewritten so that white is white")
    lb = OmenLightbar.__new__(OmenLightbar)
    d = lb_payload(lb._build_payload([(255, 255, 255)] * 4))
    check("FFFFFF -> FFFFFE", bytes.fromhex("fffffe" * 4), d[7:19])

    lb.AVOID_FIRMWARE_WHITE = False
    d = lb_payload(lb._build_payload([(255, 255, 255)] * 4))
    check("opt out sends it verbatim", bytes.fromhex("ffffff" * 4), d[7:19])

    lb.AVOID_FIRMWARE_WHITE = True
    d = lb_payload(lb._build_payload([(255, 0, 0), (255, 0, 1)] + [(0, 0, 0)] * 2))
    check("FF0000 is left alone - the substitution is invisible",
          bytes.fromhex("ff0000ff0001"), d[7:13])


if __name__ == "__main__":
    for test in (
        test_captured_effect_records,
        test_effect_readback_decode,
        test_effect_numbering,
        test_black_screen_warnings,
        test_frame_header,
        test_apply_persist,
        test_apply_layout_unchanged,
        test_lightbar_static_unchanged,
        test_lightbar_animation,
        test_lightbar_white,
    ):
        test()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed: {', '.join(FAILURES)}")
        sys.exit(1)
    print("All checks passed.")
    print()
    print("This proves the frames are right. It does not prove anything lit - on this "
          "interface\nan acknowledged frame and a dark keyboard have been observed together.")
