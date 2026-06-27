import os
import glob
import subprocess
import time
import shutil
import numpy as np
import tifffile
from aicspylibczi import CziFile
import concurrent.futures

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
INPUT_FOLDER = "/run/media/tiaan/ExternalSSD/bella_msc/allrats/"
OUTPUT_BASE_FOLDER = "/run/media/tiaan/ExternalSSD/bella_msc/stitchedv2/"
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
            # --- STAGE 1: MULTITHREADED PYTHON EXTRACTION ---
            stage1_start = time.time()
            print("  -> Stage 1: Extracting tiles and reading metadata...")
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
            
            # --- THE MULTITHREADING FUNCTION ---
            def process_single_tile(m):
                # 1. Read the tile
                tile_data, _ = czi.read_image(M=m)
                tile_data = np.squeeze(tile_data) # Removes empty dimensions (e.g., T=1, Z=1)                     
                        
                # 2. Bulletproof Color Handling
                is_rgb = False
                if tile_data.ndim == 3:
                    # If aicspylibczi gives us (Color, Y, X), push Color to the back -> (Y, X, Color)
                    if tile_data.shape[0] in [3, 4]:  
                        tile_data = np.moveaxis(tile_data, 0, -1)
                    
                    # Check if it has exactly 3 color channels
                    if tile_data.shape[-1] == 3:
                        is_rgb = True
                        # FIX BGR TO RGB:
                        # Zeiss typically saves as BGR. We flip the last axis to make it RGB.
                        # If your colors turn out wrong, comment out the line below.
                        tile_data = tile_data[..., ::-1] 
                                            
                # 3. Determine photometric type (prevents grayscale polarized images from crashing)
                photo_type = 'rgb' if is_rgb else 'minisblack'

                # 4. Save to disk
                tile_name = f"tile_{m:02d}.tiff"
                tifffile.imwrite(os.path.join(temp_dir, tile_name), tile_data, photometric=photo_type)
                
                # 5. Grab coordinates
                bbox = czi.get_mosaic_tile_bounding_box(M=m)
                return m, tile_name, bbox.x, bbox.y
            
            # Execute the tile processing across available CPU cores
            extracted_data = {}
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(process_single_tile, m) for m in range(tile_count)]
                for future in concurrent.futures.as_completed(futures):
                    m, t_name, x, y = future.result()
                    extracted_data[m] = (t_name, x, y)
                    
            # Write the Fiji coordinate map in the correct sequential order
            tile_conf_path = os.path.join(temp_dir, "TileConfiguration.txt")
            with open(tile_conf_path, "w") as f:
                f.write("dim = 2\n\n")
                for m in range(tile_count):
                    t_name, x, y = extracted_data[m]
                    f.write(f"{t_name}; ; ({x}, {y})\n")
                    
            print(f"     (Completed in {time.time() - stage1_start:.1f}s)")
            
            # --- STAGE 2: FIJI PHASE CORRELATION STITCHING ---
            stage2_start = time.time()
            print("  -> Stage 2: Fiji mathematical blending...")
            macro_path = os.path.join(temp_dir, "stitch.ijm")
            
            # Note: I increased memory to 16G if your system allows it. 10G is low for 5x5 TIFFs.
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
            
            # --- STAGE 3: COMPRESSION & METADATA INJECTION ---
            stage3_start = time.time()
            print("  -> Stage 3: Zlib compression and OME metadata wrapping...")
            
            # Read Fiji's uncompressed output
            stitched_img = tifffile.imread(temp_fiji_out)
            stitched_img = np.squeeze(stitched_img)
            
            # Safely handle stitched dimensions
            is_rgb_stitched = False
            if stitched_img.ndim == 3:
                # If Fiji output (3, Y, X), move to (Y, X, 3)
                if stitched_img.shape[0] == 3:
                    stitched_img = np.moveaxis(stitched_img, 0, -1)
                
                if stitched_img.shape[-1] == 3:
                    is_rgb_stitched = True

            photo_stitched = 'rgb' if is_rgb_stitched else 'minisblack'
            
            # Save it as a highly compressed, tiled, metadata-rich OME-TIFF
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