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

from driver import OmenKeyboard

def cmd_static(kb, args):
    print(f"Setting static color: R={args.r}, G={args.g}, B={args.b}")
    kb.set_all(args.r, args.g, args.b)
    kb.apply()

def cmd_off(kb, args):
    print("Turning off all lights.")
    kb.set_all(0, 0, 0)
    kb.apply()

def cmd_profile(kb, args):
    p_dir = os.path.join(BASE_DIR, "profiles")
    p_path = os.path.join(p_dir, f"{args.name}.json")
    
    if not os.path.exists(p_path):
        print(f"Error: Profile '{args.name}' not found in {p_dir}")
        return

    print(f"Applying profile: {args.name}")
    try:
        with open(p_path, "r") as f:
            state = json.load(f)
        for name, color in state.items():
            kb.set_key_color(name, color[0], color[1], color[2])
        kb.apply()
    except Exception as e:
        print(f"Error loading profile: {e}")

def cmd_list(kb, args):
    p_dir = os.path.join(BASE_DIR, "profiles")
    profiles = glob.glob(os.path.join(p_dir, "*.json"))
    
    if not profiles:
        print("No profiles found.")
        return

    print("Available Profiles:")
    for p in sorted(profiles):
        print(f"  - {os.path.basename(p).replace('.json', '')}")

def cmd_rainbow(kb, args):
    import colorsys
    print("Starting rainbow wave. Press Ctrl+C to stop.")
    
    keys = {}
    for cat in kb.key_map.values():
        keys.update(cat)
    sorted_keys = sorted(keys.keys(), key=lambda k: keys[k]["offset"])
    
    t = 0
    try:
        while True:
            for i, name in enumerate(sorted_keys):
                hue = (t + (i / len(sorted_keys))) % 1.0
                r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
                kb.set_key_color(name, r, g, b)
            kb.apply()
            t += 0.05
            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nStopping rainbow wave.")

def main():
    parser = argparse.ArgumentParser(description="Omen RGB Linux CLI")
    subparsers = parser.add_subparsers(dest="command")

    # Static
    p_static = subparsers.add_parser("static", help="Set a solid color")
    p_static.add_argument("r", type=int, help="Red (0-255)")
    p_static.add_argument("g", type=int, help="Green (0-255)")
    p_static.add_argument("b", type=int, help="Blue (0-255)")

    # Profile
    p_profile = subparsers.add_parser("profile", help="Apply a saved profile")
    p_profile.add_argument("name", help="Name of the profile")

    # List
    subparsers.add_parser("list", help="List available profiles")

    # Off
    subparsers.add_parser("off", help="Turn off all lights")

    # Rainbow
    subparsers.add_parser("rainbow", help="Start a rainbow wave")

    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return

    try:
        kb = OmenKeyboard()
        if args.command == "static":
            cmd_static(kb, args)
        elif args.command == "off":
            cmd_off(kb, args)
        elif args.command == "profile":
            cmd_profile(kb, args)
        elif args.command == "list":
            cmd_list(kb, args)
        elif args.command == "rainbow":
            cmd_rainbow(kb, args)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
