# Omen RGB Linux

A high-fidelity, per-key lighting controller for the **HP Omen Max 16** keyboard (**HP Gaming Keyboard II**, USB ID **0d62:54bf**) on Linux.

## Features
- **SDK**: Python library for custom lighting scripts.
- **CLI**: Control your keyboard from the terminal.
- **GUI**: Control your keyboard with graphical interface.
- **Hardware effects**: select one of the keyboard MCU's twelve built-in animations, and one of
  the lightbar's nine, with a single report — they keep running after the process exits.
- **Per-LED addressing**: a key is not one LED. Dual-legend keys have two, Space has five,
  backspace six, and each is individually addressable.
- **48 keyboard layouts**, derived from OMEN Gaming Hub's own tables and keyed to 92 board ids,
  so a board other than the one this was written on gets its own key map rather than a guess.

The wire protocol is documented in [docs/PROTOCOL.md](docs/PROTOCOL.md).

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

# One LED rather than one key — Esc has two, and this lights only the lower one
sudo python3 scripts/omen_cli.py set-led 1 '#ff0000'

# Which keyboard is this, and what are its keys called
python3 scripts/omen_cli.py layouts
sudo python3 scripts/omen_cli.py keys
sudo python3 scripts/omen_cli.py --layout Starmade/German static '#ff9900'

# Everything acknowledges and nothing lights? Hand the LEDs back to the keyboard
sudo python3 scripts/omen_cli.py unstick

# Control Bottom Lightbar (supports hex codes or RGB integer components)
sudo python3 scripts/omen_cli.py lightbar static '#ff9900'
sudo python3 scripts/omen_cli.py lightbar zones '#ff9900' '#00ff00' '#0000ff' '#ffff00'
sudo python3 scripts/omen_cli.py lightbar zones 255 0 0 0 255 0 0 0 255 255 255 0
sudo python3 scripts/omen_cli.py lightbar off

# Hardware effects — the keyboard MCU renders these itself, one report, no host process
python3 scripts/omen_cli.py effect list
sudo python3 scripts/omen_cli.py effect set ghosting
sudo python3 scripts/omen_cli.py effect set wave '#faac0f' '#0ffa36' --speed fast --direction left-to-right
sudo python3 scripts/omen_cli.py effect set ripple --theme ocean --size large
sudo python3 scripts/omen_cli.py effect set color-cycle --persist   # survives a reboot
sudo python3 scripts/omen_cli.py effect show                        # read the MCU's state back
sudo python3 scripts/omen_cli.py effect defaults                    # firmware lighting reset

