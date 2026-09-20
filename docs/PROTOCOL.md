# HP GAMING KEYBOARD II LIGHTING INTERFACE SPECIFICATION

## 1. GENERAL AND SCOPE

This specification defines the low-level lighting control protocol, wire layout, register behaviors, and firmware quirks for the HP Gaming Keyboard II subsystem and its companion chassis light bar.

### 1.1 Source Material and Scope

The protocol parameters documented herein are established through:

1. **Passive USB Bus Traces:** Frame-by-frame analysis of vendor control software driving hardware routines, palette selections, and real-time animation feeds.
2. **Decompiled Vendor Binaries:** Static analysis of vendor control suite v1101.2607.3.0 (`McuSDK2.dll`, `HP.Omen.Core.Common.StarmadeKbLightingEffectCommandHelper`, and `KbAnimationDefaultSetting_Voco.json` embedded in `HP.Omen.Core.Model.DataStructure.dll`) providing wire enumerations, record structures, and nominal field limits.
3. **Embedded Layout Manifests:** Assembly manifests extracting `KBKeys*Data` tables and `DeviceList.json`. These define the mapping between LED array byte offsets, physical switch assemblies, and DMI system board identifiers.
4. **Empirical Hardware Observation:** Direct visual verification of all matrix states, effect routines, boundary quirks, and modifier overlays on physical machinery (HP OMEN MAX 16, board IDs `8D87` and `8D41`).

### 1.2 SDK Architecture Differentiation

Hardware governed by this specification interfaces exclusively via **`McuSDK2`**. It is completely incompatible with legacy **`McuSDK`** implementations (`KeyboardCommandHelper`, 23-byte `LightingEffectSetting`, `BLength = 22`, `COLOR_PAGE_1/2/3 = 60/60/24`). Legacy SDK parameters describe different hardware and must not be referenced.

---

## 2. PHYSICAL AND LINK LAYER PROTOCOL

The lighting microcontroller enumerates as USB device `0d62:54bf`, interface 3 (`MI_03`), usage page `0xFF01`. Reports have a fixed length of 64 octets, prefixed by a 4-octet header:

```
Octet  0      : Command identifier (Opcode)
Octet  1      : Sub-index / Target selector
Octet  2      : Block length (BLength), low-order byte
Octet  3      : Block length (BLength), high-order byte
Octet  4..63  : Payload data (60 octets)

```

The microcontroller does not implement HID report numbering; octet 0 of the host buffer maps directly to octet 0 on the USB bus. Writing 64-octet buffers via `hidraw` preserves direct byte alignment provided the leading octet is non-zero.

Status replies returned via the IN endpoint omit report identifiers. Response offsets align directly with request frames (buffer offset `[4]` constitutes payload octet 0 in both directions).

---

## 3. COMMAND DISPATCH MATRIX

| Opcode | Designation | Index | Length | Payload Definition |
| --- | --- | --- | --- | --- |
| `0x03` | `SetLightingEffect` | Target (`0`) | 36 | 36-octet effect control record (see Section 6) |
| `0x05` | Static Red Channel | Page `0..2` | 0 | 60 octets static red matrix |
| `0x06` | Static Green Channel | Page `0..2` | 0 | 60 octets static green matrix |
| `0x07` | Static Blue Channel | Page `0..2` | 0 | 60 octets static blue matrix |
| `0x09` | `SetKeyboardLightingOnOff` | 0 | 1 | Control argument: `0x01` (prep/enable), `0xFF` (blank) |
| `0x0A` | `StoreLightingToFlash` | Target (`0`) | 2 | Fixed sequence: `0xAC 0x53` |
| `0x0C` | `SetKeyboardBrightness` | 0 | 1 | Intensity value (**Unacknowledged / Times out**) |
| `0x10` | `RestoreLightingToDefault` | 7 | 4 | Fixed sequence: `0x94 0x10 0x98 0x27` |
| `0x80` | `GetDeviceInfo` | 1 | 0 | Status query (interrogation) |
| `0x83` | `GetLightingEffect` | Target (`0`) | 0 | Read merged effect state |

