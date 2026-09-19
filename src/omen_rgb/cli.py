#!/usr/bin/env python3
# Omen RGB Control Center - CLI Engine
# Copyright (C) 2026 arfelious

import sys
import os
import argparse
import time
import json
import glob

# Project Path Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))

try:
    from omen_rgb.driver import OmenKeyboard, ZONE_NAMES_4, restore_device_lighting_control
    from omen_rgb.lightbar import OmenLightbar, LB_ANIMATIONS, LB_THEMES, LB_SPEEDS, LB_DIRECTIONS
    from omen_rgb import effects as fx
    from omen_rgb import layouts as kbl
except ImportError:
    from driver import OmenKeyboard, ZONE_NAMES_4, restore_device_lighting_control
    from lightbar import OmenLightbar, LB_ANIMATIONS, LB_THEMES, LB_SPEEDS, LB_DIRECTIONS
    import effects as fx
    import layouts as kbl

def _parse_single_hex(s):
    s = str(s).strip()
    if s.startswith('#'):
        s = s[1:]
    elif s.startswith('0x') or s.startswith('0X'):
        s = s[2:]
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    elif len(s) == 3:
        return (int(s[0] * 2, 16), int(s[1] * 2, 16), int(s[2] * 2, 16))
    raise ValueError(f"Invalid hex color '{s}'")

def parse_color_list(args_list, expected_count=None):
    """
    Parses a list of color arguments into (R, G, B) tuples.
    Supports hex values ('#ff9900', 'ff9900') or RGB triplets ('255 153 0').
    """
    args = [str(x).strip() for x in args_list]

    is_hex_list = False
    if expected_count and len(args) == expected_count:
        is_hex_list = True
    elif all(a.startswith('#') or a.startswith('0x') or a.startswith('0X') for a in args):
        is_hex_list = True

    if is_hex_list:
        colors = []
        for a in args:
            try:
                colors.append(_parse_single_hex(a))
            except Exception:
                is_hex_list = False
                break
        if is_hex_list:
            if expected_count and len(colors) != expected_count:
                raise ValueError(f"Expected {expected_count} colors, got {len(colors)}.")
            return colors

    try:
        ints = [int(a) for a in args]
    except ValueError:
        colors = [_parse_single_hex(a) for a in args]
        if expected_count and len(colors) != expected_count:
            raise ValueError(f"Expected {expected_count} colors, got {len(colors)}.")
        return colors

    if len(ints) % 3 != 0:
        raise ValueError("Invalid color arguments. Provide hex values (e.g. #ff9900) or RGB triplets (e.g. 255 153 0).")

    colors = []
    for i in range(0, len(ints), 3):
        r, g, b = ints[i], ints[i+1], ints[i+2]
        colors.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))

    if expected_count and len(colors) != expected_count:
        raise ValueError(f"Expected {expected_count} colors, got {len(colors)}.")

    return colors


def _get_state_file_path():
    config_dir = os.path.expanduser("~/.config/omen-rgb-linux")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, "state.json")

def _load_current_state():
    state_file = _get_state_file_path()
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                loaded = json.load(f)
            return {k: tuple(v) if isinstance(v, list) else v for k, v in loaded.items()}
        except Exception:
            pass
    return {}

def _update_active_state(updates):
    state = _load_current_state()
    state.update(updates)
    serializable = {k: list(v) if isinstance(v, tuple) else v for k, v in state.items()}
    try:
        with open(_get_state_file_path(), "w") as f:
            json.dump(serializable, f)
    except Exception as e:
        print(f"State save notice: {e}")

def _get_all_keyboard_keys(kb):
    return kb.keys()


def _sorted_key_names(kb):
    """Every key, in colour-map order - which is roughly reading order across the board."""
    keys = {}
    for cat in kb.key_map.values():
        keys.update(cat)
    return sorted(keys, key=lambda k: keys[k]["leds"][0])


def cmd_static(kb, args):
    colors = parse_color_list(args.color, expected_count=1)
    r, g, b = colors[0]
    print(f"Setting static keyboard color: R={r}, G={g}, B={b}")
    kb.set_all(r, g, b)
    kb.apply()

    updates = {k: (r, g, b) for k in _get_all_keyboard_keys(kb)}
    _update_active_state(updates)

