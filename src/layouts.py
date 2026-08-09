#!/usr/bin/env python3
# Omen Keyboard layouts - which LED byte belongs to which key, for every per-key OMEN keyboard
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
The static colour map is one byte per **LED**, not one per key.

A key with two printed legends has two LEDs, Space has five, backspace six.  So "make W blue"
is meaningless without a grouping, and the grouping is board-specific.  ``data/keyboards.json``
is that grouping for all 48 per-key OMEN keyboards OMEN Gaming Hub supports, keyed to 92 board
ids; ``data/keys.json`` is the same thing for the one keyboard this project was written on,
under friendlier names.

**Only one layout has been watched light up: Dojo/Global, board 8D87.**  Every other entry is
derived from the same HP resource by the same rule and nobody has seen it run, which is what
``Layout.verified`` says.  Surface that flag - a keyboard that lights the wrong key is worse
than one that admits it does not know.

Detection is by DMI board name, which is the same string Windows calls
``Win32_BaseBoard.Product``.  It has to be the board and not the model: Dojo and Vibrance each
ship SSIDs on both sides of HP's 26C1 firmware boundary, the two firmwares blank different LED
positions, and the model name alone would pick the wrong map.

See ``docs/PROTOCOL.md`` for where the data came from.
"""

import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CATALOG_PATH = os.path.join(BASE_DIR, 'data', 'keyboards.json')
KEYS_PATH = os.path.join(BASE_DIR, 'data', 'keys.json')

# Win32_BaseBoard.Product under another name.  board_name is DMI type 2 "Product Name", which
# is the field HP's own DeviceList.json keys its SSID table on.
DMI_BOARD = '/sys/class/dmi/id/board_name'

#: The layout every entry point falls back to.  It is the one that has been verified, and it is
#: what ``data/keys.json`` describes.
DEFAULT_LAYOUT = 'Dojo/Global'


class Key:
    """
    One physical key: HP's name for it, where it sits, and which LED bytes light it.

    ``rect`` is the KEY's rectangle and every LED of the key repeats it - HP's tables carry no
    sub-key geometry at all.  So this says which key an LED belongs to and never where on the
    key it sits.  Intra-key order is a byte order, not a geometry, and it is not consistent
    between rows: on Esc LED 1 is under the legend and LED 2 below it, while on the number row
    the digit takes the lower index and the shifted glyph the higher.  Say "LED 1 of 2", not
    "top", unless someone has looked at that key on that keyboard.
    """

    __slots__ = ('name', 'rect', 'leds', 'label')

    def __init__(self, name, rect, leds, label=None):
        self.name = name
        self.rect = rect
        self.leds = leds
        self.label = label

    def __repr__(self):
        return f"Key({self.name!r}, leds={self.leds})"


class Layout:
    """One keyboard: how long its colour map is, and what the keys are."""

    def __init__(self, layout_id, data):
        self.id = layout_id
        self.leds = data['leds']
        self.bounds = data.get('bounds', [])
        self.verified = bool(data.get('verified'))
        self.keys = [Key(k['name'], k.get('rect', []), k['leds'], k.get('label'))
                     for k in data['keys']]
        self._by_name = {k.name.lower(): k for k in self.keys}

    def key(self, name):
        """One key by HP's name, case-insensitively.  None when this layout has no such key."""
        return self._by_name.get(str(name).lower())

    def __repr__(self):
        return (f"Layout({self.id!r}, {self.leds} LEDs, {len(self.keys)} keys, "
                f"{'verified' if self.verified else 'UNVERIFIED'})")


