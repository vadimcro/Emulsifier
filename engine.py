import numpy as np
import cv2
import os
import sys
import tkinter as tk
from tkinter import messagebox

# --- HARDWARE ACCELERATION ENGINE CHECK ---
try:
    import numexpr as ne
    cores = os.cpu_count()
    ne.set_num_threads(cores if cores else 4)
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing Acceleration Engine", 
        "Emulsifier requires 'numexpr' for CPU hardware acceleration.\n\n"
        "Please open your terminal and run:\npip install numexpr"
    )
    sys.exit(1)

# --- TAICHI GPU ACCELERATION ---
try:
    import taichi as ti
    import taichi.math as tm
    ti.init(arch=ti.gpu) 
except ImportError:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Missing GPU Framework", 
        "Emulsifier requires 'taichi' for GPU VFX rendering.\n\n"
        "Please open your terminal and run:\npip install taichi"
    )
    sys.exit(1)

# --- TAICHI KERNEL DEFINITIONS ---
@ti.func
def hash2d(p: tm.vec2) -> ti.f32:
    return tm.fract(tm.sin(p[0] * 12.9898 + p[1] * 78.233) * 43758.5453)

@ti.func
def noise(p: tm.vec2) -> ti.f32:
    i = tm.floor(p)
    f = tm.fract(p)
    u = f * f * (3.0 - 2.0 * f)
    a = hash2d(i)
    b = hash2d(i + tm.vec2(1.0, 0.0))
    c = hash2d(i + tm.vec2(0.0, 1.0))
    d = hash2d(i + tm.vec2(1.0, 1.0))
    return tm.mix(tm.mix(a, b, u[0]), tm.mix(c, d, u[0]), u[1])

@ti.func
def cc(color: tm.vec3, factor: ti.f32, factor2: ti.f32) -> tm.vec3:
    w = color[0] + color[1] + color[2]
    return tm.mix(color, tm.vec3(w) * factor, w * factor2)

@ti.func
def lensflare_hidden_sun(uv: tm.vec2, pos: tm.vec2, time: ti.f32) -> tm.vec3:
    main_vec = uv - pos
    uvd = uv * tm.length(uv)
    ang = tm.atan2(main_vec[1], main_vec[0])
    dist = tm.length(main_vec)
    dist = tm.pow(dist, 0.1)
    n = noise(tm.vec2((ang - time / 9.0) * 16.0, dist * 32.0))
    
    f2 = tm.max(1.0 / (1.0 + 32.0 * tm.pow(tm.length(uvd + 0.8 * pos), 2.0)), 0.0) * 0.25
    f22 = tm.max(1.0 / (1.0 + 32.0 * tm.pow(tm.length(uvd + 0.85 * pos), 2.0)), 0.0) * 0.23
    f23 = tm.max(1.0 / (1.0 + 32.0 * tm.pow(tm.length(uvd + 0.9 * pos), 2.0)), 0.0) * 0.21
    
    uvx = tm.mix(uv, uvd, -0.5)
    f4 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.4 * pos), 2.4), 0.0) * 6.0
    f42 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.45 * pos), 2.4), 0.0) * 5.0
    f43 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.5 * pos), 2.4), 0.0) * 3.0
    
    uvx = tm.mix(uv, uvd, -0.4)
    f5 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.2 * pos), 5.5), 0.0) * 2.0
    f52 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.4 * pos), 5.5), 0.0) * 2.0
    f53 = tm.max(0.01 - tm.pow(tm.length(uvx + 0.6 * pos), 5.5), 0.0) * 2.0
    
    uvx = tm.mix(uv, uvd, -0.5)
    f6 = tm.max(0.01 - tm.pow(tm.length(uvx - 0.3 * pos), 1.6), 0.0) * 6.0
    f62 = tm.max(0.01 - tm.pow(tm.length(uvx - 0.325 * pos), 1.6), 0.0) * 3.0
    f63 = tm.max(0.01 - tm.pow(tm.length(uvx - 0.35 * pos), 1.6), 0.0) * 5.0
    
    c = tm.vec3(0.0)
    c[0] += f2 + f4 + f5 + f6
    c[1] += f22 + f42 + f52 + f62
    c[2] += f23 + f43 + f53 + f63
    return c

