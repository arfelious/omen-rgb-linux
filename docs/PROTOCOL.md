# The HP Gaming Keyboard II lighting protocol

Everything this driver sends, and where each fact came from.

## Provenance and scope

Two independent sources, in the order that mattered:

1. **A USB capture of OMEN Gaming Hub driving the device.** Twelve seconds of OGH switching
   effects and dragging the colour picker, decoded frame by frame. This is what the client
   actually puts on the wire.
2. **The OGH 1101.2607.3.0 binaries**, decompiled — `McuSDK2.dll`
   (`General.GeneralCommandHelper`), `HP.Omen.Core.Common`
   (`StarmadeKbLightingEffectCommandHelper`), and `KbAnimationDefaultSetting_Voco.json`
   embedded in `HP.Omen.Core.Model.DataStructure.dll`. This is where the numbering, the enums
   and the per-effect defaults came from; a capture could never have produced them.

Then all twelve effects were written to real hardware and **looked at by a person**.

Two cautions about the second source, both learned expensively. HP ships more than one
keyboard SDK, and this device is served by **`McuSDK2`**, not the v1 `McuSDK`
(`KeyboardCommandHelper`, 23-byte `LightingEffectSetting`, `BLength = 22`,
`COLOR_PAGE_1/2/3 = 60/60/24`). The v1 path describes a *different keyboard* and none of its
byte-level claims hold here. And where a decompile and a capture disagree about this MCU, the
capture wins — the shipping client does not use every path in its own binary.

**Board scope.** All of this was measured on one machine: HP OMEN MAX 16-ak0098nr, board
`8D87`, BIOS F.07, EC 40.38 — on **Windows**. The frames are device-level, so nothing about
them should depend on the host OS, but the Linux side of this driver's effect support has not
been run on Linux. Treat the negatives in particular (command `0x0C`) as facts about this
firmware, not about the product line.

## Wire format

The MCU is USB `0d62:54bf`, **interface 3** (`MI_03`), usage page `0xFF01`. Reports are 64
bytes with a four-byte header:

```
[0]      Command
[1]      Index
[2]      BLength, low byte
[3]      BLength, high byte
[4..63]  payload, 60 bytes
```

The device does not use numbered HID reports, so byte 0 goes out as byte 0 on the wire. That
is why writing a 64-byte buffer whose first byte is the command works: `hidapi` hands the
buffer to `hidraw`, and `usbhid` only strips a leading byte when it is `0x00`.

Replies arrive on the IN endpoint with **no report-id byte**, so a reply's offsets are wire
offsets and line up with the request: `[4]` is `payload[0]` either way.

## Commands

| Cmd | Name | Index | BLength | Payload |
|---|---|---|---|---|
| `0x03` | **SetLightingEffect** | target | **36** | 36-byte effect record, below |
| `0x05` | static colour, red | page `0..2` | **0** | 60 bytes of the red key map |
| `0x06` | static colour, green | page `0..2` | **0** | 60 bytes of the green key map |
| `0x07` | static colour, blue | page `0..2` | **0** | 60 bytes of the blue key map |
| `0x09` | SetKeyboardLightingOnOff | 0 | 1 | `0` off, `1` on |
| `0x0A` | **StoreLightingToFlash** | target | 2 | `AC 53` |
| `0x0C` | SetKeyboardBrightness | 0 | 1 | physical value — **refused on this board** |
| `0x10` | RestoreLightingToDefault | `7` | 4 | `94 10 98 27` |
| `0x80` | GetDeviceInfo | 1 | 0 | — read |
| `0x83` | **GetLightingEffect** | target | 0 | — read, reply below |

`target` is `LightingEffectTarget`: `0` = ALL_LED_AREA, the only one a keyboard has. `1` and
`2` are a mouse's logo and wheel.

Commands `0x01` (StoreSettingToFlash), `0x02` (StoreMacroToFlash) and `0x0B`
(SyncLightingEffect) exist in HP's table and are not used here. Commands `0x04`
(`SetUserModeEnable`) and `0x0D` are never sent by OGH on this board, and `0x04` never
acknowledges — treat it as unimplemented rather than as a missing unlock.

### `BLength = 0` on the colour pages is correct

