#!/usr/bin/env python3
# Omen Lightbar Controller - Linux ACPI/WMI Support for HP OMEN Light Strip
# Copyright (C) 2026 arfelious

import os
import struct
import re

class OmenLightbar:
    """
    Controller for the HP OMEN Laptop bottom light strip (Dojo Lightbar) using ACPI calls on Linux.
    Requires the `acpi_call` kernel module (`/proc/acpi/call`) and root privileges.
    """
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


    def _build_payload(self, colors, brightness=100):
        # Ensure 4 zones
        colors = list(colors)
        if len(colors) > 4:
            colors = colors[:4]
        while len(colors) < 4:
            colors.append((0, 0, 0))

        # 128-byte payload layout
        data = bytearray(128)
        data[0] = 0    # Target device: LightBar
        data[1] = 0    # Mode: Static
        data[2] = 0    # Config: Static
        data[3] = max(0, min(100, brightness))
        data[4] = 0    # tribe
        data[5] = 0    # bass
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

    def set_colors(self, colors, brightness=100):
        """
        Set color of the 4 lightbar zones.

        Parameters:
            colors (list of tuples): Up to 4 (R, G, B) tuples for zones 1 to 4.
            brightness (int): Brightness level (0-100).
        """
        self.ensure_available(auto_load=True)

        hex_arg = self._build_payload(colors, brightness)
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



