import os
import glob
import subprocess
import time
import shutil
import numpy as np
import tifffile
from aicspylibczi import CziFile

# =============================================================================
# GLOBAL VARIABLES
# =============================================================================
FIJI_EXECUTABLE = "/home/tiaan/Downloads/Fiji.app/ImageJ-linux64" 
INPUT_FOLDER = "/home/tiaan/Downloads/2026 rats/control/"
OUTPUT_BASE_FOLDER = "/home/tiaan/Downloads/2026 rats/stitched_output/perfect_pipelineP2/"
# =============================================================================
# Conclusion: Colours correct! Files compressed (sample file 385MB), timing added, but getting the "axes do not match stored shape" error

# microscopy_env) tiaan@fedora:/mnt/data/dev/personal/stitch_script$ python p2test.py 
# --- PERFECT EXTRACTION & STITCHING PIPELINE ---

# [1/49] Processing: R26_PRFG2-0017.czi
#   -> Stage 1: Extracting tiles and reading metadata...
#      (Completed in 4.2s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 69.8s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#   -> ERROR on R26_PRFG2-0017.czi: axes do not match stored shape

# [2/49] Processing: R30_HE-0002.czi
#   -> Stage 1: Extracting tiles and reading metadata...
#      (Completed in 3.3s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 50.2s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#   -> ERROR on R30_HE-0002.czi: axes do not match stored shape

# [3/49] Processing: R30_PRFG-0003.czi
#   -> Stage 1: Extracting tiles and reading metadata...
#      (Completed in 4.5s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 70.9s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#   -> ERROR on R30_PRFG-0003.czi: axes do not match stored shape

# [4/49] Processing: R30_PRFG-0004.czi
#   -> Stage 1: Extracting tiles and reading metadata...
#      (Completed in 5.1s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 69.2s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#   -> ERROR on R30_PRFG-0004.czi: axes do not match stored shape

# [5/49] Processing: R30_PRFG-0005.czi
#   -> Stage 1: Extracting tiles and reading metadata...
#      (Completed in 5.1s)
#   -> Stage 2: Fiji mathematical blending...
#      (Completed in 71.8s)
#   -> Stage 3: Zlib compression and OME metadata wrapping...
#   -> ERROR on R30_PRFG-0005.czi: axes do not match stored shape

# Ignore rhis prompt: ok and does it make sense to multithread or something to make it faster or is this the fastest it can gp?

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
            # --- STAGE 1: PYTHON EXTRACTION ---
            stage1_start = time.time()
            print("  -> Stage 1: Extracting tiles and reading metadata...")
            czi = CziFile(czi_path)
            
            if 'M' not in czi.dims:
                print("  -> Skipping: Not a mosaic.")
                shutil.rmtree(temp_dir)
                continue
                
            tile_count = czi.get_dims_shape()[0]['M'][1]
            
            # --- METADATA EXTRACTION ---
            # Zeiss stores scale in meters. We multiply by 1,000,000 to get microns.
            pixel_size_x, pixel_size_y = 1.0, 1.0
            try:
                x_node = czi.meta.find('.//Distance[@Id="X"]/Value')
                y_node = czi.meta.find('.//Distance[@Id="Y"]/Value')
                if x_node is not None: pixel_size_x = float(x_node.text) * 1e6
                if y_node is not None: pixel_size_y = float(y_node.text) * 1e6
            except Exception as e:
                print(f"     (Warning: Could not read physical pixel size, defaulting to 1.0. {e})")
            
            # Create coordinate map
            tile_conf_path = os.path.join(temp_dir, "TileConfiguration.txt")
            with open(tile_conf_path, "w") as f:
                f.write("dim = 2\n\n")
                
                for m in range(tile_count):
                    tile_data, _ = czi.read_image(M=m)
                    tile_data = np.squeeze(tile_data) 
                    
                    # --- BULLETPROOF COLOR FIX (BGR to RGB) ---
                    if len(tile_data.shape) == 3:
                        if tile_data.shape[0] == 3:      # If shape is (3, Y, X)
                            tile_data = np.moveaxis(tile_data, 0, -1)
                            tile_data = tile_data[..., ::-1] 
                        elif tile_data.shape[-1] == 3:   # If shape is (Y, X, 3)
                            tile_data = tile_data[..., ::-1] 
                            
                    tile_name = f"tile_{m:02d}.tiff"
                    tifffile.imwrite(os.path.join(temp_dir, tile_name), tile_data, photometric='rgb')
                    
                    bbox = czi.get_mosaic_tile_bounding_box(M=m)
                    f.write(f"{tile_name}; ; ({bbox.x}, {bbox.y})\n")
                    
            print(f"     (Completed in {time.time() - stage1_start:.1f}s)")
            
            # --- STAGE 2: FIJI PHASE CORRELATION STITCHING ---
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
                
            cmd = [FIJI_EXECUTABLE, "--headless", "--mem=10G", "-macro", macro_path]
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
            
            # Save it as a highly compressed, tiled, metadata-rich OME-TIFF
            tifffile.imwrite(
                final_ome_tiff_path,
                stitched_img,
                photometric='rgb',
                tile=(512, 512),
                compression='zlib',
                ome=True,
                metadata={
                    'axes': 'YXC',
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