It looks like an omission and it is not. `GeneralCommandHelper.CreateStaticCMD` writes
`Raw[3] = 0; Raw[4] = 0` as literals and copies 60 bytes per page, three pages per channel —
nine frames for a full repaint — and OGH's own traffic shows `00 00` there on every page. The
`60/60/24` framing with a real `BLength` is the v1 SDK's, and it is not what ships.

This driver's 186-byte channel buffer with its first two bytes of each 62-byte chunk forced to
zero is exactly that layout: those two bytes *are* `BLength`.

### `0x0A` is a flash write, not a commit

`StoreLightingToFlash` writes MCU flash. That is why lighting survives a reboot — and why it
must not be looped. Colour and effect writes take hold without it; they just do not persist.

`apply()` still persists by default, because whether the colour pages display without it has
not been confirmed on this hardware. Anything drawing frames in a loop should pass
`persist=False`.

### Acknowledgement is not display

Every command is answered with the request echoed and a status at `[4],[5]`: `EC AC` accepted,
`EC FA` refused. **Both are firmware-level answers about the frame, not about the LEDs.**
During one stuck-keyboard session every frame HP's own client sent was acknowledged and nothing
displayed. Close a claim about this interface with two things: a `0x83` readback showing the
field changed, *and* a person looking at the keyboard. Neither alone has been sufficient.

## The effect record — command `0x03`

36 declared bytes. Field names are HP's.

```
[0]   Effect              effect id, wire numbering — table below
[1]   ShowMode            0 single custom colour   1 multiple custom colours
                          2 Volcano   3 Jungle   4 Ocean   5 Rainbow
[2]   ColorNumber         (n - 1) for n custom colours; 4 means "a preset is in use"
[3]   LedSpeed            0 slow   1 medium   2 fast
[4]   Brightness          0..3 = LV_01..LV_04, 100 = physical value
[5]   Direction           0 inward  1 outward  2 right-to-left  3 left-to-right
                          4 up  5 down  6 clockwise  7 counter-clockwise
[6]   RippleSize          0 small  1 medium  2 large
[7]   RaindropFrequency   0 slow  1 medium  2 fast
[8]   InnerBrightness     Audio Pulse only — treble level
[9]   OuterBrightness     Audio Pulse only — bass level
[10..23]  unused, zero
[24..26]  colour 1 R,G,B
[27..29]  colour 2
[30..32]  colour 3
[33..35]  colour 4
```

Colour bytes are RGB, confirmed against HP's own swatch palette (`#EA002A` crimson, `#0FFA36`
green, `#FA0FE7` purple, `#FAAC0F` yellow, `#0F36FA` blue).

Three fields are not what a reader would assume:

- **`ColorNumber` is a zero-based count.** Four custom colours send `3`. The value `4` is a
  sentinel — HP spells it `COLOR_NUMBER_PRESET` — meaning "ignore the colour block".
- **`ShowMode` merges two ideas.** `0` and `1` say how many custom colours there are; `2..5`
  name a preset instead, and the colour block is only meaningful for `0`/`1`.
- **`RaindropFrequency` is never set independently.** OGH assigns it the same value as
  `LedSpeed` for every effect, so `[3]` and `[7]` always match in a capture.

**Six colour slots reach the device and four are declared.** HP's builder writes colours 5 and
6 into `[36..41]`, and the report is 64 bytes so they are physically transmitted — but
`BLength` is 36, which ends the record at colour 4, and OGH's UI caps at four. Whether the MCU
would honour six under `BLength = 42` is untested. This driver does not send them.

### The MCU merges the record; it does not replace it

**A `0x03` frame only updates the fields the selected effect actually consumes.** Everything
else keeps whatever it held before. Measured four ways:

| sent | read back | reading |
|---|---|---|
| Wave, `Inner`/`Outer` = 0 (after a frame that set them to 200) | `Inner`/`Outer` = **200** | Wave does not consume them |
| Audio Pulse, `ShowMode`/`ColorNumber` = 0 (after a preset frame) | **3 / 4** | Audio Pulse has no theme control |
| Wave, `LedSpeed` = 0 and `Direction` = 0 | **0 / 0** | Wave *does* consume them |
| Audio Pulse, `Inner`/`Outer` = 150 | **150 / 150** | consumed |

Two consequences worth holding onto:

- **You cannot clear a field by sending zero** unless the current effect consumes it. To zero
  `InnerBrightness`, select Audio Pulse and send zero. A frame that "sets everything to
  defaults" does no such thing.
