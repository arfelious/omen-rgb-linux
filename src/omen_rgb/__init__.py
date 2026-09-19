"""
Omen RGB Linux - HP OMEN RGB Keyboard & Lightbar Control
"""

from .driver import OmenKeyboard, ZONE_NAMES_4
from .lightbar import OmenLightbar

__all__ = ["OmenKeyboard", "OmenLightbar", "ZONE_NAMES_4"]
__version__ = "1.0.0"
