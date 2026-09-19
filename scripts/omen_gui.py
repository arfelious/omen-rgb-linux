#!/usr/bin/env python3
import sys
import os

# Add src to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

from omen_rgb.gui import main

if __name__ == "__main__":
    main()


