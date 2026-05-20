#!/usr/bin/env python3
import sys
import os

# Add src to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))

from gui import OmenGUI
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = OmenGUI(root)
    root.mainloop()
