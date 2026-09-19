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

The colour map itself is addressed by **LED position**, not by buffer offset and not by key.
Three pages of 60 positions are transmitted per channel; on this keyboard the first 176 of them
reach an LED and the last four are padding.  A key owns as many positions as it has LEDs - two
for a dual-legend key, five for Space, six for backspace - and ``data/keys.json`` holds that
grouping.  ``_offset`` is the only place the 62-byte chunking is allowed to matter.
"""

import hid

try:
    # Package import: `from src import OmenKeyboard`
    from . import effects as fx
    from . import layouts as kbl
except ImportError:
    # Flat import: scripts/ append src/ to sys.path and do `from driver import ...`
    import effects as fx
    import layouts as kbl


class OmenKeyboard:
    """
    SDK for controlling HP Gaming Keyboard II (0d62:54bf) lighting on Linux.

    Two independent lighting mechanisms live behind this one interface:

    * **Per-key colour** - commands 0x05/0x06/0x07 paint a static picture the host owns.
      ``set_key_color`` / ``set_led_color`` / ``set_all`` / ``apply``.
    * **The effect engine** - command 0x03 hands one 36-byte record to the MCU, which then
      renders one of twelve animations itself, with no host process running.  ``set_effect``.

    Prefer the effect engine for anything animated: a host-drawn animation is 9 reports per
    frame and the MCU renders the same thing from a single report.

    Both of these are the MCU's own state, which is why a picture written here survives the Fn
    overlay with nothing running on the host - see docs/PROTOCOL.md, "Fn, and which interface
    owns the picture".
    """

    VID = 0x0d62
    PID = 0x54bf

    REPORT_LENGTH = 64

    # One page is 62 buffer bytes: two of BLength and 60 of colour map.  Three pages per
    # channel, so 186 buffer bytes carrying 180 transmitted LED positions.
    PAGES = 3
    PAGE_BYTES = 62
    PAYLOAD_BYTES = 60
    CHANNEL_BYTES = PAGES * PAGE_BYTES              # 186
    TRANSMITTED_POSITIONS = PAGES * PAYLOAD_BYTES   # 180

    #: Positions that reach an LED when the layout is unknown.  HP's pre-26C1 table declares 180
    #: entries and annotates the last four as padding, and the wire capture agrees: OGH's third
    #: page carries 56 colour bytes and four zeros.
    DEFAULT_LIVE_POSITIONS = 176

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

    def __init__(self, key_map_path=None, layout=None):
        """
        ``layout`` forces a keyboard from ``data/keyboards.json`` (e.g. ``"Starmade/German"``)
        instead of detecting one from the DMI board name.  Pass it for a board the catalogue
        does not know, or gets wrong.
        """
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
            0x05: bytearray(self.CHANNEL_BYTES), # Red
            0x06: bytearray(self.CHANNEL_BYTES), # Green
            0x07: bytearray(self.CHANNEL_BYTES)  # Blue
        }

        self._load_layout(key_map_path, layout)

    def _load_layout(self, key_map_path=None, layout=None):
        """
        Work out which keyboard this is, and so which LED bytes make up each key.

        An unknown board falls back to the one verified layout rather than refusing to run, but
        it says so: the wrong layout lights the wrong keys and looks like a working feature.
        ``self.layout_warning`` carries the message for a UI to show, or None.
        """
        self.board = kbl.board_id()
        self.layout_warning = None

        try:
            self.catalog = kbl.Catalog()
            self.names = kbl.KeyNames(key_map_path) if key_map_path else kbl.KeyNames()
        except Exception as e:
            print(f"Warning: Could not load keyboard layouts: {e}")
            self.catalog, self.names = None, None
            self.layout, self.key_map = None, {}
            self.live_positions = self.DEFAULT_LIVE_POSITIONS
            return

        if layout:
            self.layout = self.catalog.by_id(layout)
            if self.layout is None:
                raise ValueError(f"No layout '{layout}' in data/keyboards.json.")
            if not self.layout.verified:
                self.layout_warning = kbl.describe(self.layout, self.board)
        else:
            self.layout = self.catalog.for_board(self.board)
            if self.layout is None:
                self.layout = self.catalog.by_id(self.names.layout_id)
                self.layout_warning = kbl.describe(None, self.board)
            elif not self.layout.verified:
                self.layout_warning = kbl.describe(self.layout, self.board)

        self.live_positions = self.layout.leds if self.layout else self.DEFAULT_LIVE_POSITIONS

        if self.layout is None:
            print(f"Warning: data/keys.json names layout '{self.names.layout_id}', which is not "
                  f"in data/keyboards.json.")
            self.key_map = {}
        elif self.layout.id == self.names.layout_id:
            #: group -> key name -> {"hp", "leds"}, in colour-map order.  The friendly names and
            #: the display grouping the GUI draws its rows from.
            self.key_map = self.names.rows
        else:
            # A keyboard this project has no friendly names for.  Keys are HP's names, in
            # colour-map order, in one group - enough to address them, not enough to draw them.
            self.key_map = {'keys': {
                k.name: {'hp': k.name, 'leds': k.leds}
                for k in sorted(self.layout.keys, key=lambda k: k.leds[0])}}

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

    @classmethod
    def _offset(cls, position):
        """
        Buffer offset of an LED position.

        Two bytes of BLength sit at the head of every 62-byte page, so the map is not
        contiguous in the buffer: position 60 is at offset 64, not 62.  Go through this rather
        than adding to an offset - backspace spans positions 58 to 63, and walking those as
        buffer offsets puts a colour byte where the firmware requires a zero.
        """
        if not 0 <= position < cls.TRANSMITTED_POSITIONS:
            return None
        page, within = divmod(position, cls.PAYLOAD_BYTES)
        return page * cls.PAGE_BYTES + 2 + within

    def set_led_color(self, position, r, g, b):
        """
        Colour ONE LED, addressed by colour-map position rather than by key.

        A key is not one LED.  Dual-legend keys have two, Space five, backspace six, and the map
        is per-LED natively - so the legends of one key can take different colours, which is
        what the keyboard itself does for the Fn overlay.  ``key_leds`` gives the positions of a
        key, in the order HP's table declares them.

        Which LED is which ON the key is not in the data.  See ``layouts.Key``.
        """
        offset = self._offset(position)
        if offset is None:
            return False
        self.channels[0x05][offset] = r & 0xFF
        self.channels[0x06][offset] = g & 0xFF
        self.channels[0x07][offset] = b & 0xFF
        return True

    def key_leds(self, key_name):
        """The colour-map positions of a key, by friendly name or HP's.  None if unknown."""
        for category in self.key_map.values():
            if key_name in category:
                return category[key_name]['leds']
        if self.names and self.layout:
            hp = self.names.hp_name(key_name, self.layout)
            if hp:
                return self.layout.key(hp).leds
        return None

    def keys(self):
        """Every key name this keyboard answers to, in colour-map order."""
        return [name for category in self.key_map.values() for name in category]

    def set_key_color(self, key_name, r, g, b):
        """Colour every LED of a key.  False when this keyboard has no such key."""
        leds = self.key_leds(key_name)
        if not leds:
            return False
        for position in leds:
            self.set_led_color(position, r, g, b)
        return True

    def set_all(self, r, g, b):
        """
        Fill every live position.

        Only the live ones.  Three full pages go on the wire either way, but the last four
        positions are padding on this board, so HP's third page is 56 colour bytes and four
        zeros - which is what the capture shows and what this reproduces.
        """
        for channel_id, value in ((0x05, r), (0x06, g), (0x07, b)):
            self.channels[channel_id] = bytearray(self.CHANNEL_BYTES)
            for position in range(self.live_positions):
                self.channels[channel_id][self._offset(position)] = value & 0xFF

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
            for chunk_idx in range(self.PAGES):
                report = bytearray(self.REPORT_LENGTH)
                report[0] = channel_id
                report[1] = chunk_idx
                chunk_data = data[chunk_idx * self.PAGE_BYTES:(chunk_idx + 1) * self.PAGE_BYTES]
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

        The colour of a key's FIRST LED.  A key with two legends can hold two colours and this
        reports one of them; ``get_led_colors`` is the whole picture.

        Per-key colour has no readback: the MCU answers colour pages with an acknowledgement
        and offers no command that returns the key map, so this reflects what the driver last
        buffered rather than what the hardware holds.  The interface as a whole is not
        write-only, though - see ``get_effect`` (0x83) and ``get_device_info`` (0x80), both of
        which return real state.
        """
        colors = self.get_led_colors()
        return {name: colors[info['leds'][0]]
                for row in self.key_map.values()
                for name, info in row.items()
                if info['leds'] and info['leds'][0] < len(colors)}

    def get_led_colors(self):
        """The buffered colour of every live position, indexed by colour-map position."""
        return [(self.channels[0x05][self._offset(p)],
                 self.channels[0x06][self._offset(p)],
                 self.channels[0x07][self._offset(p)])
                for p in range(self.live_positions)]

    def close(self):
        self.device.close()


# --------------------------------------------------------------------------------------
# The other interface, and the one way it can make this one look broken
# --------------------------------------------------------------------------------------

#: HID LampArray control report.  Report id 6 is the LampArrayControlReport in the HID Lighting
#: and Illumination spec's own ordering, and it carries one field: AutonomousMode.
LAMP_CONTROL_REPORT_ID = 6

#: mi_04, the keyboard's HID LampArray (usage page 0x59).  A second, coarser enumeration of the
#: same LEDs - 120 lamps against this map's 176 positions - and a different way to drive them.
LAMPARRAY_INTERFACE = 4


def restore_device_lighting_control(vid=OmenKeyboard.VID, pid=OmenKeyboard.PID):
    """
    Tell the keyboard to go back to drawing its own lighting: ``AutonomousMode = 1``.

    Run this if the keyboard is dark, every command is acknowledged, and nothing lights.

    The other interface on this device, mi_04, is a HID LampArray.  A host that writes
    ``AutonomousMode = 0`` to its control report takes ownership of the LEDs, and the MCU stops
    drawing - including the static colour map this driver writes.  Everything then acknowledges
    honestly and displays nothing, for HP's own client as much as for this one.

    Three things make that worth a recovery command rather than a footnote:

    * **Nothing sets it back.**  It is device state, not process state; it outlives the program
      that set it and survives a reboot, because the internal USB bus stays powered.
    * **It is not readable.**  Report 6 is write-only on this device, so the state is invisible
      to software and the only symptom is a keyboard that ignores you.
    * **It travels across a dual boot.**  Windows Dynamic Lighting and some OMEN control apps
      take host control and do not hand it back, so the wedge can arrive from the other OS.

    Returns the number of interfaces the report was accepted by.  As everywhere else here, an
    accepted write is not a lit keyboard: look at it.
    """
    written = 0
    for entry in hid.enumerate(vid, pid):
        if entry.get('interface_number') not in (LAMPARRAY_INTERFACE, -1):
            continue
        if entry.get('usage_page') not in (0x59, 0, None):
            continue
        try:
            device = hid.Device(path=entry['path'])
        except Exception:
            continue
        try:
            device.send_feature_report(bytes((LAMP_CONTROL_REPORT_ID, 0x01)))
            written += 1
        except Exception:
            pass
        finally:
            device.close()
    return written
