import tkinter as tk
from tkinter import filedialog, messagebox
from tkinterdnd2 import DND_FILES, TkinterDnD
import customtkinter as ctk
from PIL import Image, ImageTk
import numpy as np
import cv2
import json
import csv
import os
import sys
import threading
import queue
import platform
import multiprocessing

# --- HARDWARE ACCELERATION ENGINE CHECK ---
try:
    import numexpr as ne
    # Force NumExpr to utilize all available logical CPU cores for max vectorization
    cores = os.cpu_count()
    ne.set_num_threads(cores if cores else 4)
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing Acceleration Engine", 
        "Emulsifier v1.86 requires 'numexpr' for CPU hardware acceleration.\n\n"
        "Please open your terminal and run:\npip install numexpr"
    )
    sys.exit(1)

# --- UI DEPENDENCY CHECK ---
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    import customtkinter as ctk
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing UI Dependencies", 
        "Emulsifier v1.86 requires 'tkinterdnd2' and 'customtkinter'.\n\n"
        "Please open your terminal and run:\npip install tkinterdnd2 customtkinter"
    )
    sys.exit(1)

# Initialize CustomTkinter globally
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# --- TOOLTIP CLASS ---
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.show_id = None
        self.hide_id = None
        self.widget.bind("<Enter>", self.enter, add="+")
        self.widget.bind("<Leave>", self.leave, add="+")
        self.widget.bind("<ButtonPress>", self.force_hide, add="+")

    def enter(self, event=None):
        self.cancel_timers()
        self.show_id = self.widget.after(500, self.showtip)

    def leave(self, event=None):
        self.cancel_timers()
        self.hidetip()
        
    def force_hide(self, event=None):
        self.cancel_timers()
        self.hidetip()

    def cancel_timers(self):
        if self.show_id:
            self.widget.after_cancel(self.show_id)
            self.show_id = None
        if self.hide_id:
            self.widget.after_cancel(self.hide_id)
            self.hide_id = None

    def showtip(self, event=None):
        self.show_id = None
        x, y, cx, cy = self.widget.bbox("insert") or (0,0,0,0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry("+%d+%d" % (x, y))
        
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#252525", foreground="#FFD700", 
                         relief=tk.SOLID, borderwidth=1,
                         font=("Arial", 12, "normal"), padx=8, pady=6, wraplength=350)
        label.pack(ipadx=1)
        
        self.hide_id = self.widget.after(5000, self.hidetip)

    def hidetip(self):
        self.cancel_timers()
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

# --- DPI-AWARE CUSTOM BYPASS SWITCH ---
class BypassSwitch(tk.Canvas):
    def __init__(self, parent, app, variable, command=None, bg_color="#2A2A2A"):
        self.sf = ctk.ScalingTracker.get_widget_scaling(parent)
        self.w = int(34 * self.sf)
        self.h = int(18 * self.sf)
        super().__init__(parent, bg=bg_color, highlightthickness=0, width=self.w, height=self.h)
        self.app = app
        self.variable = variable
        self.command = command
        self.bg_color = bg_color
        
        self.bind("<ButtonPress-1>", self.toggle)
        self.variable.trace_add("write", self.draw)
        self.draw()

    def set_bg(self, new_bg):
        self.bg_color = new_bg
        self.config(bg=new_bg)
        self.draw()

    def toggle(self, event=None):
        if not self.app.film_profile:
            self.app.show_no_profile_warning()
            return
            
        self.variable.set(not self.variable.get())
        if self.command:
            self.command()

    def draw(self, *args):
        self.delete("all")
        state = self.variable.get()
        
        track_color = "#555555" if state else "#151515" 
        knob_color = "#C0C0C0" if state else "#444444"  
        
        r = self.h / 2
        self.create_oval(0, 0, self.h, self.h, fill=track_color, outline="")
        self.create_oval(self.w-self.h, 0, self.w, self.h, fill=track_color, outline="")
        self.create_rectangle(r, 0, self.w-r, self.h, fill=track_color, outline="")
        
        knob_r = int(5 * self.sf)
        cx = self.w - r if state else r
        cy = r
        self.create_oval(cx - knob_r, cy - knob_r, cx + knob_r, cy + knob_r, fill=knob_color, outline="")

# --- CUSTOM ACCORDION UI COMPONENT ---
class CollapsiblePane(ctk.CTkFrame):
    def __init__(self, parent, title, app, expanded=False):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.expanded = expanded
        self.title_text = title
        
        self.current_bg = "#3A3A3A" if expanded else "#2A2A2A"
        self.hover_bg = "#454545"
        
        self.header_frame = ctk.CTkFrame(self, fg_color=self.current_bg, corner_radius=6, height=36)
        self.header_frame.pack(fill=ctk.X, pady=(2, 0))
        self.header_frame.pack_propagate(False) 
        
        self.header_btn = ctk.CTkButton(self.header_frame, text=f"▼  {title}" if expanded else f"▶  {title}",
                                    fg_color="transparent", hover_color=self.hover_bg, text_color="#E0E0E0",
                                    font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
                                    anchor="w", command=self.toggle)
        self.header_btn.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.switch_var = tk.BooleanVar(master=self.app, value=True)
        self.bypass_switch = BypassSwitch(self.header_frame, app=self.app, variable=self.switch_var, command=self.on_switch_toggle, bg_color=self.current_bg)
        self.bypass_switch.pack(side=tk.RIGHT, padx=(0, 15), pady=9)
        
        self.header_frame.bind("<Enter>", self.on_hover)
        self.header_frame.bind("<Leave>", self.on_leave)
        self.header_btn.bind("<Enter>", self.on_hover)
        self.header_btn.bind("<Leave>", self.on_leave)
        self.bypass_switch.bind("<Enter>", self.on_hover)
        self.bypass_switch.bind("<Leave>", self.on_leave)
        
        self.content_frame = ctk.CTkFrame(self, fg_color="#222222", corner_radius=6)
        if self.expanded:
            self.content_frame.pack(fill=ctk.BOTH, expand=True, pady=(2, 5), padx=2)

    def on_hover(self, event=None):
        self.header_frame.configure(fg_color=self.hover_bg)
        self.bypass_switch.set_bg(self.hover_bg)

    def on_leave(self, event=None):
        self.header_frame.configure(fg_color=self.current_bg)
        self.bypass_switch.set_bg(self.current_bg)

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self.header_btn.configure(text=f"▼  {self.title_text}")
            self.content_frame.pack(fill=ctk.BOTH, expand=True, pady=(2, 5), padx=2)
        else:
            self.header_btn.configure(text=f"▶  {self.title_text}")
            self.content_frame.pack_forget()
        self.app.set_active_pane(self)

    def on_switch_toggle(self):
        self.app.trigger_render()
        self.app.save_state()

# --- DPI-AWARE CUSTOM LIGHTROOM-STYLE SLIDER ---
class LightroomSlider(tk.Canvas):
    def __init__(self, parent, app, variable, from_=0, to=100, default_val=None, command=None, bg_color="#222222"):
        self.sf = ctk.ScalingTracker.get_widget_scaling(parent)
        super().__init__(parent, bg=bg_color, highlightthickness=0, height=int(22*self.sf))
        self.app = app
        self.variable = variable
        self.from_ = from_
        self.to = to
        self.default_val = default_val if default_val is not None else from_
        self.command = command
        self.bg_color = bg_color

        self.pad = int(12 * self.sf)
        self.knob_radius = int(7 * self.sf)
        self.outline_color = "#A0A0A0"
        self.hover_color = "#FFFFFF"

        self.bind("<Configure>", self.on_resize)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        
        self.bind("<Button-2>", self.on_right_click)
        self.bind("<Button-3>", self.on_right_click)

        self.variable.trace_add("write", self.on_var_change)
        self._is_dragging = False
        self._hover = False

    def on_resize(self, event):
        self.draw()

    def on_var_change(self, *args):
        if not self._is_dragging:
            self.draw()

    def on_enter(self, event):
        self._hover = True
        self.draw()

    def on_leave(self, event):
        self._hover = False
        self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1: return

        val = self.variable.get()
        pct = (val - self.from_) / (self.to - self.from_)
        pct = max(0.0, min(1.0, pct))
        x = self.pad + pct * (w - 2 * self.pad)
        
        def_pct = (self.default_val - self.from_) / (self.to - self.from_)
        def_pct = max(0.0, min(1.0, def_pct))
        def_x = self.pad + def_pct * (w - 2 * self.pad)
        
        cy = h / 2

        self.create_line(self.pad, cy, w - self.pad, cy, fill="#333333", width=2)
        self.create_line(def_x, cy - 3, def_x, cy + 4, fill="#666666", width=2)

        if val < self.default_val:
            self.create_line(x, cy, def_x, cy, fill="#555555", width=2) 
        elif val > self.default_val:
            self.create_line(def_x, cy, x, cy, fill="#999999", width=2) 

        current_outline = self.hover_color if self._hover else self.outline_color
        self.create_oval(x - self.knob_radius, cy - self.knob_radius,
                         x + self.knob_radius, cy + self.knob_radius,
                         fill=self.bg_color, outline=current_outline, width=3)

    def on_press(self, event):
        if not self.app.film_profile:
            self.app.show_no_profile_warning()
            return
        self._is_dragging = True
        self.update_val_from_mouse(event.x)

    def on_drag(self, event):
        if not self.app.film_profile: return
        self.update_val_from_mouse(event.x)

    def on_release(self, event):
        self._is_dragging = False
        if self.command and self.app.film_profile:
            self.command(self.variable.get())
            self.app.save_state()
            
    def on_right_click(self, event):
        if not self.app.film_profile:
            self.app.show_no_profile_warning()
            return
        self.variable.set(self.default_val)
        self.draw()
        if self.command:
            self.command(self.default_val)
            self.app.save_state()

    def update_val_from_mouse(self, x):
        w = self.winfo_width()
        track_w = w - 2 * self.pad
        if track_w <= 0: return

        pct = (x - self.pad) / track_w
        pct = max(0.0, min(1.0, pct))
        val = self.from_ + pct * (self.to - self.from_)
        self.variable.set(val)
        self.draw()
        if self.command:
            self.command(val)