- **The `0x83` reply is merged state, not an echo.** A matching readback does not prove the
  firmware took that field from your frame.

The firmware's idea of which fields an effect uses matches OGH's UI option matrix, which was
read out of the view-model independently. Two unrelated sources, one answer — that matrix is
`EFFECT_INFO` in `src/effects.py`.

### Reply to `0x83`

```
[1]      EffectTargetIndex
[4]      Effect        [5] ShowMode   [6] ColorNumber   [7] LedSpeed
[8]      Brightness    [9] Direction  [10] RippleSize   [11] RaindropFrequency
[12]     InnerBrightness   [13] OuterBrightness
[28..45] six colour triples
```

`EC FA` at `[4],[5]` means the read was refused — not that the effect is zero.

### Effect numbering

OGH's dropdown is a 1-based list; the wire uses `LightingEffectType`, and the map
(`EffectCommandTable`) is not the identity.

| UI # | OGH name | wire | `LightingEffectType` |
|---|---|---|---|
| 1 | Color Cycle | `4` | COLOR_LOOP |
| 2 | Starlight | `7` | SPARKLE |
| 3 | Breathing | `2` | BREATHING |
| 4 | Ghosting | `8` | GHOSTING |
| 5 | Ripple | `9` | RIPPLE |
| 6 | Wave | `10` | WAVE |
| 7 | OMEN X | `13` | OMEN_X |
| 8 | Raindrop | `12` | RAINDROP |
| 9 | Audio Pulse | `14` | AUDIO_PULSE |
| 10 | Confetti | `15` | CONFETTI |
| 11 | Sun | `16` | SUN |
| 12 | Swipe | `17` | SWIPE |

The wire enum has values this list never reaches — `0` OFF, `1` STEADY, `3` BLINKING,
`5` STATIC_DPI_COLOR, `6` STATIC_SHUFFLE, `11` LINE_STREAK, `159` ALL_KEY_SINGLE_COLOR,
`160`/`161` WAVE_RIGHT_TO_LEFT / WAVE_LEFT_TO_RIGHT, `162` STATIC_TEMPLATE. Whether this
firmware implements any of them is untested, and it is the cheapest interesting experiment
left on this interface. Note that under the merge rule an unknown effect id may render using
retained fields, so prime the record first.

### All twelve render, including the two that look broken

Confirmed by writing each effect id and looking. Ten drew immediately on a preset palette. The
two that came up black did so for reasons that follow from the field map rather than
contradicting it:

- **Swipe requires custom colours.** Sent with `ColorNumber = 4` it renders **black**; sent
  with two custom colours it sweeps. That is why OGH offers Swipe no presets — a firmware
  constraint, not a UI preference.
- **Audio Pulse is device-side but host-fed.** Sent with both levels at `0` it renders
  **black**; sent at `200` with no audio playing at all, it pulses. Reproducing it is a ~5 Hz
  loop feeding two bytes, not a per-key renderer. OGH re-sends the record every 200 ms with the
  high band in `InnerBrightness` and the low band in `OuterBrightness`; colour 1 is bass/outer
  and colour 2 treble/inner.

A black keyboard is a reading, not a failure. Recording these two as "Audio Pulse and Swipe do
not work" would have been two false negatives written down as settled.

Also: `Rainbow` (`ShowMode = 5`) is offered for Wave only, but nothing in the frame restricts
it — OGH simply hides the button. Confetti and Sun take no custom colours at all.

## Brightness: there is no working lever

**Command `0x0C` does not work on this board.** The frame is not acknowledged at any payload
value — `0`, `1`, `2`, `3`, `50`, `100` — while five other commands are acknowledged through
the same handle and the same frame builder. Five accepted and one refused across six payloads
is the command being rejected, not the transport failing.

It is in HP's command table and `McuSDK2` composes it, so it is real somewhere; it is not
implemented in this firmware.

**And brightness is not a property of an effect either.** `Brightness` at `[4]` read back
`160` unchanged through every frame ever sent, which under the merge rule means no effect
consumes it. So a device-rendered effect runs at whatever brightness the firmware chose, and
nothing on this interface changes it. The Fn backlight key does.

## `GetDeviceInfo` — command `0x80`

A typical reply, as it arrives (no report-id byte):

```
80 01 29 d0 00 00 00 00 01 00 03 01 c8
                                 ^^ ^^
                        effect ──┘  └── brightness
```

