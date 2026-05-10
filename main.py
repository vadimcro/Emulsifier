import tkinter as tk
from tkinter import filedialog, messagebox, colorchooser
import customtkinter as ctk
from PIL import Image, ImageTk, ImageGrab
import numpy as np
import cv2
import json
import csv
import os
import sys
import gc
import threading
import queue
import platform
from gallery_lightbox import GalleryLightbox

# --- UI DEPENDENCY CHECK ---
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing UI Dependencies", 
        "Emulsifier requires 'tkinterdnd2' and 'customtkinter'.\n\n"
        "Please open your terminal and run:\npip install tkinterdnd2 customtkinter"
    )
    sys.exit(1)

# --- IMPORT OUR MODULARIZED COMPONENTS ---
try:
    from ui_widgets import ToolTip, BypassSwitch, CollapsiblePane, LightroomSlider, LevelsWidget
    import engine
except ImportError as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing Modules", 
        f"Could not load application modules:\n{e}\n\nPlease ensure ui_widgets.py and engine.py are in the same folder."
    )
    sys.exit(1)


# Initialize CustomTkinter globally
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# --- MAIN APPLICATION ---
class FilmRendererApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.base_title = "Emulsifier Film Emulator - Modular Engine v2.01"
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

        # --- CROSS-PLATFORM PATHING ---
        if getattr(sys, 'frozen', False):
            self.base_dir = os.path.dirname(sys.executable)
        else:
            self.base_dir = os.path.dirname(os.path.abspath(__file__))

        self.recipes_dir = os.path.join(self.base_dir, "recipes")
        if not os.path.exists(self.recipes_dir):
            os.makedirs(self.recipes_dir)

        self.original_image = None
        self.working_img_pil = None       
        self.preview_array = None         
        self.processed_img_pil = None     
        self.current_chunk_pil = None 
        self.current_unprocessed_array = None 
        self._last_view_state = None      
        
        self.hovered_btn = None 
        self.preset_mapping = {}

        self.view_mode = "single"
        self.wipe_percent = 0.5
        self.show_original_toggle = False 
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
        
        # --- ARCH FIX: FULLSCREEN TOGGLE FLAG ---
        self.is_fullscreen = False

        self.film_profile = None   
        self.curve_data = {}       
        self.log_e_grid = []

        # --- ARCHITECTURE FIX: THREAD-SAFE QUEUES ---
        self.render_queue = queue.Queue(maxsize=1) 
        self.result_queue = queue.Queue(maxsize=1)
        self._render_after_id = None
        
        # Shared cache dict explicitly initialized ONCE here
        self._render_cache = {}
        
        self.worker_thread = threading.Thread(target=self._render_worker, daemon=True)
        self.worker_thread.start()
        
        # Start the 60FPS UI poller
        self._poll_results()
        
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

        self.str_var = ctk.DoubleVar(master=self, value=65) 
        self.soft_var = ctk.DoubleVar(master=self, value=10)
        self.ca_var = ctk.DoubleVar(master=self, value=1)
        
        self.cross_var = ctk.DoubleVar(master=self, value=15) 
        self.flat_var = ctk.DoubleVar(master=self, value=10)
        self.hal_var = ctk.DoubleVar(master=self, value=15)
        self.bloom_var = ctk.DoubleVar(master=self, value=7.5)
        
        self.cont_var = ctk.DoubleVar(master=self, value=25)
        self.split_var = ctk.DoubleVar(master=self, value=15)
        self.subsat_var = ctk.DoubleVar(master=self, value=30) 
        
        self.grain_amt_var = ctk.DoubleVar(master=self, value=20)
        self.grain_size_var = ctk.DoubleVar(master=self, value=1.2)
        self.grain_chroma_var = ctk.DoubleVar(master=self, value=12) 
        self.ff_amt_var = ctk.DoubleVar(master=self, value=0)
        self.ff_fall_var = ctk.DoubleVar(master=self, value=40)
        self.vig_amt_var = ctk.DoubleVar(master=self, value=0)
        self.vig_fall_var = ctk.DoubleVar(master=self, value=30)
        
        self.flare_amt_var = ctk.DoubleVar(master=self, value=0)
        self.flare_u_var = ctk.DoubleVar(master=self, value=1.5) 
        self.flare_v_var = ctk.DoubleVar(master=self, value=1.5)
        self.is_placing_flare = False

        self.wash_amt_var = ctk.DoubleVar(master=self, value=25)          
        self.wash_color_var = ctk.StringVar(master=self, value="none")    
        self.wash_buttons = {} 

        self.setup_ui()

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop)
        
        self.bind("<KeyPress-space>", self.on_space_press)
        self.bind("<KeyRelease-space>", self.on_space_release)
        
        self.bind("<Control-v>", self.paste_image)
        self.bind("<Command-v>", self.paste_image)
        
        self.bind("<Control-z>", self.undo)
        self.bind("<Command-z>", self.undo)
        self.bind("<Control-y>", self.redo)
        self.bind("<Command-y>", self.redo)
        self.bind("<Control-Z>", self.redo) 
        self.bind("<Command-Z>", self.redo)

        self.bind("<KeyPress-slash>", self.on_slash_press)
        self.bind("<KeyRelease-slash>", self.on_slash_release)
        self.bind("<Escape>", self.exit_fullscreen)

    def _poll_results(self):
        """Safely checks for completed frames 60 times a second."""
        try:
            while not self.result_queue.empty():
                res = self.result_queue.get_nowait()
                if 'error' in res:
                    self._handle_render_error(res['error'])
                else:
                    self._apply_render_result(
                        res['pil'], res['orig_hist'], res['proc_hist'], 
                        res['pre_levels_hist'], res['optimal_str'], 
                        res['auto_bp'], res['auto_wp']
                    )
        except queue.Empty:
            pass
        
        self.after(16, self._poll_results)

    def _handle_render_error(self, error_msg):
        self.lbl_profile.configure(text="RENDER ERROR", text_color="#FF4444")
        self.show_osd_message("Engine Error (Check Console)")
        self.is_auto_mixing = False
        self.is_auto_levels = False
        self.update_canvases() 

    # --- RECIPE ECOSYSTEM ---
    def save_recipe_dialog(self):
        if not self.film_profile:
            self.show_no_profile_warning()
            return
            
        dialog = ctk.CTkInputDialog(text="Enter a name for this Recipe:", title="Save Recipe")
        name = dialog.get_input()
        
        if name:
            filename = "".join(x for x in name if x.isalnum() or x in " _-").replace(" ", "_") + ".json"
            filepath = os.path.join(self.recipes_dir, filename)
            
            recipe_data = {
                "type": "emulsifier_recipe",
                "version": "1.89.1",
                "name": name,
                "state": self.get_current_state()
            }
            
            try:
                with open(filepath, 'w') as f:
                    json.dump(recipe_data, f, indent=4)
                self.show_osd_message(f"Recipe Saved:\n{name}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save recipe:\n{e}")

    def _generate_gradient_icon(self, size=24):
        import math
        from PIL import Image
        
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        
        for y in range(size):
            for x in range(size):
                cx, cy = size / 2, size / 2
                dist = math.hypot(x - cx, y - cy)
                
                if dist <= cx:
                    pct_x = x / size
                    pct_y = y / size
                    
                    r = int(50 + (200 * pct_x))
                    g = int(200 - (100 * pct_y))
                    b = int(250 - (200 * pct_x))
                    
                    alpha = 255
                    if dist > cx - 1:
                        alpha = int(255 * (cx - dist))
                        
                    img.putpixel((x, y), (r, g, b, alpha))
                    
        return img            

    def load_recipe_dialog(self):
        filepath = filedialog.askopenfilename(
            initialdir=self.recipes_dir, 
            title="Load Recipe",
            filetypes=[("Emulsifier Recipe", "*.json")]
        )
        
        if filepath:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    
                if data.get("type") != "emulsifier_recipe":
                    messagebox.showerror("Invalid File", "This is not a valid Emulsifier Recipe file.")
                    return

                state = data.get("state", {})
                prof = state.get("profile")

                warning_msg = ""
                if prof and prof != "Select Film Emulation..." and prof != "--- NONE ---":
                    if prof not in self.preset_mapping:
                        warning_msg = f"\nWarning: Target Film Profile '{prof}' is missing."
                        state["profile"] = "--- NONE ---" 

                self.apply_state(state)
                self.show_osd_message(f"Recipe Loaded:\n{data.get('name', 'Unknown')}{warning_msg}")

            except Exception as e:
                messagebox.showerror("Load Error", f"Could not load recipe:\n{e}")

    # --- CLIPBOARD SYSTEM ---
    def paste_image(self, event=None):
        try:
            img = ImageGrab.grabclipboard()
            
            if isinstance(img, Image.Image):
                self.original_image = img.convert("RGB")
            elif isinstance(img, list) and len(img) > 0 and isinstance(img[0], str):
                file_path = img[0]
                valid_ext = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
                if file_path.lower().endswith(valid_ext):
                    self.load_image_from_path(file_path)
                    self.show_osd_message("Image File Pasted")
                return
            else:
                return 
                
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
            
            # --- ARCH FIX: Safely clear shared dict memory ---
            self._render_cache.clear()
            
            self.tk_img_left = None
            self.tk_img_right = None
            
            gc.collect() 
            
            self.save_state()
            
            mode_str = "GPU" if cv2.ocl.useOpenCL() else "CPU"
            file_size_mb = (w * h * 3) / (1024 * 1024) 
            self.title(f"{self.base_title} - Clipboard Image loaded. {w} x {h} px. ~{file_size_mb:.1f}Mb. {mode_str} Mode.")
            
            self.show_osd_message("Image Pasted From Clipboard")
            self.trigger_render()
            
        except Exception as e:
            pass

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
            
            # --- ARCH FIX: Updated to match exact init defaults ---
            self.str_var.set(65)
            self.soft_var.set(10)
            self.ca_var.set(1)
            self.cross_var.set(15)
            self.flat_var.set(10)  
            self.hal_var.set(15)   
            self.bloom_var.set(7.5)
            self.cont_var.set(25)
            self.split_var.set(15)
            self.subsat_var.set(30)
            
            # Fixed Grain Defaults
            self.grain_amt_var.set(20)
            self.grain_size_var.set(1.2)
            self.grain_chroma_var.set(12)
            
            self.ff_amt_var.set(0)
            self.ff_fall_var.set(40)
            self.vig_amt_var.set(0)
            self.vig_fall_var.set(30)
            self.flare_amt_var.set(0)
            self.flare_u_var.set(1.5)
            self.flare_v_var.set(1.5)

            self.wash_amt_var.set(25)
            self.wash_color_var.set("none")
            if hasattr(self, 'update_wash_halos'): self.update_wash_halos("none")

            self.pane_optics.switch_var.set(True)
            self.pane_light.switch_var.set(True)
            self.pane_print.switch_var.set(True)
            self.pane_grain.switch_var.set(True)
            self.pane_edge.switch_var.set(True)
            self.pane_levels.switch_var.set(True)
            self.pane_flare.switch_var.set(True)
            
            self.levels_widget.reset()
            
            self.update_labels()
            self.trigger_render()
            self.show_osd_message("Workspace Reset")

    def on_slash_press(self, event):
        if not getattr(self, 'show_original_toggle', False):
            self.show_original_toggle = True
            self.update_canvases()

    def on_slash_release(self, event):
        if getattr(self, 'show_original_toggle', False):
            self.show_original_toggle = False
            self.update_canvases()

    # --- FULLSCREEN DISTRACTION-FREE TOGGLE ---
    def toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        
        # Tell the OS to take over the entire monitor
        self.attributes("-fullscreen", self.is_fullscreen)
        
        if self.is_fullscreen:
            self.control_container.pack_forget()
            self.preview_frame.configure(bg="#000000") # Pure black for OS Fullscreen
            self.canvas_left.configure(bg="#000000")
            self.canvas_right.configure(bg="#000000")
        else:
            self.control_container.pack(side=tk.RIGHT, fill=tk.Y)
            self.preview_frame.configure(bg="#111111")
            self.canvas_left.configure(bg="#151515")
            self.canvas_right.configure(bg="#151515")
        self.update_canvases()

    def exit_fullscreen(self, event=None):
        """Escape hatch for OS-level fullscreen."""
        if getattr(self, 'is_fullscreen', False):
            self.toggle_fullscreen()

    def on_space_press(self, event):
        if self.space_pressed: return # Prevent OS auto-repeat from strobing
        self.space_pressed = True
        
        if self.is_zoomed:
            self.canvas_left.config(cursor=self.cursor_pan)
            self.canvas_right.config(cursor=self.cursor_pan)
        elif self.view_mode == "single" and self.film_profile is not None:
            self.toggle_fullscreen()

    def on_space_release(self, event):
        self.space_pressed = False
        if not getattr(self, 'is_fullscreen', False):
            cur = self.cursor_zoom_out if self.is_zoomed else self.cursor_zoom_in
            self.canvas_left.config(cursor=cur)
            self.canvas_right.config(cursor=cur)


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
        profiles_dir = os.path.join(self.base_dir, "profiles")
        cache_file = os.path.join(self.base_dir, "_profiles_cache.json")
        
        if not os.path.exists(profiles_dir) or not os.path.isdir(profiles_dir):
            messagebox.showerror(
                "Missing Folder", 
                f"Could not find the required '/profiles' folder.\n\n"
                f"Please ensure it exists in the same directory as the app:\n{self.base_dir}"
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
            canvas.bind("<Leave>", self.on_canvas_leave) 

        self.canvas_left.bind("<Configure>", lambda e: self.update_canvases())

        self.control_container = ctk.CTkFrame(self, width=400, fg_color="#1E1E1E", corner_radius=0)
        self.control_container.pack_propagate(False)
        self.control_container.pack(side=tk.RIGHT, fill=tk.Y)

        self.top_pinned = ctk.CTkFrame(self.control_container, fg_color="transparent")
        self.top_pinned.pack(side=tk.TOP, fill=tk.X, padx=15, pady=(15, 0))

        # --- ROW 1: Load Image & Reset ---
        self.row1_frame = ctk.CTkFrame(self.top_pinned, fg_color="transparent")
        self.row1_frame.pack(fill=tk.X, pady=(0, 6))

        self.btn_load = ctk.CTkButton(self.row1_frame, text="Load Digital / AI Photo", command=self.load_image_dialog, 
                      fg_color="#5C5C5C", hover_color="#8B7300", text_color="#FFFFFF", height=40,
                      font=ctk.CTkFont(family="Arial", size=14, weight="bold"))
        self.btn_load.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.btn_reset = ctk.CTkButton(self.row1_frame, text="↺", width=40, height=40,
                                       fg_color="#7A2828", hover_color="#B22222", text_color="#FFFFFF",
                                       font=ctk.CTkFont(family="Arial", size=18, weight="bold"),
                                       command=self.confirm_reset)
        self.btn_reset.pack(side=tk.RIGHT)
        ToolTip(self.btn_reset, "Master Reset: Return all sliders, switches, and profiles to default.")

        # --- ROW 2: Profile Dropdown & Gallery ---
        self.row2_frame = ctk.CTkFrame(self.top_pinned, fg_color="transparent")
        self.row2_frame.pack(fill=tk.X, pady=(0, 10))

        preset_names = self.refresh_and_load_presets()
        
        self.profile_var = ctk.StringVar(master=self, value="Select Film Emulation...")
        self.profile_dropdown = ctk.CTkOptionMenu(
            self.row2_frame,
            variable=self.profile_var,
            values=preset_names,
            command=self.on_profile_select,
            fg_color="#333333", button_color="#444444", button_hover_color="#555555",
            dropdown_fg_color="#2A2A2A", dropdown_hover_color="#444444", 
            font=ctk.CTkFont(family="Arial", size=13),
            dropdown_font=ctk.CTkFont(family="Arial", size=13),
            height=40, 
            state="disabled" 
        )
        self.profile_dropdown.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        def open_gallery():
            if self.preview_array is None:
                messagebox.showwarning("Warning", "Please load an image first.")
                return
            GalleryLightbox(self)

        self.btn_gallery = ctk.CTkButton(self.row2_frame, text="⌕", width=40, height=40,
                                         fg_color="#333333", hover_color="#444444", text_color="#FFFFFF",
                                         font=ctk.CTkFont(family="Arial", size=26, weight="bold"),
                                         command=open_gallery)
        self.btn_gallery.pack(side=tk.RIGHT)
        ToolTip(self.btn_gallery, "Open the Lightbox Gallery to compare all film presets visually.")

        # --- ROW 3: Active Profile Label ---
        self.lbl_profile = ctk.CTkLabel(self.top_pinned, text="NO TONE PROFILE", text_color="#FFD700", 
                                        font=ctk.CTkFont(family="Arial", size=14, weight="bold"), 
                                        fg_color="#111111", corner_radius=6, height=36)
        self.lbl_profile.pack(fill=tk.X, pady=(0, 5))

        # --- ROW 4: Recipe Management ---
        self.recipe_frame = ctk.CTkFrame(self.top_pinned, fg_color="transparent")
        self.recipe_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_load_recipe = ctk.CTkButton(self.recipe_frame, text="Load Recipe", command=self.load_recipe_dialog,
                                             fg_color="#2A2A2A", hover_color="#444444", text_color="#E0E0E0",
                                             font=ctk.CTkFont(family="Arial", size=12, weight="bold"))
        self.btn_load_recipe.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ToolTip(self.btn_load_recipe, "Load a previously saved Emulsifier settings configuration.")

        self.btn_save_recipe = ctk.CTkButton(self.recipe_frame, text="Save Recipe", command=self.save_recipe_dialog,
                                             fg_color="#2A2A2A", hover_color="#444444", text_color="#E0E0E0",
                                             font=ctk.CTkFont(family="Arial", size=12, weight="bold"))
        
        self.btn_save_recipe.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))
        ToolTip(self.btn_save_recipe, "Save current settings as recipe.")

        self.hist_canvas_h = int(65 * ctk.ScalingTracker.get_widget_scaling(self))
        self.hist_canvas = tk.Canvas(self.top_pinned, height=self.hist_canvas_h, bg="#111111", highlightthickness=1, highlightbackground="#333333")
        self.hist_canvas.pack(fill=tk.X, pady=(0, 10))
        ToolTip(self.hist_canvas, "Global Luminance Scope\nGrey: Original Image | Gold: Dehanced Image")

        self.master_mix_frame = ctk.CTkFrame(self.top_pinned, fg_color="#2A2A2A", corner_radius=8)
        self.master_mix_frame.pack(fill=tk.X, pady=(0, 15), ipadx=5, ipady=5)
        
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
        
        # Arch Fix: Export UI triggers background thread
        self.btn_export = ctk.CTkButton(self.bottom_pinned, text="Export Full-Res Render", command=self.export_image, 
                      fg_color="#5C5C5C", hover_color="#8B7300", text_color="#FFFFFF", height=44, 
                      font=ctk.CTkFont(family="Arial", size=14, weight="bold"))
        self.btn_export.pack(fill=tk.X)

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

        self.pane_optics = CollapsiblePane(self.scroll_frame, "Lens Optics", app=self)
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

        self.pane_flare = CollapsiblePane(self.scroll_frame, "VFX Lens Flare", app=self)
        self.pane_flare.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_flare)

        def toggle_flare_placement():
            if not self.film_profile:
                self.show_no_profile_warning()
                return
            self.is_placing_flare = True
            self.canvas_left.config(cursor="crosshair")
            self.canvas_right.config(cursor="crosshair")
            self.show_osd_message("Click on Image to place Light Source")

        self.btn_place_flare = ctk.CTkButton(self.pane_flare.content_frame, text="Set Light Source (Click)", 
                                             command=toggle_flare_placement, fg_color="#333333", hover_color="#8B7300")
        self.btn_place_flare.pack(fill=tk.X, padx=10, pady=(10, 5))
        self.lbl_flare_amt = create_slider_row(self.pane_flare.content_frame, self.pane_flare, "Flare Intensity", "GPU-accelerated lens flare.", self.flare_amt_var, 0, 100)

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

        self.pane_wash = CollapsiblePane(self.scroll_frame, "Color Compensating (CC) Filters", app=self)
        self.pane_wash.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_wash)

        self.wash_swatch_frame = tk.Frame(self.pane_wash.content_frame, bg="#222222")
        self.wash_swatch_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        def update_wash_halos(active_id, custom_hex=None):
            for btn_id, btn in self.wash_buttons.items():
                if btn_id == active_id:
                    btn.configure(border_color="#E0E0E0") 
                    if btn_id == "custom" and custom_hex:
                        btn.configure(fg_color=custom_hex, hover_color=custom_hex)
                else:
                    btn.configure(border_color="#222222")
        
        self.update_wash_halos = update_wash_halos

        def set_wash_color(hex_color, btn_id):
            if not self.film_profile: return self.show_no_profile_warning()
            self.wash_color_var.set(hex_color)
            self.update_wash_halos(btn_id, custom_hex=hex_color if btn_id == "custom" else None)
            self.trigger_render()
            self.save_state()

        swatches = [
            ("cto", "#FF8B14", "CTO (Daylight to Tungsten)"),
            ("ctb", "#A4C6FF", "CTB (Tungsten to Daylight)"),
            ("golden", "#FFD1A3", "Golden Hour"),
            ("night", "#2B3A67", "Cinematic Night"),
            ("cyber", "#44FFAA", "Fluorescent / Cyberpunk"),
            ("sepia", "#DDAAA4", "Vintage Sepia")
        ]

        self.swatch_wrapper = tk.Frame(self.wash_swatch_frame, bg="#222222")
        self.swatch_wrapper.pack(anchor=tk.CENTER)

        for s_id, color, tooltip in swatches:
            btn = ctk.CTkButton(self.swatch_wrapper, text="", width=26, height=26, corner_radius=13,
                                fg_color=color, hover_color=color, border_width=2, border_color="#222222",
                                command=lambda c=color, i=s_id: set_wash_color(c, i))
            btn.pack(side=tk.LEFT, padx=4)
            ToolTip(btn, tooltip)
            self.wash_buttons[s_id] = btn

        def pick_custom_color():
            if not self.film_profile: return self.show_no_profile_warning()
            current = self.wash_color_var.get()
            if current == "none": current = "#FFFFFF" 
            color_code = colorchooser.askcolor(title="Choose CC Filter Color", color=current)[1]
            if color_code: set_wash_color(color_code, "custom")

        grad_pil = self._generate_gradient_icon(size=22)
        self.icon_custom_color = ctk.CTkImage(light_image=grad_pil, dark_image=grad_pil, size=(22, 22))

        self.btn_picker = ctk.CTkButton(
            self.swatch_wrapper, 
            text="", 
            image=self.icon_custom_color,
            width=26, 
            height=26, 
            corner_radius=13, 
            border_spacing=0,        
            fg_color="transparent", 
            hover_color="#333333",
            border_width=2, 
            border_color="#222222",
            command=pick_custom_color
        )
        
        original_configure = self.btn_picker.configure
        def safe_configure(**kwargs):
            if "fg_color" in kwargs:
                kwargs.pop("fg_color") 
            original_configure(**kwargs) 
            
        self.btn_picker.configure = safe_configure
        
        self.btn_picker.pack(side=tk.LEFT, padx=(20, 4))
        ToolTip(self.btn_picker, "Custom Colored Filter")  

        self.update_wash_halos("none")

        self.lbl_wash_amt = create_slider_row(self.pane_wash.content_frame, self.pane_wash, "Filter Density", "Intensity of the CC Filter.", self.wash_amt_var, 0, 100)

        self.pane_levels = CollapsiblePane(self.scroll_frame, "Output Levels", app=self)
        self.pane_levels.pack(fill=tk.X, pady=2)
        self.panes.append(self.pane_levels)
        
        def trigger_auto_levels():
            if not self.film_profile:
                self.show_no_profile_warning()
                return
            self.save_state() 
            self.is_auto_levels = True
            self.trigger_render()

        self.btn_auto_levels = ctk.CTkButton(self.pane_levels.content_frame, text="Auto Levels", 
                                             fg_color="#333333", hover_color="#8B7300", height=28,
                                             command=trigger_auto_levels)
        self.btn_auto_levels.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        self.levels_widget = LevelsWidget(self.pane_levels.content_frame, self)
        self.levels_widget.pack(fill=tk.X, padx=10, pady=(5, 10))
        
        ToolTip(self.levels_widget.canvas, "Output Levels\nDrag triangles to adjust Black, Midtone (Gamma), and White points.\nRight-click to reset.")

        self.set_active_pane(self.pane_optics)
        self.update_labels()
        self.update_canvases_layout()

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
            'flare_amt': self.flare_amt_var.get(),
            'flare_u': self.flare_u_var.get(),
            'flare_v': self.flare_v_var.get(),
            'bp': self.bp_var.get(),
            'mid': self.mid_var.get(),
            'wp': self.wp_var.get(),
            'optics_on': self.pane_optics.switch_var.get(),
            'light_on': self.pane_light.switch_var.get(),
            'print_on': self.pane_print.switch_var.get(),
            'grain_on': self.pane_grain.switch_var.get(),
            'edge_on': self.pane_edge.switch_var.get(),
            'levels_on': self.pane_levels.switch_var.get(),
            'flare_on': self.pane_flare.switch_var.get(),
            'wash_amt': self.wash_amt_var.get(), 
            'wash_color': self.wash_color_var.get(),
            'wash_on': self.pane_wash.switch_var.get()
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
        
        prof = state.get('profile', "--- NONE ---")
        self.profile_var.set(prof)
        if prof != "Select Film Emulation..." and prof != "--- NONE ---":
            if prof in self.preset_mapping:
                self.load_profile_from_file(self.preset_mapping[prof]) 
            else:
                self.film_profile = None
                self.lbl_profile.configure(text="NO TONE PROFILE")
        else:
            self.film_profile = None
            self.curve_data = {}
            self.log_e_grid = []
            self.lbl_profile.configure(text="NO TONE PROFILE")

        self.str_var.set(state.get('str', self.str_var.get()))
        self.soft_var.set(state.get('soft', self.soft_var.get()))
        self.ca_var.set(state.get('ca', self.ca_var.get()))
        self.flat_var.set(state.get('flat', self.flat_var.get()))
        self.cross_var.set(state.get('cross', self.cross_var.get()))
        self.hal_var.set(state.get('hal', self.hal_var.get()))
        self.bloom_var.set(state.get('bloom', self.bloom_var.get()))
        self.cont_var.set(state.get('cont', self.cont_var.get()))
        self.subsat_var.set(state.get('subsat', self.subsat_var.get()))
        self.split_var.set(state.get('split', self.split_var.get()))
        self.grain_amt_var.set(state.get('grain_amt', self.grain_amt_var.get()))
        self.grain_size_var.set(state.get('grain_size', self.grain_size_var.get()))
        self.grain_chroma_var.set(state.get('grain_chroma', self.grain_chroma_var.get()))
        self.ff_amt_var.set(state.get('ff_amt', self.ff_amt_var.get()))
        self.ff_fall_var.set(state.get('ff_fall', self.ff_fall_var.get()))
        self.vig_amt_var.set(state.get('vig_amt', self.vig_amt_var.get()))
        self.vig_fall_var.set(state.get('vig_fall', self.vig_fall_var.get()))
        self.flare_amt_var.set(state.get('flare_amt', self.flare_amt_var.get()))
        self.flare_u_var.set(state.get('flare_u', self.flare_u_var.get()))
        self.flare_v_var.set(state.get('flare_v', self.flare_v_var.get()))

        self.pane_optics.switch_var.set(state.get('optics_on', True))
        self.pane_light.switch_var.set(state.get('light_on', True))
        self.pane_print.switch_var.set(state.get('print_on', True))
        self.pane_grain.switch_var.set(state.get('grain_on', True))
        self.pane_edge.switch_var.set(state.get('edge_on', True))
        self.pane_levels.switch_var.set(state.get('levels_on', True))
        self.pane_flare.switch_var.set(state.get('flare_on', True))

        self.wash_amt_var.set(state.get('wash_amt', self.wash_amt_var.get()))
        self.wash_color_var.set(state.get('wash_color', self.wash_color_var.get()))
        self.pane_wash.switch_var.set(state.get('wash_on', True))
        if hasattr(self, 'update_wash_halos'):
            hex_val = self.wash_color_var.get()
            if hex_val == "none":
                active_id = "none"
            else:
                preset_ids = {"#FF8B14":"cto", "#A4C6FF":"ctb", "#FFD1A3":"golden", "#2B3A67":"night", "#44FFAA":"cyber", "#DDAAA4":"sepia"}
                active_id = preset_ids.get(hex_val, "custom")
            self.update_wash_halos(active_id, custom_hex=hex_val)

        self.levels_widget.set_values_from_vars(
            state.get('bp', self.bp_var.get()), 
            state.get('mid', self.mid_var.get()), 
            state.get('wp', self.wp_var.get())
        )
        
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
        
        self.lbl_wash_amt.configure(text=f"Filter Density: {int(self.wash_amt_var.get())}%")

        if "Calculating" not in self.lbl_str.cget("text"):
            self.lbl_str.configure(text=f"Overall Physical Mix: {int(self.str_var.get())}%")
            
        self.lbl_ff_amt.configure(text=f"Field Flatness Softness: {int(self.ff_amt_var.get())}%")
        self.lbl_ff_fall.configure(text=f"Field Flatness Creep: {int(self.ff_fall_var.get())}%")
        self.lbl_vig_amt.configure(text=f"Vignette Intensity: {int(self.vig_amt_var.get())}%")
        self.lbl_vig_fall.configure(text=f"Vignette Creep: {int(self.vig_fall_var.get())}%")
        self.lbl_flare_amt.configure(text=f"Flare Intensity: {int(self.flare_amt_var.get())}%")

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

        if getattr(self, 'show_original_toggle', False):
            right_display = left_display.copy()

        if self.view_mode == "side_by_side":
            self.tk_img_left = ImageTk.PhotoImage(left_display)
            self.tk_img_right = ImageTk.PhotoImage(right_display)
            self.canvas_left.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_left, tags="render_img")
            self.canvas_right.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_right, tags="render_img")
        elif self.view_mode == "single":
            self.tk_img_left = ImageTk.PhotoImage(right_display)
            self.canvas_left.create_image(draw_x, draw_y, anchor=tk.CENTER, image=self.tk_img_left, tags="render_img")
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
        
        if self.view_mode == "single":
            if not self.film_profile or getattr(self, 'show_original_toggle', False):
                lbl_text = "ORIGINAL"
            else:
                lbl_text = "DEHANCED"
                
            mid_x = cw // 2
            half_w = int(50 * sf) 
            
            self.canvas_left.create_rectangle(mid_x - half_w, int(15*sf), mid_x + half_w, int(40*sf), fill="#111111", outline="")
            self.canvas_left.create_text(mid_x, int(27*sf), text=lbl_text, fill="white", font=("Arial", 10, "bold"))
            
        else:
            self.canvas_left.create_rectangle(int(15*sf), int(15*sf), int(95*sf), int(40*sf), fill="#222222", outline="")
            self.canvas_left.create_text(int(55*sf), int(27*sf), text="ORIGINAL", fill="white", font=("Arial", 10, "bold"))
            
            if self.view_mode == "side_by_side":
                self.canvas_right.create_rectangle(int(15*sf), int(15*sf), int(105*sf), int(40*sf), fill="#222222", outline="")
                self.canvas_right.create_text(int(60*sf), int(27*sf), text="DEHANCED", fill="white", font=("Arial", 10, "bold"))
            else: 
                self.canvas_left.create_rectangle(cw-int(105*sf), int(15*sf), cw-int(15*sf), int(40*sf), fill="#222222", outline="")
                self.canvas_left.create_text(cw-int(60*sf), int(27*sf), text="DEHANCED", fill="white", font=("Arial", 10, "bold"))

        # --- HIDE ICONS IF FULLSCREEN ---
        if not getattr(self, 'is_fullscreen', False):
            y_off = ch - int(40 * sf)
            z_text = f"{int(self.zoom_level * 100)}%" if self.is_zoomed else "FIT"
            z_color = "#FFD700" if self.is_zoomed else "#AAAAAA"
            
            c_zoom = "#555555" if getattr(self, 'hovered_btn', None) == "zoom" else "#222222"
            c_single = "#555555" if getattr(self, 'hovered_btn', None) == "single" else ("#444444" if self.view_mode == "single" else "#222222")
            c_sbs = "#555555" if getattr(self, 'hovered_btn', None) == "sbs" else ("#444444" if self.view_mode == "side_by_side" else "#222222")
            c_wipe = "#555555" if getattr(self, 'hovered_btn', None) == "wipe" else ("#444444" if self.view_mode == "wipe" else "#222222")
            
            self.canvas_left.create_rectangle(int(15*sf), y_off, int(70*sf), y_off + int(25*sf), fill=c_zoom, outline="")
            self.canvas_left.create_text(int(42*sf), y_off + int(12*sf), text=z_text, fill=z_color, font=("Arial", 10, "bold"))
            
            self.canvas_left.create_rectangle(int(85*sf), y_off, int(120*sf), y_off + int(25*sf), fill=c_single, outline="")
            self.canvas_left.create_text(int(102*sf), y_off + int(12*sf), text="[   ]", fill="#FFFFFF", font=("Arial", 10, "bold"))
            
            self.canvas_left.create_rectangle(int(130*sf), y_off, int(165*sf), y_off + int(25*sf), fill=c_sbs, outline="")
            self.canvas_left.create_text(int(147*sf), y_off + int(12*sf), text="[ | ]", fill="#FFFFFF", font=("Arial", 10, "bold"))
            
            self.canvas_left.create_rectangle(int(175*sf), y_off, int(230*sf), y_off + int(25*sf), fill=c_wipe, outline="")
            self.canvas_left.create_text(int(202*sf), y_off + int(12*sf), text="WIPE", fill="#FFFFFF", font=("Arial", 10, "bold"))
            
            if self.view_mode == "side_by_side" and self.is_zoomed:
                self.canvas_right.create_rectangle(int(15*sf), y_off, int(70*sf), y_off + int(25*sf), fill=c_zoom, outline="")
                self.canvas_right.create_text(int(42*sf), y_off + int(12*sf), text=z_text, fill=z_color, font=("Arial", 10, "bold"))

    def on_canvas_hover(self, event):
        if getattr(self, 'is_fullscreen', False):
            event.widget.config(cursor="arrow")
            return
            
        if getattr(self, 'is_placing_flare', False):
            event.widget.config(cursor="crosshair")
            return
        if self.space_pressed: return
        
        cw = event.widget.winfo_width()
        ch = event.widget.winfo_height()
        sf = ctk.ScalingTracker.get_widget_scaling(self)
        y_off = ch - int(40 * sf)
        
        btn_w, btn_h = int(30 * sf), int(25 * sf)
        
        new_hovered_btn = None
        if event.widget == self.canvas_left:
            if int(15*sf) <= event.x <= int(70*sf) and y_off <= event.y <= y_off + btn_h:
                new_hovered_btn = "zoom"
            elif int(85*sf) <= event.x <= int(120*sf) and y_off <= event.y <= y_off + btn_h:
                new_hovered_btn = "single"
            elif int(130*sf) <= event.x <= int(165*sf) and y_off <= event.y <= y_off + btn_h:
                new_hovered_btn = "sbs"
            elif int(175*sf) <= event.x <= int(230*sf) and y_off <= event.y <= y_off + btn_h:
                new_hovered_btn = "wipe"

        if new_hovered_btn != getattr(self, 'hovered_btn', None):
            self.hovered_btn = new_hovered_btn
            self.update_canvases()
            
        if self.hovered_btn:
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

    def on_canvas_leave(self, event):
        if getattr(self, 'hovered_btn', None) is not None:
            self.hovered_btn = None
            self.update_canvases()

    def set_view_mode(self, target_mode):
        if self.view_mode == target_mode:
            return
            
        self.view_mode = target_mode
        self.wipe_dragging = False
        
        if target_mode != "single":
            self.show_original_toggle = False
            
        self.update_canvases_layout()

    def update_canvases_layout(self):
        if self.view_mode in ["wipe", "single"]:
            self.canvas_right.pack_forget()
            self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        else:
            self.canvas_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 5), pady=10)
            self.canvas_right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)
        self.update_canvases()

    def on_canvas_press(self, event):
        if getattr(self, 'is_fullscreen', False): return
        if self.working_img_pil is None: return
        
        cw = event.widget.winfo_width()
        ch = event.widget.winfo_height()
        sf = ctk.ScalingTracker.get_widget_scaling(self)
        
        if getattr(self, 'is_placing_flare', False):
            img_w, img_h = self.working_img_pil.size
            master_w, master_h = self.original_image.size
            
            if not self.is_zoomed:
                scale = min(cw / img_w, ch / img_h)
                disp_w, disp_h = int(img_w * scale), int(img_h * scale)
                off_x, off_y = (cw - disp_w) // 2, (ch - disp_h) // 2
                
                click_x, click_y = event.x - off_x, event.y - off_y
                if 0 <= click_x <= disp_w and 0 <= click_y <= disp_h:
                    self.flare_u_var.set(click_x / disp_w)
                    self.flare_v_var.set(click_y / disp_h)
            else:
                zx, zy = self.zoom_center_master
                dx = (event.x - cw / 2) / self.zoom_level
                dy = (event.y - ch / 2) / self.zoom_level
                
                self.flare_u_var.set((zx + dx) / master_w)
                self.flare_v_var.set((zy + dy) / master_h)

            if self.flare_amt_var.get() == 0:
                self.flare_amt_var.set(20)
                self.update_labels() 

            self.is_placing_flare = False
            cur = self.cursor_zoom_out if self.is_zoomed else self.cursor_zoom_in
            self.canvas_left.config(cursor=cur)
            self.canvas_right.config(cursor=cur)
            self.trigger_render()
            self.save_state()
            return

        y_off = ch - int(40 * sf)
        btn_w, btn_h = int(30 * sf), int(25 * sf)
        
        if event.widget == self.canvas_left:
            if int(15*sf) <= event.x <= int(70*sf) and y_off <= event.y <= y_off + btn_h:
                if self.is_zoomed:
                    self.is_zoomed = False
                    self.zoom_level = 1.0
                    event.widget.config(cursor=self.cursor_zoom_in)
                else:
                    self.is_zoomed = True
                    self.zoom_level = 1.0
                    self.zoom_center_master = (self.original_image.size[0]/2, self.original_image.size[1]/2)
                    event.widget.config(cursor=self.cursor_zoom_out)
                self.trigger_render()
                return
            elif int(85*sf) <= event.x <= int(120*sf) and y_off <= event.y <= y_off + btn_h:
                self.set_view_mode("single")
                return
            elif int(130*sf) <= event.x <= int(165*sf) and y_off <= event.y <= y_off + btn_h:
                self.set_view_mode("side_by_side")
                return
            elif int(175*sf) <= event.x <= int(230*sf) and y_off <= event.y <= y_off + btn_h:
                self.set_view_mode("wipe")
                return

        elif event.widget == self.canvas_right:
            if self.view_mode == "side_by_side" and self.is_zoomed:
                if int(15*sf) <= event.x <= int(70*sf) and y_off <= event.y <= y_off + btn_h:
                    self.is_zoomed = False
                    self.zoom_level = 1.0
                    event.widget.config(cursor=self.cursor_zoom_in)
                    self.trigger_render()
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
        if getattr(self, 'is_fullscreen', False): return
        
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
        if getattr(self, 'is_fullscreen', False): return
        
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
        if getattr(self, 'is_fullscreen', False): return
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
            
            self._render_cache.clear() 
            
            self.tk_img_left = None
            self.tk_img_right = None
            
            gc.collect() 
            
            self.save_state()
            
            try:
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                mode_str = "GPU" if cv2.ocl.useOpenCL() else "CPU"
                self.title(f"{self.base_title} - Image loaded. {w} x {h} px. {file_size_mb:.1f}Mb. {mode_str} Mode.")
            except Exception:
                self.title(self.base_title)
            
            self.trigger_render()

            # --- ARCH FIX: Force OS focus back to the main window ---
            self.lift()
            self.focus_force()
            
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

        raw_hex = self.wash_color_var.get()
        if raw_hex == "none":
            wash_r, wash_g, wash_b = 0.5, 0.5, 0.5 
        else:
            hex_color = raw_hex.lstrip('#')
            wash_r = int(hex_color[0:2], 16) / 255.0
            wash_g = int(hex_color[2:4], 16) / 255.0
            wash_b = int(hex_color[4:6], 16) / 255.0
        
        return {
            'img_array': self.current_unprocessed_array, 
            'film_profile': self.film_profile,
            'log_e_grid': self.log_e_grid,
            'curve_data': self.curve_data,
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
            'wash_r': wash_r, 'wash_g': wash_g, 'wash_b': wash_b, 
            'wash_amt': self.wash_amt_var.get(),
            'wash_on': self.pane_wash.switch_var.get(), 
            'flare_amt': self.flare_amt_var.get(),
            'flare_u': self.flare_u_var.get(),
            'flare_v': self.flare_v_var.get(),
            'optics_on': self.pane_optics.switch_var.get(),
            'light_on': self.pane_light.switch_var.get(),
            'print_on': self.pane_print.switch_var.get(),
            'grain_on': self.pane_grain.switch_var.get(),
            'edge_on': self.pane_edge.switch_var.get(),
            'levels_on': self.pane_levels.switch_var.get(),
            'flare_on': self.pane_flare.switch_var.get(),
            'virtual_width': self._cached_virtual_width,
            'true_master_width': self._cached_true_master_width,
            'master_width': self._cached_master_width,
            'master_height': self._cached_master_height,
            'offset_x': self._cached_offset_x,
            'offset_y': self._cached_offset_y,
            'is_auto_mixing': getattr(self, 'is_auto_mixing', False),
            'is_auto_levels': getattr(self, 'is_auto_levels', False)
        }

    def trigger_render(self, event=None):
        if self.preview_array is None: 
            return
            
        self.update_labels()
        self.lbl_profile.configure(text="RENDERING...")

        params = self._prepare_render_params()
        if not params: return

        # ARCH FIX: The 35ms Micro-Debounce.
        # Cancels the pending render if the user moves the slider again before 35ms.
        if self._render_after_id is not None:
            self.after_cancel(self._render_after_id)
        
        self._render_after_id = self.after(35, self._queue_render, params)
        
    def _queue_render(self, params):
        while not self.render_queue.empty():
            try:
                self.render_queue.get_nowait()
            except queue.Empty:
                break
                
        self.render_queue.put(params)

    def _render_worker(self):
        while True:
            params = self.render_queue.get() 
            try:
                rendered_array, pre_levels_array, optimal_str, auto_bp, auto_wp = engine.process_engine(self._render_cache, **params)
                
                def calc_hist(arr):
                    if arr is None: return None
                    img_uint8 = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
                    gray = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2GRAY)
                    return cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()

                img_id = id(params['img_array'])
                if self._render_cache.get('orig_hist_hash') != img_id:
                    self._render_cache['orig_hist'] = calc_hist(params['img_array'])
                    self._render_cache['orig_hist_hash'] = img_id
                    
                orig_hist = self._render_cache['orig_hist']
                proc_hist = calc_hist(rendered_array)
                pre_levels_hist = calc_hist(pre_levels_array)
                
                processed_pil = Image.fromarray((rendered_array * 255).astype(np.uint8))
                
                while not self.result_queue.empty():
                    try: self.result_queue.get_nowait()
                    except queue.Empty: break
                    
                self.result_queue.put({
                    'pil': processed_pil,
                    'orig_hist': orig_hist,
                    'proc_hist': proc_hist,
                    'pre_levels_hist': pre_levels_hist,
                    'optimal_str': optimal_str,
                    'auto_bp': auto_bp,
                    'auto_wp': auto_wp
                })

            except Exception as e:
                print(f"Render engine error: {e}")
                self.result_queue.put({'error': str(e)})

    def _apply_render_result(self, final_pil, orig_hist, proc_hist, pre_levels_hist, optimal_str,auto_bp, auto_wp):
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
        
        if auto_bp is not None and auto_wp is not None:
            self.is_auto_levels = False
            self.bp_var.set(auto_bp)
            self.wp_var.set(auto_wp)
            self.levels_widget.set_values_from_vars(auto_bp, self.mid_var.get(), auto_wp)
            self.save_state()
            self.show_osd_message("Auto Levels Applied")

        self.update_canvases()
        self.update_histogram(orig_hist, proc_hist, pre_levels_hist)

    # --- ARCH FIX: ASYNCHRONOUS EXPORTING ---
    def export_image(self):
        if self.original_image is None or not self.film_profile:
            messagebox.showwarning("Warning", "Load an image and profile first.")
            return
            
        save_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("TIFF Image", "*.tif"), ("JPEG Image", "*.jpg")]
        )
        if not save_path: return
        
        self.lbl_profile.configure(text="EXPORTING FULL-RES...")
        self.btn_export.configure(state="disabled", text="Exporting... Please Wait")
        self.update_idletasks() 
        
        master_w, master_h = self.original_image.size
        full_array = np.array(self.original_image, dtype=np.float32) / 255.0

        raw_hex = self.wash_color_var.get()
        if raw_hex == "none":
            wash_r, wash_g, wash_b = 0.5, 0.5, 0.5 
        else:
            hex_color = raw_hex.lstrip('#')
            wash_r = int(hex_color[0:2], 16) / 255.0
            wash_g = int(hex_color[2:4], 16) / 255.0
            wash_b = int(hex_color[4:6], 16) / 255.0
            
        # Extract UI state completely on the main thread
        export_params = {
            'img_array': full_array,
            'film_profile': self.film_profile,
            'log_e_grid': self.log_e_grid,
            'curve_data': self.curve_data,
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
            'flare_amt': self.flare_amt_var.get(),
            'flare_u': self.flare_u_var.get(),
            'flare_v': self.flare_v_var.get(),
            'wash_r': wash_r, 'wash_g': wash_g, 'wash_b': wash_b,                
            'wash_amt': self.wash_amt_var.get(),                           
            'wash_on': self.pane_wash.switch_var.get(),                    
            'optics_on': self.pane_optics.switch_var.get(),
            'light_on': self.pane_light.switch_var.get(),
            'print_on': self.pane_print.switch_var.get(),
            'grain_on': self.pane_grain.switch_var.get(),
            'edge_on': self.pane_edge.switch_var.get(),
            'levels_on': self.pane_levels.switch_var.get(),
            'flare_on': self.pane_flare.switch_var.get(),
            'virtual_width': master_w,
            'true_master_width': master_w,
            'master_width': master_w,
            'master_height': master_h,
            'offset_x': 0,
            'offset_y': 0,
            'is_auto_mixing': False
        }

        # Fire off the background thread
        threading.Thread(target=self._export_worker, args=(save_path, export_params), daemon=True).start()

    def _export_worker(self, save_path, params):
        try:
            # Empty cache used so we don't pollute our live preview RAM
            rendered_array, _,_,_,_ = engine.process_engine(cache={}, **params)
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
                
            success = True
            
        except Exception as e:
            print(f"Export error: {e}")
            success = False
        finally:
            # Aggressively delete the massive memory blocks from this thread
            del params['img_array']
            del params
            if 'rendered_array' in locals():
                del rendered_array
            if 'rendered_img' in locals():
                del rendered_img
            gc.collect()
            
            self.after(0, self._export_complete, success)

    def _export_complete(self, success):
        self.btn_export.configure(state="normal", text="Export Full-Res Render")
        if success:
            name = f"{self.film_profile['manufacturer']} {self.film_profile['film_name']}".upper()
            self.lbl_profile.configure(text=f"SAVED: {name}")
            self.show_osd_message("Export Complete")
        else:
            self.lbl_profile.configure(text="EXPORT FAILED", text_color="#FF4444")
            self.show_osd_message("Export Failed (See Console)")

if __name__ == "__main__":
    app = FilmRendererApp()
    app.mainloop()