import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
import numpy as np
import json
import csv
import os
import cv2
import threading
import queue
import gc
import platform
import engine

class GalleryLightbox(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Emulsion Gallery")

        self.parsed_profiles_cache = {} #save I/O operations
        
        self.geometry("1000x950")
        self.resizable(False, False)
        
        self.configure(fg_color="#181818")
        self.transient(parent)
        self.grab_set() 
        
        self.previews = {} 
        self.thumb_widgets = {} 
        self.selected_preset = None
        self.current_tk_preview = None
        self.pill_tk = None 
        self.completed_full_presets = set()

        # --- ARCH FIX: Thread Management & Priority Queues ---
        self._is_alive = True 
        self.priority_queue = queue.Queue()
        self.ui_queue = queue.Queue()
        self._ui_poll_id = None

        
        self.ordered_presets = list(self.parent.preset_mapping.keys())
        if "--- NONE ---" in self.ordered_presets:
            self.ordered_presets.remove("--- NONE ---")
  
        self.setup_ui()
        self._poll_ui_queue()
        self.start_processing()
        
        self.bind("<MouseWheel>", self.on_mouse_wheel)
        self.bind("<Button-4>", self.on_mouse_wheel)
        self.bind("<Button-5>", self.on_mouse_wheel)

        self.focus_set() 
        self.bind("<Escape>", lambda e: self.destroy())
            
        self.bind("<Left>", self.nav_left)
        self.bind("<Right>", self.nav_right)
    
    def destroy(self):
        # 1. KILL SIGNAL: Instantly stops the background spooler from starting new renders
        self._is_alive = False
        
        if hasattr(self, '_preview_timer') and self._preview_timer is not None:
            self.after_cancel(self._preview_timer)

        if getattr(self, '_ui_poll_id', None) is not None:
            try:
                self.after_cancel(self._ui_poll_id)
            except Exception:
                pass
            self._ui_poll_id = None
            
        # 2. THE JANITOR: Aggressively scrape all arrays and Tkinter C-bindings
        if hasattr(self, 'previews'):
            for key in list(self.previews.keys()):
                preview = self.previews[key]
                if 'tk_thumb' in preview: del preview['tk_thumb']
                if 'thumb_pil' in preview: del preview['thumb_pil']
                if 'full_pil' in preview: del preview['full_pil']
            self.previews.clear()
            
        self.current_tk_preview = None
        self.pill_tk = None
        
        try:
            self.canvas_preview.delete("all")
        except:
            pass
        
        # 3. Force Python to release the memory back to the OS immediately
        gc.collect()
        
        super().destroy()

    def setup_ui(self):
        self.preview_frame = tk.Frame(self, bg="#111111")
        self.preview_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas_preview = tk.Canvas(self.preview_frame, bg="#151515", highlightthickness=0)
        self.canvas_preview.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        self.canvas_preview.bind("<Configure>", self.on_preview_resize)
        
        self.loading_frame = ctk.CTkFrame(self.preview_frame, fg_color="#151515", corner_radius=10)
        self.loading_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        self.lbl_loading = ctk.CTkLabel(self.loading_frame, text="Developing Filmstrip...", font=("Arial", 16, "bold"), text_color="#FFD700")
        self.lbl_loading.pack(padx=20, pady=(20, 10))
        
        self.progress_bar = ctk.CTkProgressBar(self.loading_frame, width=250, fg_color="#333333", progress_color="#FFD700")
        self.progress_bar.set(0)
        self.progress_bar.pack(padx=20, pady=(0, 20))

        self.bottom_container = tk.Frame(self, bg="#181818")
        self.bottom_container.pack(side=tk.BOTTOM, fill=tk.X)

        tk.Frame(self.bottom_container, bg="#333333", height=1).pack(side=tk.TOP, fill=tk.X)

        self.control_frame = tk.Frame(self.bottom_container, bg="#181818")
        self.control_frame.pack(side=tk.TOP, fill=tk.X, pady=(15, 10), padx=20)
        
        self.btn_wrapper = tk.Frame(self.control_frame, bg="#181818")
        self.btn_wrapper.pack(anchor=tk.CENTER)
        
        self.btn_apply = ctk.CTkButton(self.btn_wrapper, text="Apply Selected", 
                                       fg_color="#8B7300", hover_color="#B8860B", text_color="#000000", 
                                       font=("Arial", 14, "bold"), command=self.apply_and_close, state="disabled", height=36)
        self.btn_apply.pack(side=tk.LEFT, padx=10)
        
        self.btn_cancel = ctk.CTkButton(self.btn_wrapper, text="Cancel", 
                                        fg_color="#333333", hover_color="#4A4A4A", text_color="#FFFFFF", 
                                        font=("Arial", 14, "bold"), command=self.destroy, height=36, width=100)
        self.btn_cancel.pack(side=tk.LEFT, padx=10)

        self.filmstrip_wrapper = tk.Frame(self.bottom_container, bg="#181818")
        self.filmstrip_wrapper.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 15), padx=20)

        self.btn_left = ctk.CTkButton(self.filmstrip_wrapper, text="◀", width=30, height=140, fg_color="#2A2A2A", hover_color="#444444", command=self.scroll_left, font=("Arial", 20, "bold"), corner_radius=4)
        self.btn_left.pack(side=tk.LEFT, fill=tk.NONE, padx=(10, 15), pady=(0, 15))

        self.filmstrip_frame = ctk.CTkScrollableFrame(self.filmstrip_wrapper, orientation="horizontal", fg_color="#1E1E1E", height=210, corner_radius=0)
        self.filmstrip_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_right = ctk.CTkButton(self.filmstrip_wrapper, text="▶", width=30, height=140, fg_color="#2A2A2A", hover_color="#444444", command=self.scroll_right, font=("Arial", 20, "bold"), corner_radius=4)
        self.btn_right.pack(side=tk.RIGHT, fill=tk.NONE, padx=(15, 10), pady=(0, 15))

    def on_mouse_wheel(self, event):
        try:
            scroll_speed = 5 
            if hasattr(event, 'delta') and event.delta != 0:
                direction = -scroll_speed if event.delta > 0 else scroll_speed
                self.filmstrip_frame._parent_canvas.xview_scroll(direction, "units")
            elif event.num == 4:
                self.filmstrip_frame._parent_canvas.xview_scroll(-scroll_speed, "units")
            elif event.num == 5:
                self.filmstrip_frame._parent_canvas.xview_scroll(scroll_speed, "units")
        except Exception:
            pass

    def scroll_left(self):
        try: self.filmstrip_frame._parent_canvas.xview_scroll(-8, "units")
        except: pass

    def scroll_right(self):
        try: self.filmstrip_frame._parent_canvas.xview_scroll(8, "units")
        except: pass

    def nav_left(self, event=None):
        if not self.selected_preset or not self.ordered_presets: return
        idx = self.ordered_presets.index(self.selected_preset)
        if idx > 0:
            new_preset = self.ordered_presets[idx - 1]
            self.select_preset(new_preset)         
            self._auto_scroll_filmstrip(idx - 1)   

    def nav_right(self, event=None):
        if not self.selected_preset or not self.ordered_presets: return
        idx = self.ordered_presets.index(self.selected_preset)
        if idx < len(self.ordered_presets) - 1:
            new_preset = self.ordered_presets[idx + 1]
            self.select_preset(new_preset)
            self._auto_scroll_filmstrip(idx + 1)

    def _auto_scroll_filmstrip(self, idx):
        if len(self.ordered_presets) <= 1: return
        try:
            canvas = self.filmstrip_frame._parent_canvas
            cw = canvas.winfo_width()
            bbox = canvas.bbox("all")
            if not bbox: return
            tw = bbox[2] - bbox[0]
            
            if tw <= cw: return 
            
            item_w = tw / len(self.ordered_presets)
            item_center_x = (idx + 0.5) * item_w
            target_view_x = item_center_x - (cw / 2.0)
            fraction = target_view_x / tw
            fraction = max(0.0, fraction)
            
            canvas.xview_moveto(fraction)
        except Exception:
            pass

    def start_processing(self):
        threading.Thread(target=self._initial_load_worker, daemon=True).start()

    def _post_ui(self, event_type, *payload):
        if self._is_alive:
            self.ui_queue.put((event_type, payload))

    def _poll_ui_queue(self):
        if not self._is_alive:
            return

        try:
            while True:
                event_type, payload = self.ui_queue.get_nowait()
                if event_type == "close":
                    self.destroy()
                    return
                elif event_type == "progress":
                    self.progress_bar.set(payload[0])
                elif event_type == "thumb":
                    name, thumb_pil = payload
                    self.previews[name] = {'thumb_pil': thumb_pil}
                    self._add_thumbnail_to_ui(name, thumb_pil)
                elif event_type == "full":
                    name, full_pil = payload
                    if name in self.previews:
                        self.previews[name]['full_pil'] = full_pil
                    else:
                        self.previews[name] = {'full_pil': full_pil}

                    if self.selected_preset == name:
                        self.update_large_preview()
                elif event_type == "finish":
                    self._finish_loading()
        except queue.Empty:
            pass

        self._ui_poll_id = self.after(16, self._poll_ui_queue)


    def _get_smart_crop_box(self, img_array, crop_ratio=0.5):
        h, w = img_array.shape[:2]
        crop_h, crop_w = int(h * crop_ratio), int(w * crop_ratio)
        best_center = None

        try:
            img_uint8 = (np.clip(img_array, 0, 1) * 255).astype(np.uint8)
            gray = cv2.cvtColor(img_uint8, cv2.COLOR_RGB2GRAY)
            
            frontal_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            profile_path = cv2.data.haarcascades + 'haarcascade_profileface.xml'
            
            frontal_cascade = cv2.CascadeClassifier(frontal_path)
            profile_cascade = cv2.CascadeClassifier(profile_path)
            
            faces = frontal_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces) == 0:
                faces = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
            if len(faces) == 0:
                gray_flipped = cv2.flip(gray, 1)
                flipped_faces = profile_cascade.detectMultiScale(gray_flipped, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
                if len(flipped_faces) > 0:
                    faces = []
                    for (fx, fy, fw, fh) in flipped_faces:
                        original_fx = w - (fx + fw) 
                        faces.append((original_fx, fy, fw, fh))
            
            if len(faces) > 0:
                faces = sorted(faces, key=lambda x: x[2] * x[3], reverse=True)
                fx, fy, fw, fh = faces[0]
                best_center = (fx + fw // 2, fy + fh // 2)
                
        except Exception:
            pass

        if best_center is None:
            luma = np.dot(img_array[..., :3], [0.299, 0.587, 0.114])
            grid_y, grid_x = 3, 3
            step_y, step_x = h // grid_y, w // grid_x
            max_var = -1
            best_center = (w // 2, h // 2)

            for i in range(grid_y):
                for j in range(grid_x):
                    y_start, y_end = i * step_y, (i + 1) * step_y
                    x_start, x_end = j * step_x, (j + 1) * step_x
                    cell = luma[y_start:y_end, x_start:x_end]
                    var = np.var(cell) 
                    if var > max_var:
                        max_var = var
                        best_center = (x_start + step_x // 2, y_start + step_y // 2)

        left = best_center[0] - crop_w // 2
        top = best_center[1] - crop_h // 2
        left = max(0, min(left, w - crop_w))
        top = max(0, min(top, h - crop_h))

        return left, top, crop_w, crop_h

    # --- ARCH FIX: DRY Helper for generating an image through the engine ---
    def _run_engine_for_preset(self, preset_name, input_array, is_thumb=False):
        if not self._is_alive: return None
        
        state = self.parent.get_current_state()
        h, w = input_array.shape[:2]
        
        try:
            if preset_name in self.parsed_profiles_cache:
                film_profile, log_e_grid, curve_data = self.parsed_profiles_cache[preset_name]
            else:
                filepath = self.parent.preset_mapping[preset_name]
                with open(filepath, 'r') as f:
                    film_profile = json.load(f)
                
                csv_path = film_profile['data_files']['characteristic_curve']
                csv_full_path = os.path.join(os.path.dirname(filepath), csv_path)
                
                curve_data = {'r': [], 'g': [], 'b': []}
                log_e_grid = []
                with open(csv_full_path, 'r') as f:
                    reader = csv.reader(f)
                    next(reader) 
                    for row in reader:
                        log_e_grid.append(float(row[0]))
                        curve_data['r'].append(float(row[1]))
                        curve_data['g'].append(float(row[2]))
                        curve_data['b'].append(float(row[3]))
                        
                log_e_grid = np.array(log_e_grid)
                for ch in ['r', 'g', 'b']:
                    curve_data[ch] = np.array(curve_data[ch])
                    
                self.parsed_profiles_cache[preset_name] = (film_profile, log_e_grid, curve_data)
                
        except Exception as e:
            print(f"Skipping {preset_name} due to load error: {e}")
            return None

        main_app = getattr(self, 'master', getattr(self, 'parent', getattr(self, 'main_app', None)))
        
        raw_hex = main_app.wash_color_var.get()
        if raw_hex == "none":
            wash_r, wash_g, wash_b = 0.5, 0.5, 0.5
        else:
            hex_color = raw_hex.lstrip('#')
            wash_r = int(hex_color[0:2], 16) / 255.0
            wash_g = int(hex_color[2:4], 16) / 255.0
            wash_b = int(hex_color[4:6], 16) / 255.0

        rendered_array, _, _, _, _, = engine.process_engine(
            cache={}, 
            img_array=input_array,
            film_profile=film_profile,
            log_e_grid=log_e_grid,
            curve_data=curve_data,
            soft_amt=0, ca_amt=0, ff_amt=0, ff_fall=0, vig_amt=0, vig_fall=0,
            flatten_pct=state.get('flat', 19),
            cross_pct=state.get('cross', 15),
            hal_pct=state.get('hal', 15),
            bloom_pct=state.get('bloom', 7.5),
            contrast_pct=state.get('cont', 40),
            subsat_pct=state.get('subsat', 30),
            split_pct=state.get('split', 15),
            grain_amt=state.get('grain_amt', 30), 
            grain_size=state.get('grain_size', 1.5), 
            grain_chroma=state.get('grain_chroma', 0), 
            strength_pct=state.get('str', 65),
            bp_pct=state.get('bp', 0), 
            mid_val=state.get('mid', 1.0), 
            wp_pct=state.get('wp', 255), 
            flare_amt=0, flare_u=0, flare_v=0,
            wash_r=wash_r, wash_g=wash_g, wash_b=wash_b, wash_amt=state.get('wash_amt', 0), wash_on=state.get('wash_on', True), 
            input_on=state.get('input_on', True),
            input_exposure_pct=state.get('input_exp', 20),
            input_luma_pct=state.get('input_luma', 25),
            input_vibrance_pct=state.get('input_vib', 20),
            input_tint_pct=state.get('input_tint', 0),
            input_source_fade_pct=state.get('input_fade', 0),
            optics_on=False, 
            light_on=state.get('light_on', True), 
            print_on=state.get('print_on', True), 
            grain_on=state.get('grain_on', True), 
            edge_on=False, 
            levels_on=state.get('levels_on', True), 
            flare_on=False,
            virtual_width=w, true_master_width=w, master_width=w, master_height=h, offset_x=0, offset_y=0,
            is_auto_mixing=False
        )

        pil_out = Image.fromarray((rendered_array * 255).astype(np.uint8))
        
        # Explicit GC handoff for the background thread
        del rendered_array
        
        return pil_out


    def _initial_load_worker(self):
        img_array = self.parent.preview_array
        if img_array is None:
            self._post_ui("close")
            return

        # 1. Pre-Crop for instant thumbnails
        c_left, c_top, c_w, c_h = self._get_smart_crop_box(img_array, crop_ratio=0.5)
        cropped_array = img_array[c_top:c_top + c_h, c_left:c_left + c_w]
        
        scale_factor = 300.0 / max(c_w, c_h)
        thumb_w, thumb_h = int(c_w * scale_factor), int(c_h * scale_factor)
        thumb_input_array = cv2.resize(cropped_array, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)

        total = len(self.ordered_presets)
        if total == 0:
            self._post_ui("close")
            return


        # 2. GENERATE ALL 300px THUMBNAILS (Extremely Fast)
        for idx, preset_name in enumerate(self.ordered_presets):
            if not self._is_alive: return 

            pct = (idx + 1) / total
            self._post_ui("progress", pct)
            
            thumb_raw = self._run_engine_for_preset(preset_name, thumb_input_array, is_thumb=True)
            if not thumb_raw: continue
            
            ui_thumb_h = 140
            ui_thumb_w = int(thumb_w * (ui_thumb_h / thumb_h))
            thumb_pil = thumb_raw.resize((ui_thumb_w, ui_thumb_h), Image.Resampling.LANCZOS)
            
            self._post_ui("thumb", preset_name, thumb_pil)

        # 3. GENERATE THE FIRST 1024px IMAGE BEFORE DROPPING THE LOADING SCREEN
        if self._is_alive and self.ordered_presets:
            first_preset = self.ordered_presets[0]
            first_full = self._run_engine_for_preset(first_preset, img_array, is_thumb=False)
            if first_full:
                self.completed_full_presets.add(first_preset)
                self._post_ui("full", first_preset, first_full)

        # 4. Drop the Loading Screen & Fire up the Spooler
        if self._is_alive:
            self._post_ui("finish")
            threading.Thread(target=self._spooler_worker, daemon=True).start()

    def _spooler_worker(self):
        """ARCH FIX: The Predictive Spooler. Silently renders 1024px images in the background."""
        img_array = self.parent.preview_array
        
        while self._is_alive:
            target_preset = None
            
            # Priority 1: Did the user just click something that hasn't finished yet?
            try:
                target_preset = self.priority_queue.get_nowait()
            except queue.Empty:
                # Priority 2: Keep spooling sequentially through the list
                for preset in self.ordered_presets:
                    if preset not in self.completed_full_presets:
                        target_preset = preset
                        break
            
            if target_preset is None:
                # Everything is fully rendered! The spooler can rest.
                break
                
            # Render the 1024px heavy array
            if target_preset not in self.completed_full_presets:
                full_pil = self._run_engine_for_preset(target_preset, img_array, is_thumb=False)
                
                if not self._is_alive: break # Catch if closed mid-render
                
                if full_pil:
                    self.completed_full_presets.add(target_preset)
                    self._post_ui("full", target_preset, full_pil)

    def _add_thumbnail_to_ui(self, name, thumb_pil):
        if not self.winfo_exists(): return

        tk_thumb = ImageTk.PhotoImage(thumb_pil)
        self.previews[name]['tk_thumb'] = tk_thumb
        
        frame = ctk.CTkFrame(self.filmstrip_frame, fg_color="#2A2A2A", border_color="#2A2A2A", border_width=2, corner_radius=6)
        frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.thumb_widgets[name] = frame
        
        lbl_img = tk.Label(frame, image=tk_thumb, bg="#2A2A2A", cursor="hand2")
        lbl_img.pack(padx=4, pady=(4, 2))
        
        lbl_txt = tk.Label(frame, text=name, bg="#2A2A2A", fg="#E0E0E0", font=("Arial", 9, "bold"), justify=tk.CENTER, wraplength=thumb_pil.width - 4)
        lbl_txt.pack(fill=tk.X, padx=4, pady=(0, 4))
        
        def on_click(e, n=name):
            self.select_preset(n)
            
        def on_enter(e, n=name, f=frame, txt=lbl_txt):
            if self.selected_preset != n:
                f.configure(fg_color="#4A4A4A")
                lbl_img.configure(bg="#4A4A4A")
                txt.configure(bg="#4A4A4A")
            
        def on_leave(e, n=name, f=frame, txt=lbl_txt):
            if self.selected_preset != n:
                f.configure(fg_color="#2A2A2A")
                lbl_img.configure(bg="#2A2A2A")
                txt.configure(bg="#2A2A2A")

        lbl_img.bind("<Button-1>", on_click)
        lbl_txt.bind("<Button-1>", on_click)
        lbl_img.bind("<Enter>", on_enter)
        lbl_txt.bind("<Enter>", on_enter)
        lbl_img.bind("<Leave>", on_leave)
        lbl_txt.bind("<Leave>", on_leave)
        
        if self.selected_preset is None:
            self.select_preset(name)

    def _finish_loading(self):
        if not self.winfo_exists(): return
        self.loading_frame.place_forget()
        self.update_large_preview()

    def select_preset(self, name):
        self.selected_preset = name
        self.btn_apply.configure(state="normal")
        
        for n, f in self.thumb_widgets.items():
            if n == name:
                f.configure(border_color="#FFD700", fg_color="#2A2A2A")
                for child in f.winfo_children():
                    if isinstance(child, tk.Label): child.configure(bg="#2A2A2A")
            else:
                f.configure(border_color="#2A2A2A", fg_color="#2A2A2A")
                for child in f.winfo_children():
                    if isinstance(child, tk.Label): child.configure(bg="#2A2A2A")
                    
        # If the predictive spooler hasn't reached this image yet, bump it to the front of the line!
        if name in self.previews and 'full_pil' not in self.previews[name]:
            self.priority_queue.put(name)
            
        self.update_large_preview()

    def update_large_preview(self):
        if not self.selected_preset or self.selected_preset not in self.previews:
            return
            
        cw = self.canvas_preview.winfo_width()
        ch = self.canvas_preview.winfo_height()
        if cw <= 1 or ch <= 1: return

        # Check if the predictive spooler has finished this image yet
        if 'full_pil' in self.previews[self.selected_preset]:
            full_pil = self.previews[self.selected_preset]['full_pil']
            
            img_w, img_h = full_pil.size
            scale = min(cw / img_w, ch / img_h)
            new_w, new_h = int(img_w * scale), int(img_h * scale)
            
            display_pil = full_pil.resize((new_w, new_h), Image.Resampling.LANCZOS)
            self.current_tk_preview = ImageTk.PhotoImage(display_pil)
            
            self.canvas_preview.delete("all")
            self.canvas_preview.create_image(cw//2, ch//2, anchor=tk.CENTER, image=self.current_tk_preview)
            self._draw_overlay_pill(cw, ch, f"SELECTED PROFILE: {self.selected_preset}")
            
        else:
            # The user clicked an image the spooler hasn't reached. Show the "Developing" pill briefly.
            self.canvas_preview.delete("all")
            self._draw_overlay_pill(cw, ch, f"DEVELOPING: {self.selected_preset}...")

    def _draw_overlay_pill(self, cw, ch, text):
        sf = ctk.ScalingTracker.get_widget_scaling(self)
        
        temp_id = self.canvas_preview.create_text(cw // 2, int(30*sf), text=text, font=("Arial", 12, "bold"))
        bbox = self.canvas_preview.bbox(temp_id)
        self.canvas_preview.delete(temp_id)
        
        if bbox:
            pad_x = int(25 * sf)
            pad_y = int(8 * sf)
            pill_w = bbox[2] - bbox[0] + pad_x * 2
            pill_h = bbox[3] - bbox[1] + pad_y * 2
            
            pill_img = Image.new('RGBA', (pill_w, pill_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(pill_img)
            draw.rounded_rectangle((0, 0, pill_w, pill_h), radius=pill_h//2, fill=(20, 20, 20, 160))
            
            self.pill_tk = ImageTk.PhotoImage(pill_img)
            
            self.canvas_preview.create_image(cw // 2, int(30*sf) - pad_y, image=self.pill_tk, anchor=tk.N, tags="overlay")
            self.canvas_preview.create_text(cw // 2, int(30*sf), text=text, fill="#FFFFFF", font=("Arial", 12, "bold"), anchor=tk.N, justify=tk.CENTER, tags="overlay")

    def on_preview_resize(self, event):
        self.update_large_preview()

    def apply_and_close(self):
        if self.selected_preset:
            self.parent.profile_var.set(self.selected_preset)
            self.parent.on_profile_select(self.selected_preset)
        self.destroy()