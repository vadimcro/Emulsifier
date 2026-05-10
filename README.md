
# Emulsifier v2.01

A photometrically accurate film emulation engine built in Python. This tool bridges the gap between digital perfection and analog reality, bypassing standard digital additive math ("video game filters") in favor of subtractive color science, physical density mapping, and optical degradation models.

<img width="2048" height="1370" alt="image" src="https://github.com/user-attachments/assets/447be247-0cf3-40b2-9dbf-64f3106db183" />


## The Main Idea: Breaking the Digital Illusion

Modern digital cameras and AI image generators produce sterile, mathematically perfect pixels. They operate in a linear light domain where colors are added together, resulting in a hyper-clean, often "plastic" aesthetic.

Physical film is the exact opposite. Film is a messy, subtractive, physical medium. It relies on chemical dye layers that block light, microscopic silver halide crystals that form irregular grain, and optical glass that bleeds red light (halation) and softens at the edges.

**Emulsifier was built to "dehance" digital perfection.** Instead of slapping a simple RGB color LUT onto an image, Emulsifier pushes your digital image through a simulated physical pipeline (*Optics -> Light Scatter -> Emulsion -> Darkroom Print -> VFX Flare -> Silver Grain -> CC Filters*). It maps your digital exposure directly into the logarithmic physical film density domain, perfectly replicating the exact mathematical space used by high-end Hollywood film scanners. The result is a rich, organic, and truly cinematic image that feels like it was developed in a darkroom, not rendered on a GPU.

## Key Architectural Pillars

1. **Density-Direct Math:** Avoids the "Transmittance Trap". By keeping calculations in the Density domain, highlights roll off gently and shadows maintain analog milkiness without violently blowing out or crushing.
2. **Smart Auto-Mix Safety Net:** Film curves are inherently aggressive. Emulsifier's built-in "Smart Auto-Mix" analyzes the global average luminance of your image and calculates the exact blend limit that preserves organic dye shifts without washing out your midtones.
3. **Subtractive Color Physics:** Accurately simulates Emulsion Crosstalk (chemical dye impurities) and Subtractive Saturation (where extreme highlights and shadows naturally lose color density).
4. **Hardware Acceleration Engine:** Emulsifier intelligently routes math through the fastest available hardware. It utilizes `NumExpr` for hyper-threaded CPU vectorization, mutating massive arrays entirely in-place to stabilize RAM. It seamlessly offloads heavy procedural VFX (like fractal Lens Flares) to your dedicated GPU via the `Taichi` framework.
5. **Asynchronous Architecture & Predictive Spooling:** Heavy processing is strictly segregated from the UI. A background daemon thread handles full-res exporting with aggressive garbage collection, preventing UI freezes and RAM creep. In the Gallery, a Predictive Spooler pre-renders high-res presets in the background to stay one step ahead of the user's keystrokes.

---

# Feature Guide: Interface & Color Science

The Analogue Emulsion Renderer is divided into two main components: the Workspace (where you navigate and analyze your image) and the Physics Pipeline (where you manipulate the color science).

---

## Part 1: Workspace & Navigation

### 1. Dynamic Telemetry HUD & Importing

* **The HUD:** The application's window title acts as a real-time telemetry readout. Upon loading an image, it dynamically displays the App Version, original image resolution (px), approximate uncompressed memory footprint (MB), and the active compute layer (GPU vs. CPU Mode).
* **Importing:** Load your digital images using the dedicated UI button, standard Drag & Drop, or **Direct Clipboard Paste** (`Ctrl+V` / `Cmd+V`). Emulsifier can instantly intercept and build canvases from raw pixel data or copied files directly from your OS clipboard. *New in v2.01: The app aggressively forces OS-level focus upon loading an image so you can instantly use keyboard shortcuts.*

### 2. Film Profiles & The Emulsion Lightbox ( ⌕ )

* **How it works:** The engine is driven by physical film data. When the app launches, it scans the local `/profiles` folder for JSON files containing film metadata, which are mapped to CSV files containing the actual characteristic densitometry curves of real film stocks.
* **The Lightbox Gallery:** Click the magnifying glass icon to compare your image across every film profile simultaneously. The Lightbox utilizes a **Smart Saliency algorithm** (Haar cascades + variance mapping) to find the most detailed part of your photo and crops instant 300px thumbnails.
* **Predictive Spooler:** Navigate the gallery using your keyboard's Arrow Keys. A background spooler silently pre-renders the 1024px high-res versions of adjacent presets into RAM, guaranteeing a zero-lag, instant A/B comparison as you scroll.

### 3. Dual-Luminance Histograms (Ghost & Gold)

