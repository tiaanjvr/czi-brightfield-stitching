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
OUTPUT_BASE_FOLDER = "/home/tiaan/Downloads/2026 rats/stitched_output/perfect_pipelineP1/"
# =============================================================================
# Conclusion: The blue output should be red, files uncompressed (sample file 663MB), no timing

# Output: (microscopy_env) tiaan@fedora:/mnt/data/dev/personal/stitch_script$ python p1test.py 
# --- PERFECT EXTRACTION & STITCHING PIPELINE ---

# [1/49] Processing: R26_PRFG2-0017.czi
#   -> Extracting raw 100% tiles and coordinates...
#   -> Raw data secured. Handing over to Fiji for seamless blending...
#   -> Success: Flawless stitch saved to R26_PRFG2-0017.tiff

# [2/49] Processing: R30_HE-0002.czi
#   -> Extracting raw 100% tiles and coordinates...
#   -> Raw data secured. Handing over to Fiji for seamless blending...
#   -> Success: Flawless stitch saved to R30_HE-0002.tiff

# [3/49] Processing: R30_PRFG-0003.czi
#   -> Extracting raw 100% tiles and coordinates...
#   -> Raw data secured. Handing over to Fiji for seamless blending...
#   -> Success: Flawless stitch saved to R30_PRFG-0003.tiff

# [4/49] Processing: R30_PRFG-0004.czi
#   -> Extracting raw 100% tiles and coordinates...
#   -> Raw data secured. Handing over to Fiji for seamless blending...
#   -> Success: Flawless stitch saved to R30_PRFG-0004.tiff

# [5/49] Processing: R30_PRFG-0005.czi
#   -> Extracting raw 100% tiles and coordinates...
#   -> Raw data secured. Handing over to Fiji for seamless blending...
#   -> Success: Flawless stitch saved to R30_PRFG-0005.tiff

# Ignore rhis prompt: Ok cool the stitching finally works! 1. The red appears blue again 2. 
# The final file is 400-700MB, can it be compressed? 3. Add timing output 4. 
# Do I need to add anything else (is it possible to add metadata without crashing the program)?

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
    
    for idx, czi_path in enumerate(czi_files, 1):
        filename = os.path.basename(czi_path)
        base_name = os.path.splitext(filename)[0]
        out_tiff_path = os.path.join(OUTPUT_BASE_FOLDER, f"{base_name}.tiff")
        
        print(f"\n[{idx}/{total_files}] Processing: {filename}")
        
        if os.path.exists(out_tiff_path):
            print("  -> Skipping: Output already exists.")
            continue

        temp_dir = os.path.join(OUTPUT_BASE_FOLDER, f"temp_{base_name}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # --- STAGE 1: PYTHON EXTRACTION ---
            print("  -> Extracting raw 100% tiles and coordinates...")
            czi = CziFile(czi_path)
            
            if 'M' not in czi.dims:
                print("  -> Skipping: Not a mosaic.")
                shutil.rmtree(temp_dir)
                continue
                
            tile_count = czi.get_dims_shape()[0]['M'][1]
            
            # Create the exact coordinate map Fiji needs
            tile_conf_path = os.path.join(temp_dir, "TileConfiguration.txt")
            with open(tile_conf_path, "w") as f:
                f.write("dim = 2\n\n")
                
                for m in range(tile_count):
                    # 1. Extract raw tile data
                    tile_data, _ = czi.read_image(M=m)
                    tile_data = np.squeeze(tile_data) 
                    
                    # 2. Fix Zeiss BGR to RGB color swap
                    if len(tile_data.shape) == 3 and tile_data.shape[0] == 3:
                        tile_data = np.moveaxis(tile_data, 0, -1)
                        tile_data = tile_data[..., ::-1] 
                        
                    tile_name = f"tile_{m:02d}.tiff"
                    tifffile.imwrite(os.path.join(temp_dir, tile_name), tile_data, photometric='rgb')
                    
                    # 3. Extract mechanical coordinates for the map
                    bbox = czi.get_mosaic_tile_bounding_box(M=m)
                    f.write(f"{tile_name}; ; ({bbox.x}, {bbox.y})\n")
                    
            # --- STAGE 2: FIJI PHASE CORRELATION STITCHING ---
            print("  -> Raw data secured. Handing over to Fiji for seamless blending...")
            macro_path = os.path.join(temp_dir, "stitch.ijm")
            
            # We tell Fiji to read the TileConfiguration.txt, compute pixel overlaps, and erase seams
            macro_code = f"""
            run("Grid/Collection stitching", "type=[Positions from file] order=[Defined by TileConfiguration] directory=[{temp_dir}] layout_file=TileConfiguration.txt fusion_method=[Linear Blending] regression_threshold=0.30 max/avg_displacement_threshold=2.50 absolute_displacement_threshold=3.50 compute_overlap subpixel_accuracy computation_parameters=[Save memory (but be slower)] image_output=[Fuse and display]");
            saveAs("Tiff", "{out_tiff_path}");
            run("Close All");
            run("Quit");
            """
            with open(macro_path, "w") as f:
                f.write(macro_code)
                
            cmd = [FIJI_EXECUTABLE, "--headless", "--mem=10G", "-macro", macro_path]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            if os.path.exists(out_tiff_path):
                print(f"  -> Success: Flawless stitch saved to {base_name}.tiff")
            else:
                print("  -> Error: Fiji failed to output the TIFF.")
                
        except Exception as e:
            print(f"  -> ERROR on {filename}: {e}")
            
        finally:
            # --- STAGE 3: CLEANUP ---
            # Deletes the temporary tiles to save your hard drive space
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

if __name__ == "__main__":
    perfect_pipeline_stitch()