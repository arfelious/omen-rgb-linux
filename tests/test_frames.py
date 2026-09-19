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

try:
    from omen_rgb import effects as fx                      # noqa: E402
    from omen_rgb import layouts as kbl                     # noqa: E402
    from omen_rgb.driver import OmenKeyboard                # noqa: E402
    from omen_rgb.lightbar import OmenLightbar, LB_ANIMATIONS   # noqa: E402
except ImportError:
    import effects as fx                      # noqa: E402
    import layouts as kbl                     # noqa: E402
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


def test_colour_map_positions():
    print("the colour map is addressed by LED position, not by buffer offset")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"))

    # The two BLength bytes at the head of each page are not map positions, so position 60 is
    # buffer offset 64. Getting this wrong is invisible until a key straddles a page.
    check("position 0 -> offset 2", 2, kb._offset(0))
    check("position 59 -> offset 61", 61, kb._offset(59))
    check("position 60 -> offset 64", 64, kb._offset(60))
    check("position 120 -> offset 126", 126, kb._offset(120))
    check("position 179 -> offset 185", 185, kb._offset(179))
    check("180 is off the end", None, kb._offset(180))

    # Backspace is positions 58..63, which crosses the page-0/page-1 boundary. Written as one
    # run of buffer offsets it lands on the BLength bytes and declares a length on a page that
    # must declare zero.
    check("backspace owns six LEDs across a page boundary", [58, 59, 60, 61, 62, 63],
          kb.key_leds("backspace"))

    kb.set_all(0, 0, 0)
    kb.set_key_color("backspace", 0xFF, 0xFF, 0xFF)
    kb.device.writes.clear()
    kb.apply(persist=False)
    check("BLength stays zero on every page with backspace lit",
          {(0, 0)}, {(w[2], w[3]) for w in kb.device.writes})

    red = b"".join(w[4:] for w in kb.device.writes[:3])
    check("and exactly those six positions are lit",
          [58, 59, 60, 61, 62, 63], [i for i, v in enumerate(red) if v])
    kb.close()


def test_live_positions():
    print("176 positions light up; the four transmitted after them are padding")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"))
    check("live positions", 176, kb.live_positions)
    check("transmitted positions", 180, kb.TRANSMITTED_POSITIONS)

    kb.set_all(0x40, 0x50, 0x60)
    kb.device.writes.clear()
    kb.apply(persist=False)
    red = b"".join(w[4:] for w in kb.device.writes[:3])
    check("176 colour bytes", bytes([0x40] * 176), red[:176])
    # HP's third page is 56 colour bytes and four zeros - the capture shows it, and its own
    # layout resource calls 176-179 padding.
    check("four zeros after them", bytes(4), red[176:180])
    check("one LED per position on this board", 176, len(kb.get_led_colors()))
    kb.close()


def test_key_map_matches_the_catalog():
    print("data/keys.json is HP's own grouping for the board it claims to be")
    catalog = kbl.Catalog(os.path.join(ROOT, "data", "keyboards.json"))
    names = kbl.KeyNames(os.path.join(ROOT, "data", "keys.json"))
    layout = catalog.by_id(names.layout_id)

    check("the layout it names exists", True, layout is not None)
    check("it is the one that has been verified on hardware", True, layout.verified)

    friendly = {}
    for group in names.rows.values():
        for name, info in group.items():
            friendly[info["hp"]] = info["leds"]

    check("same keys as HP's table", set(), set(friendly) ^ {k.name for k in layout.keys})
    mismatched = {k.name: (k.leds, friendly[k.name])
                  for k in layout.keys if friendly[k.name] != k.leds}
    check("same LEDs for every key", {}, mismatched)

    covered = sorted(p for leds in friendly.values() for p in leds)
    check("every live position is reachable", list(range(layout.leds)), covered)

    # The two names this project chose before HP's tables settled what the keys are. Both are
    # kept resolvable so saved profiles and ~/.config state files do not silently stop working.
    check("p owns the logo beneath it", [81, 175], friendly["KeyP"])
    check("p_icon still resolves", "KeyP", names.to_hp["p_icon"])
    check("r_ctrl still resolves, to the Copilot key", "KeyCopliot", names.to_hp["r_ctrl"])


def test_catalog_integrity():
    print("every layout in the catalogue covers its own map exactly once")
    catalog = kbl.Catalog(os.path.join(ROOT, "data", "keyboards.json"))
    check("48 layouts", 48, len(catalog.layouts))
    check("92 boards", 92, len(catalog.boards))
    check("exactly one is verified", ["Dojo/Global"],
          sorted(l.id for l in catalog.layouts.values() if l.verified))

    # A position claimed twice means two keys fight over one LED; a position claimed by nobody
    # means a light no caller can reach. Both were real bugs in the Windows sibling of this map.
    duplicated, unreachable = {}, {}
    for layout in catalog.layouts.values():
        seen = [p for k in layout.keys for p in k.leds]
        if len(seen) != len(set(seen)):
            duplicated[layout.id] = len(seen) - len(set(seen))
        # Dojo26C1 is the exception, and deliberately: that firmware blanks 137, 138 and 146
        # mid-map, so those three are absent rather than dark.
        missing = [p for p in range(layout.leds) if p not in set(seen)]
        if missing and not layout.id.startswith("Dojo26C1"):
            unreachable[layout.id] = missing
    check("no position claimed by two keys", {}, duplicated)
    check("no position unreachable", {}, unreachable)
    check("the 26C1 firmware's blanked positions are the only gaps",
          [137, 138, 146],
          [p for p in range(176)
           if p not in {q for k in catalog.by_id("Dojo26C1/Global").keys for q in k.leds}])

    # This board ships on both sides of HP's cycle boundary under one device name, which is why
    # detection is by board id: the two firmwares blank different positions.
    check("8D87 is a 25C1 Dojo", ("Dojo", "25C1"),
          (catalog.boards["8D87"]["layout"], catalog.boards["8D87"]["cycle"]))
    check("and it resolves to the verified layout", "Dojo/Global", catalog.for_board("8D87").id)
    check("an unknown board resolves to nothing rather than a near miss",
          None, catalog.for_board("FFFF"))


def test_other_layouts_are_addressable():
    print("a keyboard other than this one can be driven by name")
    kb = OmenKeyboard(key_map_path=os.path.join(ROOT, "data", "keys.json"),
                      layout="Starmade/German")
    check("layout selected", "Starmade/German", kb.layout.id)
    check("and it is flagged unverified", False, kb.layout.verified)
    check("live positions follow the layout", 167, kb.live_positions)
    check("friendly names still resolve", True, kb.key_leds("space") is not None)
    check("HP's names resolve too", kb.key_leds("space"), kb.key_leds("KeySpace"))
    check("a key this keyboard does not have returns nothing", None, kb.key_leds("num_0"))

    kb.set_all(0x10, 0x20, 0x30)
    kb.device.writes.clear()
    kb.apply(persist=False)
    red = b"".join(w[4:] for w in kb.device.writes[:3])
    check("167 colour bytes, then zeros", (bytes([0x10] * 167), bytes(13)),
          (red[:167], red[167:180]))
    kb.close()


def test_apply_layout_unchanged():
    print("apply() still frames the buffer the way it always did")
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
        test_colour_map_positions,
        test_live_positions,
        test_key_map_matches_the_catalog,
        test_catalog_integrity,
        test_other_layouts_are_addressable,
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