def cmd_set_key(kb, args):
    colors = parse_color_list(args.color, expected_count=1)
    r, g, b = colors[0]
    if kb.is_4zone:
        success = kb.set_key_color(args.key, r, g, b)
        if success:
            kb.apply()
            z_name = kb.key_to_zone.get(args.key, "unknown")
            print(f"Set zone '{z_name}' (via key '{args.key}') to RGB({r}, {g}, {b})")
            keys_in_z = kb.zones_data.get("zones", {}).get(z_name, {}).get("keys", [args.key])
            updates = {k: (r, g, b) for k in keys_in_z}
            _update_active_state(updates)
        return

    if kb.is_single_zone:
        kb.set_key_color(args.key, r, g, b)
        kb.apply()
        print(f"Set backlight (via key '{args.key}') to RGB({r}, {g}, {b})")
        _update_active_state({args.key: (r, g, b)})
        return

    leds = kb.key_leds(args.key)
    if not leds:
        print(f"Error: Key '{args.key}' is not on this keyboard. Try: omen-cli keys")
        return
    kb.set_key_color(args.key, r, g, b)
    kb.apply()
    plural = "" if len(leds) == 1 else f", {len(leds)} LEDs"
    print(f"Set key '{args.key}' to RGB({r}, {g}, {b}){plural}")
    _update_active_state({args.key: (r, g, b)})


def cmd_set_led(kb, args):
    colors = parse_color_list(args.color, expected_count=1)
    r, g, b = colors[0]
    if not kb.set_led_color(args.position, r, g, b):
        print(f"Error: position {args.position} is outside the colour map "
              f"(0..{kb.live_positions - 1} light up on this keyboard).")
        return
    kb.apply()
    print(f"Set LED position {args.position} to RGB({r}, {g}, {b})")


def cmd_keys(kb, args):
    print(kbl.describe(kb.layout, kb.board))
    print()
    for group, keys in kb.key_map.items():
        print(f"{group}:")
        for name, info in sorted(keys.items(), key=lambda kv: kv[1]["leds"][0]):
            leds = ",".join(str(p) for p in info["leds"])
            hp = "" if info["hp"] == name else f"  ({info['hp']})"
            print(f"  {name:<12} LED {leds}{hp}")
    print()
    print("A key is not an LED. Colour one legend of a two-legend key with 'set-led'.")


def cmd_layouts(kb, args):
    catalog = kbl.Catalog()
    board = kbl.board_id()
    print(f"This machine's DMI board name: {board or 'unreadable'}")
    entry = catalog.board(board)
    if entry:
        print(f"  {entry['display']} - HP device '{entry['device']}', "
              f"cycle {entry['cycle'] or 'unrecorded'}, layout {entry['layout']}")
    else:
        print("  not in the catalogue")
    print(f"\n{len(catalog.layouts)} layouts, {len(catalog.boards)} boards known.\n")
    for layout in sorted(catalog.layouts.values(),
                         key=lambda l: (not l.verified, l.id)):
        mark = "verified" if layout.verified else "unverified"
        print(f"  {layout.id:<32} {layout.leds:>3} LEDs  {len(layout.keys):>3} keys  {mark}")
    print("\nOnly Dojo/Global has been watched light up. The rest are derived from HP's own")
    print("tables by the same rule and have never been run; pass one with --layout to try it.")


def cmd_unstick(kb, args):
    print("Writing AutonomousMode = 1 to the mi_04 LampArray control report.")
    print("This tells the keyboard to go back to drawing its own lighting.")
    count = restore_device_lighting_control()
    if count:
        print(f"Accepted by {count} interface(s). Look at the keyboard - an accepted feature")
        print("report is not a lit keyboard, and report 6 cannot be read back.")
    else:
        print("No LampArray interface accepted it. mi_04 may not be exposed, or hidraw")
        print("permissions may be missing - see the udev rule in the README.")