The `Target` field accepts `0` (`ALL_LED_AREA`), representing the keyboard matrix. Indices `1` and `2` designate mouse peripheral targets (logo and scroll wheel).

* **Unused/Vendor Opcodes:** `0x01` (`StoreSettingToFlash`), `0x02` (`StoreMacroToFlash`), and `0x0B` (`SyncLightingEffect`) exist in dispatch tables but are unreferenced by driver operations.
* **Unimplemented/Unacknowledged Opcodes:** `0x04` (`SetUserModeEnable`) fails to produce an acknowledgement and must be treated as unimplemented. `0x0D` is never emitted by the host suite.

### 3.1 Static Block Length Framing

Submitting `BLength = 0` (`Raw[2] = 0x00, Raw[3] = 0x00`) on static color submissions (`0x05`, `0x06`, `0x07`) is required by the hardware decoder. The host transmits three successive 60-octet segments per color channel (nine total frames to execute a full matrix repaint).

Driver buffers maintaining 186 octets per channel must store two zeroed octets at the head of each 62-octet page slice to preserve framing.

### 3.2 Volatile vs. Non-Volatile Memory Retention

* **Volatile Refresh (`persist=False`):** Color matrices and effect parameters take immediate effect in controller RAM upon submission. Volatile updates execute without invoking `0x0A`. Interactive animations and real-time color streaming must run in this mode to avoid flash wear.
* **Flash Persistence (`0x0A`):** Writing `0xAC 0x53` via command `0x0A` commits active RAM tables to non-volatile MCU storage, preserving lighting state across power cycles. Due to finite flash write cycles, `0x0A` must never be called in continuous rendering loops.

### 3.3 Link Status Acknowledgement

Command frames are confirmed by echoing the request header with status flags at payload positions `[4]` and `[5]`:

* `0xEC 0xAC`: Frame parsed and accepted by MCU registers.
* `0xEC 0xFA`: Frame syntax or parameters rejected.

> **Operational Warning:** Status codes reflect register acceptance only; they do not verify physical drive by the LED output circuitry. Fully qualifying a hardware state requires a state readback query alongside physical inspection.

### 3.4 Opcode Quirks (`0x0C` and `0x09`)

* **Brightness Command `0x0C` Failure:** Command `0x0C` is not implemented in this firmware generation. Submissions with arguments `0, 1, 2, 3, 50, 100` fail to generate an acknowledgement frame, resulting in transport-level timeouts.
* **Master State Control `0x09`:** Argument `0x01` must be transmitted immediately prior to static color page series. Argument `0xFF` forces immediate hardware matrix blanking. Submitting `0x00` **does not** undo blanking; restoring matrix illumination requires actuating the hardware `Fn` backlight toggle key, which signals the embedded controller (EC) to fire an asynchronous WMI event.

---

## 4. STATIC COLOUR MATRIX

Static matrix lighting uses opcodes `0x05` (Red), `0x06` (Green), and `0x07` (Blue). Each channel is divided into three 60-octet segments with `BLength = 0`.

Elements in the matrix address individual LED emitters, not physical key switches. Many physical key assemblies contain two or more discrete emitters. For example, logical offsets `0` through `9` address ten independent diodes across key assemblies `Esc`, `F1`, `F2`, `F3`, and `F4`. On `Esc`, offset `0` illuminates the top legend diode, while offset `1` illuminates the lower diode.

### 4.1 Frame Buffer Translation

Logical emitter indices translate to serialized channel buffer offsets across interleaved page headers:

```
Logical Indices   0..59   ->  Buffer Offsets   2..61   (Page 0)
Logical Indices  60..119  ->  Buffer Offsets  64..123  (Page 1)
Logical Indices 120..179  ->  Buffer Offsets 126..185  (Page 2)

```

Because logical elements `58` through `63` span a page boundary, linear block writes must preserve zeroed `BLength` bytes at offsets `62..63` and `124..125` to prevent data byte displacement.

### 4.2 Array Sizing and Physical Allocation

A complete transfer transmits three 60-octet segments per channel (180 octets). The active keyboard matrix implements 176 operational LED circuits. Trailing positions `176..179` represent dead fill octets required to complete the third 60-octet transfer.

