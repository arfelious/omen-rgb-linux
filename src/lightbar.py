#!/usr/bin/env python3
# Omen Lightbar Controller - Linux ACPI/WMI Support for HP OMEN Light Strip
# Copyright (C) 2026 arfelious

import os
import struct
import re

# The bar's nine device-side animations, selected by payload byte [1] of the same command that
# sets a static colour.  5 is unassigned.  This numbering is the light bar's own - it is NOT the
# keyboard MCU's, and Ghosting, Ripple and OMEN X do not exist here at all.  OGH's twelve-item
# keyboard list and this nine-item list are two device paths merged in the UI, so always name the
# device along with the number.  All nine were written to real hardware and looked at.
LB_ANIMATIONS = {
    "lighting-sync": 1,
    "color-cycle": 2,
    "starlight": 3,
    "breathing": 4,
    "wave": 6,
    "raindrop": 7,
    "audio-pulse": 8,
    "confetti": 9,
    "sun": 10,
    "swipe": 11,
}

# Payload byte [2] packs three fields.
LB_SPEEDS = {"slow": 0, "medium": 1, "fast": 2}
LB_DIRECTIONS = {"left": 4, "right": 8}          # two directions, not the keyboard's six
LB_THEMES = {"galaxy": 16, "volcano": 32, "jungle": 48, "ocean": 64, "custom": 80}

# The firmware special-cases exactly two input values and stores something else.  #FF0000 comes
# back as #FE0000, which is visually indistinguishable; #FFFFFF comes back as #FEA3DA, which is a
# plainly purple-white next to a plainly white #FFFFFE.  Every other value tested passes through
# byte-exact, including #FF0001 one bit away - so this is a two-entry lookup, not a gamma curve.
# White is therefore the one colour a caller must not ask this device for.
_WHITE_SUBSTITUTION = {(0xFF, 0xFF, 0xFF): (0xFF, 0xFF, 0xFE)}