def cmd_zone(kb, args):
    colors = parse_color_list(args.color, expected_count=1)
    r, g, b = colors[0]
    zone_arg = args.zone_id.lower().strip()
    if zone_arg.isdigit():
        zone_arg = int(zone_arg)
    kb.set_zone(zone_arg, r, g, b)
    kb.apply()
    
    # Resolve display name
    z_name = ZONE_NAMES_4[zone_arg] if isinstance(zone_arg, int) else zone_arg
    print(f"Set keyboard zone '{z_name}' to RGB({r}, {g}, {b})")
    keys_in_z = kb.zones_data.get("zones", {}).get(z_name, {}).get("keys", [])
    if keys_in_z:
        _update_active_state({k: (r, g, b) for k in keys_in_z})

def cmd_zones(kb, args):
    colors = parse_color_list(args.color, expected_count=4)
    kb.set_zones(colors)
    kb.apply()
    print("Set keyboard zone colors:")
    updates = {}
    for i, zn in enumerate(["right", "center", "left", "wasd"]):
        r, g, b = colors[i]
        print(f"  Zone {i} ({zn}): RGB({r}, {g}, {b})")
        keys_in_z = kb.zones_data.get("zones", {}).get(zn, {}).get("keys", [])
        for k in keys_in_z:
            updates[k] = (r, g, b)
    _update_active_state(updates)

def cmd_off(kb, args):
    print("Turning off all lights.")
    kb.set_all(0, 0, 0)
    kb.apply()
    updates = {k: (0, 0, 0) for k in _get_all_keyboard_keys(kb)}
    _update_active_state(updates)

def cmd_status(kb, args):
    print(f"Keyboard Backend: {kb.backend}")
    kb_type = kb.keyboard_type
    if kb_type is not None:
        print(f"Keyboard Type: {kb_type} ({kb.keyboard_type_name})")
    print(f"Numeric Keypad: {'Present' if kb.has_numpad else 'Absent'}")
    if kb.is_4zone:

        print("4-Zone Keyboard (hp-wmi sysfs):")
        live_colors = kb.get_zone_colors()
        for zn in ["right", "center", "left", "wasd"]:
            c = live_colors.get(zn, (0, 0, 0)) if live_colors else kb.zone_colors.get(zn, (0, 0, 0))
            b = kb.get_zone_brightness(zn)
            print(f"  Zone '{zn}': RGB{c}, Brightness={b}%")
    elif kb.is_single_zone:
        c = kb.zone_colors.get("backlight", (0, 0, 0))
        b = kb.get_zone_brightness("backlight")
        print(f"Single-Zone Keyboard (hp-wmi sysfs): RGB{c}, Brightness={b}%")

    else:
        print("Per-Key RGB Keyboard (USB HID 0d62:54bf)")

    if OmenLightbar.is_supported():
        lb = OmenLightbar()
        b = lb.get_brightness()
        colors = lb.get_colors()
        print(f"\nLightbar Backend: {lb.backend}")
        print(f"Lightbar Brightness: {b if b is not None else 'unknown'}%")
        if colors:
            print("Lightbar Zones:")
            for i, c in enumerate(colors, 1):
                print(f"  Zone {i}: RGB{c}")

def cmd_rainbow(kb, args):
    import colorsys
    print("Starting rainbow wave. Press Ctrl+C to stop.")
    t = 0
    try:
        while True:
            if kb.is_4zone:
                zone_offsets = {"left": 0.0, "wasd": 0.15, "center": 0.35, "right": 0.6}
                for zn, offset in zone_offsets.items():
                    zhue = (t + offset) % 1.0
                    zr, zg, zb = [int(x * 255) for x in colorsys.hsv_to_rgb(zhue, 1.0, 1.0)]
                    kb.set_zone(zn, zr, zg, zb)
                kb.apply(persist=False)
                t += 0.02
            elif kb.is_single_zone:
                r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(t % 1.0, 1.0, 1.0)]
                kb.set_all(r, g, b)
                kb.apply(persist=False)
                t += 0.02
            else:
                sorted_keys = _sorted_key_names(kb)
                for i, name in enumerate(sorted_keys):
                    hue = (t + (i / len(sorted_keys))) % 1.0
                    r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
                    kb.set_key_color(name, r, g, b)
                kb.apply(persist=False)
                t += 0.05
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nStopping rainbow wave.")
        kb.apply()   # persist the frame we stopped on, once