* **Positional Indexing:** Byte offsets dictate matrix indices rather than Cartesian geometry. Key legend orders vary: function keys map the primary legend to the lower index, whereas numeric keys place the base glyph at the lower index and the shifted character at the higher index.
* **Discontinuous Key Switches:** While most key switch emitters are contiguous, select assemblies are split. On verified hardware layouts (`8D87`, `8D41`), key assembly `KeyP` addresses diode indices `81` and `175`.
* **HID LampArray Divergence (`MI_04`):** The secondary HID LampArray interface on `MI_04` exposes a coarse 120-lamp topology. It merges multi-emitter switches into single lamps and completely omits eight functional keys (`Omen`, `Calculator`, `Settings`, `Power`, `Fn`, `Copilot`, among others). True per-diode addressing is only achievable via Interface 3.

### 4.3 DMI Board Revision and Zero-Fill Boundaries

Sub-allocations within the 180-octet static table are determined by platform generation:

| System Board / Layout | Resource Manifest | Unused / Zeroed Indices |
| --- | --- | --- |
| Dojo / Vibrance, cycle ≤ 260 (25C1, e.g., `8D87`) | `DojoKBKeysGlobalData.json` | `176..179` |
| Dojo / Vibrance, cycle > 260, non-JP | `DojoKBKeysGlobalData26C1.json` | `137..138`, `146` |
| Dojo / Vibrance, cycle > 260, JP | `DojoKBKeysJPData26C1.json` | `174..176`, `179` |

Indices `137` and `138` map to `KeyDot`; index `146` maps to the terminal emitter of `KeyShiftR`. Erroneously applying cycle > 260 padding rules to a 25C1 controller blanks these working diodes. Drivers must evaluate DMI board identifiers (`/sys/class/dmi/id/board_name`) rather than marketing model strings to resolve the correct layout table.

---

## 5. HARDWARE MODIFIER HANDLING & SYSTEM LOCKOUT

### 5.1 Internal Fn Matrix Override

The physical `Fn` key is intercepted and serviced directly by the keyboard MCU. Actuation triggers an internal firmware override: valid combination keys light up in purple while remaining keys are blanked.

* **Interface 3 Restoration:** When `Fn` is released, the MCU repaints the base lighting layer directly from its internal RAM registers. No host driver interaction or polling is involved.
* **Interface 4 (`MI_04`) Failure:** Host frames written via the `MI_04` LampArray interface do not reside in the MCU's autonomous memory. When `Fn` is released after a LampArray paint, the keyboard remains blank indefinitely until refreshed by the host.

### 5.2 Autonomous Mode Lockout (`AutonomousMode = 0`)

Writing `AutonomousMode = 0` via HID LampArray Feature Report 6 on `MI_04` commands the MCU to disable internal lighting pipelines and await external host streaming:

* Standard Interface 3 commands continue to acknowledge (`0xEC 0xAC`) but display no light.
* Lockout state outlives software shutdowns and warm reboots because internal USB bus power persists.
* Report 6 is strictly write-only and cannot be interrogated.

**Recovery:** Transmit `AutonomousMode = 1` via Feature Report 6 on `MI_04`. Alternatively, execute a complete hardware discharge by disconnecting AC power and holding the chassis power button.

---

## 6. EFFECT CONTROL BLOCK (COMMAND `0x03`)

Hardware effects are configured using a 36-octet command frame (`BLength = 36`):