# The lightbar's own nine animations (a different numbering — see docs/PROTOCOL.md)
python3 scripts/omen_cli.py lightbar animation list
sudo python3 scripts/omen_cli.py lightbar animation wave --theme ocean --speed fast
sudo python3 scripts/omen_cli.py lightbar animation swipe --theme custom '#ff0000' '#0000ff'
```

### Hardware effects vs. `rainbow`

`rainbow` is host-rendered: nine reports per frame, redrawn forever, and it stops when you do.
`effect set color-cycle` asks the MCU for the same thing in one report and it keeps running with
nothing attached. Prefer the effect engine unless you need per-key control of the pattern.

Two effects need their arguments chosen with care, and render **black** otherwise — the CLI warns
you, and [docs/PROTOCOL.md](docs/PROTOCOL.md) explains why:

- `swipe` has no preset palette; give it custom colours.
- `audio-pulse` is host-fed — `--inner` and `--outer` *are* the animation, and at 0 it draws
  nothing. To make it react to audio you have to re-send the record from your own audio thread at
  about 5 Hz.

There is no working brightness command on this keyboard: HP's `0x0C` is refused by the firmware,
and no effect consumes the record's brightness field. The Fn backlight key is the lever.

### Checking the frames without a keyboard

```bash
python3 tests/test_frames.py
```

No hardware, no dependencies, no test framework. It stubs `hidapi` and compares the bytes this
driver would send against frames transcribed from a USB capture of OMEN Gaming Hub driving the
same device — so a change that stops matching HP's client fails here rather than on someone's
desk.

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

#### Constructor: `OmenKeyboard(key_map_path=None, layout=None)`
Initializes the driver, connects to the keyboard, and works out which keyboard it is.
- **Parameters**:
  - `key_map_path` (*str*, optional): Custom path to the `keys.json` file. If not provided, it defaults to `data/keys.json` relative to the package root.
  - `layout` (*str*, optional): Force a layout id from `data/keyboards.json`, e.g. `"Dojo/JP"`. If not provided, the layout is detected from the DMI board name.
- **Raises**:
  - `RuntimeError`: If the HP Gaming Keyboard II lighting interface cannot be found.
  - `ValueError`: If `layout` names a layout the catalogue does not have.
- **Attributes**: `layout` (the detected `Layout`), `board` (the DMI board name), `live_positions` (how many LED positions light up), and `layout_warning` — a string to show the user when the board was not recognised or its layout has never been verified on hardware, `None` otherwise.

> Writing to raw USB devices requires root permissions by default on most Linux systems. Run your SDK scripts using `sudo python3 script.py` or configure appropriate `udev` rules.

### API Methods

#### `set_key_color(key_name, r, g, b)`
Set the RGB color of every LED of a key in the buffer.
- **Parameters**:
  - `key_name` (*str*): The identifier of the key to modify (e.g., `"esc"`, `"space"`, `"a"`, `"num_0"`). HP's own names work too (`"KeyEsc"`). See [Key Mapping Reference](#key-mapping-reference) for details.
  - `r` (*int*): Red channel value (0–255).
  - `g` (*int*): Green channel value (0–255).
  - `b` (*int*): Blue channel value (0–255).
- **Returns**: `bool` – `True` if the key exists on this keyboard and the color was set; `False` otherwise.
- **Notes**: A key owns as many LEDs as it has, and all of them take the colour. The `"p"` key owns the logo beneath it, which HP's table groups with it — the old separate `"p_icon"` name still resolves.

#### `set_led_color(position, r, g, b)`
Set the RGB color of a single LED, addressed by colour-map position rather than by key. This is how one printed legend of a dual-legend key takes its own colour.
- **Parameters**:
  - `position` (*int*): Colour-map position, `0` to `live_positions - 1` (176 positions on 8D87).
  - `r` (*int*), `g` (*int*), `b` (*int*): RGB channel values (0–255).
- **Returns**: `bool` – `True` if the position is on the map; `False` otherwise.

#### `key_leds(key_name)` / `keys()`
`key_leds` returns the list of colour-map positions a key owns, or `None` if this keyboard has no such key. `keys()` returns every key name, in colour-map order.

#### `set_all(r, g, b)`
Set the color of every LED across the entire keyboard to a static color.
- **Parameters**:
  - `r` (*int*), `g` (*int*), `b` (*int*): RGB channel values (0–255).

#### `apply(persist=True)`
Writes the buffered colors to the keyboard hardware — nine colour pages, then command `0x0a`.

`0x0a` is HP's `StoreLightingToFlash`: it writes **MCU flash**, which is why lighting survives a
reboot. Anything drawing frames in a loop should pass `persist=False` so it is not writing flash
tens of times a second. The colours still display; they just do not persist.

#### `set_effect(setting, persist=False)`
Select one of the MCU's twelve hardware-rendered animations. `setting` is an `EffectSetting` or
just an effect name, in which case HP's own defaults for that effect are used.

```python
from src import OmenKeyboard, EffectSetting

kb = OmenKeyboard()
kb.set_effect("ghosting")                       # HP's defaults: Jungle, medium
kb.set_effect(EffectSetting("wave",
                            colors=[(0xFA, 0xAC, 0x0F), (0x0F, 0xFA, 0x36)],
                            speed="fast",
                            direction="left-to-right"))
kb.set_effect(EffectSetting("ripple", show_mode="ocean", ripple_size="large"))

for w in EffectSetting("swipe", show_mode="volcano").warnings():
    print(w)                                    # "renders BLACK on a preset..."