class Catalog:
    """
    Every per-key OMEN keyboard, and which board has which.

    Generated from OGH's own embedded layout tables by omen-max-16's
    ``tools/static/emit-omencore-layouts.py``.  Regenerate it there rather than editing
    ``data/keyboards.json`` by hand.
    """

    def __init__(self, path=CATALOG_PATH):
        with open(path, 'r') as handle:
            raw = json.load(handle)
        self.layouts = {k: Layout(k, v) for k, v in raw.get('layouts', {}).items()}
        self.boards = raw.get('boards', {})

    def by_id(self, layout_id):
        """One layout by id, e.g. ``"Dojo/Global"``.  None when the id is not in the table."""
        return self.layouts.get(layout_id)

    def board(self, board_id):
        """What the catalogue knows about a board id, or None."""
        if not board_id:
            return None
        return self.boards.get(str(board_id).strip().upper())

    def for_board(self, board_id, language=None):
        """
        The layout for a DMI board name, or None when the board is unknown.

        ``language`` is HP's own keyboard-language name (``JP``, ``UK``, ``German``, ...); a
        layout with no table for it falls back to Global, which is what OGH does.

        Returning None rather than a near miss is deliberate.  Guessing the wrong keyboard
        lights the wrong keys and looks like a working feature.
        """
        entry = self.board(board_id)
        if not entry:
            return None
        if language:
            localised = self.by_id(f"{entry['layout']}/{language}")
            if localised:
                return localised
        return self.by_id(f"{entry['layout']}/Global")


def board_id(path=DMI_BOARD):
    """This machine's DMI board name, e.g. ``"8D87"``.  None if it cannot be read."""
    try:
        with open(path, 'r') as handle:
            return handle.read().strip().upper() or None
    except OSError:
        return None


class KeyNames:
    """
    Friendly names for HP's, and the reverse.

    ``data/keys.json`` names the keys of the verified board the way a person would type them -
    ``esc``, ``l_shift``, ``num_7`` - and carries HP's name alongside each.  That table is the
    alias list, and it is applied to *every* layout: ``l_shift`` resolves on any keyboard that
    has a ``KeyShiftL``.

    Anything with no friendly name is addressable by HP's name, and a generic rule catches the
    rest: strip a leading ``Key`` and lowercase, so ``num7`` finds ``KeyNum7``.
    """

    def __init__(self, path=KEYS_PATH):
        with open(path, 'r') as handle:
            raw = json.load(handle)

        #: group -> friendly name -> {"hp": ..., "leds": [...]}, in colour-map order.  This is
        #: the display grouping the GUI draws from, and it describes DEFAULT_LAYOUT only.
        self.rows = raw.get('rows', raw)
        self.layout_id = raw.get('layout', DEFAULT_LAYOUT)

        self.to_hp = {}
        for group in self.rows.values():
            for name, info in group.items():
                self.to_hp[name] = info['hp']

        # Names this project used before HP's own tables settled what the keys are.  Kept so
        # saved profiles and ~/.config state files keep resolving.
        for old, new in raw.get('aliases', {}).items():
            if new in self.to_hp:
                self.to_hp[old] = self.to_hp[new]

        self.to_friendly = {}
        for group in self.rows.values():
            for name, info in group.items():
                self.to_friendly.setdefault(info['hp'], name)

    def hp_name(self, name, layout):
        """
        HP's name for whatever the caller typed, resolved against ``layout``.  None if the
        layout has no such key.
        """
        if name is None:
            return None
        candidates = [self.to_hp.get(name), self.to_hp.get(str(name).lower()), name]
        for candidate in candidates:
            if candidate and layout.key(candidate):
                return layout.key(candidate).name

        # Generic fall-back: "num7" -> "KeyNum7", "esc" -> "KeyEsc".
        wanted = str(name).lower().replace('_', '').replace('-', '')
        for key in layout.keys:
            bare = key.name.lower()
            bare = bare[3:] if bare.startswith('key') else bare
            if bare.replace('_', '') == wanted:
                return key.name
        return None

    def friendly(self, hp_name):
        """The friendly name for an HP name, or the HP name itself when there is none."""
        return self.to_friendly.get(hp_name, hp_name)


def describe(layout, board=None):
    """One line naming the keyboard, for a log or a --version banner."""
    if layout is None:
        return (f"board {board or 'unknown'}: no layout in the catalogue. "
                f"Falling back to {DEFAULT_LAYOUT}, which may light the wrong keys.")
    return (f"{layout.id}: {layout.leds} LEDs, {len(layout.keys)} keys"
            + (f", board {board}" if board else "")
            + ("" if layout.verified else " - UNVERIFIED, derived from HP's tables and never "
                                          "seen on hardware"))