```
Octet  0      : Effect identifier (Wire ID; see Section 6.3)
Octet  1      : ShowMode
                0 = Single custom colour
                1 = Multiple custom colours
                2 = Preset: Volcano
                3 = Preset: Jungle
                4 = Preset: Ocean
                5 = Preset: Rainbow (Wave routine only)
Octet  2      : ColorNumber (0-based count: n - 1; value 4 = Preset in use)
Octet  3      : LedSpeed (0 = Slow, 1 = Medium, 2 = Fast)
Octet  4      : Brightness (0..3 = Step levels, 100 = Max; ignored by firmware)
Octet  5      : Direction (Vector mapping):
                0 = Inward
                1 = Outward
                2 = Right-to-Left
                3 = Left-to-Right
                4 = Up
                5 = Down
                6 = Clockwise
                7 = Counter-Clockwise
Octet  6      : RippleSize (0 = Small, 1 = Medium, 2 = Large)
Octet  7      : RaindropFrequency (Mirrors LedSpeed [Octet 3])
Octet  8      : InnerBrightness (Treble amplitude; Audio Pulse only)
Octet  9      : OuterBrightness (Bass amplitude; Audio Pulse only)
Octet 10..23  : Reserved (Pad with 0x00)
Octet 24..26  : Colour 1 (R, G, B) - Bass/Outer color in Audio Pulse
Octet 27..29  : Colour 2 (R, G, B) - Treble/Inner color in Audio Pulse
Octet 30..32  : Colour 3 (R, G, B)
Octet 33..35  : Colour 4 (R, G, B)

```

Although host packets carry 64 bytes on the wire (including color slots 5 and 6 at octets `36..41`), the MCU parser terminates at octet 35 per `BLength = 36`.

### 6.1 Register Merging Architecture

The MCU does not overwrite internal state unconditionally. A `0x03` submission updates **only** the register fields consumed by the specified effect. All unconsumed registers retain their previous values:

* An unconsumed parameter cannot be zeroed out unless the active effect consumes that field. (For example, clearing residual `InnerBrightness` values requires selecting Audio Pulse and transmitting zeros).
* Hardware effect brightness (Octet 4) is not consumed by the animation engines and reads back at an immutable value of `160`.

### 6.2 State Readback Query (`0x83`) and Parser Safeguards

Executing command `0x83` returns the combined MCU register block:

```
Octet  1      : EffectTargetIndex
Octet  4      : Active Effect Identifier (or 0xEC on refusal)
Octet  5      : ShowMode                 (or 0xFA on refusal)
Octet  6      : ColorNumber
Octet  7      : LedSpeed
Octet  8      : Brightness
Octet  9      : Direction
Octet 10      : RippleSize
Octet 11      : RaindropFrequency
Octet 12      : InnerBrightness
Octet 13      : OuterBrightness
Octet 28..45  : Six 3-octet RGB colour definitions (18 octets)

```

> **Parser Alert:** If octets `[4]` and `[5]` evaluate to `0xEC 0xFA`, the readback command was refused. Software parsers must check for this condition prior to decoding octet `[4]` as an active effect identifier.

### 6.3 Effect Enumeration & Operational Rules

| UI # | Effect Name | Wire ID | Vendor Identifier | Operational Constraints |
| --- | --- | --- | --- | --- |
| 1 | Color Cycle | 4 | `COLOR_LOOP` | Standard operation |
| 2 | Starlight | 7 | `SPARKLE` | Standard operation |
| 3 | Breathing | 2 | `BREATHING` | Standard operation |
| 4 | Ghosting | 8 | `GHOSTING` | Standard operation |
| 5 | Ripple | 9 | `RIPPLE` | Standard operation |
| 6 | Wave | 10 | `WAVE` | Exclusively supports Rainbow preset (`ShowMode = 5`) |
| 7 | OMEN X | 13 | `OMEN_X` | Standard operation |
| 8 | Raindrop | 12 | `RAINDROP` | `RaindropFrequency` [7] must mirror `LedSpeed` [3] |
| 9 | Audio Pulse | 14 | `AUDIO_PULSE` | Host-fed rendering loop; requires live magnitude updates |
| 10 | Confetti | 15 | `CONFETTI` | Custom colors rejected; operates on fixed internal palette |
| 11 | Sun | 16 | `SUN` | Custom colors rejected; operates on fixed internal palette |
| 12 | Swipe | 17 | `SWIPE` | Custom color mode mandatory (`ColorNumber != 4`) |

#### Effect Execution Caveats:

* **Swipe (Wire 17):** Must be configured with custom colors (`ShowMode = 0` or `1`). If submitted with `ColorNumber = 4` (preset mode), the keyboard remains unlit.
* **Audio Pulse (Wire 14):** Driven by an autonomous firmware routine that requires real-time host amplitude feeds. If octets `[8]` and `[9]` remain `0`, the matrix outputs black. The host driver must cycle updates at ~5 Hz:
* `InnerBrightness` [8] modulates the treble band.
* `OuterBrightness` [9] modulates the bass band.
* `Colour 1` (`[24..26]`) maps to bass/outer perimeter lighting.
* `Colour 2` (`[27..29]`) maps to treble/inner lighting.



