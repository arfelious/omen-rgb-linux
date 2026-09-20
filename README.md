# Omen RGB Linux

A high-fidelity lighting controller for **HP Omen 4-Zone RGB keyboards**, **HP Victus Single-Zone RGB keyboards**, **HP Omen Max 16 Per-Key keyboards** (**HP Gaming Keyboard II**, USB ID **0d62:54bf**), and the **bottom lightbar** on Linux.

## Features
- **Multi-Hardware Support**:
  - **Per-Key RGB**: Direct USB HID interface (`0d62:54bf`) with per-LED addressing.
  - **4-Zone & Single-Zone**: Native Linux Multicolor LED subsystem (`/sys/class/leds/hp::kbd_zoned_backlight-*`, `hp::kbd_backlight`) via `hp-wmi`.
  - **Bottom Lightbar**: 4-zone addressable light strip via Linux Multicolor LED class nodes and direct ACPI WMI commands.
- **Hardware Effect Engine**: For per-key keyboards, select any of the keyboard MCU's twelve built-in animations and the lightbar's nine animations.
- **48 Keyboard Layouts Across 92 Boards**: Automatically detects motherboard DMI names (`/sys/class/dmi/id/board_name`) to select precise physical LED maps derived from OMEN Gaming Hub binaries.
- **LampArray Recovery**: Includes `unstick` command to recover keyboards locked into autonomous mode by Windows Dynamic Lighting.
- **CLI & GUI**: Terminal CLI tool and responsive Tkinter GUI.
- **Python SDK**: Complete API for custom scripts and profiles (see [examples/](examples/)).

The wire protocol is documented in detail in [docs/PROTOCOL.md](docs/PROTOCOL.md).

---

## Driver Prerequisites