def _describe_effect_state(state):
    if not state:
        return "  (the MCU did not answer, or refused the read)"
    lines = [
        f"  effect      : {state['effect']} (wire {state['effect_wire']})",
        f"  show mode   : {state['show_mode']}",
        f"  colours     : {state['color_number']}",
        f"  speed       : {state['speed']}",
        f"  direction   : {state['direction']}",
        f"  ripple size : {state['ripple_size']}",
    ]
    if state["inner_brightness"] or state["outer_brightness"]:
        lines.append(f"  levels      : inner {state['inner_brightness']} "
                     f"outer {state['outer_brightness']}")
    if state["colors"]:
        swatches = " ".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in state["colors"])
        lines.append(f"  palette     : {swatches}")
    return "\n".join(lines)


def cmd_effect(kb, args):
    if args.fx_cmd == "list":
        print("Hardware effects (rendered by the keyboard MCU, no host process required):\n")
        for name, wire in fx.EFFECTS.items():
            info = fx.EFFECT_INFO[name]
            opts = []
            if info.colors:
                opts.append(f"{info.colors} colour(s)")
            if info.presets:
                opts.append("presets: " + "/".join(info.presets))
            if info.speed:
                opts.append("speed")
            if info.direction:
                opts.append("direction")
            if info.size:
                opts.append("size")
            if info.levels:
                opts.append("audio levels")
            print(f"  {name:<12} wire {wire:>3}   {', '.join(opts)}")
        print("\nShow modes  : " + ", ".join(fx.SHOW_MODES))
        print("Speeds      : " + ", ".join(fx.SPEEDS))
        print("Directions  : " + ", ".join(fx.DIRECTIONS))
        print("Ripple sizes: " + ", ".join(fx.SIZES))
        return

    if args.fx_cmd == "show":
        state = kb.get_effect()
        print("Installed effect record:")
        print(_describe_effect_state(state))
        if state:
            print("\nThis is the MCU's merged state, and a readback is not proof that anything")
            print("is lit. Look at the keyboard too.")
        return

    if args.fx_cmd == "off":
        kb.set_lighting_on(False)
        print("Keyboard backlight off. The Fn backlight key brings it back.")
        return

    if args.fx_cmd == "defaults":
        kb.restore_lighting_defaults()
        print("Sent RestoreLightingToDefault (0x10). Lighting is back to firmware defaults.")
        return

    # effect set
    colors = parse_color_list(args.color) if args.color else None
    setting = fx.EffectSetting(
        args.name,
        show_mode=args.theme,
        colors=colors or [],
        speed=args.speed,
        direction=args.direction,
        ripple_size=args.size,
        inner_brightness=args.inner,
        outer_brightness=args.outer,
    )

    for warning in setting.warnings():
        print(f"note: {warning}")

    kb.set_effect(setting, persist=args.persist)
    print(f"Effect set: {setting}")
    if args.persist:
        print("Stored to MCU flash; it will survive a reboot.")
    else:
        print("Not persisted - pass --persist to keep it across a power cycle.")


def _get_profiles_dir():
    config_dir = os.path.expanduser("~/.config/omen-rgb-linux/profiles")
    if os.path.exists(config_dir):
        return config_dir
    repo_p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles")
    if os.path.exists(repo_p):
        return repo_p
    os.makedirs(config_dir, exist_ok=True)
    return config_dir


def cmd_list(kb, args):
    p_dir = _get_profiles_dir()
    profiles = [os.path.splitext(f)[0] for f in os.listdir(p_dir) if f.endswith(".json")] if os.path.exists(p_dir) else []
    if profiles:
        print("Available profiles:")
        for p in sorted(profiles):
            print(f"  - {p}")
    else:
        print("No profiles found.")