---

## 7. SYSTEM TELEMETRY & BRIGHTNESS CONTROL

### 7.1 Status Query (`0x80`)

Submitting `0x80` returns hardware telemetry without a report ID prefix:

```
Byte Offset:  00 01 02 03 04 05 06 07 08 09 10 11 12
Value:        80 01 29 d0 00 00 00 00 01 00 03 01 c8
                                                |  |
                    Active Wire Effect ID ------+  +--- Backlight Intensity

```

* **Offset `[11]`:** Active effect wire identifier matching the table in Section 6.3.
* **Offset `[12]`:** Global backlight state (`0xC8` or `0xA0` = Active/Lit; `0x64` = Dark/Suspended).

*Alignment Note:* Host stacks inserting an artificial HID report-ID byte will read these values offset by +1 (indices `[12]` and `[13]`).

### 7.2 Brightness Mediation

Backlight intensity cannot be modified via Interface 3 commands. Physical LED brightness is controlled entirely through the embedded controller via the hardware `Fn` backlight toggle key.

---

## 8. AUXILIARY CHASSIS LIGHT BAR SUBSYSTEM

The front light bar is an independent peripheral controlled via ACPI WMI class `Keyboard`, command `0x0B`, passing a 128-octet payload. On Linux systems, this interface is addressed via `/proc/acpi/call`. It exposes four physical lighting zones ordered 0 to 3 from left to right.

### 8.1 WMI Command Structure

```
Octet  0      : Target Device (0 = Light Bar, 1 = FourZoneAni variant)
Octet  1      : Animation ID (0 = Static Colour, non-zero = Animation)
Octet  2      : Configuration Bitfield:
                Bits 0..1 : Speed (0 = Slow, 1 = Medium, 2 = Fast)
                Bits 2..3 : Direction (4 = Leftward, 8 = Rightward)
                Bits 4..7 : Theme Preset:
                            16 = Galaxy
                            32 = Volcano
                            48 = Jungle
                            64 = Ocean
                            80 = Custom
Octet  3      : Brightness (0..100)
Octet  4      : Treble level (Audio Pulse stream)
Octet  5      : Bass level (Audio Pulse stream)
Octet  6      : Colour Count (4 for static assignment)
Octet  7..18  : Zones 0 through 3, three octets per zone (R, G, B)

```

### 8.2 Light Bar Animation Routines

The light bar firmware implements 10 animation routines (routine `5` is unassigned):

* `1`: Lighting Sync
* `2`: Color Cycle
* `3`: Starlight
* `4`: Breathing
* `6`: Wave
* `7`: Raindrop
* `8`: Audio Pulse (requires host feed of bytes `[4]` and `[5]`)
* `9`: Confetti
* `10`: Sun
* `11`: Swipe (requires custom color assignment)

*Note:* Keyboard effects `Ghosting`, `Ripple`, and `OMEN X` do not exist on the light bar subsystem.

### 8.3 Firmware White Substitution Workaround

The light bar firmware contains a two-entry hardcoded lookup table:

* `#FF0000` is remapped to `#FE0000` (imperceptible change).
* `#FFFFFF` is remapped to `#FEA3DA`, emitting a distinct **violet-tinted white**.

Values adjacent to the lookup entries (such as `#FFFFFE` and `#FF0001`) pass through unmodified. Drivers must rewrite incoming pure white requests (`#FFFFFF`) to `#FFFFFE` prior to serialization.

### 8.4 Query Capabilities & Limitations

* **Static Colors:** Static RGB color state is readable through standard WMI query operations.
* **Animation and Brightness:** Animation state and brightness queries are unsupported by the firmware. Executing a Keyboard-class read (`0x0C`) returns `sign FAIL`, `RTCD 4`. Byte `[1]` of the query structure contains volatile scratchpad data rather than the active brightness level. Animation state and brightness changes must be verified via physical observation.