```

One frame is all it takes: the animation runs with the process exited and nothing maintaining it.

#### `get_effect()`
Read the installed effect record back off the MCU (command `0x83`). Returns a decoded dict, or
`None` if the device refused. This is real state — but it is the MCU's *merged* record, and a
readback that matches what you wrote does not prove anything lit. Look at the keyboard as well.

#### `get_device_info()` / `set_lighting_on(on)` / `restore_lighting_defaults()` / `store_to_flash()`
Commands `0x80`, `0x09`, `0x10` and `0x0a`. `restore_lighting_defaults()` is a firmware-level
lighting reset and is the thing to reach for if lighting ends up in a state nothing else clears.

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

# 4. Run one of the nine device-side animations
lb.set_animation("wave", theme="ocean", speed="fast")
lb.set_animation("swipe", theme="custom", colors=[(255, 0, 0), (0, 0, 255)])
lb.set_animation("audio-pulse", theme="custom", colors=[(0, 0, 255), (255, 0, 255)],
                 levels=(100, 100))   # the levels ARE the animation; feed them yourself

# 5. Turn off lightbar
lb.turn_off()
```

> Ask this device for `#FFFFFE` rather than `#FFFFFF`. The firmware substitutes exactly two input
> values, and `#FFFFFF` becomes a visibly purple-white `#FEA3DA`. `OmenLightbar` rewrites it for
> you; set `AVOID_FIRMWARE_WHITE = False` to send values verbatim.



### Key Mapping Reference

Key names are mapped to the LED positions they own in `data/keys.json`. Available keys are organized in the following categories:

- **Row 0–5**: Standard keyboard rows (e.g. `"esc"`, `"f1"`, `"tilde"`, `"1"`, `"tab"`, `"q"`, `"caps_lock"`, `"a"`, `"l_shift"`, `"z"`, `"l_ctrl"`, `"space"` etc.)
- **Navigation**: `"left"`, `"up"`, `"down"`, `"right"`
- **Numpad**: `"num_lock"`, `"num_0"` through `"num_9"`, `"num_plus"`, `"num_enter"`, etc.
- **Special keys**: `"omen"`, `"calculator"`, `"settings"`, `"power"`

`sudo omen_cli keys` prints the list with the LED positions of each. Two details are worth
knowing before you write against it:

- **A key is not an LED.** Most keys own one; a key with two printed legends owns two, Space
  owns five and backspace six. `set_key_color` colours all of a key's LEDs; `set_led_color`
  colours one. Which LED of a pair is the upper legend is not in HP's data — the tables give
  every LED of a key the key's own rectangle — so it takes one `set-led` and a look.
- **`"p"` owns the illuminated logo below it**, positions 81 and 175. HP's table groups them,
  so it is one key with two LEDs rather than a key plus a `p_icon`; the old name still resolves
  for saved profiles. The bottom-row key right of the right Alt is HP's `KeyCopliot`, named
  `"copilot"` here; `"r_ctrl"` still resolves to it.

## Device Support & Contributions

This program targets HP keyboards with **per-key** RGB lighting behind the **HP Gaming Keyboard
II (0d62:54bf)** MCU interface.

`data/keyboards.json` carries the key maps for **48 OMEN keyboards across 92 board ids**,
derived from OMEN Gaming Hub's own embedded layout tables. Layout detection reads the DMI board
name and picks from that table; `omen_cli layouts` shows what it found and what else is there.

**Only one of the 48 has been watched light up** — `Dojo/Global`, board 8D87, the OMEN MAX 16
this was written on. The rest come out of the same tables by the same rule and nobody has run
one, which is what the *unverified* marking means. If you have another OMEN and are willing to
try `--layout`, a report either way is useful: the failure mode is not a crash, it is the wrong
keys lighting up.

Support for **4-zone Omen/Victus/Omen Max keyboards** is a different transport entirely (WMI,
not HID) and may be added in the future if a tester with the physical device is found to verify
drivers. If you own a 4-zone Omen keyboard and are willing to help test, please contact
**arfelious@proton.me**.

## Disclaimer

> This software is not affiliated with, authorized, maintained, sponsored, or endorsed by HP (Hewlett-Packard) or any of its affiliates. Use this software at your own risk. The authors and contributors assume no responsibility or liability for any potential hardware damage, data loss, or system issues resulting from using this software.

