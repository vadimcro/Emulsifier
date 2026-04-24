# Changelog: Emulsifier Film Emulator 

This document tracks the evolution of the Emulsifier engine, covering major architectural pivots, mathematical implementations, UI/UX polish, and critical bug fixes.

## [v1.80 - v1.83] - The Hardware Acceleration Sprint
**Major Architecture Pivots & Optimization:**
* **CPU Vectorization (NumExpr) [v1.80]:** Completely refactored the math engine to bypass Python's Global Interpreter Lock (GIL). Photometric operations (S-Curves, Subtractive Saturation, Log mapping) are now compiled into C-machine code on the fly and distributed across all available logical CPU cores using AVX instructions. This eliminates gigabytes of temporary memory allocation (RAM thrashing) during real-time UI scrubbing.
* **Auto-Mix Algorithm Rewrite [v1.80]:** Refactored the Global Washout Detector. It now resolves the 6.0% Luma threshold purely mathematically in a flattened, multithreaded `NumExpr` equation rather than rendering and blending massive 3D arrays sequentially.
* **Pyramid Blur (Mipmapping) Architecture [v1.82]:** Solved a critical mathematical bottleneck when zooming into 4K+ images. Previously, scaling a Halation blur radius proportionally to a 4K file required massive 500x500px convolution kernels, freezing the UI. The engine now intercepts any blur with a Sigma > 5.0, geometrically downsamples the image, applies a micro-blur, and upsamples it back using bilinear interpolation. It creates identical low-frequency optical glows but executes ~100x faster.

**Critical Bugfixes:**
* **NumExpr Syntax Panic [v1.81]:** Fixed a crash where the NumExpr compiler encountered "forbidden control characters" because standard Python array slicing (`[:,:,0]`) was accidentally passed directly inside the evaluation strings.
* **OpenCV Grain Destruction [v1.83]:** Attempted to use OpenCV's native C++ `cv2.randn` to generate film grain faster than NumPy. Discovered a structural quirk where passing a scalar standard deviation to a 3-channel OpenCV array only applies noise to the Red channel, zeroing out Green and Blue. Rolled the grain generation safely back to `np.random.normal()` to preserve the physically accurate 3-channel crystalline structure.

## [v1.79] - 2026-04-23 (The Non-Destructive Update)
**Major Features & Architecture:**
* **Undo / Redo Architecture:** Implemented a robust, 5-step state-caching system, allowing users to freely experiment with color chemistry without the fear of ruining their current grade.
* **State Optimization (Action Hooks):** To prevent the undo stack from filling up with hundreds of useless micro-adjustments, the engine only takes a state snapshot when the user *finishes* an action (e.g., slider mouse release, right-click reset, toggle switch flip, profile change, or Auto-Mix completion).
* **Native Keyboard Bindings:** Hooked up standard OS shortcuts for a seamless workflow: `Ctrl+Z` / `Cmd+Z` to Undo, and `Ctrl+Y` / `Cmd+Y` / `Cmd+Shift+Z` to Redo.
* **Stack Management:** Capped the historical memory stack at 5 previous states to prevent RAM bloat, and ensured the redo stack automatically clears whenever a new parameter is actively adjusted.

## [v1.78] - 2026-04-22 (The PyInstaller Build Fixes)
**Bugfixes & Code Architecture:**
* **Fixed `_MEIxxxxx` Temp Folder Bug:** Implemented `sys.frozen` path routing. When compiled as a `--onefile` executable via PyInstaller, the app now correctly looks for the `/profiles` directory next to the `.exe` rather than crashing inside the Windows hidden AppData temp folder.
* **Fixed `RuntimeError: no default root window`:** Explicitly anchored all `CustomTkinter` (`ctk.DoubleVar`, `ctk.StringVar`) and standard `tk.BooleanVar` variables to the `master=self` root window. This prevents threading panics when running in a compiled environment.
* **Cleaned Imports:** Completely purged lingering, unused `matplotlib` imports from the header to optimize boot time and reduce the compiled `.exe` size.
* **Branding:** Officially updated application title string to *Emulsifier Film Emulator - Rendering Engine v1.78*.