# --- DPI-AWARE CUSTOM INTERACTIVE LEVELS WIDGET ---
class LevelsWidget(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg="#222222")
        self.app = app
        self.sf = ctk.ScalingTracker.get_widget_scaling(parent)
        self.width = int(340 * self.sf)
        self.height = int(110 * self.sf)
        self.pad = int(12 * self.sf)

        self.canvas = tk.Canvas(self, width=self.width, height=self.height, bg="#2A2A2A", highlightthickness=1, highlightbackground="#111111")
        self.canvas.pack(pady=(5, 0))

        self.val_frame = tk.Frame(self, bg="#222222")
        self.val_frame.pack(fill=tk.X, pady=5, padx=self.pad)

        self.bp_label = tk.Label(self.val_frame, text="0", bg="#151515", fg="#E0E0E0", width=4, font=("Arial", 11), relief=tk.SUNKEN, borderwidth=1)
        self.bp_label.pack(side=tk.LEFT)

        self.wp_label = tk.Label(self.val_frame, text="255", bg="#151515", fg="#E0E0E0", width=4, font=("Arial", 11), relief=tk.SUNKEN, borderwidth=1)
        self.wp_label.pack(side=tk.RIGHT)

        self.mid_label = tk.Label(self.val_frame, text="1.00", bg="#151515", fg="#E0E0E0", width=4, font=("Arial", 11), relief=tk.SUNKEN, borderwidth=1)
        self.mid_label.pack(side=tk.TOP, anchor=tk.CENTER)

        self.hist_data = None
        self.bp_pixel = self.pad
        self.wp_pixel = self.width - self.pad
        self.mid_pixel = self.width / 2

        self.active_knob = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.canvas.bind("<Button-2>", self.on_right_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

        self.draw()

    def set_histogram(self, hist_array):
        self.hist_data = hist_array
        self.draw()

    def draw(self):
        self.canvas.delete("all")

        if self.hist_data is not None:
            max_val = np.max(self.hist_data)
            if max_val > 0:
                normalized = self.hist_data / max_val
                poly_points = [(self.pad, self.height - int(15*self.sf))]
                bin_w = (self.width - 2*self.pad) / 256.0
                for i, val in enumerate(normalized):
                    x = self.pad + i * bin_w
                    y = self.height - int(15*self.sf) - (val * (self.height - int(25*self.sf)))
                    poly_points.append((x, y))
                poly_points.append((self.width - self.pad, self.height - int(15*self.sf)))
                self.canvas.create_polygon(poly_points, fill="#8B7300", outline="")

        self.canvas.create_line(self.pad, self.height - int(15*self.sf), self.width - self.pad, self.height - int(15*self.sf), fill="#111111", width=2)

        self.draw_knob(self.bp_pixel, "#000000", "#FFFFFF", "bp")
        self.draw_knob(self.wp_pixel, "#FFFFFF", "#000000", "wp")
        self.draw_knob(self.mid_pixel, "#888888", "#FFFFFF", "mid")

    def draw_knob(self, x, fill_color, outline_color, tag):
        y = self.height - int(15*self.sf)
        k_w = int(7*self.sf)
        k_h = int(13*self.sf)
        pts = [x, y, x-k_w, y+k_h, x+k_w, y+k_h]
        self.canvas.create_polygon(pts, fill=fill_color, outline=outline_color, tags=tag)

    def on_press(self, event):
        if not self.app.film_profile:
            self.app.show_no_profile_warning()
            return
            
        for tag, px in [("mid", self.mid_pixel), ("bp", self.bp_pixel), ("wp", self.wp_pixel)]:
            if abs(event.x - px) < (12*self.sf) and event.y > self.height - (25*self.sf):
                self.active_knob = tag
                break

    def on_drag(self, event):
        if not self.app.film_profile or not self.active_knob: return

        new_x = max(self.pad, min(event.x, self.width - self.pad))

        if self.active_knob == "bp":
            self.bp_pixel = min(new_x, self.mid_pixel - 5)
        elif self.active_knob == "wp":
            self.wp_pixel = max(new_x, self.mid_pixel + 5)
        elif self.active_knob == "mid":
            self.mid_pixel = max(self.bp_pixel + 5, min(new_x, self.wp_pixel - 5))

        self.update_values()
        self.draw()
        self.app.trigger_render()

    def on_release(self, event):
        self.active_knob = None
        if self.app.film_profile:
            self.app.trigger_render()
            self.app.save_state()
            
    def on_right_click(self, event):
        if not self.app.film_profile:
            self.app.show_no_profile_warning()
            return
        self.reset()
        self.app.trigger_render()
        self.app.save_state()

    def update_values(self):
        w_range = self.width - 2*self.pad
        
        bp_val = ((self.bp_pixel - self.pad) / w_range) * 255.0
        wp_val = ((self.wp_pixel - self.pad) / w_range) * 255.0

        safe_range = max(1.0, (self.wp_pixel - self.bp_pixel))
        pos = (self.mid_pixel - self.bp_pixel) / safe_range
        pos = max(0.01, min(0.99, pos)) 
        gamma = np.log(0.5) / np.log(pos)

        self.bp_label.config(text=f"{int(bp_val)}")
        self.mid_label.config(text=f"{gamma:.2f}")
        self.wp_label.config(text=f"{int(wp_val)}")

        self.app.bp_var.set(bp_val)
        self.app.wp_var.set(wp_val)
        self.app.mid_var.set(gamma)

    def set_values_from_vars(self, bp_val, gamma, wp_val):
        w_range = self.width - 2 * self.pad
        self.bp_pixel = self.pad + (bp_val / 255.0) * w_range
        self.wp_pixel = self.pad + (wp_val / 255.0) * w_range
        
        pos = np.exp(np.log(0.5) / gamma)
        safe_range = max(1.0, (self.wp_pixel - self.bp_pixel))
        self.mid_pixel = self.bp_pixel + pos * safe_range
        
        self.bp_label.config(text=f"{int(bp_val)}")
        self.mid_label.config(text=f"{gamma:.2f}")
        self.wp_label.config(text=f"{int(wp_val)}")
        
        self.app.bp_var.set(bp_val)
        self.app.wp_var.set(wp_val)
        self.app.mid_var.set(gamma)
        
        self.draw()

    def reset(self):
        self.bp_pixel = self.pad
        self.wp_pixel = self.width - self.pad
        self.mid_pixel = self.width / 2
        self.update_values()
        self.draw()

# --- MAIN APPLICATION ---
class FilmRendererApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.base_title = "Emulsifier Film Emulator - Rendering Engine v1.86"
        self.title(self.base_title)
        self.geometry("1450x900")
        self.configure(bg="#181818") 

        if platform.system() == "Darwin":
            self.cursor_pan = "openhand"
            self.cursor_grab = "closedhand"
            self.cursor_zoom_in = "zoom-in"
            self.cursor_zoom_out = "zoom-out"
            self.cursor_wipe = "resizeleftright"
        else:
            self.cursor_pan = "fleur"
            self.cursor_grab = "fleur"
            self.cursor_zoom_in = "plus"
            self.cursor_zoom_out = "plus" 
            self.cursor_wipe = "sb_h_double_arrow"

        self.original_image = None
        self.working_img_pil = None       
        self.preview_array = None         
        self.processed_img_pil = None     
        self.current_chunk_pil = None 
        self.current_unprocessed_array = None 
        self._last_view_state = None      
        
        self.preset_mapping = {}

        self.view_mode = "side_by_side"
        self.wipe_percent = 0.5
        self.wipe_dragging = False
        
        self.space_pressed = False
        self.is_panning = False
        self.pan_start_x = 0
        self.pan_start_y = 0
        self.pan_cum_dx = 0
        self.pan_cum_dy = 0

        self.is_zoomed = False
        self.zoom_level = 1.0
        self.zoom_center_master = (0, 0)
        self.render_center_x = 0
        self.render_center_y = 0

        self.film_profile = None   
        self.curve_data = {}       
        self.log_e_grid = []

        self._render_after_id = None
        self.render_queue = queue.Queue()
        self.worker_thread = threading.Thread(target=self._render_worker, daemon=True)
        self.worker_thread.start()
        
        self.bp_var = ctk.DoubleVar(master=self, value=0)
        self.mid_var = ctk.DoubleVar(master=self, value=1.0)
        self.wp_var = ctk.DoubleVar(master=self, value=255)
        
        self.is_auto_mixing = False
        self._showing_warning = False
        
        # --- UNDO / REDO ARCHITECTURE ---
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo_steps = 5
        self.is_restoring_state = False
        
        # --- OSD NOTIFICATION VARS ---
        self.osd_window = None
        self.osd_timer = None

        self.panes = [] 
        self.setup_ui()

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        
        self.bind("<KeyPress-space>", self.on_space_press)
        self.bind("<KeyRelease-space>", self.on_space_release)
        
        # --- UNDO / REDO BINDINGS ---
        self.bind("<Control-z>", self.undo)
        self.bind("<Command-z>", self.undo)
        self.bind("<Control-y>", self.redo)
        self.bind("<Command-y>", self.redo)
        self.bind("<Control-Z>", self.redo) 
        self.bind("<Command-Z>", self.redo)

    # --- MASTER RESET SYSTEM ---
    def confirm_reset(self):
        if self.original_image is None: return
        
        if messagebox.askyesno("Reset Workspace", "Are you sure you want to reset all applied settings?"):
            self.save_state() 
            
            self.profile_var.set("--- NONE ---")
            self.film_profile = None
            self.curve_data = {}
            self.log_e_grid = []
            self.lbl_profile.configure(text="NO TONE PROFILE")
            
            self.str_var.set(65)
            self.soft_var.set(15)
            self.ca_var.set(2)
            self.cross_var.set(15) # Adjusted default
            self.flat_var.set(19)  # Adjusted default
            self.hal_var.set(15)   # Adjusted default
            self.bloom_var.set(7.5)# Adjusted default
            self.cont_var.set(40)
            self.split_var.set(15)
            self.subsat_var.set(30)
            self.grain_amt_var.set(30)
            self.grain_size_var.set(1.5)
            self.grain_chroma_var.set(15)
            self.ff_amt_var.set(0)
            self.ff_fall_var.set(40)
            self.vig_amt_var.set(0)
            self.vig_fall_var.set(30)
            
            self.pane_optics.switch_var.set(True)
            self.pane_light.switch_var.set(True)
            self.pane_print.switch_var.set(True)
            self.pane_grain.switch_var.set(True)
            self.pane_edge.switch_var.set(True)
            self.pane_levels.switch_var.set(True)
            
            self.levels_widget.reset()
            
            self.update_labels()
            self.trigger_render()
            self.show_osd_message("Workspace Reset")

    # --- ON-SCREEN DISPLAY (OSD) SYSTEM ---
    def show_osd_message(self, message):
        if self.osd_window and self.osd_window.winfo_exists():
            self.osd_window.destroy()
        if self.osd_timer:
            self.after_cancel(self.osd_timer)

        self.osd_window = tk.Toplevel(self)
        self.osd_window.wm_overrideredirect(True)
        self.osd_window.attributes("-alpha", 0.6) 
        self.osd_window.configure(bg="#222222")
        
        lbl = tk.Label(self.osd_window, text=message, font=("Arial", 20, "normal"), 
                       bg="#222222", fg="#E0E0E0", padx=20, pady=8)
        lbl.pack()

        self.update_idletasks()
        pf_x = self.preview_frame.winfo_rootx()
        pf_y = self.preview_frame.winfo_rooty()
        pf_w = self.preview_frame.winfo_width()
        pf_h = self.preview_frame.winfo_height()
        
        win_w = lbl.winfo_reqwidth()
        win_h = lbl.winfo_reqheight()
        
        pos_x = pf_x + (pf_w // 2) - (win_w // 2)
        pos_y = pf_y + (pf_h // 2) - (win_h // 2)
        
        self.osd_window.geometry(f"+{pos_x}+{pos_y}")
        self.osd_timer = self.after(1000, self.hide_osd_message)

    def hide_osd_message(self):
        if self.osd_window and self.osd_window.winfo_exists():
            self.osd_window.destroy()
            self.osd_window = None

    def show_no_profile_warning(self):
        if getattr(self, '_showing_warning', False): 
            return
        self._showing_warning = True
        messagebox.showwarning("Profile Required", "Please load Film Emulation Profile prior to changing values.")
        self._showing_warning = False

    def set_active_pane(self, active_pane):
        for pane in self.panes:
            pane.current_bg = "#3A3A3A" if pane.expanded else "#2A2A2A"
            pane.header_frame.configure(fg_color=pane.current_bg) 
            pane.bypass_switch.set_bg(pane.current_bg) 
                
            if pane == active_pane:
                pane.header_btn.configure(text_color="#FFD700") 
            else:
                pane.header_btn.configure(text_color="#E0E0E0") 

    def refresh_and_load_presets(self):
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        profiles_dir = os.path.join(base_dir, "profiles")
        cache_file = os.path.join(base_dir, "_profiles_cache.json")
        
        if not os.path.exists(profiles_dir) or not os.path.isdir(profiles_dir):
            messagebox.showerror(
                "Missing Folder", 
                f"Could not find the required '/profiles' folder.\n\n"
                f"Please ensure it exists in the same directory as the app:\n{base_dir}"
            )
            self.preset_mapping = {}
            return ["No Profiles Found"]
            
        json_files = [f for f in os.listdir(profiles_dir) if f.lower().endswith('.json')]
        cache_data = []
        needs_refresh = True
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                if len(cache_data) == len(json_files):
                    needs_refresh = False
            except Exception:
                pass
                
        if needs_refresh:
            modal = tk.Toplevel(self)
            modal.title("Refreshing")
            modal.geometry("350x120")
            modal.configure(bg="#222222")
            modal.transient(self)
            modal.grab_set()
            
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - 175
            y = self.winfo_y() + (self.winfo_height() // 2) - 60
            modal.geometry(f"+{x}+{y}")
            
            lbl = tk.Label(modal, text="Refreshing Emulsion Presets list.\n\nHold on couple of seconds please...", bg="#222222", fg="#E0E0E0", font=("Arial", 11))
            lbl.pack(expand=True, fill=tk.BOTH)
            self.update_idletasks()
            
            cache_data = []
            for jf in json_files:
                filepath = os.path.join(profiles_dir, jf)
                try:
                    with open(filepath, 'r') as file:
                        data = json.load(file)
                        mfg = data.get('manufacturer', '')
                        name = data.get('film_name', '')
                        full_name = f"{mfg} {name}".strip().upper()
                        if full_name:
                            cache_data.append({"name": full_name, "file": jf})
                except Exception:
                    pass
                    
            cache_data = sorted(cache_data, key=lambda x: x["name"])
            
            try:
                with open(cache_file, 'w') as f:
                    json.dump(cache_data, f)
            except Exception:
                pass
                
            modal.destroy()
            
        self.preset_mapping = {item["name"]: os.path.join(profiles_dir, item["file"]) for item in cache_data}
        
        preset_names = [item["name"] for item in cache_data]
        if not preset_names:
            preset_names = ["No Valid Profiles Found"]
        else:
            preset_names.insert(0, "--- NONE ---") 
            
        return preset_names

    def setup_ui(self):
        self.preview_frame = tk.Frame(self, bg="#111111")
        self.preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.canvas_left = tk.Canvas(self.preview_frame, bg="#151515", highlightthickness=0, cursor="arrow")
        self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 5), pady=10)
        
        self.canvas_right = tk.Canvas(self.preview_frame, bg="#151515", highlightthickness=0, cursor="arrow")
        self.canvas_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)
        
        for canvas in (self.canvas_left, self.canvas_right):
            canvas.bind("<ButtonPress-1>", self.on_canvas_press)
            canvas.bind("<B1-Motion>", self.on_canvas_drag)
            canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
            
            canvas.bind("<MouseWheel>", self.on_mouse_wheel)
            canvas.bind("<Button-4>", self.on_mouse_wheel)
            canvas.bind("<Button-5>", self.on_mouse_wheel)
            
            canvas.bind("<Motion>", self.on_canvas_hover)

        self.canvas_left.bind("<Configure>", lambda e: self.update_canvases())

        self.control_container = ctk.CTkFrame(self, width=400, fg_color="#1E1E1E", corner_radius=0)
        self.control_container.pack_propagate(False)
        self.control_container.pack(side=tk.RIGHT, fill=tk.Y)

        self.top_pinned = ctk.CTkFrame(self.control_container, fg_color="transparent")
        self.top_pinned.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(15, 0))

        # --- QoL: LOAD & RESET BUTTON ROW ---
        self.btn_row = ctk.CTkFrame(self.top_pinned, fg_color="transparent")
        self.btn_row.pack(fill=tk.X, pady=(0, 6))

        self.btn_load = ctk.CTkButton(self.btn_row, text="Load Digital / AI Photo", command=self.load_image_dialog, 
                      fg_color="#5C5C5C", hover_color="#8B7300", text_color="#FFFFFF", height=40,
                      font=ctk.CTkFont(family="Arial", size=14, weight="bold"))
        self.btn_load.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_reset = ctk.CTkButton(self.btn_row, text="↺", width=40, height=40,
                                       fg_color="#7A2828", hover_color="#B22222", text_color="#FFFFFF",
                                       font=ctk.CTkFont(family="Arial", size=18, weight="bold"),
                                       command=self.confirm_reset)
        self.btn_reset.pack(side=tk.RIGHT)
        ToolTip(self.btn_reset, "Master Reset: Return all sliders, switches, and profiles to default.")

        preset_names = self.refresh_and_load_presets()
        
        self.profile_var = ctk.StringVar(master=self, value="Select Film Emulation...")
        self.profile_dropdown = ctk.CTkOptionMenu(
            self.top_pinned,
            variable=self.profile_var,
            values=preset_names,
            command=self.on_profile_select,
            fg_color="#333333", button_color="#444444", button_hover_color="#555555",
            dropdown_fg_color="#2A2A2A", dropdown_hover_color="#444444", 
            font=ctk.CTkFont(family="Arial", size=13),
            dropdown_font=ctk.CTkFont(family="Arial", size=13),
            height=36,
            state="disabled" 
        )
        self.profile_dropdown.pack(fill=tk.X, pady=(0, 10))

        self.lbl_profile = ctk.CTkLabel(self.top_pinned, text="NO TONE PROFILE", text_color="#FFD700", 
                                        font=ctk.CTkFont(family="Arial", size=14, weight="bold"), 
                                        fg_color="#111111", corner_radius=6, height=36)
        self.lbl_profile.pack(fill=tk.X, pady=(0, 10))

        self.hist_canvas_h = int(65 * ctk.ScalingTracker.get_widget_scaling(self))
        self.hist_canvas = tk.Canvas(self.top_pinned, height=self.hist_canvas_h, bg="#111111", highlightthickness=1, highlightbackground="#333333")
        self.hist_canvas.pack(fill=tk.X, pady=(0, 10))
        
        ToolTip(self.hist_canvas, "Global Luminance Scope\nGrey: Original Image | Gold: Dehanced Image")

        self.str_var = ctk.DoubleVar(master=self, value=65) 
        self.soft_var = ctk.DoubleVar(master=self, value=15)
        self.ca_var = ctk.DoubleVar(master=self, value=2)
        
        # --- V1.86: REDUCED LIGHT & SCATTER DEFAULTS ---
        self.cross_var = ctk.DoubleVar(master=self, value=15) 
        self.flat_var = ctk.DoubleVar(master=self, value=19)
        self.hal_var = ctk.DoubleVar(master=self, value=15)
        self.bloom_var = ctk.DoubleVar(master=self, value=7.5)
        
        self.cont_var = ctk.DoubleVar(master=self, value=40)
        self.split_var = ctk.DoubleVar(master=self, value=15)
        self.subsat_var = ctk.DoubleVar(master=self, value=30) 
        
        self.grain_amt_var = ctk.DoubleVar(master=self, value=30)
        self.grain_size_var = ctk.DoubleVar(master=self, value=1.5)
        self.grain_chroma_var = ctk.DoubleVar(master=self, value=15) 
        self.ff_amt_var = ctk.DoubleVar(master=self, value=0)
        self.ff_fall_var = ctk.DoubleVar(master=self, value=40)
        self.vig_amt_var = ctk.DoubleVar(master=self, value=0)
        self.vig_fall_var = ctk.DoubleVar(master=self, value=30)

        self.master_mix_frame = ctk.CTkFrame(self.top_pinned, fg_color="#2A2A2A", corner_radius=8)
        self.master_mix_frame.pack(fill=tk.X, pady=(0, 15), ipadx=5, ipady=5)
        
        # --- UI AUTO-MIX HEADER ---
        self.mix_header_frame = tk.Frame(self.master_mix_frame, bg="#2A2A2A")
        self.mix_header_frame.pack(fill=tk.X, padx=10, pady=(5, 0))

        self.lbl_str = ctk.CTkLabel(self.mix_header_frame, text="Overall Physical Mix: 65%", text_color="#FFFFFF", font=ctk.CTkFont(family="Arial", size=13, weight="bold"))
        self.lbl_str.pack(side=tk.LEFT)

        def trigger_auto_mix():
            if not self.film_profile:
                self.show_no_profile_warning()
                return
            self.is_auto_mixing = True
            self.lbl_str.configure(text="Calculating Auto...")
            self.trigger_render()

        self.btn_auto = ctk.CTkButton(self.mix_header_frame, text="Auto", width=40, height=20, 
                                      fg_color="#444444", hover_color="#8B7300", 
                                      font=ctk.CTkFont(family="Arial", size=10, weight="bold"), 
                                      command=trigger_auto_mix)
        self.btn_auto.pack(side=tk.RIGHT)
        ToolTip(self.btn_auto, "Smart Auto-Mix: Analyzes global luminance and finds the highest possible film blend that protects the midtones from washing out.")
        
        def master_mix_cmd(val):
            self.lbl_str.configure(text=f"Overall Physical Mix: {int(val)}%")
            self.set_active_pane(None)
            self.trigger_render()
            
        default_mix = self.str_var.get()
        str_slider = LightroomSlider(self.master_mix_frame, app=self, variable=self.str_var, from_=0, to=100, default_val=default_mix, command=master_mix_cmd, bg_color="#2A2A2A")
        str_slider.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ToolTip(str_slider, "Overall blend of the final film emulation against the original digital image.")

        self.bottom_pinned = ctk.CTkFrame(self.control_container, fg_color="transparent")
        self.bottom_pinned.pack(side=tk.BOTTOM, fill=tk.X, padx=15, pady=(10, 20))
        
        ctk.CTkButton(self.bottom_pinned, text="Export Full-Res Render", command=self.export_image, 
                      fg_color="#5C5C5C", hover_color="#8B7300", text_color="#FFFFFF", height=44, 
                      font=ctk.CTkFont(family="Arial", size=14, weight="bold")).pack(fill=tk.X)

        self.scroll_frame = ctk.CTkScrollableFrame(self.control_container, fg_color="transparent")
        self.scroll_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5)

        def make_slider_cmd(pane, label_widget, text_prefix, is_float=False):
            def cmd(val):
                if is_float:
                    label_widget.configure(text=f"{text_prefix}: {val:.1f}")
                else:
                    label_widget.configure(text=f"{text_prefix}: {int(val)}{'px' if 'Aberration' in text_prefix else '%'}")
                self.set_active_pane(pane)
                self.trigger_render()
            return cmd
            
        def create_slider_row(parent, pane, label_text, tooltip_text, var, from_, to, is_float=False):
            lbl = ctk.CTkLabel(parent, text=f"{label_text}: {var.get()}", font=ctk.CTkFont(family="Arial", size=12))
            lbl.pack(anchor="w", padx=10, pady=(5,0))
            
            default_val = var.get()
            slider = LightroomSlider(parent, app=self, variable=var, from_=from_, to=to, default_val=default_val, command=make_slider_cmd(pane, lbl, label_text, is_float), bg_color="#222222")
            slider.pack(fill=tk.X, padx=10, pady=(0,10))
            
            if tooltip_text:
                ToolTip(slider, tooltip_text)
                
            return lbl

        self.pane_optics = CollapsiblePane(self.scroll_frame, "Lens Optics", app=self, expanded=True)
        self.pane_optics.pack(fill=tk.X, pady=(0, 2))
        self.panes.append(self.pane_optics)
        self.lbl_soft = create_slider_row(self.pane_optics.content_frame, self.pane_optics, "Optical Softness", "Simulates vintage lens defocus.", self.soft_var, 0, 100)
        self.lbl_ca = create_slider_row(self.pane_optics.content_frame, self.pane_optics, "Chromatic Aberration", "Lateral color fringing.", self.ca_var, 0, 10)

        self.pane_light = CollapsiblePane(self.scroll_frame, "Light & Scatter", app=self)
        self.pane_light.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_light)
        self.lbl_flat = create_slider_row(self.pane_light.content_frame, self.pane_light, "Cine-Log Flattening", "Pre-flattens digital contrast.", self.flat_var, 0, 100)
        self.lbl_cross = create_slider_row(self.pane_light.content_frame, self.pane_light, "Emulsion Crosstalk", "Simulates chemical dye impurities and complex hue twists.", self.cross_var, 0, 100)
        self.lbl_hal = create_slider_row(self.pane_light.content_frame, self.pane_light, "Dual-Stage Halation", "Red emulsion scatter around edges.", self.hal_var, 0, 100)
        self.lbl_bloom = create_slider_row(self.pane_light.content_frame, self.pane_light, "Lens Bloom", "Wide, soft white glow.", self.bloom_var, 0, 100)

        self.pane_print = CollapsiblePane(self.scroll_frame, "Darkroom Print", app=self)
        self.pane_print.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_print)
        self.lbl_cont = create_slider_row(self.pane_print.content_frame, self.pane_print, "Analog Print Contrast", "S-Curve contrast.", self.cont_var, 0, 100)
        self.lbl_subsat = create_slider_row(self.pane_print.content_frame, self.pane_print, "Subtractive Saturation", "Organically desaturates extreme highlights and shadows.", self.subsat_var, 0, 100)
        self.lbl_split = create_slider_row(self.pane_print.content_frame, self.pane_print, "Warm/Cool Split Tone", "Pushes midtones warm, shadows cool.", self.split_var, -50, 50)

        self.pane_grain = CollapsiblePane(self.scroll_frame, "Physical Grain", app=self)
        self.pane_grain.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_grain)
        self.lbl_grain_amt = create_slider_row(self.pane_grain.content_frame, self.pane_grain, "Dye Cloud Amount", "Intensity of physical grain.", self.grain_amt_var, 0, 100)
        self.lbl_grain_size = create_slider_row(self.pane_grain.content_frame, self.pane_grain, "Crystal Size", "Coarseness of the grain.", self.grain_size_var, 1.0, 5.0, is_float=True)
        self.lbl_grain_chroma = create_slider_row(self.pane_grain.content_frame, self.pane_grain, "Color Variation", "Blends between structural monochrome crystals (0%) and colored dye clouds (100%).", self.grain_chroma_var, 0, 100)

        self.pane_edge = CollapsiblePane(self.scroll_frame, "Edge Imperfections", app=self)
        self.pane_edge.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_edge)
        self.lbl_ff_amt = create_slider_row(self.pane_edge.content_frame, self.pane_edge, "Field Flatness Softness", "Optical degradation at edges.", self.ff_amt_var, 0, 100)
        self.lbl_ff_fall = create_slider_row(self.pane_edge.content_frame, self.pane_edge, "Field Flatness Creep", "Falloff size of degradation.", self.ff_fall_var, 0, 100)
        self.lbl_vig_amt = create_slider_row(self.pane_edge.content_frame, self.pane_edge, "Vignette Intensity", "Darkens the corners.", self.vig_amt_var, 0, 100)
        self.lbl_vig_fall = create_slider_row(self.pane_edge.content_frame, self.pane_edge, "Vignette Creep", "Falloff size of the vignette.", self.vig_fall_var, 0, 100)

        self.pane_levels = CollapsiblePane(self.scroll_frame, "Output Levels", app=self)
        self.pane_levels.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_levels)
        
        self.levels_widget = LevelsWidget(self.pane_levels.content_frame, self)
        self.levels_widget.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ToolTip(self.levels_widget.canvas, "Output Levels\nDrag triangles to adjust Black, Midtone (Gamma), and White points.\nRight-click to reset.")

        self.set_active_pane(self.pane_optics)
        self.update_labels()

    # --- UNDO / REDO LOGIC ---
    def get_current_state(self):
        return {
            'profile': self.profile_var.get(),
            'str': self.str_var.get(),
            'soft': self.soft_var.get(),
            'ca': self.ca_var.get(),
            'flat': self.flat_var.get(),
            'cross': self.cross_var.get(),
            'hal': self.hal_var.get(),
            'bloom': self.bloom_var.get(),
            'cont': self.cont_var.get(),
            'subsat': self.subsat_var.get(),
            'split': self.split_var.get(),
            'grain_amt': self.grain_amt_var.get(),
            'grain_size': self.grain_size_var.get(),
            'grain_chroma': self.grain_chroma_var.get(),
            'ff_amt': self.ff_amt_var.get(),
            'ff_fall': self.ff_fall_var.get(),
            'vig_amt': self.vig_amt_var.get(),
            'vig_fall': self.vig_fall_var.get(),
            'bp': self.bp_var.get(),
            'mid': self.mid_var.get(),
            'wp': self.wp_var.get(),
            'optics_on': self.pane_optics.switch_var.get(),
            'light_on': self.pane_light.switch_var.get(),
            'print_on': self.pane_print.switch_var.get(),
            'grain_on': self.pane_grain.switch_var.get(),
            'edge_on': self.pane_edge.switch_var.get(),
            'levels_on': self.pane_levels.switch_var.get()
        }

    def save_state(self):
        if self.is_restoring_state: return
        state = self.get_current_state()
        if self.undo_stack and self.undo_stack[-1] == state:
            return
        self.undo_stack.append(state)
        if len(self.undo_stack) > self.max_undo_steps + 1:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def apply_state(self, state):
        self.is_restoring_state = True
        
        prof = state['profile']
        self.profile_var.set(prof)
        if prof != "Select Film Emulation..." and prof != "--- NONE ---":
            if prof in self.preset_mapping:
                self.load_profile_from_file(self.preset_mapping[prof]) 
        else:
            self.film_profile = None
            self.curve_data = {}
            self.log_e_grid = []
            self.lbl_profile.configure(text="NO TONE PROFILE")

        self.str_var.set(state['str'])
        self.soft_var.set(state['soft'])
        self.ca_var.set(state['ca'])
        self.flat_var.set(state['flat'])
        self.cross_var.set(state['cross'])
        self.hal_var.set(state['hal'])
        self.bloom_var.set(state['bloom'])
        self.cont_var.set(state['cont'])
        self.subsat_var.set(state['subsat'])
        self.split_var.set(state['split'])
        self.grain_amt_var.set(state['grain_amt'])
        self.grain_size_var.set(state['grain_size'])
        self.grain_chroma_var.set(state['grain_chroma'])
        self.ff_amt_var.set(state['ff_amt'])
        self.ff_fall_var.set(state['ff_fall'])
        self.vig_amt_var.set(state['vig_amt'])
        self.vig_fall_var.set(state['vig_fall'])

        self.pane_optics.switch_var.set(state['optics_on'])
        self.pane_light.switch_var.set(state['light_on'])
        self.pane_print.switch_var.set(state['print_on'])
        self.pane_grain.switch_var.set(state['grain_on'])
        self.pane_edge.switch_var.set(state['edge_on'])
        self.pane_levels.switch_var.set(state['levels_on'])

        self.levels_widget.set_values_from_vars(state['bp'], state['mid'], state['wp'])
        
        self.update_labels()
        
        self.is_restoring_state = False
        self.trigger_render()

    def undo(self, event=None):
        if len(self.undo_stack) > 1: 
            current_state = self.undo_stack.pop()
            self.redo_stack.append(current_state)
            previous_state = self.undo_stack[-1]
            self.apply_state(previous_state)
            self.show_osd_message("Undo")

    def redo(self, event=None):
        if self.redo_stack:
            next_state = self.redo_stack.pop()
            self.undo_stack.append(next_state)
            self.apply_state(next_state)
            self.show_osd_message("Redo")

    def update_labels(self):
        self.lbl_soft.configure(text=f"Optical Softness: {int(self.soft_var.get())}%")
        self.lbl_ca.configure(text=f"Chromatic Aberration: {int(self.ca_var.get())}px")
        self.lbl_flat.configure(text=f"Cine-Log Flattening: {int(self.flat_var.get())}%")
        self.lbl_cross.configure(text=f"Emulsion Crosstalk: {int(self.cross_var.get())}%")
        self.lbl_hal.configure(text=f"Dual-Stage Halation: {int(self.hal_var.get())}%")
        self.lbl_bloom.configure(text=f"Lens Bloom: {int(self.bloom_var.get())}%")
        self.lbl_cont.configure(text=f"Analog Print Contrast: {int(self.cont_var.get())}%")
        self.lbl_subsat.configure(text=f"Subtractive Saturation: {int(self.subsat_var.get())}%")
        self.lbl_split.configure(text=f"Warm/Cool Split Tone: {int(self.split_var.get())}%")
        self.lbl_grain_amt.configure(text=f"Dye Cloud Amount: {int(self.grain_amt_var.get())}%")
        self.lbl_grain_size.configure(text=f"Crystal Size: {self.grain_size_var.get():.1f}")
        self.lbl_grain_chroma.configure(text=f"Color Variation: {int(self.grain_chroma_var.get())}%")
        
        if "Calculating" not in self.lbl_str.cget("text"):
            self.lbl_str.configure(text=f"Overall Physical Mix: {int(self.str_var.get())}%")
            
        self.lbl_ff_amt.configure(text=f"Field Flatness Softness: {int(self.ff_amt_var.get())}%")
        self.lbl_ff_fall.configure(text=f"Field Flatness Creep: {int(self.ff_fall_var.get())}%")
        self.lbl_vig_amt.configure(text=f"Vignette Intensity: {int(self.vig_amt_var.get())}%")
        self.lbl_vig_fall.configure(text=f"Vignette Creep: {int(self.vig_fall_var.get())}%")

    def update_histogram(self, orig_hist, proc_hist, pre_levels_hist=None):
        if orig_hist is None or proc_hist is None: return

        orig_max = max(orig_hist.max(), 1)
        proc_max = max(proc_hist.max(), 1)

        orig_hist_norm = orig_hist / orig_max
        proc_hist_norm = proc_hist / proc_max
        
        if pre_levels_hist is not None:
            self.levels_widget.set_histogram(pre_levels_hist)
        else:
            self.levels_widget.set_histogram(orig_hist_norm)

        self.hist_canvas.delete("all")
        
        w = self.hist_canvas.winfo_width()
        if w <= 1: w = 370 
        h = self.hist_canvas_h

        def draw_poly(hist_data, fill_color, outline_color):
            poly_points = [(0, h)]
            bin_w = w / 256.0
            for i, val in enumerate(hist_data):
                x = i * bin_w
                y = h - (val * h)
                poly_points.append((x, y))
            poly_points.append((w, h))
            self.hist_canvas.create_polygon(poly_points, fill=fill_color, outline=outline_color)

        draw_poly(orig_hist_norm, "#333333", "#444444")
        if not np.allclose(orig_hist_norm, proc_hist_norm, atol=0.001):
            draw_poly(proc_hist_norm, "#8B7300", "#FFD700")

    def update_canvases(self):
        if self.working_img_pil is None or self.processed_img_pil is None: return

        cw = self.canvas_left.winfo_width()
        ch = self.canvas_left.winfo_height()
        if cw <= 1 or ch <= 1: return 

        self.canvas_left.delete("all")
        self.canvas_right.delete("all")
        
        if not self.is_zoomed:
            img_w, img_h = self.working_img_pil.size
            scale = min(cw / img_w, ch / img_h)
            new_w, new_h = int(img_w * scale), int(img_h * scale)
            
            left_display = self.working_img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            right_display = self.processed_img_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            draw_x, draw_y = cw // 2, ch // 2
        else:
            target_w = int(self.current_chunk_pil.width * self.zoom_level)
            target_h = int(self.current_chunk_pil.height * self.zoom_level)
            
            left_display = self.current_chunk_pil.resize((target_w, target_h), Image.Resampling.BILINEAR)
            right_display = self.processed_img_pil.resize((target_w, target_h), Image.Resampling.BILINEAR)

            draw_x, draw_y = self.render_center_x, self.render_center_y

        if self.view_mode == "side_by_side":
            self.tk_img_left = ImageTk.PhotoImage(left_display)
            self.tk_img_right = ImageTk.PhotoImage(right_display)
            self.canvas_left.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_left, tags="render_img")
            self.canvas_right.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_right, tags="render_img")
        else:
            disp_w, disp_h = left_display.size
            composite = left_display.copy()
            
            screen_wipe_x = int(self.wipe_percent * cw)
            
            img_left_on_screen = draw_x - disp_w // 2
            wipe_px_in_img = screen_wipe_x - img_left_on_screen
            
            if 0 < wipe_px_in_img < disp_w:
                right_crop = right_display.crop((wipe_px_in_img, 0, disp_w, disp_h))
                composite.paste(right_crop, (wipe_px_in_img, 0))
            elif wipe_px_in_img <= 0:
                composite = right_display.copy()
                
            self.tk_img_left = ImageTk.PhotoImage(composite)
            self.canvas_left.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_left, tags="render_img")
            
            if not self.is_panning:
                self.canvas_left.create_line(screen_wipe_x, 0, screen_wipe_x, ch, fill="#A0A0A0", width=2, tags="wipe_line")
                self.canvas_left.create_polygon(screen_wipe_x-6, ch//2-10, screen_wipe_x+6, ch//2-10, screen_wipe_x+6, ch//2+10, screen_wipe_x-6, ch//2+10, fill="#A0A0A0", outline="#222222", tags="wipe_line")

        sf = ctk.ScalingTracker.get_widget_scaling(self)
        
        self.canvas_left.create_rectangle(int(15*sf), int(15*sf), int(95*sf), int(40*sf), fill="#222222", outline="")
        self.canvas_left.create_text(int(55*sf), int(27*sf), text="ORIGINAL", fill="white", font=("Arial", 10, "bold"))
        
        if self.view_mode == "side_by_side":
            self.canvas_right.create_rectangle(int(15*sf), int(15*sf), int(105*sf), int(40*sf), fill="#222222", outline="")
            self.canvas_right.create_text(int(60*sf), int(27*sf), text="DEHANCED", fill="white", font=("Arial", 10, "bold"))
        else:
            self.canvas_left.create_rectangle(cw-int(105*sf), int(15*sf), cw-int(15*sf), int(40*sf), fill="#222222", outline="")
            self.canvas_left.create_text(cw-int(60*sf), int(27*sf), text="DEHANCED", fill="white", font=("Arial", 10, "bold"))

        y_off = ch - int(40 * sf)
        
        z_text = f"{int(self.zoom_level * 100)}%" if self.is_zoomed else "FIT"
        z_color = "#FFD700" if self.is_zoomed else "#AAAAAA"
        
        self.canvas_left.create_rectangle(int(15*sf), y_off, int(70*sf), y_off + int(25*sf), fill="#222222", outline="")
        self.canvas_left.create_text(int(42*sf), y_off + int(12*sf), text=z_text, fill=z_color, font=("Arial", 10, "bold"))
        
        c_sbs = "#444444" if self.view_mode == "side_by_side" else "#222222"
        c_wipe = "#444444" if self.view_mode == "wipe" else "#222222"
        
        self.canvas_left.create_rectangle(int(85*sf), y_off, int(115*sf), y_off + int(25*sf), fill=c_sbs, outline="")
        self.canvas_left.create_text(int(100*sf), y_off + int(12*sf), text="[ | ]", fill="#FFFFFF", font=("Arial", 10, "bold"))
        
        self.canvas_left.create_rectangle(int(125*sf), y_off, int(180*sf), y_off + int(25*sf), fill=c_wipe, outline="")
        self.canvas_left.create_text(int(152*sf), y_off + int(12*sf), text="WIPE", fill="#FFFFFF", font=("Arial", 10, "bold"))
        
        if self.view_mode == "side_by_side" and self.is_zoomed:
            self.canvas_right.create_rectangle(int(15*sf), y_off, int(70*sf), y_off + int(25*sf), fill="#222222", outline="")
            self.canvas_right.create_text(int(42*sf), y_off + int(12*sf), text=z_text, fill=z_color, font=("Arial", 10, "bold"))

    def on_canvas_hover(self, event):
        if self.space_pressed: return
        
        cw = event.widget.winfo_width()
        ch = event.widget.winfo_height()
        sf = ctk.ScalingTracker.get_widget_scaling(self)
        y_off = ch - int(40 * sf)
        
        btn_w, btn_h = int(30 * sf), int(25 * sf)
        if (int(85*sf) <= event.x <= int(85*sf)+btn_w and y_off <= event.y <= y_off + btn_h) or \
           (int(125*sf) <= event.x <= int(125*sf)+int(55*sf) and y_off <= event.y <= y_off + btn_h):
            event.widget.config(cursor="hand2")
            return

        if self.working_img_pil is None:
            event.widget.config(cursor="arrow")
            return

        if self.view_mode == "wipe" and event.widget == self.canvas_left:
            img_w, img_h = self.working_img_pil.size
            if not self.is_zoomed:
                scale = min(cw / img_w, ch / img_h)
                disp_w = int(img_w * scale)
            else:
                scale = 1.0 
                disp_w = int((cw / self.zoom_level) * self.zoom_level)
                
            off_x = (cw - disp_w) // 2
            line_x = off_x + int(self.wipe_percent * disp_w)
            
            if abs(event.x - line_x) < 20:
                event.widget.config(cursor=self.cursor_wipe)
                return

        if self.is_zoomed:
            event.widget.config(cursor=self.cursor_zoom_out)
        else:
            event.widget.config(cursor=self.cursor_zoom_in)

    def on_space_press(self, event):
        self.space_pressed = True
        if self.is_zoomed:
            self.canvas_left.config(cursor=self.cursor_pan)
            self.canvas_right.config(cursor=self.cursor_pan)

    def on_space_release(self, event):
        self.space_pressed = False
        cur = self.cursor_zoom_out if self.is_zoomed else self.cursor_zoom_in
        self.canvas_left.config(cursor=cur)
        self.canvas_right.config(cursor=cur)

    def update_canvases_layout(self):
        if self.view_mode == "wipe":
            self.canvas_right.pack_forget()
            self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        else:
            self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 5), pady=10)
            self.canvas_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)
        self.update_canvases()

    def on_canvas_press(self, event):
        if self.working_img_pil is None: return
        
        cw = event.widget.winfo_width()
        ch = event.widget.winfo_height()
        sf = ctk.ScalingTracker.get_widget_scaling(self)
        y_off = ch - int(40 * sf)
        
        btn_w, btn_h = int(30 * sf), int(25 * sf)
        if int(85*sf) <= event.x <= int(85*sf)+btn_w and y_off <= event.y <= y_off + btn_h:
            self.view_mode = "side_by_side"
            self.update_canvases_layout()
            return
        if int(125*sf) <= event.x <= int(125*sf)+int(55*sf) and y_off <= event.y <= y_off + btn_h:
            self.view_mode = "wipe"
            self.update_canvases_layout()
            return

        img_w, img_h = self.working_img_pil.size
        if not self.is_zoomed:
            scale = min(cw / img_w, ch / img_h)
            disp_w = int(img_w * scale)
            disp_h = int(img_h * scale)
        else:
            scale = 1.0 
            disp_w = int((cw / self.zoom_level) * self.zoom_level)
            disp_h = int((ch / self.zoom_level) * self.zoom_level)
            
        off_x = (cw - disp_w) // 2
        off_y = (ch - disp_h) // 2

        if self.view_mode == "wipe" and not self.space_pressed:
            line_x = off_x + int(self.wipe_percent * disp_w)
            if abs(event.x - line_x) < 20: 
                self.wipe_dragging = True
                return

        if self.space_pressed and self.is_zoomed:
            self.is_panning = True
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            self.pan_cum_dx = 0
            self.pan_cum_dy = 0
            self.canvas_left.config(cursor=self.cursor_grab)
            self.canvas_right.config(cursor=self.cursor_grab)
            
            if self.view_mode == "wipe":
                self.canvas_left.delete("wipe_line")
            return

        if self.is_zoomed:
            self.is_zoomed = False
            self.zoom_level = 1.0
            event.widget.config(cursor=self.cursor_zoom_in)
            self.trigger_render()
        else:
            click_x = event.x - off_x
            click_y = event.y - off_y
            if 0 <= click_x <= disp_w and 0 <= click_y <= disp_h:
                click_x_proxy = click_x / scale
                click_y_proxy = click_y / scale
                master_w, master_h = self.original_image.size
                proxy_to_master = master_w / img_w
                
                self.zoom_center_master = (click_x_proxy * proxy_to_master, click_y_proxy * proxy_to_master)
                self.is_zoomed = True
                self.zoom_level = 1.0
                event.widget.config(cursor=self.cursor_zoom_out)
                self.trigger_render()

    def on_canvas_drag(self, event):
        if self.wipe_dragging:
            cw = event.widget.winfo_width()
            new_pct = event.x / cw
            self.wipe_percent = max(0.0, min(1.0, new_pct))
            self.update_canvases() 
            
        elif self.is_panning:
            dx = event.x - self.pan_start_x
            dy = event.y - self.pan_start_y
            self.pan_cum_dx += dx
            self.pan_cum_dy += dy
            self.pan_start_x = event.x
            self.pan_start_y = event.y
            
            self.canvas_left.move("render_img", dx, dy)
            self.canvas_right.move("render_img", dx, dy)

    def on_canvas_release(self, event):
        if self.wipe_dragging:
            self.wipe_dragging = False
            self.on_canvas_hover(event) 
        elif self.is_panning:
            self.is_panning = False
            
            if self.space_pressed:
                self.canvas_left.config(cursor=self.cursor_pan)
                self.canvas_right.config(cursor=self.cursor_pan)
            else:
                cur = self.cursor_zoom_out if self.is_zoomed else self.cursor_zoom_in
                self.canvas_left.config(cursor=cur)
                self.canvas_right.config(cursor=cur)
            
            shift_master_x = -(self.pan_cum_dx / self.zoom_level)
            shift_master_y = -(self.pan_cum_dy / self.zoom_level)
            
            zx, zy = self.zoom_center_master
            self.zoom_center_master = (zx + shift_master_x, zy + shift_master_y)
            
            self.trigger_render() 
            
    def on_mouse_wheel(self, event):
        if not self.is_zoomed or self.working_img_pil is None:
            return

        direction = 0
        if event.num == 4:
            direction = 1
        elif event.num == 5:
            direction = -1
        elif hasattr(event, 'delta'):
            if platform.system() == "Darwin":
                direction = 1 if event.delta > 0 else -1
            else:
                direction = 1 if event.delta > 0 else -1
                
        if direction == 0: return

        new_zoom = self.zoom_level + (0.5 * direction)
        new_zoom = max(1.0, min(new_zoom, 2.5))

        if new_zoom != self.zoom_level:
            self.zoom_level = new_zoom
            self.trigger_render()

    def on_drop(self, event):
        file_path = event.data
        if file_path.startswith('{') and file_path.endswith('}'):
            file_path = file_path[1:-1]
        
        valid_ext = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
        if file_path.lower().endswith(valid_ext):
            self.load_image_from_path(file_path)

    def load_image_dialog(self):
        file_path = filedialog.askopenfilename(filetypes=[("Images", "*.jpg;*.jpeg;*.png;*.tif;*.tiff")])
        if file_path:
            self.load_image_from_path(file_path)

    def load_image_from_path(self, file_path):
        try:
            self.original_image = Image.open(file_path).convert("RGB")
            w, h = self.original_image.size
            max_dim = max(w, h)
            
            if max_dim > 1024:
                ratio = 1024 / max_dim
                new_w, new_h = int(w * ratio), int(h * ratio)
                self.working_img_pil = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                self.working_img_pil = self.original_image.copy()
                
            self.preview_array = np.array(self.working_img_pil, dtype=np.float32) / 255.0
            self.is_zoomed = False
            self.zoom_level = 1.0
            self._last_view_state = None 
            
            self.processed_img_pil = None
            
            self.current_unprocessed_array = self.preview_array
            self.profile_dropdown.configure(state="normal")
            
            self.canvas_left.config(cursor=self.cursor_zoom_in)
            self.canvas_right.config(cursor=self.cursor_zoom_in)
            
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.save_state()
            
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                mode_str = "GPU" if cv2.ocl.useOpenCL() else "CPU"
                self.title(f"Image loaded. {w} x {h} px. {file_size_mb:.1f}Mb. {mode_str} Mode.")
            except Exception:
                self.title(self.base_title)
            
            self.trigger_render()
            
        except Exception as e:
            messagebox.showerror("Image Error", f"Could not load image:\n{e}")

    def on_profile_select(self, selected_name):
        if selected_name == "--- NONE ---":
            self.film_profile = None
            self.curve_data = {}
            self.log_e_grid = []
            
            self.levels_widget.reset()
            
            self.processed_img_pil = None 
            self.lbl_profile.configure(text="NO TONE PROFILE")
            
            self.trigger_render()
            self.save_state()
            return

        if selected_name not in self.preset_mapping:
            return
            
        file_path = self.preset_mapping[selected_name]
        self.load_profile_from_file(file_path)
        self.save_state()

    def load_profile_from_file(self, file_path):
        try:
            with open(file_path, 'r') as f:
                self.film_profile = json.load(f)
            
            csv_path = self.film_profile['data_files']['characteristic_curve']
            csv_full_path = os.path.join(os.path.dirname(file_path), csv_path)
            
            self.curve_data = {'r': [], 'g': [], 'b': []}
            self.log_e_grid = []
            with open(csv_full_path, 'r') as f:
                reader = csv.reader(f)
                headers = next(reader)
                for row in reader:
                    self.log_e_grid.append(float(row[0]))
                    self.curve_data['r'].append(float(row[1]))
                    self.curve_data['g'].append(float(row[2]))
                    self.curve_data['b'].append(float(row[3]))
            self.log_e_grid = np.array(self.log_e_grid)
            for ch in ['r', 'g', 'b']:
                self.curve_data[ch] = np.array(self.curve_data[ch])

            name = f"{self.film_profile['manufacturer']} {self.film_profile['film_name']}".upper()
            self.lbl_profile.configure(text=f"{name}") 
            self.trigger_render()
        except Exception as e:
            messagebox.showerror("Profile Error", f"Failed to load profile:\n{str(e)}")

    def _prepare_render_params(self):
        if self.original_image is None: return None
        
        master_w, master_h = self.original_image.size
        cw = self.canvas_left.winfo_width()
        ch = self.canvas_left.winfo_height()

        state_hash = hash((self.is_zoomed, self.zoom_level, self.zoom_center_master, id(self.original_image), cw, ch))
        
        if self._last_view_state != state_hash:
            if not self.is_zoomed:
                img_array = self.preview_array
                virtual_width = self.working_img_pil.width
                offset_x, offset_y = 0, 0
                mw, mh = self.working_img_pil.size
                self.render_center_x = cw // 2
                self.render_center_y = ch // 2
            else:
                zx, zy = self.zoom_center_master
                overscan = 2.0 
                
                crop_w_ideal = int((cw * overscan) / self.zoom_level)
                crop_h_ideal = int((ch * overscan) / self.zoom_level)

                left = int(zx - crop_w_ideal / 2)
                top = int(zy - crop_h_ideal / 2)
                right = int(zx + crop_w_ideal / 2)
                bottom = int(zy + crop_h_ideal / 2)

                left = max(0, left)
                top = max(0, top)
                right = min(right, master_w)
                bottom = min(bottom, master_h)

                if left >= right: left = 0; right = master_w
                if top >= bottom: top = 0; bottom = master_h

                self.current_chunk_pil = self.original_image.crop((left, top, right, bottom))
                img_array = np.array(self.current_chunk_pil, dtype=np.float32) / 255.0

                actual_cx_master = left + (right - left) / 2.0
                actual_cy_master = top + (bottom - top) / 2.0

                self.render_center_x = int(cw / 2 + (actual_cx_master - zx) * self.zoom_level)
                self.render_center_y = int(ch / 2 + (actual_cy_master - zy) * self.zoom_level)

                virtual_width = master_w
                offset_x, offset_y = left, top
                mw, mh = master_w, master_h

            self.current_unprocessed_array = img_array
            self._last_view_state = state_hash
            
            self._cached_virtual_width = virtual_width
            self._cached_true_master_width = master_w
            self._cached_master_width = mw
            self._cached_master_height = mh
            self._cached_offset_x = offset_x
            self._cached_offset_y = offset_y

        return {
            'img_array': self.current_unprocessed_array, 
            'full_proxy_array': self.preview_array, # ALWAYS PASS THE UNZOOMED PROXY FOR STATS
            'soft_amt': self.soft_var.get(),
            'ca_amt': self.ca_var.get(),
            'ff_amt': self.ff_amt_var.get(),
            'ff_fall': self.ff_fall_var.get(),
            'vig_amt': self.vig_amt_var.get(),
            'vig_fall': self.vig_fall_var.get(),
            'flatten_pct': self.flat_var.get(),
            'cross_pct': self.cross_var.get(),
            'hal_pct': self.hal_var.get(),
            'bloom_pct': self.bloom_var.get(),
            'contrast_pct': self.cont_var.get(),
            'subsat_pct': self.subsat_var.get(),
            'split_pct': self.split_var.get(),
            'grain_amt': self.grain_amt_var.get(),
            'grain_size': self.grain_size_var.get(),
            'grain_chroma': self.grain_chroma_var.get(),
            'strength_pct': self.str_var.get(),
            'bp_pct': self.bp_var.get(),
            'mid_val': self.mid_var.get(),
            'wp_pct': self.wp_var.get(),
            'optics_on': self.pane_optics.switch_var.get(),
            'light_on': self.pane_light.switch_var.get(),
            'print_on': self.pane_print.switch_var.get(),
            'grain_on': self.pane_grain.switch_var.get(),
            'edge_on': self.pane_edge.switch_var.get(),
            'levels_on': self.pane_levels.switch_var.get(),
            'virtual_width': self._cached_virtual_width,
            'true_master_width': self._cached_true_master_width,
            'master_width': self._cached_master_width,
            'master_height': self._cached_master_height,
            'offset_x': self._cached_offset_x,
            'offset_y': self._cached_offset_y,
            'is_auto_mixing': getattr(self, 'is_auto_mixing', False)
        }

    def trigger_render(self, event=None):
        if self.preview_array is None: 
            return
            
        self.update_labels()
        self.lbl_profile.configure(text="RENDERING...")

        params = self._prepare_render_params()
        if not params: return

        while not self.render_queue.empty():
            try:
                self.render_queue.get_nowait()
            except queue.Empty:
                break
                
        if self._render_after_id is not None:
            self.after_cancel(self._render_after_id)
            
        self._render_after_id = self.after(150, lambda p=params: self.render_queue.put(p))

    def _generate_radial_mask(self, h, w, falloff_pct, master_w, master_h, offset_x, offset_y):
        y_coords = np.arange(offset_y, offset_y + h, dtype=np.float32)
        x_coords = np.arange(offset_x, offset_x + w, dtype=np.float32)
        x, y = np.meshgrid(x_coords, y_coords)
        cy, cx = master_h / 2.0, master_w / 2.0
        max_dist = np.sqrt(cx**2 + cy**2)
        safe_radius = 1.0 - (falloff_pct / 100.0)
        
        mask = ne.evaluate("sqrt((x - cx)**2 + (y - cy)**2) / max_dist")
        mask = ne.evaluate("(mask - safe_radius) / (1.0 - safe_radius + 1e-5)")
        mask = ne.evaluate("where(mask > 0.0, mask, 0.0)")
        mask = ne.evaluate("where(mask < 1.0, mask, 1.0)")
        mask = ne.evaluate("mask * mask * (3.0 - 2.0 * mask)")
        
        return mask

    def _render_worker(self):
        self._render_cache = {} 
        self._stats_cache = {} 
        
        while True:
            params = self.render_queue.get() 
            try:
                # --- PASS 1: DECOUPLED STATS PIPELINE (Runs first to calculate Auto-Mix) ---
                params_stats = params.copy()
                params_stats['img_array'] = params['full_proxy_array']
                params_stats['grain_on'] = False # Exclude grain spikes from histogram math!
                
                # Reset spatial offsets so the edge masks perfectly fit the full proxy
                proxy_h, proxy_w, _ = params['full_proxy_array'].shape
                params_stats['virtual_width'] = proxy_w 
                params_stats['offset_x'] = 0
                params_stats['offset_y'] = 0
                params_stats['master_width'] = proxy_w
                params_stats['master_height'] = proxy_h
                params_stats.pop('full_proxy_array')
                
                stats_array, pre_levels_array, optimal_str = self.process_engine(self._stats_cache, **params_stats)

                # --- PASS 2: MAIN VIEWPORT RENDER ---
                # Renders the visible chunk, with full grain, for the UI.
                params_main = params.copy()
                params_main.pop('full_proxy_array')
                params_main['is_auto_mixing'] = False # Disable auto-mix on viewport chunk
                
                # If Auto-Mix found a new optimal strength, feed it directly into the viewport render parameters
                if optimal_str is not None:
                    params_main['strength_pct'] = optimal_str
                
                rendered_array, _, _ = self.process_engine(self._render_cache, **params_main)
                
                def calc_hist(arr):
                    if arr is None: return None
                    img_uint8 = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
                    gray = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2GRAY)
                    return cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()

                # Always base original histogram on the full un-zoomed proxy
                img_id = id(params['full_proxy_array'])
                if self._render_cache.get('orig_hist_hash') != img_id:
                    self._render_cache['orig_hist'] = calc_hist(params['full_proxy_array'])
                    self._render_cache['orig_hist_hash'] = img_id
                    
                orig_hist = self._render_cache['orig_hist']
                
                # Calculate histograms exclusively from the grain-free stats pass
                proc_hist = calc_hist(stats_array)
                pre_levels_hist = calc_hist(pre_levels_array)
                
                # Push the grain-inclusive image to the UI
                processed_pil = Image.fromarray((rendered_array * 255).astype(np.uint8))
                
                self.after(0, self._apply_render_result, processed_pil, orig_hist, proc_hist, pre_levels_hist, optimal_str)
            except Exception as e:
                print(f"Render engine error: {e}")

    def process_engine(self, cache, img_array, soft_amt, ca_amt, ff_amt, ff_fall, vig_amt, vig_fall, flatten_pct, 
                       cross_pct, hal_pct, bloom_pct, contrast_pct, subsat_pct, split_pct, grain_amt, grain_size, grain_chroma, strength_pct, 
                       bp_pct, mid_val, wp_pct, 
                       optics_on, light_on, print_on, grain_on, edge_on, levels_on,
                       virtual_width, true_master_width, master_width, master_height, offset_x, offset_y, is_auto_mixing=False):
        
        if not self.film_profile:
            bypass = np.clip(img_array, 0, 1)
            return bypass, bypass, None

        img_id = id(img_array)
        h, w, _ = img_array.shape

        def _fast_glow(img_mat, sigma):
            if sigma <= 5.0:
                return cv2.GaussianBlur(img_mat, (0, 0), sigma)
            
            ratio = sigma / 5.0
            new_w, new_h = max(16, int(w / ratio)), max(16, int(h / ratio))
            
            sigma_x = sigma / (w / new_w)
            sigma_y = sigma / (h / new_h)
            
            u_down = cv2.resize(img_mat, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            u_blur = cv2.GaussianBlur(u_down, (0, 0), sigmaX=sigma_x, sigmaY=sigma_y)
            return cv2.resize(u_blur, (w, h), interpolation=cv2.INTER_LINEAR)

        optics_hash = hash((img_id, soft_amt, ca_amt, optics_on, virtual_width))
        if cache.get('optics_hash') == optics_hash:
            img = cache['optics']
        else:
            img = np.copy(img_array)
            if optics_on:
                soft = soft_amt / 100.0
                ca_float = ca_amt * (virtual_width / true_master_width) 

                if soft > 0:
                    sigma = (virtual_width * 0.001) * (soft * 2)
                    u_img = cv2.UMat(img)
                    u_blur = _fast_glow(u_img, sigma)
                    img = u_blur.get()

                if ca_float > 0:
                    r, g, b = cv2.split(img)
                    M_R = np.float32([[1, 0, ca_float], [0, 1, ca_float]])
                    r_shift = cv2.warpAffine(r, M_R, (w, h), borderMode=cv2.BORDER_REPLICATE)
                    M_B = np.float32([[1, 0, -ca_float], [0, 1, -ca_float]])
                    b_shift = cv2.warpAffine(b, M_B, (w, h), borderMode=cv2.BORDER_REPLICATE)
                    img = cv2.merge([r_shift, g, b_shift])
            cache['optics'] = img
            cache['optics_hash'] = optics_hash

        light_hash = hash((optics_hash, flatten_pct, cross_pct, bloom_pct, hal_pct, light_on, virtual_width))
        if cache.get('light_hash') == light_hash:
            linear = cache['light']
        else:
            img_clipped = ne.evaluate("where(img > 0.0, img, 0.0)")
            linear = ne.evaluate("img_clipped ** 2.2")
            
            if light_on:
                flat_amount = flatten_pct / 100.0
                if flat_amount > 0:
                    log_base = 1.0 + (flat_amount * 10.0)
                    linear = ne.evaluate("log(1.0 + (log_base - 1.0) * linear) / log(log_base)")

                cross_amount = (cross_pct / 100.0) * 0.25 
                if cross_amount > 0:
                    r = linear[:,:,0]
                    g = linear[:,:,1]
                    b = linear[:,:,2]
                    ca_d = 1.0 + cross_amount
                    ca_n = -cross_amount
                    new_r = ne.evaluate("r * ca_d + g * ca_n")
                    new_g = ne.evaluate("g * ca_d + b * ca_n")
                    new_b = ne.evaluate("r * ca_n + b * ca_d")
                    linear = np.stack([new_r, new_g, new_b], axis=-1)
                    linear = ne.evaluate("where(linear > 0.0, linear, 0.0)")

                bloom = bloom_pct / 100.0
                if bloom > 0:
                    hl_mask_wide = ne.evaluate("where((linear - 0.5) / 0.5 > 0.0, (linear - 0.5) / 0.5, 0.0)")
                    hl_mask_wide = ne.evaluate("where(hl_mask_wide < 1.0, hl_mask_wide, 1.0)")
                    
                    mask_f32 = hl_mask_wide.astype(np.float32)
                    bloom_blur = _fast_glow(mask_f32, virtual_width * 0.02)
                    
                    linear = ne.evaluate("linear + (bloom_blur * bloom * 0.5)")
                
                hal = hal_pct / 100.0
                if hal > 0:
                    hl_threshold = 0.4
                    highlights = ne.evaluate("where((linear - hl_threshold) / (1.0 - hl_threshold) > 0.0, (linear - hl_threshold) / (1.0 - hl_threshold), 0.0)")
                    highlights = ne.evaluate("where(highlights < 1.0, highlights, 1.0)")
                    sigma_core = virtual_width * 0.005 
                    sigma_wide = virtual_width * 0.02  
                    
                    hl_f32 = highlights.astype(np.float32)
                    core_blur = _fast_glow(hl_f32, sigma_core)
                    wide_blur = _fast_glow(hl_f32, sigma_wide)
                    
                    halation_map = ne.evaluate("(core_blur * 0.6) + (wide_blur * 0.4)")
                    
                    hm_r = halation_map[:,:,0]
                    hm_g = halation_map[:,:,1]
                    hm_b = halation_map[:,:,2]
                    
                    r_hal = ne.evaluate("hm_r * 5.0 * hal")
                    g_hal = ne.evaluate("hm_g * 1.0 * hal")
                    b_hal = ne.evaluate("hm_b * 0.0 * hal")
                    
                    r = linear[:,:,0]
                    g = linear[:,:,1]
                    b = linear[:,:,2]
                    
                    r = ne.evaluate("r + r_hal")
                    g = ne.evaluate("g + g_hal")
                    b = ne.evaluate("b + b_hal")
                    linear = np.stack([r, g, b], axis=-1)
                    
            cache['light'] = linear
            cache['light_hash'] = light_hash

        film_prof_name = self.film_profile['film_name']
        film_hash = hash((light_hash, film_prof_name))
        if cache.get('film_hash') == film_hash:
            film_out = cache['film']
        else:
            digital_log = ne.evaluate("log10(where(linear > 1e-5, linear, 1e-5))")
            min_log_e = np.min(self.log_e_grid)
            max_log_e = np.max(self.log_e_grid)
            curve_center = (min_log_e + max_log_e) / 2.0
            
            mapped_log_e = ne.evaluate("digital_log - log10(0.18) + curve_center")
            
            out_r = np.interp(mapped_log_e[:, :, 0], self.log_e_grid, self.curve_data['r']).astype(np.float32)
            out_g = np.interp(mapped_log_e[:, :, 1], self.log_e_grid, self.curve_data['g']).astype(np.float32)
            out_b = np.interp(mapped_log_e[:, :, 2], self.log_e_grid, self.curve_data['b']).astype(np.float32)
            density = np.stack([out_r, out_g, out_b], axis=-1)
            
            density_scalar = 0.60 

            d_min_raw = self.film_profile['density_anchors']['d_min']
            d_max_raw = self.film_profile['density_anchors']['d_max']
            
            raw_min_array = np.array([d_min_raw['r'], d_min_raw['g'], d_min_raw['b']], dtype=np.float32) * density_scalar
            raw_max_array = np.array([d_max_raw['r'], d_max_raw['g'], d_max_raw['b']], dtype=np.float32) * density_scalar
            
            d_min_array = np.minimum(raw_min_array, raw_max_array)
            d_max_array = np.maximum(raw_min_array, raw_max_array)

            transmittance = ne.evaluate("10.0 ** (-1.0 * density * density_scalar)")
            t_max_3d = (10.0 ** (-d_min_array)).reshape(1,1,3)
            t_min_3d = (10.0 ** (-d_max_array)).reshape(1,1,3)
            
            t_norm = ne.evaluate("(transmittance - t_min_3d) / (t_max_3d - t_min_3d)")

            if self.film_profile['properties']['film_type'] == 'negative':
                out_linear = ne.evaluate("1.0 - t_norm")
            else:
                out_linear = t_norm

            out_linear = ne.evaluate("where(out_linear < 0.999, out_linear, 0.999)")
            out_linear = ne.evaluate("where(out_linear > 0.001, out_linear, 0.001)")
            
            inv_gamma = 1.0 / 2.2
            film_out = ne.evaluate("out_linear ** inv_gamma")
            
            cache['film'] = film_out
            cache['film_hash'] = film_hash

        current_film_out = ne.evaluate("where(film_out > 0.0, film_out, 0.0)")
        current_film_out = ne.evaluate("where(current_film_out < 1.0, current_film_out, 1.0)")
        
        optimal_str = None
        if is_auto_mixing:
            r_orig = img_array[:,:,0]
            g_orig = img_array[:,:,1]
            b_orig = img_array[:,:,2]
            r_film = current_film_out[:,:,0]
            g_film = current_film_out[:,:,1]
            b_film = current_film_out[:,:,2]
            
            orig_luma = ne.evaluate("0.299 * r_orig + 0.587 * g_orig + 0.114 * b_orig")
            orig_global_avg = np.mean(orig_luma)
            
            optimal_str = 40.0 
            for test_str in [100.0, 90.0, 80.0, 70.0, 60.0, 50.0, 40.0]:
                test_opacity = (test_str / 100.0) * 0.50 
                inv_opacity = 1.0 - test_opacity
                
                test_luma = ne.evaluate("0.299 * (r_orig * inv_opacity + r_film * test_opacity) + 0.587 * (g_orig * inv_opacity + g_film * test_opacity) + 0.114 * (b_orig * inv_opacity + b_film * test_opacity)")
                
                if (np.mean(test_luma) - orig_global_avg) <= 0.06: 
                    optimal_str = test_str
                    break
            
            strength_pct = optimal_str

        print_hash = hash((film_hash, contrast_pct, subsat_pct, split_pct, print_on, strength_pct))
        if cache.get('print_hash') == print_hash:
            blended = cache['print']
        else:
            if print_on:
                contrast = contrast_pct / 100.0
                if contrast > 0:
                    k = 0.46 
                    n = 2.5  
                    x_n = ne.evaluate("where(current_film_out > 1e-6, current_film_out, 1e-6) ** n")
                    k_n = k ** n
                    nr_curve = ne.evaluate("x_n / (x_n + k_n)")
                    max_val = 1.0 / (1.0 + k_n)
                    nr_curve = ne.evaluate("nr_curve / max_val")
                    current_film_out = ne.evaluate("(current_film_out * (1.0 - contrast)) + (nr_curve * contrast)")

                subsat_amount = (subsat_pct / 100.0) * 0.85 
                if subsat_amount > 0:
                    r = current_film_out[:,:,0]
                    g = current_film_out[:,:,1]
                    b = current_film_out[:,:,2]
                    luma = ne.evaluate("0.299 * r + 0.587 * g + 0.114 * b")
                    
                    sat_mult = ne.evaluate("1.0 - subsat_amount * ((2.0 * luma - 1.0) ** 2.0)")
                    sat_mult = ne.evaluate("where(sat_mult > 0.0, sat_mult, 0.0)")
                    sat_mult = ne.evaluate("where(sat_mult < 1.0, sat_mult, 1.0)")
                    
                    r = ne.evaluate("luma + (r - luma) * sat_mult")
                    g = ne.evaluate("luma + (g - luma) * sat_mult")
                    b = ne.evaluate("luma + (b - luma) * sat_mult")
                    current_film_out = np.stack([r,g,b], axis=-1)

                split = split_pct / 100.0
                if abs(split) > 0:
                    r = current_film_out[:,:,0]
                    g = current_film_out[:,:,1]
                    b = current_film_out[:,:,2]
                    luma = ne.evaluate("0.299 * r + 0.587 * g + 0.114 * b")
                    warm_r, warm_g, warm_b = 1.1, 1.0, 0.9
                    cool_r, cool_g, cool_b = 0.9, 1.0, 1.1
                    
                    if split > 0: 
                        cmap_r = ne.evaluate("(warm_r * luma) + (cool_r * (1.0 - luma))")
                        cmap_g = ne.evaluate("(warm_g * luma) + (cool_g * (1.0 - luma))")
                        cmap_b = ne.evaluate("(warm_b * luma) + (cool_b * (1.0 - luma))")
                        r = ne.evaluate("r * ((1.0 - split) + (cmap_r * split))")
                        g = ne.evaluate("g * ((1.0 - split) + (cmap_g * split))")
                        b = ne.evaluate("b * ((1.0 - split) + (cmap_b * split))")
                    else: 
                        neg_split = -split
                        cmap_r = ne.evaluate("(cool_r * luma) + (warm_r * (1.0 - luma))")
                        cmap_g = ne.evaluate("(cool_g * luma) + (warm_g * (1.0 - luma))")
                        cmap_b = ne.evaluate("(cool_b * luma) + (warm_b * (1.0 - luma))")
                        r = ne.evaluate("r * ((1.0 + split) + (cmap_r * neg_split))")
                        g = ne.evaluate("g * ((1.0 + split) + (cmap_g * neg_split))")
                        b = ne.evaluate("b * ((1.0 + split) + (cmap_b * neg_split))")
                    current_film_out = np.stack([r,g,b], axis=-1)

            current_film_out = ne.evaluate("where(current_film_out > 0.0, current_film_out, 0.0)")
            current_film_out = ne.evaluate("where(current_film_out < 1.0, current_film_out, 1.0)")
            
            max_opacity_limit = 0.50
            opacity = (strength_pct / 100.0) * max_opacity_limit
            blended = ne.evaluate("(img_array * (1.0 - opacity)) + (current_film_out * opacity)")
            cache['print'] = blended
            cache['print_hash'] = print_hash

        pre_levels_blended = np.copy(blended)

        levels_hash = hash((print_hash, bp_pct, mid_val, wp_pct, levels_on))
        if cache.get('levels_hash') == levels_hash:
            blended_levels = cache['levels']
        else:
            blended_levels = np.copy(blended)
            if levels_on:
                bp = bp_pct / 255.0
                wp = wp_pct / 255.0
                if bp > 0.0 or wp < 1.0 or mid_val != 1.0:
                    blended_levels = ne.evaluate("(blended_levels - bp) / (wp - bp + 1e-5)")
                    blended_levels = ne.evaluate("where(blended_levels > 0.0, blended_levels, 0.0)")
                    blended_levels = ne.evaluate("where(blended_levels < 1.0, blended_levels, 1.0)")
                    if mid_val != 1.0:
                        inv_mid = 1.0 / mid_val
                        blended_levels = ne.evaluate("blended_levels ** inv_mid")
            cache['levels'] = blended_levels
            cache['levels_hash'] = levels_hash

        final_out = np.copy(blended_levels)
        
        if grain_on:
            grain = grain_amt / 100.0
            chroma = grain_chroma / 100.0
            if grain > 0:
                applied_grain_size = grain_size * (virtual_width / true_master_width)
                scale = max(1.0, applied_grain_size / 1.5)
                
                gh, gw = int(h / scale), int(w / scale)
                
                base_noise = np.random.normal(0, 1.0, (gh, gw, 3)).astype(np.float32)
                
                if scale > 1.0:
                    noise = cv2.resize(base_noise, (w, h), interpolation=cv2.INTER_LINEAR)
                else:
                    noise = base_noise
                
                noise = ne.evaluate("sign(noise) * (abs(noise) ** 1.5)")
                
                n_0 = noise[:,:,0]
                n_1 = noise[:,:,1]
                n_2 = noise[:,:,2]
                n_luma = ne.evaluate("(n_0 + n_1 + n_2) / 3.0")
                
                luma_blend = 1.0 - chroma
                n_r = ne.evaluate("(n_luma * luma_blend) + (n_0 * chroma)")
                n_g = ne.evaluate("(n_luma * luma_blend) + (n_1 * chroma)")
                n_b = ne.evaluate("(n_luma * luma_blend) + (n_2 * chroma)")
                    
                r = final_out[:,:,0]
                g = final_out[:,:,1]
                b = final_out[:,:,2]
                luma_img = ne.evaluate("0.299 * r + 0.587 * g + 0.114 * b")
                
                grain_mask = ne.evaluate("(luma_img ** 0.5) * ((1.0 - luma_img) ** 1.5) * 2.5")
                grain_mask = ne.evaluate("where(grain_mask > 0.0, grain_mask, 0.0)")
                grain_mask = ne.evaluate("where(grain_mask < 1.0, grain_mask, 1.0)")
                
                grain_factor = grain * 0.15
                
                r = ne.evaluate("r + (n_r * grain_mask * grain_factor)")
                g = ne.evaluate("g + (n_g * grain_mask * grain_factor)")
                b = ne.evaluate("b + (n_b * grain_mask * grain_factor)")
                final_out = np.stack([r,g,b], axis=-1)

        if edge_on:
            if ff_amt > 0:
                ff_mask = self._generate_radial_mask(h, w, ff_fall, master_width, master_height, offset_x, offset_y)
                max_sigma = (virtual_width * 0.005) * (ff_amt / 100.0) 
                
                blurred_img = _fast_glow(final_out, max_sigma)
                
                r = final_out[:,:,0]
                g = final_out[:,:,1]
                b = final_out[:,:,2]
                br = blurred_img[:,:,0]
                bg = blurred_img[:,:,1]
                bb = blurred_img[:,:,2]
                
                r = ne.evaluate("(r * (1.0 - ff_mask)) + (br * ff_mask)")
                g = ne.evaluate("(g * (1.0 - ff_mask)) + (bg * ff_mask)")
                b = ne.evaluate("(b * (1.0 - ff_mask)) + (bb * ff_mask)")
                final_out = np.stack([r,g,b], axis=-1)

            if vig_amt > 0:
                vig_mask = self._generate_radial_mask(h, w, vig_fall, master_width, master_height, offset_x, offset_y)
                intensity = vig_amt / 100.0
                v_mult = ne.evaluate("1.0 - (vig_mask * intensity)")
                
                r = final_out[:,:,0]
                g = final_out[:,:,1]
                b = final_out[:,:,2]
                r = ne.evaluate("r * v_mult")
                g = ne.evaluate("g * v_mult")
                b = ne.evaluate("b * v_mult")
                final_out = np.stack([r,g,b], axis=-1)

        final_out = ne.evaluate("where(final_out > 0.0, final_out, 0.0)")
        final_out = ne.evaluate("where(final_out < 1.0, final_out, 1.0)")
        pre_levels_blended = ne.evaluate("where(pre_levels_blended > 0.0, pre_levels_blended, 0.0)")
        pre_levels_blended = ne.evaluate("where(pre_levels_blended < 1.0, pre_levels_blended, 1.0)")

        return final_out, pre_levels_blended, optimal_str

    def _apply_render_result(self, final_pil, orig_hist, proc_hist, pre_levels_hist, optimal_str):
        if optimal_str is not None:
            self.is_auto_mixing = False
            self.str_var.set(optimal_str)
            self.lbl_str.configure(text=f"Overall Physical Mix: {int(optimal_str)}% (Auto)")
            self.save_state()
            
        self.processed_img_pil = final_pil
        if self.film_profile:
            name = f"{self.film_profile['manufacturer']} {self.film_profile['film_name']}".upper()
            self.lbl_profile.configure(text=f"{name}")
        else:
            self.lbl_profile.configure(text="NO TONE PROFILE")
            
        self.update_canvases()
        self.update_histogram(orig_hist, proc_hist, pre_levels_hist)

    def export_image(self):
        if self.original_image is None or not self.film_profile:
            messagebox.showwarning("Warning", "Load an image and profile first.")
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("TIFF Image", "*.tif"), ("JPEG Image", "*.jpg")]
        )
        if not save_path: return
        
        full_array = np.array(self.original_image, dtype=np.float32) / 255.0
        self.lbl_profile.configure(text="EXPORTING FULL-RES...")
        self.update_idletasks() 
        
        master_w, master_h = self.original_image.size
        
        rendered_array, _, _ = self.process_engine(
            cache={},
            img_array=full_array, 
            soft_amt=self.soft_var.get(),
            ca_amt=self.ca_var.get(),
            ff_amt=self.ff_amt_var.get(),
            ff_fall=self.ff_fall_var.get(),
            vig_amt=self.vig_amt_var.get(),
            vig_fall=self.vig_fall_var.get(),
            flatten_pct=self.flat_var.get(),
            cross_pct=self.cross_var.get(),
            hal_pct=self.hal_var.get(),
            bloom_pct=self.bloom_var.get(),
            contrast_pct=self.cont_var.get(),
            subsat_pct=self.subsat_var.get(),
            split_pct=self.split_var.get(),
            grain_amt=self.grain_amt_var.get(),
            grain_size=self.grain_size_var.get(),
            grain_chroma=self.grain_chroma_var.get(),
            strength_pct=self.str_var.get(),
            bp_pct=self.bp_var.get(),
            mid_val=self.mid_var.get(),
            wp_pct=self.wp_var.get(),
            optics_on=self.pane_optics.switch_var.get(),
            light_on=self.pane_light.switch_var.get(),
            print_on=self.pane_print.switch_var.get(),
            grain_on=self.pane_grain.switch_var.get(),
            edge_on=self.pane_edge.switch_var.get(),
            levels_on=self.pane_levels.switch_var.get(),
            virtual_width=master_w,
            true_master_width=master_w,
            master_width=master_w,
            master_height=master_h,
            offset_x=0,
            offset_y=0,
            is_auto_mixing=False
        )
        rendered_img = Image.fromarray((rendered_array * 255).astype(np.uint8))
        
        ext = save_path.lower()
        if ext.endswith(".jpg") or ext.endswith(".jpeg"):
            rendered_img.save(save_path, quality=100, subsampling=0)
        elif ext.endswith(".png"):
            rendered_img.save(save_path, compress_level=1)
        elif ext.endswith(".tif") or ext.endswith(".tiff"):
            rendered_img.save(save_path, compression="tiff_deflate")
        else:
            rendered_img.save(save_path)

        name = f"{self.film_profile['manufacturer']} {self.film_profile['film_name']}".upper()
        self.lbl_profile.configure(text=f"SAVED: {name}")

if __name__ == "__main__":
    app = FilmRendererApp()
    app.mainloop()