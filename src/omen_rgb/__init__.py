"""
Omen RGB Linux - HP OMEN RGB Keyboard & Lightbar Control
"""

from .driver import OmenKeyboard, ZONE_NAMES_4, restore_device_lighting_control
from .lightbar import OmenLightbar, LB_ANIMATIONS, LB_THEMES, LB_SPEEDS, LB_DIRECTIONS
from .effects import EffectSetting, EFFECTS, SHOW_MODES, DIRECTIONS
from .layouts import Catalog, Layout, Key, board_id

__all__ = [
    "OmenKeyboard",
    "OmenLightbar",
    "EffectSetting",
    "EFFECTS",
    "SHOW_MODES",
    "DIRECTIONS",
    "LB_ANIMATIONS",
    "LB_THEMES",
    "LB_SPEEDS",
    "LB_DIRECTIONS",
    "Catalog",
    "Layout",
    "Key",
    "board_id",
    "restore_device_lighting_control",
    "ZONE_NAMES_4",
]

__version__ = "1.1.0"