class OmenLightbar:
    """
    Controller for the HP OMEN Laptop bottom light strip (Dojo Lightbar) using ACPI calls on Linux.
    Requires the `acpi_call` kernel module (`/proc/acpi/call`) and root privileges.

    Four zones, zone 0 leftmost, confirmed by writing red/green/blue/white and looking.
    """

    #: Rewrite #FFFFFF to #FFFFFE so "white" is white.  Set False to send values verbatim.
    AVOID_FIRMWARE_WHITE = True
    def __init__(self, acpi_path=None):
        self.acpi_path = acpi_path or self._detect_acpi_path()

    def _detect_acpi_path(self):
        # Default ACPI device method path for HP WMI
        default_path = "\\_SB.WMID.WMAA"
        sys_path = "/sys/devices/platform/hp-wmi"
        if os.path.exists(sys_path):
            return default_path
        return default_path

    @classmethod
    def ensure_available(cls, auto_load=True):
        """
        Ensures /proc/acpi/call is available.
        Attempts to execute `modprobe acpi_call` automatically if missing.
        """
        if os.path.exists("/proc/acpi/call"):
            return True

        if auto_load:
            try:
                import subprocess
                subprocess.run(["modprobe", "acpi_call"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            except Exception:
                pass

        if os.path.exists("/proc/acpi/call"):
            return True

        msg = (
            "Lightbar control error: acpi_call kernel module is missing (/proc/acpi/call not found).\n"
            "Tried running 'modprobe acpi_call', but the module could not be loaded.\n\n"
            "Please install the acpi_call package for your Linux distribution:\n"
            "  - Arch Linux:    sudo pacman -S acpi_call-dkms\n"
            "  - Ubuntu/Debian: sudo apt install acpi_call-dkms\n"
            "  - Fedora:        sudo dnf install akmod-acpi_call\n"
        )
        raise RuntimeError(msg)

    @classmethod
    def is_available(cls):
        """Checks if /proc/acpi/call interface is available or can be loaded."""
        try:
            return cls.ensure_available(auto_load=True)
        except RuntimeError:
            return False

    @staticmethod
    def _is_success_response(response):
        if not response:
            return False
        res = response.upper()
        if "50415353" in res or "PASS" in res:
            return True
        if "0X50, 0X41, 0X53, 0X53" in res or "0X50,0X41,0X53,0X53" in res.replace(" ", ""):
            return True
        if res.startswith("{"):
            parts = [p.strip() for p in res.strip("{}").split(",") if p.strip()]
            if len(parts) >= 4:
                try:
                    bytes_val = [int(p, 16) for p in parts[:4]]
                    if bytes_val == [0x50, 0x41, 0x53, 0x53]:
                        return True
                except ValueError:
                    pass
        return False

    @classmethod
    def is_supported(cls):
        """
        Queries system and ACPI BIOS to detect if HP OMEN Lightbar hardware is supported and responsive.
        """
        if not os.path.exists("/sys/devices/platform/hp-wmi"):
            return False

        if not cls.is_available():
            return False

        try:
            lb = cls()
            # Use GET command 131080 (0x20008) to poll the current state without overwriting
            header = struct.pack("<4sIII", b"SECU", 131080, 4, 128)
            data = bytearray(128)
            data[0] = 0
            hex_arg = f"b{(header + data).hex()}"
            acpi_cmd = f"{lb.acpi_path} 0 3 {hex_arg}"

            with open("/proc/acpi/call", "w") as f:
                f.write(acpi_cmd)
            with open("/proc/acpi/call", "r") as f:
                response = f.read().strip()

            return cls._is_success_response(response)
        except Exception:
            return False


    def _build_payload(self, colors, brightness=100, effect=0, config=0, tribe=0, bass=0):
        # Ensure 4 zones
        colors = list(colors)
        if len(colors) > 4:
            colors = colors[:4]
        while len(colors) < 4:
            colors.append((0, 0, 0))

        if self.AVOID_FIRMWARE_WHITE:
            colors = [_WHITE_SUBSTITUTION.get(tuple(c), c) for c in colors]

        # 128-byte payload layout
        data = bytearray(128)
        data[0] = 0    # Target device: 0 LightBar, 1 FourZoneAni (the 4-zone keyboard variant)
        data[1] = effect & 0xFF   # 0 = static colour; non-zero selects one of LB_ANIMATIONS
        data[2] = config & 0xFF   # speed | direction | theme, packed - see _pack_config
        data[3] = max(0, min(100, brightness))
        # tribe/bass are the audio-pulse band levels, and they ARE the animation rather than an
        # enable for it: held constant the bar shows a steady colour and keeps showing it after
        # the process exits.  At 0/0 Audio Pulse renders black.  HP varies them per audio sample
        # from its own thread.
        data[4] = max(0, min(255, tribe))
        data[5] = max(0, min(255, bass))
        data[6] = len(colors)  # Zone count (4)

        # Write RGB values for zones
        offset = 7
        for r, g, b in colors:
            data[offset] = max(0, min(255, r))
            data[offset + 1] = max(0, min(255, g))
            data[offset + 2] = max(0, min(255, b))
            offset += 3

        # Header: Sign (4 bytes "SECU"), Command (131081 / 0x20009), CommandType (11 / 0x0B), Size (128)
        header = struct.pack("<4sIII", b"SECU", 131081, 11, 128)
        full_buffer = header + data
        return f"b{full_buffer.hex()}"

    def _write(self, hex_arg):
        acpi_cmd = f"{self.acpi_path} 0 3 {hex_arg}"

        try:
            with open("/proc/acpi/call", "w") as f:
                f.write(acpi_cmd)

            with open("/proc/acpi/call", "r") as f:
                response = f.read().strip()

            if self._is_success_response(response):
                return True
            else:
                raise RuntimeError(f"BIOS ACPI call failed. Response: {response}")
        except PermissionError:
            raise PermissionError("Permission denied when writing to /proc/acpi/call. Please run as root (sudo).")
        except FileNotFoundError:
            raise RuntimeError("acpi_call module missing (/proc/acpi/call not found).")

    def set_colors(self, colors, brightness=100):
        """
        Set color of the 4 lightbar zones.

        Parameters:
            colors (list of tuples): Up to 4 (R, G, B) tuples for zones 1 to 4.
            brightness (int): Brightness level (0-100).

        Brightness is byte [3] of the payload and rides along with the colour; there is no
        separate brightness command on this path, and no way to read it back.
        """
        self.ensure_available(auto_load=True)
        return self._write(self._build_payload(colors, brightness))

    @staticmethod
    def _pack_config(speed="medium", direction="left", theme="galaxy"):
        """Pack payload byte [2]: bits 0-1 speed, bits 2-3 direction, bits 4-7 theme."""
        def pick(table, value, what):
            if isinstance(value, int):
                return value
            key = str(value).strip().lower()
            if key not in table:
                raise ValueError(f"Unknown {what} '{value}'. Choose one of: {', '.join(table)}")
            return table[key]

        return (pick(LB_SPEEDS, speed, "speed")
                | pick(LB_DIRECTIONS, direction, "direction")
                | pick(LB_THEMES, theme, "theme"))

    def set_animation(self, effect, theme="galaxy", speed="medium", direction="left",
                      colors=None, brightness=100, levels=(0, 0)):
        """
        Run one of the bar's nine device-side animations. See LB_ANIMATIONS for the names.

        The animation runs in firmware with nothing maintaining it, so this is one call and
        the process can exit.  Two of the nine need their arguments chosen with care, and both
        render **black** otherwise:

        * ``swipe`` has no preset palette - pass ``theme="custom"`` and two colours.
        * ``audio-pulse`` is host-fed; ``levels`` are the band levels and at ``(0, 0)`` it
          draws nothing.  Constant levels give a constant colour, not a pulse: to make it
          react to audio you have to re-send this from your own audio thread.

        There is no readback for animation state on this path - HP's own read command returns
        FAIL on this board - so the only way to confirm an animation is to look at the bar.
        """
        self.ensure_available(auto_load=True)

        if isinstance(effect, str):
            key = effect.strip().lower()
            if key not in LB_ANIMATIONS:
                raise ValueError(
                    f"Unknown animation '{effect}'. Choose one of: {', '.join(LB_ANIMATIONS)}")
            effect = LB_ANIMATIONS[key]

        tribe, bass = (list(levels) + [0, 0])[:2]
        payload = self._build_payload(
            colors or [(0, 0, 0)] * 4,
            brightness=brightness,
            effect=effect,
            config=self._pack_config(speed, direction, theme),
            tribe=tribe,
            bass=bass,
        )
        return self._write(payload)

    def set_static(self, r, g, b, brightness=100):
        """Sets all 4 lightbar zones to the same RGB color."""
        return self.set_colors([(r, g, b)] * 4, brightness=brightness)

    def turn_off(self):
        """Turns off all lightbar zones."""
        return self.set_static(0, 0, 0, brightness=0)

    @staticmethod
    def _parse_acpi_response_bytes(response):
        if not response:
            return None
        res = str(response).strip()
        
        hex_tokens = re.findall(r'0x[0-9a-fA-F]+', res)
        if hex_tokens:
            try:
                return bytearray([int(h, 16) for h in hex_tokens])
            except ValueError:
                pass

        clean_res = res.strip("{}").strip()
        if clean_res.startswith("0x") or clean_res.startswith("b"):
            raw_hex = clean_res.lstrip("b0x").replace(" ", "")
            try:
                return bytearray.fromhex(raw_hex)
            except ValueError:
                pass
        return None

    def get_colors(self):
        """
        Queries system ACPI BIOS for current active lightbar zone colors.
        Uses reverse-engineered Command 131080 (0x20008), CommandType 4 (0x04).
        Queries each zone (0..3) and extracts RGB bytes directly from BIOS response.
        Returns list of 4 (R, G, B) tuples or None if unsupported/failed.
        """
        self.ensure_available(auto_load=True)

        colors = []
        for zone_idx in range(4):
            header = struct.pack("<4sIII", b"SECU", 131080, 4, 128)
            data = bytearray(128)
            data[0] = zone_idx
            hex_arg = f"b{(header + data).hex()}"
            acpi_cmd = f"{self.acpi_path} 0 3 {hex_arg}"

            try:
                with open("/proc/acpi/call", "w") as f:
                    f.write(acpi_cmd)
                with open("/proc/acpi/call", "r") as f:
                    response = f.read().strip()

                if not self._is_success_response(response):
                    return None

                buf = self._parse_acpi_response_bytes(response)
                if not buf:
                    return None

                pass_idx = buf.find(b"PASS")
                if pass_idx == -1:
                    return None

                payload_idx = pass_idx + 8
                if len(buf) < payload_idx + 3:
                    return None

                r = buf[payload_idx]
                g = buf[payload_idx + 1]
                b = buf[payload_idx + 2]
                colors.append((r, g, b))
            except Exception as e:
                print(f"Lightbar get_colors notice: {e}")
                return None

        return colors if len(colors) == 4 else None



