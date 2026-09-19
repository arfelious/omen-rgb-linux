# Omen RGB Linux - Python SDK Examples

This directory contains standalone Python SDK example scripts demonstrating how to interact programmatically with the various HP OMEN and Victus lighting interfaces.

## Available Examples

| File | Target Hardware | Description |
|:---|:---|:---|
| **[`four_zone.py`](four_zone.py)** | 4-Zone RGB keyboards | Shows querying live zone status, configuring individual zones (`wasd`, `left`, `center`, `right`), applying all zones at once, and automatic key-to-zone routing. |
| **[`single_zone.py`](single_zone.py)** | Single-Zone RGB keyboards (e.g. Victus) | Shows controlling single-zone RGB backlight intensity and overall brightness via the Linux Multicolor LED subsystem. |
| **[`per_key.py`](per_key.py)** | Per-Key RGB keyboards (HP Gaming Keyboard II / `0d62:54bf`) | Shows setting colors for individual physical keys (WASD cluster, navigation arrows, ESC, Spacebar) and dual-LED P key synchronization via USB HID. |
| **[`lightbar.py`](lightbar.py)** | Bottom Lightbar (OMEN MAX) | Demonstrates configuring static color, distinct 4-zone colors, brightness control, and turning off the bottom lightbar. |
| **[`rainbow.py`](rainbow.py)** | All devices | A dynamic rainbow wave animation that automatically adapts to the connected hardware (4-zone wave, single-zone cycling, per-key wave, and lightbar sync). |

---

## Running the Examples

Because controlling raw USB HID or sysfs LED nodes requires root permissions, execute scripts with `sudo`:

```bash
# 4-Zone Keyboards (OMEN)
sudo python3 examples/four_zone.py

# Single-Zone Keyboards (Victus)
sudo python3 examples/single_zone.py

# Per-Key Keyboards (OMEN Max 16)
sudo python3 examples/per_key.py

# Bottom Lightbar
sudo python3 examples/lightbar.py

# Rainbow Animation
sudo python3 examples/rainbow.py
```
