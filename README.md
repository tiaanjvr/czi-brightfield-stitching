# Automated Brightfield Microscopy Stitching Pipeline (CZI to OME-TIFF)

A high-performance, hybrid Python/Fiji pipeline designed to batch process, seamlessly stitch, color-correct, and compress massive Zeiss `.czi` brightfield microscopy datasets into QuPath-ready `.ome.tif` files.

## 1. Evolution & Architecture
This pipeline was developed to solve the specific mathematical and software challenges of handling large brightfield histology slides (e.g., H&E, Masson's Trichrome). 

### The Challenges (Why standard tools failed):
* **Flat Stitching:** Relying strictly on the microscope's mechanical stage coordinates left jagged edges and misaligned cells due to mechanical drift.
* **ASHLAR:** Failed on brightfield images. ASHLAR uses phase correlation optimized for dark backgrounds (fluorescence). The bright white glass and dark optical vignetting in brightfield slides caused the algorithm to scatter the tiles.
* **Headless Fiji (Bio-Formats):** Trying to run Fiji's Grid/Collection stitching directly on `.czi` files caused "Ghosting" (Fiji accidentally tried to stitch the 100% resolution tiles to the 50% and 25% thumbnail pyramids embedded in the `.czi`), crashed due to Java memory limits, and stripped physical pixel metadata.
* **Zeiss Color Space:** Zeiss AxioCam sensors natively record in BGR (Blue, Green, Red). Standard TIFFs expect RGB, causing tissue to render with flipped colors (red tissue appeared blue).

### The Final Solution: The Hybrid Pipeline
This script splits the workload to use the best tool for each specific job:
1. **Stage 1 (Python - Multithreaded Extraction):** Uses `aicspylibczi` and `concurrent.futures` to bypass Fiji's confusion. It rips only the pure 100% resolution tiles from the `.czi`, utilizes numpy to perform a BGR-to-RGB matrix flip, and writes a strict `TileConfiguration.txt` coordinate map.
2. **Stage 2 (Fiji - Phase Correlation):** Fiji reads the pure TIFFs and the coordinate map. It performs subpixel phase correlation to align the overlapping cellular structures and applies Linear Blending to mathematically erase the dark vignetting seams.
3. **Stage 3 (Python - Compression & Metadata):** Python intercepts Fiji's massive, uncompressed output. It strips out ghost dimensions, applies `zlib` compression (reducing file size by ~50%), formats the image into 512x512 chunks for smooth rendering, and wraps it in OME-XML metadata containing the exact physical micron measurements for QuPath analysis.

---

## 2. Environment Setup (`microscopy_env`)
This pipeline requires an isolated Conda environment to prevent dependency conflicts between Python libraries and the Java Virtual Machine.

**Create and activate the environment:**
```bash
conda create -n microscopy_env python=3.11
conda activate microscopy_env
```

**Install the required system dependencies:**
The underlying Bio-Formats engine requires Java to read proprietary microscope metadata.
```bash
conda install -c conda-forge openjdk
```

---

## 3. Libraries and Versions
The script relies on the following core libraries:

### Python Packages
Install via `pip`:
```bash
pip install aicspylibczi tifffile numpy
```
* `aicspylibczi`: Developed by the Allen Institute. Used for high-speed, headless reading of proprietary Zeiss CZI chunk logic.
* `tifffile`: Used for writing OME-compliant, BigTIFF formatted files with zlib compression.
* `numpy`: Used for multi-dimensional array manipulation (squeezing ghost dimensions and axis-swapping color channels).

### Standard Python Libraries (Built-in)
* `concurrent.futures` (ThreadPoolExecutor for multithreaded tile extraction)
* `subprocess` (For invoking the headless Fiji JVM)
* `os`, `glob`, `shutil`, `time`

### External Software
* **Fiji (ImageJ):** Must be downloaded and extracted locally. The script requires the exact path to the `ImageJ-linux64` executable. Used strictly for its `Grid/Collection stitching` algorithm (Linear Blending).

---

## Usage
1. Update the `FIJI_EXECUTABLE`, `INPUT_FOLDER`, and `OUTPUT_BASE_FOLDER` variables in the script.
2. Run the pipeline:
```bash
python stitch_script_extract_fiji.py
```
3. Drag the resulting `.ome.tif` files into QuPath and select "Yes" when prompted to Auto-Pyramidalize.