* **How it works:** The top right panel features a decoupled, dual-display histogram to visualize exactly how the film chemistry is altering your exposure. It safely bypasses localized viewports to calculate exact, full-frame statistics.
* **The "Ghost" (Grey):** This represents the luminance of your *original* digital image. It remains static, acting as a structural anchor.
* **The "Gold":** This represents your *dehanced* image. As you push contrast, flares, or split tones, you can watch the gold histogram shift, compress, or expand against the grey original.

### 4. Interactive Comparative View Modes

Monitor your dehancing process in real-time with responsive UI buttons located at the bottom of the preview window:

* **[ | ] Side-by-Side:** Splits the canvas evenly. The left monitor shows the raw original; the right shows the live rendered output.
* **WIPE:** Overlays the dehanced image directly on top of the original. Click and drag the vertical slider left and right to inspect specific details (like skin tones or halation bleed) across the exact same pixel coordinates.
* **The Quick Flash ( / ):** Hold the Forward Slash key at any time to instantly flash the original digital image onto the screen. Release to bring back your grade.
* **Distraction-Free Fullscreen:** Pressing the **[ Spacebar ]** while zoomed out triggers an OS-level fullscreen takeover. All UI panels and sliders vanish, the background drops to pitch black, and your image scales to fit your entire monitor for objective evaluation. Tap again or press `ESC` to return.

### 5. Zooming, Panning & Master Reset

* **Zooming:** Use your mouse wheel, or simply click directly on the canvas to punch in for 1-to-1 pixel peeping. Click again to return to "FIT" mode.
* **Panning:** While zoomed in, hold the **[ Spacebar ]** and drag your mouse to pan around the image. *(The Spacebar is context-aware: it pans when zoomed in, and toggles Fullscreen when zoomed out).*
* **Resets:** Right-click any slider to snap it back to its specific default. The global reset button (`↺`) instantly flattens all sliders and neutralizes the workspace to our calibrated 35mm optimal defaults. All changes are tracked by a 5-step Undo/Redo stack (`Ctrl+Z` / `Ctrl+Y`).

### 6. Asynchronous Exporting

* **How it works:** Because the real-time UI operates on a proxy image, clicking "Export Full-Res Render" bypasses the proxy. The engine funnels your original, massive image file through the math pipeline utilizing a dedicated daemon thread.
* **Zero UI Freeze:** The UI remains perfectly responsive during export. Upon completion, a ruthless "Janitor" protocol forces Python's garbage collector to release the massive memory arrays back to the OS, allowing for heavy batch sessions without RAM creep. Supports `.PNG`, `.TIFF` (deflate compression), and `.JPEG`.


<img width="2048" height="1370" alt="image" src="https://github.com/user-attachments/assets/936e346b-a2f5-4a78-9a7f-4372450aa12d" />


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

### VFX Lens Flare

* **Interactive Light Placement:** A heavily procedural, GPU-accelerated optical flare. Click the **"Set Light Source"** button to convert your cursor to a crosshair, allowing you to click anywhere on your image to physically pinpoint the flare's `U, V` origin coordinates. The flare uses authentic Linear Dodge additive math to realistically blow out your image's highlights.

### Physical Grain

* **Dye Cloud Amount & Crystal Size:** Generates non-linear grain that correctly interacts with image luminance (grain is most visible in midtones, and disappears in pure whites/blacks). Optimized defaults (Amount 20, Size 1.2) provide a photorealistic 35mm baseline.
* **Color Variation:** Blends between crisp, monochromatic structural crystals (0%) and chaotic, overlapping chemical dye clouds (100%).

### Edge Imperfections

* **Field Flatness Softness & Creep:** Simulates older lenses losing resolving power (blurring) toward the edges of the frame.
* **Vignette Intensity & Creep:** Simulates physical light falloff darkening the corners of the lens barrel.

### Color Compensating (CC) Filters

* **Significance:** Simulates mounting physical, colored optical glass (like CTO or CTB filters) to the front of your taking lens.
* **The Physics:** Emulsifier uses an advanced luminosity gradient. It analyzes the per-pixel brightness of your photo, burning a deep version of your chosen color into the shadows and dodging a bright version into the highlights. It perfectly preserves absolute blacks and pure whites so the image never feels washed out.
* Choose from 6 calibrated presets or use the custom hex picker to mix your own.

### Output Levels

* **Significance:** An interactive digital adjustment pass. Drag the three triangles under the histogram to set the absolute black point, white point, and midtone gamma. Use this to anchor true digital black if the film emulation leaves the shadows too "milky". Right-click to reset.
the absolute black point, white point, and midtone gamma. Use this to anchor true digital black if the film emulation leaves the shadows too "milky". Right-click to reset.

---
