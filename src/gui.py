#!/usr/bin/env python3
# Omen RGB Control Center - GUI Engine
# Copyright (C) 2026 arfelious

import tkinter as tk
from tkinter import PhotoImage
import sys
import os
import signal
import json
import colorsys
import threading
import time
import glob

# Project Path Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(BASE_DIR, 'src'))

from driver import OmenKeyboard
from lightbar import OmenLightbar


class ModernDialog(tk.Toplevel):
    def __init__(self, parent, title, message, type="info", scroll_content=None):
        super().__init__(parent)
        self.title(title)
        
        width = 600 if scroll_content else 400
        height = 500 if scroll_content else 250
        self.geometry(f"{width}x{height}")
        
        self.configure(bg="#1a1a1a")
        self.transient(parent)
        self.grab_set()
        
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        content = tk.Frame(self, bg="#1a1a1a", pady=20)
        content.pack(expand=True, fill="both")

        accent = "#00FFFF" if type == "info" else "#FF4500"
        tk.Label(content, text=title.upper(), font=("Outfit", 14, "bold"), bg="#1a1a1a", fg=accent).pack(pady=(0, 10))
        
        if scroll_content:
            text_frame = tk.Frame(content, bg="#111111", padx=10, pady=10)
            text_frame.pack(expand=True, fill="both", padx=20)
            
            scrollbar = tk.Scrollbar(text_frame)
            scrollbar.pack(side="right", fill="y")
            
            text_area = tk.Text(text_frame, font=("Outfit", 9), bg="#111111", fg="#AAAAAA", 
                                wrap="word", height=15, relief="flat", yscrollcommand=scrollbar.set,
                                highlightthickness=0)
            text_area.tag_configure("center", justify="center")
            text_area.insert("1.0", scroll_content)
            text_area.tag_add("center", "1.0", "end")
            text_area.configure(state="disabled")
            text_area.pack(side="left", expand=True, fill="both")
            scrollbar.config(command=text_area.yview)
        else:
            tk.Label(content, text=message, font=("Outfit", 11), bg="#1a1a1a", fg="#AAAAAA", wraplength=350).pack(pady=10)

        tk.Button(self, text="DISMISS", font=("Outfit", 10, "bold"), bg="#333333", fg="white", 
                  relief="flat", padx=30, pady=5, command=self.destroy).pack(pady=20)

class ConfirmDialog(tk.Toplevel):
    def __init__(self, parent, title, message, callback):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x220")
        self.configure(bg="#1a1a1a")
        self.callback = callback
        self.transient(parent)
        self.grab_set()
        
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        content = tk.Frame(self, bg="#1a1a1a", pady=15)
        content.pack(expand=True, fill="both")

        tk.Label(content, text=title.upper(), font=("Outfit", 13, "bold"), bg="#1a1a1a", fg="#FF9900").pack(pady=(0, 10))
        tk.Label(content, text=message, font=("Outfit", 10), bg="#1a1a1a", fg="#AAAAAA", wraplength=340).pack(pady=5)

        btn_frame = tk.Frame(self, bg="#1a1a1a", pady=10)
        btn_frame.pack(fill="x")

        tk.Button(btn_frame, text="OVERWRITE", font=("Outfit", 10, "bold"), bg="#FF4500", fg="white", 
                  relief="flat", padx=15, pady=6, command=self.on_yes).pack(side="left", padx=30)
        tk.Button(btn_frame, text="CANCEL", font=("Outfit", 10, "bold"), bg="#333333", fg="white", 
                  relief="flat", padx=15, pady=6, command=self.on_no).pack(side="right", padx=30)

    def on_yes(self):
        self.destroy()
        self.callback(True)

    def on_no(self):
        self.destroy()
        self.callback(False)