@ti.kernel
def apply_gpu_lens_flare(
    img: ti.types.ndarray(dtype=ti.f32),
    out: ti.types.ndarray(dtype=ti.f32),
    master_w: ti.i32, master_h: ti.i32,
    offset_x: ti.i32, offset_y: ti.i32,
    flare_u: ti.f32, flare_v: ti.f32,
    strength: ti.f32
):
    inv_w = 1.0 / master_w
    inv_h = 1.0 / master_h
    aspect = master_w * inv_h
    
    pos_u = (flare_u - 0.5) * aspect
    pos_v = 0.5 - flare_v
    pos = tm.vec2(pos_u, pos_v)

    for y, x in ti.ndrange(img.shape[0], img.shape[1]):
        master_x = x + offset_x
        master_y = y + offset_y
        
        u = (master_x * inv_w - 0.5) * aspect
        v = 0.5 - (master_y * inv_h) 
        
        uv = tm.vec2(u, v)
        
        flare_col = tm.vec3(1.4, 1.2, 1.0) * lensflare_hidden_sun(uv, pos, 0.0)
        flare_col = flare_col * (strength * 3.0) 
        
        base_col = tm.vec3(img[y, x, 0], img[y, x, 1], img[y, x, 2])
        
        out[y, x, 0] = tm.clamp(base_col[0] + flare_col[0], 0.0, 1.0)
        out[y, x, 1] = tm.clamp(base_col[1] + flare_col[1], 0.0, 1.0)
        out[y, x, 2] = tm.clamp(base_col[2] + flare_col[2], 0.0, 1.0)


def _smoothstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0 + 1e-6), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _luma_display(img):
    return (
        img[:, :, 0] * 0.2126 +
        img[:, :, 1] * 0.7152 +
        img[:, :, 2] * 0.0722
    ).astype(np.float32)

def _stats_sample(img, max_side=384):
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return img

    scale = max_side / float(longest)
    sample_w = max(16, int(w * scale))
    sample_h = max(16, int(h * scale))
    return cv2.resize(img, (sample_w, sample_h), interpolation=cv2.INTER_AREA)