Two bytes here move. `[11]` is the effect id **in the same wire numbering `0x03` uses** — it
reads `0x08` when `0x83` independently reports Ghosting. `[12]` tracks the backlight: `0xC8` /
`0xA0` while lit, `0x64` while dark.

Get the alignment right. HP's own code indexes a buffer that *does* carry a report-id byte, so
its `data[11]`/`data[12]` are these plus one. The rival alignment gives a brightness of `0x01`,
which is plausible and meaningless.

## Command `0x09` is two-argument, not a blanking command

Argument `0x01` is what OGH sends immediately before every colour round. Argument `0xFF`
**blanks the keyboard**, and `0x09`/`0x00` does not undo it — the Fn backlight key does,
instantly, with every HP service stopped. The master lighting state lives in firmware and the
EC raises a WMI event *after* the key is pressed, so the host is told, never asked.

Do not generalise from one argument to the command.

## The light bar is a different device

Not HID at all: WMI class `Keyboard`, command `0x0B`, one 128-byte payload, reached on Linux
through `/proc/acpi/call`. Four zones, zone 0 leftmost.

```
[0]      TargetDevice   0 = light bar, 1 = FourZoneAni (the four-zone keyboard variant)
[1]      effect         0 = static colour; non-zero selects an animation
[2]      bits 0-1 speed      slow 0  medium 1  fast 2
         bits 2-3 direction  left 4  right 8       (two directions, not the keyboard's six)
         bits 4-7 theme      galaxy 16  volcano 32  jungle 48  ocean 64  custom 80
[3]      brightness     0..100
[4]      tribe          } audio-pulse levels, host-fed
[5]      bass           }
[6]      colour count   4 for a static colour
[7..18]  four zones, R,G,B each, zone 0 first
```

**Nine animations**, all written and looked at: `1` lighting sync, `2` ColorCycle,
`3` Starlight, `4` Breathing, `6` Wave, `7` Raindrop, `8` AudioPulse, `9` Confetti, `10` Sun,
`11` Swipe. `5` is unassigned.

**This numbering is not the keyboard's**, and Ghosting, Ripple and OMEN X do not exist here at
all. OGH's twelve-item keyboard list and this nine-item list are two device paths merged in one
UI. Always name the device along with the number — mixing the two is the single most common way
to get lost in this part of the machine.

The same two effects fail the same way as on the keyboard, for the same two reasons: **Swipe**
is custom-colour only, and **Audio Pulse**'s levels *are* the animation rather than an enable
for it. Held constant, Audio Pulse shows a steady colour and keeps showing it after the process
exits. Predicted from the keyboard result and confirmed first try.

### Never ask this device for `#FFFFFF`

The firmware special-cases exactly two input values:

| asked | stored | looks like |
|---|---|---|
| `FF0000` | `FE0000` | indistinguishable from `FF0001` — harmless |
| `FFFFFF` | `FEA3DA` | **purple-white**, next to a plainly white `FFFFFE` |

Everything else tested passes through byte-exact, including `FF0001`, one bit away from a
substituted value. That rules out a calibration curve, a per-channel clamp and a gamma table:
it is a lookup with two entries. `OmenLightbar.AVOID_FIRMWARE_WHITE` rewrites `#FFFFFF` to
`#FFFFFE` for this reason; set it `False` to send values verbatim.

### What the bar cannot tell you

**Colours are readable and animation state is not.** HP's only Keyboard-class read
(`0x0C`) returns `sign FAIL`, `RTCD 4` on this board. **Brightness is not readable either** —
byte `[1]` of the support reply looks like brightness and is scratch; it read `0x7D` after a
write whose green channel was `0x7D`, and stayed there across brightnesses of 30, 75, 5 and
100. HP's own code reads only bit 1 of byte `[0]` from that reply, and that now looks like
knowledge rather than laziness.

So an animation or a brightness written to the bar can only be confirmed by looking at it.

## A note on method

The rule that produced most of the above, stated once because it cost the most to learn:

> **Verify by outcome, not by return code.** A command that acknowledges has told you the
> firmware parsed your bytes. It has told you nothing about the LEDs. The failure mode is a
> false success — bytes good, light wrong — and several confident wrong claims in this work had
> exactly that shape.

The corollary for anyone extending this: a buffer is not state until you have watched it change
in response to something you did. Read the same field twice with a visible change in between.
It takes a minute and it catches the expensive kind of mistake.