def cmd_profile(kb, args):
    name = args.name
    p_dir = _get_profiles_dir()
    p_file = os.path.join(p_dir, f"{name}.json")
    if not os.path.exists(p_file):
        print(f"Profile '{name}' not found.")
        return
    with open(p_file, "r") as f:
        data = json.load(f)
    for k, c in data.items():
        if isinstance(c, (list, tuple)) and len(c) == 3:
            kb.set_key_color(k, c[0], c[1], c[2])
    kb.apply()
    print(f"Profile '{name}' applied.")


def cmd_lightbar(args):
    lb = OmenLightbar()
    brightness = getattr(args, "brightness", 100)
    updates = {}
    if args.lb_cmd == "static":
        colors = parse_color_list(args.color, expected_count=1)
        r, g, b = colors[0]
        lb.set_static(r, g, b, brightness=brightness)
        print(f"Lightbar set to static RGB({r}, {g}, {b}) brightness={brightness}")
        updates = {f"lb_zone_{i}": (r, g, b) for i in range(1, 5)}
    elif args.lb_cmd == "zone":
        colors = parse_color_list(args.color, expected_count=1)
        r, g, b = colors[0]
        lb.set_zone(args.zone_id, r, g, b, brightness=args.brightness)
        print(f"Lightbar Zone {args.zone_id} set to RGB({r}, {g}, {b})" + (f" brightness={args.brightness}" if args.brightness is not None else ""))
        updates = {f"lb_zone_{args.zone_id}": (r, g, b)}
    elif args.lb_cmd == "zones":
        colors = parse_color_list(args.color, expected_count=4)
        lb.set_colors(colors, brightness=brightness)
        print("Lightbar individual zone colors set:")
        for i, (r, g, b) in enumerate(colors, 1):
            print(f"  Zone {i}: RGB({r}, {g}, {b})")
            updates[f"lb_zone_{i}"] = (r, g, b)
    elif args.lb_cmd == "brightness":
        lb.set_brightness(args.level)
        print(f"Lightbar brightness set to {args.level}%")
    elif args.lb_cmd == "status":
        backend = lb.backend
        b = lb.get_brightness()
        colors = lb.get_colors()
        print(f"Lightbar backend: {backend}")
        print(f"Lightbar brightness: {b if b is not None else 'unknown'}%")
        if colors:
            print("Zone colors:")
            for i, (r, g, b_c) in enumerate(colors, 1):
                print(f"  Zone {i}: RGB({r}, {g}, {b_c})")
        else:
            print("Could not query zone colors.")
    elif args.lb_cmd == "off":
        lb.turn_off()
        print("Lightbar turned off.")
        updates = {f"lb_zone_{i}": (0, 0, 0) for i in range(1, 5)}
    elif args.lb_cmd == "animation":
        if args.name == "list":
            print("Lightbar animations (device-side; this numbering is NOT the keyboard's):\n")
            for name, wire in LB_ANIMATIONS.items():
                print(f"  {name:<14} {wire}")
            print("\nThemes    : " + ", ".join(LB_THEMES))
            print("Speeds    : " + ", ".join(LB_SPEEDS))
            print("Directions: " + ", ".join(LB_DIRECTIONS))
            return
        colors = parse_color_list(args.color) if args.color else None
        if args.name == "swipe" and args.theme != "custom":
            print("note: swipe has no preset palette and renders black on one; "
                  "use --theme custom with two colours.")
        if args.name == "audio-pulse" and not (args.tribe or args.bass):
            print("note: audio-pulse renders black at level 0 - the levels are the animation. "
                  "Pass --tribe/--bass, and re-run this from your own audio thread to make it "
                  "react.")
        lb.set_animation(args.name, theme=args.theme, speed=args.speed,
                         direction=args.direction, colors=colors,
                         brightness=brightness, levels=(args.tribe, args.bass))
        print(f"Lightbar animation '{args.name}' started (theme={args.theme}, "
              f"speed={args.speed}, brightness={brightness}).")
        print("There is no readback for animation state on this path - confirm by looking.")

    if updates:
        _update_active_state(updates)