def _apply_input_conditioning(img_array, exposure_pct, luma_pct, source_fade_pct, vibrance_pct, tint_pct):
    img = np.clip(img_array, 0.0, 1.0).astype(np.float32, copy=True)
    eps = 1e-5
    source_fade_amt = max(0.0, float(source_fade_pct)) / 100.0

    exp_amt = exposure_pct / 100.0
    if exp_amt > 0.0:
        y_stats = _luma_display(_stats_sample(img))
        mid = float(np.percentile(y_stats, 50.0))
        if mid > eps:
            target_mid = 0.42
            gain = np.clip(target_mid / mid, 0.65, 1.55)
            img *= gain ** (exp_amt * 0.75)
            img = np.clip(img, 0.0, 1.0)

    luma_amt = luma_pct / 100.0
    if luma_amt > 0.0:
        y = _luma_display(img)
        y_stats = _luma_display(_stats_sample(img))
        p05 = float(np.percentile(y_stats, 5.0))
        p50 = float(np.percentile(y_stats, 50.0))
        p95 = float(np.percentile(y_stats, 95.0))
        scene_range = max(p95 - p05, 0.01)
        target_range = 0.62

        if scene_range > target_range:
            pressure = min((scene_range - target_range) / target_range, 1.0)
            contrast_factor = 1.0 - (0.45 * luma_amt * pressure)
        else:
            pressure = min((target_range - scene_range) / target_range, 1.0)
            contrast_factor = 1.0 + (0.35 * luma_amt * pressure)

        y2 = np.clip((y - p50) * contrast_factor + p50, 0.0, 1.0)
        ratio = y2 / np.maximum(y, eps)
        img *= ratio[:, :, None]
        img = np.clip(img, 0.0, 1.0)

    if source_fade_amt > 0.0:
        y = _luma_display(img)
        shadow = ((1.0 - y) ** 1.6).astype(np.float32)
        highlight = (y ** 2.0).astype(np.float32)
        midtone = (1.0 - np.abs((2.0 * y) - 1.0)).astype(np.float32)

        floor_color = np.array([0.090, 0.082, 0.066], dtype=np.float32).reshape(1, 1, 3)
        img += shadow[:, :, None] * floor_color * source_fade_amt
        img = np.clip(img, 0.0, 1.0)

        y = _luma_display(img)
        y_stats = _luma_display(_stats_sample(img))
        mid = float(np.percentile(y_stats, 50.0))
        contrast_factor = 1.0 - (source_fade_amt * 0.45)
        img = mid + (img - mid) * contrast_factor
        img = np.clip(img, 0.0, 1.0)

        y = _luma_display(img)
        chroma = img - y[:, :, None]
        sat_mask = 0.35 + (0.65 * (1.0 - midtone))
        sat_loss = source_fade_amt * 0.38 * sat_mask
        img = y[:, :, None] + chroma * (1.0 - sat_loss[:, :, None])

        shadow_cast = np.array([0.050, 0.028, -0.014], dtype=np.float32).reshape(1, 1, 3)
        highlight_cast = np.array([0.016, 0.026, 0.038], dtype=np.float32).reshape(1, 1, 3)
        img += (shadow[:, :, None] * shadow_cast * source_fade_amt)
        img += (highlight[:, :, None] * highlight_cast * source_fade_amt)
        img = np.clip(img, 0.0, 1.0)

        y = _luma_display(img)
        channel_loss = source_fade_amt * 0.28
        img = y[:, :, None] + (img - y[:, :, None]) * (1.0 - channel_loss)
        img = np.clip(img, 0.0, 1.0)

    vib_amt = vibrance_pct / 100.0
    if vib_amt > 0.0:
        y = _luma_display(img)
        chroma = img - y[:, :, None]
        sat = np.sqrt(np.mean(chroma * chroma, axis=2))
        excess = _smoothstep(0.16, 0.42, sat).astype(np.float32)
        reduction = 1.0 - (excess * vib_amt * 0.65)
        img = y[:, :, None] + chroma * reduction[:, :, None]
        img = np.clip(img, 0.0, 1.0)

    tint_amt = tint_pct / 100.0
    if tint_amt > 0.0:

        stats_img = _stats_sample(img)
        y_stats = _luma_display(stats_img)
        chroma_stats = stats_img - y_stats[:, :, None]
        sat_stats = np.sqrt(np.mean(chroma_stats * chroma_stats, axis=2))
        y20 = float(np.percentile(y_stats, 20.0))
        y80 = float(np.percentile(y_stats, 80.0))
        sat_limit = float(np.percentile(sat_stats, 45.0))

        y = _luma_display(img)
        chroma = img - y[:, :, None]
        sat = np.sqrt(np.mean(chroma * chroma, axis=2))
        mask = (y > y20) & (y < y80) & (sat <= max(sat_limit, 0.04))

        if np.count_nonzero(mask) > max(64, img.shape[0] * img.shape[1] * 0.01):
            avg = np.mean(img[mask], axis=0)
            gray = float(np.mean(avg))
            gains = np.clip(gray / np.maximum(avg, eps), 0.85, 1.18)
            confidence = np.clip(np.count_nonzero(mask) / (img.shape[0] * img.shape[1] * 0.20), 0.0, 1.0)
            img *= gains.reshape(1, 1, 3) ** (tint_amt * confidence * 0.70)
            img = np.clip(img, 0.0, 1.0)

    return img


