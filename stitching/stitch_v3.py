"""
Batch stitching of Zeiss .czi brightfield tile scans into OME-TIFF (v3).

Pipeline per slide:
  1A. Read all tiles and estimate a flat-field illumination profile
      (per-pixel 95th percentile across tiles, Gaussian sigma 150).
  1B. Apply the correction and write the tiles plus a Fiji TileConfiguration.
  2.  Stitch in headless Fiji (Grid/Collection stitching, phase correlation,
      linear blending).
  3.  Write a tiled, zlib-compressed OME-TIFF with physical pixel sizes.

Usage:
  python stitch_v3.py --input <czi_folder> --output <output_folder> --fiji <fiji_launcher>
"""
import os
import glob
import argparse
import subprocess
import time
import shutil
import numpy as np
import tifffile
from aicspylibczi import CziFile
import concurrent.futures
from scipy.ndimage import gaussian_filter

# =============================================================================
# DEFAULT SETTINGS (can be overridden on the command line)
# =============================================================================
FIJI_EXECUTABLE = "/path/to/Fiji.app/ImageJ-linux64"
INPUT_FOLDER = "/path/to/czi_files/"
OUTPUT_BASE_FOLDER = "/path/to/stitched_output/"
FIJI_MEMORY = "16G"
# =============================================================================


