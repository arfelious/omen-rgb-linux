# Omen RGB Linux

A high-fidelity lighting controller for **HP Omen 4-Zone RGB keyboards**, **HP Victus Single-Zone RGB keyboards**, a **per-key controller for the HP Omen Max 16** keyboard (**HP Gaming Keyboard II**, USB ID **0d62:54bf**), and the bottom lightbar on Linux.

## Features
- **SDK**: Python library for custom lighting scripts (see [examples/](examples/)).
- **CLI**: Control your keyboard from the terminal.
- **GUI**: Control your keyboard with graphical interface.


### Driver Prerequisites

- RGB controlling functionality requires installing a custom `hp-wmi` driver via the [omen-fan-control](https://github.com/arfelious/omen-fan-control) project. That driver exposes multicolor LED support for 4-zone keyboards, single-zone keyboards, and the bottom lightbar when applicable. The driver also exposes keyboard type, which is used to determine whether the numpad should be shown in the GUI.


---

## Installation & Usage

### Option A: uv (Recommended)
Install `omen-rgb` and `omen-rgb-gui` globally in an isolated environment via uv:
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

## CLI Reference
After installation, use `omen-rgb` to use the CLI. If running locally from source, you can also use `python3 scripts/omen_cli.py`.

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

# Keyboard-only commands
sudo omen-rgb static '#ff9900'
sudo omen-rgb static 255 0 255
sudo omen-rgb set-key esc '#ff0000'
sudo omen-rgb rainbow
sudo omen-rgb off

# 4-Zone Keyboard commands
# Possible zone names are wasd, left, center, and right 
sudo omen-rgb zone wasd '#ff0000'
sudo omen-rgb zones '#0099ff' '#7a00ff' '#ff3300' '#ffb700'

# Control Bottom Lightbar (supports hex codes or RGB integer components)
sudo omen-rgb lightbar static '#ff9900'
sudo omen-rgb lightbar zones '#ff9900' '#00ff00' '#0000ff' '#ffff00'
sudo omen-rgb lightbar off
```

### GUI
Launch the graphical interface:
After installation, yobu can use `sudo omen-rgb-gui` to launch the graphical interface. You can use `sudo python3 scripts/omen_gui.py` if you haven't done the installation process.
```bash
sudo omen-rgb-gui
# Or locally from source: 
sudo python3 scripts/omen_gui.py
```

|<img width="400" height="300" alt="Omen RGB Keyboard Controller GUI" src="https://github.com/user-attachments/assets/0731ca40-34a7-4b62-bdc9-6a62cfdcbb00" />|
|---|



## Uninstallation

### Option A: uv
```bash
sudo rm -rf ~/.local/share/uv/tools/omen-rgb ~/.local/bin/omen-rgb* /usr/local/bin/omen-rgb*
```
> **Note:** Regular `uv tool uninstall omen-rgb` may fail with permission errors if cache or `.pyc` files were created with `sudo`. The command above cleanly removes the tool and symlinks.

### Option B: pipx
```bash
pipx uninstall omen-rgb
sudo rm -f /usr/local/bin/omen-rgb*
```

### Clean configuration and profiles (Optional):
```bash
rm -rf ~/.config/omen-rgb-linux
```

## Device Support

This software supports:
- **Per-Key RGB Keyboards**: HP Gaming Keyboard II (USB ID `0d62:54bf`) via raw USB HID protocol (standalone, no extra drivers required).
- **4-Zone RGB Keyboards**: Linux Multicolor LED class nodes (`/sys/class/leds/hp::kbd_zoned_backlight-*`) exposed by the `hp-wmi` kernel driver (requires [omen-fan-control](https://github.com/arfelious/omen-fan-control)).
- **Single-Zone RGB Keyboards**: Single-zone HP/Victus backlight node (`/sys/class/leds/hp::kbd_backlight`) exposed by the `hp-wmi` kernel driver (requires [omen-fan-control](https://github.com/arfelious/omen-fan-control)).

- **Bottom Lightbar**: 4-zone addressable lightbar on HP OMEN MAX laptops (requires [omen-fan-control](https://github.com/arfelious/omen-fan-control)).

## Disclaimer

> This software is not affiliated with, authorized, maintained, sponsored, or endorsed by HP (Hewlett-Packard) or any of its affiliates. Use this software at your own risk. The authors and contributors assume no responsibility or liability for any potential hardware damage, data loss, or system issues resulting from using this software.