# --- MAIN ENGINE PIPELINE ---
def process_engine(cache, img_array, film_profile, log_e_grid, curve_data, 
                   soft_amt, ca_amt, ff_amt, ff_fall, vig_amt, vig_fall, flatten_pct, 
                   cross_pct, hal_pct, bloom_pct, contrast_pct, subsat_pct, split_pct, grain_amt, grain_size, grain_chroma, strength_pct, 
                   bp_pct, mid_val, wp_pct, 
                   flare_amt, flare_u, flare_v, flare_on, wash_r, wash_g, wash_b, wash_amt, wash_on,
                   optics_on, light_on, print_on, grain_on, edge_on, levels_on,
                   virtual_width, true_master_width, master_width, master_height, offset_x, offset_y, is_auto_mixing=False, is_auto_levels=False,
                   input_on=True, input_exposure_pct=20, input_luma_pct=25, input_source_fade_pct=0, input_vibrance_pct=20, input_tint_pct=0):
    
    if not film_profile:
        bypass = np.clip(img_array, 0, 1)
        return bypass, bypass, None, None, None

    h, w, _ = img_array.shape

    # --- NODE 0: INPUT CONDITIONING ---
    input_hash = hash((
        id(img_array), img_array.shape, input_on,
        round(float(input_exposure_pct), 3),
        round(float(input_luma_pct), 3),
        round(float(input_source_fade_pct), 3),
        round(float(input_vibrance_pct), 3),
        round(float(input_tint_pct), 3)
    ))
    if cache.get('input_hash') == input_hash:
        img_array = cache['input_conditioned']
    else:
        if input_on and (input_exposure_pct > 0 or input_luma_pct > 0 or input_source_fade_pct > 0 or input_vibrance_pct > 0 or input_tint_pct > 0):
            img_array = _apply_input_conditioning(
                img_array,
                input_exposure_pct,
                input_luma_pct,
                input_source_fade_pct,
                input_vibrance_pct,
                input_tint_pct
            )
        else:
            img_array = np.clip(img_array, 0.0, 1.0)
        cache['input_conditioned'] = img_array
        cache['input_hash'] = input_hash

    img_id = input_hash

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

    # =========================================================================
    # ROLLING CACHE: HEAVY NODES (1-3)
    # =========================================================================

    # --- NODE 1: OPTICS ---
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

    # --- NODE 2: LIGHT & SCATTER ---
    light_hash = hash((optics_hash, flatten_pct, cross_pct, bloom_pct, hal_pct, light_on, virtual_width))
    if cache.get('light_hash') == light_hash:
        linear = cache['light']
    else:
        linear = ne.evaluate("where(img > 0.0, img, 0.0) ** 2.2")
        
        if light_on:
            flat_amount = flatten_pct / 100.0
            if flat_amount > 0:
                log_base = 1.0 + (flat_amount * 10.0)
                ne.evaluate("log(1.0 + (log_base - 1.0) * linear) / log(log_base)", out=linear)

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
                ne.evaluate("where(linear > 0.0, linear, 0.0)", out=linear)

            bloom = bloom_pct / 100.0
            if bloom > 0:
                hl_mask_wide = ne.evaluate("where((linear - 0.5) / 0.5 > 0.0, (linear - 0.5) / 0.5, 0.0)")
                ne.evaluate("where(hl_mask_wide < 1.0, hl_mask_wide, 1.0)", out=hl_mask_wide)
                
                mask_f32 = hl_mask_wide.astype(np.float32)
                bloom_blur = _fast_glow(mask_f32, virtual_width * 0.02)
                ne.evaluate("linear + (bloom_blur * bloom * 0.5)", out=linear)
            
            hal = hal_pct / 100.0
            if hal > 0:
                hl_threshold = 0.4
                highlights = ne.evaluate("where((linear - hl_threshold) / (1.0 - hl_threshold) > 0.0, (linear - hl_threshold) / (1.0 - hl_threshold), 0.0)")
                ne.evaluate("where(highlights < 1.0, highlights, 1.0)", out=highlights)
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

    # --- NODE 3: EMULSION DENSITY ---
    film_prof_name = film_profile['film_name']
    film_hash = hash((light_hash, film_prof_name))
    if cache.get('film_hash') == film_hash:
        film_out = cache['film']
    else:
        digital_log = ne.evaluate("log10(where(linear > 1e-5, linear, 1e-5))")
        min_log_e = np.min(log_e_grid)
        max_log_e = np.max(log_e_grid)
        curve_center = (min_log_e + max_log_e) / 2.0
        
        mapped_log_e = ne.evaluate("digital_log - log10(0.18) + curve_center")
        
        out_r = np.interp(mapped_log_e[:, :, 0], log_e_grid, curve_data['r']).astype(np.float32)
        out_g = np.interp(mapped_log_e[:, :, 1], log_e_grid, curve_data['g']).astype(np.float32)
        out_b = np.interp(mapped_log_e[:, :, 2], log_e_grid, curve_data['b']).astype(np.float32)
        density = np.stack([out_r, out_g, out_b], axis=-1)
        
        density_scalar = 0.60 

        d_min_raw = film_profile['density_anchors']['d_min']
        d_max_raw = film_profile['density_anchors']['d_max']
        
        raw_min_array = np.array([d_min_raw['r'], d_min_raw['g'], d_min_raw['b']], dtype=np.float32) * density_scalar
        raw_max_array = np.array([d_max_raw['r'], d_max_raw['g'], d_max_raw['b']], dtype=np.float32) * density_scalar
        
        d_min_array = np.minimum(raw_min_array, raw_max_array)
        d_max_array = np.maximum(raw_min_array, raw_max_array)

        transmittance = ne.evaluate("10.0 ** (-1.0 * density * density_scalar)")
        t_max_3d = (10.0 ** (-d_min_array)).reshape(1,1,3)
        t_min_3d = (10.0 ** (-d_max_array)).reshape(1,1,3)
        
        out_linear = ne.evaluate("(transmittance - t_min_3d) / (t_max_3d - t_min_3d)")

        if film_profile['properties']['film_type'] == 'negative':
            ne.evaluate("1.0 - out_linear", out=out_linear)

        ne.evaluate("where(out_linear < 0.001, 0.001, where(out_linear > 0.999, 0.999, out_linear))", out=out_linear)
        
        inv_gamma = 1.0 / 2.2
        film_out = ne.evaluate("out_linear ** inv_gamma")
        
        cache['film'] = film_out
        cache['film_hash'] = film_hash

    # =========================================================================
    # LIVE NODES: COMPUTED ON THE FLY (4-9)
    # =========================================================================

    current_film_out = ne.evaluate("where(film_out < 0.0, 0.0, where(film_out > 1.0, 1.0, film_out))")
    
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

    if print_on:
        contrast = contrast_pct / 100.0
        if contrast > 0:
            k = 0.46 
            n = 2.5  
            x_n = ne.evaluate("where(current_film_out > 1e-6, current_film_out, 1e-6) ** n")
            k_n = k ** n
            nr_curve = ne.evaluate("x_n / (x_n + k_n)")
            max_val = 1.0 / (1.0 + k_n)
            ne.evaluate("nr_curve / max_val", out=nr_curve)
            ne.evaluate("(current_film_out * (1.0 - contrast)) + (nr_curve * contrast)", out=current_film_out)

        subsat_amount = (subsat_pct / 100.0) * 0.85 
        if subsat_amount > 0:
            r = current_film_out[:,:,0]
            g = current_film_out[:,:,1]
            b = current_film_out[:,:,2]
            luma = ne.evaluate("0.299 * r + 0.587 * g + 0.114 * b")
            
            sat_mult = ne.evaluate("1.0 - subsat_amount * ((2.0 * luma - 1.0) ** 2.0)")
            ne.evaluate("where(sat_mult < 0.0, 0.0, where(sat_mult > 1.0, 1.0, sat_mult))", out=sat_mult)
            
            new_r = ne.evaluate("luma + (r - luma) * sat_mult")
            new_g = ne.evaluate("luma + (g - luma) * sat_mult")
            new_b = ne.evaluate("luma + (b - luma) * sat_mult")
            current_film_out = np.stack([new_r, new_g, new_b], axis=-1)

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
                new_r = ne.evaluate("r * ((1.0 - split) + (cmap_r * split))")
                new_g = ne.evaluate("g * ((1.0 - split) + (cmap_g * split))")
                new_b = ne.evaluate("b * ((1.0 - split) + (cmap_b * split))")
            else: 
                neg_split = -split
                cmap_r = ne.evaluate("(cool_r * luma) + (warm_r * (1.0 - luma))")
                cmap_g = ne.evaluate("(cool_g * luma) + (warm_g * (1.0 - luma))")
                cmap_b = ne.evaluate("(cool_b * luma) + (warm_b * (1.0 - luma))")
                new_r = ne.evaluate("r * ((1.0 + split) + (cmap_r * neg_split))")
                new_g = ne.evaluate("g * ((1.0 + split) + (cmap_g * neg_split))")
                new_b = ne.evaluate("b * ((1.0 + split) + (cmap_b * neg_split))")
            current_film_out = np.stack([new_r, new_g, new_b], axis=-1)

    ne.evaluate("where(current_film_out < 0.0, 0.0, where(current_film_out > 1.0, 1.0, current_film_out))", out=current_film_out)
    
    max_opacity_limit = 0.50
    opacity = (strength_pct / 100.0) * max_opacity_limit
    final_out = ne.evaluate("(img_array * (1.0 - opacity)) + (current_film_out * opacity)")

    if flare_on and flare_amt > 0 and not is_auto_mixing:
        contig_in = np.ascontiguousarray(final_out, dtype=np.float32)
        out_flare = np.empty_like(contig_in, dtype=np.float32)
        apply_gpu_lens_flare(
            contig_in, out_flare,
            int(master_width), int(master_height),
            int(offset_x), int(offset_y),
            float(flare_u), float(flare_v),
            float(flare_amt / 100.0)
        )
        final_out = out_flare

    if grain_on:
        grain = grain_amt / 100.0
        chroma = grain_chroma / 100.0
        if grain > 0:
            applied_grain_size = grain_size * (virtual_width / true_master_width)
            scale = max(1.0, applied_grain_size / 1.5)
            gh, gw = int(h / scale), int(w / scale)
            
            base_noise = np.random.normal(0, 1.0, (gh, gw, 3)).astype(np.float32)
            noise = cv2.resize(base_noise, (w, h), interpolation=cv2.INTER_LINEAR) if scale > 1.0 else base_noise
            
            ne.evaluate("sign(noise) * (abs(noise) ** 1.5)", out=noise)
            
            n_0, n_1, n_2 = noise[:,:,0], noise[:,:,1], noise[:,:,2]
            n_luma = ne.evaluate("(n_0 + n_1 + n_2) / 3.0")
            
            luma_blend = 1.0 - chroma
            n_r = ne.evaluate("(n_luma * luma_blend) + (n_0 * chroma)")
            n_g = ne.evaluate("(n_luma * luma_blend) + (n_1 * chroma)")
            n_b = ne.evaluate("(n_luma * luma_blend) + (n_2 * chroma)")
                
            r, g, b = final_out[:,:,0], final_out[:,:,1], final_out[:,:,2]
            luma_img = ne.evaluate("0.299 * r + 0.587 * g + 0.114 * b")
            
            grain_mask = ne.evaluate("(luma_img ** 0.5) * ((1.0 - luma_img) ** 1.5) * 2.5")
            ne.evaluate("where(grain_mask < 0.0, 0.0, where(grain_mask > 1.0, 1.0, grain_mask))", out=grain_mask)
            
            grain_factor = grain * 0.15
            new_r = ne.evaluate("r + (n_r * grain_mask * grain_factor)")
            new_g = ne.evaluate("g + (n_g * grain_mask * grain_factor)")
            new_b = ne.evaluate("b + (n_b * grain_mask * grain_factor)")
            final_out = np.stack([new_r, new_g, new_b], axis=-1)

    if edge_on and (ff_amt > 0 or vig_amt > 0):
        y_coords = np.arange(offset_y, offset_y + h, dtype=np.float32)
        x_coords = np.arange(offset_x, offset_x + w, dtype=np.float32)
        x, y = np.meshgrid(x_coords, y_coords)
        cy, cx = master_height / 2.0, master_width / 2.0
        max_dist = np.sqrt(cx**2 + cy**2)
        base_dist = ne.evaluate("sqrt((x - cx)**2 + (y - cy)**2) / max_dist")

        if ff_amt > 0:
            safe_radius_ff = 1.0 - (ff_fall / 100.0)
            ff_mask = ne.evaluate("(base_dist - safe_radius_ff) / (1.0 - safe_radius_ff + 1e-5)")
            ne.evaluate("where(ff_mask < 0.0, 0.0, where(ff_mask > 1.0, 1.0, ff_mask))", out=ff_mask)
            ne.evaluate("ff_mask * ff_mask * (3.0 - 2.0 * ff_mask)", out=ff_mask)
            
            max_sigma = (virtual_width * 0.005) * (ff_amt / 100.0) 
            blurred_img = _fast_glow(final_out, max_sigma)
            
            r, g, b = final_out[:,:,0], final_out[:,:,1], final_out[:,:,2]
            br, bg, bb = blurred_img[:,:,0], blurred_img[:,:,1], blurred_img[:,:,2]
            
            new_r = ne.evaluate("(r * (1.0 - ff_mask)) + (br * ff_mask)")
            new_g = ne.evaluate("(g * (1.0 - ff_mask)) + (bg * ff_mask)")
            new_b = ne.evaluate("(b * (1.0 - ff_mask)) + (bb * ff_mask)")
            final_out = np.stack([new_r, new_g, new_b], axis=-1)

        if vig_amt > 0:
            safe_radius_vig = 1.0 - (vig_fall / 100.0)
            vig_mask = ne.evaluate("(base_dist - safe_radius_vig) / (1.0 - safe_radius_vig + 1e-5)")
            ne.evaluate("where(vig_mask < 0.0, 0.0, where(vig_mask > 1.0, 1.0, vig_mask))", out=vig_mask)
            ne.evaluate("vig_mask * vig_mask * (3.0 - 2.0 * vig_mask)", out=vig_mask)
            
            intensity = vig_amt / 100.0
            v_mult = ne.evaluate("1.0 - (vig_mask * intensity)")
            
            r, g, b = final_out[:,:,0], final_out[:,:,1], final_out[:,:,2]
            new_r = ne.evaluate("r * v_mult")
            new_g = ne.evaluate("g * v_mult")
            new_b = ne.evaluate("b * v_mult")
            final_out = np.stack([new_r, new_g, new_b], axis=-1)

    pre_levels_blended = np.copy(final_out)
    ne.evaluate("where(pre_levels_blended < 0.0, 0.0, where(pre_levels_blended > 1.0, 1.0, pre_levels_blended))", out=pre_levels_blended)

    auto_bp_out = None
    auto_wp_out = None
    if is_auto_levels:
        r_pl, g_pl, b_pl = pre_levels_blended[:,:,0], pre_levels_blended[:,:,1], pre_levels_blended[:,:,2]
        luma_pl = ne.evaluate("0.299 * r_pl + 0.587 * g_pl + 0.114 * b_pl")
        bp_val = float(np.percentile(luma_pl, 0.5))
        wp_val = float(np.percentile(luma_pl, 99.5))
        
        if wp_val > bp_val + 0.05:
            bp_pct = bp_val * 255.0
            wp_pct = wp_val * 255.0
            auto_bp_out = bp_pct
            auto_wp_out = wp_pct

    if levels_on:
        bp = bp_pct / 255.0
        wp = wp_pct / 255.0
        if bp > 0.0 or wp < 1.0 or mid_val != 1.0:
            ne.evaluate("(final_out - bp) / (wp - bp + 1e-5)", out=final_out)
            ne.evaluate("where(final_out < 0.0, 0.0, where(final_out > 1.0, 1.0, final_out))", out=final_out)
            if mid_val != 1.0:
                inv_mid = 1.0 / mid_val
                ne.evaluate("final_out ** inv_mid", out=final_out)

    ne.evaluate("where(final_out < 0.0, 0.0, where(final_out > 1.0, 1.0, final_out))", out=final_out)
    
    if wash_on and wash_amt > 0:
        wash_val = wash_amt / 100.0
        r_out, g_out, b_out = final_out[:,:,0], final_out[:,:,1], final_out[:,:,2]
        luma = ne.evaluate("0.299 * r_out + 0.587 * g_out + 0.114 * b_out")
        
        sh_r, sh_g, sh_b = wash_r * 0.3, wash_g * 0.3, wash_b * 0.3
        hi_r = wash_r + (1.0 - wash_r) * 0.3
        hi_g = wash_g + (1.0 - wash_g) * 0.3
        hi_b = wash_b + (1.0 - wash_b) * 0.3
        
        grad_r = ne.evaluate("sh_r * (1.0 - luma) + hi_r * luma")
        grad_g = ne.evaluate("sh_g * (1.0 - luma) + hi_g * luma")
        grad_b = ne.evaluate("sh_b * (1.0 - luma) + hi_b * luma")
        
        r_soft = ne.evaluate("(1.0 - 2.0 * grad_r) * (r_out ** 2.0) + (2.0 * grad_r * r_out)")
        g_soft = ne.evaluate("(1.0 - 2.0 * grad_g) * (g_out ** 2.0) + (2.0 * grad_g * g_out)")
        b_soft = ne.evaluate("(1.0 - 2.0 * grad_b) * (b_out ** 2.0) + (2.0 * grad_b * b_out)")
        
        new_r = ne.evaluate("r_out * (1.0 - wash_val) + r_soft * wash_val")
        new_g = ne.evaluate("g_out * (1.0 - wash_val) + g_soft * wash_val")
        new_b = ne.evaluate("b_out * (1.0 - wash_val) + b_soft * wash_val")
        
        final_out = np.stack([new_r, new_g, new_b], axis=-1)
        ne.evaluate("where(final_out < 0.0, 0.0, where(final_out > 1.0, 1.0, final_out))", out=final_out)

    return final_out, pre_levels_blended, optimal_str, auto_bp_out, auto_wp_out