def stitch_folder():
    if not os.path.exists(FIJI_EXECUTABLE):
        print(f"CRITICAL ERROR: Fiji not found at {FIJI_EXECUTABLE}")
        return

    os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)
    czi_files = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.czi")))
    total_files = len(czi_files)

    if total_files == 0:
        print(f"No CZI files found in {INPUT_FOLDER}")
        return

    print("--- CZI BRIGHTFIELD STITCHING (v3) ---")
    overall_start_time = time.time()

    for idx, czi_path in enumerate(czi_files, 1):
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        final_ome_tiff_path = os.path.join(OUTPUT_BASE_FOLDER, f"{base_name}.ome.tif")

        print(f"\n[{idx}/{total_files}] Processing: {filename}")
        file_start_time = time.time()

        if os.path.exists(final_ome_tiff_path):
            print("  -> Skipping: Output already exists.")
            continue

        temp_dir = os.path.join(OUTPUT_BASE_FOLDER, f"temp_{base_name}")
        os.makedirs(temp_dir, exist_ok=True)
        temp_fiji_out = os.path.join(temp_dir, "fiji_stitched.tiff")

        try:
            czi = CziFile(czi_path)
            if 'M' not in czi.dims:
                print("  -> Skipping: Not a mosaic.")
                shutil.rmtree(temp_dir)
                continue

            tile_count = czi.get_dims_shape()[0]['M'][1]

            # Physical pixel size (CZI stores metres; OME expects µm)
            pixel_size_x, pixel_size_y = 1.0, 1.0
            try:
                x_node = czi.meta.find('.//Distance[@Id="X"]/Value')
                y_node = czi.meta.find('.//Distance[@Id="Y"]/Value')
                if x_node is not None: pixel_size_x = float(x_node.text) * 1e6
                if y_node is not None: pixel_size_y = float(y_node.text) * 1e6
            except Exception as e:
                print(f"     (Warning: Could not read physical pixel size. {e})")

            # ---------------------------------------------------------
            # STAGE 1A: FLAT-FIELD ILLUMINATION PROFILE
            # ---------------------------------------------------------
            stage1a_start = time.time()
            print("  -> Stage 1A: Reading tiles and calculating illumination correction...")

            all_tiles = []
            is_rgb_global = False
            original_dtype = None

            for m in range(tile_count):
                t_data, _ = czi.read_image(M=m)
                t_data = np.squeeze(t_data)

                # Convert to YXC and Zeiss BGR to RGB
                if t_data.ndim == 3:
                    if t_data.shape[0] in [3, 4]:
                        t_data = np.moveaxis(t_data, 0, -1)
                    if t_data.shape[-1] == 3:
                        is_rgb_global = True
                        t_data = t_data[..., ::-1]

                if original_dtype is None:
                    original_dtype = t_data.dtype

                all_tiles.append(t_data.astype(np.float32))

            # The per-pixel 95th percentile across tiles is dominated by bright,
            # empty glass, which avoids the over-correction seen with the median.
            all_tiles = np.array(all_tiles)
            background_img = np.percentile(all_tiles, 95, axis=0)

            # A heavy blur keeps only the smooth illumination gradient
            print("     Smoothing illumination map...")
            flat_field = np.zeros_like(background_img)
            sigma_val = 150

            if background_img.ndim == 3:
                for c in range(background_img.shape[-1]):
                    flat_field[..., c] = gaussian_filter(background_img[..., c], sigma=sigma_val)
            else:
                flat_field = gaussian_filter(background_img, sigma=sigma_val)

            # Normalise to mean 1.0
            mean_ff = np.mean(flat_field)
            if mean_ff > 0:
                flat_field = flat_field / mean_ff
            else:
                flat_field = np.ones_like(flat_field)

            # Limit the correction to at most ~1.4x brightening to prevent blown-out edges
            flat_field = np.clip(flat_field, 0.7, 1.3)

            print(f"     (Completed in {time.time() - stage1a_start:.1f}s)")

            # ---------------------------------------------------------
            # STAGE 1B: APPLY CORRECTION AND WRITE TILES
            # ---------------------------------------------------------
            stage1b_start = time.time()
            print("  -> Stage 1B: Applying correction and writing tiles...")

            def process_and_save_tile(m):
                t_data = all_tiles[m]

                if is_rgb_global:
                    # Brightfield: multiplicative flat-field correction
                    corrected = t_data / flat_field
                else:
                    # Grayscale (polarised/darkfield): division would amplify noise
                    corrected = t_data

                # Restore the original bit depth
                if original_dtype.kind in ['u', 'i']:
                    max_val = np.iinfo(original_dtype).max
                    corrected = np.clip(corrected, 0, max_val)
                corrected = corrected.astype(original_dtype)

                photo_type = 'rgb' if is_rgb_global else 'minisblack'
                tile_name = f"tile_{m:02d}.tiff"
                tifffile.imwrite(os.path.join(temp_dir, tile_name), corrected, photometric=photo_type)

                # Stage coordinates used as Fiji's starting positions
                bbox = czi.get_mosaic_tile_bounding_box(M=m)
                return m, tile_name, bbox.x, bbox.y

            extracted_data = {}
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(process_and_save_tile, m) for m in range(tile_count)]
                for future in concurrent.futures.as_completed(futures):
                    m, t_name, x, y = future.result()
                    extracted_data[m] = (t_name, x, y)

            tile_conf_path = os.path.join(temp_dir, "TileConfiguration.txt")
            with open(tile_conf_path, "w") as f:
                f.write("dim = 2\n\n")
                for m in range(tile_count):
                    t_name, x, y = extracted_data[m]
                    f.write(f"{t_name}; ; ({x}, {y})\n")

            print(f"     (Completed in {time.time() - stage1b_start:.1f}s)")

            # ---------------------------------------------------------
            # STAGE 2: FIJI PHASE CORRELATION STITCHING
            # ---------------------------------------------------------
            stage2_start = time.time()
            print("  -> Stage 2: Fiji stitching and linear blending...")
            macro_path = os.path.join(temp_dir, "stitch.ijm")

            macro_code = f"""
            run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by TileConfiguration] directory=[{temp_dir}] layout_file=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
            saveAs("Tiff", "{temp_fiji_out}");
            run("Close All");
            run("Quit");
            """
            with open(macro_path, "w") as f:
                f.write(macro_code)

            cmd = [FIJI_EXECUTABLE, "--headless", f"--mem={FIJI_MEMORY}", "-macro", macro_path]
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            if not os.path.exists(temp_fiji_out):
                print("  -> Error: Fiji failed to output the stitched TIFF.")
                continue
            print(f"     (Completed in {time.time() - stage2_start:.1f}s)")

            # ---------------------------------------------------------
            # STAGE 3: COMPRESSION AND OME METADATA
            # ---------------------------------------------------------
            stage3_start = time.time()
            print("  -> Stage 3: Zlib compression and OME metadata...")

            stitched_img = tifffile.imread(temp_fiji_out)
            stitched_img = np.squeeze(stitched_img)

            is_rgb_stitched = False
            if stitched_img.ndim == 3:
                if stitched_img.shape[0] == 3:
                    stitched_img = np.moveaxis(stitched_img, 0, -1)
                if stitched_img.shape[-1] == 3:
                    is_rgb_stitched = True

            photo_stitched = 'rgb' if is_rgb_stitched else 'minisblack'

            tifffile.imwrite(
                final_ome_tiff_path,
                stitched_img,
                photometric=photo_stitched,
                tile=(512, 512),
                compression='zlib',
                ome=True,
                metadata={
                    'axes': 'YXC' if is_rgb_stitched else 'YX',
                    'PhysicalSizeX': pixel_size_x,
                    'PhysicalSizeXUnit': 'µm',
                    'PhysicalSizeY': pixel_size_y,
                    'PhysicalSizeYUnit': 'µm',
                }
            )
            print(f"     (Completed in {time.time() - stage3_start:.1f}s)")
            print(f"  -> SUCCESS: Saved {base_name}.ome.tif (Total file time: {time.time() - file_start_time:.1f}s)")

        except Exception as e:
            print(f"  -> ERROR on {filename}: {e}")

        finally:
            # STAGE 4: CLEANUP
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    print("\n--- BATCH STITCHING COMPLETE ---")
    print(f"Grand Total Processing Time: {(time.time() - overall_start_time) / 60:.2f} minutes")


def parse_args():
    parser = argparse.ArgumentParser(description="Stitch Zeiss .czi brightfield tile scans into OME-TIFF (v3).")
    parser.add_argument("--input", default=INPUT_FOLDER, help="Folder containing the .czi files.")
    parser.add_argument("--output", default=OUTPUT_BASE_FOLDER, help="Folder for the stitched .ome.tif files.")
    parser.add_argument("--fiji", default=FIJI_EXECUTABLE, help="Path to the Fiji launcher (e.g. ImageJ-linux64).")
    parser.add_argument("--mem", default=FIJI_MEMORY, help="Maximum memory for Fiji (default: %(default)s).")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    INPUT_FOLDER = args.input
    OUTPUT_BASE_FOLDER = args.output
    FIJI_EXECUTABLE = args.fiji
    FIJI_MEMORY = args.mem
    stitch_folder()
