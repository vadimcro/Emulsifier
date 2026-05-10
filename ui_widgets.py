import tkinter as tk
import customtkinter as ctk
import numpy as np

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