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

"""
The lighting MCU on interface 3 speaks 64-byte reports with a four-byte header:

    [0]      Command
    [1]      Index
    [2]      BLength, low byte
    [3]      BLength, high byte
    [4..63]  payload, 60 bytes

The colour pages this driver already sent fit that layout exactly: the two bytes zeroed at the
head of each 62-byte chunk are BLength, and the firmware wants them zero on a colour page.
See docs/PROTOCOL.md for the full command table and where it came from.
"""

import json
import os
import hid

try:
    # Package import: `from src import OmenKeyboard`
    from . import effects as fx
except ImportError:
    # Flat import: scripts/ append src/ to sys.path and do `from driver import ...`
    import effects as fx


class OmenKeyboard:
    """
    SDK for controlling HP Gaming Keyboard II (0d62:54bf) lighting on Linux.

    Two independent lighting mechanisms live behind this one interface:

    * **Per-key colour** - commands 0x05/0x06/0x07 paint a static picture the host owns.
      ``set_key_color`` / ``set_all`` / ``apply``.
    * **The effect engine** - command 0x03 hands one 36-byte record to the MCU, which then
      renders one of twelve animations itself, with no host process running.  ``set_effect``.

    Prefer the effect engine for anything animated: a host-drawn animation is 9 reports per
    frame and the MCU renders the same thing from a single report.
    """

    VID = 0x0d62
    PID = 0x54bf

    REPORT_LENGTH = 64

    # Commands.  Names are HP's, from McuSDK2 General.GeneralCommandHelper.
    CMD_SET_EFFECT = 0x03
    CMD_COLOR_R = 0x05
    CMD_COLOR_G = 0x06
    CMD_COLOR_B = 0x07
    CMD_LIGHTING_ON_OFF = 0x09
    CMD_STORE_TO_FLASH = 0x0a
    CMD_RESTORE_DEFAULT = 0x10
    CMD_GET_DEVICE_INFO = 0x80
    CMD_GET_EFFECT = 0x83

    # LightingEffectTarget.ALL_LED_AREA - the only target a keyboard has.  1 and 2 are a
    # mouse's logo and wheel.
    TARGET_ALL = 0

    FLASH_MAGIC = bytes((0xac, 0x53))
    RESTORE_MAGIC = bytes((0x94, 0x10, 0x98, 0x27))

    # Every command is answered on the IN endpoint with the request echoed and a status at
    # [4],[5].  An acknowledgement means the MCU parsed the frame - it is NOT the keyboard
    # saying anything lit, and the two have been observed to disagree.
    ACK = bytes((0xec, 0xac))
    NAK = bytes((0xec, 0xfa))

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

    # ----------------------------------------------------------------------------------
    # Framing
    # ----------------------------------------------------------------------------------

    def _frame(self, command, index=0, blength=0, payload=b""):
        """Compose one 64-byte report."""
        if len(payload) > self.REPORT_LENGTH - 4:
            raise ValueError(f"Payload is {len(payload)} bytes; 60 is the maximum.")
        report = bytearray(self.REPORT_LENGTH)
        report[0] = command & 0xFF
        report[1] = index & 0xFF
        report[2] = blength & 0xFF
        report[3] = (blength >> 8) & 0xFF
        report[4:4 + len(payload)] = payload
        return bytes(report)

    def _send(self, command, index=0, blength=0, payload=b""):
        """
        Write one frame.

        Byte 0 is the command.  hidapi treats byte 0 of a write as the report id, and this
        device does not use numbered reports, so the kernel passes the whole 64 bytes through
        and the command lands in wire position 0 - which is what the MCU expects.  This is the
        same convention ``apply()`` has always used.
        """
        return self.device.write(self._frame(command, index, blength, payload))

    def _read_reply(self, timeout_ms=250):
        """
        Read one 64-byte answer, or None on timeout.

        The reply carries no report-id byte, so its offsets are wire offsets and line up with
        the request: [4] is payload[0] either way.
        """
        try:
            data = self.device.read(self.REPORT_LENGTH, timeout_ms)
        except Exception:
            return None
        return bytes(data) if data else None

    @classmethod
    def _acknowledged(cls, reply):
        """True if the MCU accepted the frame. See the caution on ACK above."""
        return bool(reply) and len(reply) >= 6 and bytes(reply[4:6]) == cls.ACK

    # ----------------------------------------------------------------------------------
    # Per-key colour
    # ----------------------------------------------------------------------------------

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

    def apply(self, persist=True):
        """
        Send the nine colour pages, then optionally persist them.

        ``persist=True`` (the default, and what this driver has always done) ends the round
        with command 0x0a - HP's ``StoreLightingToFlash``.  That is an MCU **flash** write, not
        a commit: it is why lighting survives a reboot, and it is why it must not be put in a
        loop.  Any animation that calls ``apply()`` per frame should pass ``persist=False``.

        Whether the colour pages display without the flash write has not been confirmed on
        this hardware, which is why the default is unchanged.
        """
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
        
        # Execute all reports
        for r in reports:
            self.device.write(bytes(r))
        
        if persist:
            self.store_to_flash()

    # ----------------------------------------------------------------------------------
    # MCU commands
    # ----------------------------------------------------------------------------------

    def store_to_flash(self, target=TARGET_ALL):
        """
        Command 0x0a, ``StoreLightingToFlash`` - make the current lighting survive a reboot.

        This writes MCU flash.  Call it deliberately, once, at the end of a change; never per
        animation frame.
        """
        # Sent twice: the second write is what this driver has always done and is retained
        # because it is the behaviour reported working on real Linux hardware.
        self._send(self.CMD_STORE_TO_FLASH, target, 2, self.FLASH_MAGIC)
        return self._send(self.CMD_STORE_TO_FLASH, target, 2, self.FLASH_MAGIC)

    def set_lighting_on(self, on=True):
        """
        Command 0x09, ``SetKeyboardLightingOnOff`` - the backlight master.

        OGH opens every colour and effect round with this, argument ``1``.  It is a
        two-argument command, not a blanking command: argument ``0xff`` blanks the keyboard
        and ``0x09``/``0x00`` does not undo it - the Fn backlight key does, from firmware,
        with no host software running.  So do not pass a raw ``0xff`` here casually.
        """
        return self._send(self.CMD_LIGHTING_ON_OFF, 0, 1,
                          bytes((0x01 if on is True else (0x00 if on is False else int(on) & 0xFF),)))

    def set_effect(self, setting, persist=False, target=TARGET_ALL):
        """
        Command 0x03 - select one of the MCU's twelve hardware-rendered animations.

        ``setting`` is an :class:`effects.EffectSetting`, or an effect name for HP's defaults.
        One frame is enough: the animation then runs with this process exited and nothing
        maintaining it.  The single exception is Audio Pulse, which is host-fed - re-send the
        record at about 5 Hz with the current audio band levels in ``inner_brightness`` and
        ``outer_brightness``.

        ``persist=False`` by default, because persisting is a flash write.  Pass ``True`` to
        make the effect survive a reboot.

        Returns the reply, or None if the MCU did not answer.

        Note that the MCU **merges** this record into its stored state rather than replacing
        it - a field the selected effect does not consume keeps whatever it held before.  You
        therefore cannot clear a field by sending zero unless the current effect uses it.
        """
        if not isinstance(setting, fx.EffectSetting):
            setting = fx.EffectSetting(setting)

        self.set_lighting_on(True)
        self._read_reply()

        self._send(self.CMD_SET_EFFECT, target, fx.RECORD_LENGTH, setting.to_bytes())
        reply = self._read_reply()

        if persist:
            self.store_to_flash(target)
            self._read_reply()

        return reply

    def get_effect(self, target=TARGET_ALL):
        """
        Command 0x83, ``GetLightingEffect`` - read the installed effect record back.

        Returns the dict from :func:`effects.parse_record`, or None if the MCU refused or did
        not answer.  This is a genuine state read: it has been checked blind against what a
        person could see on the keyboard.

        What it reports is the MCU's *merged* record, not an echo of the last write - so a
        readback matching what you sent does not prove the firmware took that field from your
        frame, and it does not prove anything lit.  Look at the keyboard as well.
        """
        self._send(self.CMD_GET_EFFECT, target, 0, b"")
        reply = self._read_reply()
        if not reply or len(reply) < fx.FX_COLOR_0 + 3 + 4:
            return None
        if bytes(reply[4:6]) == self.NAK:
            return None                       # refused; not a zeroed record
        return fx.parse_record(reply[4:46])

    def get_device_info(self):
        """
        Command 0x80, ``GetDeviceInfo``.  Returns ``{'effect', 'effect_wire', 'brightness',
        'raw'}``, or None.

        Two bytes here move and are worth watching.  Byte ``[11]`` is the effect id, in the
        same wire numbering command 0x03 uses; byte ``[12]`` tracks the backlight.  Those
        offsets are the reply as it arrives with no report-id byte in front - HP's own code
        indexes a buffer that has one, so its ``[11]`` and ``[12]`` are these plus one.
        Picking the wrong alignment gives a plausible, meaningless brightness.
        """
        self._send(self.CMD_GET_DEVICE_INFO, 1, 0, b"")
        reply = self._read_reply()
        if not reply or len(reply) < 13:
            return None
        return {
            "effect": fx.effect_name(reply[11]),
            "effect_wire": reply[11],
            "brightness": reply[12],
            "raw": reply,
        }

    def restore_lighting_defaults(self, index=7):
        """
        Command 0x10, ``RestoreLightingToDefault`` - a firmware-level lighting reset.

        Worth knowing about before the next stuck keyboard: it resets the lighting from
        firmware and needs no power cycle.
        """
        return self._send(self.CMD_RESTORE_DEFAULT, index, len(self.RESTORE_MAGIC),
                          self.RESTORE_MAGIC)

    # ----------------------------------------------------------------------------------

    def get_colors(self):
        """
        Returns a dict mapping key_name -> (R, G, B) based on current driver buffer state.

        Per-key colour has no readback: the MCU answers colour pages with an acknowledgement
        and offers no command that returns the key map, so this reflects what the driver last
        buffered rather than what the hardware holds.  The interface as a whole is not
        write-only, though - see ``get_effect`` (0x83) and ``get_device_info`` (0x80), both of
        which return real state.
        """
        key_colors = {}
        r_buf = self.channels.get(0x05, bytearray(186))
        g_buf = self.channels.get(0x06, bytearray(186))
        b_buf = self.channels.get(0x07, bytearray(186))

        for row in self.key_map.values():
            for key_name, info in row.items():
                offset = info.get("offset", 0)
                if 0 <= offset < 186:
                    key_colors[key_name] = (r_buf[offset], g_buf[offset], b_buf[offset])

        return key_colors

    def close(self):
        self.device.close()