## [v1.76 - v1.77] - The Smart Auto-Mix Era
**Major Math Pivots & Features:**
* **Added Smart Auto-Mix (v77):** Introduced an asynchronous background thread that tests multiple mix strengths (100% down to 40%) using the Node Cache. 
* **Global Washout Detector (v77 Pivot):** Fixed the flawed logic of v76 (which only checked the top 5% of highlights for pure-white clipping and constantly failed by returning 100%). The new v77 algorithm measures *Global Average Luminance*. It locks the slider at the absolute highest film blend that does not raise the overall image brightness by more than 6.0%.
* **UX Tweak:** Changed the default "Overall Physical Mix" boot value from an aggressive 100% down to a safer 65% for better first impressions on harsh profiles.

## [v1.73 - v1.75] - The Photometric Disaster & Rollback
**Math Pivot (Dead End):**
* Attempted to rewrite the core physics of the Film Node by stripping out the standard `Log10` exposure shift and replacing it with a pure density-domain Cineon Log compression formula without transmittance stretching.
* **The Result:** Caused catastrophic "White Veil" midtone washouts and crushed shadows because digital SDR monitors cannot display raw, un-normalized physical film density. 
* **Bugfix:** A missing `max_val` variable in v73 caused silent background thread crashes.
* **Resolution:** Completely scrapped versions 73, 74, and 75. Rolled the core film emulation math back to the highly stable, visually superior v72 baseline.

## [v1.70 - v1.72] - UX Polish & Histogram Math
**UI Fixes & Code Architecture:**
* **Decoupled Ghost Histograms (v72):** Fixed a major visual bug where the "Original" (grey) histogram dynamically shrank when the "Dehanced" (gold) histogram spiked. Decoupled their Y-axis normalizations so the grey silhouette remains a static, reliable reference anchor.
* **Strict Tooltip Discipline (v70-v71):** Engineered a custom tooltip class to stop UI clutter. Tooltips now only appear when hovering on a slider track, feature a 5-second auto-kill timer, and instantly destroy themselves upon mouse click.
* **Hover Sync:** Bound the accordion tab headers and their respective bypass toggle switches to highlight simultaneously, creating cohesive interactive hitboxes.

## [v1.65 - v1.69] - The Matplotlib Purge & Subtractive Chemistry
**Code Architecture & Math Pivots:**
* **Excised Matplotlib (v69):** Completely removed `matplotlib` from the rendering pipeline. Rewrote the histogram engine to map normalized OpenCV arrays directly to native `tk.Canvas` polygons. Eliminated UI lag and achieved instantaneous booting and rendering.
* **Subtractive Color Physics:** Implemented *Emulsion Crosstalk* (a 3x3 color matrix simulating chemical dye impurities, shifting greens to cyan and reds to orange) and *Subtractive Saturation* (a parabolic luminance curve to naturally desaturate extreme highlights and shadows).
* **Scroll Accumulator Dead End (v66-v67):** Attempted to build a floating-point "bucket" to smooth out Magic Trackpad scrolling. It ruined the precise, mechanical step-zoom required for pixel-peeping grain structure. Scrapped the accumulator and rolled back to strict 1-to-1 discrete mapping.

## [v1.22 - v1.64] - The Foundations (Summary)
**Code Architecture & UI:**
* Transitioned from procedural scripts to a strict Object-Oriented GUI architecture using `customtkinter`.
* Implemented the `TkinterDnD` drag-and-drop file loader.
* Built the **Node Cache Pipeline**: Separated the math into independent blocks (*Optics -> Light Scatter -> Emulsion -> Print -> Grain -> Edges*). Hashing and caching each step ensured that tweaking a downstream node (like Grain) did not trigger a heavy recalculation of an upstream node (like Halation), enabling real-time slider response.
* Built the interactive comparative view modes (Side-by-Side and Wipe slider).
* Implemented the interactive Output Levels canvas widget (Black point, Gamma, White point mapping).

