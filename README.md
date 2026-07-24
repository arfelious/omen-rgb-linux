# Omen RGB Linux

A high-fidelity, per-key lighting controller for the **HP Omen Max 16** keyboard (**HP Gaming Keyboard II**, USB ID **0d62:54bf**) on Linux.

## Features
- **SDK**: Python library for custom lighting scripts.
- **CLI**: Control your keyboard from the terminal.
- **GUI**: Control your keyboard with graphical interface.

## Installation & Usage

### 1. Install Dependencies
Requires `hidapi` for USB keyboard communication. Controlling the optional bottom lightbar requires the `acpi_call` kernel module.

```bash
# Python dependency
pip install hidapi

# System dependency (Optional for per-key RGB keyboards if you don't want to change the lightbar, necessary for 4-zone keyboards)
sudo pacman -S acpi_call-dkms      # Arch Linux
sudo apt install acpi_call-dkms    # Ubuntu / Debian
sudo dnf install akmod-acpi_call   # Fedora
```

### 2. Quick Start (Local Run)
You can run the controller directly from the repository without installing it globally.
```bash
# Set a static color
sudo python3 scripts/omen_cli.py static 0 255 0

# Open the GUI
sudo python3 scripts/omen_gui.py
```

### 3. System-wide Installation (Optional)
To use the `omen_cli` command from any directory, install the package:
```bash
pip install .
sudo omen_cli static 255 0 255
```

## CLI Reference
If running locally, use `python3 scripts/omen_cli.py`. If installed, use `omen_cli`.
```bash
# Control all devices (keyboard + lightbar if supported, only keyboard if not supported)
sudo python3 scripts/omen_cli.py all static '#ff9900'
sudo python3 scripts/omen_cli.py all profile my_preset
sudo python3 scripts/omen_cli.py all off
sudo python3 scripts/omen_cli.py all rainbow

# Apply or list saved profiles
sudo python3 scripts/omen_cli.py list
sudo python3 scripts/omen_cli.py profile my_preset

# Keyboard-only commands
sudo python3 scripts/omen_cli.py static '#ff9900'
sudo python3 scripts/omen_cli.py static 255 0 255
sudo python3 scripts/omen_cli.py set-key esc '#ff0000'
sudo python3 scripts/omen_cli.py rainbow
sudo python3 scripts/omen_cli.py off

# Control Bottom Lightbar (supports hex codes or RGB integer components)
sudo python3 scripts/omen_cli.py lightbar static '#ff9900'
sudo python3 scripts/omen_cli.py lightbar zones '#ff9900' '#00ff00' '#0000ff' '#ffff00'
sudo python3 scripts/omen_cli.py lightbar zones 255 0 0 0 255 0 0 0 255 255 255 0
sudo python3 scripts/omen_cli.py lightbar off
```

### GUI
```bash
sudo python3 scripts/omen_gui.py
```

|<img width="400" height="300" alt="Omen RGB Keyboard Controller GUI" src="https://github.com/user-attachments/assets/0731ca40-34a7-4b62-bdc9-6a62cfdcbb00" />|
|---|


## SDK Documentation

The project includes a Python SDK (`OmenKeyboard`) to control keyboard lighting programmatically.

### Import & Initialization

If you are running scripts from the root directory or installing it locally, import the driver class:
```python
from src import OmenKeyboard
```

#### Constructor: `OmenKeyboard(key_map_path=None)`
Initializes the driver and connects to the keyboard.
- **Parameters**:
  - `key_map_path` (*str*, optional): Custom path to the `keys.json` file. If not provided, it defaults to `data/keys.json` relative to the package root.
- **Raises**:
  - `RuntimeError`: If the HP Gaming Keyboard II lighting interface cannot be found.

> Writing to raw USB devices requires root permissions by default on most Linux systems. Run your SDK scripts using `sudo python3 script.py` or configure appropriate `udev` rules.

### API Methods

