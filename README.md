# CZI Brightfield Stitching

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A hybrid Python/Fiji pipeline for batch processing, seamlessly stitching, illumination-correcting and compressing Zeiss `.czi` brightfield microscopy tile scans into QuPath-ready `.ome.tif` files, followed by a QuPath script for automated tissue masking.

## Contents
- [Overview](#overview)
- [Repository Structure](#repository-structure)
- [Method](#method)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage: Phase 1, Stitching](#usage-phase-1-stitching)
- [Usage: Phase 2, Tissue Masking in QuPath](#usage-phase-2-tissue-masking-in-qupath)
- [Troubleshooting](#troubleshooting)
- [Citation](#citation)
- [License](#license)
- [Legacy Usage (v0.1.0, No Longer Applicable)](#legacy-usage-v010-no-longer-applicable)

---

## Overview
A Zeiss slide scanner records a slide as a grid of overlapping images (tiles) stored together in a single `.czi` file. This pipeline converts each `.czi` file into one seamless, compressed image of the whole slide and then outlines the tissue for quantitative analysis.

The workflow has two phases:

1. **Phase 1: Stitching (Python and Fiji, fully automated).** For every `.czi` file in a folder, the tiles are extracted, corrected for uneven illumination, aligned by phase correlation, blended, and saved as a tiled, compressed `.ome.tif`.
2. **Phase 2: Tissue masking (QuPath).** A QuPath script outlines the tissue in each stitched image and excludes the black padding left around the edges of the stitched canvas.

Terminology:
* **`.czi`**: Zeiss's proprietary microscope image format.
* **`.ome.tif`**: An open, standard microscopy image format that stores the physical pixel size (µm), so measurements in QuPath are calibrated.
* **Fiji**: An open-source image analysis distribution of ImageJ. Phase 1 runs it headless in the background, so it is never opened manually.
* **QuPath**: Open-source software for viewing and analysing whole-slide images.

---

## Repository Structure

```
czi-brightfield-stitching/
├── stitching/
│   ├── stitch_v3.py        Phase 1 stitching (default)
│   └── stitch_v2.py        Phase 1 stitching, alternative illumination correction
├── qupath/
│   └── tissue_mask.groovy  Phase 2 tissue masking
├── archive/                Earlier development versions (see archive/README.md)
├── environment.yml         Conda environment (pinned versions)
├── requirements.txt        pip requirements (pinned versions)
├── CITATION.cff
└── LICENSE
```

| Script | Use |
|---|---|
| `stitching/stitch_v3.py` | **Default.** Illumination profile from the per-pixel 95th percentile across tiles. |
| `stitching/stitch_v2.py` | Alternative for slides where the v3 correction makes the seams too light. Illumination profile from the per-pixel median. |
| `qupath/tissue_mask.groovy` | Phase 2 tissue masking in QuPath. |

---

## Method
This pipeline was developed to solve the specific mathematical and software challenges of handling large brightfield histology slides (e.g., H&E, Masson's Trichrome, Picrosirius Red/Fast Green).

### Challenges with standard tools
* **Flat Stitching:** Relying strictly on the microscope's mechanical stage coordinates left jagged edges and misaligned cells due to mechanical drift.
* **ASHLAR:** Failed on brightfield images. ASHLAR uses phase correlation optimized for dark backgrounds (fluorescence). The bright white glass and dark optical vignetting in brightfield slides caused the algorithm to scatter the tiles.
* **Headless Fiji (Bio-Formats):** Trying to run Fiji's Grid/Collection stitching directly on `.czi` files caused "Ghosting" (Fiji accidentally tried to stitch the 100% resolution tiles to the 50% and 25% thumbnail pyramids embedded in the `.czi`), crashed due to Java memory limits, and stripped physical pixel metadata.
* **Zeiss Color Space:** Zeiss AxioCam sensors natively record in BGR (Blue, Green, Red). Standard TIFFs expect RGB, causing tissue to render with flipped colors (red tissue appeared blue).
* **Uneven Illumination:** Brightfield tiles are brighter in the centre than at the edges (vignetting), producing uneven brightness across the stitched slide. A flat-field profile estimated from all tiles of a slide is divided out of each tile. A median-based profile (v2) over-corrected some slides, so v3 estimates the profile from the per-pixel 95th percentile, which is dominated by empty glass, with a much stronger blur to suppress tissue structure.

### The Hybrid Pipeline (Phase 1)
The workload is split to use the best tool for each specific job:
1. **Stage 1 (Python - Multithreaded Extraction):** Uses `aicspylibczi` and `concurrent.futures` to bypass Fiji's confusion. It rips only the pure 100% resolution tiles from the `.czi`, utilizes numpy to perform a BGR-to-RGB matrix flip, and writes a strict `TileConfiguration.txt` coordinate map.
   * **Stage 1A – Flat-field illumination profile:** All tiles are loaded and combined into a per-pixel background estimate (v3: 95th percentile, Gaussian sigma 150; v2: median, Gaussian sigma 30). The profile is normalised to a mean of 1.0 and clipped to 0.7–1.3, limiting any brightening to approximately 1.4x to prevent blown-out edges.
   * **Stage 1B – Correction and export:** Each RGB (brightfield) tile is divided by the profile, restored to its original bit depth and written to disk in parallel. Grayscale tiles (polarised/darkfield) are not corrected, since division would amplify noise.
2. **Stage 2 (Fiji - Phase Correlation):** Fiji reads the pure TIFFs and the coordinate map. It performs subpixel phase correlation to align the overlapping cellular structures and applies Linear Blending to mathematically erase the dark vignetting seams. Fiji is allocated 16 GB of memory by default.
3. **Stage 3 (Python - Compression & Metadata):** Python intercepts Fiji's massive, uncompressed output. It strips out ghost dimensions, applies `zlib` compression (reducing file size by ~50%), formats the image into 512x512 chunks for smooth rendering, and wraps it in OME-XML metadata containing the exact physical micron measurements for QuPath analysis.
4. **Stage 4 (Cleanup):** The temporary tile folder (`temp_<slide name>`) is deleted, whether the slide succeeded or failed.

### Tissue Masking (Phase 2)
The fused image contains black padding along its edges wherever no tile covers the canvas. Because a single brightness threshold would classify this dark padding as tissue, `qupath/tissue_mask.groovy` uses two saved thresholders:
1. **`Black_Padding`** detects near-black pixels and assigns them to `Artifact`.
2. **`Brightfield_Mask`** detects pixels darker than the glass background and assigns them to `Tissue`, discarding objects smaller than 10,000.
3. The padding, expanded by a 2-pixel buffer to include anti-aliased border pixels, is geometrically subtracted from the tissue.
4. All other annotations are removed, and the trimmed `Tissue` annotations are added and locked.

### Version History

| Date | Version | Change | Outcome |
|---|---|---|---|
| Mar 2026 | `archive/stitch_scriptv1.py` | `aicspylibczi.read_mosaic` placing tiles by stage coordinates only. | Misaligned tiles, swapped colours. |
| Mar–Apr 2026 | ASHLAR | ASHLAR command-line stitcher. | Tiles scattered on brightfield images. |
| Apr 2026 | `archive/stitch_script_fiji.py` | Fiji Grid/Collection stitching reading `.czi` directly. | Ghosting from embedded pyramid levels, memory failures. |
| Apr 2026 | `archive/stitch_v1.py` | Hybrid pipeline (v0.1.0): Python extraction, Fiji stitching, Python compression. | Working. |
| Jun–Jul 2026 | `stitching/stitch_v2.py` | Flat-field illumination correction (median), clipping, grayscale support. | Working. |
| Jul 2026 | `qupath/tissue_mask.groovy` | Dual-threshold QuPath tissue masking. | Working. |
| Sep 2026 | `stitching/stitch_v3.py` | Illumination profile from the 95th percentile, blur sigma 30 → 150. | Working. Default. |

---

## Requirements

### Hardware
* **Operating system:** Linux (developed and tested on Fedora). Windows and macOS are untested.
* **Memory:** 32 GB RAM recommended. Fiji is allocated up to 16 GB (adjustable with `--mem`), and the tiles of the current slide are held in memory by Python at the same time.
* **Disk space:** 200–450 MB per stitched slide, plus 1–2 GB of temporary space while a slide is processed.

### Software
The pipeline relies on the following core libraries.

**Python packages:**
* `aicspylibczi`: Developed by the Allen Institute. Used for high-speed, headless reading of proprietary Zeiss CZI chunk logic.
* `tifffile`: Used for writing OME-compliant, BigTIFF formatted files with zlib compression.
* `numpy`: Used for multi-dimensional array manipulation (squeezing ghost dimensions and axis-swapping color channels).
* `scipy`: `gaussian_filter` smooths the flat-field illumination profile.

**Standard Python libraries (built-in):**
* `concurrent.futures` (ThreadPoolExecutor for multithreaded tile extraction)
* `subprocess` (For invoking the headless Fiji JVM)
* `argparse`, `os`, `glob`, `shutil`, `time`

**External software:**
* **Fiji (ImageJ):** Used strictly for its `Grid/Collection stitching` algorithm (Linear Blending). The scripts require the path to the `ImageJ-linux64` launcher.
* **QuPath:** Used to view the stitched images and run the Phase 2 tissue masking script (QuPath 0.4 or newer).

### Tested Versions

| Software | Version |
|---|---|
| Python | 3.11.15 |
| aicspylibczi | 3.3.1 |
| tifffile | 2026.3.3 |
| numpy | 2.4.4 |
| scipy | 1.17.1 |
| Fiji | 2.16 (ImageJ 1.54p, Stitching plugin 3.1.9) |
| QuPath | 0.7.0 |

---

## Installation
Setup is required once per computer. All commands are entered in a terminal, one line at a time.

### 1. Install conda
Conda creates an isolated environment so the pipeline's Python packages do not conflict with other software. Check for an existing installation:
```bash
conda --version
```
If no version is printed, install Miniforge:
```bash
curl -L -O "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh"
bash Miniforge3-$(uname)-$(uname -m).sh
```
Accept the licence, keep the default install location and answer `yes` to initialise conda. Open a new terminal before continuing.

### 2. Download the code
Download the latest release from the [Releases page](https://github.com/tiaanjvr/czi-brightfield-stitching/releases) and extract it, or clone the repository:
```bash
git clone https://github.com/tiaanjvr/czi-brightfield-stitching.git
cd czi-brightfield-stitching
```

### 3. Create the Python environment
From inside the project folder:
```bash
conda env create -f environment.yml
conda activate microscopy_env
```
This installs Python 3.11 and the tested package versions. After activation, the terminal prompt begins with `(microscopy_env)`. To verify the installation:
```bash
python -c "import aicspylibczi, tifffile, numpy, scipy; print('OK')"
```

Equivalent manual setup:
```bash
conda create -n microscopy_env python=3.11
conda activate microscopy_env
pip install -r requirements.txt
```

### 4. Install Fiji
1. Download Fiji for Linux from [fiji.sc](https://fiji.sc/) and extract the `.zip` file to a permanent location.
2. Locate the launcher inside the extracted folder: `ImageJ-linux64` (tested). Recent Fiji releases also include `fiji-linux-x64`.
3. Note the launcher's full path, for example `/opt/Fiji.app/ImageJ-linux64`. Dragging the file into a terminal window prints its path.

The Grid/Collection stitching plugin is included with Fiji. No additional plugins are required.

### 5. Install QuPath
Download QuPath from [qupath.github.io](https://qupath.github.io/) (version 0.4 or newer; tested with 0.7.0).

---

## Usage: Phase 1, Stitching

### Input
All `.czi` files must be placed directly in one folder. Sub-folders are not searched, and the extension must be lowercase `.czi`. Files that are single images rather than tile mosaics are skipped.

### Running
```bash
conda activate microscopy_env
cd czi-brightfield-stitching
python stitching/stitch_v3.py \
    --input  /data/slides/czi \
    --output /data/slides/stitched \
    --fiji   /opt/Fiji.app/ImageJ-linux64
```

| Argument | Description |
|---|---|
| `--input` | Folder containing the `.czi` files. |
| `--output` | Folder for the stitched `.ome.tif` files. Created if it does not exist. |
| `--fiji` | Full path to the Fiji launcher. |
| `--mem` | Maximum memory for Fiji (default `16G`). On computers with less than 32 GB of RAM, use a lower value such as `10G`. |

The defaults for these arguments can also be set in the `DEFAULT SETTINGS` block at the top of each script, after which the script runs without arguments.

To use the v2 illumination correction for slides where v3 makes the seams too light, run `stitching/stitch_v2.py` with the same arguments. Both versions produce identically named files, so use a separate `--output` folder for each.

### Output
Progress is reported for each slide:
```
--- CZI BRIGHTFIELD STITCHING (v3) ---

[1/49] Processing: R30_HE-0002.czi
  -> Stage 1A: Reading tiles and calculating illumination correction...
     Smoothing illumination map...
     (Completed in ...s)
  -> Stage 1B: Applying correction and writing tiles...
     (Completed in ...s)
  -> Stage 2: Fiji stitching and linear blending...
     (Completed in ...s)
  -> Stage 3: Zlib compression and OME metadata...
     (Completed in ...s)
  -> SUCCESS: Saved R30_HE-0002.ome.tif (Total file time: ...s)
...
--- BATCH STITCHING COMPLETE ---
Grand Total Processing Time: ... minutes
```
* One `<slide name>.ome.tif` is written per `.czi` file. A `temp_<slide name>` folder exists in the output folder while a slide is processed and is removed afterwards.
* Stage 2 (Fiji) is the longest step and produces no output while it runs. Processing took 1–1.5 minutes per 25-tile slide with v1. The illumination correction in v2 and v3 adds to this.
* A failure on one slide is reported as an `ERROR` line, and processing continues with the next slide.

### Stopping and resuming
* **Ctrl + C** stops the run (**Ctrl + \\** if it does not respond).
* Re-running the same command resumes the batch: slides that already have an `.ome.tif` in the output folder are skipped.
* If a run is stopped during Stage 3, the partially written `.ome.tif` for that slide must be deleted before resuming. Otherwise that slide is skipped.
* To reprocess a slide, delete its `.ome.tif` and run the script again.

### Viewing
Drag the resulting `.ome.tif` files into QuPath and select "Yes" when prompted to Auto-Pyramidalize.

---

## Usage: Phase 2, Tissue Masking in QuPath
The script creates one locked `Tissue` annotation per image, with the stitching padding removed.

> **Warning:** The script deletes all existing annotations on each image it is run on.

### 1. Create a project
1. In QuPath, create a new project in an empty folder (*File → Project → Create project*).
2. Drag the stitched `.ome.tif` files into the QuPath window. Choose **Yes** when prompted to generate pyramids.
3. Set the image type to **Brightfield**.

### 2. Create the thresholders
Two pixel thresholders named `Black_Padding` and `Brightfield_Mask` must be saved in the project. Thresholders are stored per project in `classifiers/pixel_classifiers/`, so they can be copied between projects.

The classes `Artifact` and `Tissue` must exist in the class list (*Annotations* tab).

Open an image and select *Classify → Pixel classification → Create thresholder*.

**`Black_Padding`** (black padding):

| Setting | Value |
|---|---|
| Resolution | Full (1.10 µm/px) |
| Channel | Average channels |
| Smoothing sigma | 0 |
| Threshold | 10 |
| Above threshold | *(none)* |
| Below threshold | `Artifact` |
| Region | Everywhere |

**`Brightfield_Mask`** (tissue):

| Setting | Value |
|---|---|
| Resolution | Very high (2.19 µm/px) |
| Channel | Average channels |
| Smoothing sigma | 0.5 |
| Threshold | 1700 |
| Above threshold | *(none)* |
| Below threshold | `Tissue` |
| Create objects | Minimum object size 10000, minimum hole size 0 |

Enter each name and click **Save**.

Tissue is darker than the glass background, so pixels below the threshold are classified as tissue. If background is included in the mask, lower the `Brightfield_Mask` threshold. If pale tissue is excluded, raise it. The resolutions and thresholds listed were determined for the slides used in development.

### 3. Run the script
1. Open *Automate → Script editor*, then *File → Open* and select `qupath/tissue_mask.groovy`.
2. With an image open, select *Run → Run* (**Ctrl + R**). On success the log ends with `Tissue masking complete.`
3. To process every image, select *Run → Run for project*.

---

## Troubleshooting

### Phase 1

| Message or symptom | Cause | Solution |
|---|---|---|
| `CRITICAL ERROR: Fiji not found at ...` | Incorrect `--fiji` path. | Provide the full path including the launcher file name. |
| `No CZI files found in ...` | No `.czi` files directly in `--input`. | Check the path, sub-folders and the lowercase `.czi` extension. |
| `ModuleNotFoundError` | Environment not active or incomplete. | `conda activate microscopy_env`, then `pip install -r requirements.txt` if needed. |
| `Skipping: Not a mosaic.` | The `.czi` contains a single image. | None required. |
| `Skipping: Output already exists.` | The slide has already been processed. | Delete the `.ome.tif` to reprocess it. |
| `ERROR on <file>: Command '[...]' returned non-zero exit status ...` | Fiji failed, usually from insufficient memory. | Close other programs, lower `--mem`, and check free disk space. |
| `Error: Fiji failed to output the stitched TIFF.` | Fiji produced no image. | As above. |
| `Permission denied` when Fiji starts | The launcher is not executable. | `chmod +x /path/to/Fiji.app/ImageJ-linux64` |
| Seams or tile edges too light | The v3 illumination correction does not suit the slide. | Process the slide with `stitching/stitch_v2.py`. |
| Uneven brightness or blown-out edges | Illumination correction strength. | Adjust `sigma_val` and the `np.clip(flat_field, 0.7, 1.3)` limits in the script. |
| Colours swapped (red appears blue) | Camera channel order differs from Zeiss BGR. | Remove the `t_data = t_data[..., ::-1]` channel flip for that camera. |
| `temp_...` folders remain in the output folder | The run was terminated forcibly. | Delete them. |

### Phase 2

| Message or symptom | Cause | Solution |
|---|---|---|
| `No tissue found! ...` | `Brightfield_Mask` does not assign `Tissue`, or the threshold is unsuitable. | Check the thresholder's *Below threshold* class and threshold value. |
| Classifier not found | Thresholders missing from the project or misnamed. | Create them with the exact names `Black_Padding` and `Brightfield_Mask`. |
| Mask includes the black padding | `Black_Padding` does not assign `Artifact`. | Check the thresholder's *Below threshold* class. |

---

## Citation
If you use this software, please cite it. Citation metadata is provided in [`CITATION.cff`](CITATION.cff), and GitHub's **Cite this repository** button (repository sidebar) exports it as APA or BibTeX.

> JvR, T., & Lohse, I. (2026). *CZI Brightfield Stitching* (Version 1.0.0) [Computer software]. https://github.com/tiaanjvr/czi-brightfield-stitching

---

## License
Released under the [MIT License](LICENSE).

---

## Legacy Usage (v0.1.0, No Longer Applicable)
The instructions below applied to the original single-script version. That script was renamed to `archive/stitch_v1.py` and has been superseded by `stitching/stitch_v3.py`. They are retained for reference.

1. Update the `FIJI_EXECUTABLE`, `INPUT_FOLDER`, and `OUTPUT_BASE_FOLDER` variables in the script.
2. Run the pipeline:
```bash
python stitch_script_extract_fiji.py
```
3. Drag the resulting `.ome.tif` files into QuPath and select "Yes" when prompted to Auto-Pyramidalize.

**Environment setup (original):** The original README installed Java into the environment with `conda install -c conda-forge openjdk`, since the Bio-Formats engine used by earlier approaches requires Java. The current scripts read `.czi` files with `aicspylibczi` and Fiji includes its own Java runtime, so this step is no longer required.
