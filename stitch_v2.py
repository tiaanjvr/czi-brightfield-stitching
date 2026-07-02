import os
import glob
import subprocess
import time
import shutil
import numpy as np
import tifffile
from aicspylibczi import CziFile
import concurrent.futures
from scipy.ndimage import gaussian_filter

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
INPUT_FOLDER = "/run/media/tiaan/ExternalSSD/bella_msc/allrats/"
OUTPUT_BASE_FOLDER = "/run/media/tiaan/ExternalSSD/bella_msc/stitchedv2_1/"
# =============================================================================

def perfect_pipeline_stitch():
    if not os.path.exists(FIJI_EXECUTABLE):
        print(f"CRITICAL ERROR: Fiji not found at {FIJI_EXECUTABLE}")
        return

    os.makedirs(OUTPUT_BASE_FOLDER, exist_ok=True)
    czi_files = sorted(glob.glob(os.path.join(INPUT_FOLDER, "*.czi")))
    total_files = len(czi_files)
    
    if total_files == 0:
        print("No CZI files found.")
        return

    print("--- PERFECT EXTRACTION & STITCHING PIPELINE ---")
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
            
            # Extract Metadata
            pixel_size_x, pixel_size_y = 1.0, 1.0
            try:
                x_node = czi.meta.find('.//Distance[@Id="X"]/Value')
                y_node = czi.meta.find('.//Distance[@Id="Y"]/Value')
                if x_node is not None: pixel_size_x = float(x_node.text) * 1e6
                if y_node is not None: pixel_size_y = float(y_node.text) * 1e6
            except Exception as e:
                print(f"     (Warning: Could not read physical pixel size. {e})")

# ---------------------------------------------------------
            # STAGE 1A: CALCULATE FLAT-FIELD ILLUMINATION PROFILE
            # ---------------------------------------------------------
            stage1a_start = time.time()
            print("  -> Stage 1A: Reading tiles and calculating Illumination Correction...")
            
            all_tiles = []
            is_rgb_global = False
            original_dtype = None

            for m in range(tile_count):
                t_data, _ = czi.read_image(M=m)
                t_data = np.squeeze(t_data)
                
                # Standardize colors safely
                if t_data.ndim == 3:
                    if t_data.shape[0] in [3, 4]:
                        t_data = np.moveaxis(t_data, 0, -1)
                    if t_data.shape[-1] == 3:
                        is_rgb_global = True
                        t_data = t_data[..., ::-1] # BGR to RGB
                
                if original_dtype is None:
                    original_dtype = t_data.dtype
                    
                all_tiles.append(t_data.astype(np.float32))

            # Stack into numpy array and calculate the median image
            all_tiles = np.array(all_tiles)
            median_img = np.median(all_tiles, axis=0)
            
            # Apply heavy Gaussian blur to leave ONLY the lighting gradient
            print("     Smoothing illumination map...")
            flat_field = np.zeros_like(median_img)
            sigma_val = 30 # Blur intensity
            
            if median_img.ndim == 3:
                for c in range(median_img.shape[-1]):
                    flat_field[..., c] = gaussian_filter(median_img[..., c], sigma=sigma_val)
            else:
                flat_field = gaussian_filter(median_img, sigma=sigma_val)
                
            # Normalize flat field (mean = 1.0)
            mean_ff = np.mean(flat_field)
            if mean_ff > 0:
                flat_field = flat_field / mean_ff
            else:
                flat_field = np.ones_like(flat_field)
                
            # --- THE QUICK FIX: CLIP TO PREVENT EDGE BLOWOUT ---
            # We prevent the flat field from dropping below 0.7, meaning the script 
            # is mathematically prevented from boosting any pixel's brightness by more than ~1.4x.
            flat_field = np.clip(flat_field, 0.7, 1.3)
                
            print(f"     (Completed in {time.time() - stage1a_start:.1f}s)")

            # ---------------------------------------------------------
            # STAGE 1B: APPLY CORRECTION & MULTITHREADED EXTRACTION
            # ---------------------------------------------------------
            stage1b_start = time.time()
            print("  -> Stage 1B: Applying correction and writing tiles...")
            
            def process_and_save_tile(m):
                t_data = all_tiles[m]
                
                # --- THE QUICK FIX: MODALITY CHECK ---
                if is_rgb_global:
                    # Brightfield (PR/FG): Apply Multiplicative Correction
                    corrected = t_data / flat_field
                else:
                    # Polarized (Grayscale/Darkfield): Skip division to avoid noise explosion
                    corrected = t_data
                
                # Restore to original bit-depth safely
                if original_dtype.kind in ['u', 'i']:
                    max_val = np.iinfo(original_dtype).max
                    corrected = np.clip(corrected, 0, max_val)
                corrected = corrected.astype(original_dtype)
                
                # Save to disk
                photo_type = 'rgb' if is_rgb_global else 'minisblack'
                tile_name = f"tile_{m:02d}.tiff"
                tifffile.imwrite(os.path.join(temp_dir, tile_name), corrected, photometric=photo_type)
                
                # Grab coordinates
                bbox = czi.get_mosaic_tile_bounding_box(M=m)
                return m, tile_name, bbox.x, bbox.y

            extracted_data = {}
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(process_and_save_tile, m) for m in range(tile_count)]
                for future in concurrent.futures.as_completed(futures):
                    m, t_name, x, y = future.result()
                    extracted_data[m] = (t_name, x, y)
                    
            # Write Fiji coordinate map
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
            print("  -> Stage 2: Fiji mathematical blending...")
            macro_path = os.path.join(temp_dir, "stitch.ijm")
            
            macro_code = f"""
            run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by TileConfiguration] directory=[{temp_dir}] layout_file=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
            saveAs("Tiff", "{temp_fiji_out}");
            run("Close All");
            run("Quit");
            """
            with open(macro_path, "w") as f:
                f.write(macro_code)
                
            cmd = [FIJI_EXECUTABLE, "--headless", "--mem=16G", "-macro", macro_path]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if not os.path.exists(temp_fiji_out):
                print("  -> Error: Fiji failed to output the stitched TIFF.")
                continue
            print(f"     (Completed in {time.time() - stage2_start:.1f}s)")
            
            # ---------------------------------------------------------
            # STAGE 3: COMPRESSION & METADATA INJECTION
            # ---------------------------------------------------------
            stage3_start = time.time()
            print("  -> Stage 3: Zlib compression and OME metadata wrapping...")
            
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
            print(f"  -> SUCCESS: Stitched and saved {base_name}.ome.tif (Total file time: {time.time() - file_start_time:.1f}s)")
                
        except Exception as e:
            print(f"  -> ERROR on {filename}: {e}")
            
        finally:
            # --- STAGE 4: CLEANUP ---
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    print("\n--- BATCH STITCHING COMPLETE ---")
    print(f"Grand Total Processing Time: {(time.time() - overall_start_time) / 60:.2f} minutes")

if __name__ == "__main__":
    perfect_pipeline_stitch()