#### `set_key_color(key_name, r, g, b)`
Set the RGB color of a specific key in the buffer.
- **Parameters**:
  - `key_name` (*str*): The identifier of the key to modify (e.g., `"esc"`, `"space"`, `"a"`, `"num_0"`). See [Key Mapping Reference](#key-mapping-reference) for details.
  - `r` (*int*): Red channel value (0–255).
  - `g` (*int*): Green channel value (0–255).
  - `b` (*int*): Blue channel value (0–255).
- **Returns**: `bool` – `True` if the key exists and the color was set; `False` otherwise.
- **Notes**: Setting the color of the `"p"` key automatically applies the same color to the `"p_icon"` special logo key.

#### `set_all(r, g, b)`
Set the color of all keys across the entire keyboard to a static color.
- **Parameters**:
  - `r` (*int*), `g` (*int*), `b` (*int*): RGB channel values (0–255).

#### `apply()`
Commits and writes the buffered colors to the keyboard hardware. This performs the multi-channel transfer and commits the changes using the commit protocol.

#### `close()`
Closes the underlying HID device connection. It's recommended to call this to cleanly release system resources.

### Complete Example

Here is a complete script demonstrating initialization, custom layout configuration, error handling, and proper resource cleanup:

```python
import sys
import time
from src import OmenKeyboard

try:
    # Initialize the keyboard interface
    kb = OmenKeyboard()
    
    # 1. Clear all previous lights
    kb.set_all(0, 0, 0)
    kb.apply()
    time.sleep(0.2)

    # 2. Highlight WASD cluster in Red
    for key in ["w", "a", "s", "d"]:
        kb.set_key_color(key, 255, 0, 0)
        
    # 3. Highlight ESC key in Green
    kb.set_key_color("esc", 0, 255, 0)
    
    # 4. Highlight Spacebar in Blue
    kb.set_key_color("space", 0, 0, 255)

    # Write changes to keyboard hardware
    kb.apply()

    print("RGB lighting applied successfully.")
    
except RuntimeError as e:
    print(f"Driver Error: {e}", file=sys.stderr)
    print("Ensure the keyboard is connected and you have write permissions (run with sudo).", file=sys.stderr)
    sys.exit(1)
finally:
    # Ensure connections are cleanly closed
    if 'kb' in locals():
        kb.close()
```

### OmenLightbar (Bottom Light Strip SDK)

Control the 4-zone bottom lightbar on HP OMEN laptops using Linux ACPI calls (`/proc/acpi/call`).

```python
from src import OmenLightbar

lb = OmenLightbar()

# 1. Set static color on all 4 zones
lb.set_static(255, 0, 0, brightness=100)

# 2. Set distinct colors for individual zones (Zones 1-4)
lb.set_colors([
    (255, 0, 0),    # Zone 1: Red
    (0, 255, 0),    # Zone 2: Green
    (0, 0, 255),    # Zone 3: Blue
    (255, 255, 0)   # Zone 4: Yellow
], brightness=100)

# 3. Query current active hardware zone colors and brightness from ACPI BIOS
result = lb.get_colors()
if result:
    colors, brightness = result
    print(f"Current lightbar colors: {colors}, brightness: {brightness}")

# 4. Turn off lightbar
lb.turn_off()
```



### Key Mapping Reference

Key names are mapped to hardware offsets in `data/keys.json`. Available keys are organized in the following categories:

- **Row 0–5**: Standard keyboard rows (e.g. `"esc"`, `"f1"`, `"tilde"`, `"1"`, `"tab"`, `"q"`, `"caps_lock"`, `"a"`, `"l_shift"`, `"z"`, `"l_ctrl"`, `"space"` etc.)
- **Navigation**: `"left"`, `"up"`, `"down"`, `"right"`
- **Numpad**: `"num_lock"`, `"num_0"` through `"num_9"`, `"num_plus"`, `"num_enter"`, etc.
- **Special keys**: `"omen"`, `"calculator"`, `"settings"`, `"power"`, `"p_icon"` (The icon beneath the P key)

## Device Support & Contributions

Currently, this program specifically targets the **HP Gaming Keyboard II (0d62:54bf)** with **per-key** RGB lighting. 

Support for **4-zone Omen/Victus/Omen Max keyboards** may be added in the future if a tester with the physical device is found to verify drivers. If you own a 4-zone Omen keyboard and are willing to help test, please contact **arfelious@proton.me**.

## Disclaimer

> This software is not affiliated with, authorized, maintained, sponsored, or endorsed by HP (Hewlett-Packard) or any of its affiliates. Use this software at your own risk. The authors and contributors assume no responsibility or liability for any potential hardware damage, data loss, or system issues resulting from using this software.