class ProfileDialog(tk.Toplevel):
    def __init__(self, parent, mode="load", callback=None):
        super().__init__(parent)
        self.title("Profile Manager")
        self.geometry("450x500")
        self.configure(bg="#1a1a1a")
        self.callback = callback
        self.mode = mode
        self.transient(parent)
        self.grab_set()
        
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        self.p_dir = os.path.join(BASE_DIR, "profiles")
        if not os.path.exists(self.p_dir):
            os.makedirs(self.p_dir)

        tk.Label(self, text="PROFILE MANAGER", font=("Outfit", 16, "bold"), bg="#1a1a1a", fg="#00FFFF", pady=20).pack()

        if mode == "save":
            self.setup_save_ui()
        else:
            self.setup_load_ui()

    def setup_save_ui(self):
        tk.Label(self, text="Enter Profile Name:", font=("Outfit", 10), bg="#1a1a1a", fg="#888888").pack(pady=10)
        self.entry = tk.Entry(self, font=("Outfit", 12), bg="#333333", fg="white", 
                              insertbackground="white", relief="flat", justify="center")
        self.entry.pack(pady=10, padx=40, fill="x")
        self.entry.focus_set()
        tk.Button(self, text="SAVE NEW PROFILE", font=("Outfit", 10, "bold"), bg="#008888", fg="white", 
                  relief="flat", pady=10, command=self.do_save).pack(pady=20, padx=40, fill="x")

    def setup_load_ui(self):
        list_frame = tk.Frame(self, bg="#111111")
        list_frame.pack(expand=True, fill="both", padx=20, pady=10)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.listbox = tk.Listbox(list_frame, font=("Outfit", 11), bg="#111111", fg="#AAAAAA", 
                                 selectbackground="#008888", relief="flat", highlightthickness=0, 
                                 yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", expand=True, fill="both")
        scrollbar.config(command=self.listbox.yview)

        self.refresh_list()

        btn_f = tk.Frame(self, bg="#1a1a1a")
        btn_f.pack(fill="x", pady=20, padx=20)
        
        tk.Button(btn_f, text="LOAD", font=("Outfit", 10, "bold"), bg="#008888", fg="white", 
                  relief="flat", width=12, pady=8, command=self.do_load).pack(side="left", padx=5)
        tk.Button(btn_f, text="DELETE", font=("Outfit", 10, "bold"), bg="#880000", fg="white", 
                  relief="flat", width=12, pady=8, command=self.do_delete).pack(side="right", padx=5)

    def refresh_list(self):
        self.listbox.delete(0, tk.END)
        for f in sorted(glob.glob(os.path.join(self.p_dir, "*.json"))):
            self.listbox.insert(tk.END, os.path.basename(f).replace(".json", ""))

    def do_save(self):
        name = self.entry.get().strip()
        if not name:
            return
        
        target_file = os.path.join(self.p_dir, f"{name}.json")
        if os.path.exists(target_file):
            def on_confirm(confirmed):
                if confirmed:
                    self.callback(name)
                    self.destroy()
            ConfirmDialog(self, "Overwrite Profile?", f"A profile named '{name}' already exists. Overwrite it?", on_confirm)
        else:
            self.callback(name)
            self.destroy()

    def do_load(self):
        sel = self.listbox.curselection()
        if sel:
            self.callback(self.listbox.get(sel[0]))
            self.destroy()

    def do_delete(self):
        sel = self.listbox.curselection()
        if sel:
            name = self.listbox.get(sel[0])
            try:
                os.remove(os.path.join(self.p_dir, f"{name}.json"))
                self.refresh_list()
            except Exception as e:
                print(f"Delete fail: {e}")

class RainbowThread(threading.Thread):
    def __init__(self, kb, gui):
        super().__init__(daemon=True)
        self.kb = kb
        self.gui = gui
        self.running = True
        self.hue = 0

    def run(self):
        while self.running:
            self.hue = (self.hue + 0.003) % 1.0
            r, g, b = [int(x * 255) for x in colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)]
            self.kb.set_all(r, g, b)
            # persist=False: command 0x0a is an MCU flash write, not a commit, and this is a
            # loop. _flush_hardware_writes() persists once when the user commits a change.
            self.kb.apply(persist=False)
            if self.gui.lb and self.gui.lb.is_available():
                try:
                    self.gui.lb.set_static(r, g, b)
                except Exception:
                    pass
            with self.gui.state_lock:
                for key in self.gui.key_items.keys():
                    self.gui.session_state[key] = (r, g, b)
                self.gui.rainbow_dirty = True
            time.sleep(0.016)


    def stop(self):
        self.running = False

