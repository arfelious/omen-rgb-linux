#!/usr/bin/env python3
# Omen Keyboard HID Driver - Linux Support for HP Gaming Keyboard II (0d62:54bf)
# Copyright (C) 2026 arfelious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

import json
import os
import hid

class OmenKeyboard:
    """
    SDK for controlling HP Gaming Keyboard II (0d62:54bf) lighting on Linux.
    Restored to original protocol specifications with 0x0a Commit support.
    """
    VID = 0x0d62
    PID = 0x54bf

    def __init__(self, key_map_path=None):
        target_path = None
        for d in hid.enumerate(self.VID, self.PID):
            if d.get('interface_number') == 3:
                target_path = d['path']
                break
        
        if not target_path:
            raise RuntimeError("Omen Keyboard Lighting Interface not found.")
            
        self.device = hid.Device(path=target_path)
        # Buffer for each color channel (3 chunks of 62 bytes = 186 bytes)
        self.channels = {
            0x05: bytearray(186), # Red
            0x06: bytearray(186), # Green
            0x07: bytearray(186)  # Blue
        }
        
        if not key_map_path:
            # Traversal: src/driver.py -> src -> [ROOT]
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            key_map_path = os.path.join(base_dir, 'data', 'keys.json')
            
        try:
            with open(key_map_path, 'r') as f:
                self.key_map = json.load(f)
        except Exception as e:
            print(f"Warning: Could not load key map: {e}")
            self.key_map = {}

    def _set_zone(self, channel_id, zone_idx, value):
        if 0 <= zone_idx < 186:
            self.channels[channel_id][zone_idx] = value & 0xFF

    def set_key_color(self, key_name, r, g, b):
        mapping = None
        for category in self.key_map.values():
            if key_name in category: mapping = category[key_name]; break
        
        if not mapping: return False
            
        offset = mapping["offset"]
        width = mapping.get("width", 1)
        for i in range(width):
            self._set_zone(0x05, offset + i, r)
            self._set_zone(0x06, offset + i, g)
            self._set_zone(0x07, offset + i, b)

        # Link P key to P icon automatically
        if key_name == "p":
            self.set_key_color("p_icon", r, g, b)
            
        return True

    def set_all(self, r, g, b):
        for ch_id in [0x05, 0x06, 0x07]:
            val = [r, g, b][[0x05, 0x06, 0x07].index(ch_id)]
            self.channels[ch_id] = bytearray([val] * 186)
            # Hardware alignment bytes
            for chunk_idx in range(3):
                self.channels[ch_id][chunk_idx * 62] = 0
                self.channels[ch_id][chunk_idx * 62 + 1] = 0

    def apply(self):
        """Sends data reports and the mandatory 0x0a Commit report."""
        reports = []
        for channel_id in [0x05, 0x06, 0x07]:
            data = self.channels[channel_id]
            for chunk_idx in range(3):
                report = bytearray(64)
                report[0] = channel_id
                report[1] = chunk_idx
                chunk_data = data[chunk_idx * 62 : (chunk_idx + 1) * 62]
                report[2:64] = chunk_data
                reports.append(report)
        
        # Commit report (ID 0x0a)
        commit = bytearray(64)
        commit[0] = 0x0a
        commit[1] = 0x00
        commit[2] = 0x02
        commit[4] = 0xac
        commit[5] = 0x53
        reports.append(commit)

        # Execute all reports
        for r in reports:
            self.device.write(bytes(r))
        
        # Mandatory double-apply for the commit packet
        self.device.write(bytes(commit))

    def close(self):
        self.device.close()