def cmd_all(args):
    kb = OmenKeyboard(layout=getattr(args, "layout", None))
    if kb.layout_warning:
        print(f"note: {kb.layout_warning}")
    lb = None
    has_lb = False
    try:
        if OmenLightbar.is_supported():
            lb = OmenLightbar()
            has_lb = True
    except Exception:
        has_lb = False

    updates = {}
    if args.all_cmd == "static":
        colors = parse_color_list(args.color, expected_count=1)
        r, g, b = colors[0]
        kb.set_all(r, g, b)
        kb.apply()
        print(f"Keyboard set to static RGB({r}, {g}, {b})")
        updates = {k: (r, g, b) for k in _get_all_keyboard_keys(kb)}

        if has_lb and lb:
            try:
                lb.set_static(r, g, b)
                print(f"Lightbar set to static RGB({r}, {g}, {b})")
                for i in range(1, 5):
                    updates[f"lb_zone_{i}"] = (r, g, b)
            except Exception as e:
                print(f"Lightbar notice: {e}")

        _update_active_state(updates)

    elif args.all_cmd == "off":
        kb.set_all(0, 0, 0)
        kb.apply()
        print("Keyboard turned off.")
        updates = {k: (0, 0, 0) for k in _get_all_keyboard_keys(kb)}

        if has_lb and lb:
            try:
                lb.turn_off()
                print("Lightbar turned off.")
                for i in range(1, 5):
                    updates[f"lb_zone_{i}"] = (0, 0, 0)
            except Exception as e:
                print(f"Lightbar notice: {e}")

        _update_active_state(updates)

    elif args.all_cmd == "profile":
        cmd_profile(kb, args)

    elif args.all_cmd == "rainbow":
        import colorsys
        print("Starting rainbow wave across keyboard" + (" and lightbar" if has_lb else "") + ". Press Ctrl+C to stop.")
        sorted_keys = _sorted_key_names(kb)
        t = 0
        try:
            while True:
                for i, name in enumerate(sorted_keys):
                    hue = (t + (i / len(sorted_keys))) % 1.0
                    r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
                    kb.set_key_color(name, r, g, b)
                kb.apply(persist=False)   # see cmd_rainbow: 0x0a is a flash write

                if has_lb and lb:
                    try:
                        lb_colors = []
                        for zone_i in range(4):
                            zhue = (t + (zone_i / 4.0)) % 1.0
                            zr, zg, zb = [int(x * 255) for x in colorsys.hsv_to_rgb(zhue, 1.0, 1.0)]
                            lb_colors.append((zr, zg, zb))
                        lb.set_colors(lb_colors)
                    except Exception:
                        pass
                t += 0.05
                time.sleep(0.02)
        except KeyboardInterrupt:
            print("\nStopping rainbow wave.")