class ModernColorPicker(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.title("Color Picker")
        self.geometry("300x400")
        self.configure(bg="#1a1a1a")
        self.callback = callback
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        self.hue, self.sat, self.val = 0.0, 1.0, 1.0
        
        self.sv_canvas = tk.Canvas(self, width=256, height=256, bg="#000000", highlightthickness=0)
        self.sv_canvas.pack(pady=10, padx=10)
        self.sv_canvas.bind("<B1-Motion>", self.update_sv)
        self.sv_canvas.bind("<Button-1>", self.update_sv)
        
        self.h_canvas = tk.Canvas(self, width=256, height=20, bg="#000000", highlightthickness=0)
        self.h_canvas.pack(pady=5)
        self.h_canvas.bind("<B1-Motion>", self.update_h)
        self.h_canvas.bind("<Button-1>", self.update_h)
        
        self.draw_h_gradient()
        self.draw_sv_gradient()
        
        btn_frame = tk.Frame(self, bg="#1a1a1a")
        btn_frame.pack(pady=10, fill="x")
        
        self.preview = tk.Frame(btn_frame, width=50, height=30, bg="#ff0000")
        self.preview.pack(side="left", padx=20)
        
        tk.Button(btn_frame, text="APPLY", font=("Outfit", 10, "bold"), bg="#333333", fg="white", 
                  relief="flat", padx=30, command=self.confirm).pack(side="right", padx=20)

    def draw_h_gradient(self):
        for x in range(256):
            rgb = colorsys.hsv_to_rgb(x/256, 1.0, 1.0)
            color = f"#{int(rgb[0]*255):02x}{int(rgb[1]*255):02x}{int(rgb[2]*255):02x}"
            self.h_canvas.create_line(x, 0, x, 20, fill=color)

    def draw_sv_gradient(self):
        self.sv_canvas.delete("gradient")
        for x in range(0, 256, 8): 
            for y in range(0, 256, 8):
                rgb = colorsys.hsv_to_rgb(self.hue, x/256, 1.0 - (y/256))
                color = f"#{int(rgb[0]*255):02x}{int(rgb[1]*255):02x}{int(rgb[2]*255):02x}"
                self.sv_canvas.create_rectangle(x, y, x+8, y+8, fill=color, outline=color, tags="gradient")

    def update_h(self, event):
        self.hue = max(0, min(255, event.x)) / 256
        self.draw_sv_gradient()
        self.update_preview()

    def update_sv(self, event):
        self.sat = max(0, min(255, event.x)) / 256
        self.val = 1.0 - (max(0, min(255, event.y)) / 256)
        self.update_preview()

    def update_preview(self):
        rgb = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        color = f"#{int(rgb[0]*255):02x}{int(rgb[1]*255):02x}{int(rgb[2]*255):02x}"
        self.preview.configure(bg=color)

    def confirm(self):
        rgb = colorsys.hsv_to_rgb(self.hue, self.sat, self.val)
        self.callback(int(rgb[0]*255), int(rgb[1]*255), int(rgb[2]*255))
        self.destroy()

class OmenGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Omen RGB Control Center")
        self.root.geometry("1150x850")
        self.root.configure(bg="#1a1a1a")
        
        self.selected_keys = set()
        self.session_state = {} 
        self.key_items = {}
        self.state_lock = threading.Lock()
        self.debounce_timer = None
        self.save_timer = None
        
        self.rainbow_dirty = False
        self.pre_drag_selection = set()
        self.selection_start = None
        self.selection_rect = None
        self.current_focus = "esc"
        self.rainbow_thread = None
        
        signal.signal(signal.SIGINT, lambda *args: self.quit())
        self.root.after(16, self.gui_heartbeat)
        self.root.protocol("WM_DELETE_WINDOW", self.quit)
        
        # Set Window Icon
        try:
            icon_path = os.path.join(BASE_DIR, "assets", "logo.png")
            self.icon_img = tk.PhotoImage(file=icon_path)
            self.root.iconphoto(True, self.icon_img)
        except Exception as e:
            print(f"Icon load fail: {e}")
            
        try:
            self.kb = OmenKeyboard()
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
            
        try:
            self.lb = OmenLightbar()
            self.has_lightbar = self.lb.is_supported()
        except Exception as e:
            print(f"Lightbar notice: {e}")
            self.lb = None
            self.has_lightbar = False

        if self.has_lightbar:
            self.lightbar_keys = ["lb_zone_1", "lb_zone_2", "lb_zone_3", "lb_zone_4"]
        else:
            self.lightbar_keys = []
            
        self.selected_keys.clear()

        self._init_session_state()
        self.setup_ui()
        self.root.bind("<KeyPress>", self.handle_keydown)

    def _save_active_state(self):
        try:
            config_dir = os.path.expanduser("~/.config/omen-rgb-linux")
            os.makedirs(config_dir, exist_ok=True)
            state_file = os.path.join(config_dir, "state.json")
            serializable_state = {k: list(v) for k, v in self.session_state.items()}
            with open(state_file, "w") as f:
                json.dump(serializable_state, f)
        except Exception:
            pass

    def _schedule_state_save(self):
        if getattr(self, "save_timer", None):
            self.save_timer.cancel()
        self.save_timer = threading.Timer(0.3, self._save_active_state)
        self.save_timer.start()

    def _load_active_state(self):
        state_file = os.path.expanduser("~/.config/omen-rgb-linux/state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    loaded = json.load(f)
                for k, v in loaded.items():
                    if isinstance(v, list) and len(v) == 3:
                        self.session_state[k] = tuple(v)
                return True
            except Exception:
                pass
        return False


    def _init_session_state(self):
        # 1. Attempt to query live lightbar colors directly from hardware ACPI BIOS
        lb_hardware_colors = None
        if self.has_lightbar and self.lb:
            try:
                colors = self.lb.get_colors()
                if colors:
                    lb_hardware_colors = colors
                    for i, color in enumerate(colors[:4], 1):
                        self.session_state[f"lb_zone_{i}"] = color
            except Exception as e:
                print(f"Lightbar hardware query notice: {e}")

        # 2. Load saved state for keyboard lighting
        loaded = self._load_active_state()

        # Prioritize live hardware lightbar colors over saved state.json file
        if lb_hardware_colors:
            for i, color in enumerate(lb_hardware_colors[:4], 1):
                self.session_state[f"lb_zone_{i}"] = color

        # 3. Fallback defaults if no saved state exists as keyboard color doesn't seem to be queriable
        if not loaded:
            fallback_color = (255, 153, 0)  # #ff9900
            lb_first_zone = lb_hardware_colors[0] if (lb_hardware_colors and sum(lb_hardware_colors[0]) > 0) else None
            base_color = lb_first_zone if lb_first_zone else fallback_color

            if self.has_lightbar and not lb_hardware_colors:
                for i in range(1, 5):
                    self.session_state[f"lb_zone_{i}"] = fallback_color

            for row in self.kb.key_map.values():
                for k_name in row.keys():
                    if k_name not in self.session_state:
                        self.session_state[k_name] = base_color

        # Sync all keyboard key colors from session_state into self.kb driver buffer
        for k_name, color in self.session_state.items():
            if k_name not in self.lightbar_keys:
                try:
                    self.kb.set_key_color(k_name, color[0], color[1], color[2])
                except Exception:
                    pass


    def gui_heartbeat(self):
        if self.rainbow_dirty:
            with self.state_lock:
                self.update_key_visuals()
                self.rainbow_dirty = False
        self.root.after(16, self.gui_heartbeat)

    def quit(self):
        if self.rainbow_thread:
            self.rainbow_thread.stop()
        self.root.destroy()
        sys.exit(0)

    def setup_ui(self):
        canvas_h = 360 if self.has_lightbar else 300
        win_h = 820 if self.has_lightbar else 750
        self.root.geometry(f"1150x{win_h}")

        header_frame = tk.Frame(self.root, bg="#1a1a1a")
        header_frame.pack(fill="x", pady=(30, 0))
        
        # Logo and Title
        title_container = tk.Frame(header_frame, bg="#1a1a1a")
        title_container.pack(side="left", expand=True, padx=(120, 0))
        
        try:
            logo_path = os.path.join(BASE_DIR, "assets", "logo.png")
            self.logo_img = tk.PhotoImage(file=logo_path).subsample(4, 4)
            tk.Label(title_container, image=self.logo_img, bg="#1a1a1a").pack(side="left", padx=10)
        except Exception as e:
            print(f"Logo fail: {e}")

        tk.Label(title_container, text="OMEN RGB CONTROL CENTER", font=("Outfit", 26, "bold"), bg="#1a1a1a", fg="#ffffff", pady=5).pack(side="left")
        
        tk.Button(header_frame, text="LICENSE", bg="#222222", fg="#888888", font=("Outfit", 8), relief="flat", command=self.show_license).pack(side="right", padx=20, pady=(0, 20))
        
        self.canvas = tk.Canvas(self.root, width=1050, height=canvas_h, bg="#1a1a1a", highlightthickness=0)

        self.canvas.pack(pady=(20, 5))
        self.canvas.bind("<ButtonPress-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.draw_keyboard_init()
        
        presets_frame = tk.Frame(self.root, bg="#1a1a1a")
        presets_frame.pack(pady=5)
        
        colors = ["#FF0000", "#FF4500", "#FF8C00", "#FFA500", "#FFD700", "#FFFF00", "#ADFF2f", "#00FF00", "#00FA9A", "#00FFFF", "#00BFFF", "#0000FF", "#4B0082", "#8A2BE2", "#FF00FF", "#FFFFFF", "#000000"]
        for c in colors:
            tk.Button(presets_frame, bg=c, width=2, height=1, relief="flat", command=lambda x=c: self.set_preset(x)).pack(side="left", padx=3)
        
        controls = tk.Frame(self.root, bg="#1a1a1a")
        controls.pack(pady=15)
        
        btn_s = {"font": ("Outfit", 12, "bold"), "bg": "#333333", "fg": "white", "relief": "flat", "padx": 25, "pady": 12}
        tk.Button(controls, text="COLOR PICKER", command=lambda: ModernColorPicker(self.root, self.apply_custom_color), **btn_s).pack(side="left", padx=15)
        self.rainbow_btn = tk.Button(controls, text="RAINBOW WAVE", command=self.toggle_rainbow, **btn_s)
        self.rainbow_btn.pack(side="left", padx=15)
        tk.Button(controls, text="RESET SELECTION", command=self.clear_selection, **btn_s).pack(side="left", padx=15)
        
        profile_frame = tk.Frame(self.root, bg="#1a1a1a")
        profile_frame.pack(pady=5)
        
        prof_s = {**btn_s, "bg": "#444444", "font": ("Outfit", 10, "bold")}
        tk.Button(profile_frame, text="SAVE PROFILE", command=lambda: ProfileDialog(self.root, "save", self.save_profile), **prof_s).pack(side="left", padx=10)
        tk.Button(profile_frame, text="LOAD PROFILE", command=lambda: ProfileDialog(self.root, "load", self.load_profile), **prof_s).pack(side="left", padx=10)

    def update_rainbow_button_state(self):
        if getattr(self, "rainbow_btn", None):
            if self.rainbow_thread and self.rainbow_thread.is_alive():
                self.rainbow_btn.configure(bg="#00CCCC", fg="#000000", activebackground="#00EEEE", activeforeground="#000000")
            else:
                self.rainbow_btn.configure(bg="#333333", fg="white", activebackground="#444444", activeforeground="white")

    def toggle_rainbow(self):
        if self.rainbow_thread:
            self.rainbow_thread.stop()
            self.rainbow_thread = None
        else:
            self.rainbow_thread = RainbowThread(self.kb, self)
            self.rainbow_thread.start()
        self.update_rainbow_button_state()

    def _flush_hardware_writes(self, do_kb, do_lb):
        with self.state_lock:
            if do_kb:
                try:
                    for k, color in self.session_state.items():
                        if k not in self.lightbar_keys:
                            self.kb.set_key_color(k, color[0], color[1], color[2])
                    self.kb.apply()
                except Exception as e:
                    print(f"Keyboard apply notice: {e}")

            if do_lb and self.lb and self.has_lightbar:
                try:
                    lb_colors = [self.session_state.get(k, (0, 0, 0)) for k in self.lightbar_keys]
                    self.lb.set_colors(lb_colors)
                except Exception as e:
                    print(f"Lightbar set colors notice: {e}")

    def _schedule_hardware_write(self, do_kb, do_lb):
        if getattr(self, "debounce_timer", None):
            self.debounce_timer.cancel()
        self.debounce_timer = threading.Timer(0.03, self._flush_hardware_writes, args=(do_kb, do_lb))
        self.debounce_timer.start()

    def apply_custom_color(self, r, g, b):
        if self.rainbow_thread:
            self.rainbow_thread.stop()
            self.rainbow_thread = None
            self.update_rainbow_button_state()
            
        with self.state_lock:
            if self.selected_keys:
                kb_keys = [k for k in self.selected_keys if k not in self.lightbar_keys]
                lb_keys = [k for k in self.selected_keys if k in self.lightbar_keys]
            else:
                kb_keys = [k for k in self.key_items.keys() if k not in self.lightbar_keys]
                lb_keys = list(self.lightbar_keys)

            # 1. Update Keyboard state if targeted
            if kb_keys:
                for k in kb_keys:
                    self.kb.set_key_color(k, r, g, b)
                    self.session_state[k] = (r, g, b)

            # 2. Update Lightbar state if targeted
            if lb_keys and self.has_lightbar:
                for k in lb_keys:
                    self.session_state[k] = (r, g, b)

            # Debounce hardware writes across 30ms window to prevent kernel/HID flooding
            self._schedule_hardware_write(bool(kb_keys), bool(lb_keys and self.has_lightbar))

            self._schedule_state_save()
            self.update_key_visuals()






    def show_license(self):
        try:
            lp = os.path.join(BASE_DIR, "LICENSE")
            with open(lp, "r") as f:
                ModernDialog(self.root, "GPL v3 LICENSE", "", "info", scroll_content=f.read())
        except:
            ModernDialog(self.root, "Error", "LICENSE not found!", "error")

    def on_click(self, event):
        self.selection_start = (event.x, event.y)
        is_ctrl = (event.state & 0x4)
        items = self.canvas.find_overlapping(event.x, event.y, event.x, event.y)
        
        target = items[0] if items else 0
        key_name = next((t for t in self.canvas.gettags(target) if t not in ["key", "current"]), None)
        
        if not is_ctrl:
            self.selected_keys.clear()
            
        if key_name:
            if is_ctrl and key_name in self.selected_keys:
                self.selected_keys.remove(key_name)
            else:
                self.selected_keys.add(key_name)
                self.current_focus = key_name
                
        self.pre_drag_selection = set(self.selected_keys)
        with self.state_lock:
            self.update_key_visuals()

    def on_drag(self, event):
        if not self.selection_start:
            return
            
        x0, y0 = self.selection_start
        x1, y1 = event.x, event.y
        self.selected_keys = set(self.pre_drag_selection)
        
        for item in self.canvas.find_overlapping(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)):
            tag = next((t for t in self.canvas.gettags(item) if t not in ["key", "current"]), None)
            if tag:
                self.selected_keys.add(tag)
                
        with self.state_lock:
            self.update_key_visuals()
            
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
        self.selection_rect = self.canvas.create_rectangle(x0, y0, x1, y1, outline="#00FFFF", dash=(4, 4))

    def on_release(self, event):
        if self.selection_rect:
            self.canvas.delete(self.selection_rect)
            self.selection_rect = None
            
        self.selection_start = None
        with self.state_lock:
            self.update_key_visuals()

    def handle_keydown(self, event):
        if event.keysym in ["Up", "Down", "Left", "Right"]:
            all_k = list(self.key_items.keys())
            try:
                idx = all_k.index(self.current_focus)
                if event.keysym == "Right":
                    idx = (idx + 1) % len(all_k)
                elif event.keysym == "Left":
                    idx = (idx - 1) % len(all_k)
                self.current_focus = all_k[idx]
                self.selected_keys.add(self.current_focus)
            except:
                pass
            with self.state_lock:
                self.update_key_visuals()

    def clear_selection(self):
        self.selected_keys.clear()
        with self.state_lock:
            self.update_key_visuals()

    def save_profile(self, name):
        try:
            p_dir = os.path.join(BASE_DIR, "profiles")
            with open(os.path.join(p_dir, f"{name}.json"), "w") as f:
                json.dump(self.session_state, f)
            ModernDialog(self.root, "Success", f"Saved: {name}", "info")
        except:
            ModernDialog(self.root, "Error", "Fail", "error")

    def load_profile(self, name):
        if self.rainbow_thread:
            self.rainbow_thread.stop()
            self.rainbow_thread = None
            self.update_rainbow_button_state()
        try:
            p_dir = os.path.join(BASE_DIR, "profiles")
            with open(os.path.join(p_dir, f"{name}.json"), "r") as f:
                self.session_state = json.load(f)
            for k, c in self.session_state.items():
                if k not in self.lightbar_keys:
                    self.kb.set_key_color(k, c[0], c[1], c[2])
            self.kb.apply()
            if self.lb and self.lb.is_available():
                try:
                    lb_colors = [self.session_state.get(k, (0, 0, 0)) for k in self.lightbar_keys]
                    self.lb.set_colors(lb_colors)
                except Exception as e:
                    print(f"Lightbar set colors error: {e}")
            with self.state_lock:
                self.update_key_visuals()
            ModernDialog(self.root, "Success", f"Loaded: {name}", "info")
        except:
            ModernDialog(self.root, "Error", "No profile found!", "error")


    def draw_keyboard_init(self):
        mx, my, bw, sp = 156, 80, 36, 2
        sym = {"tilde": "`", "minus": "-", "equal": "=", "backspace": "BSP", "tab": "TAB", "l_bracket": "[", "r_bracket": "]", "backslash": "\\", "caps_lock": "CAPS", "semicolon": ";", "quote": "'", "enter": "ENTER", "l_shift": "SHIFT", "comma": ",", "dot": ".", "slash": "/", "r_shift": "SHIFT", "l_ctrl": "CTRL", "l_win": "WIN", "l_alt": "ALT", "space": "SPACE", "r_alt": "ALT", "r_ctrl": "CTRL", "num_lock": "NUM", "num_slash": "/", "num_star": "*", "num_minus": "-", "num_plus": "+", "num_enter": "ENT", "num_dot": ".", "omen": "◆", "calculator": "田", "settings": "⚙", "power": "⏻"}
        tr = mx + (15 * bw) + (14 * sp)
        y_off = my
        
        for row_n in ["row_0", "row_1", "row_2", "row_3", "row_4", "row_5"]:
            if row_n not in self.kb.key_map:
                continue
            x_off, ch = mx, (20 if row_n == "row_0" else 34)
            sk = sorted(self.kb.key_map[row_n].items(), key=lambda x: x[1]["offset"])
            for i, (name, data) in enumerate(sk):
                w = bw
                if name == "tab": w = 72
                elif name == "caps_lock": w = 90
                elif name == "l_shift": w = 110
                elif name in ["l_ctrl", "fn", "l_win", "l_alt"]: w = 45
                elif name in ["r_alt", "r_ctrl"]: w = 33
                if row_n == "row_0": w = (tr - mx - 13 * sp) // 14
                if row_n == "row_5" and name == "space": w = (tr - 120 - sp) - x_off - 33*2 - sp*2
                if i == len(sk) - 1 and row_n != "row_5": w = tr - x_off
                rid = self.canvas.create_rectangle(x_off, y_off, x_off+w, y_off+ch, fill="#252525", outline="#333333", tags=("key", name))
                tid = self.canvas.create_text(x_off+w/2, y_off+ch/2, text=sym.get(name, name.replace("num_","").upper()), fill="#AAAAAA", font=("Outfit", 7, "bold"), state="disabled")
                self.key_items[name] = (rid, tid)
                x_off += w + sp
            if row_n == "row_0":
                x_off = tr + sp * 2
                for spec in ["omen", "calculator", "settings", "power"]:
                    rid = self.canvas.create_rectangle(x_off, y_off, x_off+34, y_off+20, fill="#252525", outline="#333333", tags=("key", spec))
                    tid = self.canvas.create_text(x_off+17, y_off+10, text=sym.get(spec, spec), fill="#AAAAAA", font=("Outfit", 7, "bold"), state="disabled")
                    self.key_items[spec] = (rid, tid)
                    x_off += 34 + sp
            y_off += ch + sp
            
        ay, ax = my + 20 + sp + (34 + sp) * 4, tr - 80
        for n, c in {"up": (ax, ay, 38, 17), "down": (ax, ay+18, 38, 16), "left": (ax-40, ay, 38, 34), "right": (ax+40, ay, 38, 34)}.items():
            rid = self.canvas.create_rectangle(c[0], c[1], c[0]+c[2], c[1]+c[3], fill="#252525", outline="#333333", tags=("key", n))
            tid = self.canvas.create_text(c[0]+c[2]/2, c[1]+c[3]/2, text=sym.get(n, n.upper()), fill="#AAAAAA", font=("Outfit", 7, "bold"), state="disabled")
            self.key_items[n] = (rid, tid)
            
        nx, ny = tr + sp*2, my + 20 + sp
        for r in [["num_lock", "num_slash", "num_star", "num_minus"], ["num_7", "num_8", "num_9", "num_plus"], ["num_4", "num_5", "num_6"], ["num_1", "num_2", "num_3", "num_enter"], ["num_0", "num_dot"]]:
            x_off = nx
            for k in r:
                w, h = (70 if k == "num_0" else 34), (70 if k in ["num_plus", "num_enter"] else 34)
                rid = self.canvas.create_rectangle(x_off, ny, x_off+w, ny+h, fill="#252525", outline="#333333", tags=("key", k))
                tid = self.canvas.create_text(x_off+w/2, ny+h/2, text=sym.get(k, k.replace("num_","").upper()), fill="#AAAAAA", font=("Outfit", 7, "bold"), state="disabled")
                self.key_items[k] = (rid, tid)
                x_off += w + sp
            ny += 34 + sp

        # Draw Bottom Lightbar (4 zones) if supported
        if self.has_lightbar:
            lb_y = my + 20 + sp + (34 + sp) * 5 + 15
            lb_total_w = tr + sp * 2 + 4 * 34 + 3 * sp - mx
            lb_zone_w = (lb_total_w - 3 * sp) // 4
            lb_x = mx
            for i, zone_name in enumerate(self.lightbar_keys, 1):
                rid = self.canvas.create_rectangle(lb_x, lb_y, lb_x + lb_zone_w, lb_y + 24, fill="#252525", outline="#333333", tags=("key", zone_name))
                tid = self.canvas.create_text(lb_x + lb_zone_w / 2, lb_y + 12, text=f"LIGHTBAR ZONE {i}", fill="#AAAAAA", font=("Outfit", 8, "bold"), state="disabled")
                self.key_items[zone_name] = (rid, tid)
                lb_x += lb_zone_w + sp
            
        with self.state_lock:
            self.update_key_visuals()




    def update_key_visuals(self):
        for name, (rid, tid) in self.key_items.items():
            r, g, b = self.session_state.get(name, (37, 37, 37))
            fill = f"#{r:02x}{g:02x}{b:02x}"
            sel = name in self.selected_keys
            if sel:
                sr, sg, sb = 255-r, 255-g, 255-b
                if abs(sr-r) < 50:
                    sr, sg, sb = 0, 255, 255
                out = f"#{sr:02x}{sg:02x}{sb:02x}"
            else:
                out = "#333333"
            luma = (0.299 * r + 0.587 * g + 0.114 * b)
            self.canvas.itemconfig(rid, fill=fill, outline=out, width=2 if sel else 1)
            self.canvas.itemconfig(tid, fill="#222222" if luma > 180 else "#EEEEEE")

    def set_preset(self, hc):
        self.apply_custom_color(int(hc[1:3], 16), int(hc[3:5], 16), int(hc[5:7], 16))

def main():
    root = tk.Tk()
    app = OmenGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