- **Per-Key Keyboards (`0d62:54bf`)**: Work directly out of the box with standard `hidapi` (run with `sudo` or configure a `udev` rule).
- **4-Zone & Single-Zone Keyboards**: Require the custom `hp-wmi` kernel driver with multicolor LED support, available from the [omen-fan-control](https://github.com/arfelious/omen-fan-control) project.
- **Bottom Lightbar**:
  - **Static Zone Lighting**: Supported through `hp-wmi` multicolor LED class nodes (`/sys/class/leds/hp::lightbar-*`) from the [omen-fan-control](https://github.com/arfelious/omen-fan-control) project.
  - **Hardware Animations**: Lightbar onboard animations (9 built-in effects) run directly via BIOS ACPI WMI calls, requiring the `acpi_call` kernel module (`/proc/acpi/call`):
    - **Debian / Ubuntu**: `sudo apt install acpi-call-dkms && sudo modprobe acpi_call`
    - **Arch Linux**: `sudo pacman -S acpi_call-dkms && sudo modprobe acpi_call`
    - **Fedora**: `sudo dnf install akmod-acpi_call && sudo modprobe acpi_call`


---

## Installation & Usage

### Option A: uv (Recommended)
Install `omen-rgb` and `omen-rgb-gui` globally in an isolated environment via `uv`:
```bash
uv tool install git+https://github.com/arfelious/omen-rgb-linux.git
sudo ln -sf "$HOME/.local/bin/omen-rgb"* /usr/local/bin/
```

### Option B: pipx
```bash
pipx install git+https://github.com/arfelious/omen-rgb-linux.git
sudo ln -sf "$HOME/.local/bin/omen-rgb"* /usr/local/bin/
```
> **Note:** Because device hardware access requires root permissions, symlinking the binaries to `/usr/local/bin` ensures `sudo` can locate `omen-rgb` and `omen-rgb-gui`.

### Option C: Clone and run from source
```bash
git clone https://github.com/arfelious/omen-rgb-linux.git
cd omen-rgb-linux

# Run with uv:
uv sync
sudo uv run omen-rgb status
sudo uv run omen-rgb-gui
```

---

## CLI Reference
After installation, use `omen-rgb` in your terminal. If running locally from source, you can also use `python3 scripts/omen_cli.py`.

```bash
# Check device status & active zones
sudo omen-rgb status

# Control all devices (keyboard + lightbar if supported)
sudo omen-rgb all static '#ff9900'
sudo omen-rgb all profile my_preset
sudo omen-rgb all off
sudo omen-rgb all rainbow

# Apply or list saved profiles
sudo omen-rgb list
sudo omen-rgb profile my_preset

# Static colors (accepts hex or RGB components)
sudo omen-rgb static '#ff9900'
sudo omen-rgb static 255 153 0
sudo omen-rgb set-key esc '#ff0000'
sudo omen-rgb off

# 4-Zone Keyboard commands (zones: wasd, left, center, right)
sudo omen-rgb zone wasd '#ff0000'
sudo omen-rgb zones '#0099ff' '#7a00ff' '#ff3300' '#ffb700'

# Per-LED addressing — light individual LEDs on multi-LED keys
sudo omen-rgb set-led 1 '#ff0000'

# Keyboard layouts and catalogue inspection
sudo omen-rgb layouts
sudo omen-rgb keys
sudo omen-rgb --layout Starmade/German static '#ff9900'

# Clear Windows Dynamic Lighting LampArray lockups
sudo omen-rgb unstick

# Hardware-rendered keyboard effects (no host CPU usage)
sudo omen-rgb effect list
sudo omen-rgb effect set ghosting
sudo omen-rgb effect set wave '#faac0f' '#0ffa36' --speed fast --direction left-to-right
sudo omen-rgb effect set ripple --theme ocean --size large
sudo omen-rgb effect set color-cycle --persist   # persists across reboots
sudo omen-rgb effect show                        # reads MCU state back
sudo omen-rgb effect defaults                    # resets to firmware defaults

# Host-rendered rainbow wave (safe: persist=False)
sudo omen-rgb rainbow

# Bottom Lightbar controls
sudo omen-rgb lightbar static '#ff9900'
sudo omen-rgb lightbar zones '#ff9900' '#00ff00' '#0000ff' '#ffff00'
sudo omen-rgb lightbar off

# Lightbar onboard animations
omen-rgb lightbar animation list
sudo omen-rgb lightbar animation wave --theme ocean --speed fast
sudo omen-rgb lightbar animation swipe --theme custom '#ff0000' '#0000ff'
```

### Hardware effects vs. `rainbow`
- `rainbow` is software-rendered: sends reports every frame continuously, stopping when you kill the command.
- `effect set color-cycle` asks the MCU for the same animation in a single packet; it renders directly in hardware with 0% CPU and keeps running after the terminal is closed.

> **Note on White Color:** Asking the lightbar for `#FFFFFF` triggers a firmware bug where it substitutes `#FEA3DA` (visibly purple). The driver automatically rewrites `#FFFFFF` to `#FFFFFE` (pure white) to bypass this bug.

---

## Graphical Interface (GUI)
Launch the graphical interface:
```bash
sudo omen-rgb-gui
# Or from source:
sudo python3 scripts/omen_gui.py
```

|<img width="500" alt="Omen RGB Keyboard Controller GUI" src="https://github.com/user-attachments/assets/0731ca40-34a7-4b62-bdc9-6a62cfdcbb00" />|
|---|


---

## Python SDK Reference

```python
from omen_rgb import OmenKeyboard, OmenLightbar, EffectSetting

# Initialize keyboard (auto-detects 4-zone WMI, single-zone, or per-key HID)
kb = OmenKeyboard()

# 1. Solid color across all keys / zones
kb.set_all(255, 153, 0)
kb.apply()

# 2. 4-Zone keyboard control
if kb.is_4zone:
    kb.set_zone("wasd", 255, 0, 0)
    kb.set_zone("left", 0, 255, 0)
    kb.apply()

# 3. Per-Key RGB & LED control
if kb.is_per_key:
    kb.set_key_color("esc", 255, 0, 0)
    kb.set_led_color(1, 0, 0, 255) # Secondary LED on Esc
    kb.apply()

    # Hardware MCU animations (0% CPU, persists after script exits)
    kb.set_effect("ghosting")
    kb.set_effect(EffectSetting("wave", colors=[(255, 150, 0), (0, 200, 255)], speed="fast"))

# Bottom Lightbar control
lb = OmenLightbar()
if lb.is_supported():
    lb.set_static(255, 100, 0)
    lb.set_animation("wave", theme="ocean", speed="fast")

kb.close()
```

---

## Uninstallation

### Option A: uv
```bash
sudo rm -rf ~/.local/share/uv/tools/omen-rgb ~/.local/bin/omen-rgb* /usr/local/bin/omen-rgb*
```

### Option B: pipx
```bash
pipx uninstall omen-rgb
sudo rm -f /usr/local/bin/omen-rgb*
```

### Clean configuration and profiles (Optional):
```bash
rm -rf ~/.config/omen-rgb-linux
```

---

## Device Support & Contributions
- **Per-Key RGB**: Tested and verified on **HP OMEN MAX 16** (boards `8D87` and `8D41`). Includes 48 derived layouts across 92 motherboard models.
- **4-Zone RGB**: Fully supported via `hp-wmi` multicolor LED subsystem nodes (`hp::kbd_zoned_backlight-*`).
- **Single-Zone RGB**: Fully supported via `hp-wmi` multicolor LED subsystem nodes (`hp::kbd_backlight`).
- **Bottom Lightbar**: Supported via `hp-wmi` (`hp::lightbar-*`) for static control, and `/proc/acpi/call` for hardware animations.

Pull requests, hardware captures, and layout verifications are welcome!

---

## Disclaimer

> This software is not affiliated with, authorized, maintained, sponsored, or endorsed by HP (Hewlett-Packard) or any of its affiliates. Use this software at your own risk. The authors and contributors assume no responsibility or liability for any potential hardware damage, data loss, or system issues resulting from using this software.