def main():
    parser = argparse.ArgumentParser(description="Omen RGB Linux CLI")
    parser.add_argument("-s", "--simulate-4zone", action="store_true",
                        help="Run in 4-zone simulation mode without writing to hardware or filesystem")
    parser.add_argument("-s1", "--simulate-1zone", action="store_true",
                        help="Run in single-zone simulation mode without writing to hardware or filesystem")
    parser.add_argument(
        "--layout", metavar="ID",
        help="Force a keyboard layout from data/keyboards.json (see 'layouts') instead of "
             "detecting one from the DMI board name")
    subparsers = parser.add_subparsers(dest="command")

    # All (keyboard + lightbar if present)
    p_all = subparsers.add_parser("all", help="Control all devices (keyboard + lightbar if available)")
    all_subparsers = p_all.add_subparsers(dest="all_cmd", help="All devices subcommands")
    
    all_static = all_subparsers.add_parser("static", help="Set static color for keyboard and lightbar")
    all_static.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")

    all_profile = all_subparsers.add_parser("profile", help="Apply a saved profile to keyboard and lightbar")
    all_profile.add_argument("name", help="Name of the profile (e.g. orange_theme)")

    all_subparsers.add_parser("off", help="Turn off keyboard and lightbar")
    all_subparsers.add_parser("rainbow", help="Start rainbow wave on keyboard and lightbar")

    # Keyboard Zone
    p_kbd_zone = subparsers.add_parser("zone", help="Set color for a keyboard zone (right, center, left, wasd or 0..3)")
    p_kbd_zone.add_argument("zone_id", help="Zone name (right, center, left, wasd) or index (0..3)")
    p_kbd_zone.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")

    # Keyboard Zones
    p_kbd_zones = subparsers.add_parser("zones", help="Set distinct colors for keyboard zones (right, center, left, wasd)")
    p_kbd_zones.add_argument("color", nargs="+", help="4 hex colors (#ff9900 ...) or 12 RGB values (255 153 0 ...)")

    # Status
    subparsers.add_parser("status", help="Query keyboard and lightbar status")

    # Static
    p_static = subparsers.add_parser("static", help="Set a solid color (accepts #RRGGBB or R G B)")
    p_static.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")

    # Set key
    p_key = subparsers.add_parser("set-key", help="Set color for a single key")
    p_key.add_argument("key", help="Name of the key (e.g. esc, a, space)")
    p_key.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")

    # Set one LED. A key with two printed legends has two of them.
    p_led = subparsers.add_parser(
        "set-led", help="Set color for a single LED, by colour-map position")
    p_led.add_argument("position", type=int, help="Colour-map position (0..175 on 8D87)")
    p_led.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components")

    # Keys and keyboards
    subparsers.add_parser("keys", help="List this keyboard's keys and the LEDs of each")
    subparsers.add_parser("layouts", help="List every keyboard layout, and which one this is")

    # Recovery
    subparsers.add_parser(
        "unstick", help="Hand the LEDs back to the keyboard when everything acknowledges "
                        "and nothing lights")

    # Profile
    p_profile = subparsers.add_parser("profile", help="Apply a saved profile")
    p_profile.add_argument("name", help="Name of the profile")

    # List
    subparsers.add_parser("list", help="List available profiles")

    # Off
    subparsers.add_parser("off", help="Turn off all lights")

    # Rainbow
    subparsers.add_parser("rainbow", help="Start a host-rendered rainbow wave")

    # Effects - rendered by the keyboard MCU itself
    p_effect = subparsers.add_parser(
        "effect", help="Hardware-rendered keyboard animations (no host process required)")
    fx_subparsers = p_effect.add_subparsers(dest="fx_cmd", help="Effect subcommands")

    fx_subparsers.add_parser("list", help="List the effects and the options each one uses")
    fx_subparsers.add_parser("show", help="Read the installed effect record back off the MCU")
    fx_subparsers.add_parser("off", help="Blank the keyboard backlight (Fn backlight key undoes it)")
    fx_subparsers.add_parser("defaults", help="Reset lighting to firmware defaults")

    fx_set = fx_subparsers.add_parser("set", help="Select an effect")
    fx_set.add_argument("name", choices=list(fx.EFFECTS), help="Effect name")
    fx_set.add_argument("color", nargs="*", default=None,
                        help="Up to 4 custom colors, hex or RGB triplets. Omit for HP's defaults.")
    fx_set.add_argument("--theme", choices=list(fx.SHOW_MODES),
                        help="Firmware palette instead of custom colors")
    fx_set.add_argument("--speed", choices=list(fx.SPEEDS))
    fx_set.add_argument("--direction", choices=list(fx.DIRECTIONS))
    fx_set.add_argument("--size", choices=list(fx.SIZES), help="Ripple only")
    fx_set.add_argument("--inner", type=int, help="Audio Pulse treble level (0-255)")
    fx_set.add_argument("--outer", type=int, help="Audio Pulse bass level (0-255)")
    fx_set.add_argument("--persist", action="store_true",
                        help="Store to MCU flash so it survives a reboot (a flash write - "
                             "deliberate, and never in a loop)")

    # Lightbar
    p_lightbar = subparsers.add_parser("lightbar", help="Control bottom light bar (Linux Multicolor LED subsystem)")
    lb_subparsers = p_lightbar.add_subparsers(dest="lb_cmd", help="Lightbar subcommands")
    
    lb_static = lb_subparsers.add_parser("static", help="Set static color for all 4 lightbar zones")
    lb_static.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")
    lb_static.add_argument("--brightness", type=int, default=100, help="Brightness (0-100)")

    lb_zone = lb_subparsers.add_parser("zone", help="Set color for a single lightbar zone (1 to 4)")
    lb_zone.add_argument("zone_id", type=int, choices=[1, 2, 3, 4], help="Zone number (1-4)")
    lb_zone.add_argument("color", nargs="+", help="Color as hex (#ff9900) or RGB components (255 153 0)")
    lb_zone.add_argument("--brightness", type=int, default=None, help="Brightness (0-100)")

    lb_zones = lb_subparsers.add_parser("zones", help="Set distinct colors for lightbar zones 1..4")
    lb_zones.add_argument("color", nargs="+", help="4 hex colors (#ff9900 ...) or 12 RGB values (255 153 0 ...)")
    lb_zones.add_argument("--brightness", type=int, default=100, help="Brightness (0-100)")

    lb_bright = lb_subparsers.add_parser("brightness", help="Set brightness level without changing colors")
    lb_bright.add_argument("level", type=int, help="Brightness percentage (0-100)")

    lb_subparsers.add_parser("status", help="Query active lightbar status and zone colors")
    lb_subparsers.add_parser("off", help="Turn off bottom lightbar")

    lb_anim = lb_subparsers.add_parser(
        "animation", help="Run one of the bar's nine device-side animations")
    lb_anim.add_argument("name", choices=["list"] + list(LB_ANIMATIONS))
    lb_anim.add_argument("color", nargs="*", default=None,
                         help="Zone colors, used when --theme custom")
    lb_anim.add_argument("--theme", choices=list(LB_THEMES), default="galaxy")
    lb_anim.add_argument("--speed", choices=list(LB_SPEEDS), default="medium")
    lb_anim.add_argument("--direction", choices=list(LB_DIRECTIONS), default="left")
    lb_anim.add_argument("--brightness", type=int, default=100, help="Brightness (0-100)")
    lb_anim.add_argument("--tribe", type=int, default=0, help="Audio Pulse treble level (0-255)")
    lb_anim.add_argument("--bass", type=int, default=0, help="Audio Pulse bass level (0-255)")

    args = parser.parse_args()
    if getattr(args, "simulate_4zone", False):
        os.environ["OMEN_SIMULATE_4ZONE"] = "1"
    if getattr(args, "simulate_1zone", False):
        os.environ["OMEN_SIMULATE_1ZONE"] = "1"

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == "all":
            if not args.all_cmd:
                p_all.print_help()
                return
            cmd_all(args)
            return

        if args.command == "lightbar":
            if not args.lb_cmd:
                p_lightbar.print_help()
                return
            cmd_lightbar(args)
            return

        if args.command == "list":
            cmd_list(None, args)
            return

        if args.command == "layouts":
            cmd_layouts(None, args)     # a table, not a device operation
            return

        if args.command == "unstick":
            cmd_unstick(None, args)     # the device this talks to is mi_04, not mi_03
            return

        if args.command == "effect":
            if not args.fx_cmd:
                p_effect.print_help()
                return
            if args.fx_cmd == "list":
                cmd_effect(None, args)   # a table, not a device operation
                return

        kb = OmenKeyboard(layout=args.layout, simulate_4zone=getattr(args, "simulate_4zone", False), simulate_1zone=getattr(args, "simulate_1zone", False))
        if kb.layout_warning:
            print(f"note: {kb.layout_warning}")

        if args.command == "static":
            cmd_static(kb, args)
        elif args.command == "zone":
            cmd_zone(kb, args)
        elif args.command == "zones":
            cmd_zones(kb, args)
        elif args.command == "status":
            cmd_status(kb, args)
        elif args.command == "set-key":
            cmd_set_key(kb, args)
        elif args.command == "set-led":
            cmd_set_led(kb, args)
        elif args.command == "keys":
            cmd_keys(kb, args)
        elif args.command == "off":
            cmd_off(kb, args)
        elif args.command == "profile":
            cmd_profile(kb, args)
        elif args.command == "rainbow":
            cmd_rainbow(kb, args)
        elif args.command == "effect":
            cmd_effect(kb, args)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

