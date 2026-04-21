# Emulsifier

A professional-grade, photometrically accurate film emulation engine built in Python. This tool bridges the gap between digital perfection and analog reality, bypassing standard digital additive math ("video game filters") in favor of subtractive color science, physical density mapping, and optical degradation models.

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
