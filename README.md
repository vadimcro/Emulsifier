# Emulsifier

A photometrically accurate film emulation engine built in Python. This tool bridges the gap between digital perfection and analog reality, bypassing standard digital additive math ("video game filters") in favor of subtractive color science, physical density mapping, and optical degradation models.

## The Main Idea: Breaking the Digital Illusion
Modern digital cameras and AI image generators produce sterile, mathematically perfect pixels. They operate in a linear light domain where colors are added together, resulting in a hyper-clean, often "plastic" aesthetic. 

Physical film is the exact opposite. Film is a messy, subtractive, physical medium. It relies on chemical dye layers that block light, microscopic silver halide crystals that form irregular grain, and optical glass that bleeds red light (halation) and softens at the edges. 

**Emulsifier was built to "dehance" digital perfection.** Instead of slapping a simple RGB color LUT onto an image, Emulsifier pushes your digital image through a simulated physical pipeline (*Optics -> Light Scatter -> Emulsion -> Darkroom Print -> Silver Grain*). It maps your digital exposure directly into the logarithmic physical film density domain, perfectly replicating the exact mathematical space used by high-end Hollywood film scanners. The result is a rich, organic, and truly cinematic image that feels like it was developed in a darkroom, not rendered on a GPU.

## Key Architectural Pillars
1. **Density-Direct Math:** Avoids the "Transmittance Trap." By keeping calculations in the Density domain, highlights roll off gently and shadows maintain analog milkiness without violently blowing out or crushing.
2. **Smart Auto-Mix Safety Net:** Film curves are inherently aggressive. Emulsifier's built-in "Smart Auto-Mix" analyzes the global average luminance of your image and calculates the exact blend limit that preserves organic dye shifts without washing out your midtones.
3. **Subtractive Color Physics:** Accurately simulates Emulsion Crosstalk (chemical dye impurities) and Subtractive Saturation (where extreme highlights and shadows naturally lose color density).
4. **Node Cache Performance:** Emulsifier caches every step of the photometric pipeline in RAM. Adjusting the print contrast or grain size does not require recalculating the heavy halation blur, allowing for seamless, real-time UI performance.

---

﻿﻿<img width="1971" height="1161" alt="image" src="https://github.com/user-attachments/assets/d3265db6-1c05-4a1a-bbde-d1ad72db8494" />

---

# Feature Guide: Interface & Color Science

The Analogue Emulsion Renderer is divided into two main components: the Workspace (where you navigate and analyze your image) and the Physics Pipeline (where you manipulate the color science).

---

## Part 1: Workspace & Navigation

### 1. Film Profiles & The `/profiles` Directory
* **How it works:** The engine is driven by physical film data. When the app launches, it scans the local `/profiles` folder for JSON files containing film metadata, which are mapped to CSV files containing the actual characteristic densitometry curves of real film stocks (e.g., Kodak Vision3, Fujifilm Provia).
* **Usage:** Use the top dropdown menu to select a film emulation. If you add new JSON/CSV profiles to the `/profiles` folder, the app will automatically build a cached list on its next boot.

### 2. Dual-Luminance Histograms (Ghost & Gold)
* **How it works:** The top right panel features a decoupled, dual-display histogram to visualize exactly how the film chemistry is altering your exposure.
* **The "Ghost" (Grey):** This represents the luminance of your *original* digital image. It remains static, acting as a structural anchor.
* **The "Gold":** This represents your *dehanced* image. As you push contrast, grain, or split tones, you can watch the gold histogram shift, compress, or expand against the grey original.

### 3. Comparative View Modes
Monitor your dehancing process in real-time with two distinct comparison tools located at the bottom left of the preview window:
* **[ | ] Side-by-Side:** Splits the canvas evenly. The left monitor shows the raw original; the right shows the live rendered output.
* **WIPE:** Overlays the dehanced image directly on top of the original. Click and drag the vertical slider left and right to inspect specific details (like skin tones or halation bleed) across the exact same pixel coordinates.

### 4. Zoom & Panning
* **Zooming:** Use your mouse wheel, or simply click directly on the canvas to punch in for 1-to-1 pixel peeping (crucial for checking grain size and chromatic aberration). Click again to return to "FIT" mode.
* **Panning:** While zoomed in, hold the **[ Spacebar ]** and drag your mouse to pan around the image. 

### 5. Exporting Full-Res Renders
* **How it works:** Because the real-time UI operates on a proxy image for performance, clicking "Export Full-Res Render" bypasses the proxy. The engine funnels your original, massive image file through the math pipeline utilizing your exact slider coordinates.
* **Formats:** Supports lossless `.PNG`, `.TIFF` (with deflate compression), and high-quality `.JPEG`.

---

<img width="1971" height="1161" alt="image" src="https://github.com/user-attachments/assets/8c7df058-5936-46ec-90b9-0d938b20673a" />

---

## Part 2: The Physics Pipeline (Sliders)

### Overall Physical Mix & Auto-Mix
* **Significance:** The master opacity of the film emulation against your digital image. 
* **The [ Auto ] Button:** Because physical film density can sometimes wash out digital midtones, clicking `Auto` triggers a background binary search. The engine analyzes the global luminance and automatically glides the slider to the absolute highest mix percentage that protects your image from blowing out.

### Lens Optics
* **Optical Softness:** Simulates the lack of hyper-sharp micro-contrast in vintage lenses. Takes the "digital edge" off modern AI/digital portraits.
* **Chromatic Aberration:** Simulates lateral color fringing (red/blue splitting) near high-contrast edges, mimicking imperfect vintage glass.

### Light & Scatter
* **Cine-Log Flattening:** Pre-flattens your digital contrast into a logarithmic space *before* it hits the film curve. Excellent for recovering crushed shadows in harsh digital photos.
* **Emulsion Crosstalk:** Simulates impure chemical dye layers. Pushing this slider twists greens toward cyan and reds toward orange, instantly creating a rich, vintage color palette.
* **Dual-Stage Halation:** Simulates bright light bouncing off the camera backplate and scattering into the red emulsion layer, creating a distinct red/orange bleeding halo around highlights.
* **Lens Bloom:** Simulates light scattering inside the lens glass, creating a wide, soft, neutral-colored glow that reduces global micro-contrast.

### Darkroom Print
* **Analog Print Contrast:** Simulates printing the negative onto different grades of darkroom paper. It steepens the image density organically without separating luma from color.
* **Subtractive Saturation:** In physical film, pure white and pure black cannot hold color. This slider naturally desaturates the extreme highlights and darkest shadows, fixing "neon" digital skies.
* **Warm/Cool Split Tone:** Mimics slight chemical temperature imbalances during darkroom development, pushing midtones warm and shadows cool (or vice versa).

### Physical Grain
* **Dye Cloud Amount & Crystal Size:** Generates non-linear grain that correctly interacts with image luminance (grain is most visible in midtones, and disappears in pure whites/blacks). Use size `1.2` for clean 35mm, or `2.5+` for gritty 16mm.

### Edge Imperfections
* **Field Flatness Softness & Creep:** Simulates older lenses losing resolving power (blurring) toward the edges of the frame.
* **Vignette Intensity & Creep:** Simulates physical light falloff darkening the corners of the lens barrel.

### Output Levels
* **Significance:** An interactive digital adjustment pass. Drag the three triangles under the histogram to set the absolute black point, white point, and midtone gamma. Use this to anchor true digital black if the film emulation leaves the shadows too "milky". Right-click to reset.
